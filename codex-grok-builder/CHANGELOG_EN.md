# Change Log

**Language**: English | [中文](CHANGELOG_ZH-CN.md)
**README**: [English](README_EN.md) | [中文](README_ZH-CN.md)

This English change log is the default GitHub changelog for Grok Builder. Keep `CHANGELOG.md` identical to this file.

## 2026-09-06

- **Sized handoffs to the task**: explicit model choices and valid authorization remain authoritative. With open model selection, small edits stay with the current agent and substantial work is delegated in one packet. The controller does not read the entire project, write the full implementation before delegation, or supervise every tool call. Sol and a separate Luna review are no longer mandatory.
- **Retained permission boundaries**: specific plan, scope, and test-command approvals remain required. Documented that dontAsk works with existing configuration rather than forming a hard filesystem sandbox. Installation now targets each machine's effective CODEX_HOME/skills instead of an obsolete fixed E-drive Junction.
- **Repaired the wrapper**: isolated per-call logs and stderr, preserved actual exit codes, used independent run IDs for log filenames instead of session titles, and removed DryRun directory creation. Quiet retains complete logs while reducing only the stream returned to the controller. run.json reads TokenUsage, NumTurns, ResolvedModels, CliReportedCostUsd, and UsageStatus from terminal output; missing fields remain null and actual subscription charges remain unknown.
- **Validation and corrected inference**: 11 mock runs and 16 assertions passed. On September 5, Grok passed 12/12 synthetic merge_rows checks on the first attempt with no repairs: five turns and 50.319 seconds native time. The CLI reported 96,927 total tokens, including 58,624 cached tokens, and $0.01963398. This is not a subscription bill and excludes controller, preparation, and acceptance overhead. Without a complete strong-model baseline, workflow success does not establish token savings or a cost advantage. See the [public record](../docs/history/2026-09-05-skill-cost-optimization.md).

## 2026-08-24

- **Initial controlled Codex-to-Grok workflow**: added a Windows-first personal Codex skill that runs `Codex plans → user approves → Grok Build implements → Codex verifies → Grok repairs if needed`.
- **Skill contract**: `SKILL.md` defines trigger phrases, the approved-task packet shape, the permission model, and acceptance rules. Codex remains the planner and verifier; Grok Build is the implementation worker.
- **Deterministic wrapper**: `scripts/invoke-grok.ps1` starts Grok Build headlessly with a named session, default `dontAsk` permissions, explicit allow rules for approved commands, and deny rules for push, hard reset, repository cleaning, and common recursive deletes.
- **Codex metadata**: `agents/openai.yaml` sets the display name, short description, default prompt, and implicit invocation.
- **No secrets in the project**: the wrapper uses the existing local `grok login` session or environment-based authentication resolved by Grok Build.
