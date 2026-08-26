"""Read-only Streamlit UI for the concept fable gallery (M19)."""

from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from concept_fables.catalog import filter_items, load_catalog, select_item

QUERY_KEY = "concept"
ALL_FIELDS = "全部"
SORT_OPTIONS = ("最新", "名称")
DEFINITION_PREVIEW_LEN = 72


def _safe(value: Any) -> str:
    """Escape catalog-derived text before HTML interpolation."""
    if value is None:
        return ""
    return escape(str(value), quote=True)


def _short_text(value: Any, limit: int = DEFINITION_PREVIEW_LEN) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _latest_update_label(items: list[dict[str, Any]]) -> str:
    dates = [str(item.get("updated_at") or "").strip() for item in items]
    dates = [d for d in dates if d]
    if not dates:
        return "等待首篇"
    return max(dates)


def _field_options(items: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for item in items:
        field = str(item.get("field") or "").strip()
        if not field:
            continue
        key = field.casefold()
        if key in seen:
            continue
        seen.add(key)
        fields.append(field)
    fields.sort(key=lambda value: value.casefold())
    return [ALL_FIELDS, *fields]


def _read_selected_id() -> str:
    raw = st.query_params.get(QUERY_KEY, "")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return str(raw or "").strip()


def _open_concept(item_id: str) -> None:
    st.query_params[QUERY_KEY] = item_id
    st.rerun()


def _clear_selection() -> None:
    if QUERY_KEY in st.query_params:
        del st.query_params[QUERY_KEY]
    st.rerun()


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        /* Page canvas: warm-night archive on command-center navy */
        .stApp {
            color: #e8eef6;
            background:
                linear-gradient(rgba(245, 184, 75, .035) 1px, transparent 1px),
                linear-gradient(90deg, rgba(245, 184, 75, .035) 1px, transparent 1px),
                radial-gradient(circle at top right, rgba(255, 92, 168, .11), transparent 40%),
                radial-gradient(circle at 18% 12%, rgba(245, 184, 75, .08), transparent 34%),
                linear-gradient(135deg, #05070d 0%, #0a1220 38%, #121018 70%, #14100d 100%);
            background-size: 28px 28px, 28px 28px, auto, auto, auto;
        }
        .block-container {
            color: #e8eef6;
        }
        /* Compact dark controls in main content only; leave fixed home link + sidebar alone */
        section.main .stButton > button {
            border-radius: 8px;
            border: 1px solid rgba(245, 184, 75, .34);
            background: linear-gradient(180deg, rgba(24, 30, 44, .96), rgba(14, 18, 28, .96));
            color: #f4ead6;
            font-weight: 700;
            box-shadow: inset 0 1px 0 rgba(255, 217, 138, .06);
        }
        section.main .stButton > button:hover {
            border-color: rgba(255, 92, 168, .45);
            background: linear-gradient(180deg, rgba(36, 28, 38, .98), rgba(18, 20, 30, .98));
            color: #ffe6b0;
        }
        section.main .stButton > button:focus {
            box-shadow: 0 0 0 1px rgba(245, 184, 75, .45);
        }
        section.main div[data-baseweb="select"] > div,
        section.main input,
        section.main textarea,
        section.main [data-baseweb="input"] {
            border-radius: 8px !important;
            border-color: rgba(245, 184, 75, .22) !important;
            background-color: rgba(8, 12, 20, .92) !important;
            color: #e8eef6 !important;
        }
        section.main div[data-baseweb="select"] > div:hover,
        section.main input:hover,
        section.main textarea:hover {
            border-color: rgba(255, 92, 168, .35) !important;
        }
        section.main div[data-baseweb="select"] > div:focus-within,
        section.main input:focus,
        section.main textarea:focus {
            border-color: rgba(245, 184, 75, .55) !important;
            box-shadow: 0 0 0 1px rgba(245, 184, 75, .28);
        }
        section.main [data-baseweb="popover"] li,
        section.main [data-baseweb="menu"] li {
            background-color: #101826 !important;
            color: #e8eef6 !important;
        }
        section.main .stAlert {
            border-radius: 10px;
            border: 1px solid rgba(245, 184, 75, .22);
            background: rgba(14, 18, 28, .88);
            color: #d7e0ec;
        }
        .cf-wrap { color: #e8eef6; }
        .cf-hero {
            padding: .95rem 1.05rem;
            margin-bottom: .85rem;
            border-radius: 14px;
            border: 1px solid rgba(245, 184, 75, .22);
            background:
                linear-gradient(135deg, rgba(18, 24, 38, .94), rgba(28, 22, 18, .88)),
                radial-gradient(circle at top right, rgba(255, 92, 168, .12), transparent 42%);
            box-shadow: 0 14px 34px rgba(0, 0, 0, .28);
        }
        .cf-kicker {
            display: inline-flex;
            align-items: center;
            gap: .4rem;
            margin-bottom: .35rem;
            color: #f5b84b;
            font-size: .78rem;
            font-weight: 750;
            letter-spacing: .04em;
            text-transform: uppercase;
        }
        .cf-hero h1 {
            margin: 0 0 .35rem;
            color: #fff7e8;
            font-size: 1.72rem;
            line-height: 1.2;
        }
        .cf-hero p {
            margin: 0;
            color: #b7c2d0;
            font-size: .95rem;
            line-height: 1.55;
        }
        .cf-stats {
            display: flex;
            flex-wrap: wrap;
            gap: .45rem;
            margin-top: .75rem;
        }
        .cf-stat {
            min-width: 5.6rem;
            padding: .38rem .62rem;
            border-radius: 10px;
            border: 1px solid rgba(245, 184, 75, .18);
            background: rgba(8, 12, 20, .55);
        }
        .cf-stat b {
            display: block;
            color: #ffd98a;
            font-size: 1.05rem;
            line-height: 1.2;
        }
        .cf-stat span {
            color: #93a0b3;
            font-size: .74rem;
        }
        .cf-card {
            min-height: 0;
            padding: .72rem .78rem .66rem;
            margin-bottom: .55rem;
            border-radius: 12px;
            border: 1px solid rgba(148, 163, 184, .18);
            background: linear-gradient(180deg, rgba(16, 22, 34, .92), rgba(12, 16, 26, .92));
            box-shadow: inset 0 1px 0 rgba(255, 217, 138, .05);
        }
        .cf-card-title {
            margin: 0 0 .28rem;
            color: #fff4df;
            font-size: 1.02rem;
            font-weight: 750;
            line-height: 1.3;
        }
        .cf-card-meta {
            margin: 0 0 .4rem;
            color: #9aa8bb;
            font-size: .78rem;
        }
        .cf-card-def {
            margin: 0 0 .45rem;
            color: #c5d0de;
            font-size: .86rem;
            line-height: 1.45;
        }
        .cf-tags {
            display: flex;
            flex-wrap: wrap;
            gap: .28rem;
            margin: 0 0 .35rem;
        }
        .cf-tag {
            display: inline-flex;
            padding: .12rem .42rem;
            border-radius: 999px;
            border: 1px solid rgba(255, 92, 168, .28);
            background: rgba(255, 92, 168, .08);
            color: #ff9ec8;
            font-size: .72rem;
            font-weight: 650;
        }
        .cf-date {
            color: #7f8ea3;
            font-size: .74rem;
        }
        .cf-empty {
            padding: 1.1rem 1.15rem;
            border-radius: 14px;
            border: 1px dashed rgba(245, 184, 75, .34);
            background: rgba(14, 18, 28, .78);
        }
        .cf-empty h3 {
            margin: 0 0 .4rem;
            color: #ffe6b0;
            font-size: 1.08rem;
        }
        .cf-empty p {
            margin: 0 0 .55rem;
            color: #aeb9c9;
            line-height: 1.55;
        }
        .cf-empty code {
            padding: .12rem .38rem;
            border-radius: 6px;
            background: rgba(255, 92, 168, .12);
            color: #ffb3d4;
            font-size: .86rem;
        }
        .cf-detail {
            padding: 1rem 1.05rem 1.1rem;
            border-radius: 14px;
            border: 1px solid rgba(245, 184, 75, .28);
            background:
                linear-gradient(180deg, rgba(28, 22, 16, .95), rgba(12, 16, 26, .96));
            box-shadow: 0 16px 36px rgba(0, 0, 0, .28);
        }
        .cf-detail-title {
            margin: 0 0 .25rem;
            color: #fff7e8;
            font-size: 1.45rem;
            line-height: 1.25;
        }
        .cf-detail-meta {
            margin: 0 0 .75rem;
            color: #a8b4c5;
            font-size: .86rem;
        }
        .cf-story {
            margin: 0 0 .9rem;
            padding: .85rem .9rem;
            border-radius: 12px;
            border-left: 3px solid #f5b84b;
            background: rgba(245, 184, 75, .08);
            color: #f4ead6;
            font-size: 1rem;
            line-height: 1.7;
            white-space: pre-wrap;
        }
        .cf-section-label {
            margin: 0 0 .35rem;
            color: #ff9ec8;
            font-size: .78rem;
            font-weight: 750;
            letter-spacing: .03em;
        }
        .cf-block {
            margin: 0 0 .75rem;
            color: #d5deea;
            font-size: .92rem;
            line-height: 1.55;
            white-space: pre-wrap;
        }
        .cf-map-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: .45rem;
            margin: 0 0 .75rem;
        }
        .cf-map-item {
            padding: .5rem .58rem;
            border-radius: 10px;
            border: 1px solid rgba(148, 163, 184, .16);
            background: rgba(8, 12, 20, .45);
        }
        .cf-map-item .k {
            display: block;
            margin-bottom: .18rem;
            color: #f5b84b;
            font-size: .74rem;
            font-weight: 700;
        }
        .cf-map-item .v {
            color: #d7e0ec;
            font-size: .86rem;
            line-height: 1.4;
        }
        .cf-q {
            margin: 0 0 .45rem;
            padding: .55rem .65rem;
            border-radius: 10px;
            border: 1px solid rgba(255, 92, 168, .18);
            background: rgba(255, 92, 168, .06);
            color: #e7edf6;
            font-size: .9rem;
            line-height: 1.5;
        }
        .cf-q b {
            color: #ffb3d4;
            font-weight: 750;
        }
        @media (max-width: 900px) {
            .cf-map-grid { grid-template-columns: 1fr; }
            .cf-hero h1 { font-size: 1.42rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_hero(items: list[dict[str, Any]]) -> None:
    concept_count = len(items)
    field_count = max(0, len(_field_options(items)) - 1)
    latest = _latest_update_label(items)
    st.markdown(
        f"""
        <section class="cf-hero cf-wrap">
          <div class="cf-kicker"><span>M19</span><span>Concept Archive</span></div>
          <h1>📜 概念寓言馆</h1>
          <p>Codex 把抽象概念写成可记的寓言；本馆只负责检索、筛选与重读，不在页面上改稿。</p>
          <div class="cf-stats">
            <div class="cf-stat"><b>{_safe(concept_count)}</b><span>概念数</span></div>
            <div class="cf-stat"><b>{_safe(field_count)}</b><span>领域数</span></div>
            <div class="cf-stat"><b>{_safe(latest)}</b><span>最近更新</span></div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_empty_catalog() -> None:
    st.markdown(
        """
        <section class="cf-empty cf-wrap">
          <h3>馆藏仍空，等待首篇寓言</h3>
          <p>生产目录当前没有概念条目。本页只读展示，不提供页面内新建或编辑。</p>
          <p>请在 Codex 中调用 <code>$concept-fable-gallery &lt;概念&gt;</code> 生成并入库，然后再回到这里检索与重读。</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_empty_filter() -> None:
    st.info("当前筛选条件下没有匹配概念。可清空搜索词，或把领域切回「全部」。")


def _render_controls(items: list[dict[str, Any]]) -> tuple[str, str, str]:
    fields = _field_options(items)
    c1, c2, c3 = st.columns([2.2, 1.1, 1.0], gap="small")
    with c1:
        query = st.text_input(
            "搜索",
            value="",
            placeholder="搜索概念 / 领域 / 流派 / 定义 / 标签",
            label_visibility="collapsed",
            key="cf_search_query",
        )
    with c2:
        field = st.selectbox(
            "领域",
            options=fields,
            index=0,
            label_visibility="collapsed",
            key="cf_field_filter",
        )
    with c3:
        sort = st.selectbox(
            "排序",
            options=list(SORT_OPTIONS),
            index=0,
            label_visibility="collapsed",
            key="cf_sort_mode",
        )
    return query or "", field or ALL_FIELDS, sort or "最新"


def _render_card(item: dict[str, Any], button_key: str) -> None:
    concept = _safe(item.get("concept", ""))
    field = _safe(item.get("field", ""))
    school = str(item.get("school") or "").strip()
    meta = field if not school else f"{field} · {_safe(school)}"
    definition = _safe(_short_text(item.get("definition", "")))
    updated = _safe(item.get("updated_at", ""))
    tags = item.get("tags") or []
    tag_html = "".join(
        f'<span class="cf-tag">{_safe(tag)}</span>'
        for tag in tags
        if str(tag).strip()
    )
    tags_block = f'<div class="cf-tags">{tag_html}</div>' if tag_html else ""

    st.markdown(
        f"""
        <article class="cf-card cf-wrap">
          <div class="cf-card-title">{concept}</div>
          <div class="cf-card-meta">{meta}</div>
          <div class="cf-card-def">{definition}</div>
          {tags_block}
          <div class="cf-date">更新 {updated}</div>
        </article>
        """,
        unsafe_allow_html=True,
    )
    if st.button("打开寓言", key=button_key, use_container_width=True):
        _open_concept(str(item.get("id", "")))


def _render_gallery(items: list[dict[str, Any]]) -> None:
    if not items:
        _render_empty_filter()
        return

    columns = st.columns(3, gap="small")
    for index, item in enumerate(items):
        with columns[index % 3]:
            _render_card(item, button_key=f"cf_open_{item.get('id', index)}_{index}")


def _render_mappings(mappings: list[dict[str, Any]]) -> str:
    if not mappings:
        return ""
    cells: list[str] = []
    for mapping in mappings:
        story_el = _safe(mapping.get("story_element", ""))
        concept_el = _safe(mapping.get("concept_element", ""))
        cells.append(
            f"""
            <div class="cf-map-item">
              <span class="k">故事元素</span>
              <span class="v">{story_el}</span>
              <span class="k" style="margin-top:.35rem;">概念元素</span>
              <span class="v">{concept_el}</span>
            </div>
            """
        )
    return f'<div class="cf-map-grid">{"".join(cells)}</div>'


def _render_detail(item: dict[str, Any]) -> None:
    if st.button("← 返回全部概念", key="cf_back_to_gallery"):
        _clear_selection()

    concept = _safe(item.get("concept", ""))
    field = _safe(item.get("field", ""))
    school = str(item.get("school") or "").strip()
    meta_bits = [field]
    if school:
        meta_bits.append(_safe(school))
    updated = _safe(item.get("updated_at", ""))
    created = _safe(item.get("created_at", ""))
    meta_bits.append(f"更新 {updated}")
    if created and created != updated:
        meta_bits.append(f"创建 {created}")
    meta = " · ".join(meta_bits)

    tags = item.get("tags") or []
    tag_html = "".join(
        f'<span class="cf-tag">{_safe(tag)}</span>'
        for tag in tags
        if str(tag).strip()
    )
    tags_block = f'<div class="cf-tags">{tag_html}</div>' if tag_html else ""

    story = _safe(item.get("story", ""))
    definition = _safe(item.get("definition", ""))
    mappings_html = _render_mappings(item.get("mappings") or [])
    questions = item.get("questions") or {}
    core = _safe(questions.get("core", ""))
    transfer = _safe(questions.get("transfer", ""))

    st.markdown(
        f"""
        <section class="cf-detail cf-wrap">
          <h2 class="cf-detail-title">{concept}</h2>
          <div class="cf-detail-meta">{meta}</div>
          {tags_block}
          <div class="cf-section-label">寓言正文</div>
          <div class="cf-story">{story}</div>
          <div class="cf-section-label">定义</div>
          <div class="cf-block">{definition}</div>
          <div class="cf-section-label">元素映射</div>
          {mappings_html}
          <div class="cf-section-label">核心与迁移问题</div>
          <div class="cf-q"><b>核心问题</b><br>{core}</div>
          <div class="cf-q"><b>迁移问题</b><br>{transfer}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_page() -> None:
    """Render the read-only concept fable gallery."""
    _inject_styles()

    try:
        catalog = load_catalog()
    except (OSError, ValueError, TypeError) as exc:
        st.error(f"概念寓言目录无法读取或格式不正确：{exc}")
        return

    items = catalog.get("items") or []
    if not isinstance(items, list):
        st.error("概念寓言目录格式不正确：items 必须是列表。")
        return

    _render_hero(items)

    if not items:
        _render_empty_catalog()
        return

    selected_id = _read_selected_id()
    selected = select_item(items, selected_id) if selected_id else None
    if selected_id and selected is None:
        # Invalid id: quietly fall back to gallery.
        selected = None

    if selected is not None:
        _render_detail(selected)
        return

    query, field, sort = _render_controls(items)
    filtered = filter_items(items, query=query, field=field, sort=sort)
    _render_gallery(filtered)
