"""M23：docker-monitor 公开只读展示页。"""

import streamlit as st

from utils.ui_theme import render_home_link


st.set_page_config(
    page_title="M23 · docker-monitor",
    page_icon="📡",
    layout="wide",
)
render_home_link()

st.markdown(
    """
    <style>
    .m23-shell { color: #e8f4f8; }
    .m23-hero {
        display: grid;
        grid-template-columns: minmax(0, 1.5fr) minmax(180px, .55fr);
        gap: .55rem .9rem;
        align-items: center;
        margin: .1rem 0 .55rem;
        padding: .6rem .8rem;
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
        margin: .12rem 0 .22rem;
        color: #f4fbff;
        font-size: clamp(1.12rem, 2vw, 1.42rem);
        line-height: 1.2;
    }
    .m23-hero p { margin: 0; color: #9fb4c2; font-size: .8rem; line-height: 1.45; }
    .m23-ports {
        display: flex;
        flex-wrap: wrap;
        justify-content: flex-end;
        gap: .28rem;
    }
    .m23-port {
        min-width: 4.2rem;
        padding: .22rem .36rem;
        border: 1px solid rgba(103, 232, 249, .28);
        border-radius: 8px;
        background: rgba(8, 47, 54, .7);
        color: #ecfeff;
        font-size: .7rem;
        font-weight: 800;
        text-align: center;
        font-variant-numeric: tabular-nums;
    }
    .m23-tasks { display: grid; gap: .42rem; margin-bottom: .5rem; }
    .m23-task {
        display: grid;
        grid-template-columns: minmax(9.5rem, .9fr) minmax(0, 1.6fr) minmax(10.5rem, .85fr);
        gap: .35rem .65rem;
        align-items: start;
        padding: .42rem .55rem;
        border: 1px solid rgba(125, 211, 252, .16);
        border-radius: 10px;
        background: rgba(8, 20, 30, .78);
    }
    .m23-task h3 {
        margin: 0;
        color: #e0f2fe;
        font-size: .82rem;
        letter-spacing: .03em;
    }
    .m23-meta {
        margin: .18rem 0 0;
        color: #7dd3fc;
        font-size: .7rem;
        font-weight: 760;
    }
    .m23-task p {
        margin: 0;
        color: #b6c7d4;
        font-size: .76rem;
        line-height: 1.4;
    }
    .m23-times {
        display: flex;
        flex-wrap: wrap;
        justify-content: flex-end;
        gap: .22rem;
    }
    .m23-time {
        padding: .16rem .32rem;
        border: 1px solid rgba(103, 232, 249, .22);
        border-radius: 6px;
        background: rgba(8, 47, 54, .55);
        color: #ecfeff;
        font-size: .66rem;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
    }
    .m23-boundary {
        padding: .4rem .65rem;
        border-left: 3px solid #22d3ee;
        border-radius: 8px;
        background: rgba(34, 211, 238, .07);
        color: #b9c9d4;
        font-size: .76rem;
        line-height: 1.45;
    }
    @media (max-width: 900px) {
        .m23-hero, .m23-task { grid-template-columns: 1fr; }
        .m23-ports, .m23-times { justify-content: flex-start; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("M23 · docker-monitor")

st.markdown(
    """
    <div class="m23-shell">
      <section class="m23-hero">
        <div>
          <div class="m23-kicker">M23 · DOCKER MONITOR</div>
          <h2>本机 Docker 常驻任务合集</h2>
          <p>真实监控在独立仓库 docker-monitor。一个 Compose 跑三个任务，去重或比价后发同一条钉钉。本页只展示有什么、做什么。</p>
        </div>
        <div class="m23-ports">
          <span class="m23-port">8091</span>
          <span class="m23-port">8092</span>
          <span class="m23-port">8093</span>
        </div>
      </section>

      <div class="m23-tasks">
        <article class="m23-task">
          <div>
            <h3>GLM 促销雷达</h3>
            <p class="m23-meta">glm-monitor · 8092</p>
          </div>
          <p>扫描智谱官网渠道，关键词 / 价格去重后发钉钉。没有新优惠正文只发「无」。第一次扫描只建基线，不当新闻重报。</p>
          <div class="m23-times">
            <span class="m23-time">09:00</span>
            <span class="m23-time">13:00</span>
            <span class="m23-time">18:30</span>
            <span class="m23-time">20:00</span>
            <span class="m23-time">22:00</span>
          </div>
        </article>
        <article class="m23-task">
          <div>
            <h3>AIHOT 增量</h3>
            <p class="m23-meta">aihot-push · 8091</p>
          </div>
          <p>跟随 TrendRadar 窗口读取 AIHOT 增量精选，过滤后发钉钉。不复制全库，只保存游标和去重状态。</p>
          <div class="m23-times">
            <span class="m23-time">09:30</span>
            <span class="m23-time">14:00</span>
            <span class="m23-time">17:00</span>
          </div>
        </article>
        <article class="m23-task">
          <div>
            <h3>德亚显卡报价</h3>
            <p class="m23-meta">gpu-watch · 8093</p>
          </div>
          <p>Amazon.de 自营 ASUS Prime / TUF / PNY 的 5080、5090，各报最低 3 条。不要 Slim、EVO。每次都推当前价和涨跌；没货写无货。</p>
          <div class="m23-times">
            <span class="m23-time">09:00</span>
            <span class="m23-time">21:00</span>
          </div>
        </article>
      </div>

      <div class="m23-boundary"><b>只读展示：</b>本页不联网、不启容器、不读本机状态、不发钉钉。标题带 TrendRadar 才能被同一条机器人收下。真实监控留在 docker-monitor。</div>
    </div>
    """,
    unsafe_allow_html=True,
)
