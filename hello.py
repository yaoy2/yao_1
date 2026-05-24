import math

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
        "title": "Recorder_笔记",
        "desc": "每天扫描钉钉导出的 Word 转写，保留原文并生成可归档、可复盘的 AI 整理稿。",
        "tag": "纪要整理",
        "created": "2026_05_24",
        "page": "pages/00_11、🎙️_Recorder_笔记.py",
        "code": "M11",
        "accent": "green",
    },
    {
        "title": "灵感便签盒",
        "desc": "快速记录灵感、摘录、待办和写作素材，支持标签、色卡和 Markdown 硬备份。",
        "tag": "知识管理",
        "created": "2026_05_24",
        "page": "pages/01_10、🧾_灵感便签盒.py",
        "code": "M10",
        "accent": "cyan",
    },
    {
        "title": "配色方案预览",
        "desc": "查看沉淀的配色组合，为 PPT、通知和页面视觉提供参考。",
        "tag": "视觉资产",
        "created": "2026_05_17",
        "page": "pages/02_9、🎨_配色方案预览.py",
        "code": "M09",
        "accent": "amber",
    },
    {
        "title": "预算速记台账",
        "desc": "记录支出、查看分类预算和导出流水，服务学院预算过程管理。",
        "tag": "预算管理",
        "created": "2026_05_16",
        "page": "pages/03_8、💰_预算速记台账.py",
        "code": "M08",
        "accent": "magenta",
    },
    {
        "title": "微信归档",
        "desc": "把微信文章和网页内容沉淀为可复用资料，减少信息流失。",
        "tag": "知识归档",
        "created": "2026_05_04",
        "page": "pages/04_7、📥_wechat归档.py",
        "code": "M07",
        "accent": "green",
    },
    {
        "title": "课表查询",
        "desc": "查询课表缓存数据，支持日常协调、教室和教学安排确认。",
        "tag": "教学协调",
        "created": "2026_04_30",
        "page": "pages/05_6、📚_课表查询.py",
        "code": "M06",
        "accent": "cyan",
    },
    {
        "title": "万能合并机",
        "desc": "把分散文件合成便于归档、转交和复核的结果，降低整理成本。",
        "tag": "文件整理",
        "created": "2025_12_18",
        "page": "pages/06_5、🧰_万能合并机.py",
        "code": "M05",
        "accent": "amber",
    },
    {
        "title": "Word 收割机",
        "desc": "从 Word 材料中提取、整理和汇总内容，适合行政材料批处理。",
        "tag": "文档处理",
        "created": "2025_12_17",
        "page": "pages/07_4、🌾_word收割机.py",
        "code": "M04",
        "accent": "magenta",
    },
    {
        "title": "名单核对",
        "desc": "处理名单、报名表、汇总表之间的匹配、遗漏和交叉确认。",
        "tag": "名单治理",
        "created": "2025_12_12",
        "page": "pages/08_3、✅_名单核对.py",
        "code": "M03",
        "accent": "green",
    },
    {
        "title": "文件比对",
        "desc": "快速发现文件、名单与提交材料之间的差异，减少人工逐行核对。",
        "tag": "核对校验",
        "created": "2025_12_12",
        "page": "pages/09_2、🔍_文件比对.py",
        "code": "M02",
        "accent": "cyan",
    },
    {
        "title": "报告评分",
        "desc": "辅助检查材料结构、表达和完成度，适合初稿打磨与批量评阅前的预处理。",
        "tag": "材料质量",
        "created": "2025_12_12",
        "page": "pages/10_1、📝_报告评分.py",
        "code": "M01",
        "accent": "amber",
    },
]


def build_hero_visual_html() -> str:
    return (
        '<div class="hero-visual" aria-label="首页视觉">'
        '<div class="principle-chip">干他妈的</div>'
        '<div class="visual-orbit">'
        '<span class="orbit-node node-a"></span>'
        '<span class="orbit-node node-b"></span>'
        '<span class="orbit-node node-c"></span>'
        '<span class="orbit-node node-d"></span>'
        '<div class="orbit-core">YAO<br/>OPS</div>'
        "</div>"
        "</div>"
    )


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
        <h2>十一个工具，分页进入</h2>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

total_pages = math.ceil(len(TOOLS) / 9)
if total_pages > 1:
    page_options = [f"第 {index + 1} 页" for index in range(total_pages)]
    selected_page = st.radio("工具分页", page_options, horizontal=True, label_visibility="collapsed")
    page_index = page_options.index(selected_page)
else:
    page_index = 0

page_tools = TOOLS[page_index * 9 : page_index * 9 + 9]
for row_start in range(0, 9, 3):
    cols = st.columns(3)
    for col, tool in zip(cols, page_tools[row_start : row_start + 3]):
        with col:
            st.markdown(
                f"""
                <a class="tool-card {tool["accent"]}" href="{tool["page"]}">
                  <div class="tool-head">
                    <div class="tool-code">{tool["code"]}</div>
                    <div class="tool-date">{tool["created"]}</div>
                  </div>
                  <div class="tool-title">{tool["title"]}</div>
                  <div class="tool-meta">{tool["desc"]}</div>
                  <div class="tool-footer">
                    <span class="tool-tag">{tool["tag"]}</span>
                    <span class="tool-pulse">READY</span>
                  </div>
                </a>
                """,
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
