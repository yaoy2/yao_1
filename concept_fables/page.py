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
    st.html(
        """
        <style>
        /* White reading canvas, aligned with the shared navigation and M20. */
        .stApp {
            color-scheme: light;
            color: #334155;
            background: #ffffff;
            font-family: "Inter", -apple-system, BlinkMacSystemFont,
                "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
        }
        [data-testid="stHeader"] {
            background: #ffffff;
            color: #334155;
        }
        [data-testid="stHeader"] button { color: #334155; }
        .block-container { color: #334155; }
        /* Key-scoped controls keep the shared home button and sidebar intact. */
        [class*="st-key-cf_"] button {
            border-radius: 8px;
            border: 1px solid #cbd5e1;
            background: #ffffff;
            color: #1d4ed8;
            font-family: inherit;
            font-weight: 600;
        }
        [class*="st-key-cf_"] button:hover {
            border-color: #2563eb;
            background: #eff6ff;
            color: #1e40af;
        }
        [class*="st-key-cf_"] button:focus-visible {
            outline: 2px solid #2563eb;
            outline-offset: 2px;
        }
        [class*="st-key-cf_"] [data-baseweb="select"] > div,
        [class*="st-key-cf_"] [data-baseweb="input"],
        [class*="st-key-cf_"] [data-baseweb="base-input"],
        [class*="st-key-cf_"] input {
            border-radius: 8px;
            border-color: #cbd5e1;
            background-color: #ffffff;
            color: #334155;
            caret-color: #1d4ed8;
        }
        [class*="st-key-cf_"] input::placeholder {
            color: #64748b;
            opacity: 1;
        }
        [class*="st-key-cf_"] [data-baseweb="select"] > div:hover,
        [class*="st-key-cf_"] [data-baseweb="input"]:hover {
            border-color: #94a3b8;
        }
        [class*="st-key-cf_"] [data-baseweb="select"] > div:focus-within,
        [class*="st-key-cf_"] [data-baseweb="input"]:focus-within {
            border-color: #2563eb;
            box-shadow: 0 0 0 2px #dbeafe;
        }
        [class*="st-key-cf_"] [data-baseweb="select"] svg {
            color: #64748b;
            fill: currentColor;
        }
        /* Select menus are portals outside the main content container. */
        body:has(.cf-wrap) [data-baseweb="popover"],
        body:has(.cf-wrap) [data-baseweb="menu"],
        body:has(.cf-wrap) [role="listbox"],
        body:has(.cf-wrap) [role="option"] {
            background-color: #ffffff;
            color: #334155;
        }
        body:has(.cf-wrap) [role="option"]:hover,
        body:has(.cf-wrap) [role="option"][aria-selected="true"] {
            background-color: #eff6ff;
            color: #1d4ed8;
        }
        .cf-wrap {
            color: #334155;
            overflow-wrap: anywhere;
        }
        .cf-hero {
            padding: .95rem 1.05rem;
            margin-bottom: .85rem;
            border-radius: 14px;
            border: 1px solid #e2e8f0;
            border-top: 3px solid #2563eb;
            background: #ffffff;
            box-shadow: 0 2px 8px rgba(15, 23, 42, .04);
        }
        .cf-kicker {
            display: inline-flex;
            align-items: center;
            gap: .4rem;
            margin-bottom: .35rem;
            color: #1d4ed8;
            font-size: .78rem;
            font-weight: 700;
            letter-spacing: .04em;
            text-transform: uppercase;
        }
        .cf-hero h1 {
            margin: 0 0 .35rem;
            color: #0f172a;
            font-size: 1.72rem;
            line-height: 1.2;
        }
        .cf-hero p {
            margin: 0;
            color: #64748b;
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
            border: 1px solid #e2e8f0;
            background: #f8fafc;
        }
        .cf-stat b {
            display: block;
            color: #1d4ed8;
            font-size: 1.05rem;
            line-height: 1.2;
        }
        .cf-stat span {
            color: #64748b;
            font-size: .74rem;
        }
        .cf-card {
            min-height: 0;
            padding: .72rem .78rem .66rem;
            margin-bottom: .55rem;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            background: #ffffff;
            box-shadow: 0 2px 6px rgba(15, 23, 42, .03);
        }
        .cf-card-title {
            margin: 0 0 .28rem;
            color: #0f172a;
            font-size: 1.02rem;
            font-weight: 700;
            line-height: 1.3;
        }
        .cf-card-meta {
            margin: 0 0 .4rem;
            color: #64748b;
            font-size: .78rem;
        }
        .cf-card-def {
            margin: 0 0 .45rem;
            color: #334155;
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
            border: 1px solid #dbeafe;
            background: #eff6ff;
            color: #1d4ed8;
            font-size: .72rem;
            font-weight: 600;
        }
        .cf-date {
            color: #64748b;
            font-size: .74rem;
        }
        .cf-empty {
            padding: 1.1rem 1.15rem;
            border-radius: 14px;
            border: 1px dashed #cbd5e1;
            background: #f8fafc;
        }
        .cf-empty h3 {
            margin: 0 0 .4rem;
            color: #0f172a;
            font-size: 1.08rem;
        }
        .cf-empty p {
            margin: 0 0 .55rem;
            color: #475569;
            line-height: 1.55;
        }
        .cf-empty code {
            padding: .12rem .38rem;
            border-radius: 6px;
            background: #eff6ff;
            color: #1e40af;
            font-size: .86rem;
        }
        .cf-detail {
            padding: 1rem 1.05rem 1.1rem;
            border-radius: 14px;
            border: 1px solid #e2e8f0;
            background: #ffffff;
            box-shadow: 0 2px 8px rgba(15, 23, 42, .04);
        }
        .cf-detail-title {
            margin: 0 0 .25rem;
            color: #0f172a;
            font-size: 1.45rem;
            line-height: 1.25;
        }
        .cf-detail-meta {
            margin: 0 0 .75rem;
            color: #64748b;
            font-size: .86rem;
        }
        .cf-story {
            margin: 0 0 .9rem;
            padding: .85rem .9rem;
            border-radius: 12px;
            border-left: 3px solid #b6a27c;
            background: #faf9f6;
            color: #334155;
            font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC",
                "SimSun", serif;
            font-size: 1.05rem;
            line-height: 1.85;
            white-space: pre-wrap;
        }
        .cf-section-label {
            margin: 0 0 .35rem;
            color: #1d4ed8;
            font-size: .78rem;
            font-weight: 700;
            letter-spacing: .03em;
        }
        .cf-block {
            margin: 0 0 .75rem;
            color: #334155;
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
            border: 1px solid #e2e8f0;
            background: #f8fafc;
        }
        .cf-map-item .k {
            display: block;
            margin-bottom: .18rem;
            color: #1d4ed8;
            font-size: .74rem;
            font-weight: 700;
        }
        .cf-map-item .v {
            color: #334155;
            font-size: .86rem;
            line-height: 1.4;
        }
        .cf-q {
            margin: 0 0 .45rem;
            padding: .55rem .65rem;
            border-radius: 10px;
            border: 1px solid #dbeafe;
            background: #eff6ff;
            color: #334155;
            font-size: .9rem;
            line-height: 1.5;
        }
        .cf-q b {
            color: #1e40af;
            font-weight: 700;
        }
        @media (max-width: 900px) {
            .cf-map-grid { grid-template-columns: 1fr; }
            .cf-hero h1 { font-size: 1.42rem; }
        }
        </style>
        """,
    )


def _render_hero(items: list[dict[str, Any]]) -> None:
    concept_count = len(items)
    field_count = max(0, len(_field_options(items)) - 1)
    latest = _latest_update_label(items)
    st.html(
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
    )


def _render_empty_catalog() -> None:
    st.html(
        """
        <section class="cf-empty cf-wrap">
          <h3>馆藏仍空，等待首篇寓言</h3>
          <p>生产目录当前没有概念条目。本页只读展示，不提供页面内新建或编辑。</p>
          <p>请在 Codex 中调用 <code>$concept-fable-gallery &lt;概念&gt;</code> 生成并入库，然后再回到这里检索与重读。</p>
        </section>
        """,
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

    st.html(
        f"""
        <article class="cf-card cf-wrap">
          <div class="cf-card-title">{concept}</div>
          <div class="cf-card-meta">{meta}</div>
          <div class="cf-card-def">{definition}</div>
          {tags_block}
          <div class="cf-date">更新 {updated}</div>
        </article>
        """,
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


# Render these fragments with st.html: blank lines in catalog text and nested
# templates must never be interpreted as Markdown code blocks.
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

    st.html(
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
