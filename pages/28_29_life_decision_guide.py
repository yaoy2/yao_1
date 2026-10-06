"""M29 · Search and read the attributed HowToLiveBetter snapshot."""

import streamlit as st

from utils.life_guide_component import declare_life_guide_component
from utils.ui_theme import render_home_link


st.set_page_config(page_title="M29·人生指南", page_icon="📖", layout="wide")
render_home_link()
st.markdown("### 📖 M29·人生指南")
st.caption("翻阅《高性价比人生指南》，按关键词、条件或具体问题查原文。每条结果保留章节出处、证据与适用条件。")
declare_life_guide_component()(key="m29_life_guide", default=None)
