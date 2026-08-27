---
name: codex-grok-builder
description: "Orchestrate controlled coding handoffs where Sol defines the approved plan and final acceptance, Grok Build implements, and Luna handles routine review and repair coordination. Use when the user explicitly asks Grok to implement or operate, such as 用 Grok 去做, 让 Grok 做, 交给 Grok 实现, or a clear wording variant. Do not use for quoted or discussed phrases, Codex-only edits, or browser-only Grok work."
metadata:
  short-description: Sol plans, Grok builds, Luna reviews
---

# Codex → Grok Builder

Run a controlled implementation handoff optimized for reliability and low Sol token usage. The user-approved Sol plan is canonical.

Use this control flow:

```text
Sol planning
→ Grok implementation
→ Luna review
→ Grok repair if needed
→ Luna re-review
→ Sol final acceptance
```

Keep Sol out of routine review and repair loops unless escalation is required.

## Trigger

Invoke when the user clearly authorizes Grok to implement or operate, regardless of capitalization, spacing, or minor wording differences. Common examples include:

- `用 Grok 去做`
- `让 Grok 做`
- `让 Grok 写代码`
- `交给 Grok 实现`
- `让 Grok 完成，你来验收`

Quoted or discussed wording alone is not authorization to execute. Do not invoke for edits to this skill, Codex-only implementation, or browser-only Grok work.

## Roles

### Sol

Sol owns:

- repository inspection
- the canonical implementation plan
- allowed and forbidden scope
- acceptance criteria
- approved test and build commands
- architecture decisions
- final acceptance

Prefer GPT-5.6 Sol with `xhigh` reasoning when configurable. If the active model or reasoning level cannot be verified, state the limitation instead of claiming it was changed.

Sol should normally participate only during planning, escalation, and final acceptance.

### Grok

Grok is the implementation worker. It must:

- follow the canonical plan without independently redesigning it
- stay inside the approved scope and preserve unrelated user changes
- run only approved commands
- report changed files, commands, results, warnings, blockers, and deviations
- avoid commits, pushes, deployments, destructive operations, secrets, and unapproved external writes

If the implementation requires new authority or a plan deviation, Grok stops and reports it.

### Luna

Luna is the independent implementation quality gate and routine repair coordinator. Create one independent review agent for this stage.

Prefer GPT-5.6 Luna with `high` reasoning; `medium` is acceptable for a small, low-risk task. Give Luna the canonical plan, repository path, pre-existing status, Grok session ID, log path, approved commands, and actual implementation state. Do not give it an intended verdict.

Luna may:

- inspect the actual diff and changed files
- compare the implementation with the canonical plan, scope, and acceptance criteria
- inspect or rerun approved tests
- identify implementation defects with evidence
- create a focused repair packet
- resume the same Grok session for repair
- review the repaired result

Luna may not:

- change architecture, the canonical plan, scope, or acceptance criteria
- authorize new commands, dependencies, secrets, commits, pushes, deployments, destructive operations, or external writes
- implement the fix directly

Luna's status line must be exactly one of:

```text
PASS CANDIDATE
REPAIR REQUIRED
ESCALATE TO SOL
```

It should follow the status with concise evidence, checks performed, and any remaining risk. Only Sol may give final acceptance.

If an independent Luna agent cannot be created or its model cannot be selected, disclose the fallback and have Sol perform the same evidence-based review. Never claim that Luna reviewed the work when it did not.

## Preconditions

Before implementation:

1. Read the active repository instructions.
2. Record `git status --short` and preserve unrelated existing changes.
3. Verify `grok --no-auto-update models` reports an authenticated local session and `grok inspect` succeeds in the target repository.
4. Produce a concrete plan containing:
   - objective
   - implementation approach
   - allowed files and operations
   - forbidden files and operations
   - acceptance criteria
   - approved test and build commands
   - major risks
5. Obtain user approval before invoking Grok. A clear request to execute an already-presented plan counts as approval.

Never put secrets, credentials, or unnecessary private data in Grok or Luna task packets.

## Grok Handoff

After approval, create a temporary task packet outside the repository:

