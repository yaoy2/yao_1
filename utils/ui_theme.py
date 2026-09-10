import ast
import re
from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import quote

import streamlit as st


_PINNED_SIDEBAR_CODES = {"M15", "M14", "M08", "M06"}


def _load_homepage_tools():
    hello_path = Path(__file__).resolve().parents[1] / "hello.py"
    try:
        module = ast.parse(hello_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "TOOLS" for target in node.targets):
            continue
        try:
            return ast.literal_eval(node.value)
        except Exception:
            return []
    return []


def _nav_sort_key(tool):
    code = str(tool.get("code", "M0")).removeprefix("M")
    try:
        module_number = int(code)
    except ValueError:
        module_number = 0
    return (tool.get("code") in _PINNED_SIDEBAR_CODES, not bool(tool.get("blocked")), module_number)


def _get_sidebar_tools(tools):
    return sorted(tools, key=_nav_sort_key, reverse=True)


def _streamlit_page_href(page_path):
    page_name = Path(str(page_path)).name
    match = re.match(r"([0-9]*)[_ -]*(.*)\.py$", page_name)
    if not match:
        return "#"
    url_path = re.sub(r"[_ ]+", "_", match.group(2)).strip() or match.group(1)
    return f"/{quote(url_path)}"


def render_sidebar_nav() -> None:
    _inject_theme()
    tools = _load_homepage_tools()
    if not tools:
        return
    ordered_tools = _get_sidebar_tools(tools)

    def item_html(tool):
        title = escape(str(tool.get("title", "")))
        code = escape(str(tool.get("code", "")))
        tag = escape(str(tool.get("tag", "")))
        href = escape(_streamlit_page_href(tool.get("page", "")), quote=True)
        lock = " 🔒" if tool.get("locked") else ""
        blocked_mark = "❌ " if tool.get("blocked") else ""
        return (
            f'<a class="custom-nav-item" href="{href}" target="_self">'
            f'<span class="custom-nav-code">{code}</span>'
            f'<span class="custom-nav-main"><strong><span class="custom-nav-marks">{blocked_mark}</span>'
            f'<span class="custom-nav-label">{title}</span>'
            f'<span class="custom-nav-marks">{lock}</span></strong><em>{tag}</em></span>'
            "</a>"
        )

    nav_html = "".join(item_html(tool) for tool in ordered_tools)
    st.sidebar.markdown(
        f"""
        <div class="custom-nav-title"><span class="custom-nav-brand-mark">Y</span>YaoYao 工具箱</div>
        <div class="custom-nav-section">全部模块</div>
        {nav_html}
        """,
        unsafe_allow_html=True,
    )


@lru_cache(maxsize=1)
def load_theme_css() -> str:
    """Read immutable bundled styles once per process, never cache UI rendering."""
    directory = Path(__file__).parent
    return "\n".join(
        (directory / name).read_text(encoding="utf-8")
        for name in ("theme_tokens.css", "ui_theme.css")
    )


def _inject_theme() -> None:
    # Emit on every rerun: session state survives navigation, style elements do not.
    st.markdown(f"<style>\n{load_theme_css()}\n</style>", unsafe_allow_html=True)


def apply_global_theme(*, include_sidebar: bool = True) -> None:
    """Apply the shared shell; independent apps can keep their own navigation."""
    if include_sidebar:
        render_sidebar_nav()
    else:
        _inject_theme()


def render_home_link(*, include_sidebar: bool = True) -> None:
    """Initialize a toolbox page before authentication, then render its home control."""
    apply_global_theme(include_sidebar=include_sidebar)
    with st.container(key="home-link-fixed"):
        if st.button("回到主页", icon="🏠", width="content"):
            st.switch_page("hello.py")


def apply_home_theme() -> None:
    from utils.home_theme import apply_home_theme as _apply_home_theme

    _apply_home_theme()
