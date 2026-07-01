import json
import os
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.email_notice_parser import parse_notice_text
from utils.ui_theme import render_home_link


st.set_page_config(page_title="邮件通知编辑器", page_icon="✉️", layout="wide")

ROOT_DIR = Path(__file__).resolve().parents[1]
EDITOR_HTML_PATH = ROOT_DIR / "assets" / "email_notice_editor.html"


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
        .parsed-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: .65rem;
            margin: .4rem 0 .8rem;
        }
        .parsed-item {
            min-height: 72px;
            padding: .65rem .75rem;
            border: 1px solid rgba(24, 34, 48, .12);
            border-radius: 8px;
            background: #fff;
        }
        .parsed-item span {
            display: block;
            color: #667085;
            font-size: .78rem;
            font-weight: 750;
        }
        .parsed-item strong {
            display: block;
            margin-top: .28rem;
            color: #182230;
            font-size: .95rem;
            line-height: 1.42;
            word-break: break-word;
        }
        iframe {
            border-radius: 8px;
        }
        @media (max-width: 900px) {
            .parsed-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def load_editor_html():
    return EDITOR_HTML_PATH.read_text(encoding="utf-8")


def build_prefill_script(parsed):
    payload = {
        "inputHeader": parsed.get("header", ""),
        "inputSubject": parsed.get("subject", ""),
        "inputNumber": parsed.get("number", ""),
        "inputUnit": parsed.get("unit", ""),
        "inputDate": parsed.get("date", ""),
        "editorContent": parsed.get("body_html", ""),
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    return f"""
<script>
(function() {{
    const payload = {payload_json};
    function setValue(id, value) {{
        const el = document.getElementById(id);
        if (el && value !== undefined) {{
            el.value = value;
        }}
    }}
    setValue("inputHeader", payload.inputHeader);
    setValue("inputSubject", payload.inputSubject);
    setValue("inputNumber", payload.inputNumber);
    setValue("inputUnit", payload.inputUnit);
    setValue("inputDate", payload.inputDate);
    const editor = document.getElementById("editorContent");
    if (editor && payload.editorContent) {{
        editor.innerHTML = payload.editorContent;
    }}
    if (typeof applyStylesToEditor === "function") {{
        applyStylesToEditor();
    }} else if (typeof refreshPreview === "function") {{
        refreshPreview();
    }}
}})();
</script>
"""


def render_parsed_summary(parsed):
    fields = [
        ("表头", parsed.get("header") or "未识别"),
        ("主题", parsed.get("subject") or "未识别"),
        ("编号", parsed.get("number") or "未识别"),
        ("落款单位", parsed.get("unit") or "未识别"),
        ("落款日期", parsed.get("date") or "未识别"),
        ("正文行数", str(len([line for line in parsed.get("body_text", "").splitlines() if line.strip()]))),
    ]
    cards = "".join(
        f'<div class="parsed-item"><span>{label}</span><strong>{value}</strong></div>'
        for label, value in fields
    )
    st.markdown(f'<div class="parsed-grid">{cards}</div>', unsafe_allow_html=True)


render_home_link()
apply_style()

st.markdown('<h1 class="notice-title">邮件通知编辑器</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="notice-subtitle">表头固定为“成都东软学院健康医疗科技学院”；粘贴内容请从通知主题开始，一键识别后会自动填入下方编辑器。</p>',
    unsafe_allow_html=True,
)

if "email_notice_parsed" not in st.session_state:
    st.session_state["email_notice_parsed"] = {}

raw_notice = st.text_area(
    "粘贴通知内容（从通知主题开始）",
    height=190,
    placeholder="第一行粘贴通知主题，后面继续粘贴编号、正文、落款单位和日期。",
)

left, right = st.columns([1, 5])
with left:
    recognize = st.button("一键识别并填入", type="primary", use_container_width=True)
with right:
    st.caption("规则会把第一行识别为通知主题，并继续识别“通知〔年份〕编号”、末尾中文日期和日期上一行落款单位。")

if recognize:
    parsed = parse_notice_text(raw_notice)
    if not raw_notice.strip():
        st.warning("还没有识别到有效内容，请先粘贴通知全文。")
    else:
        st.session_state["email_notice_parsed"] = parsed
        st.success("已识别并填入下方编辑器，可继续微调后保存 HTML 或 PDF。")

parsed_notice = st.session_state.get("email_notice_parsed", {})
if parsed_notice:
    render_parsed_summary(parsed_notice)

editor_html = load_editor_html()
if parsed_notice:
    editor_html = editor_html.replace("</body>", build_prefill_script(parsed_notice) + "\n</body>")

components.html(editor_html, height=980, scrolling=True)
