"""M33 · 中国通史图读。"""

from pathlib import Path

import streamlit as st

from utils.ui_theme import render_home_link


st.set_page_config(page_title="M33 · 中国通史图读", page_icon="📚", layout="wide")
render_home_link()

st.title("中国通史图读")
st.subheader("第一卷　从西周到秦统一六国")
st.caption("7 页 · 西周分封、春秋争霸、三家分晋、秦灭六国")

pdf_path = Path(__file__).resolve().parents[1] / "assets" / "chinese-history" / "01-zhou-to-qin.pdf"
pdf = pdf_path.read_bytes()
st.download_button(
    "下载本卷 PDF",
    data=pdf,
    file_name="从西周到秦统一六国.pdf",
    mime="application/pdf",
    on_click="ignore",
)
st.pdf(pdf, height=760, key="history_volume_01")
