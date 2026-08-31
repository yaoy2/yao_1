# Packet Protocol

Use these schemas to keep handoffs compact, traceable, and non-duplicative. Omit sections that genuinely do not apply; never invent evidence to fill a field.

## 1. Sol Task Contract

```markdown
# Task Contract

## Mode
query | diagnose | plan | change

## User goal

## In scope

## Out of scope

## Allowed reads

## Potential writes

## Approval required

## Acceptance criteria

## Constraints

## Documentation impact

## Important ambiguity
```

Only the user resolves ambiguity about their desired outcome. ChatGPT may compare options but cannot grant permission or choose a preference that materially changes the user's request.

## 2. Luna Discovery Assignment

```markdown
# Luna Discovery Assignment

## Objective
Collect the local facts needed to plan this task. Do not modify files.

## Questions to answer

## Likely files, symbols, or entry points

## Required evidence
- file path and location
- observed behavior
- relevant error or test result
- confidence: CONFIRMED | INFERRED | UNKNOWN

## Exclusions

## Stop condition
Stop when every question is answered or explicitly marked UNKNOWN.

## Required output
Return the Discovery Packet schema below.
```

## 3. Luna Discovery Packet

```markdown
# Discovery Packet

## Project state

## Initial worktree state

## Confirmed facts

## Inferences

## Unknowns

## Relevant files

## Call paths or data flow

## Existing tests and commands

## Errors and prior attempts

## Risks observed

## Questions still requiring judgment

## Sensitive-content check
CLEAR | REDACTION REQUIRED | USER APPROVAL REQUIRED
```

Evidence must distinguish observed repository facts from conclusions. Large logs and full files are not packet content; cite locations and include only the decisive excerpt.

## 4. ChatGPT Context Packet

Target about 1K–3K tokens when practical.

```markdown
# Context Packet for Planning

## User's actual goal

## Task contract

## Sol orientation

## Luna-confirmed local facts

## Relevant files and minimal excerpts

## Errors or failed attempts

## Unknowns

## Decision requested from ChatGPT

## Constraints and forbidden actions

## Required plan format
1. Task understanding
2. Recommended approach and rationale
3. Files and change scope
4. Ordered implementation steps
5. Risks and mitigations
6. Test plan
7. Acceptance criteria
8. User decisions still required
```

ChatGPT must not claim to inspect, edit, run, test, or verify the local project.

## 5. Approved Execution Packet

Create this only after user approval.

```markdown
# Approved Execution Packet

## Approved objective

## Approved plan

## Allowed files and operations

## Forbidden files and operations

## Approved commands

## Acceptance criteria

## Required stop and escalation conditions

## Required final report
Use the Final Review Packet schema.
```

If the current worktree materially differs from the discovery state, Luna stops before editing and reports the conflict.

## 6. Final Review Packet

```markdown
# Final Review Packet

## Actual completed work

## Changed files

## Key diff summary

## Commands executed

## Tests and exit status

## Deviations from the approved plan

## Unverified or skipped checks

## Remaining risks

## Unrelated work preserved

## Sensitive-pattern check

## Luna status
READY | BLOCKED
```

Include exact test outcomes and concise evidence. A report that says only `tests passed` is insufficient.

## 7. ChatGPT Review Request and Verdict

```markdown
# Final Review Request

Review the implementation evidence against the approved objective, scope, risks, and acceptance criteria. Do not assume unreported local facts.

Return exactly one leading verdict:

PASS
FIX
REPLAN

Then provide:
- evidence considered
- blocking findings
- non-blocking residual risks
- explicit repair items when verdict is FIX
- the invalidated assumption when verdict is REPLAN
```

`FIX` items must be finite, local, evidence-backed, and within existing authority. Otherwise the correct verdict is `REPLAN`.

## 8. Luna Fix Packet

```markdown
# Approved Fix Packet

## Reviewer verdict
FIX

## Observed problem and evidence

## Required correction

## Allowed scope

## Commands to rerun

## Acceptance condition

## Stop condition
Stop if the fix requires architecture, authority, dependency, credential, or scope changes.
```

Allow one ChatGPT-directed Luna repair cycle. This is the second and final cross-stage repair cycle permitted for the task; the first is the single focused local repair allowed for a repeated core execution failure. Routine edits inside one continuous execution run are not separate repair cycles. After the one permitted re-review, any remaining `FIX` or `REPLAN` becomes `BLOCKED`.

## 9. Sol Final Acceptance

```markdown
# Sol Final Acceptance

## ChatGPT verdict
PASS

## Scope check

## Worktree and changed-file check

## Key test evidence

## Unrelated-change preservation

## Sensitive-pattern check

## Deviations and residual risk

## Final status
ACCEPTED | BLOCKED | CANCELLED
```

Sol performs this acceptance once. Contradictory local evidence produces `BLOCKED`, not another automatic review or repair cycle.
