"""M19：A股研究与公开信息搜索中心。"""

from __future__ import annotations

import os
import sys

import streamlit as st


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stock.portal import render_stock_portal
from utils.ui_theme import render_home_link


st.set_page_config(page_title="股票研究中心", page_icon="📈", layout="wide")
render_home_link()
render_stock_portal()
