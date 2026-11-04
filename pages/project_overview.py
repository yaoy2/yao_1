"""Public navigation index; reads descriptions, never project business records."""

from collections import Counter
import importlib
from pathlib import Path

import streamlit as st

from utils import project_overview, ui_theme

if getattr(ui_theme, "UI_THEME_VERSION", 0) < 3:
    ui_theme = importlib.reload(ui_theme)
if getattr(project_overview, "PROJECT_OVERVIEW_VERSION", 0) < 2:
    project_overview = importlib.reload(project_overview)

from utils.project_overview import (
    SECTION_LABELS,
    STATUS_LABELS,
    build_project_rows,
    build_update_rows,
    filter_projects,
    load_public_updates,
    project_status,
)
from utils.ui_theme import _load_homepage_tools, render_home_link


st.set_page_config(page_title="项目总览 · YaoYao", page_icon="🗂️", layout="wide")
render_home_link()

css_path = Path(__file__).resolve().parents[1] / "utils" / "project_overview.css"
st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
st.title("项目总览")
st.caption("先看用途和状态，再进入需要的项目。这里整理工具箱公开展示的功能介绍与简要更新。")

tools = _load_homepage_tools()
if not tools:
    st.warning("项目清单暂时无法读取，请稍后重试。")
    st.stop()

counts = Counter(project_status(tool) for tool in tools)
st.markdown(
    '<div class="overview-summary">'
    f'<span>共 <strong>{len(tools)}</strong> 个入口</span>'
    + "".join(f'<span>{label} <strong>{counts[key]}</strong></span>' for key, label in STATUS_LABELS.items())
    + '</div>',
    unsafe_allow_html=True,
)

projects_tab, updates_tab = st.tabs(["项目清单", "简要更新"])
with projects_tab:
    search_col, section_col, status_col = st.columns([3, 1, 1])
    query = search_col.text_input("搜索项目", placeholder="项目名、编号或用途，如 M20、月报、通知")
    section = section_col.selectbox(
        "分类", ["all", *SECTION_LABELS], format_func=lambda value: SECTION_LABELS.get(value, "全部分类")
    )
    status = status_col.selectbox(
        "状态", ["all", *STATUS_LABELS], format_func=lambda value: STATUS_LABELS.get(value, "全部状态")
    )
    selected = filter_projects(tools, query, section, status)
    st.caption(f"找到 {len(selected)} 个入口。部分项目提供说明或需要本机组件，具体条件见项目介绍。")
    if not selected:
        st.info("没有匹配的项目，可以缩短关键词或切换分类、状态。")
    elif section == "all" and status == "all" and not query.strip():
        current = [tool for tool in selected if project_status(tool) != "archived"]
        archived = [tool for tool in selected if project_status(tool) == "archived"]
        st.markdown(build_project_rows(current), unsafe_allow_html=True)
        if archived:
            with st.expander(f"已归档的 {len(archived)} 个入口"):
                st.markdown(build_project_rows(archived), unsafe_allow_html=True)
    else:
        st.markdown(build_project_rows(selected), unsafe_allow_html=True)

with updates_tab:
    try:
        updates = load_public_updates()
        st.caption("只保留影响使用的近期变化，按日期倒序排列。")
        st.markdown(build_update_rows(updates), unsafe_allow_html=True)
    except (OSError, ValueError, KeyError, TypeError):
        st.warning("更新摘要暂时无法读取，项目清单仍可正常使用。")
    st.markdown("[查看代码更新历史 ↗](https://github.com/yaoy2/yao_1/commits/main/)")
