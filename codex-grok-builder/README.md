# Codex → Grok Builder

**Language**: English | [简体中文](README_ZH-CN.md)

**Change logs**: [English](CHANGELOG_EN.md) | [中文](CHANGELOG_ZH-CN.md)

A Windows personal Codex skill: Codex packages the goal, scope, and acceptance criteria; an authenticated Grok Build CLI implements the approved plan; Codex accepts the result using the actual diff and test evidence.

## When to Use It

Invoke for an explicit request such as “use Grok to implement this,” “let Grok write the code,” or `用 Grok 去做`. Quoting these phrases while discussing or maintaining the skill does not start Grok. Requests limited to the Grok website belong to browser tools.

When model selection is open, the current agent should usually complete small edits directly. Delegation is more worthwhile for substantial work with a clear scope. Use a stronger model for important uncertainty, consequential choices, and necessary acceptance; do not fix the controller to Sol or require a Luna review for every task. Compare the total cost of a qualified result, including preparation, handoff, waiting, repair, and acceptance.

## Workflow and Boundaries

1. Codex reads repository rules, existing changes, and enough context to orient the task, then defines the plan, allowed and forbidden files, test commands, and acceptance criteria. Stop prereading once the goal, scope, and acceptance are clear; do not write the complete implementation before delegation.
2. The user approves Grok's specific plan, edit scope, and test commands. Reuse still-valid authorization in the same task; seek renewed approval when scope or conditions change.
3. Combine related work into one packet. Grok handles scoped exploration, implementation, tests, and routine repairs without the controller inspecting every tool call.
4. Grok returns changed files, check results, and relevant log locations. Codex focuses on the actual diff, material risks, and a small amount of verifiable evidence. Add checks or repairs only for defects or unresolved concerns.

A task packet is not a permission sandbox. Grok must not independently expand scope, commit, push, deploy, use credentials, or perform destructive actions. Specific plan and command approvals remain required; the wrapper does not change global permissions.

## Installation and Requirements

Use Windows PowerShell, a working local `grok` command, and Grok authentication completed by the user. The skill stores no keys; the wrapper uses existing CLI authentication. Python 3 is needed only when using the skill validator.

Copy or install the complete `codex-grok-builder/` directory into each machine's effective `CODEX_HOME/skills/codex-grok-builder/`. If `CODEX_HOME` is unset, this is typically `.codex/skills/` under the user profile. Check existing skills and preserve local edits before updating. Pulling the repository does not update installed copies automatically; no fixed drive letter or Junction is assumed. Start a new Codex task if discovery needs to refresh.

Read [SKILL.md](SKILL.md) for the contract, [agents/openai.yaml](agents/openai.yaml) for interface metadata, and [scripts/invoke-grok.ps1](scripts/invoke-grok.ps1) for the wrapper.

## Wrapper Example

This is an approved synthetic merge-function task example. Replace paths and the exact test command with the values approved for the current task. Run from the skill directory:

```powershell
& '.\scripts\invoke-grok.ps1' `
  -ProjectPath 'C:\path\to\repo' `
  -TaskFile 'C:\path\to\approved-task.md' `
  -AllowRule @('Bash(python -B -m pytest -q tests/test_merge_rows.py -p no:cacheprovider)') `
  -Quiet `
  -MaxTurns 12
```

- `-AllowRule` lists only exact commands approved for this run; avoid broad wildcards.
- `-Quiet` retains full logs and reduces the stream returned to the controller. It does not reduce Grok's own reasoning or tool tokens.
- `-MaxTurns 12` is this example's budget, not a completion guarantee. Inspect the actual outcome when the limit is reached.
- `-DryRun` displays arguments without starting Grok or creating output directories or logs.
- Use `-ResumeSessionId` for repairs in an existing session. Each invocation gets independent logs, separate stderr, and the real Grok exit code.

Default `dontAsk` and existing configuration jointly determine actual permissions; it is not a hard filesystem sandbox. The wrapper allows read, search, edit, `git status`, and `git diff` by default, with deny rules for push, hard reset, and common recursive deletion commands. `-AlwaysApprove` requires separate authorization for that run's tool-mode change; do not enable global automatic approval.

## Validation and Cost Reporting

Check PowerShell parsing, then use `-DryRun` to inspect the project, packet, commands, and output location. For wrapper repairs, use a mock CLI to check failure exit codes, log separation, resume names, and side-effect-free previews. Real coding still requires actual diff inspection and proportionate tests.

The wrapper reads actual usage/cost from the CLI's terminal report. Its `run.json` provides `TokenUsage`, `NumTurns`, `ResolvedModels`, `CliReportedCostUsd`, and `UsageStatus`; unavailable fields remain `null`, and `ActualSubscriptionCharge` is `unknown`. Total tokens, higher-priced model usage, subscription allowance, and fees are separate measures; a CLI estimate is not a subscription bill. The synthetic `merge_rows` task on 2026-09-05 passed the same 12 checks on the first attempt with no repairs. Without a complete strong-model baseline, this establishes neither token savings nor a cost ranking. See the [public validation record](../docs/history/2026-09-05-skill-cost-optimization.md).
