import re
from html import escape
from pathlib import Path
from urllib.parse import quote

import streamlit as st

from utils.home_theme import apply_home_theme

st.set_page_config(
    page_title="YaoYao's Space",
    page_icon="⚡",
    layout="wide",
)

apply_home_theme()

TOOLS = [
    {
        "title": "Awesome Design MD",
        "desc": "只读浏览本地拉取的 74 组品牌 DESIGN.md 设计规范，为页面设计和 AI 生成界面提供视觉参考。",
        "tag": "视觉资产",
        "created": "2026_08_31",
        "page": "pages/20_21_awesome_design_md.py",
        "code": "M21",
        "accent": "cyan",
        "section": "个人",
    },
    {
        "title": "Ding2026 文件中转发放系统",
        "desc": "展示学院行政文件如何被识别、手动分发、进入中转裁决，并按五条时间轴安全归档。",
        "tag": "文件治理",
        "created": "2026_08_31",
        "page": "pages/19_20_ding2026.py",
        "code": "M20",
        "accent": "green",
        "section": "行政",
    },
    {
        "title": "概念寓言馆",
        "desc": "Codex 把概念写成寓言，本馆集中保存，便于检索与重读。",
        "tag": "概念学习",
        "created": "2026_08_26",
        "page": "pages/18_19_concept_fables.py",
        "code": "M19",
        "accent": "magenta",
        "section": "个人",
    },
    {
        "title": "评分工作台使用说明",
        "desc": "第18个项目：集中说明M17操作流程、分数口径、数据位置、跨电脑状态和常见问题。",
        "tag": "使用说明",
        "created": "2026_07_12",
        "page": "pages/17_18_grade_workbench_guide.py",
        "code": "M18",
        "accent": "amber",
        "section": "教学",
    },
    {
        "title": "教学评分工作台",
        "desc": "第17个项目：持久化管理花名册、小组路演与报告原始分、个人系数和各层调整，校验后导出审核工作簿。",
        "tag": "成绩审核",
        "created": "2026_07_12",
        "page": "pages/16_17_grade_workbench.py",
        "code": "M17",
        "accent": "green",
        "section": "教学",
    },
    {
        "title": "旧版报告评分与成绩联动",
        "desc": "已由M17教学评分工作台替代，仅保留旧流程作历史对照，不再用于正式成绩处理。",
        "tag": "已替代",
        "created": "2026_07_05",
        "page": "pages/15_16_report_grader.py",
        "code": "M16",
        "accent": "cyan",
        "blocked": True,
        "section": "archived",
    },
    {
        "title": "邮件通知编辑器",
        "desc": "粘贴通知全文后自动识别标题、编号、正文、落款和日期，并嵌入现有邮件排版工具一键预览与导出。",
        "tag": "通知排版",
        "created": "2026_07_01",
        "page": "pages/15_0_email_notice.py",
        "code": "M15",
        "accent": "amber",
        "section": "行政",
    },
    {
        "title": "待办清单",
        "desc": "记录日常待办、自动识别截止日期和时间，完成后软归档，并通过本地备份和 GitHub 同步保护数据。",
        "tag": "任务管理",
        "created": "2026_06_29",
        "page": "pages/14_todos.py",
        "code": "M14",
        "accent": "green",
        "locked": True,
        "section": "行政",
    },
    {
        "title": "LLM 余额管理",
        "desc": "统一管理各家 LLM API / Token Plan 余额，自动查询 DeepSeek、Kimi，手动录入 MiMo 和 ChatGPT。",
        "tag": "AI 工具管理",
        "created": "2026_06_22",
        "page": "pages/00_13_llm_budget.py",
        "code": "M13",
        "accent": "cyan",
        "blocked": True,
        "section": "archived",
    },
    {
        "title": "Recorder_笔记",
        "desc": "每天扫描钉钉导出的 Word 转写，保留原文并生成可归档、可复盘的 AI 整理稿。",
        "tag": "纪要整理",
        "created": "2026_05_24",
        "page": "pages/02_11_recorder.py",
        "code": "M11",
        "accent": "green",
        "locked": True,
        "section": "行政",
    },
    {
        "title": "灵感便签盒",
        "desc": "快速记录灵感、摘录、待办和写作素材，支持标签、色卡和 Markdown 硬备份。",
        "tag": "知识管理",
        "created": "2026_05_24",
        "page": "pages/03_10_memos.py",
        "code": "M10",
        "accent": "cyan",
        "section": "个人",
    },
    {
        "title": "配色方案预览",
        "desc": "查看沉淀的配色组合，为 PPT、通知和页面视觉提供参考。",
        "tag": "视觉资产",
        "created": "2026_05_17",
        "page": "pages/04_9_palette.py",
        "code": "M09",
        "accent": "amber",
        "section": "个人",
    },
    {
        "title": "预算速记台账",
        "desc": "记录支出、查看分类预算和导出流水，服务学院预算过程管理。",
        "tag": "预算管理",
        "created": "2026_05_16",
        "page": "pages/05_8_budget.py",
        "code": "M08",
        "accent": "magenta",
        "locked": True,
        "section": "行政",
    },
    {
        "title": "微信归档",
        "desc": "把微信文章和网页内容沉淀为可复用资料，减少信息流失。",
        "tag": "知识归档",
        "created": "2026_05_04",
        "page": "pages/06_7_wechat.py",
        "code": "M07",
        "accent": "green",
        "section": "个人",
    },
    {
        "title": "课表查询",
        "desc": "查询课表缓存数据，支持日常协调、教室和教学安排确认。",
        "tag": "教学协调",
        "created": "2026_04_30",
        "page": "pages/07_6_schedule.py",
        "code": "M06",
        "accent": "cyan",
        "section": "行政",
    },
    {
        "title": "万能合并机",
        "desc": "把分散文件合成便于归档、转交和复核的结果，降低整理成本。",
        "tag": "文件整理",
        "created": "2025_12_18",
        "page": "pages/08_5_merger❌.py",
        "code": "M05",
        "accent": "amber",
        "blocked": True,
        "section": "archived",
    },
    {
        "title": "Word 收割机",
        "desc": "从 Word 材料中提取、整理和汇总内容，适合行政材料批处理。",
        "tag": "文档处理",
        "created": "2025_12_17",
        "page": "pages/09_4_word❌.py",
        "code": "M04",
        "accent": "magenta",
        "blocked": True,
        "section": "archived",
    },
    {
        "title": "名单核对",
        "desc": "处理名单、报名表、汇总表之间的匹配、遗漏和交叉确认。",
        "tag": "名单治理",
        "created": "2025_12_12",
        "page": "pages/10_3_checker❌.py",
        "code": "M03",
        "accent": "green",
        "blocked": True,
        "section": "archived",
    },
    {
        "title": "文件比对",
        "desc": "快速发现文件、名单与提交材料之间的差异，减少人工逐行核对。",
        "tag": "核对校验",
        "created": "2025_12_12",
        "page": "pages/11_2_compare❌.py",
        "code": "M02",
        "accent": "cyan",
        "blocked": True,
        "section": "archived",
    },
    {
        "title": "报告评分",
        "desc": "已弃用：旧版提示词评分流程过期，后续改用 DeepSeek 网页版完成评分。",
        "tag": "已弃用",
        "created": "2025_12_12",
        "page": "pages/12_1_scoring❌.py",
        "code": "M01",
        "accent": "amber",
        "blocked": True,
        "section": "archived",
    },
]

