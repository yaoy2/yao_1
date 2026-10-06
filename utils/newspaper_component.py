"""Register Newspaper from an importable module for multipage/Cloud runners."""

from pathlib import Path
from datetime import datetime, timezone
import importlib

import streamlit as st
import streamlit.components.v1 as components

from utils import newspaper_interviews as _newspaper_interviews
if getattr(_newspaper_interviews, "NEWSPAPER_INTERVIEWS_VERSION", 0) < 2:
    _newspaper_interviews = importlib.reload(_newspaper_interviews)

from utils import newspaper_data as _newspaper_data
if getattr(_newspaper_data, "NEWSPAPER_SOURCE_VERSION", 0) < 4:
    _newspaper_data = importlib.reload(_newspaper_data)

from utils import newspaper_sources as _newspaper_sources
if getattr(_newspaper_sources, "NEWSPAPER_MEDIA_VERSION", 0) < 3:
    _newspaper_sources = importlib.reload(_newspaper_sources)

from utils import newspaper_daily as _newspaper_daily
if getattr(_newspaper_daily, "NEWSPAPER_DAILY_VERSION", 0) < 3:
    _newspaper_daily = importlib.reload(_newspaper_daily)

from utils.newspaper_data import fetch_newspaper_article, load_newspaper_feed
from utils.newspaper_ai_sources import fetch_ai_official_article, load_ai_official_feed
from utils.newspaper_sources import INTERVIEW_SOURCE_IDS, fetch_extended_article, load_extended_news_feed
from utils.newspaper_daily import read_daily_feed
from utils.newspaper_interviews import INTERVIEW_CATEGORY, without_expired_interviews


NEWSPAPER_SERVICE_VERSION = 6


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def _read_daily_feed():
    # Credentials stay server-side and are never component arguments.
    return read_daily_feed(secrets=st.secrets)


def newspaper_feed_for_page(force_live=False):
    """Prefer a valid completed edition; manual refresh still reads all sources."""
    if not force_live:
        try:
            daily = _read_daily_feed()
            if daily:
                expires_at = datetime.fromisoformat(daily["expires_at"])
                checked_sources = {source.get("id") for source in daily.get("sources", [])}
                if (expires_at.tzinfo and expires_at > datetime.now(timezone.utc)
                        and INTERVIEW_SOURCE_IDS <= checked_sources):
                    return daily
        except Exception:
            # A missing private snapshot must never break public news reading.
            pass
    feed = cached_newspaper_feed()
    return {**feed, "articles": without_expired_interviews(feed.get("articles", []))}


class _IncompleteFeed(Exception):
    """Carry partial or non-reusable public results through cache decorators."""

    def __init__(self, feed):
        super().__init__("Some public sources are temporarily unavailable")
        self.feed = feed


def _require_complete(feed):
    if feed.get("errors") or any(source.get("status") == "error"
                                 for source in feed.get("sources", [])):
        raise _IncompleteFeed(feed)
    return feed


def _require_reusable(feed, cache_seconds):
    policy = feed.get("cache_policy") or {}
    if policy.get("reuse") is False or policy.get("store") is False:
        raise _IncompleteFeed(feed)
    max_age = policy.get("max_age_seconds")
    if isinstance(max_age, (int, float)) and max_age <= cache_seconds:
        # A fixed-TTL cache cannot promise a shorter publisher expiry. Returning
        # it without caching also avoids adding time spent in a shorter layer.
        raise _IncompleteFeed(feed)
    return feed


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def _recent_ai_official_feed():
    # A short retry window avoids hammering an unavailable publisher.
    return _require_reusable(load_ai_official_feed(), 60)


@st.cache_data(ttl=7200, max_entries=1, show_spinner=False)
def _complete_ai_official_feed():
    return _require_complete(_require_reusable(_recent_ai_official_feed(), 7200))


