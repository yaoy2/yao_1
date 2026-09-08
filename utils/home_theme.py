from functools import lru_cache
from pathlib import Path

import streamlit as st

from utils.ui_theme import load_theme_css


@lru_cache(maxsize=1)
def _home_css() -> str:
    return Path(__file__).with_name("home_theme.css").read_text(encoding="utf-8")


def apply_home_theme() -> None:
    css = load_theme_css() + "\n" + _home_css()
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)
