import streamlit as st


def apply_global_theme() -> None:
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
            min-height: 360px;
            overflow: hidden;
            padding: 1.15rem 1.25rem;
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
            justify-content: center;
            min-width: 0;
            padding: .85rem .8rem .85rem .55rem;
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
            margin-top: .72rem;
            color: #f7fbff;
            font-size: clamp(2.45rem, 4.8vw, 4.55rem);
            line-height: 1;
            font-weight: 920;
            white-space: nowrap;
            text-shadow: 0 0 34px rgba(57, 223, 247, .22);
        }

        .hero-copy {
            max-width: 660px;
            margin-top: .85rem;
            color: rgba(234, 247, 255, .76);
            font-size: .98rem;
            line-height: 1.72;
        }

        .hero-visual {
            position: relative;
            z-index: 1;
            align-self: center;
            min-width: 0;
            min-height: 236px;
            max-width: 520px;
            width: 100%;
            justify-self: end;
            padding: .85rem;
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
            inset: 2.1rem 1.55rem 1.55rem;
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
            width: 104px;
            height: 104px;
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
            width: 34px;
            height: 34px;
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
            margin-top: .72rem;
            color: var(--ink) !important;
            font-size: 1.16rem;
            font-weight: 860;
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

        .tool-pulse {
            color: var(--green);
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: .72rem;
            font-weight: 820;
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
