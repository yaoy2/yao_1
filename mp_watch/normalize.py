# -*- coding: utf-8 -*-
"""公众号链接规范化，用于去重键。"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse, urlunparse


_SHORT_S = re.compile(r"/s/([A-Za-z0-9_-]+)")


def normalize_wechat_url(url: str) -> str:
    """把各种 mp.weixin 链接压成稳定主键，便于去重。"""
    raw = (url or "").strip()
    if not raw:
        return ""

    raw = raw.rstrip(").,，。；;]\"'")
    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = "https://" + raw.lstrip("/")
        parsed = urlparse(raw)

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    path = parsed.path or ""
    m = _SHORT_S.search(path)
    if m and "mp.weixin.qq.com" in host:
        return f"https://mp.weixin.qq.com/s/{m.group(1)}"

    qs = parse_qs(parsed.query)
    if "mp.weixin.qq.com" in host and path.rstrip("/") in {"/s", "/s/"}:
        biz = (qs.get("__biz") or [""])[0]
        mid = (qs.get("mid") or [""])[0]
        sn = (qs.get("sn") or [""])[0]
        idx = (qs.get("idx") or ["1"])[0]
        if biz and mid and sn:
            return f"https://mp.weixin.qq.com/s?__biz={biz}&mid={mid}&idx={idx}&sn={sn}"

    # 去掉 fragment 与常见追踪参数
    drop = {"chksm", "scene", "key", "ascene", "uin", "devicetype", "version", "exportkey", "pass_ticket"}
    kept = []
    for key, values in qs.items():
        if key.lower() in drop:
            continue
        for v in values:
            kept.append((key, v))
    kept.sort()
    query = "&".join(f"{k}={v}" for k, v in kept)
    clean = urlunparse(("https" if parsed.scheme in {"http", "https"} else parsed.scheme or "https", host, path, "", query, ""))
    return clean.rstrip("?")


def is_wechat_article_url(url: str) -> bool:
    u = (url or "").strip()
    if not u or any(ch.isspace() for ch in u):
        return False
    low = u.lower()
    if "mp.weixin.qq.com" not in low:
        return False
    return "/s/" in low or "/s?" in low or low.rstrip("/").endswith("/s")


def pick_article_url(*candidates: Optional[str]) -> str:
    for c in candidates:
        if not c:
            continue
        text = str(c).strip()
        # 先抽文本中的 mp 链接，避免把整段描述误当成 URL
        found = re.findall(r"https?://mp\.weixin\.qq\.com/[^\s\"'<>]+", text)
        for f in found:
            cleaned = f.rstrip(").,，。；;]\"'")
            if is_wechat_article_url(cleaned):
                return normalize_wechat_url(cleaned)
        if is_wechat_article_url(text):
            return normalize_wechat_url(text)
    return ""