HOME_SECTIONS = {
    "行政": "学院事务在这里归位。",
    "教学": "评分相关的工作台。",
    "个人": "给自己留的工具、笔记和视觉参考。",
    "archived": "已经停用的项目，只作对照，不再启用。",
}

SECTION_DISPLAY = {
    "行政": "行政狗",
    "教学": "教学",
    "个人": "个人",
    "archived": "archived",
}

FEATURED_LEADS = {
    "M15": "把通知全文收成可寄出的秩序：标题、编号、落款，一次成形。",
    "M14": "截止日期自动识别，做完就归档，学院的一天先落在纸面上。",
    "M06": "教室、时间和安排，行政核对时立刻能看见。",
    "M17": "花名册、路演、报告分和个人系数，校验后导出审核工作簿。",
    "M18": "流程、口径、数据位置和跨电脑状态，先读这一页再动手。",
    "M19": "把难懂的概念写成可重读的寓言，供自己慢慢回来。",
    "M10": "灵感、摘录和写作素材，随手放下，日后还能找回来。",
    "M07": "把微信文章和网页沉淀下来，减少个人资料流失。",
}


def sort_tool_key(tool):
    code = str(tool.get("code", "M0")).removeprefix("M")
    try:
        module_number = int(code)
    except ValueError:
        module_number = 0
    return module_number


