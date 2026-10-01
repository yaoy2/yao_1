"""M11: retirement notice for Recorder."""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.ui_theme import render_home_link

st.set_page_config(page_title="Recorder_笔记 · 已停用", page_icon="❌", layout="wide")
render_home_link()
st.title("M11 · Recorder_笔记 ❌")
st.warning("Recorder 已停用：扫描、AI 整理、备注编辑和云端同步已关闭。")
st.write("原有记录与备份保留，页面仅显示停用说明。")
st.caption("archived · 2026-10-02")
