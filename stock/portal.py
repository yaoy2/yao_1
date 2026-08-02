"""Unified Streamlit renderer for the two stock research sections."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any, Iterable

import streamlit as st

from stock.runtime import ASTOCKLAB_ROOT, activate_astocklab_imports, snapshot_manifest
from stock.search_html.collector import search_archive, search_live


SEARCH_ROOT = Path(__file__).resolve().parent / "search_html"
LATEST_SEARCH_SNAPSHOT = SEARCH_ROOT / "data" / "latest.json"


@st.cache_data(show_spinner=False)
def load_search_snapshot() -> dict[str, Any]:
    return json.loads(LATEST_SEARCH_SNAPSHOT.read_text(encoding="utf-8"))


def _safe_url(value: object) -> str | None:
    url = str(value or "").strip()
    return url if url.startswith(("https://", "http://")) else None


def _labels(values: Iterable[object]) -> str:
    return " · ".join(str(value) for value in values if value)


def _render_post(item: dict[str, Any], *, key: str) -> None:
    source = str(item.get("source") or "来源未知")
    title = str(item.get("title") or "未命名内容")
    heat = float(item.get("heat_score") or item.get("max_heat_score") or 0)
    published = item.get("published_at") or item.get("snapshot_date") or "时间未知"
    themes = list(item.get("themes") or item.get("common_themes") or [])
    mentions = list(item.get("mentions") or [])
    mention_text = _labels(
        f"{entry.get('name') or entry.get('symbol')}（{entry.get('symbol')}）"
        for entry in mentions
        if isinstance(entry, dict)
    )
    with st.container(border=True):
        heading, score = st.columns([5, 1])
        heading.markdown(f"**{title}**")
        heading.caption(f"{source} · {published}")
        score.metric("热度", f"{heat:.0f}")
        if themes:
            st.caption("主题：" + _labels(themes))
        if mention_text:
            st.caption("涉及：" + mention_text)
        excerpt = str(item.get("excerpt") or item.get("summary") or "").strip()
        reason = str(item.get("why") or item.get("reason") or "").strip()
        if excerpt or reason:
            with st.expander("展开查看证据与判定"):
                if reason:
                    st.write("判定依据：", reason)
                if excerpt:
                    st.write(excerpt)
        url = _safe_url(item.get("url"))
        if url:
            st.link_button("打开原文", url, key=f"source_{key}")


def _render_posts(items: list[dict[str, Any]], *, prefix: str) -> None:
    if not items:
        st.info("当前没有符合条件的内容。")
        return
    columns = st.columns(2, gap="medium")
    for index, item in enumerate(items):
        with columns[index % 2]:
            _render_post(item, key=f"{prefix}_{index}")


def _render_pool_item(item: dict[str, Any], *, key: str) -> None:
    title = f"{item.get('name') or item.get('symbol')}（{item.get('symbol') or '代码未知'}）"
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption("主题：" + (_labels(item.get("themes") or []) or "未分类"))
        st.write(item.get("reason") or "暂无判定说明。")
        evidence = list(item.get("evidence") or [])
        with st.expander(f"查看 {len(evidence)} 条来源证据"):
            for index, entry in enumerate(evidence):
                st.markdown(f"**{entry.get('source', '来源未知')}｜{entry.get('title', '未命名')}**")
                st.caption(str(entry.get("published_at") or "时间未知"))
                if entry.get("excerpt"):
                    st.write(entry["excerpt"])
                url = _safe_url(entry.get("url"))
                if url:
                    st.link_button("打开该证据", url, key=f"pool_{key}_{index}")


def _render_source_health(payload: dict[str, Any]) -> None:
    health = payload.get("source_health") or {}
    if isinstance(health, list):
        entries = [
            (str(item.get("source") or "来源未知"), item)
            for item in health
            if isinstance(item, dict)
        ]
    elif isinstance(health, dict):
        entries = list(health.items())
    else:
        return
    columns = st.columns(max(1, len(entries)))
    for column, (source, status) in zip(columns, entries):
        if isinstance(status, dict):
            state = status.get("status") or status.get("state") or "未知"
            note = status.get("note") or status.get("message") or ""
            item_count = status.get("item_count")
        else:
            state, note, item_count = status, "", None
        column.metric(str(source), str(state))
        if item_count is not None:
            column.caption(f"本次公开条目：{item_count}")
        if note:
            column.caption(str(note))


def _render_search_results(payload: dict[str, Any]) -> None:
    counts = payload.get("source_counts") or {}
    summary = st.columns(3)
    summary[0].metric("结果", int(payload.get("count") or 0))
    summary[1].metric("雪球", int(counts.get("雪球") or 0))
    summary[2].metric("淘股吧", int(counts.get("淘股吧") or 0))
    statuses = payload.get("source_statuses") or []
    if statuses:
        for status in statuses:
            complete = bool(status.get("complete"))
            message = f"{status.get('source')}：{status.get('note') or status.get('status')}"
            (st.success if complete else st.warning)(message)
    if not payload.get("complete", True):
        st.warning("至少一个来源未完整返回；当前结果不能解释为“没有相关内容”。")
    st.caption(str(payload.get("scope") or ""))
    _render_posts(list(payload.get("results") or []), prefix="search")


def _render_search_form() -> None:
    search_scope = st.radio(
        "搜索范围",
        ["已发布快照", "实时公开搜索（最近7天）"],
        horizontal=True,
        help="实时搜索只访问公开入口；站点限制会被原样标记。",
    )
    query_col, sort_col = st.columns([4, 1])
    query = query_col.text_input(
        "个股、代码或关键词",
        placeholder="例如：蓝色光标、300058、AI营销",
        label_visibility="collapsed",
    )
    sort_label = sort_col.selectbox("排序", ["按热度", "按时间"], label_visibility="collapsed")
    if st.button("开始搜索", type="primary", disabled=not query.strip()):
        sort_by = "heat" if sort_label == "按热度" else "time"
        try:
            if search_scope == "已发布快照":
                result = search_archive(query, sort_by)
                result["complete"] = True
            else:
                with st.spinner("正在查询雪球与淘股吧公开入口……"):
                    result = search_live(query, sort_by)
            st.session_state["stock_search_result"] = result
        except Exception as exc:
            st.session_state.pop("stock_search_result", None)
            st.error(f"搜索失败：{type(exc).__name__}: {exc}")
    result = st.session_state.get("stock_search_result")
    if result:
        _render_search_results(result)


def render_search_dashboard() -> None:
    payload = load_search_snapshot()
    ai_pool = payload.get("ai_pool") or {}
    confirmed = list(ai_pool.get("confirmed") or [])
    disputed = list(ai_pool.get("disputed") or [])
    hotspots = list(payload.get("hotspots") or [])

    st.markdown("## 雪球 × 淘股吧公开信息搜索")
    st.caption(
        f"快照日期：{payload.get('date', '未知')}｜生成时间：{payload.get('generated_at', '未知')}。"
        "热点是线索，不是结论；页面不构成投资建议。"
    )
    metrics = st.columns(4)
    metrics[0].metric("每日热点", len(hotspots))
    metrics[1].metric("AI确认池", len(confirmed))
    metrics[2].metric("AI争议池", len(disputed))
    metrics[3].metric("来源证据", len(payload.get("evidence") or []))
    _render_source_health(payload)

    hotspot_tab, confirmed_tab, disputed_tab, search_tab, method_tab = st.tabs(
        ["每日热点", "AI确认池", "AI争议池", "个股 / 关键词搜索", "口径说明"]
    )
    with hotspot_tab:
        keyword = st.text_input("筛选热点", placeholder="标题、股票或主题", key="hotspot_filter")
        if keyword.strip():
            needle = keyword.strip().lower()
            visible = [
                item for item in hotspots
                if needle in json.dumps(item, ensure_ascii=False).lower()
            ]
        else:
            visible = hotspots
        _render_posts(visible, prefix="hotspot")
    with confirmed_tab:
        if not confirmed:
            st.info("本次快照没有满足“两站、同股、同一 AI 子主题”的确认项。")
        for index, item in enumerate(confirmed):
            _render_pool_item(item, key=f"confirmed_{index}")
    with disputed_tab:
        for index, item in enumerate(disputed):
            _render_pool_item(item, key=f"disputed_{index}")
    with search_tab:
        _render_search_form()
    with method_tab:
        methodology = payload.get("methodology") or {}
        for name, description in methodology.items():
            st.markdown(f"**{name}**")
            st.write(description)


def render_astocklab() -> None:
    activate_astocklab_imports()
    manifest = snapshot_manifest()
    st.info(
        f"当前为只读在线快照：{manifest['snapshot_date']}，"
        f"日线 {int(manifest['daily_rows']):,} 条，AI产业链成员记录 "
        f"{int(manifest['ai_membership_rows']):,} 条。数据更新与预测仍在本地项目完成。"
    )
    runpy.run_path(str(ASTOCKLAB_ROOT / "online_app.py"), run_name="__yaoyao_astocklab__")


def render_stock_portal() -> None:
    st.markdown("# 股票研究中心")
    st.caption("本地生产、在线只读展示｜不自动交易，不构成投资建议")
    section = st.segmented_control(
        "子板块",
        ["AStockLab", "股票搜索"],
        default="AStockLab",
        selection_mode="single",
        key="stock_portal_section",
    )
    st.divider()
    if section == "股票搜索":
        render_search_dashboard()
    else:
        render_astocklab()
