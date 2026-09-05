# GPT Planner · Luna Executor

**Language**: English | [简体中文](README_ZH-CN.md)

**Change logs**: [English](CHANGELOG_EN.md) | [中文](CHANGELOG_ZH-CN.md)

A personal Codex skill that coordinates GPT planning and Luna execution according to the task. The objective is a qualified result with proportionate preparation, handoff, and acceptance; it does not promise token savings or a fixed reduction without evidence.

## When to Use It

| Request or task | Appropriate route |
| --- | --- |
| A small edit with no model specified | The current agent completes it directly, avoiding another handoff. |
| “Use Luna to execute,” with a clear goal and substantial work | Delegate scoped exploration, implementation, and checks together; do not open the web. |
| “Use GPT to plan” or “planning only” | Produce the requested plan and stop before implementation. |
| “GPT plans, then Luna executes” | Follow the explicitly requested web-planning and Luna-execution route, preserving valid authority and acceptance requirements. |
| Unresolved architecture, diagnosis, or material choices | Use a stronger model for the important uncertainty, then decide whether to delegate. |
| An explicit model, web channel, or sequence | Respect the selection; identify unavailable steps rather than silently switching models. |

Natural-language triggers include “use Luna to execute,” “use GPT to plan,” “GPT plans, then Luna executes,” and `让 GPT 去做`. Discussing those phrases or maintaining the skill does not authorize a live run. Route Grok coding to [Codex → Grok Builder](../codex-grok-builder/README_EN.md).

## Collaboration

The controller establishes the goal, repository rules, existing changes, and key scope, then sends a concise packet containing the goal, allowed scope, necessary sources, acceptance criteria, authority, and unresolved questions. Stop prereading once the goal, scope, and acceptance are clear. Do not write the complete implementation before delegation or supervise every tool call.

Luna handles scoped discovery, edits, tests, and routine repairs. At milestones or completion, the controller receives a small amount of evidence: changed files, test commands and outcomes, key differences, and blockers. Escalate to a stronger model only for new risk or failure. Reuse the same task's context and valid authorization, and batch related work into one handoff where practical.

The default does not fix the controller to Sol, require web planning, or mandate another web review for every task. When web use is explicitly requested, use an available authenticated browser; the user handles login, account selection, and MFA. Missing web capability blocks only dependent steps. An unperformed check must not be reported as a failed check.

Invoking the skill does not expand repository permissions. Sensitive material, external writes, deployment, and other restricted operations follow current task authorization and project rules. Planning-only requests stop at the plan; explicit delegation is not silently replaced by controller implementation.

## Installation and Validation

Copy or install the complete `gpt-planner-luna-executor/` directory into each machine's effective `CODEX_HOME/skills/gpt-planner-luna-executor/`. If `CODEX_HOME` is unset, this is typically `.codex/skills/` under the user profile. Check existing installations and preserve local edits. Pulling the repository does not update installed copies automatically; no fixed drive letter or Junction is required. Start a new Codex task if discovery needs to refresh.

[SKILL.md](SKILL.md) is the execution entry point; the [packet protocol](references/packet-protocol.md) defines handoff fields. Validate skill discovery, the actual executor model, the agreed scope, and necessary checks. Call the web-planning-to-Luna route complete only after actually running the entire sequence.

## Available Evidence

In the synthetic `merge_rows` task on 2026-09-05, Luna medium passed 12/12 checks on the first attempt with no repairs, taking about 22 seconds for the execution stage; usage was not provided. An independent planning test in ChatGPT Web, visibly labeled `6 Pro`, took about 94 seconds. These were separate channel checks, not a complete sequential web-to-Luna run, and there was no full strong-model baseline.

Total tokens, higher-priced model usage, allowance, and fees are different measures. Comparisons must include the controller, preparation, handoff, repairs, and acceptance. These results establish the tested channels' operation, not a fee ranking or proven token savings. See the [public validation record](../docs/history/2026-09-05-skill-cost-optimization.md). The M22 [online guide](https://whatsup.streamlit.app/22_gpt_planner_luna_executor) displays the workflow and record without calling models.
