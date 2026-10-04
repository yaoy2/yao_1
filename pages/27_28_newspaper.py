"""M28: Newspaper's interactive design preview inside the personal toolbox."""

import streamlit as st

from utils.newspaper_component import declare_newspaper_component
from utils.ui_theme import render_home_link


st.set_page_config(page_title="M28·Newspaper", page_icon="📰", layout="wide")
render_home_link()
st.markdown("### 📰 M28·Newspaper")
st.caption(
    "个人 · 交互预览｜60 个栏目、文艺副刊、专题追踪与我的剪报。"
    "当前新闻和作品均为示例，真实新闻采集与私人同步尚未接入。"
)

newspaper = declare_newspaper_component()
newspaper(key="newspaper-preview-v1", default=None)
