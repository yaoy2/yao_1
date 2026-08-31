"""M21：Awesome Design MD 本地只读展示入口。"""

from __future__ import annotations

import streamlit as st

from utils.awesome_design_md import (
    DESIGN_ROOT,
    discover_designs,
    heading_names,
    load_design_document,
    load_readme,
)
from utils.ui_theme import render_home_link


st.set_page_config(page_title="Awesome Design MD", page_icon="🧩", layout="wide")
render_home_link()

st.markdown(
    """
    <style>
    .m21-hero {
        padding: 1rem 1.1rem;
        margin-bottom: .8rem;
        border: 1px solid rgba(104, 211, 145, .24);
        border-radius: 14px;
        background: linear-gradient(135deg, rgba(18, 34, 31, .94), rgba(14, 24, 39, .94));
    }
    .m21-kicker {
        color: #7ee2a8;
        font-size: .78rem;
        font-weight: 750;
        letter-spacing: .06em;
        text-transform: uppercase;
    }
    .m21-hero h1 {
        margin: .25rem 0 .35rem;
        color: #f1fff6;
        font-size: 1.75rem;
    }
    .m21-hero p {
        margin: 0;
        color: #b9c9c4;
        line-height: 1.55;
    }
    .m21-readonly {
        display: inline-block;
        padding: .18rem .52rem;
        border: 1px solid rgba(126, 226, 168, .34);
        border-radius: 999px;
        color: #9cf0bd;
        background: rgba(126, 226, 168, .08);
        font-size: .76rem;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<section class="m21-hero"><div class="m21-kicker">M21 · DESIGN REFERENCE</div>'
    '<h1>🧩 Awesome Design MD</h1>'
    '<p>浏览本地拉取的品牌设计系统文档，为页面设计提供可检索、可重读的视觉参考。</p>'
    '<span class="m21-readonly">只读展示 · 不修改源文件</span></section>',
    unsafe_allow_html=True,
)

items = discover_designs()
if not items:
    st.error(f"未找到本地设计规范目录：{DESIGN_ROOT}")
    st.stop()

query = st.text_input("筛选设计系统", placeholder="输入品牌名或关键词，例如 apple、dark、editorial")
query_terms = query.casefold().split()
filtered_items = [
    item
    for item in items
    if all(
        term
        in " ".join(
            [item["slug"], item["title"], item.get("description", "")]
        ).casefold()
        for term in query_terms
    )
]

if not filtered_items:
    st.warning("没有匹配的设计系统，请换一个关键词。")
    st.stop()

selected_slug = st.selectbox(
    "选择要阅读的设计系统",
    options=[item["slug"] for item in filtered_items],
    format_func=lambda slug: next(
        item["title"] for item in filtered_items if item["slug"] == slug
    ),
)
selected = next(item for item in filtered_items if item["slug"] == selected_slug)
metadata, body = load_design_document(selected)
sections = heading_names(body)

stat_col1, stat_col2, stat_col3 = st.columns(3)
stat_col1.metric("本地设计系统", len(items))
stat_col2.metric("当前文档大小", f"{selected['design_path'].stat().st_size / 1024:.1f} KB")
stat_col3.metric("主要章节", len(sections))

st.markdown(f"### {selected['title']}")
if selected.get("description"):
    st.info(selected["description"])
st.caption(
    f"仓库来源：assets/awesome-design-md/design-md/{selected['slug']}/DESIGN.md"
)

if sections:
    st.caption("章节：" + " · ".join(sections))

st.markdown("#### DESIGN.md")
st.markdown(body, unsafe_allow_html=False)

readme = load_readme(selected)
if readme:
    with st.expander("查看来源说明（只读）"):
        st.code(readme, language="markdown")

with st.expander("查看文件头元数据（只读）"):
    st.code("\n".join(f"{key}: {value}" for key, value in metadata.items()), language="yaml")
