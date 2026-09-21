"""Register the component from an importable module, including Cloud page runs."""

from pathlib import Path

import streamlit.components.v1 as components


def declare_transfer_component():
    # Multipage runners may execute a page without an inspectable module.
    # declare_component derives its identity from the calling module, so keep
    # this call in a normally imported module instead of in the page script.
    frontend = Path(__file__).resolve().parents[1] / "integrations" / "phone_transfer" / "frontend"
    return components.declare_component("suishouchuan", path=str(frontend))