def cached_ai_official_feed():
    """Cache successful AI batches for two hours, failures for only one minute."""
    try:
        return _complete_ai_official_feed()
    except _IncompleteFeed as error:
        return error.feed


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def _recent_newspaper_feed(source_version):
    """Share the retry window, including partial results, across viewers."""
    result = {"articles": [], "sources": [], "errors": [],
              "cache_policy": {"store": True, "reuse": True},
              "fetched_at": datetime.now(timezone.utc).isoformat()}
    seen_urls = {}
    for label, loader in (("综合新闻", load_newspaper_feed),
                          ("官方 AI 信源", cached_ai_official_feed),
                          ("扩展媒体", load_extended_news_feed)):
        try:
            feed = loader()
        except Exception:
            result["errors"].append(label + "暂时无法读取，可稍后更新。")
            result["sources"].append({"id": label, "name": label, "status": "error",
                                      "count": 0, "error": "本次读取失败"})
            continue
        result["sources"].extend(feed.get("sources", []))
        result["errors"].extend(feed.get("errors", []))
        for key in ("store", "reuse"):
            if (feed.get("cache_policy") or {}).get(key) is False:
                result["cache_policy"][key] = False
        max_age = (feed.get("cache_policy") or {}).get("max_age_seconds")
        if isinstance(max_age, (int, float)):
            previous = result["cache_policy"].get("max_age_seconds", max_age)
            result["cache_policy"]["max_age_seconds"] = min(previous, max_age)
        for article in feed.get("articles", []):
            identity = article.get("url") or article.get("id")
            if identity and identity not in seen_urls:
                seen_urls[identity] = len(result["articles"])
                result["articles"].append(article)
            elif (identity and article.get("category") == INTERVIEW_CATEGORY
                  and result["articles"][seen_urls[identity]].get("category") != INTERVIEW_CATEGORY):
                # A link also appearing on a general book page keeps its verified
                # interview membership when the dedicated source is available.
                result["articles"][seen_urls[identity]] = article
    return _require_reusable(result, 60)


@st.cache_data(ttl=900, max_entries=1, show_spinner=False)
def _complete_newspaper_feed(source_version):
    return _require_complete(_require_reusable(_recent_newspaper_feed(source_version), 900))


def cached_newspaper_feed():
    """Never turn a temporary source outage into a fifteen-minute empty feed."""
    try:
        # Include the source contract in both shared cache keys on Cloud upgrades.
        return _complete_newspaper_feed(NEWSPAPER_SERVICE_VERSION)
    except _IncompleteFeed as error:
        return error.feed


def _clear_combined_feed():
    _read_daily_feed.clear()
    _complete_newspaper_feed.clear()
    _recent_newspaper_feed.clear()
    # Manual refresh retries failed AI sources; successful two-hour batches stay.
    _recent_ai_official_feed.clear()


def _clear_ai_feed():
    _complete_ai_official_feed.clear()
    _recent_ai_official_feed.clear()


# Preserve the cache API used by the page and test fixtures.
cached_newspaper_feed.clear = _clear_combined_feed
cached_ai_official_feed.clear = _clear_ai_feed


@st.cache_data(ttl=3600, max_entries=192, show_spinner=False)
def _cached_newspaper_article(article):
    family = article.get("source_family")
    if family == "ai_official":
        detail = fetch_ai_official_article(article)
    elif family == "public_media":
        detail = fetch_extended_article(article)
    else:
        detail = fetch_newspaper_article(article)
    if detail.get("status") == "error":
        # A temporary transport failure must not become a one-hour cached result.
        raise RuntimeError("News article temporarily unavailable")
    return _require_reusable(detail, 3600)


def cached_newspaper_article(article):
    try:
        return _cached_newspaper_article(article)
    except _IncompleteFeed as error:
        return error.feed


cached_newspaper_article.clear = _cached_newspaper_article.clear


def declare_newspaper_component():
    frontend = Path(__file__).resolve().parents[1] / "integrations" / "newspaper" / "frontend"
    return components.declare_component("newspaper", path=str(frontend))
