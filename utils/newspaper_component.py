"""Register Newspaper from an importable module for multipage/Cloud runners."""

from pathlib import Path

import streamlit.components.v1 as components


def declare_newspaper_component():
    frontend = Path(__file__).resolve().parents[1] / "integrations" / "newspaper" / "frontend"
    return components.declare_component("newspaper", path=str(frontend))
