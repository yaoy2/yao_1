"""M22：GPT Planner · Luna Executor 公开只读展示页。"""

from __future__ import annotations

import streamlit as st

from utils.ui_theme import render_home_link


st.set_page_config(
    page_title="GPT Planner · Luna Executor",
    page_icon="🧭",
    layout="wide",
)
render_home_link()

st.markdown(
    """
    <style>
    .m22-shell {
        --ink: #eef2ff;
        --muted: #aab4d0;
        --line: rgba(148, 163, 184, .22);
        --sol: #a78bfa;
        --luna: #60a5fa;
        --gpt: #34d399;
    }
    .m22-hero {
        padding: 1.1rem 1.2rem;
        margin-bottom: .85rem;
        border: 1px solid rgba(167, 139, 250, .28);
        border-radius: 16px;
        background:
            radial-gradient(circle at 88% 12%, rgba(52, 211, 153, .13), transparent 28%),
            linear-gradient(135deg, rgba(28, 25, 55, .97), rgba(13, 25, 43, .97));
    }
    .m22-kicker {
        color: #c4b5fd;
        font-size: .76rem;
        font-weight: 780;
        letter-spacing: .08em;
        text-transform: uppercase;
    }
    .m22-hero h1 {
        margin: .28rem 0 .35rem;
        color: #f8fafc;
        font-size: clamp(1.55rem, 3vw, 2.15rem);
    }
    .m22-hero p {
        max-width: 880px;
        margin: 0;
        color: #bec8de;
        line-height: 1.65;
    }
    .m22-badges {
        display: flex;
        flex-wrap: wrap;
        gap: .38rem;
        margin-top: .75rem;
    }
    .m22-badge {
        padding: .2rem .55rem;
        border: 1px solid rgba(196, 181, 253, .28);
        border-radius: 999px;
        color: #ddd6fe;
        background: rgba(139, 92, 246, .09);
        font-size: .75rem;
        font-weight: 700;
    }
    .m22-section-title {
        margin: 1.05rem 0 .55rem;
        color: #dbe4f4;
        font-size: 1.04rem;
        font-weight: 760;
    }
    .m22-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: .65rem;
    }
    .m22-card {
        min-height: 148px;
        padding: .8rem .85rem;
        border: 1px solid var(--line);
        border-radius: 13px;
        background: rgba(15, 23, 42, .72);
    }
    .m22-card.sol { border-top: 3px solid var(--sol); }
    .m22-card.luna { border-top: 3px solid var(--luna); }
    .m22-card.gpt { border-top: 3px solid var(--gpt); }
    .m22-card small {
        color: #8894b2;
        font-size: .7rem;
        font-weight: 760;
        letter-spacing: .05em;
    }
    .m22-card h3 {
        margin: .25rem 0 .38rem;
        color: var(--ink);
        font-size: 1rem;
    }
    .m22-card p {
        margin: 0;
        color: var(--muted);
        font-size: .86rem;
        line-height: 1.55;
    }
    .m22-flow {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .5rem;
    }
    .m22-step {
        padding: .65rem .7rem;
        border: 1px solid var(--line);
        border-radius: 12px;
        background: rgba(15, 23, 42, .56);
    }
    .m22-step b {
        display: block;
        margin-bottom: .22rem;
        color: #e2e8f0;
        font-size: .84rem;
    }
    .m22-step span {
        color: #98a5c2;
        font-size: .76rem;
        line-height: 1.42;
    }
    .m22-limit {
        display: grid;
        grid-template-columns: 1.05fr 1fr;
        gap: .65rem;
        margin-top: .65rem;
    }
    .m22-note {
        padding: .78rem .85rem;
        border: 1px solid var(--line);
        border-radius: 13px;
        background: rgba(15, 23, 42, .62);
        color: var(--muted);
        font-size: .84rem;
        line-height: 1.58;
    }
    .m22-note strong { color: #f1f5f9; }
    .m22-note code { color: #c4b5fd; }
    .m22-public {
        margin-top: .8rem;
        padding: .82rem .9rem;
        border: 1px solid rgba(52, 211, 153, .25);
        border-radius: 13px;
        background: rgba(6, 78, 59, .12);
        color: #b8c9c2;
        line-height: 1.58;
    }
    .m22-public strong { color: #a7f3d0; }
    .m22-public a { color: #6ee7b7; }
    @media (max-width: 850px) {
        .m22-grid, .m22-flow, .m22-limit { grid-template-columns: 1fr; }
        .m22-card { min-height: auto; }
    }
    </style>
    <div class="m22-shell">
      <section class="m22-hero">
        <div class="m22-kicker">M22 · PUBLIC SKILL SHOWCASE</div>
        <h1>🧭 我做了一套“会分工”的 AI 开发流程</h1>
        <p>GPT Planner · Luna Executor 把同一个任务拆给三种角色：Sol 只负责定向与把关，Luna 进入真实项目探索、修改和测试，ChatGPT 网页版集中承担复杂规划与最终审查。目标是保留高质量判断，同时避免 Sol 在执行和 Review 中无限消耗 token。</p>
        <div class="m22-badges">
          <span class="m22-badge">公开 Skill</span>
          <span class="m22-badge">本地项目可执行</span>
          <span class="m22-badge">最多一次 Planning</span>
          <span class="m22-badge">最多一次 Final Review</span>
          <span class="m22-badge">展示页只读</span>
        </div>
      </section>

      <div class="m22-section-title">三个角色，各做自己最合适的事</div>
      <section class="m22-grid">
        <article class="m22-card sol">
          <small>SOL · ORCHESTRATOR</small>
          <h3>先定向，再分发</h3>
          <p>理解用户目标、权限和项目入口，只做少量战略性查看；给 Luna 明确调查边界，控制范围，并在最后进行一次证据验收。</p>
        </article>
        <article class="m22-card luna">
          <small>LUNA · EXPLORER / EXECUTOR</small>
          <h3>探索、修改、测试</h3>
          <p>接收有边界的问题，在本地查代码与收集事实；计划获批后由同一个 Luna 修改文件、运行命令、处理小修复并检查 diff。</p>
        </article>
        <article class="m22-card gpt">
          <small>CHATGPT WEB · PLANNER / REVIEWER</small>
          <h3>集中做复杂判断</h3>
          <p>基于精简 Context Packet 设计方案、明确风险和验收标准；执行完成后审查 Final Review Packet，不假装操作本地项目。</p>
        </article>
      </section>

      <div class="m22-section-title">从第一句话到最终交付</div>
      <section class="m22-flow">
        <div class="m22-step"><b>1 · RECEIVED</b><span>Sol 确认真实目标、权限和验收条件。</span></div>
        <div class="m22-step"><b>2 · ORIENTING</b><span>Sol 少量查看规则、状态和关键入口。</span></div>
        <div class="m22-step"><b>3 · DISCOVERING</b><span>Luna 做有边界的只读探索并提交证据。</span></div>
        <div class="m22-step"><b>4 · PLANNING</b><span>ChatGPT 根据精简 Packet 输出可执行方案。</span></div>
        <div class="m22-step"><b>5 · APPROVAL</b><span>用户确认方案后，才允许本地修改。</span></div>
        <div class="m22-step"><b>6 · EXECUTING</b><span>同一个 Luna 修改、测试、检查差异。</span></div>
        <div class="m22-step"><b>7 · REVIEWING</b><span>ChatGPT 对实际结果给出 PASS / FIX / REPLAN。</span></div>
        <div class="m22-step"><b>8 · ACCEPTING</b><span>Sol 只做一次最终证据检查并交付。</span></div>
      </section>

      <section class="m22-limit">
        <div class="m22-note"><strong>怎样触发</strong><br>对 Codex 说 <code>让 GPT 去做</code>，或显式使用 <code>$gpt-planner-luna-executor</code>。普通任务不会自动把项目内容发送到 ChatGPT 网页版。</div>
        <div class="m22-note"><strong>怎样防止烧 token</strong><br>常规路径只有一次 ChatGPT Planning、一次 Luna Execution、一次 ChatGPT Final Review。Sol 不在执行阶段反复审代码，也不重做 ChatGPT 已完成的高层推理。</div>
      </section>

      <div class="m22-public">
        <strong>源码已经公开并可迁移。</strong> Skill 源文件保存在仓库的 <code>gpt-planner-luna-executor/</code>，包含主规则、模型界面说明和 Packet 协议。另一台电脑执行 <code>git pull</code> 即可取得源码；要让该机的 Codex 全局识别，还需把这个目录安装或链接到那台电脑自己的 Skills 目录。<br>
        <a href="https://github.com/yaoy2/yao_1/tree/main/gpt-planner-luna-executor" target="_blank">查看 GitHub 上的完整 Skill 源码 ↗</a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("查看公开文件组成（只读）"):
    st.code(
        """gpt-planner-luna-executor/
├── SKILL.md                         # 主工作流、角色与边界
├── agents/openai.yaml              # Skill 展示元数据
└── references/packet-protocol.md   # 九种任务交接 Packet 模板""",
        language="text",
    )

with st.expander("查看最简单的跨电脑使用方式（只读）"):
    st.code(
        """git clone https://github.com/yaoy2/yao_1.git
cd yao_1

# 已经克隆过时只需：
git pull""",
        language="powershell",
    )
    st.caption("拉取会获得 Skill 源码；实际启用位置取决于另一台电脑的 Codex Skills 配置。")

st.caption(
    "M22 只负责公开介绍这套协作方法，不会创建 subagent、控制浏览器、修改项目或调用 ChatGPT。"
)
