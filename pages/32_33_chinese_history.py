"""M33 · 中国通史图读。"""

import streamlit as st

from utils.chinese_history_component import FRONTEND, declare_history_reader
from utils.ui_theme import render_home_link


st.set_page_config(page_title="M33 · 中国通史图读", page_icon="📚", layout="wide")
render_home_link()
declare_history_reader()(key="history_reader", default=None)
st.download_button(
    "下载两卷 HTML（可离线阅读）",
    data=(FRONTEND / "index.html").read_bytes(),
    file_name="中国通史图读_周秦与楚汉.html",
    mime="text/html; charset=utf-8",
    on_click="ignore",
)
