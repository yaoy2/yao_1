from __future__ import annotations

import re
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from .models import Signal, isoformat


USER_AGENT = "yao-1-codex-radar-lite/1.0"
REDDIT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def fetch_url(url: str, timeout: int = 20, extra_headers: dict[str, str] | None = None) -> str:
    headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.text


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)


def normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def extract_matching_signals(text: str, source: dict[str, Any], now: datetime | None = None) -> list[Signal]:
    checked_at = isoformat(now or datetime.now(timezone.utc))
    keywords = [keyword.lower() for keyword in source.get("keywords", [])]
    if not keywords:
        keywords = ["codex", "rate limit", "usage limit", "quota"]

    signals: list[Signal] = []
    seen: set[str] = set()
    lines = [normalize_line(line) for line in text.splitlines()]
    for line in lines:
        lowered = line.lower()
        if len(line) < 8 or not any(keyword in lowered for keyword in keywords):
            continue
        title = line[:140]
        if title in seen:
            continue
        seen.add(title)
        tags = [keyword for keyword in keywords if keyword in lowered]
        signals.append(
            Signal(
                source_id=str(source.get("id", "source")),
                source_name=str(source.get("name", source.get("id", "source"))),
                title=title,
                summary=line[:360],
                url=str(source.get("url", "")),
                observed_at=checked_at,
                weight=int(source.get("weight", 1)),
                tags=tags,
            )
        )
    return signals[:20]


def extract_statuspage_incidents(payload: str, source: dict[str, Any], now: datetime | None = None) -> list[Signal]:
    checked_at = isoformat(now or datetime.now(timezone.utc))
    data = json.loads(payload)
    keywords = [keyword.lower() for keyword in source.get("keywords", [])]
    signals: list[Signal] = []
    for incident in data.get("incidents", [])[:20]:
        parts = [
            str(incident.get("name", "")),
            str(incident.get("status", "")),
            " ".join(str(component.get("name", "")) for component in incident.get("components", [])),
            " ".join(str(update.get("body", "")) for update in incident.get("incident_updates", [])[:3]),
        ]
        text = normalize_line(" ".join(parts))
        lowered = text.lower()
        if keywords and not any(keyword in lowered for keyword in keywords):
            continue
        signals.append(
            Signal(
                source_id=str(source.get("id", "source")),
                source_name=str(source.get("name", source.get("id", "source"))),
                title=str(incident.get("name", "Status incident"))[:140],
                summary=text[:500],
                url=str(incident.get("shortlink") or source.get("url", "")),
                observed_at=str(incident.get("updated_at") or incident.get("created_at") or checked_at),
                weight=int(source.get("weight", 1)),
                tags=[keyword for keyword in keywords if keyword in lowered],
            )
        )
    return signals


def extract_statuspage_components(payload: str, source: dict[str, Any], now: datetime | None = None) -> list[Signal]:
    """Extract signals from Statuspage summary.json (component health)."""
    checked_at = isoformat(now or datetime.now(timezone.utc))
    data = json.loads(payload)
    keywords = [keyword.lower() for keyword in source.get("keywords", [])]
    signals: list[Signal] = []
    for component in data.get("components", []):
        status = str(component.get("status", ""))
        name = str(component.get("name", ""))
        text = f"{name} {status}"
        lowered = text.lower()
        if keywords and not any(keyword in lowered for keyword in keywords):
            continue
        # Only alert on non-operational statuses
        if status == "operational":
            continue
        signals.append(
            Signal(
                source_id=str(source.get("id", "statuspage")),
                source_name=str(source.get("name", "Statuspage")),
                title=f"{name}: {status}"[:140],
                summary=f"Component '{name}' status: {status}"[:500],
                url=str(data.get("page", {}).get("url", source.get("url", ""))),
                observed_at=checked_at,
                weight=int(source.get("weight", 1)),
                tags=[keyword for keyword in keywords if keyword in lowered],
            )
        )
    return signals


