import ast
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

import streamlit as st


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
    return (str(tool.get("created", "")), module_number)


def _get_sidebar_tools(tools):
    return sorted(tools, key=_nav_sort_key, reverse=True)


def _streamlit_page_href(page_path):
    page_name = Path(str(page_path)).name
    match = re.match(r"([0-9]*)[_ -]*(.*)\.py$", page_name)
    if not match:
        return "#"
    url_path = re.sub(r"[_ ]+", "_", match.group(2)).strip() or match.group(1)
    return f"/{quote(url_path)}"


def _current_script_name() -> str:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx is not None and getattr(ctx, "main_script_path", None):
            return Path(ctx.main_script_path).name
    except Exception:
        pass
    return ""


def render_sidebar_nav() -> None:
    tools = _load_homepage_tools()
    if not tools:
        return
    ordered_tools = _get_sidebar_tools(tools)
    current_name = _current_script_name()

    def item_html(tool):
        title = escape(str(tool.get("title", "")))
        code = escape(str(tool.get("code", "")))
        tag = escape(str(tool.get("tag", "")))
        href = escape(_streamlit_page_href(tool.get("page", "")), quote=True)
        lock = " 🔒" if tool.get("locked") else ""
        blocked_mark = " ❌" if tool.get("blocked") else ""
        page_name = Path(str(tool.get("page", ""))).name
        classes = ["custom-nav-item"]
        if page_name and page_name == current_name:
            classes.append("is-active")
        if tool.get("blocked"):
            classes.append("is-blocked")
        if tool.get("locked"):
            classes.append("is-locked")
        class_attr = " ".join(classes)
        return (
            f'<a class="{class_attr}" href="{href}" target="_self">'
            f'<span class="custom-nav-code">{code}</span>'
            f'<span class="custom-nav-main"><strong>{title}{lock}{blocked_mark}</strong><em>{tag}</em></span>'
            "</a>"
        )

    nav_html = "".join(item_html(tool) for tool in ordered_tools)
    st.sidebar.markdown(
        f"""
        <style>
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #07111f 0%, #05090f 100%) !important;
            border-right: 1px solid rgba(115, 238, 255, .18) !important;
        }}
        [data-testid="stSidebar"] * {{
            color: rgba(234, 247, 255, .86);
        }}
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] {{
            display: none;
        }}
        .custom-nav-title {{
            margin: .35rem .45rem .55rem;
            color: #EAF7FF;
            font-size: .92rem;
            font-weight: 850;
        }}
        .custom-nav-item {{
            display: grid;
            grid-template-columns: 2.75rem minmax(0, 1fr);
            gap: .55rem;
            align-items: center;
            margin: .14rem .35rem;
            padding: .46rem .56rem;
            border: 1px solid rgba(57, 223, 247, .14);
            border-radius: 8px;
            background: rgba(255,255,255,.025);
            text-decoration: none !important;
        }}
        .custom-nav-item:hover {{
            border-color: rgba(57, 223, 247, .32);
            background: rgba(57, 223, 247, .09);
        }}
        .custom-nav-item.is-active {{
            border-color: rgba(57, 223, 247, .48);
            background: rgba(57, 223, 247, .14);
            box-shadow: inset 3px 0 0 #39DFF7;
        }}
        .custom-nav-item.is-blocked {{
            opacity: .48;
            filter: grayscale(.55);
        }}
        .custom-nav-item.is-blocked:hover {{
            opacity: .62;
        }}
        .custom-nav-item.is-locked:not(.is-blocked) {{
            border-color: rgba(245, 184, 75, .28);
        }}
        .custom-nav-code {{
            color: #39DFF7;
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .78rem;
            font-weight: 850;
        }}
        .custom-nav-item.is-blocked .custom-nav-code {{
            color: rgba(234, 247, 255, .42);
        }}
        .custom-nav-main {{
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: .08rem;
        }}
        .custom-nav-main strong {{
            overflow: hidden;
            color: #EAF7FF;
            font-size: .86rem;
            line-height: 1.24;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .custom-nav-main em {{
            overflow: hidden;
            color: rgba(234, 247, 255, .56);
            font-size: .72rem;
            font-style: normal;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .custom-nav-section {{
            margin: .7rem .48rem .2rem;
            color: rgba(234, 247, 255, .52);
            font-size: .72rem;
            font-weight: 780;
            letter-spacing: .08em;
        }}
        </style>
        <div class="custom-nav-title">YaoYao 工具箱</div>
        <div class="custom-nav-section">按模块编号</div>
        {nav_html}
        """,
        unsafe_allow_html=True,
    )


