---
name: codex-grok-builder
description: "Orchestrate coding tasks where Codex plans and verifies while the locally authenticated Grok Build CLI implements. Trigger whenever the user's directive means 用grok去做, 用 Grok 去做, 让 Grok 做, 交给 Grok 实现, 让 Grok 写代码, or a clear wording variant. Do not trigger for quoted phrases used only to discuss or configure this skill, Codex-only edits, or browser-only Grok work."
metadata:
  short-description: Codex plans and verifies; Grok implements
---

# Codex → Grok Builder

Run a controlled handoff. The user-approved Codex plan is canonical; Grok is the implementation worker, not a second architect.

## Triggering

Invoke this skill whenever the user's direct instruction is semantically equivalent to “用 Grok 去做,” regardless of capitalization, spacing, or minor wording differences. Common examples include:

- `用grok去做`
- `用 Grok 去做`
- `让 Grok 做`
- `这个交给 Grok 实现`
- `让 Grok 写代码`
- `让 Grok 完成操作，你来验收`

The wording does not need to mention Codex's role explicitly; this skill supplies Codex planning and acceptance automatically. A phrase quoted only to edit, document, test, or discuss the skill is not execution authorization.

## Preconditions

- If the app exposes model settings, verify the Codex task is using GPT-5.6 Sol with `xhigh` reasoning. If this cannot be verified, state that limitation; never claim the model was changed.
- Verify `grok --no-auto-update models` reports an authenticated local session and `grok inspect` succeeds in the target repository.
- Read the active repository instructions and record the pre-existing `git status --short`. Preserve unrelated user changes.
- Obtain approval for the plan, mutation scope, and test commands before invoking Grok. A message that clearly asks to execute an already-presented plan counts as approval.
- Never put API keys, tokens, passwords, or private data in the handoff prompt.

## Workflow

1. Codex inspects the repository and produces a concrete plan containing the objective, file scope, forbidden scope, implementation steps, acceptance criteria, test commands, and risks.
2. After approval, Codex writes a temporary task packet outside the repository. Use this structure:

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

   Tell Grok to implement the packet exactly, report any necessary deviation, avoid commits and pushes, and finish with changed files plus test results.
3. Invoke [scripts/invoke-grok.ps1](scripts/invoke-grok.ps1). The default `dontAsk` permission mode silently denies unapproved tools. Pass every approved shell command as an additional `-AllowRule`; file reads, searches, edits, `git status`, and `git diff` are allowed by default.
4. Capture the printed session ID and log path. Do not treat Grok's own completion claim or test output as acceptance.
5. Codex independently reviews the actual diff against the approved packet, checks for scope expansion, and reruns the approved tests/build itself.
6. If acceptance fails, create a focused repair packet with observed evidence and resume the same Grok session with `-ResumeSessionId`. Recheck independently after every repair.
7. Stop after two repair cycles, after the same blocker recurs twice, or when completion needs new authority, a broader scope, secrets, deployment, push, or destructive operations. Report the exact remaining blocker.

## Invocation

New implementation run:

```powershell
& "$env:USERPROFILE\.codex\skills\codex-grok-builder\scripts\invoke-grok.ps1" `
  -ProjectPath 'C:\path\to\repo' `
  -TaskFile 'C:\path\to\approved-task.md' `
  -AllowRule @('Bash(npm.cmd test*)', 'Bash(npm.cmd run build*)')
```

Repair run in the same Grok session:

```powershell
& "$env:USERPROFILE\.codex\skills\codex-grok-builder\scripts\invoke-grok.ps1" `
  -ProjectPath 'C:\path\to\repo' `
  -TaskFile 'C:\path\to\repair-task.md' `
  -ResumeSessionId '<session-uuid>' `
  -AllowRule @('Bash(npm.cmd test*)', 'Bash(npm.cmd run build*)')
```

Use `-AlwaysApprove` only after the user explicitly authorizes unrestricted Grok tool execution for that run. Deny rules remain active, but this mode is still materially riskier.

## Acceptance contract

Accept only when all applicable conditions hold:

- The diff stays inside the approved scope and preserves pre-existing unrelated changes.
- No secret, commit, push, deployment, destructive cleanup, or external write occurred without explicit authorization.
- Relevant tests and build commands pass when rerun by Codex.
- The implementation matches the acceptance criteria, not merely the task wording.
- Any unverified behavior, warning, or skipped check is clearly reported.