def extract_rss_feed(payload: str, source: dict[str, Any], now: datetime | None = None) -> list[Signal]:
    """Extract signals from RSS/Atom feeds (Reddit, etc.)."""
    checked_at = isoformat(now or datetime.now(timezone.utc))
    keywords = [keyword.lower() for keyword in source.get("keywords", [])]
    signals: list[Signal] = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return signals
    # Atom feed
    entries = root.findall(".//atom:entry", ns) or root.findall(".//entry")
    # RSS feed
    items = root.findall(".//item")
    for entry in entries[:25]:
        title = (entry.findtext("atom:title", "", ns) or entry.findtext("title", "")).strip()
        content = (entry.findtext("atom:content", "", ns) or entry.findtext("atom:summary", "", ns) or entry.findtext("content", "") or entry.findtext("summary", ""))[:300]
        link_el = entry.find("atom:link", ns) or entry.find("link")
        link = link_el.get("href", "") if link_el is not None else ""
        updated = (entry.findtext("atom:updated", "", ns) or entry.findtext("atom:published", "", ns) or entry.findtext("updated", "") or entry.findtext("published", ""))
        # Parse HTML content to plain text
        if "<" in content:
            content = html_to_text(content)[:300]
        text = f"{title} {content}"
        lowered = text.lower()
        if keywords and not any(keyword in lowered for keyword in keywords):
            continue
        signals.append(
            Signal(
                source_id=str(source.get("id", "rss")),
                source_name=str(source.get("name", "RSS")),
                title=title[:140],
                summary=text[:500],
                url=link or str(source.get("url", "")),
                observed_at=updated or checked_at,
                weight=int(source.get("weight", 1)),
                tags=[keyword for keyword in keywords if keyword in lowered],
            )
        )
    for item in items[:25]:
        title = (item.findtext("title", "")).strip()
        content = (item.findtext("description", "") or item.findtext("content:encoded", ""))[:300]
        link = (item.findtext("link", "")).strip()
        pub_date = item.findtext("pubDate", "")
        if "<" in content:
            content = html_to_text(content)[:300]
        text = f"{title} {content}"
        lowered = text.lower()
        if keywords and not any(keyword in lowered for keyword in keywords):
            continue
        signals.append(
            Signal(
                source_id=str(source.get("id", "rss")),
                source_name=str(source.get("name", "RSS")),
                title=title[:140],
                summary=text[:500],
                url=link or str(source.get("url", "")),
                observed_at=pub_date or checked_at,
                weight=int(source.get("weight", 1)),
                tags=[keyword for keyword in keywords if keyword in lowered],
            )
        )
    return signals


def extract_community_json(payload: str, source: dict[str, Any], now: datetime | None = None) -> list[Signal]:
    """Extract signals from OpenAI Community Forum search JSON."""
    checked_at = isoformat(now or datetime.now(timezone.utc))
    data = json.loads(payload)
    keywords = [keyword.lower() for keyword in source.get("keywords", [])]
    signals: list[Signal] = []
    # Build blurb map from posts (posts have blurb, topics have title)
    blurb_map: dict[int, str] = {}
    for post in data.get("posts", []):
        topic_id = post.get("topic_id")
        if topic_id:
            blurb_map[topic_id] = str(post.get("blurb", ""))[:300]
    for topic in data.get("topics", [])[:20]:
        title = str(topic.get("title", ""))
        blurb = blurb_map.get(topic.get("id", ""), "")
        text = f"{title} {blurb}"
        lowered = text.lower()
        if keywords and not any(keyword in lowered for keyword in keywords):
            continue
        topic_id = topic.get("id", "")
        slug = topic.get("slug", "")
        url = f"https://community.openai.com/t/{slug}/{topic_id}" if slug and topic_id else str(source.get("url", ""))
        created = topic.get("created_at") or topic.get("bumped_at")
        observed_at = created if created else checked_at
        signals.append(
            Signal(
                source_id=str(source.get("id", "community")),
                source_name=str(source.get("name", "Community")),
                title=title[:140],
                summary=text[:500],
                url=url,
                observed_at=observed_at,
                weight=int(source.get("weight", 1)),
                tags=[keyword for keyword in keywords if keyword in lowered],
            )
        )
    return signals


def collect_source(source: dict[str, Any]) -> list[Signal]:
    if not source.get("enabled", True):
        return []
    kind = str(source.get("kind", "html")).lower()
    extra_headers = None
    if kind == "rss":
        extra_headers = {"User-Agent": REDDIT_USER_AGENT}
    body = fetch_url(str(source["url"]), extra_headers=extra_headers)
    if kind == "statuspage_incidents":
        return extract_statuspage_incidents(body, source)
    if kind == "statuspage_components":
        return extract_statuspage_components(body, source)
    if kind == "rss":
        return extract_rss_feed(body, source)
    if kind == "community_json":
        return extract_community_json(body, source)
    text = html_to_text(body) if kind == "html" else body
    return extract_matching_signals(text, source)


def collect_all(sources_config: dict[str, Any]) -> list[Signal]:
    signals: list[Signal] = []
    for source in sources_config.get("sources", []):
        try:
            signals.extend(collect_source(source))
        except requests.RequestException as exc:
            signals.append(
                Signal(
                    source_id=str(source.get("id", "source")),
                    source_name=str(source.get("name", source.get("id", "source"))),
                    title="Source fetch failed",
                    summary=f"{type(exc).__name__}: {exc}",
                    url=str(source.get("url", "")),
                    observed_at=isoformat(),
                    weight=0,
                    tags=["fetch_error"],
                )
            )
    return dedupe_signals(signals)


def dedupe_signals(signals: list[Signal]) -> list[Signal]:
    by_title: dict[str, Signal] = {}
    for signal in signals:
        key = f"{signal.source_id}:{signal.title.lower()}"
        if key not in by_title or signal.weight > by_title[key].weight:
            by_title[key] = signal
    return list(by_title.values())
