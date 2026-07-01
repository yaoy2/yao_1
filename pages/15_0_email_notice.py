import os
import re
import sys
from datetime import date, datetime

import streamlit as st
import streamlit.components.v1 as components


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.email_notice_parser import DEFAULT_HEADER, parse_notice_text
from utils.email_notice_renderer import build_notice_html, build_notice_number, text_to_body_html
from utils.ui_theme import render_home_link


st.set_page_config(page_title="邮件通知编辑器", page_icon="✉️", layout="wide")


def apply_style():
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1500px;
            padding-top: 1.25rem !important;
            padding-bottom: 2rem !important;
        }
        .notice-title {
            margin: 0 0 .25rem;
            color: #182230;
            font-size: 2rem;
            line-height: 1.15;
            font-weight: 850;
        }
        .notice-subtitle {
            margin: 0 0 1rem;
            color: #667085;
            line-height: 1.65;
        }
        iframe {
            border-radius: 8px;
            background: #fff;
            box-shadow: 0 8px 24px rgba(24, 34, 48, .08);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _session_default(key, value):
    if key not in st.session_state:
        st.session_state[key] = value


def apply_parsed_notice(parsed):
    st.session_state["notice_header"] = parsed.get("header") or DEFAULT_HEADER
    st.session_state["notice_subject"] = parsed.get("subject", "")
    st.session_state["notice_number_digits"] = extract_notice_number_digits(parsed.get("number", ""))
    parsed_unit = parsed.get("unit", "")
    if parsed_unit in NOTICE_UNIT_OPTIONS:
        st.session_state["notice_unit"] = parsed_unit
    st.session_state["notice_date"] = parse_date_value(parsed.get("date", ""))
    st.session_state["notice_body"] = parsed.get("body_text", "")


def extract_notice_number_digits(notice_number):
    match = re.search(r"〔2026〕\s*(\d+)\s*号", str(notice_number or ""))
    return match.group(1) if match else ""


def parse_date_value(value):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return date.today()


def safe_filename(number, subject):
    raw_name = f"{number}_{subject}" if number else subject
    raw_name = raw_name or "通知"
    return re.sub(r'[\\/:*?"<>|]', "_", raw_name) + ".html"


render_home_link()
apply_style()

_session_default("notice_header", DEFAULT_HEADER)
_session_default("notice_subject", "")
_session_default("notice_number_digits", "")
NOTICE_UNIT_OPTIONS = ["健康医疗科技学院", "健康医疗科技学院党政办"]
_session_default("notice_unit", NOTICE_UNIT_OPTIONS[0])
_session_default("notice_date", date.today())
_session_default("notice_body", "")
_session_default("notice_table_width", 521.3)
_session_default("notice_header_height", 58)

st.markdown('<h1 class="notice-title">邮件通知编辑器</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="notice-subtitle">表头固定为“成都东软学院健康医疗科技学院”；粘贴内容请从通知主题开始。预览、源码和下载由 Streamlit 原生生成，避免嵌套按钮失效。</p>',
    unsafe_allow_html=True,
)

with st.form("email_notice_parse_form", clear_on_submit=False):
    raw_notice = st.text_area(
        "粘贴通知内容（从通知主题开始）",
        height=170,
        placeholder="第一行粘贴通知主题，后面继续粘贴编号、正文、落款单位和日期。",
    )
    parse_col, hint_col = st.columns([1, 5])
    with parse_col:
        recognize = st.form_submit_button("一键识别并填入", type="primary", use_container_width=True)
    with hint_col:
        st.caption("识别规则：第一行是通知主题；继续识别“通知〔年份〕编号”、末尾中文日期和日期上一行落款单位。")

if recognize:
    if not raw_notice.strip():
        st.warning("还没有识别到有效内容，请先粘贴通知内容。")
    else:
        apply_parsed_notice(parse_notice_text(raw_notice))
        st.success("已识别并填入下方字段。")

left, right = st.columns([0.92, 1.08], gap="large")

with left:
    st.subheader("编辑")
    st.text_input("表头", key="notice_header", disabled=True)
    st.text_input("通知主题", key="notice_subject")
    number_col, number_preview_col = st.columns([1, 2])
    with number_col:
        st.text_input("通知编号数字", key="notice_number_digits", placeholder="例如：41")
    notice_number = build_notice_number(st.session_state["notice_number_digits"])
    with number_preview_col:
        st.text_input("完整通知编号", value=notice_number, disabled=True)
    unit_col, date_col = st.columns(2)
    with unit_col:
        st.selectbox("落款单位", NOTICE_UNIT_OPTIONS, key="notice_unit")
    with date_col:
        st.date_input("落款日期", key="notice_date", format="YYYY-MM-DD")
    st.text_area("正文", key="notice_body", height=360)
    size_col, height_col = st.columns(2)
    with size_col:
        st.number_input("表格宽度(pt)", min_value=360.0, max_value=700.0, step=1.0, key="notice_table_width")
    with height_col:
        st.number_input("表头高度(px)", min_value=40, max_value=120, step=1, key="notice_header_height")

body_html = text_to_body_html(st.session_state["notice_body"])
notice_html = build_notice_html(
    header=st.session_state["notice_header"],
    subject=st.session_state["notice_subject"],
    number=notice_number,
    unit=st.session_state["notice_unit"],
    date_value=st.session_state["notice_date"],
    body_html=body_html,
    table_width_pt=st.session_state["notice_table_width"],
    header_height_px=st.session_state["notice_header_height"],
)

with right:
    st.subheader("实时预览")
    components.html(notice_html, height=720, scrolling=True)
    action_col, source_col = st.columns([1, 1])
    with action_col:
        st.download_button(
            "保存 HTML 文件",
            data=notice_html.encode("utf-8"),
            file_name=safe_filename(notice_number, st.session_state["notice_subject"]),
            mime="text/html",
            use_container_width=True,
        )
    with source_col:
        with st.popover("查看源代码", use_container_width=True):
            st.text_area("HTML 源代码", value=notice_html, height=420)
