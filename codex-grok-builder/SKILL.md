---
name: codex-grok-builder
description: "Use the authenticated Grok Build CLI for coding when the user asks 用 Grok 执行、用 Grok 去做、让 Grok 写代码 or equivalent. Codex makes a proportionate plan and verifies the result while controlling handoff and repair costs. Quoted discussion or skill maintenance is not authorization to run Grok; browser-only Grok work uses browser tools."
metadata:
  short-description: Codex plans and verifies; Grok implements
---

# Codex → Grok Builder

Use the smallest sufficient handoff. Optimize the cost of a correctly completed task, including planning, context transfer, execution, repair, verification, and user intervention. The user-approved Codex plan is canonical; Grok implements it and reports assumptions that turn out to be wrong.

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

- Use the model and reasoning effort selected for the current Codex task. Do not require a fixed model or effort as a prerequisite. If the user explicitly requests a setting and it is observable, verify it once; if it cannot be verified, state that limitation without claiming a change and continue independent authorized work. Change model settings only when requested.
- Check `grok --no-auto-update models` for its explicit authentication message and available model IDs; a model list alone is not login evidence. Run `grok --no-auto-update --cwd <project> inspect` once for the target and review effective permission sources without exposing credentials. Recheck only on contradictory evidence or an authentication failure. `inspect` succeeding means configuration was discovered, not that the task's file boundaries are sandbox-enforced.
- Read the active repository instructions and record the pre-existing `git status --short`. Preserve unrelated user changes.
- Obtain approval for the plan, mutation scope, and test commands before invoking Grok. A message that clearly asks to execute an already-presented plan counts as approval.
- Never put API keys, tokens, passwords, or private data in the handoff prompt.

## Cost-aware planning

- Distinguish total tokens, expensive-model usage, plan allowance, and monetary cost. A cheaper worker can reduce weighted cost while increasing total tokens. Without a matched strong-model-only baseline that also counts coordination and verification, do not claim proven savings or a percentage reduction.
- When routing is open, delegate only if there is enough independent implementation work to outweigh handoff and verification. A tiny fix already understood in the current context is often better completed directly. Preserve an explicit Grok choice; don't turn the cost heuristic into another approval step or silently replace the requested executor.
- For a localized change with a known cause, write a short objective, exact edit scope, acceptance examples, and relevant command. Do not run a second architecture exercise or ask Grok to rediscover the repository.
- When a decision is unresolved, have Codex resolve the specific uncertainty before handoff. Give Grok decisive excerpts and locations, not the entire conversation. Do not make both models independently explore the same files.
- Select only a model ID actually listed by the installed CLI. Respect an explicit user model choice. Grok's subscription, default model, and billing are separate from OpenAI's; do not assume Grok is always cheaper or free.
- Set `-MaxTurns` proportionately: a bounded single-function task can start with 12; a larger approved implementation may need more. These are starting budgets, not measured optima. Reaching the limit requires diagnosis, not an automatic fresh session or wider permissions.
- In a direct “use Grok” request, preserve that implementer. If evidence shows a different route would avoid repeated failure, explain the reason and request only the implementer change that lacks authorization. Do not silently move implementation to Codex.

Once Codex can state the objective, boundaries, decisive evidence and acceptance, stop pre-reading and hand off the remaining bounded discovery/implementation. Bundle related steps into one packet. Do not first solve the full implementation and then have Grok repeat it, or inspect every worker tool call. Use completion/blocker events and compact evidence; repeated micromanagement is a sign that this split is not paying off.

## Workflow

