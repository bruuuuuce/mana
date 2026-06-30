# Agent And Skill Output Standard

Mana agents and skills must produce consistent, reviewable artifacts. Internal
working notes must stay short; published output must stay structured.

## Internal Reasoning Mode

Use compact "caveman" working notes while analyzing:

- short fragments, not prose;
- facts, risks, evidence, owner, next action;
- no long narrative;
- no repeated restatement of inputs;
- no hidden approval assumptions;
- no publication of private chain-of-thought.

Do not include internal working notes in final artifacts. Convert them into the
standard sections below.

For story-specific continuity, agents must update or reference the canonical
story trace described in `docs/standards/story-trace-standard.md`:
`agent-memory/story-trace.md` inside the active Mana workspace. This stores
concise evidence-first reasoning summaries and decisions, not private
chain-of-thought.

## Required Output Sections

Every agent or skill output should use these sections in this order unless a
profile explicitly narrows the artifact:

1. `# <Artifact Title>`
2. `## Status`
3. `## Executive Summary`
4. `## Decision Table`
5. `## Findings`
6. `## Evidence`
7. `## Diagram`
8. `## Open Questions`
9. `## Actions`
10. `## Human Approval`

## Status

Use one of:

- `ready`
- `ready_with_warnings`
- `not_ready`
- `blocked`
- `needs_human_decision`

Include owner and timestamp when known.

## Decision Table

Use this Markdown table shape:

| Gate | Status | Owner | Evidence | Action |
|---|---|---|---|---|
| Requirement clarity | warning | Team Leader | AC missing error path | Clarify before implementation |

Gate names should be concrete, for example:

- Requirement clarity
- Architecture
- Service boundary
- Database
- Security
- Test evidence
- Rollback
- Operations
- Review readiness

## Findings

Use this table shape:

| Severity | Area | Finding | Evidence | Owner | Recommended Action |
|---|---|---|---|---|---|
| blocker | rollback | Rollback path is unclear | No rollback note for migration | DBA | Add rollback plan |

Severity values:

- `blocker`
- `warning`
- `info`

## Evidence

Use bullets with concrete references:

- `file/path.ext`: reason it matters.
- `test-name`: result and relevance.
- `JIRA-123`: requirement or decision source.

Avoid vague evidence such as "code seems fine".

### Branch Diff Base Resolution

Any agent or skill that consumes `branch_diff`, `code_diff`, `local_branch_diff`,
or compares a branch against a base must resolve and report the comparison base.
Prefer, in order:

1. An explicit user-provided `base_branch`, `main_branch`, PR target, or release
   branch.
2. The upstream default branch such as `origin/HEAD`.
3. A common primary branch name such as `origin/main`, `origin/master`,
   `main`, `master`, `develop`, or `dev`, only when exactly one candidate is
   credible in the repository.

If the base branch is missing, ambiguous, detached, or not present locally,
stop with `needs_human_decision` and ask which branch to compare against. Do
not silently default to `main`. Every report using branch evidence must name
the base branch and diff form used, for example `git diff origin/main...HEAD`.

### Branch Diff Analysis Budget

Agents and skills using branch or code diff evidence must keep analysis scoped
to changed application behavior.

Default budget rules:

- Start with a diff inventory, for example `git diff --name-status <base>...HEAD`
  plus working-tree status, before reading full file contents.
- Exclude framework/bootstrap noise before estimating scope.
- Classify changed files by risk domain, then read only the files needed to
  validate plausible blocker or warning hypotheses.
- Prefer targeted searches from changed symbols, APIs, tables, events, routes,
  config keys, and tests over repository-wide scans.
- Invoke specialist skills only for risk domains touched by the filtered diff.
- Report no more than the highest-signal findings by default: blocker findings
  first, then warnings with concrete branch evidence. Avoid exhaustive low-risk
  commentary.
- If the filtered diff is too large to review responsibly in one pass, stop with
  `needs_human_decision` and ask the user to choose a scope, for example risky
  modules first, production paths only, or a specific story/PR target.

As a default threshold, treat more than 80 filtered changed files, more than
2,000 filtered changed lines, or generated/vendor-like churn as a scope decision
rather than an invitation to inspect the whole repository. Profiles may define a
stricter budget.

### Skill Loading Budget

Agents should not read every skill listed in a profile before they know the
actual scope. Load the agent `AGENT.md` and `playbook.md`, then load only:

- the primary skill needed to start the workflow;
- specialist skills whose risk domain is touched by the filtered inputs;
- supporting skills required by a confirmed blocker, warning, or output
  contract.

For branch/code diff profiles, classify the filtered diff before loading
specialist skills. For example, load database or rollback skills only after DB
changes are present, and load contract skills only after API, event, message, or
integration changes are present.

### Framework And Bootstrap Noise

Do not use Mana framework/bootstrap files as production-risk findings or main
evidence unless the active profile is explicitly reviewing Mana setup,
runner wiring, workspace bootstrap, or profile selection. Exclude them from
`## Findings`, `## Evidence`, risk tables, missing-test tables, and production
failure hypotheses for normal delivery profiles.

Default excluded paths and files:

- `.mana/**`
- `AGENTS.md`
- `CLAUDE.md`
- `mana`
- project ignore/env bootstrap changes whose only purpose is Mana setup, such
  as `.gitignore` entries for `.mana/` or `.mana/jira-mcp.env`

If these files matter operationally, mention them only in a short operational
note or setup warning, not as application behavior evidence. Placeholder service
context files under `.mana/global/` may be reported as a context-quality warning,
but should not be listed as changed production evidence.

## Diagram

Include Mermaid by default when flow, ownership, dependency, or sequence matters:

```mermaid
flowchart TD
    Input[Input] --> Check[Skill or Agent Check]
    Check --> Gate{Human gate?}
    Gate -->|yes| Owner[Owner decision]
    Gate -->|no| Output[Artifact]
```

Use PlantUML only when the target team already prefers it or the requested
artifact requires PUML:

```plantuml
@startuml
actor Owner
Owner -> Agent: Review evidence
Agent -> Owner: Blockers and actions
@enduml
```

## Open Questions

Use a Markdown table:

| Question | Owner | Required By | Blocks |
|---|---|---|---|
| Which rollback option is approved? | DBA | before release | Database gate |

## Actions

Use a checklist:

- [ ] Owner: action, due point, expected evidence.

## Human Approval

State exactly who must approve what:

- Team Leader: scope, sequencing, story readiness.
- Architect: architecture decisions, NFR trade-offs, service boundary drift.
- Application Manager: release impact, continuity, support, go/no-go readiness.
- DBA/Security/Operations: specialist blockers.

## Style Rules

- Prefer concise bullets over paragraphs.
- Prefer tables for decisions, findings, questions, and actions.
- Use code formatting for file paths, commands, profile names, skills, agents,
  statuses, and IDs.
- Do not invent missing evidence. Mark it as an evidence gap.
- Do not mark human approval as complete unless the input includes explicit approval.
