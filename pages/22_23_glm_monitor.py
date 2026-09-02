"""M23：GLM 促销雷达（Docker）公开只读展示页。"""

import streamlit as st

from utils.ui_theme import apply_global_theme, render_home_link


st.set_page_config(
    page_title="M23 · GLM 促销雷达",
    page_icon="📡",
    layout="wide",
)
apply_global_theme()
render_home_link(include_sidebar=False)

st.markdown(
    """
    <style>
    .m23-shell { color: #e8f4f8; }
    .m23-hero {
        display: grid;
        grid-template-columns: minmax(0, 1.4fr) minmax(220px, .7fr);
        gap: .7rem 1rem;
        align-items: center;
        margin: .1rem 0 .65rem;
        padding: .72rem .9rem;
        border: 1px solid rgba(56, 189, 248, .28);
        border-radius: 12px;
        background:
            radial-gradient(circle at 92% 18%, rgba(34, 211, 238, .16), transparent 32%),
            linear-gradient(110deg, #071821, #0b1c2a 58%, #08222a);
    }
    .m23-kicker {
        color: #67e8f9;
        font-size: .68rem;
        font-weight: 800;
        letter-spacing: .14em;
    }
    .m23-hero h2 {
        margin: .18rem 0 .28rem;
        color: #f4fbff;
        font-size: clamp(1.18rem, 2.2vw, 1.55rem);
        line-height: 1.2;
    }
    .m23-hero p { margin: 0; color: #9fb4c2; font-size: .82rem; line-height: 1.5; }
    .m23-times {
        display: flex;
        flex-wrap: wrap;
        justify-content: flex-end;
        gap: .32rem;
    }
    .m23-time {
        min-width: 4.4rem;
        padding: .28rem .4rem;
        border: 1px solid rgba(103, 232, 249, .28);
        border-radius: 8px;
        background: rgba(8, 47, 54, .7);
        color: #ecfeff;
        font-size: .72rem;
        font-weight: 800;
        text-align: center;
        font-variant-numeric: tabular-nums;
    }
    .m23-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: .55rem;
        margin-bottom: .55rem;
    }
    .m23-card {
        padding: .55rem .7rem;
        border: 1px solid rgba(125, 211, 252, .16);
        border-radius: 10px;
        background: rgba(8, 20, 30, .78);
    }
    .m23-card h3 {
        margin: 0 0 .4rem;
        color: #e0f2fe;
        font-size: .82rem;
        letter-spacing: .04em;
    }
    .m23-item {
        display: grid;
        grid-template-columns: 5.6rem minmax(0, 1fr);
        gap: .35rem .55rem;
        padding: .28rem 0;
        border-top: 1px solid rgba(148, 163, 184, .12);
        font-size: .78rem;
        line-height: 1.4;
    }
    .m23-item:first-of-type { border-top: 0; padding-top: 0; }
    .m23-item b { color: #7dd3fc; font-weight: 760; }
    .m23-item span { color: #b6c7d4; }
    .m23-flow {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .4rem;
        margin-bottom: .55rem;
    }
    .m23-step {
        display: flex;
        align-items: center;
        gap: .45rem;
        padding: .38rem .5rem;
        border: 1px solid rgba(125, 211, 252, .14);
        border-radius: 9px;
        background: rgba(8, 20, 30, .62);
    }
    .m23-step i {
        flex: 0 0 auto;
        color: #22d3ee;
        font-style: normal;
        font-size: .68rem;
        font-weight: 800;
        letter-spacing: .04em;
    }
    .m23-step strong { color: #f0f9ff; font-size: .78rem; }
    .m23-boundary {
        padding: .45rem .7rem;
        border-left: 3px solid #22d3ee;
        border-radius: 8px;
        background: rgba(34, 211, 238, .07);
        color: #b9c9d4;
        font-size: .78rem;
        line-height: 1.45;
    }
    @media (max-width: 900px) {
        .m23-hero, .m23-grid, .m23-flow { grid-template-columns: 1fr; }
        .m23-times { justify-content: flex-start; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("M23 · GLM 促销雷达")

st.markdown(
    """
    <div class="m23-shell">
      <section class="m23-hero">
        <div>
          <div class="m23-kicker">M23 · DOCKER PROMO RADAR</div>
          <h2>Docker 里跑的智谱促销雷达</h2>
          <p>独立仓库 glm-monitor。容器按点抓智谱官网，去重后发钉钉；没有新优惠就显示无。本页只展示项目有什么、做了什么。</p>
        </div>
        <div class="m23-times">
          <span class="m23-time">09:00</span>
          <span class="m23-time">13:00</span>
          <span class="m23-time">18:30</span>
          <span class="m23-time">20:00</span>
          <span class="m23-time">22:00</span>
        </div>
      </section>

      <div class="m23-flow">
        <div class="m23-step"><i>01</i><strong>抓 4 个官方渠道</strong></div>
        <div class="m23-step"><i>02</i><strong>关键词 / 价格去重</strong></div>
        <div class="m23-step"><i>03</i><strong>钉钉推送</strong></div>
        <div class="m23-step"><i>04</i><strong>没有就显示无</strong></div>
      </div>

      <div class="m23-grid">
        <article class="m23-card">
          <h3>有什么</h3>
          <div class="m23-item"><b>监控对象</b><span>ZCode / BigModel / GLM Coding Plan 促销</span></div>
          <div class="m23-item"><b>官方渠道</b><span>更新日志、活动页、首页横幅、套餐价格页</span></div>
          <div class="m23-item"><b>运行形态</b><span>Docker 常驻容器，端口 8092</span></div>
          <div class="m23-item"><b>通知</b><span>TrendRadar / aihot-push 同一条钉钉机器人</span></div>
          <div class="m23-item"><b>状态</b><span>本机 data/state.json，不进 Git</span></div>
        </article>
        <article class="m23-card">
          <h3>做了什么</h3>
          <div class="m23-item"><b>换执行器</b><span>离开 ZCode 小时任务，改 Docker 调度</span></div>
          <div class="m23-item"><b>五次扫描</b><span>09:00 / 13:00 / 18:30 / 20:00 / 22:00</span></div>
          <div class="m23-item"><b>空结果</b><span>无新优惠时钉钉正文只发「无」</span></div>
          <div class="m23-item"><b>基线</b><span>第一次扫描记下已有活动，不当新闻重报</span></div>
          <div class="m23-item"><b>关键词</b><span>标题带 TrendRadar，机器人才能收下</span></div>
        </article>
      </div>

      <div class="m23-boundary"><b>只读展示：</b>本页不联网、不启容器、不读本机状态、不发钉钉。真实监控在独立仓库 glm-monitor 里跑。</div>
    </div>
    """,
    unsafe_allow_html=True,
)
