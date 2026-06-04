from __future__ import annotations

from html import escape
from pathlib import Path

from .models import RadarState


def build_feed(state: RadarState, site_url: str = "") -> str:
    link = site_url or "https://github.com/yaoy2/yao_1"
    title = f"Codex Radar Lite: {state.status}"
    description = f"{state.reason} 24h={state.probability_24h}%, 48h={state.probability_48h}%"
    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Codex Radar Lite</title>
    <link>{escape(link)}</link>
    <description>Codex quota reset radar alerts</description>
    <item>
      <title>{escape(title)}</title>
      <link>{escape(link)}</link>
      <guid>{escape(state.checked_at)}-{escape(state.status)}</guid>
      <pubDate>{escape(state.checked_at)}</pubDate>
      <description>{escape(description)}</description>
    </item>
  </channel>
</rss>
"""


def write_feed(path: Path, state: RadarState, site_url: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_feed(state, site_url), encoding="utf-8")

