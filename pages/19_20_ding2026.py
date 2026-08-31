"""M20: read-only Ding2026 file transfer and distribution showcase."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.ding2026_showcase import load_public_snapshot
from utils.ui_theme import render_home_link


st.set_page_config(
    page_title="Ding2026 文件中转发放系统",
    page_icon="🗂️",
    layout="wide",
)
render_home_link()

st.markdown(
    """
    <style>
    .m20-hero {
        padding: 1rem 1.1rem;
        margin-bottom: .75rem;
        border: 1px solid rgba(57, 223, 247, .24);
        border-radius: 14px;
        background: linear-gradient(135deg, rgba(10, 28, 46, .95), rgba(22, 32, 42, .92));
    }
    .m20-kicker {
        color: #39dff7;
        font-size: .78rem;
        font-weight: 800;
        letter-spacing: .06em;
    }
    .m20-boundary {
        margin-top: .65rem;
        padding: .55rem .7rem;
        border-left: 3px solid #f5b84b;
        border-radius: 8px;
        background: rgba(245, 184, 75, .08);
        color: #f6dfb5;
    }
    .m20-flow {
        padding: .72rem .8rem;
        border: 1px solid rgba(84, 240, 163, .2);
        border-radius: 10px;
        background: rgba(84, 240, 163, .06);
        color: #dff8ea;
        font-weight: 700;
        line-height: 1.6;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("M20 · Ding2026 文件中转发放系统")
st.markdown(
    """
    <section class="m20-hero">
      <div class="m20-kicker">M20 · LOCAL-FIRST FILE GOVERNANCE</div>
      <p><strong>规则优先 · 手动分发 · 抽样验证 · 全程可撤销 · 永不自动删除</strong></p>
      <p>Ding2026 面向学院行政材料和同步目录：先索引识别，再由用户手动触发分发，
      把不同周期的业务送入对应档案，并保留中转裁决、验证、撤销和备份链路。</p>
      <div class="m20-boundary">本页仅展示项目能力与脱敏静态快照；真实文件操作只在 Windows 本地项目中进行。</div>
    </section>
    """,
    unsafe_allow_html=True,
)

snapshot = load_public_snapshot(ROOT / "assets" / "ding2026_m20_snapshot.json")
if snapshot:
    columns = st.columns(5)
    metrics = (
        ("已索引文件", snapshot["logical_files"]),
        ("待人工裁决", snapshot["pending"]),
        ("年度发票", snapshot["invoices"]),
        ("正式文件", snapshot["official_docs"]),
        ("可撤销记录", snapshot["operations"]),
    )
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, f"{value:,}")
    st.caption(
        f"脱敏静态快照 · {snapshot['generated_at']} · {snapshot['project_version']} · "
        f"物理实例 {snapshot['instances']:,} · 根目录散落 {snapshot['root_left']}；不是实时数据。"
    )
else:
    st.warning("状态快照暂不可用；项目说明仍可正常阅读。")

problem_tab, ability_tab, usage_tab, archive_tab, limit_tab = st.tabs(
    ("解决什么问题", "它能做什么", "日常怎么用", "归档与安全", "当前限制")
)

with problem_tab:
    st.subheader("从散落文件变成可追溯档案")
    st.markdown(
        "材料常同时混有学期任务、年度工作、宣传照片、合作资料和长期制度。"
        "Ding2026 统一接收和识别，但不把不同时间口径强行塞进同一目录；"
        "同时处理重复副本、命名不稳定、误归档和事后难追溯的问题。"
    )

with ability_tab:
    st.subheader("它能做什么")
    st.markdown(
        """
        - **索引与识别**：综合文件名、正文线索、日期和目录上下文。
        - **手动分发**：只有本地用户确认后才按规则归位，系统不自动移动。
        - **五条时间轴**：学期、工作年度、宣传年度、合作年度、长期知识库各归其位。
        - **中转裁决与学习**：不确定材料进入 `90_中转`，人工纠正继续沉淀为规则。
        - **验证与撤销**：保留操作记录，支持抽样验证、单条撤销和整批撤销。
        - **备份与防误删**：同名不同内容保留版本，数据库和配置保留本地备份。
        """
    )

with usage_tab:
    st.subheader("日常怎么用")
    st.markdown(
        '<div class="m20-flow">放入材料 → 本地索引识别 → 用户点击手动分发 → '
        "中转区人工裁决 → 抽样验证并完成归档</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "首次使用时，在 Windows 本地安装独立项目、设置材料根目录、启动本地控制台并执行首次扫描。"
        "后续只需重复放入、分发、裁决和验证。"
    )

with archive_tab:
    st.subheader("五条时间轴，各归其位")
    st.markdown(
        """
        | 时间轴 | 典型内容 | 归档区域 |
        |---|---|---|
        | 学期 | 教学、会议、实习、学工、检查评估 | 学期工作档案 |
        | 工作年度 | 人事、竞赛、绩效、财务、述职、通知 | 年度工作档案 |
        | 宣传年度 | 新闻文档及配套照片 | 品牌新闻 |
        | 合作年度 | 合作单位资料与合同 | 产教融合 / 校企合作 |
        | 长期 | 制度、正式文件、专题资料 | 学院知识库 / 专题资料库 |
        """
    )
    st.markdown(
        "**安全边界：** 永不自动删除；学期不猜；手工调整优先；重复点击会拦截；"
        "进入可删区的副本必须先验证归档位置存在相同内容。"
    )

with limit_tab:
    st.subheader("当前限制")
    st.markdown(
        "老式 `.doc/.xls/.ppt` 主要依赖文件名判断；当前没有 OCR；"
        "AI 预分类默认关闭，启用时需要在本地自行配置兼容接口。"
    )