def get_homepage_tools(tools):
    return sorted(
        tools,
        key=lambda tool: (not bool(tool.get("blocked")), sort_tool_key(tool)),
        reverse=True,
    )


def get_homepage_pages(tools, page_size=9):
    ordered_tools = get_homepage_tools(tools)
    pages = [
        ordered_tools[index : index + page_size]
        for index in range(0, len(ordered_tools), page_size)
    ]
    return pages or [[]]


def tools_for_section(tools, section):
    ordered_tools = get_homepage_tools(tools)
    if section == "archived":
        return [tool for tool in ordered_tools if tool.get("blocked")]
    return [
        tool
        for tool in ordered_tools
        if not tool.get("blocked") and tool.get("section") == section
    ]


def build_streamlit_page_href(page_path):
    page_name = Path(page_path).name
    match = re.match(r"([0-9]*)[_ -]*(.*)\.py$", page_name)
    if not match:
        return "#"
    url_path = re.sub(r"[_ ]+", "_", match.group(2)).strip() or match.group(1)
    return f"/{quote(url_path)}"


def build_section_href(section):
    return f"?section={quote(section)}"


def build_tool_title_html(tool):
    href = escape(build_streamlit_page_href(tool["page"]), quote=True)
    title = escape(tool["title"])
    return f'<a class="tool-title" href="{href}" target="_self">{title}</a>'


def build_tool_status_icon_html(tool):
    if tool.get("locked"):
        return '<span class="tool-lock" title="需要密码访问" aria-label="需要密码访问">🔒</span>'
    if tool.get("blocked"):
        return '<span class="tool-blocked" title="暂不开放" aria-label="暂不开放">❌</span>'
    return '<span class="tool-lock-spacer" aria-hidden="true"></span>'


def _flyout_html(section, tools):
    items = tools_for_section(tools, section)
    if not items:
        return '<p class="nav-flyout-empty">这一栏还没有模块</p>'
    rows = []
    for tool in items:
        href = escape(build_streamlit_page_href(tool["page"]), quote=True)
        mark = " ❌" if tool.get("blocked") else ""
        rows.append(
            f'<a href="{href}" target="_self">'
            f'<span class="fly-code">{escape(tool["code"])}</span>'
            f'{escape(tool["title"])}{mark}'
            "</a>"
        )
    return "".join(rows)


def build_nav_html(current_section, tools):
    cats = []
    flyouts = []
    for section, _copy in HOME_SECTIONS.items():
        current = " current" if section == current_section else ""
        label = "archived" if section == "archived" else section
        cats.append(
            f'<a class="nav-cat{current}" data-section="{escape(section)}" '
            f'href="{escape(build_section_href(section), quote=True)}">{escape(label)}</a>'
        )
        flyouts.append(
            f'<div class="nav-flyout fly-{escape(section)}">'
            f'<div class="nav-flyout-inner">'
            f'<div class="nav-flyout-kicker">探索 {escape(label)}</div>'
            f'<div class="nav-flyout-list">{_flyout_html(section, tools)}</div>'
            "</div></div>"
        )
    return (
        '<header class="global-nav">'
        '<div class="global-nav-inner">'
        '<a class="brand" href="/" target="_self"><span class="brand-mark">Y</span>YaoYao\'s Space</a>'
        f'<nav class="nav-links">{"".join(cats)}</nav>'
        '<div class="nav-tools">'
        '<a class="icon-btn" href="#modules" target="_self" aria-label="浏览模块">⌕</a>'
        "</div></div>"
        f'{"".join(flyouts)}'
        "</header>"
    )


FEATURED_CODES = {
    "行政": ("M15", "M14", "M06"),
    "教学": ("M17", "M18"),
    "个人": ("M19", "M10", "M07"),
}


