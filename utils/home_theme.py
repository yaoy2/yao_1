from pathlib import Path

import streamlit as st

_CSS_PATH = Path(__file__).with_name("home_theme.css")


def apply_home_theme() -> None:
    css = _CSS_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)
