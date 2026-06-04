from __future__ import annotations

import re
import json
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from .models import Signal, isoformat


USER_AGENT = "yao-1-codex-radar-lite/1.0"


def fetch_url(url: str, timeout: int = 20) -> str:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
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


def collect_source(source: dict[str, Any]) -> list[Signal]:
    if not source.get("enabled", True):
        return []
    body = fetch_url(str(source["url"]))
    kind = str(source.get("kind", "html")).lower()
    if kind == "statuspage_incidents":
        return extract_statuspage_incidents(body, source)
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
