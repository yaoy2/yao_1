from functools import lru_cache
from pathlib import Path

import streamlit as st

from utils.ui_theme import load_theme_css


HOME_THEME_VERSION = 2


@lru_cache(maxsize=1)
def _home_css(path: Path, modified_ns: int, size: int) -> str:
    return path.read_text(encoding="utf-8")


def apply_home_theme() -> None:
    path = Path(__file__).with_name("home_theme.css")
    version = path.stat()
    css = load_theme_css() + "\n" + _home_css(path, version.st_mtime_ns, version.st_size)
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)