1. Codex inspects the relevant repository state and produces a concrete plan containing the objective, file scope, forbidden scope, necessary implementation decisions, acceptance criteria, and test commands. Include concrete risks only where observed. Reuse a plan and its approval when they are already present in the task.
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
3. Invoke [scripts/invoke-grok.ps1](scripts/invoke-grok.ps1). Its default `dontAsk` mode does not ask interactively and denies tools not allowed by the effective rules. Local/global configuration can contribute rules; the task packet is not a hard filesystem sandbox. Pass approved commands with narrowly matching `-AllowRule` values; never infer broader shell authorization from a task goal. The wrapper permits read/search/edit and `git status`/`git diff` by default. Do not change global permissions or use a bypass to cure an execution failure.
4. Prefer `-Quiet`: full stdout still goes to the run log, but token-by-token thought events and repeated tool catalogs do not flood the main agent's context. Capture session ID, independent run ID, stdout/stderr paths, and summary path. Read only relevant completion, tool-result, usage or error events when diagnosing. Neither a zero process exit nor Grok's own completion claim proves the task passed.
5. Codex independently reviews the actual diff against the approved packet, checks for scope expansion, and reruns the relevant approved tests/build once. Do not repeat unrelated suites or reopen accepted work without new evidence. Record skipped or unavailable checks distinctly from failures.
6. If acceptance fails, classify the cause before retrying: permission, environment, ambiguous packet, design error, or implementation error. Only a concrete implementation repair goes straight back to Grok. Create a focused evidence packet and resume the same session with `-ResumeSessionId`; recheck the affected behavior. Authentication and permission failures are not reasons to spend another model run on the same task unchanged.
7. Stop further Grok repair calls after two repair cycles or after the same blocker recurs twice. Complete read-only diagnosis within the existing authorization, then report the root cause or remaining uncertainty, evidence, and a concrete next step. Do not reset the counter, start another session to evade the limit, or switch implementers without the required approval. If a step needs new authority, broader scope, secrets, deployment, push, or destructive operations, pause that step and continue independent authorized work; request only the missing approval after making the proposed action reviewable.

## Invocation

New implementation run:

```powershell
& "$env:USERPROFILE\.codex\skills\codex-grok-builder\scripts\invoke-grok.ps1" `
  -ProjectPath 'C:\path\to\repo' `
  -TaskFile 'C:\path\to\approved-task.md' `
  -MaxTurns 12 -Quiet `
  -AllowRule @('Bash(npm.cmd test)', 'Bash(npm.cmd run build)')
```

Repair run in the same Grok session:

```powershell
& "$env:USERPROFILE\.codex\skills\codex-grok-builder\scripts\invoke-grok.ps1" `
  -ProjectPath 'C:\path\to\repo' `
  -TaskFile 'C:\path\to\repair-task.md' `
  -ResumeSessionId '<session-uuid>' `
  -MaxTurns 12 -Quiet `
  -AllowRule @('Bash(npm.cmd test)', 'Bash(npm.cmd run build)')
```

`-DryRun` validates inputs and displays the planned arguments and output paths without invoking Grok or creating the output directory. Resume accepts the session reference supported by the installed CLI; prefer the exact session UUID to an ambiguous title. Each invocation gets a unique filename-safe run ID.

Use `-AlwaysApprove` only after the user separately and explicitly authorizes unrestricted Grok tool execution for that run. The wrapper still sends deny arguments, but do not claim their precedence over this mode without verifying the installed CLI behavior. Never persist always-yes or bypass settings globally.

The `.run.json` summary records requested model, time, exit status and log paths. Requested model is not independent proof of the resolved backend model. When the CLI provides a valid final `end` event, the wrapper records its usage, reported cost and model-usage identities separately; unavailable data stays unknown. Do not sum per-turn usage on top of the final totals or equate the CLI's cost with subscription deductions. `-Quiet` reduces the stream returned to the coordinator, not Grok's own generated tokens. Compare routes using the same task and acceptance criteria, count coordination, repairs and verification, and label small samples as probes rather than a universal cost ranking.

## Acceptance contract

Accept only when all applicable conditions hold:

- The diff stays inside the approved scope and preserves pre-existing unrelated changes.
- No secret, commit, push, deployment, destructive cleanup, or external write occurred without explicit authorization.
- Relevant tests and build commands pass when rerun by Codex.
- The implementation matches the acceptance criteria, not merely the task wording.
- Any unverified behavior, warning, or skipped check is clearly reported.
