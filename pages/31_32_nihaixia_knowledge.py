"""M32 · Password-protected, manually curated Ni Haixia knowledge library."""

import hashlib
import math
import os

import streamlit as st

from utils import budget_auth
from utils import nihaixia_knowledge as knowledge
from utils.ui_theme import render_home_link


def clear_private_session():
    for key in list(st.session_state):
        if key.startswith("m32_"):
            del st.session_state[key]


def require_auth():
    password = budget_auth.get_budget_password(st.secrets, os.environ)
    if not password:
        clear_private_session()
        st.info("知识库访问密码尚未配置，请沿用工具箱的统一访问密码配置。")
        st.stop()
    fingerprint = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if st.session_state.get("m32_authenticated") == fingerprint:
        return
    clear_private_session()
    st.caption("使用工具箱统一访问密码。")
    with st.form("m32_login"):
        entered = st.text_input("访问密码", type="password")
        submitted = st.form_submit_button("进入知识库", type="primary")
    if submitted:
        if budget_auth.is_budget_password_valid(entered, password):
            st.session_state["m32_authenticated"] = fingerprint
            st.rerun()
        st.error("密码不正确，请重新输入。")
    st.stop()


def show_entry(entry, *, expanded=False):
    label = f"{entry['title']} · {entry['kind']}"
    with st.expander(label, expanded=expanded):
        st.caption(knowledge.DOMAINS[entry["domain"]])
        st.markdown(knowledge.reader_markdown(entry["body"]))
        if entry.get("sources"):
            st.markdown("**出处与定位**")
            for source in entry["sources"]:
                st.caption(source)
        if entry.get("rule", {}).get("evidence"):
            for evidence in entry["rule"]["evidence"]:
                quote = evidence.get("quote_exact") or evidence.get("excerpt")
                if quote:
                    st.markdown("原文短引：")
                    st.text(quote)
        st.caption("条目编号：" + entry["id"])


st.set_page_config(page_title="M32 · 倪海厦知识库", page_icon="☯", layout="wide")
render_home_link()
st.title("☯ 倪海厦知识库")
require_auth()

if "m32_library" not in st.session_state:
    try:
        with st.spinner("正在读取知识库…"):
            st.session_state["m32_library"] = knowledge.load_library(secrets=st.secrets)
    except Exception:
        st.error("知识库暂时未读到。请稍后重试，或检查工具箱的私有数据连接。")
        if st.button("重试"):
            st.rerun()
        st.stop()

library = st.session_state["m32_library"]
manifest, entries = library["manifest"], library["entries"]
counts = manifest["counts"]
heading, refresh, logout = st.columns([7, 1, 1])
with heading:
    st.caption(f"按思想与主题积累 · {counts['rules']:,} 条规则 · {counts['chapters']:,} 篇专题与说明 · "
               f"{counts['comparisons']:,} 项条件对照 · 更新于 {manifest['updated_on']}")
with refresh:
    if st.button("刷新版本"):
        st.session_state.pop("m32_library", None)
        st.rerun()
with logout:
    if st.button("退出访问"):
        clear_private_session()
        st.rerun()

view = st.radio("阅读方式", ["体系阅读", "全库检索", "来源与更新"], horizontal=True,
                label_visibility="collapsed", key="m32_view")

if view == "体系阅读":
    st.markdown("**先读主线，再展开完整规则与推导。**")
    guides = sorted([entry for entry in entries if entry.get("order") == 0],
                    key=lambda e: e.get("provenance", [{}])[0].get("file", e["title"]))
    if guides:
        guide_id = st.selectbox("体系导读", [entry["id"] for entry in guides],
                                format_func=lambda value: next(e["title"] for e in guides if e["id"] == value),
                                key="m32_guide")
        guide = next(e for e in guides if e["id"] == guide_id)
        st.markdown(knowledge.reader_markdown(guide["body"]))
    st.divider()
    domain = st.selectbox("展开一个主题", list(knowledge.DOMAINS), format_func=knowledge.DOMAINS.get,
                          key="m32_topic")
    chapters = knowledge.search_entries(entries, domain=domain, kinds={"总纲", "专题", "疑点与取舍"})
    st.caption(f"本主题共 {manifest['domains'].get(domain, 0):,} 项内容；下列目录展示完整专题，逐条规则可在全库检索中阅读。")
    if chapters:
        options = {entry["id"]: entry for entry in chapters}
        selected = st.selectbox("专题目录", list(options), format_func=lambda value: options[value]["title"],
                                key=f"m32_chapter_{domain}")
        show_entry(options[selected], expanded=True)
        st.download_button("下载本篇完整内容", knowledge.export_markdown([options[selected]], options[selected]["title"]),
                           "倪海厦知识专题.md", "text/markdown")

elif view == "全库检索":
    query = st.text_input("搜索全部正文、条件与推导", placeholder="例如：科权禄、阳爻阴年、鸾喜 婚期、井清未食",
                          key="m32_query")
    topic_column, kind_column = st.columns([1, 2])
    with topic_column:
        domain = st.selectbox("主题", [None, *knowledge.DOMAINS],
                              format_func=lambda value: "全部主题" if value is None else knowledge.DOMAINS[value],
                              key="m32_search_domain")
    with kind_column:
        kinds = st.multiselect("内容类型", knowledge.KINDS, default=list(knowledge.KINDS), key="m32_kinds")
    results = knowledge.search_entries(entries, query, domain, set(kinds)) if kinds else []
    st.caption(f"找到 {len(results):,} 项。多个词用空格隔开，可同时匹配；展开后显示完整正文。")
    if results:
        pages = math.ceil(len(results) / 12)
        filter_key = hashlib.sha256((query + str(domain) + str(kinds)).encode()).hexdigest()[:12]
        page = st.number_input("页码", min_value=1, max_value=pages, value=1, step=1,
                               key="m32_page_" + filter_key)
        for entry in results[(page - 1) * 12:page * 12]:
            show_entry(entry)
        st.caption(f"第 {page} / {pages} 页")
    else:
        st.info("没有匹配内容，可以减少关键词或更换主题。")

else:
    st.markdown("""
**保存内容**

规则中的判断、条件、例外、推导、作者归属和出处逐项保留。完整专题、六爻表、命例与跨课对照继续保存，
体系导读用于组织阅读。仅完全相同的内容合并来源；不将不同条件的判断压成一句话。

**来源层次**

倪氏课堂、教材、学员笔记及外部作者分别注明。规则与综合推演是研习者的理解；直接摘录另有定位。
尚未解决的排法、版本差异和局部边界保留在相应内容里。案例按原文区分教材、课堂与自拟例。

**由你发指令更新**

新学内容不会自动改动线上版本。需要更新时，在原知识库项目的聊天中发送：

> 更新倪海厦知识库：把上次发布后新学的内容按主题并入，保留条件、例外、推导和出处，核对后同步到 GH 与 M32。

更新时先比较新旧条目，补充或修正相应主题，再核对内容与来源，最后切换线上版本。
页面的“刷新版本”只读取已经发布的内容。
""")
    st.caption(f"本版条目 {counts['entries']:,} 项；来源文档 {counts['source_documents']:,} 份。"
               "原始视频、书籍、读取快照与过程日志保存在本机。")
    if st.checkbox("准备下载完整知识正文", key="m32_prepare_export"):
        st.download_button("下载完整知识库（Markdown）", knowledge.export_markdown(entries),
                           f"倪海厦知识库_{manifest['updated_on'].replace('-', '_')}.md", "text/markdown")
    st.caption("版本：" + manifest["revision"][:16])
