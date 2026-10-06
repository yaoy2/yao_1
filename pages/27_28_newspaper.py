"""M28: public news with an authenticated, private reading library."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib
import hashlib
import hmac
import os
import time

import streamlit as st

from utils import newspaper_component
# Cloud can replace the page while retaining its previously imported services.
# Refresh an older service after a source or cache contract changes.
if getattr(newspaper_component, "NEWSPAPER_SERVICE_VERSION", 0) < 6:
    newspaper_component = importlib.reload(newspaper_component)

from utils.newspaper_component import (
    cached_newspaper_article,
    cached_newspaper_feed,
    newspaper_feed_for_page,
    declare_newspaper_component,
)
from utils.ui_theme import render_home_link
from utils import budget_auth, newspaper_reader_sync

if getattr(budget_auth, "BUDGET_AUTH_VERSION", 0) < 2:
    budget_auth = importlib.reload(budget_auth)


COMPONENT_KEY = "newspaper-live-v1"
PROCESSED_KEY = "_newspaper_processed_nonce"
LAST_FEED_KEY = "_newspaper_last_feed"
DISPLAY_FEED_KEY = "_newspaper_display_feed"
DETAIL_KEY = "_newspaper_article_detail"
REFRESH_KEY = "_newspaper_refreshed_at"
SYNC_RESPONSE_KEY = "_newspaper_reader_sync_response"
AUTH_KEY = "_newspaper_reader_auth"


def render_sync_access():
    """Keep access checks on the server; never send passwords to the iframe."""
    password = budget_auth.get_budget_password(st.secrets, os.environ)
    fingerprint = hashlib.sha256(password.encode("utf-8")).hexdigest() if password else ""
    authenticated = bool(fingerprint and isinstance(st.session_state.get(AUTH_KEY), str)
                         and hmac.compare_digest(st.session_state[AUTH_KEY], fingerprint))
    if not authenticated:
        st.session_state.pop(AUTH_KEY, None)
        st.session_state.pop(SYNC_RESPONSE_KEY, None)
    if not password:
        st.caption("跨设备同步暂未启用：服务器尚未配置工具箱访问密码。当前浏览器记录继续保留。")
        return False
    with st.expander("跨设备同步 · " + ("已解锁" if authenticated else "输入访问密码启用"), expanded=False):
        st.caption("同步收藏、已保存正文、笔记、阅读状态和推荐偏好到您的私有数据仓库。"
                   "每台设备需单独解锁；使用预算台账的访问密码。仅适用于您自己的设备，"
                   "停止同步后，本浏览器已有记录仍然保留。")
        if authenticated:
            if st.button("停止本次会话同步", key="newspaper_sync_lock"):
                st.session_state.pop(AUTH_KEY, None)
                st.session_state.pop(SYNC_RESPONSE_KEY, None)
                st.rerun()
        else:
            with st.form("newspaper_sync_auth", clear_on_submit=True):
                candidate = st.text_input("工具箱访问密码", type="password")
                submitted = st.form_submit_button("启用跨设备同步")
            if submitted:
                now = time.monotonic()
                failures = [at for at in st.session_state.get("_newspaper_auth_failures", [])
                            if now - at < 60]
                if len(failures) >= 5:
                    st.error("本次会话尝试次数较多，请一分钟后再试。")
                elif budget_auth.is_budget_password_valid(candidate, password):
                    st.session_state[AUTH_KEY] = fingerprint
                    st.session_state.pop("_newspaper_auth_failures", None)
                    old_request = st.session_state.get(COMPONENT_KEY)
                    if isinstance(old_request, dict) and old_request.get("action") == "reader_sync":
                        st.session_state[PROCESSED_KEY] = old_request.get("nonce")
                    st.rerun()
                else:
                    st.session_state["_newspaper_auth_failures"] = [*failures, now]
                    st.error("访问密码不正确，尚未读取或上传个人记录。")
    return authenticated


st.set_page_config(page_title="M28·Newspaper", page_icon="📰", layout="wide")
render_home_link()
st.markdown("### 📰 M28·Newspaper")
st.caption(
    "个人 · 多来源公开新闻与 AI 专版｜优先读取已完成的有效日报；尚无日报时即时获取，手动更新可检查全部来源。"
    "访谈与阅读专栏收录近 7 天各行业、各领域的人物专访与对话。"
    "解锁跨设备同步后，收藏、笔记和推荐偏好会自动合并到私有仓库；未解锁时继续保存在当前浏览器。"
)
sync_enabled = render_sync_access()

if st.session_state.get("_newspaper_display_version") != newspaper_component.NEWSPAPER_SERVICE_VERSION:
    # A page retained in an existing Cloud session must also acquire new sources.
    st.session_state.pop(DISPLAY_FEED_KEY, None)
    st.session_state.pop(LAST_FEED_KEY, None)
    st.session_state["_newspaper_display_version"] = newspaper_component.NEWSPAPER_SERVICE_VERSION

# Streamlit exposes the latest component value before the script reruns. Handle
# it before rendering to return the result without a second, recursive rerun.
request = st.session_state.get(COMPONENT_KEY)
is_new_request = (
    isinstance(request, dict)
    and isinstance(request.get("action"), str)
    and request.get("action") in {"read", "refresh", "reader_sync"}
    and isinstance(request.get("nonce"), str)
    and 0 < len(request["nonce"]) <= 120
    and request["nonce"] != st.session_state.get(PROCESSED_KEY)
)
request_message = ""
refresh_allowed = False
if is_new_request:
    st.session_state[PROCESSED_KEY] = request["nonce"]
    if request["action"] == "refresh":
        now = time.monotonic()
        last_refresh = st.session_state.get(REFRESH_KEY)
        if last_refresh is None or now - last_refresh >= 30:
            cached_newspaper_feed.clear()
            st.session_state[REFRESH_KEY] = now
            refresh_allowed = True
        else:
            request_message = "刚刚已检查新闻来源，请稍后再刷新。"
    elif request["action"] == "reader_sync":
        # A forged component message cannot grant access to personal data.
        if not sync_enabled:
            result = {"status": "locked", "message": "请先在页面上方输入访问密码启用同步。"}
        else:
            try:
                if request.get("operation") == "load":
                    result = newspaper_reader_sync.load_reader_state(secrets=st.secrets)
                elif request.get("operation") == "save" and "expected_sha" in request:
                    result = newspaper_reader_sync.save_reader_state(
                        request.get("document"), request["expected_sha"], secrets=st.secrets)
                else:
                    result = {"status": "error", "message": "同步请求不完整，本地记录保持原样。"}
            except Exception:
                result = {"status": "error", "message": "同步暂未完成，本地记录保持原样，请稍后重试。"}
        st.session_state[SYNC_RESPONSE_KEY] = {**result, "nonce": request["nonce"]}

if st.session_state.get(DISPLAY_FEED_KEY) and not refresh_allowed:
    # Resolve the click against the exact feed already displayed to this reader.
    feed = st.session_state[DISPLAY_FEED_KEY]
else:
    try:
        with st.spinner("正在读取新闻来源…"):
            feed = newspaper_feed_for_page(force_live=refresh_allowed)
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

if feed.get("delivery") == "daily":
    st.caption("定时日报 · " + str(feed.get("edition_date", ""))
               + " · 采集完成：" + str(feed.get("fetched_at", ""))
               + "。日报只收录允许保存的来源；点击更新可读取全部即时来源。")

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
    reader_sync=({**st.session_state.get(SYNC_RESPONSE_KEY, {"status": "ready"}), "enabled": True}
                 if sync_enabled else {"enabled": False, "status": "locked"}),
    key=COMPONENT_KEY,
    default=None,
)
