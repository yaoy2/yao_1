---
name: gpt-planner-luna-executor
description: "Orchestrate a bounded Sol → Luna → ChatGPT Web workflow when the user explicitly says 让 GPT 去做, 让gpt去做, or clearly asks ChatGPT to plan/review while Luna performs local exploration and execution. Do not trigger for quoted discussion, ordinary Codex-only work, or requests that do not authorize ChatGPT Web use."
metadata:
  short-description: "Sol 定向，ChatGPT 规划审查，Luna 本地执行"
---

# GPT Planner → Luna Executor

Use a thin Sol main task to orient and route the work, one explicitly selected Luna subagent to collect local evidence and execute, and one ChatGPT Web conversation to plan and review.

The canonical flow is:

```text
RECEIVED      Sol understands the request and authority
→ ORIENTING   Sol performs small, strategic local orientation
→ DISCOVERING Luna collects targeted local evidence
→ PLANNING    ChatGPT Web produces the implementation plan
→ APPROVAL    The user approves before local mutation
→ EXECUTING   The same Luna implements and tests
→ REVIEWING   ChatGPT Web reviews the actual result
→ ACCEPTING   Sol performs one final evidence check
→ ACCEPTED / BLOCKED / CANCELLED
```

Read [references/packet-protocol.md](references/packet-protocol.md) before creating the first task packet.

## Trigger and authority

Trigger only when the user clearly authorizes this workflow, including semantic variants of:

- `让 GPT 去做`
- `让gpt去做`
- `交给 GPT 规划，Luna 执行`
- `让 ChatGPT 分析后由 Luna 修改`

Quoted wording, design discussion, or asking how the workflow works is not execution authorization.

Invocation authorizes read-only orientation, creation of one Luna subagent, and sending a minimal redacted packet to ChatGPT Web. It does not by itself authorize local writes, dependency installation, configuration changes, commits, pushes, deployments, destructive actions, credentials, or disclosure of sensitive content. Follow the target repository's instructions and obtain the user's approval for the proposed implementation before mutation.

## Fixed roles

### Sol main task: strategist and orchestrator

Sol owns:

- understanding the user's actual goal and important ambiguity
- reading the active repository instructions and initial worktree status
- strategic orientation of the project
- deciding what Luna must investigate
- constructing and routing packets
- protecting scope and approval boundaries
- one final local acceptance check

Sol does not perform broad code archaeology, routine implementation, repeated code review, or ordinary repair loops.

### Luna subagent: delegated explorer and executor

Create exactly one subagent with an explicit model override. In the current Codex environment, call `multi_agent_v1__spawn_agent` and pass these exact request fields rather than merely describing them in the prompt:

```text
model: gpt-5.6-luna
reasoning_effort: medium
fork_context: false
```

`reasoning_effort` is the subagent field. Do not replace it with the `thinking` field used by the separate new-task interface. If the available subagent tool schema changes, inspect that schema and proceed only when an equivalent explicit model override, reasoning-effort field, and context-fork control can be verified.

Use `high` only when the approved local execution is unusually complex and the quality gain justifies the additional use. Never omit the model override and silently inherit Sol. If Luna cannot be explicitly created, return `BLOCKED`; do not let Sol absorb the full exploration or implementation workload.

Keep the same Luna agent for discovery and execution. Send the approved execution packet to that agent instead of spawning another one.

Luna owns:

- targeted searches, call-chain tracing, and evidence collection
- reading the files assigned by Sol and directly related files discovered from them
- local edits inside the approved scope
- commands, tests, diff inspection, and routine local fixes
- structured discovery and final-review packets

Luna does not define user intent, choose a new architecture, expand scope, grant authority, or replace ChatGPT's planning and review role.

### ChatGPT Web: planner, architect, and reviewer

Use the available Browser control capability and follow its instructions. Use a signed-in `chatgpt.com` conversation dedicated to the current task and normally reuse it for planning and final review.

ChatGPT Web owns:

- complex diagnosis and high-level analysis
- architecture and implementation planning
- comparison of alternatives
- risk and acceptance criteria
- final review of the evidence packet

ChatGPT Web never performs or claims local actions. Do not substitute Sol for ChatGPT Web when the browser is unavailable or authentication is required. Pause and ask the user to restore access. Use another ChatGPT bridge only with the user's approval.

## Phase 1: Sol orientation

Sol first creates the task contract, then performs the smallest useful orientation needed to direct Luna.

Normally inspect only:

