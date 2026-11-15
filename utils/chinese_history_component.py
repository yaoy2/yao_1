"""Serve the self-contained M33 reader in Streamlit and as an offline HTML file."""

from pathlib import Path

import streamlit.components.v1 as components


FRONTEND = Path(__file__).resolve().parents[1] / "integrations" / "chinese_history" / "frontend"


def declare_history_reader():
    return components.declare_component("chinese_history_reader", path=str(FRONTEND))
