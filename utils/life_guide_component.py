"""Serve M29's self-contained public corpus without network or model credentials."""

from pathlib import Path

import streamlit.components.v1 as components


def declare_life_guide_component():
    # The normal module identity also works in Streamlit's multipage Cloud runner.
    frontend = Path(__file__).resolve().parents[1] / "integrations" / "life_guide" / "frontend"
    return components.declare_component("life_decision_guide", path=str(frontend))