def _workbench_shell_css() -> str:
    """Shared shell for inner tool pages: dark base, cyan controls, home link."""
    return """
        <style>
        :root {
            --wb-ink: #eaf7ff;
            --wb-muted: #95a8b8;
            --wb-panel: rgba(9, 18, 31, .82);
            --wb-line: rgba(115, 238, 255, .18);
            --wb-cyan: #39dff7;
            --wb-green: #54f0a3;
            --wb-amber: #f5b84b;
        }

        .stApp {
            color: var(--wb-ink);
            background:
                linear-gradient(rgba(57, 223, 247, .028) 1px, transparent 1px),
                linear-gradient(90deg, rgba(57, 223, 247, .028) 1px, transparent 1px),
                linear-gradient(135deg, #05070d 0%, #071525 42%, #0c1420 100%);
            background-size: 28px 28px, 28px 28px, auto;
        }

        .block-container {
            position: relative;
            z-index: 1;
            max-width: 1280px;
            padding-top: 1.15rem !important;
            padding-bottom: 3rem !important;
        }

        h1, h2, h3 {
            color: var(--wb-ink) !important;
            letter-spacing: 0;
        }

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] button {
            border-radius: 8px;
            border: 1px solid rgba(57, 223, 247, .55);
            background: linear-gradient(135deg, rgba(57, 223, 247, .94), rgba(84, 240, 163, .88));
            color: #06101b;
            font-weight: 820;
            box-shadow: 0 0 0 1px rgba(57, 223, 247, .08), 0 10px 22px rgba(57, 223, 247, .14);
        }

        div[data-baseweb="select"] > div,
        input,
        textarea,
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stNumberInput"] input {
            border-radius: 8px !important;
            border-color: rgba(57, 223, 247, .24) !important;
            background-color: rgba(8, 17, 29, .9) !important;
            color: var(--wb-ink) !important;
        }

        hr {
            border-color: rgba(115, 238, 255, .16);
        }

        .home-link-fixed {
            position: fixed;
            top: 4.1rem;
            right: 1.35rem;
            z-index: 999999;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 34px;
            padding: 0 .72rem;
            border: 1px solid rgba(57, 223, 247, .36);
            border-radius: 8px;
            background: rgba(8, 17, 29, .92);
            color: #EAF7FF !important;
            font-size: .86rem;
            font-weight: 750;
            text-decoration: none !important;
            box-shadow: 0 10px 26px rgba(0, 0, 0, .32);
            backdrop-filter: blur(8px);
        }
        .home-link-fixed:hover {
            border-color: rgba(57, 223, 247, .62);
            background: rgba(57, 223, 247, .12);
            color: #39DFF7 !important;
        }
        @media (max-width: 720px) {
            .home-link-fixed {
                top: 3.65rem;
                right: .75rem;
                min-height: 32px;
                padding: 0 .56rem;
                font-size: .8rem;
            }
        }
        </style>
        <a class="home-link-fixed" href="/" target="_self">🏠 回到主页</a>
    """


def render_home_link() -> None:
    render_sidebar_nav()
    st.markdown(_workbench_shell_css(), unsafe_allow_html=True)