- active repository instructions
- initial `git status --short` or equivalent state
- top-level structure and relevant entry points
- targeted search results
- roughly two to five key files tied directly to the request

Stop when Sol can state what is known, what is unknown, what Luna must investigate, and what ChatGPT must decide. Expand beyond this default only when necessary to formulate a reliable discovery assignment, and state why.

Do not ask Luna to `look around` or `understand the whole project`. Give it a bounded discovery assignment with concrete questions, likely files or symbols, required evidence, exclusions, and output fields.

## Phase 2: Luna discovery

Luna performs read-only local discovery and returns evidence marked as:

- `CONFIRMED`
- `INFERRED`
- `UNKNOWN`

Allow at most one focused follow-up discovery assignment to fill a named gap. After that, unresolved ambiguity goes to the user or ChatGPT; Sol does not start an unlimited local exploration loop.

Sol checks the returned packet only for completeness, relevance, scope, and sensitive content. It must not duplicate Luna's searches or independently reread every cited file.

## Phase 3: ChatGPT planning and user approval

Send ChatGPT Web the minimal Context Packet, normally about 1K–3K tokens. Include only the evidence needed for the planning decision. Redact secrets, credentials, personal data, and unrelated proprietary content. If necessary sensitive content cannot be omitted, ask the user before sending it.

Require a structured plan containing the objective, diagnosis or rationale, chosen approach, allowed changes, forbidden changes, implementation sequence, risks, tests, acceptance criteria, and unresolved user decisions.

Present the plan to the user and pause. No local mutation occurs until the user clearly approves this plan. A small user correction can be incorporated once; a material change in goal, architecture, authority, or acceptance requires an updated ChatGPT plan and renewed approval.

## Phase 4: Luna execution

Send the approved execution packet to the same Luna agent. Luna must recheck the actual worktree before editing and stop if new changes materially conflict with the approved plan.

During execution Luna:

- changes only approved files and operations
- preserves unrelated user work
- runs approved tests and checks the actual diff
- handles syntax errors and narrow implementation repairs itself
- stops for architecture, scope, authority, dependency, credential, destructive, deployment, or material-environment conflicts

Routine edits, syntax corrections, and command retries inside one continuous execution run are not separate review cycles. If Luna reaches a repeated core test or implementation failure, allow one focused local repair cycle. If the same core failure remains after that repair, return `BLOCKED` before final review. Sol performs zero routine code reviews during this phase.

## Phase 5: ChatGPT final review

Luna produces the Final Review Packet. Sol checks only packet completeness and redaction, then sends it to the existing ChatGPT Web conversation with the approved plan and only the necessary diff evidence.

ChatGPT must return exactly one leading verdict:

```text
PASS
FIX
REPLAN
```

- `PASS`: proceed to Sol final acceptance.
- `FIX`: require a finite evidence-backed repair list. Send it directly to Luna. Permit one reviewer-directed Luna repair cycle and at most one ChatGPT re-review.
- `REPLAN`: stop implementation, explain the design conflict to the user, and require a newly approved plan.

If the allowed re-review is still `FIX` or `REPLAN`, return `BLOCKED`. Across the whole task, allow at most two cross-stage repair cycles: one execution-stage local repair and one ChatGPT-directed repair. Do not create a ChatGPT → Luna → ChatGPT loop.

## Sol review budget

On the normal path Sol may perform:

```text
strategic orientation: 1
execution-stage code reviews: 0
final local acceptance checks: 1
```

Sol must not:

- reread Luna's entire discovery set
- review every Luna edit, test, or repair
- duplicate ChatGPT's architecture analysis
- request optional refactors after the approved scope is satisfied
- reopen resolved decisions without new contradictory evidence

An architecture, authority, security, or material environment conflict may cause one focused Sol escalation. If that does not resolve the blocker, stop and report it.

## Final acceptance and delivery

After ChatGPT returns `PASS`, Sol performs one risk-based local check of:

- actual changed files and final worktree status
- compliance with approved scope
- preservation of unrelated changes
- key test results and exit status
- secrets or sensitive-pattern risks
- disclosed deviations and residual risks

If local evidence contradicts the ChatGPT verdict, return `BLOCKED`; do not start another automatic repair loop.

Final status is exactly one of:

```text
ACCEPTED
BLOCKED
CANCELLED
```

Commits, pushes, deployments, and other delivery actions follow the active repository rules and the user's actual authorization. Close the Luna agent when the task ends. Report skipped and unverified checks.
