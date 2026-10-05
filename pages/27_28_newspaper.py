"""M28: public news and a browser-local reading desk."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib
import time

import streamlit as st

from utils import newspaper_component
# Cloud can replace the page while retaining its previously imported services.
# Refresh an older service after a source or cache contract changes.
if getattr(newspaper_component, "NEWSPAPER_SERVICE_VERSION", 0) < 3:
    newspaper_component = importlib.reload(newspaper_component)

from utils.newspaper_component import (
    cached_newspaper_article,
    cached_newspaper_feed,
    declare_newspaper_component,
)
from utils.ui_theme import render_home_link


COMPONENT_KEY = "newspaper-live-v1"
PROCESSED_KEY = "_newspaper_processed_nonce"
LAST_FEED_KEY = "_newspaper_last_feed"
DISPLAY_FEED_KEY = "_newspaper_display_feed"
DETAIL_KEY = "_newspaper_article_detail"
REFRESH_KEY = "_newspaper_refreshed_at"


st.set_page_config(page_title="M28·Newspaper", page_icon="📰", layout="wide")
render_home_link()
st.markdown("### 📰 M28·Newspaper")
st.caption(
    "个人 · 多来源公开新闻与 AI 专版｜按来源要求更新；综合新闻缓存最长 15 分钟，官方 AI 信源最长 2 小时。读取失败可稍后重试。"
    "推荐偏好、收藏与笔记仅保存在当前浏览器，尚未提供跨设备同步。"
)

# Streamlit exposes the latest component value before the script reruns. Handle
# it before rendering to return the result without a second, recursive rerun.
request = st.session_state.get(COMPONENT_KEY)
is_new_request = (
    isinstance(request, dict)
    and isinstance(request.get("action"), str)
    and request.get("action") in {"read", "refresh"}
    and isinstance(request.get("nonce"), str)
    and 0 < len(request["nonce"]) <= 120
    and request["nonce"] != st.session_state.get(PROCESSED_KEY)
)
request_message = ""
if is_new_request:
    st.session_state[PROCESSED_KEY] = request["nonce"]
    if request["action"] == "refresh":
        now = time.monotonic()
        last_refresh = st.session_state.get(REFRESH_KEY)
        if last_refresh is None or now - last_refresh >= 30:
            cached_newspaper_feed.clear()
            st.session_state[REFRESH_KEY] = now
        else:
            request_message = "刚刚已检查新闻来源，请稍后再刷新。"

if is_new_request and request["action"] == "read" and st.session_state.get(DISPLAY_FEED_KEY):
    # Resolve the click against the exact feed already displayed to this reader.
    feed = st.session_state[DISPLAY_FEED_KEY]
else:
    try:
        with st.spinner("正在读取新闻来源…"):
            feed = cached_newspaper_feed()
    except Exception:
        # Do not expose transport internals or secrets through a public page.
        feed = {
            "articles": [],
            "sources": [],
            "errors": ["新闻来源暂时无法读取，请稍后刷新。"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

if feed.get("articles") and not feed.get("stale"):
    st.session_state[LAST_FEED_KEY] = feed
elif not feed.get("articles") and st.session_state.get(LAST_FEED_KEY):
    failed_feed = feed
    feed = deepcopy(st.session_state[LAST_FEED_KEY])
    feed["stale"] = True
    feed["sources"] = failed_feed.get("sources", [])
    feed["errors"] = [
        "此次更新未取得新闻，继续显示本次会话中上次成功读取的内容。",
        *failed_feed.get("errors", []),
    ]
    feed["attempted_at"] = failed_feed.get("fetched_at")

st.session_state[DISPLAY_FEED_KEY] = feed

if is_new_request and request["action"] == "read":
    # The browser sends an article ID only. Never fetch a URL supplied by it.
    article_id = request.get("id")
    article = next(
        (item for item in feed.get("articles", []) if item.get("id") == article_id),
        None,
    ) if isinstance(article_id, str) else None
    if article:
        try:
            with st.spinner("正在读取原文…"):
                detail = cached_newspaper_article(article)
        except Exception:
            detail = {
                "id": article_id,
                "status": "error",
                "paragraphs": [],
                "message": "暂时无法提取正文，可阅读摘要或打开原文。",
            }
    else:
        detail = {
            "id": article_id if isinstance(article_id, str) else "",
            "status": "summary",
            "paragraphs": [],
            "message": "该条目已不在本次新闻列表中，可阅读本地收藏快照或打开原文。",
        }
    st.session_state[DETAIL_KEY] = detail

newspaper = declare_newspaper_component()
newspaper(
    feed=feed,
    article_detail=st.session_state.get(DETAIL_KEY),
    request_nonce=request.get("nonce") if is_new_request else None,
    request_message=request_message,
    key=COMPONENT_KEY,
    default=None,
)
