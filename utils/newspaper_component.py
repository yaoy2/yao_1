"""Register Newspaper from an importable module for multipage/Cloud runners."""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from utils.newspaper_data import fetch_newspaper_article, load_newspaper_feed


@st.cache_data(ttl=900, max_entries=1, show_spinner=False)
def cached_newspaper_feed():
    """Share a short-lived public feed without storing personal reading data."""
    return load_newspaper_feed()


@st.cache_data(ttl=3600, max_entries=192, show_spinner=False)
def cached_newspaper_article(article):
    detail = fetch_newspaper_article(article)
    if detail.get("status") == "error":
        # A temporary transport failure must not become a one-hour cached result.
        raise RuntimeError("News article temporarily unavailable")
    return detail


def declare_newspaper_component():
    frontend = Path(__file__).resolve().parents[1] / "integrations" / "newspaper" / "frontend"
    return components.declare_component("newspaper", path=str(frontend))
