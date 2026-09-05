# Change Log

**Language**: English | [中文](CHANGELOG_ZH-CN.md)

**README**: [English](README_EN.md) | [中文](README_ZH-CN.md)

## 2026-09-06

- **Routed work by task needs**: Sol, web planning, and web review are no longer mandatory. Small edits stay with the current agent when model selection is open; substantial, clearly scoped work is batched for Luna. Explicit model, web, and planning-only requests remain authoritative.
- **Reduced repeated exploration and handoffs**: stop controller prereading once the goal, scope, and acceptance are clear; do not write the full implementation before delegation. The executor handles scoped exploration, implementation, and routine repair, returning concise verifiable evidence without per-tool supervision.
- **Added standalone documentation**: bilingual READMEs and changelogs explain triggers, authority boundaries, and installation into each machine's effective CODEX_HOME/skills. M22 remains a read-only guide.
- **Separated validation from cost claims**: on September 5, Luna medium passed 12/12 synthetic merge_rows checks on the first attempt with no repairs, taking about 22 seconds for execution; usage was unavailable. An independent web-planning check visibly labeled 6 Pro took about 94 seconds. Neither a full sequential web-to-Luna run nor a complete strong-model baseline was measured, so token savings and fee advantages remain unproven. See the [public record](../docs/history/2026-09-05-skill-cost-optimization.md).
