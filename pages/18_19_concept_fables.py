"""M19：概念寓言馆（只读展示入口）。"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from concept_fables.page import render_page
from utils.ui_theme import render_home_link


st.set_page_config(page_title="概念寓言馆", page_icon="📜", layout="wide")
render_home_link()
render_page()
