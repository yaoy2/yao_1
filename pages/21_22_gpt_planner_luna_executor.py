"""M22：成本感知的 GPT/Luna 与 Codex/Grok 协作，只读展示。"""

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
    .m22-routes {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: .65rem;
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
    .m22-note code, .m22-card code { color: #c4b5fd; }
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
        .m22-grid, .m22-routes, .m22-limit { grid-template-columns: 1fr; }
    }
    </style>
    <div class="m22-shell">
      <section class="m22-hero">
        <div class="m22-kicker">M22 · PUBLIC SKILL SHOWCASE · 2026-09-06 更新</div>
        <h1>🧭 我做了一套“会分工”的 AI 开发流程</h1>
        <p>从固定串联转向按任务分工：小改由主 Agent 直接完成，明确且执行量大的工作交给 Luna 或 Grok，强模型集中解决关键不确定性。目标是降低<strong>完成合格任务的总成本</strong>；总 token 不保证减少。</p>
        <div class="m22-badges">
          <span class="m22-badge">GPT / Luna</span>
          <span class="m22-badge">Codex / Grok</span>
          <span class="m22-badge">按任务选路</span>
          <span class="m22-badge">计入交接与返工</span>
          <span class="m22-badge">展示页只读</span>
        </div>
      </section>

      <div class="m22-section-title">开放选型时，先判断分工是否值得</div>
      <section class="m22-grid">
        <article class="m22-card sol">
          <small>SMALL CHANGE · DIRECT</small>
          <h3>小改，直接完成</h3>
          <p>目标明确、范围小，主 Agent 就地修改并做相称检查。为少量工作安排多轮调查和交接，可能比执行本身更贵。</p>
        </article>
        <article class="m22-card luna">
          <small>LUNA / GROK · EXECUTE</small>
          <h3>执行量大，明确委派</h3>
          <p>需求清楚、执行量足以覆盖交接成本时，交给 Luna 或 Grok。主控给出目标、范围、约束和通过条件，不先通读完整调用链、逐行设计实现再交接。</p>
        </article>
        <article class="m22-card gpt">
          <small>STRONG MODEL · RESOLVE</small>
          <h3>关键不确定性，再升级</h3>
          <p>架构取舍、难定位的问题或重要审查需要更强判断时，集中解决具体疑点。非必要不额外安排网页规划或网页审查。</p>
        </article>
      </section>

      <div class="m22-section-title">两条协作路线，服从用户明确指令</div>
      <section class="m22-routes">
        <article class="m22-card luna">
          <small>GPT / LUNA</small>
          <h3>精简交接 → Luna 执行 → 相称验收</h3>
          <p>说“用 Luna 执行”即可走执行路线；需要网页规划或用户明确要求时，再由 GPT 网页处理规划。明确指定模型、网页或“仅规划”时按该指令执行；仅规划到方案为止。</p>
        </article>
        <article class="m22-card gpt">
          <small>CODEX / GROK</small>
          <h3>具体方案获批 → Grok 执行 → Codex 验收</h3>
          <p>说“用 Grok 执行”，由 Codex 定向，Grok CLI 实施。Grok 的方案、修改范围和测试命令审批保留；完成后返回摘要与可检查证据，必要时做有边界的修复。</p>
        </article>
      </section>

      <section class="m22-limit">
        <div class="m22-note"><strong>成本记完整</strong><br>主控 + 交接 + 执行 + 返工 + 验收都计入。模型单价、缓存、等待和修复都会影响结果；不能只看执行者 token 或一次 CLI 报价。</div>
        <div class="m22-note"><strong>技能怎样触发</strong><br><code>$gpt-planner-luna-executor</code> 或“让 GPT 去做”用于 GPT/Luna 协作；<code>$codex-grok-builder</code> 用于 Grok 编码。普通任务不会自动把项目材料发往网页。</div>
      </section>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("2026-09-06 · 根据 9 月 5 日实测调整")
st.markdown(
    "**之前：** 固定安排探索、网页规划、实现、网页审查和主控验收。  \n"
    "**现在：** 先判断任务规模与不确定性，再选择直接执行、委派执行或强模型判断；"
    "检查通过后，只有新改动、新失败或未解决的疑点才扩大或重复验证。"
)

st.dataframe(
    [
        {
            "独立通道样本": "Luna 执行",
            "模型显示或回报": "Luna · medium",
            "首轮验收": "12/12",
            "修复次数": "0",
            "耗时（统计边界不同）": "约 22 秒 · 执行者报告",
        },
        {
            "独立通道样本": "Grok 执行",
            "模型显示或回报": "grok-4.6-build · run 回报",
            "首轮验收": "12/12",
            "修复次数": "0",
            "耗时（统计边界不同）": "50.319 秒 · CLI run",
        },
        {
            "独立通道样本": "GPT 网页规划",
            "模型显示或回报": "6 Pro · 网页可见",
            "首轮验收": "不适用（仅规划）",
            "修复次数": "不适用",
            "耗时（统计边界不同）": "94 秒 · 网页规划",
        },
    ],
    hide_index=True,
    use_container_width=True,
)
st.markdown(
    "**证据限制：** 三个耗时的统计边界不同，不能直接作速度排名。网页规划与 Luna 是独立通道测试，"
    "没有串成完整端到端运行；也没有“全程强模型”对照，尚未证明总成本下降或任何省 token 比例。"
)

with st.expander("展开样本统计：token、报价与测量边界（只读）"):
    st.markdown(
        "- **Luna：** medium，首轮 12/12，0 次修复；约 22 秒来自执行者报告，token 和实际扣额未知。\n"
        "- **Grok：** 请求模型为 `grok-4.6`，run 回报 `grok-4.6-build`；首轮 12/12，"
        "0 次修复、5 轮，CLI run 耗时 50.319 秒。\n"
        "- **Grok token：** 总计 **96,927**，其中 **58,624** 为缓存 token。"
        "CLI 回报 **$0.01963398**，不等于订阅实际扣费，也不包含主控成本。\n"
        "- **网页规划：** 页面可见模型为 **6 Pro**，规划耗时 **94 秒**；这是规划通道记录，"
        "不代表本地执行耗时或完整任务耗时。"
    )

with st.expander("展开历史流程与本次修正（只读）"):
    st.markdown(
        "**旧流程留档：** Sol 定向 → Luna 取证 → GPT 网页规划 → 批准 → Luna 实现 → "
        "网页审查 → Sol 验收。它保留了角色分工，但把多次交接设为固定步骤。\n\n"
        "**2026-09-06 修正（依据 9 月 5 日实测）：** 开放选型时让小改就地完成，明确且执行量大时再委派，"
        "强模型聚焦关键不确定性。明确指定模型、网页和仅规划的指令继续有效，"
        "Grok 的方案、范围与测试审批继续保留。\n\n"
        "**Grok 执行脚本：** 修复日志覆盖、退出码丢失、错误流混杂、DryRun 创建目录、"
        "恢复会话的标题与路径处理。`Quiet` 只减少主 Agent 接收的输出流，"
        "不减少 Grok 自身生成的 token。\n\n"
        "**同批其他技能：** PPT 改为围绕变更做增量验收；小红书任务复用已登录浏览器；"
        "存储分析增加单次扫描内的缓存。在虚构目录样本中，读取次数由 **24 → 14**，"
        "**8 组结果不变**。这些是规则和局部检查记录，不代表业务全流程已重新测试。"
    )

st.markdown(
    """
    <div class="m22-shell"><div class="m22-public">
      <strong>公开源码与迁移入口</strong><br>
      <a href="https://github.com/yaoy2/yao_1/tree/main/gpt-planner-luna-executor" target="_blank" rel="noopener noreferrer">GPT Planner · Luna Executor ↗</a>
      &nbsp; · &nbsp;
      <a href="https://github.com/yaoy2/yao_1/tree/main/codex-grok-builder" target="_blank" rel="noopener noreferrer">Codex · Grok Builder ↗</a>
      &nbsp; · &nbsp;
      <a href="https://github.com/yaoy2/yao_1/tree/main/personal-skills" target="_blank" rel="noopener noreferrer">其他个人 Skills ↗</a><br>
      拉取仓库可获得主规则、交接协议和执行脚本；要在另一台电脑启用，还需按各技能说明安装到该机的 Skills 目录。
    </div></div>
    """,
    unsafe_allow_html=True,
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
    "M22 只负责公开介绍这套协作方法，不会创建 subagent、控制浏览器、修改项目或调用模型。"
)
