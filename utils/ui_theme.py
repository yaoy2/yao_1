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
    return (not bool(tool.get("blocked")), str(tool.get("created", "")), module_number)


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
        blocked_mark = " ❌" if tool.get("blocked") else ""
        return (
            f'<a class="custom-nav-item" href="{href}" target="_self">'
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
            margin: .35rem .45rem .6rem;
            color: #EAF7FF;
            font-size: .92rem;
            font-weight: 850;
        }}
        .custom-nav-item {{
            display: grid;
            grid-template-columns: 2.75rem minmax(0, 1fr);
            gap: .55rem;
            align-items: center;
            margin: .18rem .35rem;
            padding: .54rem .58rem;
            border: 1px solid rgba(57, 223, 247, .14);
            border-radius: 8px;
            background: rgba(255,255,255,.025);
            text-decoration: none !important;
        }}
        .custom-nav-item:hover {{
            border-color: rgba(57, 223, 247, .32);
            background: rgba(57, 223, 247, .09);
        }}
        .custom-nav-code {{
            color: #39DFF7;
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .78rem;
            font-weight: 850;
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
            margin: .75rem .48rem .25rem;
            color: rgba(234, 247, 255, .52);
            font-size: .72rem;
            font-weight: 780;
            letter-spacing: .08em;
        }}
        </style>
        <div class="custom-nav-title">YaoYao 工具箱</div>
        <div class="custom-nav-section">按需排序</div>
        {nav_html}
        """,
        unsafe_allow_html=True,
    )


def render_home_link() -> None:
    render_sidebar_nav()
    st.markdown(
        """
        <style>
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
            border: 1px solid rgba(24, 34, 48, .16);
            border-radius: 8px;
            background: rgba(255, 255, 255, .94);
            color: #182230 !important;
            font-size: .86rem;
            font-weight: 750;
            text-decoration: none !important;
            box-shadow: 0 10px 26px rgba(24, 34, 48, .12);
        }
        .home-link-fixed:hover {
            border-color: rgba(45, 106, 79, .35);
            background: #f8fffb;
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
        """,
        unsafe_allow_html=True,
    )


def apply_global_theme() -> None:
    render_sidebar_nav()
    st.markdown(
        """
        <style>
        :root {
            --ink: #eaf7ff;
            --muted: #95a8b8;
            --panel: rgba(9, 18, 31, .82);
            --line: rgba(115, 238, 255, .18);
            --cyan: #39dff7;
            --green: #54f0a3;
            --amber: #f5b84b;
            --magenta: #ff5ca8;
            --red: #ff6b6b;
            --shadow: 0 20px 60px rgba(0, 0, 0, .38);
        }

        .stApp {
            color: var(--ink);
            background:
                linear-gradient(rgba(57, 223, 247, .045) 1px, transparent 1px),
                linear-gradient(90deg, rgba(57, 223, 247, .045) 1px, transparent 1px),
                linear-gradient(135deg, #05070d 0%, #071525 38%, #101421 68%, #14100d 100%);
            background-size: 28px 28px, 28px 28px, auto;
        }

        .stApp::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background:
                linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,0) 26%),
                repeating-linear-gradient(180deg, rgba(255,255,255,.025) 0, rgba(255,255,255,.025) 1px, transparent 1px, transparent 4px);
            mix-blend-mode: screen;
            opacity: .62;
            z-index: 0;
        }

        .block-container {
            position: relative;
            z-index: 1;
            max-width: 1280px;
            padding-top: 1.3rem !important;
            padding-bottom: 3.5rem !important;
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
            margin: 1.8rem 0;
        }

        .command-hero {
            position: relative;
            display: grid;
            grid-template-columns: minmax(0, 1.22fr) minmax(320px, .78fr);
            gap: 1rem;
            min-height: 0;
            overflow: hidden;
            padding: .85rem 1rem .62rem;
            border: 1px solid rgba(57, 223, 247, .28);
            border-radius: 8px;
            background:
                linear-gradient(120deg, rgba(12, 24, 40, .96), rgba(7, 13, 24, .94) 48%, rgba(26, 18, 12, .92));
            box-shadow: var(--shadow), inset 0 0 0 1px rgba(255, 255, 255, .035);
        }

        .hero-grid {
            position: absolute;
            inset: 0;
            background:
                linear-gradient(90deg, rgba(57,223,247,.07) 1px, transparent 1px),
                linear-gradient(180deg, rgba(57,223,247,.07) 1px, transparent 1px);
            background-size: 42px 42px;
            pointer-events: none;
        }

        .hero-copy-block {
            position: relative;
            z-index: 1;
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
            min-width: 0;
            padding: .48rem .72rem .38rem .5rem;
        }

        .hero-kicker {
            width: fit-content;
            padding: .35rem .6rem;
            border: 1px solid rgba(57, 223, 247, .32);
            border-radius: 999px;
            color: var(--cyan);
            background: rgba(57, 223, 247, .06);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .78rem;
            font-weight: 820;
            letter-spacing: .08em;
            text-transform: uppercase;
        }

        .hero-title {
            max-width: 900px;
            margin-top: .46rem;
            color: #f7fbff;
            font-size: clamp(2.25rem, 4.1vw, 3.85rem);
            line-height: 1;
            font-weight: 920;
            white-space: nowrap;
            text-shadow: 0 0 34px rgba(57, 223, 247, .22);
        }

        .hero-copy {
            max-width: 660px;
            margin-top: .58rem;
            color: rgba(234, 247, 255, .76);
            font-size: .98rem;
            line-height: 1.62;
        }

        .hero-visual {
            position: relative;
            z-index: 1;
            align-self: center;
            min-width: 0;
            min-height: 190px;
            max-width: 420px;
            width: 100%;
            justify-self: end;
            padding: .7rem;
            border: 1px solid rgba(57, 223, 247, .24);
            border-radius: 8px;
            background:
                radial-gradient(circle at 70% 28%, rgba(255, 92, 168, .16), transparent 34%),
                radial-gradient(circle at 32% 70%, rgba(84, 240, 163, .14), transparent 32%),
                rgba(4, 9, 16, .74);
            box-shadow: inset 0 0 30px rgba(57, 223, 247, .06), 0 18px 46px rgba(0, 0, 0, .32);
        }

        .visual-orbit {
            position: absolute;
            inset: 1.1rem 1.1rem 1.1rem;
            border: 1px solid rgba(57, 223, 247, .18);
            border-radius: 8px;
            background:
                linear-gradient(90deg, rgba(57,223,247,.06) 1px, transparent 1px),
                linear-gradient(180deg, rgba(57,223,247,.06) 1px, transparent 1px);
            background-size: 32px 32px;
        }

        .orbit-core {
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            display: flex;
            align-items: center;
            justify-content: center;
            width: 92px;
            height: 92px;
            border: 1px solid rgba(57, 223, 247, .44);
            border-radius: 50%;
            color: var(--cyan);
            background: rgba(57, 223, 247, .08);
            box-shadow: 0 0 50px rgba(57, 223, 247, .16);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-weight: 880;
            letter-spacing: .08em;
            text-align: center;
        }

        .orbit-node {
            position: absolute;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            background: var(--cyan);
            box-shadow: 0 0 28px rgba(57, 223, 247, .38);
        }

        .node-a {
            left: 14%;
            top: 20%;
        }

        .node-b {
            right: 16%;
            top: 26%;
            background: var(--amber);
            box-shadow: 0 0 28px rgba(245, 184, 75, .36);
        }

        .node-c {
            left: 25%;
            bottom: 18%;
            background: var(--green);
            box-shadow: 0 0 28px rgba(84, 240, 163, .34);
        }

        .node-d {
            right: 24%;
            bottom: 22%;
            background: var(--magenta);
            box-shadow: 0 0 28px rgba(255, 92, 168, .34);
        }

        .section-heading {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 1.25rem;
            margin: 1.75rem 0 .8rem;
        }

        .section-heading h2 {
            margin: .18rem 0 0;
            color: var(--ink);
            font-size: clamp(1.35rem, 2.8vw, 2.15rem);
        }

        .section-heading p {
            max-width: 430px;
            margin: 0;
            color: var(--muted);
            font-size: .94rem;
            line-height: 1.7;
        }

        .section-label {
            color: var(--cyan);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .78rem;
            font-weight: 860;
            letter-spacing: .1em;
            text-transform: uppercase;
        }

        .tool-card {
            position: relative;
            display: block;
            min-height: 190px;
            padding: 1rem 1rem .95rem;
            overflow: hidden;
            border: 1px solid rgba(57, 223, 247, .2);
            border-radius: 8px;
            background: var(--panel);
            box-shadow: 0 14px 36px rgba(0, 0, 0, .28);
            text-decoration: none !important;
        }

        .tool-card-shell {
            position: relative;
        }

        .tool-card::before {
            content: "";
            position: absolute;
            inset: 0;
            border-top: 2px solid var(--cyan);
            opacity: .85;
            pointer-events: none;
        }

        .tool-card.amber::before { border-top-color: var(--amber); }
        .tool-card.green::before { border-top-color: var(--green); }
        .tool-card.magenta::before { border-top-color: var(--magenta); }

        .tool-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: .75rem;
        }

        .tool-code,
        .tool-date {
            font-size: .76rem;
            font-weight: 840;
        }

        .tool-date {
            color: var(--muted);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
        }

        .tool-title {
            display: inline-flex;
            align-items: center;
            margin-top: .72rem;
            color: var(--ink) !important;
            font-size: 1.16rem;
            font-weight: 860;
            min-height: 34px;
            text-decoration: none !important;
        }

        .tool-title:hover {
            color: var(--cyan) !important;
        }

        .tool-lock {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.28rem;
            height: 1.28rem;
            padding: 0;
            border: 1px solid rgba(245, 184, 75, .42);
            border-radius: 999px;
            color: #F8D78C;
            background: rgba(245, 184, 75, .1);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, .08);
            font-size: .78rem;
            line-height: 1;
            font-weight: 860;
        }

        .tool-blocked {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.28rem;
            height: 1.28rem;
            padding: 0;
            border: 0;
            background: transparent;
            box-shadow: none;
            font-size: .9rem;
            line-height: 1;
            font-weight: 920;
        }

        .tool-lock-spacer {
            width: 1.28rem;
            height: 1.28rem;
        }

        .tool-meta {
            min-height: 68px;
            margin-top: .5rem;
            color: rgba(234, 247, 255, .68);
            font-size: .9rem;
            line-height: 1.62;
        }

        .tool-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: .55rem;
            margin-top: .8rem;
        }

        .tool-tag {
            display: inline-flex;
            align-items: center;
            min-height: 28px;
            padding: .25rem .58rem;
            border: 1px solid rgba(245, 184, 75, .34);
            border-radius: 999px;
            color: var(--amber);
            background: rgba(245, 184, 75, .06);
            font-size: .76rem;
            font-weight: 760;
        }

        .quote-strip {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-top: 1.4rem;
            padding: 1rem 1.1rem;
            border: 1px solid rgba(57, 223, 247, .2);
            border-left: 4px solid var(--magenta);
            border-radius: 8px;
            background: rgba(9, 18, 31, .62);
            color: rgba(234, 247, 255, .86);
            font-weight: 680;
        }

        .quote-strip span {
            flex: 0 0 auto;
            color: var(--muted);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .78rem;
        }

        @media (max-width: 980px) {
            .command-hero {
                grid-template-columns: 1fr;
                min-height: auto;
            }
            .hero-title {
                white-space: normal;
            }
            .hero-visual {
                justify-self: stretch;
                max-width: none;
                min-height: 240px;
            }
            .section-heading {
                align-items: flex-start;
                flex-direction: column;
            }
        }

        @media (max-width: 620px) {
            .command-hero {
                padding: 1rem;
            }
            .hero-title {
                font-size: 2.35rem;
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


def apply_home_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --colors-primary: #0066cc;
            --colors-primary-focus: #0071e3;
            --colors-primary-on-dark: #2997ff;
            --colors-ink: #1d1d1f;
            --colors-body-on-dark: #ffffff;
            --colors-body-muted: #cccccc;
            --colors-ink-muted-80: #333333;
            --colors-ink-muted-48: #7a7a7a;
            --colors-hairline: #e0e0e0;
            --colors-canvas: #ffffff;
            --colors-canvas-parchment: #f5f5f7;
            --colors-surface-tile-1: #272729;
            --rounded-sm: 8px;
            --rounded-lg: 18px;
            --rounded-pill: 9999px;
            --spacing-lg: 24px;
            --spacing-section: 64px;
            --shadow-product: 3px 5px 30px rgba(0, 0, 0, 0.22);
            --font-display: "SF Pro Display", "Inter", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
            --font-text: "SF Pro Text", "Inter", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
        }

        [data-testid="stSidebar"],
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        .stApp {
            color: var(--colors-ink);
            background: var(--colors-canvas) !important;
            font-family: var(--font-text);
        }
        .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stMain"], [data-testid="stMainBlockContainer"],
        .block-container, [data-testid="stVerticalBlock"],
        [data-testid="stMarkdownContainer"], [data-testid="stVerticalBlockBorderWrapper"] {
            overflow: visible !important;
        }
        .block-container {
            max-width: 100% !important;
            padding: 0 !important;
        }
        .apple-home {
            color: var(--colors-ink);
            background: var(--colors-canvas);
            font-family: var(--font-text);
            font-size: 17px;
            line-height: 1.44;
            letter-spacing: -0.374px;
        }
        .apple-home a { color: inherit; text-decoration: none; }

        .global-nav {
            position: sticky;
            top: 0;
            z-index: 40;
            height: 44px;
            background: rgba(251, 251, 253, 0.92);
            backdrop-filter: saturate(180%) blur(20px);
            overflow: visible;
        }
        .global-nav-inner {
            height: 44px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
            width: min(980px, calc(100% - 32px));
            margin: 0 auto;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
        }
        .brand-mark {
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: var(--colors-ink);
            color: var(--colors-canvas);
            display: grid;
            place-items: center;
            font-size: 10px;
            font-weight: 600;
        }
        .nav-links {
            flex: 1;
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            height: 44px;
            font-size: 12px;
        }
        .nav-cat {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 44px;
            padding: 0 12px;
        }
        .nav-cat.current { font-weight: 600; }
        .nav-flyout {
            display: none;
            position: absolute;
            left: 0;
            right: 0;
            top: 44px;
            background: var(--colors-canvas-parchment);
            padding: 40px 0 56px;
        }
        .apple-home:has(.nav-cat[data-section="行政"]:hover) .fly-行政,
        .apple-home:has(.fly-行政:hover) .fly-行政,
        .apple-home:has(.nav-cat[data-section="教学"]:hover) .fly-教学,
        .apple-home:has(.fly-教学:hover) .fly-教学,
        .apple-home:has(.nav-cat[data-section="个人"]:hover) .fly-个人,
        .apple-home:has(.fly-个人:hover) .fly-个人,
        .apple-home:has(.nav-cat[data-section="archived"]:hover) .fly-archived,
        .apple-home:has(.fly-archived:hover) .fly-archived {
            display: block;
        }
        .nav-flyout-inner {
            width: min(980px, calc(100% - 32px));
            margin: 0 auto;
        }
        .nav-flyout-kicker {
            font-size: 12px;
            color: var(--colors-ink-muted-48);
            margin-bottom: 14px;
        }
        .nav-flyout-list {
            display: grid;
            grid-template-columns: minmax(240px, 420px);
        }
        .nav-flyout-list a {
            display: block;
            font-family: var(--font-display);
            font-size: 24px;
            font-weight: 600;
            line-height: 1.25;
            padding: 6px 0;
        }
        .nav-flyout-list a:hover { color: var(--colors-primary); }
        .fly-code {
            display: block;
            font-family: var(--font-text);
            font-size: 12px;
            font-weight: 400;
            color: var(--colors-ink-muted-48);
            margin-bottom: 2px;
        }
        .icon-btn {
            width: 44px;
            height: 44px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: var(--colors-ink);
        }
        .store-lock,
        .text-lock {
            width: min(980px, calc(100% - 40px));
            margin: 0 auto;
        }
        .sub-nav {
            position: sticky;
            top: 44px;
            z-index: 30;
            height: 52px;
            background: rgba(245, 245, 247, 0.8);
            backdrop-filter: saturate(180%) blur(20px);
            border-bottom: 1px solid rgba(0, 0, 0, 0.08);
        }
        .sub-nav-inner {
            height: 52px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }
        .sub-title {
            font-family: var(--font-display);
            font-size: 21px;
            font-weight: 600;
        }
        .sub-actions {
            display: flex;
            align-items: center;
            gap: 18px;
            font-size: 14px;
        }
        .pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 44px;
            border-radius: var(--rounded-pill);
            padding: 11px 22px;
            font-size: 17px;
            border: 0;
        }
        .pill-primary {
            background: var(--colors-primary);
            color: var(--colors-canvas) !important;
        }
        .pill-secondary {
            background: transparent;
            color: var(--colors-primary) !important;
            border: 1px solid var(--colors-primary);
        }
        .pill-sm { padding: 8px 15px; font-size: 14px; min-height: 36px; }
        .product-tile {
            padding: var(--spacing-section) 20px;
            text-align: center;
        }
        .product-tile-light { background: var(--colors-canvas); }
        .product-tile-parchment { background: var(--colors-canvas-parchment); }
        .product-tile-dark {
            background: var(--colors-surface-tile-1);
            color: var(--colors-body-on-dark);
        }
        .eyebrow {
            font-size: 12px;
            color: var(--colors-ink-muted-48);
        }
        .product-tile-dark .eyebrow { color: var(--colors-body-muted); }
        .product-tile h1, .product-tile h2 {
            margin: 12px 0 10px;
            font-family: var(--font-display);
            font-weight: 600;
        }
        .product-tile h1 { font-size: 56px; line-height: 1.07; }
        .product-tile h2 { font-size: 40px; line-height: 1.1; }
        .lead {
            margin: 0 auto 24px;
            max-width: 720px;
            font-size: 28px;
            line-height: 1.14;
        }
        .lead-playful {
            font-family: "Fredoka", "Comic Neue", "Segoe UI Rounded", sans-serif;
            font-size: 32px;
            font-weight: 500;
            line-height: 1.3;
            letter-spacing: 0.4px;
            color: var(--colors-ink-muted-80);
        }
        .product-tile-dark .lead { color: var(--colors-body-muted); }
        .ctas {
            display: flex;
            justify-content: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        .split { display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
        .split .product-tile { min-height: 360px; }
        .split .lead { font-size: 21px; }
        .text-link { color: var(--colors-primary) !important; }
        .store {
            background: var(--colors-canvas-parchment);
            padding: var(--spacing-section) 20px 48px;
        }
        .store-head { margin-bottom: 32px; }
        .store-head h2 {
            margin: 0;
            font-family: var(--font-display);
            font-size: 34px;
            font-weight: 600;
        }
        .store-head p {
            margin: 6px 0 0;
            font-size: 14px;
            color: var(--colors-ink-muted-48);
        }
        .card-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }
        .store-card {
            background: var(--colors-canvas);
            border: 1px solid var(--colors-hairline);
            border-radius: var(--rounded-lg);
            padding: var(--spacing-lg);
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .store-card.is-blocked { opacity: 0.62; }
        .card-media {
            height: 72px;
            border-radius: var(--rounded-sm);
            background: var(--colors-canvas-parchment);
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            padding: 12px;
        }
        .card-media span {
            font-size: 12px;
            color: var(--colors-ink-muted-48);
        }
        .card-slab {
            width: 54px;
            height: 36px;
            border-radius: var(--rounded-sm);
            background: var(--colors-canvas);
            box-shadow: var(--shadow-product);
        }
        .store-card h3, .store-card .tool-title {
            margin: 0;
            color: var(--colors-ink) !important;
            font-size: 17px;
            font-weight: 600;
            text-decoration: none !important;
        }
        .status { font-size: 12px; color: var(--colors-ink-muted-48); }
        .store-card p {
            margin: 0;
            font-size: 14px;
            color: var(--colors-ink-muted-80);
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .store-foot {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-top: auto;
            padding-top: 8px;
        }
        .fine { font-size: 12px; color: var(--colors-ink-muted-48); }
        .tool-lock, .tool-blocked, .tool-lock-spacer {
            display: inline-flex;
            width: 1.1rem;
            height: 1.1rem;
            align-items: center;
            justify-content: center;
            font-size: .86rem;
        }
        .quote-strip.quote {
            display: block;
            margin-top: 0;
            padding: var(--spacing-section) 20px;
            border: 0;
            border-radius: 0;
            background: var(--colors-surface-tile-1);
            color: var(--colors-body-on-dark);
            text-align: center;
            font-weight: 600;
        }
        .quote h2 {
            margin: 0 0 16px;
            font-family: var(--font-display);
            font-size: 40px;
        }
        .quote .fine {
            color: var(--colors-body-muted);
            display: block;
        }
        .empty {
            grid-column: 1 / -1;
            text-align: center;
            padding: 48px 16px;
            color: var(--colors-ink-muted-48);
        }
        @media (max-width: 1068px) {
            .product-tile h1 { font-size: 40px; }
        }
        @media (max-width: 833px) {
            .nav-flyout { display: none !important; }
            .split, .card-grid { grid-template-columns: 1fr 1fr; }
            .product-tile, .quote { padding-top: 48px; padding-bottom: 48px; }
        }
        @media (max-width: 640px) {
            .card-grid, .split { grid-template-columns: 1fr; }
            .product-tile h1 { font-size: 34px; }
            .lead, .lead-playful { font-size: 21px; }
            .product-tile h2, .quote h2 { font-size: 34px; }
            .sub-actions a:not(.pill) { display: none; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
