import re
from html import escape
from pathlib import Path
from urllib.parse import quote

import streamlit as st

from utils.ui_theme import apply_global_theme


st.set_page_config(
    page_title="YaoYao's Space",
    page_icon="⚡",
    layout="wide",
)

apply_global_theme()

TOOLS = [
    {
        "title": "概念寓言馆",
        "desc": "Codex 把概念写成寓言，本馆集中保存，便于检索与重读。",
        "tag": "概念学习",
        "created": "2026_08_26",
        "page": "pages/18_19_concept_fables.py",
        "code": "M19",
        "accent": "magenta",
    },
    {
        "title": "评分工作台使用说明",
        "desc": "第18个项目：集中说明M17操作流程、分数口径、数据位置、跨电脑状态和常见问题。",
        "tag": "使用说明",
        "created": "2026_07_12",
        "page": "pages/17_18_grade_workbench_guide.py",
        "code": "M18",
        "accent": "amber",
    },
    {
        "title": "教学评分工作台",
        "desc": "第17个项目：持久化管理花名册、小组路演与报告原始分、个人系数和各层调整，校验后导出审核工作簿。",
        "tag": "成绩审核",
        "created": "2026_07_12",
        "page": "pages/16_17_grade_workbench.py",
        "code": "M17",
        "accent": "green",
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
    },
    {
        "title": "邮件通知编辑器",
        "desc": "粘贴通知全文后自动识别标题、编号、正文、落款和日期，并嵌入现有邮件排版工具一键预览与导出。",
        "tag": "通知排版",
        "created": "2026_07_01",
        "page": "pages/15_0_email_notice.py",
        "code": "M15",
        "accent": "amber",
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
    },
    {
        "title": "LLM 余额管理",
        "desc": "统一管理各家 LLM API / Token Plan 余额，自动查询 DeepSeek、Kimi，手动录入 MiMo 和 ChatGPT。",
        "tag": "AI 工具管理",
        "created": "2026_06_22",
        "page": "pages/00_13_llm_budget.py",
        "code": "M13",
        "accent": "cyan",
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
    },
    {
        "title": "灵感便签盒",
        "desc": "快速记录灵感、摘录、待办和写作素材，支持标签、色卡和 Markdown 硬备份。",
        "tag": "知识管理",
        "created": "2026_05_24",
        "page": "pages/03_10_memos.py",
        "code": "M10",
        "accent": "cyan",
    },
    {
        "title": "配色方案预览",
        "desc": "查看沉淀的配色组合，为 PPT、通知和页面视觉提供参考。",
        "tag": "视觉资产",
        "created": "2026_05_17",
        "page": "pages/04_9_palette.py",
        "code": "M09",
        "accent": "amber",
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
    },
    {
        "title": "微信归档",
        "desc": "把微信文章和网页内容沉淀为可复用资料，减少信息流失。",
        "tag": "知识归档",
        "created": "2026_05_04",
        "page": "pages/06_7_wechat.py",
        "code": "M07",
        "accent": "green",
    },
    {
        "title": "课表查询",
        "desc": "查询课表缓存数据，支持日常协调、教室和教学安排确认。",
        "tag": "教学协调",
        "created": "2026_04_30",
        "page": "pages/07_6_schedule.py",
        "code": "M06",
        "accent": "cyan",
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
    },
]


def sort_tool_key(tool):
    code = str(tool.get("code", "M0")).removeprefix("M")
    try:
        module_number = int(code)
    except ValueError:
        module_number = 0
    return module_number


def get_homepage_tools(tools):
    return sorted(tools, key=sort_tool_key, reverse=True)


def get_homepage_pages(tools, page_size=9):
    ordered_tools = get_homepage_tools(tools)
    pages = [
        ordered_tools[index : index + page_size]
        for index in range(0, len(ordered_tools), page_size)
    ]
    return pages or [[]]


def build_hero_visual_html() -> str:
    return (
        '<div class="hero-visual" aria-label="首页视觉">'
        '<div class="visual-orbit">'
        '<span class="orbit-node node-a"></span>'
        '<span class="orbit-node node-b"></span>'
        '<span class="orbit-node node-c"></span>'
        '<span class="orbit-node node-d"></span>'
        '<div class="orbit-core">YAO<br/>OPS</div>'
        "</div>"
        "</div>"
    )


def coerce_page_number(raw_value, total_pages):
    if isinstance(raw_value, list):
        raw_value = raw_value[0] if raw_value else "1"
    try:
        page_number = int(raw_value)
    except (TypeError, ValueError):
        page_number = 1
    return min(max(page_number, 1), total_pages)


def build_page_href(page_number):
    return f"?module_page={page_number}"


def build_streamlit_page_href(page_path):
    page_name = Path(page_path).name
    match = re.match(r"([0-9]*)[_ -]*(.*)\.py$", page_name)
    if not match:
        return "#"
    url_path = re.sub(r"[_ ]+", "_", match.group(2)).strip() or match.group(1)
    return f"/{quote(url_path)}"