def _feature_card(tool):
    href = escape(build_streamlit_page_href(tool["page"]), quote=True)
    lead = FEATURED_LEADS.get(tool["code"], tool["desc"])
    label = "查看说明" if tool.get("blocked") else "打开"
    return (
        f'<a class="feature-card" href="{href}" target="_self">'
        f'<span class="eyebrow">{escape(tool["code"])} · {escape(tool["tag"])}</span>'
        f"<strong>{escape(tool['title'])}</strong>"
        f"<p>{escape(lead)}</p>"
        f'<span class="feature-go">{label}</span>'
        "</a>"
    )


def build_feature_html(current_section, tools):
    codes = FEATURED_CODES.get(current_section) or ()
    if not codes:
        return ""
    by_code = {tool["code"]: tool for tool in tools}
    cards = "".join(_feature_card(by_code[code]) for code in codes if code in by_code)
    return f'<section class="feature-row" id="feature">{cards}</section>'


def build_store_html(current_section, tools):
    section_tools = tools_for_section(tools, current_section)
    title = SECTION_DISPLAY.get(current_section, current_section)
    copy = HOME_SECTIONS.get(current_section, "")
    cards = []
    for tool in section_tools:
        href = escape(build_streamlit_page_href(tool["page"]), quote=True)
        blocked = " is-blocked" if tool.get("blocked") else ""
        mark = " ❌" if tool.get("blocked") else ""
        status = ""
        if tool.get("locked"):
            status = ' <span class="status">需要密码</span>'
        elif tool.get("blocked"):
            status = ' <span class="status">暂不开放</span>'
        cards.append(
            f'<article class="store-card{blocked}" id="module-{escape(tool["code"])}">'
            '<div class="store-card-main">'
            f'<span class="store-code">{escape(tool["code"])}</span>'
            f'<div class="store-copy">'
            f'<h3>{build_tool_title_html(tool)}{mark}{status}{build_tool_status_icon_html(tool)}</h3>'
            f'<p>{escape(tool["desc"])}</p>'
            "</div>"
            f'<a class="text-link" href="{href}" target="_self">'
            f'{"查看说明" if tool.get("blocked") else "打开"}</a>'
            "</div></article>"
        )
    body = "".join(cards) or '<div class="empty">没有匹配的模块</div>'
    return (
        f'<section class="store" id="modules">'
        f'<div class="store-lock"><div class="store-head"><div>'
        f"<h2>{escape(title)}</h2>"
        f'<p>{escape(copy)} · {len(section_tools)} 个模块</p>'
        f"</div></div>"
        f'<div class="card-grid">{body}</div>'
        "</div></section>"
    )


def resolve_home_section(raw_value):
    if isinstance(raw_value, list):
        raw_value = raw_value[0] if raw_value else "行政"
    section = str(raw_value or "行政")
    if section not in HOME_SECTIONS:
        return "行政"
    return section


current_section = resolve_home_section(st.query_params.get("section", "行政"))
display_title = SECTION_DISPLAY.get(current_section, current_section)

st.markdown(
    f"""
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Fredoka:wght@400;500;600&family=Inter:wght@300;400;600&display=swap" rel="stylesheet" />
<div class="apple-home">
  {build_nav_html(current_section, TOOLS)}
  <div class="sub-nav">
    <div class="sub-nav-inner store-lock">
      <div class="sub-title">{escape(display_title)}</div>
      <div class="sub-actions">
        <a href="#modules" target="_self">浏览模块</a>
        <a href="#feature" target="_self">精选</a>
        <a class="pill pill-primary pill-sm" href="#modules" target="_self">进入工作台</a>
      </div>
    </div>
  </div>
  <main>
    <section class="product-tile product-tile-light">
      <div class="text-lock">
        <div class="eyebrow">Yao · Campus · AI Operations</div>
        <h1>学院行政智能中枢</h1>
        <p class="lead lead-playful">Don't worry. Be happy.</p>
      </div>
    </section>
    <div id="feature">{build_feature_html(current_section, TOOLS)}</div>
    {build_store_html(current_section, TOOLS)}
    <section class="quote quote-strip">
      <h2>前方没有胜利，挺住意味一切</h2>
      <span class="fine">YaoYao Command Center</span>
    </section>
  </main>
</div>
    """,
    unsafe_allow_html=True,
)
