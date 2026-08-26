# Codex → Grok Builder

[中文版](README_ZH-CN.md)

A Windows-first personal Codex skill that runs a controlled two-agent coding loop:

`Codex plans → user approves → Grok Build implements → Codex verifies → Grok repairs if needed`

## Trigger phrases

The skill is automatically considered whenever a direct user instruction means “use Grok to do it,” including:

- `用grok去做`
- `用 Grok 去做`
- `让 Grok 做`
- `交给 Grok 实现`
- `让 Grok 写代码`

Capitalization, spaces, and natural wording variations do not need to match exactly. Quoting these phrases only to discuss or configure the skill does not start an implementation run.

## Responsibilities

- **Codex:** inspect the repository, create the canonical plan, define scope and acceptance criteria, review the diff, and rerun tests independently.
- **Grok Build:** edit only the approved scope and run only approved commands through its local headless CLI.
- **User:** approve the plan and any later scope, permission, deployment, secret, or destructive-operation expansion.

## Requirements

- Windows PowerShell.
- A local `grok` command authenticated with `grok login`.
- A Codex task configured to GPT-5.6 Sol with `xhigh` reasoning when that exact planner configuration is required.
- Python 3 only for the bundled Codex skill validator; the runtime wrapper itself is PowerShell.

No API key is stored in this project. The wrapper uses the existing Grok login or environment-based authentication resolved by Grok Build.

## Files

```text
codex-grok-builder/
├── SKILL.md                    Skill routing and workflow contract
├── README.md                   English default README
├── README_EN.md                English README mirror
├── README_ZH-CN.md             Chinese README
├── CHANGELOG.md                English default changelog
├── CHANGELOG_EN.md             English changelog mirror
├── CHANGELOG_ZH-CN.md          Chinese changelog
├── agents/openai.yaml          Codex UI metadata and implicit invocation
└── scripts/invoke-grok.ps1     Deterministic Grok Build wrapper
```

## How it runs

1. Codex records the existing worktree state and reads repository rules.
2. Codex proposes a plan with allowed files, forbidden scope, test commands, risks, and acceptance criteria.
3. After approval, Codex writes a temporary task packet outside the repository.
4. The wrapper starts Grok Build headlessly with a named session and explicit permission rules.
5. Codex reviews the real diff and reruns the approved tests without trusting Grok's completion claim.
6. Failed acceptance can be returned to the same Grok session for up to two focused repair cycles.

## Direct wrapper use

Normally Codex invokes the wrapper. For diagnostics or manual use:

```powershell
& "$env:USERPROFILE\.codex\skills\codex-grok-builder\scripts\invoke-grok.ps1" `
  -ProjectPath 'C:\path\to\repo' `
  -TaskFile 'C:\path\to\approved-task.md' `
  -AllowRule @('Bash(npm.cmd test*)', 'Bash(npm.cmd run build*)')
```

Add `-DryRun` to inspect the generated Grok arguments without starting Grok.

## Permission model

- Default mode is `dontAsk`: unapproved tools are silently denied.
- Reads, searches, edits, `git status`, and `git diff` are allowed by default.
- Test and build commands must be passed explicitly with `-AllowRule`.
- Push, hard reset, repository cleaning, and common recursive-delete commands are denied by default.
- `-AlwaysApprove` is available only for a run that the user explicitly authorizes; it remains riskier even with deny rules.
- The worker contract prohibits commits, pushes, deployment, secrets, and scope expansion unless the approved task explicitly grants them.

## Installation layout

The canonical source lives at:

```text
E:\github\yao_1\codex-grok-builder
```

The active personal-skill path is a Windows junction pointing to that source:

```text
E:\codex\.codex\skills\codex-grok-builder
```

This keeps the skill discoverable while allowing the project to be versioned with `yao_1`. Start a new Codex task or restart Codex if a changed skill is not immediately visible.

## Validation

From the project directory:

```powershell
py -3 -X utf8 'E:\codex\.codex\skills\.system\skill-creator\scripts\quick_validate.py' .
```

Also parse the wrapper before release:

```powershell
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  '.\scripts\invoke-grok.ps1',
  [ref]$tokens,
  [ref]$errors
) | Out-Null
$errors
```