def apply_global_theme() -> None:
    render_sidebar_nav()
    st.markdown(
        """
        <style>
        :root {
            --ink: #eaf7ff;
            --muted: #95a8b8;
            --panel: rgba(9, 18, 31, .82);
            --line: rgba(115, 238, 255, .16);
            --cyan: #39dff7;
            --green: #54f0a3;
            --amber: #f5b84b;
            --magenta: #ff5ca8;
            --red: #ff6b6b;
            --shadow: 0 14px 40px rgba(0, 0, 0, .34);
        }

        .stApp {
            color: var(--ink);
            background:
                linear-gradient(rgba(57, 223, 247, .03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(57, 223, 247, .03) 1px, transparent 1px),
                linear-gradient(135deg, #05070d 0%, #071525 38%, #101421 68%, #0e1218 100%);
            background-size: 28px 28px, 28px 28px, auto;
        }

        .stApp::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,0) 22%);
            mix-blend-mode: screen;
            opacity: .45;
            z-index: 0;
        }

        .block-container {
            position: relative;
            z-index: 1;
            max-width: 1280px;
            padding-top: 1rem !important;
            padding-bottom: 2.8rem !important;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #07111f 0%, #05090f 100%);
            border-right: 1px solid var(--line);
        }

        [data-testid="stSidebar"] * {
            color: rgba(234, 247, 255, .86);
        }

        [data-testid="stSidebar"] a {
            border-radius: 6px;
            margin: .15rem .35rem;
            border: 1px solid transparent;
        }

        [data-testid="stSidebar"] a:hover {
            background: rgba(57, 223, 247, .09);
            border-color: rgba(57, 223, 247, .2);
        }

        h1, h2, h3 {
            color: var(--ink);
            letter-spacing: 0;
        }

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] button {
            border-radius: 8px;
            border: 1px solid rgba(57, 223, 247, .55);
            background: linear-gradient(135deg, rgba(57, 223, 247, .94), rgba(84, 240, 163, .88));
            color: #06101b;
            font-weight: 820;
            box-shadow: 0 0 0 1px rgba(57, 223, 247, .08), 0 12px 28px rgba(57, 223, 247, .18);
        }

        div[data-baseweb="select"] > div,
        input,
        textarea {
            border-radius: 8px !important;
            border-color: rgba(57, 223, 247, .24) !important;
            background-color: rgba(8, 17, 29, .9) !important;
            color: var(--ink) !important;
        }

        hr {
            border-color: rgba(115, 238, 255, .16);
            margin: 1.4rem 0;
        }

        /* —— Compact command hero —— */
        .command-hero {
            position: relative;
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: .85rem;
            align-items: stretch;
            min-height: 0;
            overflow: hidden;
            padding: .72rem .9rem .68rem;
            border: 1px solid rgba(57, 223, 247, .24);
            border-radius: 8px;
            background:
                linear-gradient(120deg, rgba(12, 24, 40, .96), rgba(7, 13, 24, .94) 52%, rgba(18, 16, 14, .9));
            box-shadow: var(--shadow), inset 0 0 0 1px rgba(255, 255, 255, .03);
        }

        .hero-grid {
            position: absolute;
            inset: 0;
            background:
                linear-gradient(90deg, rgba(57,223,247,.05) 1px, transparent 1px),
                linear-gradient(180deg, rgba(57,223,247,.05) 1px, transparent 1px);
            background-size: 36px 36px;
            pointer-events: none;
            opacity: .7;
        }

        .hero-copy-block {
            position: relative;
            z-index: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
            min-width: 0;
            padding: .28rem .4rem .2rem .28rem;
        }

        .hero-kicker {
            width: fit-content;
            padding: .22rem .5rem;
            border: 1px solid rgba(57, 223, 247, .28);
            border-radius: 999px;
            color: var(--cyan);
            background: rgba(57, 223, 247, .06);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .72rem;
            font-weight: 820;
            letter-spacing: .08em;
            text-transform: uppercase;
        }

        .hero-title {
            max-width: 900px;
            margin-top: .32rem;
            color: #f7fbff;
            font-size: clamp(1.55rem, 2.6vw, 2.15rem);
            line-height: 1.12;
            font-weight: 900;
            white-space: nowrap;
            text-shadow: 0 0 22px rgba(57, 223, 247, .14);
        }

        .hero-copy {
            max-width: 720px;
            margin-top: .32rem;
            color: rgba(234, 247, 255, .7);
            font-size: .9rem;
            line-height: 1.5;
        }

        .hero-status {
            display: flex;
            flex-wrap: wrap;
            gap: .4rem;
            margin-top: .55rem;
        }

        .hero-stat {
            display: inline-flex;
            align-items: baseline;
            gap: .28rem;
            min-height: 28px;
            padding: .2rem .55rem;
            border: 1px solid rgba(57, 223, 247, .18);
            border-radius: 6px;
            background: rgba(4, 10, 18, .45);
            color: rgba(234, 247, 255, .72);
            font-size: .78rem;
            font-weight: 680;
        }

        .hero-stat b {
            color: var(--cyan);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .86rem;
            font-weight: 860;
        }

        .hero-stat.amber b { color: var(--amber); }
        .hero-stat.muted b { color: var(--muted); }
        .hero-stat.green b { color: var(--green); }

        .hero-visual {
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: .35rem .5rem;
            align-content: center;
            min-width: 168px;
            max-width: 200px;
            padding: .55rem .6rem;
            border: 1px solid rgba(57, 223, 247, .2);
            border-radius: 8px;
            background: rgba(4, 9, 16, .72);
            box-shadow: inset 0 0 20px rgba(57, 223, 247, .04);
        }

        .hero-visual .meter-item {
            display: flex;
            flex-direction: column;
            gap: .08rem;
            min-width: 0;
        }

        .hero-visual .meter-label {
            color: rgba(234, 247, 255, .48);
            font-size: .68rem;
            font-weight: 720;
            letter-spacing: .04em;
            text-transform: uppercase;
        }

        .hero-visual .meter-value {
            color: var(--cyan);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: 1.05rem;
            font-weight: 880;
            line-height: 1.1;
        }

        .hero-visual .meter-item.amber .meter-value { color: var(--amber); }
        .hero-visual .meter-item.muted .meter-value { color: var(--muted); }
        .hero-visual .meter-item.green .meter-value { color: var(--green); }

        .section-heading {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 1rem;
            margin: 1.15rem 0 .55rem;
        }

        .section-heading h2 {
            margin: .12rem 0 0;
            color: var(--ink);
            font-size: clamp(1.15rem, 2.2vw, 1.55rem);
        }

        .section-heading p {
            max-width: 430px;
            margin: 0;
            color: var(--muted);
            font-size: .9rem;
            line-height: 1.55;
        }

        .section-label {
            color: var(--cyan);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .74rem;
            font-weight: 860;
            letter-spacing: .1em;
            text-transform: uppercase;
        }

        /* —— Dense tool tiles —— */
        .tool-card {
            position: relative;
            display: block;
            min-height: 148px;
            padding: .78rem .82rem .72rem;
            overflow: hidden;
            border: 1px solid rgba(57, 223, 247, .18);
            border-radius: 8px;
            background: var(--panel);
            box-shadow: 0 10px 26px rgba(0, 0, 0, .24);
            text-decoration: none !important;
            transition: border-color .15s ease, box-shadow .15s ease, opacity .15s ease;
        }

        .tool-card-shell {
            position: relative;
            margin-bottom: .15rem;
        }

        .tool-card::before {
            content: "";
            position: absolute;
            inset: 0;
            border-top: 2px solid var(--cyan);
            opacity: .8;
            pointer-events: none;
        }

        .tool-card.amber::before { border-top-color: var(--amber); }
        .tool-card.green::before { border-top-color: var(--green); }
        .tool-card.magenta::before { border-top-color: var(--magenta); }

        .tool-card.is-locked:not(.is-blocked)::before {
            border-top-color: var(--amber);
        }

        .tool-card.is-blocked {
            opacity: .48;
            filter: grayscale(.62) saturate(.35);
            border-color: rgba(148, 163, 184, .18);
            box-shadow: none;
            background: rgba(12, 16, 22, .72);
        }

        .tool-card.is-blocked::before {
            border-top-color: rgba(148, 163, 184, .45);
            opacity: .55;
        }

        .tool-card.is-blocked .tool-title {
            color: rgba(234, 247, 255, .55) !important;
        }

        .tool-card.is-blocked .tool-meta,
        .tool-card.is-blocked .tool-code,
        .tool-card.is-blocked .tool-date {
            color: rgba(234, 247, 255, .4);
        }

        .tool-card.is-blocked .tool-tag {
            color: rgba(234, 247, 255, .42);
            border-color: rgba(148, 163, 184, .28);
            background: rgba(148, 163, 184, .06);
        }

        .tool-card:not(.is-blocked):hover {
            border-color: rgba(57, 223, 247, .36);
            box-shadow: 0 12px 30px rgba(0, 0, 0, .3);
        }

        .tool-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: .55rem;
        }

        .tool-code,
        .tool-date {
            font-size: .72rem;
            font-weight: 840;
        }

        .tool-code {
            color: var(--cyan);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
        }

        .tool-date {
            color: var(--muted);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
        }

        .tool-title {
            display: inline-flex;
            align-items: center;
            margin-top: .42rem;
            color: var(--ink) !important;
            font-size: 1.02rem;
            font-weight: 860;
            min-height: 28px;
            line-height: 1.28;
            text-decoration: none !important;
        }

        .tool-title:hover {
            color: var(--cyan) !important;
        }

        .tool-lock {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.2rem;
            height: 1.2rem;
            padding: 0;
            border: 1px solid rgba(245, 184, 75, .42);
            border-radius: 999px;
            color: #F8D78C;
            background: rgba(245, 184, 75, .1);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, .08);
            font-size: .74rem;
            line-height: 1;
            font-weight: 860;
        }

        .tool-blocked {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.2rem;
            height: 1.2rem;
            padding: 0;
            border: 0;
            background: transparent;
            box-shadow: none;
            font-size: .86rem;
            line-height: 1;
            font-weight: 920;
            opacity: .7;
        }

        .tool-lock-spacer {
            width: 1.2rem;
            height: 1.2rem;
        }

        .tool-meta {
            display: -webkit-box;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 2;
            line-clamp: 2;
            overflow: hidden;
            min-height: 2.7em;
            margin-top: .32rem;
            color: rgba(234, 247, 255, .64);
            font-size: .84rem;
            line-height: 1.45;
        }

        .tool-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: .45rem;
            margin-top: .55rem;
        }

        .tool-tag {
            display: inline-flex;
            align-items: center;
            min-height: 24px;
            padding: .16rem .48rem;
            border: 1px solid rgba(245, 184, 75, .3);
            border-radius: 999px;
            color: var(--amber);
            background: rgba(245, 184, 75, .06);
            font-size: .72rem;
            font-weight: 760;
        }

        .quote-strip {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-top: 1.1rem;
            padding: .78rem .95rem;
            border: 1px solid rgba(57, 223, 247, .18);
            border-left: 3px solid var(--magenta);
            border-radius: 8px;
            background: rgba(9, 18, 31, .58);
            color: rgba(234, 247, 255, .82);
            font-weight: 680;
            font-size: .92rem;
        }

        .quote-strip span {
            flex: 0 0 auto;
            color: var(--muted);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .74rem;
        }

        /* —— Pagination (cyan system) —— */
        .pagination-bar {
            display: inline-flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 0;
            margin: .1rem 0 .55rem auto;
            border: 1px solid rgba(57, 223, 247, .28);
            border-radius: 8px;
            background: rgba(8, 17, 29, .82);
            box-shadow: 0 12px 28px rgba(0, 0, 0, .24), inset 0 1px 0 rgba(255,255,255,.05);
            overflow: hidden;
            backdrop-filter: blur(10px);
        }
        .pagination-dock {
            display: flex;
            justify-content: flex-end;
            margin-top: .2rem;
            margin-bottom: .1rem;
        }
        .pagination-item,
        .pagination-counter {
            min-width: 2.25rem;
            height: 2.05rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0 .68rem;
            border-right: 1px solid rgba(57, 223, 247, .14);
            color: #D6E4F0;
            font-size: .88rem;
            font-weight: 750;
            text-decoration: none !important;
            letter-spacing: 0;
        }
        .pagination-item:hover {
            color: #ffffff;
            background: rgba(57, 223, 247, .16);
        }
        .pagination-item.active {
            color: #06101b;
            background: linear-gradient(180deg, rgba(57, 223, 247, .95), rgba(84, 240, 163, .82));
            box-shadow: inset 0 -2px 0 rgba(57, 223, 247, .35);
            font-weight: 860;
        }
        .pagination-item.disabled {
            color: rgba(214, 228, 240, .34);
            background: rgba(255,255,255,.03);
            pointer-events: none;
        }
        .pagination-item.text {
            min-width: 4.4rem;
            color: #D6E4F0;
            font-weight: 700;
        }
        .pagination-counter {
            min-width: 5rem;
            color: #EAF7FF;
            background: rgba(57, 223, 247, .1);
            font-weight: 850;
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .82rem;
        }
        .pagination-bar > :last-child {
            border-right: 0;
        }

        @media (max-width: 980px) {
            .command-hero {
                grid-template-columns: 1fr;
            }
            .hero-title {
                white-space: normal;
            }
            .hero-visual {
                max-width: none;
                min-width: 0;
                grid-template-columns: repeat(4, minmax(0, 1fr));
            }
            .section-heading {
                align-items: flex-start;
                flex-direction: column;
            }
        }

        @media (max-width: 620px) {
            .command-hero {
                padding: .75rem;
            }
            .hero-title {
                font-size: 1.45rem;
            }
            .hero-visual {
                grid-template-columns: 1fr 1fr;
            }
            .quote-strip {
                align-items: stretch;
                flex-direction: column;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
