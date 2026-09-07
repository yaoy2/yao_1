"""M20: retirement notice for the legacy Ding2026 system."""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.ui_theme import render_home_link

st.set_page_config(page_title="Ding2026 · 已停用", page_icon="❌", layout="wide")
render_home_link()
st.title("M20 · Ding2026 文件中转发放系统 ❌")
st.warning("旧版已停用：原有功能说明、统计及执行逻辑全部作废。")
st.write("后续使用本机双击执行的会议纪要分发工具，仅处理 Ding2026 根目录直属会议纪要。")
st.caption("archived · 2026-09-07")
