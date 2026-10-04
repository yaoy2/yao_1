"""Register Newspaper from an importable module for multipage/Cloud runners."""

from pathlib import Path
from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as components

from utils.newspaper_data import fetch_newspaper_article, load_newspaper_feed
from utils.newspaper_ai_sources import fetch_ai_official_article, load_ai_official_feed


@st.cache_data(ttl=7200, max_entries=1, show_spinner=False)
def cached_ai_official_feed():
    """Official AI RSS changes slowly; share its cache independently."""
    return load_ai_official_feed()


@st.cache_data(ttl=900, max_entries=1, show_spinner=False)
def cached_newspaper_feed():
    """Share a short-lived public feed without storing personal reading data."""
    result = {"articles": [], "sources": [], "errors": [],
              "fetched_at": datetime.now(timezone.utc).isoformat()}
    seen_urls = set()
    for label, loader in (("综合新闻", load_newspaper_feed),
                          ("官方 AI 信源", cached_ai_official_feed)):
        try:
            feed = loader()
        except Exception:
            result["errors"].append(label + "暂时无法读取，可稍后更新。")
            result["sources"].append({"id": label, "name": label, "status": "error",
                                      "count": 0, "error": "本次读取失败"})
            continue
        result["sources"].extend(feed.get("sources", []))
        result["errors"].extend(feed.get("errors", []))
        for article in feed.get("articles", []):
            identity = article.get("url") or article.get("id")
            if identity and identity not in seen_urls:
                seen_urls.add(identity)
                result["articles"].append(article)
    return result


@st.cache_data(ttl=3600, max_entries=192, show_spinner=False)
def cached_newspaper_article(article):
    detail = (fetch_ai_official_article(article)
              if article.get("source_family") == "ai_official"
              else fetch_newspaper_article(article))
    if detail.get("status") == "error":
        # A temporary transport failure must not become a one-hour cached result.
        raise RuntimeError("News article temporarily unavailable")
    return detail


def declare_newspaper_component():
    frontend = Path(__file__).resolve().parents[1] / "integrations" / "newspaper" / "frontend"
    return components.declare_component("newspaper", path=str(frontend))