def build_pagination_html(current_page, total_pages):
    if total_pages <= 1:
        return ""

    def page_item(page_number):
        if page_number == current_page:
            return f'<span class="pagination-item active">{page_number}</span>'
        return f'<a class="pagination-item" href="{build_page_href(page_number)}">{page_number}</a>'

    prev_html = (
        '<span class="pagination-item disabled">&lt;</span>'
        if current_page <= 1
        else f'<a class="pagination-item nav" href="{build_page_href(current_page - 1)}">&lt;</a>'
    )
    next_html = (
        '<span class="pagination-item disabled">&gt;</span>'
        if current_page >= total_pages
        else f'<a class="pagination-item nav" href="{build_page_href(current_page + 1)}">&gt;</a>'
    )
    prev_text = (
        '<span class="pagination-item text disabled">上一页</span>'
        if current_page <= 1
        else f'<a class="pagination-item text" href="{build_page_href(current_page - 1)}">上一页</a>'
    )
    next_text = (
        '<span class="pagination-item text disabled">下一页</span>'
        if current_page >= total_pages
        else f'<a class="pagination-item text" href="{build_page_href(current_page + 1)}">下一页</a>'
    )
    pages_html = "".join(page_item(index) for index in range(1, total_pages + 1))
    counter = escape(f"{current_page}/{total_pages}")
    return (
        '<nav class="pagination-bar" aria-label="工具分页">'
        f"{prev_html}{prev_text}{pages_html}"
        f'<span class="pagination-counter">{counter}</span>'
        f"{next_text}{next_html}"
        "</nav>"
    )


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


st.markdown(
    f"""
<section class="command-hero">
  <div class="hero-grid"></div>
  <div class="hero-copy-block">
    <div class="hero-kicker">YAO · CAMPUS · AI OPERATIONS</div>
    <div class="hero-title">学院行政智能中枢</div>
    <div class="hero-copy">
      面向学院日常事务的高效率工具矩阵：材料处理、数据核对、课表查询、预算台账、微信归档、灵感便签与视觉资产统一接入。
      把重复劳动压缩成一次点击，把复杂流程沉淀为稳定入口。
    </div>
  </div>
  {build_hero_visual_html()}
</section>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="section-heading">
      <div>
        <div class="section-label">MISSION MODULES</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
    .pagination-bar {
        display: inline-flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0;
        margin: .1rem 0 .75rem auto;
        border: 1px solid rgba(71, 205, 190, .32);
        border-radius: 8px;
        background: rgba(8, 22, 36, .76);
        box-shadow: 0 18px 36px rgba(3, 10, 18, .28), inset 0 1px 0 rgba(255,255,255,.07);
        overflow: hidden;
        backdrop-filter: blur(10px);
    }
    .pagination-dock {
        display: flex;
        justify-content: flex-end;
        margin-top: .25rem;
        margin-bottom: .15rem;
    }
    .pagination-item,
    .pagination-counter {
        min-width: 2.35rem;
        height: 2.15rem;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0 .72rem;
        border-right: 1px solid rgba(119, 176, 212, .18);
        color: #D6E4F0;
        font-size: .92rem;
        font-weight: 750;
        text-decoration: none !important;
        letter-spacing: 0;
    }
    .pagination-item:hover {
        color: #ffffff;
        background: rgba(74, 144, 217, .28);
    }
    .pagination-item.active {
        color: #ffffff;
        background: linear-gradient(180deg, #2D6A4F, #22533E);
        box-shadow: inset 0 -3px 0 rgba(71, 205, 190, .58);
    }
    .pagination-item.disabled {
        color: rgba(214, 228, 240, .36);
        background: rgba(255,255,255,.035);
        pointer-events: none;
    }
    .pagination-item.text {
        min-width: 4.6rem;
        color: #D6E4F0;
        font-weight: 700;
    }
    .pagination-counter {
        min-width: 5.4rem;
        color: #F8FAFC;
        background: rgba(27, 58, 92, .45);
        font-weight: 850;
    }
    .pagination-bar > :last-child {
        border-right: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

homepage_pages = get_homepage_pages(TOOLS)
total_pages = len(homepage_pages)
if total_pages > 1:
    current_page = coerce_page_number(st.query_params.get("module_page", "1"), total_pages)
    page_index = current_page - 1
else:
    current_page = 1
    page_index = 0

page_tools = homepage_pages[page_index]
for row_start in range(0, 9, 3):
    cols = st.columns(3)
    for col, tool in zip(cols, page_tools[row_start : row_start + 3]):
        with col:
            st.markdown(
                f"""
                <div class="tool-card-shell">
                  <div class="tool-card {tool["accent"]}">
                    <div class="tool-head">
                      <div class="tool-code">{tool["code"]}</div>
                      <div class="tool-date">{tool["created"]}</div>
                    </div>
                    {build_tool_title_html(tool)}
                    <div class="tool-meta">{tool["desc"]}</div>
                    <div class="tool-footer">
                      <span class="tool-tag">{tool["tag"]}</span>
                      {build_tool_status_icon_html(tool)}
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

if total_pages > 1:
    st.markdown(
        f'<div class="pagination-dock">{build_pagination_html(current_page, total_pages)}</div>',
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <section class="quote-strip">
      <div>前方没有胜利，挺住意味一切</div>
      <span>YaoYao Command Center</span>
    </section>
    """,
    unsafe_allow_html=True,
)