```markdown
# Approved implementation task

## Objective
## Canonical plan
## Allowed files and operations
## Forbidden files and operations
## Acceptance criteria
## Approved test and build commands
## Required final report
```

Tell Grok to implement exactly within this authority and report any required deviation instead of performing it.

Invoke [scripts/invoke-grok.ps1](scripts/invoke-grok.ps1). Its default `dontAsk` mode silently denies unapproved tools. Pass each approved shell command as an additional `-AllowRule`; reads, searches, edits, `git status`, and `git diff` are allowed by default.

New implementation run:

```powershell
$grokSkillDir = if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
  Join-Path $env:USERPROFILE '.codex\skills\codex-grok-builder'
} else {
  Join-Path $env:CODEX_HOME 'skills\codex-grok-builder'
}
& (Join-Path $grokSkillDir 'scripts\invoke-grok.ps1') `
  -ProjectPath 'C:\path\to\repo' `
  -TaskFile 'C:\path\to\approved-task.md' `
  -AllowRule @('Bash(npm.cmd test*)', 'Bash(npm.cmd run build*)')
```

Capture the printed Grok session ID and log path. Grok's completion claim and reported test output are evidence, not acceptance.

Use `-AlwaysApprove` only after the user explicitly authorizes unrestricted Grok tool execution for that run. Deny rules remain active, but this mode is materially riskier.

## Luna Review and Repair Loop

After Grok finishes, Luna independently checks:

- actual repository status, diff, and changed files
- compliance with the canonical plan and allowed scope
- acceptance criteria and incomplete behavior
- regressions and sensitive-pattern risks
- approved test and build results
- unauthorized operations or changes

If the implementation is correct, Luna returns `PASS CANDIDATE`.

If a defect can be repaired within existing authority, Luna returns `REPAIR REQUIRED`, creates a temporary repair packet outside the repository containing only the following, and resumes the same Grok session:

```markdown
# Approved repair task

## Observed problem
## Evidence
## Required fix
## Allowed scope
## Acceptance condition
## Approved commands
```

Repair run:

```powershell
$grokSkillDir = if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
  Join-Path $env:USERPROFILE '.codex\skills\codex-grok-builder'
} else {
  Join-Path $env:CODEX_HOME 'skills\codex-grok-builder'
}
& (Join-Path $grokSkillDir 'scripts\invoke-grok.ps1') `
  -ProjectPath 'C:\path\to\repo' `
  -TaskFile 'C:\path\to\repair-task.md' `
  -ResumeSessionId '<session-uuid>' `
  -AllowRule @('Bash(npm.cmd test*)', 'Bash(npm.cmd run build*)')
```

Luna may coordinate at most two Grok repair cycles under the original authority. It must re-inspect the actual result after each repair and must not accept Grok's report on trust.

## Escalation

Luna immediately returns `ESCALATE TO SOL` when:

- architecture or the canonical plan must change
- scope or acceptance criteria must expand
- forbidden files must change
- new dependencies or commands need approval
- secrets or credentials are required
- a commit, push, deployment, destructive action, or unapproved external write is required
- the same blocker occurs twice
- two Luna repair cycles fail

Include the evidence, attempted repairs, and exact authority or decision needed.

## Sol Final Acceptance

After Luna reports `PASS CANDIDATE`, Sol performs one final risk-based review. Inspect:

- the original objective and canonical plan
- acceptance criteria
- final repository status and diff summary
- Luna findings and remaining risks
- architecture-sensitive or high-risk changes
- previously failed areas
- key test and build results

Sol independently reruns the most important approved tests. Do not mechanically reread large low-risk diffs already reviewed by Luna unless evidence suggests a problem.

Final status must be one of:

```text
ACCEPTED
REPAIR REQUIRED
BLOCKED
```

Accept only when the final diff stays within scope, preserves unrelated changes, passes the relevant independently rerun checks, and satisfies the acceptance criteria. Report every skipped or unverified check.

## Core Rule

Sol decides what to build. Grok builds it. Luna handles routine review and repair. Sol performs final acceptance once.
