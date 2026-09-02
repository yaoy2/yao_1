"""M23：GLM/ZCode 促销雷达公开只读展示页。"""

import streamlit as st

from utils.ui_theme import apply_global_theme, render_home_link


st.set_page_config(
    page_title="M23 · GLM/ZCode 促销雷达",
    page_icon="📡",
    layout="wide",
)
apply_global_theme()
render_home_link(include_sidebar=False)

st.markdown(
    """
    <style>
    .m23-shell { color: #eaf7ff; }
    .m23-hero {
        margin: .2rem 0 1rem;
        padding: 1.3rem 1.45rem;
        border: 1px solid rgba(84, 240, 163, .28);
        border-radius: 18px;
        background: linear-gradient(120deg, rgba(7, 27, 36, .96), rgba(12, 22, 39, .94));
        box-shadow: 0 18px 54px rgba(0, 0, 0, .24);
    }
    .m23-kicker {
        color: #54f0a3;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .13em;
    }
    .m23-hero h2 {
        margin: .32rem 0 .4rem;
        color: #f4fbff;
        font-size: clamp(1.55rem, 3vw, 2.35rem);
        line-height: 1.1;
    }
    .m23-hero p { max-width: 880px; margin: 0; color: #b7c8d6; line-height: 1.65; }
    .m23-badges { display: flex; flex-wrap: wrap; gap: .42rem; margin-top: .85rem; }
    .m23-badge {
        padding: .28rem .58rem;
        border: 1px solid rgba(115, 238, 255, .2);
        border-radius: 999px;
        background: rgba(57, 223, 247, .07);
        color: #cdeef7;
        font-size: .72rem;
        font-weight: 700;
    }
    .m23-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .7rem; }
    .m23-card {
        min-height: 0;
        padding: .82rem .9rem;
        border: 1px solid rgba(115, 238, 255, .16);
        border-radius: 13px;
        background: rgba(9, 18, 31, .78);
    }
    .m23-card small { color: #54f0a3; font-size: .68rem; font-weight: 800; letter-spacing: .08em; }
    .m23-card strong { display: block; margin: .2rem 0; color: #f2f9fc; font-size: .95rem; }
    .m23-card p { margin: 0; color: #aebfcd; font-size: .8rem; line-height: 1.5; }
    .m23-row { display: grid; grid-template-columns: 1.15fr .85fr; gap: .75rem; margin-top: .75rem; }
    .m23-panel {
        padding: .95rem 1rem;
        border: 1px solid rgba(115, 238, 255, .16);
        border-radius: 14px;
        background: rgba(9, 18, 31, .7);
    }
    .m23-panel h3 { margin: 0 0 .55rem; color: #f4fbff; font-size: 1rem; }
    .m23-list { display: grid; gap: .4rem; }
    .m23-list div { color: #b6c7d5; font-size: .81rem; line-height: 1.45; }
    .m23-list b { color: #eaf7ff; }
    .m23-boundary {
        margin-top: .75rem;
        padding: .82rem 1rem;
        border-left: 3px solid #54f0a3;
        border-radius: 8px;
        background: rgba(84, 240, 163, .075);
        color: #c8d7e0;
        font-size: .82rem;
        line-height: 1.55;
    }
    @media (max-width: 900px) {
        .m23-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .m23-row { grid-template-columns: 1fr; }
    }
    @media (max-width: 560px) { .m23-grid { grid-template-columns: 1fr; } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("M23 · GLM/ZCode 促销雷达")

st.markdown(
    """
    <div class="m23-shell">
      <section class="m23-hero">
        <div class="m23-kicker">M23 · LOCAL-FIRST PROMO RADAR</div>
        <h2>让限时额度在过期前被看见</h2>
        <p>这是一个给 ZCode、BigModel 与 GLM Coding Plan 使用的促销监控项目。它每小时扫描官方渠道，识别新的 Token、额度、套餐和限时活动，去重后发送 Windows 桌面通知，并留下可追溯记录。</p>
        <div class="m23-badges">
          <span class="m23-badge">每小时扫描</span>
          <span class="m23-badge">4 个官方渠道</span>
          <span class="m23-badge">全网搜索兜底</span>
          <span class="m23-badge">本机状态去重</span>
        </div>
      </section>

      <div class="m23-grid">
        <article class="m23-card"><small>01 · SCAN</small><strong>抓取官方渠道</strong><p>检查 ZCode 更新日志、BigModel 活动页、官网横幅和 GLM Coding 套餐页。</p></article>
        <article class="m23-card"><small>02 · VERIFY</small><strong>确认活动事实</strong><p>社区与媒体只提供线索；日期、权益、价格和领取入口以官方渠道为准。</p></article>
        <article class="m23-card"><small>03 · DEDUPE</small><strong>本机状态去重</strong><p>活动按“来源 + 核心事实”生成标识，已经见过的内容不再重复提醒。</p></article>
        <article class="m23-card"><small>04 · ALERT</small><strong>Windows 桌面通知</strong><p>仅在发现新活动时弹窗，同时把扫描摘要和详情追加到本机历史档案。</p></article>
      </div>

      <div class="m23-row">
        <section class="m23-panel">
          <h3>监控范围</h3>
          <div class="m23-list">
            <div><b>ZCode 更新日志</b> · 重点识别赠送额度、新权益和版本活动。</div>
            <div><b>BigModel 上新活动页</b> · 查找套餐优惠、领取窗口和截止时间。</div>
            <div><b>ZCode 官网横幅</b> · 捕捉短期公告和首页限时信息。</div>
            <div><b>GLM Coding 套餐页</b> · 对比价格、额度与权益变化。</div>
          </div>
        </section>
        <section class="m23-panel">
          <h3>运行边界</h3>
          <div class="m23-list">
            <div><b>运行位置</b> · Windows 本机与 ZCode 定时任务。</div>
            <div><b>本机状态</b> · 每台电脑独立保存，不进入 Git。</div>
            <div><b>触发条件</b> · 电脑开机且 ZCode 客户端运行。</div>
            <div><b>失败处理</b> · 单页最多重试一次，不无限消耗额度。</div>
          </div>
        </section>
      </div>

      <div class="m23-boundary"><b>只读展示：</b>M23 只解释 GLM-Monitor 的设计与运行边界，不联网扫描、不创建定时任务、不读取本机状态、不执行 PowerShell，也不会触发通知。真实运行继续留在独立私有仓库和本机环境中。</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("展开查看项目结构与部署逻辑"):
    st.markdown(
        """
        - `prompt/monitor.prompt.md`：规定扫描、核验、去重和结果输出流程。
        - `scripts/toast.ps1`：发送 Windows 桌面通知，兼容 PowerShell 5.1 中文编码。
        - `templates/`：提供初始状态和历史档案模板。
        - `setup.ps1`：初始化本机状态，并生成带本机路径的任务提示词。
        - `state/`：保存每台电脑自己的运行状态，已由 Git 忽略。

        部署脚本不会覆盖已有状态；多台电脑各自维护去重记录，避免同步冲突。
        """
    )
