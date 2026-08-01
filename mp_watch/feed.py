# -*- coding: utf-8 -*-
"""免费发现源：RSS / 简单 JSON 列表。"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element

import requests

from .normalize import pick_article_url

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class FeedItem:
    title: str
    url: str
    published: str
    source_name: str
    raw: Dict[str, Any]


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _child_text(node: Element, names: set[str]) -> str:
    for child in list(node):
        if _local(child.tag) in names:
            return (child.text or "").strip()
    return ""


def _child_attr(node: Element, names: set[str], attr: str) -> str:
    for child in list(node):
        if _local(child.tag) in names:
            return (child.attrib.get(attr) or "").strip()
    return ""


def _parse_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    # ISO-ish
    if re_match_iso(text):
        return text[:10]
    try:
        dt = parsedate_to_datetime(text)
        return dt.date().isoformat()
    except Exception:
        return text[:10] if len(text) >= 10 else text


def re_match_iso(text: str) -> bool:
    return len(text) >= 10 and text[0:4].isdigit() and text[4] in "-/"


def parse_rss_xml(content: str, source_name: str) -> List[FeedItem]:
    root = ET.fromstring(content)
    items: List[FeedItem] = []

    # RSS 2.0: channel/item ; Atom: entry
    candidates: List[Element] = []
    for node in root.iter():
        local = _local(node.tag)
        if local in {"item", "entry"}:
            candidates.append(node)

    for node in candidates:
        title = _child_text(node, {"title"})
        link = _child_text(node, {"link", "id", "guid"})
        if not link:
            link = _child_attr(node, {"link"}, "href")
        description = _child_text(node, {"description", "summary", "content"})
        pub = _child_text(node, {"pubDate", "published", "updated", "date"})
        url = pick_article_url(link, description, title)
        if not url:
            continue
        items.append(
            FeedItem(
                title=title or url,
                url=url,
                published=_parse_date(pub),
                source_name=source_name,
                raw={"link": link, "description": description[:200] if description else ""},
            )
        )
    return items


def parse_json_feed(content: str, source_name: str) -> List[FeedItem]:
    data = json.loads(content)
    rows: List[Any]
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("items", "articles", "data", "list", "entries"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
        else:
            rows = []
    else:
        rows = []

    items: List[FeedItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("name") or "")
        link = str(row.get("url") or row.get("link") or row.get("source") or "")
        desc = str(row.get("description") or row.get("summary") or "")
        pub = str(row.get("published") or row.get("pubDate") or row.get("date") or "")
        url = pick_article_url(link, desc, title)
        if not url:
            continue
        items.append(
            FeedItem(
                title=title or url,
                url=url,
                published=_parse_date(pub),
                source_name=source_name,
                raw={k: row.get(k) for k in ("id", "author") if k in row},
            )
        )
    return items


def fetch_feed(
    feed_url: str,
    source_name: str,
    kind: str = "rss",
    timeout: int = 30,
    session: Optional[requests.Session] = None,
) -> List[FeedItem]:
    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/json, text/xml, */*"}
    resp = sess.get(feed_url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    text = resp.text
    kind = (kind or "rss").lower().strip()
    if kind == "json":
        return parse_json_feed(text, source_name)
    # 自动：JSON 开头则当 JSON
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return parse_json_feed(text, source_name)
    return parse_rss_xml(text, source_name)
