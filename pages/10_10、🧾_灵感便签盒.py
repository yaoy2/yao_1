import os
import sys
from datetime import date

import streamlit as st


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import web_memo_db


st.set_page_config(page_title="灵感便签盒", page_icon="🧾", layout="wide")


def color_text(hex_code):
    hex_code = hex_code or "#1B3A5C"
    r = int(hex_code[1:3], 16)
    g = int(hex_code[3:5], 16)
    b = int(hex_code[5:7], 16)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return "#ffffff" if lum < 140 else "#182230"


def apply_style():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.7rem !important;
            padding-bottom: 1.5rem !important;
        }
        .memo-hero {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            gap: 1.5rem;
            margin-bottom: 1.1rem;
        }
        .memo-mark {
            display: inline-flex;
            gap: .5rem;
            align-items: center;
            color: #344054;
            font-size: .82rem;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: .45rem;
        }
        .memo-dot {
            width: 9px;
            height: 9px;
            border-radius: 999px;
            background: #2D6A4F;
            box-shadow: 14px 0 0 #1B3A5C, 28px 0 0 #810000;
        }
        .memo-title {
            font-size: 2.35rem;
            line-height: 1.1;
            margin: 0;
            font-weight: 850;
            color: #182230;
        }
        .memo-subtitle {
            margin: .45rem 0 0;
            color: #667085;
            font-size: 1.42rem;
            font-weight: 500;
            font-family: "STXingcao", "华文行草", "FZShuTi", "方正舒体", "STXinwei", "华文新魏", cursive;
            letter-spacing: 0;
        }
        .memo-stat-row {
            display: flex;
            gap: .65rem;
            flex-wrap: wrap;
            justify-content: flex-end;
        }
        .memo-stat {
            min-width: 96px;
            text-align: center;
            padding: .72rem .65rem;
            border: 1px solid rgba(24,34,48,.1);
            border-radius: 8px;
            background: rgba(255,255,255,.78);
            box-shadow: 0 10px 26px rgba(24,34,48,.07);
        }
        .memo-stat b {
            display: block;
            font-size: 1.3rem;
        }
        .memo-stat span {
            color: #667085;
            font-size: .76rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px !important;
            border-color: rgba(24,34,48,.11) !important;
            box-shadow: 0 12px 30px rgba(24,34,48,.06);
        }
        textarea {
            min-height: 82px !important;
            line-height: 1.8 !important;
        }
        .memo-card {
            position: relative;
            width: 100%;
            min-height: 168px;
            padding: .95rem .95rem .85rem 1.08rem;
            margin: 0 0 .82rem;
            border: 1px solid rgba(24,34,48,.1);
            border-radius: 8px;
            box-shadow: 0 10px 24px rgba(24,34,48,.055);
            overflow: hidden;
        }
        .memo-card::before {
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 6px;
            background: linear-gradient(180deg, var(--main), var(--accent));
        }
        .memo-card::after {
            content: "";
            position: absolute;
            right: -24px;
            top: -24px;
            width: 86px;
            height: 86px;
            border-radius: 50%;
            background: var(--accent-soft);
        }
        .memo-card-top {
            position: relative;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: .6rem;
            margin-bottom: .7rem;
        }
        .memo-date {
            color: var(--main);
            font-size: .82rem;
            font-weight: 800;
            line-height: 1.35;
        }
        .memo-palette {
            font-size: .72rem;
            color: #667085;
            background: rgba(255,255,255,.75);
            border: 1px solid rgba(24,34,48,.08);
            border-radius: 999px;
            padding: .22rem .5rem;
        }
        .memo-content {
            position: relative;
            color: #182230;
            font-size: .94rem;
            line-height: 1.72;
            white-space: pre-wrap;
        }
        .memo-tags {
            position: relative;
            margin-top: .75rem;
            display: flex;
            gap: .38rem;
            flex-wrap: wrap;
        }
        .memo-tag {
            font-size: .74rem;
            background: rgba(255,255,255,.78);
            color: #344054;
            border: 1px solid rgba(24,34,48,.08);
            border-radius: 999px;
            padding: .16rem .48rem;
        }
        .memo-tag-main {
            color: var(--main);
            font-weight: 700;
        }
        .export-strip {
            margin-top: 1.15rem;
            padding: .95rem 1rem;
            border: 1px solid rgba(24,34,48,.11);
            border-radius: 8px;
            background: rgba(255,255,255,.8);
            box-shadow: 0 12px 30px rgba(24,34,48,.07);
        }
        @media (max-width: 980px) {
            .memo-hero {
                align-items: flex-start;
                flex-direction: column;
            }
            .memo-stat-row {
                justify-content: flex-start;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

apply_style()
web_memo_db.init_db()

records = web_memo_db.get_memos()
categories = ["全部"] + web_memo_db.get_categories()
palettes = web_memo_db.parse_palettes()

st.markdown(
    f"""
    <section class="memo-hero">
      <div>
        <div class="memo-mark"><span class="memo-dot"></span><span>Web Memo</span></div>
        <h1 class="memo-title">🧾 灵感便签盒</h1>
        <p class="memo-subtitle">“我来监督沙瑞金”</p>
      </div>
      <div class="memo-stat-row">
        <div class="memo-stat"><b>{len(records)}</b><span>全部摘录</span></div>
        <div class="memo-stat"><b>{len([r for r in records if r["memo_date"][:7] == date.today().strftime("%Y-%m")])}</b><span>本月新增</span></div>
        <div class="memo-stat"><b>{len(palettes)}</b><span>循环色卡</span></div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

with st.container(border=True):
    st.subheader("快速记录")
    with st.form("web_memo_form", clear_on_submit=True):
        content = st.text_area("内容", placeholder="请输入", label_visibility="collapsed", height=88)
        col_save, col_plain = st.columns(2)
        save_classified = col_save.form_submit_button("保存并打标签", use_container_width=True)
        save_plain = col_plain.form_submit_button("只保存", use_container_width=True)

    if save_classified or save_plain:
        try:
            web_memo_db.add_memo(date.today().isoformat(), content, classify=save_classified)
            st.success("已保存")
            st.rerun()
        except ValueError:
            st.error("请输入内容后再保存。")

with st.container(border=True):
    top_a, top_b = st.columns([1, 1])
    with top_a:
        st.subheader("备忘列表")
    with top_b:
        selected_category = st.selectbox("分类", categories, label_visibility="collapsed")
    keyword = st.text_input("搜索", placeholder="按关键词搜索", label_visibility="collapsed")

    display_records = web_memo_db.get_memos(category=selected_category, keyword=keyword.strip() or None)
    if not display_records:
        st.info("还没有记录。先在上方粘贴一条。")
    else:
        memo_columns = st.columns(3, gap="medium")
        for index, record in enumerate(display_records):
            with memo_columns[index % 3]:
                st.markdown(web_memo_db.build_memo_card_html(record), unsafe_allow_html=True)

st.markdown('<section class="export-strip">', unsafe_allow_html=True)
export_records = web_memo_db.get_memos()
export_format = st.radio("导出格式", ["Markdown", "PDF"], horizontal=True)
if export_format == "Markdown":
    export_data = web_memo_db.build_markdown_export(export_records).encode("utf-8")
    st.download_button(
        "导出全部",
        data=export_data,
        file_name=f"灵感便签盒_{date.today().isoformat()}.md",
        mime="text/markdown",
        use_container_width=True,
    )
else:
    export_data = web_memo_db.build_pdf_export(export_records)
    st.download_button(
        "导出全部",
        data=export_data,
        file_name=f"灵感便签盒_{date.today().isoformat()}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
st.markdown("</section>", unsafe_allow_html=True)
