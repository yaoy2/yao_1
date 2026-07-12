"""M18：教学评分工作台操作说明。"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.ui_theme import render_home_link


st.set_page_config(page_title="评分工作台使用说明", page_icon="📖", layout="wide")
render_home_link()

st.markdown(
    """
    <style>
    .guide-hero {
        padding: 1.15rem 1.25rem;
        border: 1px solid rgba(22, 101, 52, .18);
        border-radius: 14px;
        background: linear-gradient(135deg, rgba(236, 253, 245, .92), rgba(239, 246, 255, .92));
        margin-bottom: 1rem;
    }
    .guide-hero h1 { margin: 0 0 .35rem; color: #17324d; font-size: 2rem; }
    .guide-hero p { margin: 0; color: #496477; }
    .status-line {
        display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .75rem;
    }
    .status-chip {
        display: inline-flex; align-items: center; padding: .25rem .58rem;
        border-radius: 999px; font-size: .8rem; font-weight: 750;
        border: 1px solid rgba(15, 23, 42, .1); background: white; color: #334155;
    }
    .status-chip.ok { color: #166534; background: #f0fdf4; }
    .status-chip.wait { color: #9a3412; background: #fff7ed; }
    .module-card {
        min-height: 118px; padding: .85rem .95rem; border-radius: 12px;
        border: 1px solid rgba(71, 85, 105, .18); background: rgba(255,255,255,.84);
    }
    .module-code { color: #0891b2; font-family: Consolas, monospace; font-weight: 850; }
    .module-card h3 { margin: .25rem 0 .25rem; color: #1e293b; font-size: 1.02rem; }
    .module-card p { margin: 0; color: #64748b; font-size: .86rem; line-height: 1.5; }
    .flow-box {
        min-height: 128px; padding: .75rem .8rem; border-radius: 11px;
        border: 1px solid rgba(14, 116, 144, .16); background: rgba(240, 249, 255, .78);
    }
    .flow-number { color: #0e7490; font-size: 1.25rem; font-weight: 900; }
    .flow-box strong { display: block; margin: .1rem 0 .3rem; color: #1e293b; }
    .flow-box span { color: #64748b; font-size: .84rem; line-height: 1.45; }
    .warning-box {
        padding: .75rem .9rem; border-left: 4px solid #f59e0b;
        border-radius: 8px; background: #fffbeb; color: #78350f; margin: .45rem 0;
    }
    </style>
    <div class="guide-hero">
      <h1>评分工作台使用说明</h1>
      <p>先看本页确认入口和数据状态，再进入M17完成花名册、评分、调整、审核与导出。</p>
      <div class="status-line">
        <span class="status-chip ok">✓ M17本地评分功能可用</span>
        <span class="status-chip ok">✓ 原始分与调整分分离</span>
        <span class="status-chip wait">! 跨电脑评分数据同步尚未启用</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("先分清三个入口")
m18, m17, m16 = st.columns(3)
with m18:
    st.markdown(
        '<div class="module-card"><span class="module-code">M18</span><h3>使用说明</h3>'
        '<p>就是当前页面。忘记怎么操作、哪个版本有效、数据是否同步时先看这里。</p></div>',
        unsafe_allow_html=True,
    )
with m17:
    st.markdown(
        '<div class="module-card"><span class="module-code">M17</span><h3>正式评分工作台</h3>'
        '<p>创建任务、导入花名册、填写小组原始分和个人调整、审核并导出。</p></div>',
        unsafe_allow_html=True,
    )
with m16:
    st.markdown(
        '<div class="module-card"><span class="module-code">M16</span><h3>已替代旧版</h3>'
        '<p>仅保留历史对照，不再用于正式成绩处理，也不要在M16继续建立新任务。</p></div>',
        unsafe_allow_html=True,
    )

st.subheader("完整操作流程")
flow = [
    ("01", "启动与更新", "在项目目录先执行 git pull，再启动 Streamlit，进入M18确认状态。"),
    ("02", "创建任务", "进入M17，为每个教学批次或班级建立独立任务，避免数据混在一起。"),
    ("03", "导入花名册", "上传xlsx或csv，至少包含学号和姓名；班级、小组列可自动识别。"),
    ("04", "填写原始分", "在小组评分页填写路演原始分和三级项目报告原始分，同组成员共享。"),
    ("05", "填写调整", "统一、小组、个人加减分及个人系数单独填写，并注明调整原因。"),
    ("06", "审核与导出", "检查错误和警告，确认无误后导出审核工作簿；正式回写教学手册尚未启用。"),
]
for start in range(0, len(flow), 3):
    columns = st.columns(3)
    for column, (number, title, detail) in zip(columns, flow[start : start + 3]):
        with column:
            st.markdown(
                f'<div class="flow-box"><span class="flow-number">{number}</span>'
                f'<strong>{title}</strong><span>{detail}</span></div>',
                unsafe_allow_html=True,
            )

left, right = st.columns([1.05, .95])
with left:
    st.subheader("分数怎么理解")
    st.markdown(
        """
        | 名称 | 含义 | 能否被加减分改写 |
        |---|---|---|
        | 路演原始分 | 对小组路演成果的原始评分 | 不能 |
        | 报告原始分 | 对小组三级项目报告的原始评分 | 不能 |
        | 个人贡献系数 | 把小组原始分折算为个人分 | 可以单独设置 |
        | 统一调整 | 全体学生统一加减 | 只影响最终成绩 |
        | 小组调整 | 某个小组统一加减 | 只影响最终成绩 |
        | 个人调整 | 某名学生额外加减 | 只影响最终成绩 |
        """
    )
    st.code(
        "个人折算分 = 小组原始分 × 个人贡献系数\n"
        "最终成绩 = 按权重计算的基础成绩 + 统一调整 + 小组调整 + 个人调整",
        language="text",
    )

with right:
    st.subheader("文件和数据在哪里")
    st.code(
        "项目代码：E:\\github\\yao_1\n"
        "正式页面：pages\\16_17_grade_workbench.py\n"
        "本机任务数据：data\\grade_workbench\\tasks\n"
        "审核导出：每个任务目录下的 outputs",
        language="text",
    )
    st.markdown(
        '<div class="warning-box"><strong>当前事实：</strong>GitHub只同步了M17程序代码，'
        '真实评分任务仍保存在当前电脑。私有数据仓库和自动同步功能尚未建立。</div>',
        unsafe_allow_html=True,
    )

st.subheader("跨电脑操作注意事项")
st.markdown(
    """
    1. 当前可以在其他电脑 `git pull` 得到M17程序，但**暂时拉不到已经录入的评分任务**。
    2. `yaoy2/yao_1` 是公开仓库，禁止把花名册、学号、成绩、报告原件提交进去。
    3. 不要把正在使用的SQLite数据库直接放进Git或Google Drive同步目录，二进制冲突无法可靠合并。
    4. 以后启用私有仓库同步后，必须先“同步最新数据”，再编辑；保存时由系统检查远端版本。
    5. 同一任务不要在两台电脑上同时修改，以免发生版本冲突。
    """
)

with st.expander("常见问题", expanded=False):
    st.markdown(
        """
        **M17页面只有标题，看不到创建按钮怎么办？**

        刷新浏览器。首次使用时，主页面应显示“先创建第一个评分任务”。

        **为什么M16也能打开？**

        M16是旧版历史页面，保留用于对照；正式成绩任务统一使用M17。

        **换电脑后为什么没有原来的任务？**

        当前跨电脑数据同步尚未启用。代码能通过GitHub更新，真实评分数据仍在原电脑。

        **调整最终成绩会不会改变小组报告分？**

        不会。原始路演分、报告分和各层调整分别保存。
        """
    )

st.info("推荐使用顺序：M18查看说明 → M17正式操作 → M16不再使用。")
