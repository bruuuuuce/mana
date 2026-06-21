# Mana Workspace

The Mana workspace is the project-local evidence store used by this framework. Each application repository that adopts the framework should create a dedicated `.mana/` directory at repository root. Agents and skills write Markdown artifacts, partial memories, decisions, validation reports, and handoff material into that directory.

The workspace is not a replacement for Git, Jira, Confluence, CI, or code review. It is a structured local trace that makes AI-assisted delivery reproducible and auditable.

## Goals
- Keep all story, branch, and session artifacts in one predictable location.
- Preserve partial agent memory without mixing it with source code.
- Separate feature work from canonical branch sessions.
- Make Codex and Junie handoff explicit.
- Support PR readiness, branch validation, and post-merge learning with stable inputs.

## Top-Level Layout
```text
.mana/
  features/
    PROJ-24342/
  sessions/
    2026-05-30T101500Z-main-repo-audit/
  global/
    service-mission.md
    architecture.md
    engineering-guards.md
    domain-glossary.md
    integration-map.md
    testing-policy.md
    database-policy.md
    rules/
    known-pitfalls/
    team-decisions/
```

## Service Context Layer
`.mana/global/` contains stable service guidance used by all agents and skills. These files keep the system aligned with the service purpose, architecture and non-negotiable engineering constraints.

Core files:

- `service-mission.md`: what the service does, why it exists, owners, responsibilities, non-goals and architecture position.
- `architecture.md`: components, runtime flows, data ownership, dependencies, boundaries and approved patterns.
- `engineering-guards.md`: absolute constraints, forbidden actions, protected areas and approval gates.

Specialist files:

- `domain-glossary.md`
- `integration-map.md`
- `testing-policy.md`
- `database-policy.md`

Agents should load the core files when present. Missing files produce warnings, not blockers, unless a profile explicitly requires them. Violations of `engineering-guards.md` are blockers or require explicit owner approval.

## Feature Workspaces
Feature branches should create a workspace under `.mana/features/<feature-id>/`.

Example:

```text
branch: PROJ-24342 payment-refactoring
workspace: .mana/features/PROJ-24342/
```

Feature id resolution:

1. If `--feature` is provided, use it.
2. Else if the branch contains a ticket pattern like `PROJ-24342`, use that ticket id.
3. Else if a story id is provided by a profile or agent, use the story id.
4. Else slugify the branch name.
5. Else create a timestamped manual workspace.

## Canonical Branch Sessions
Canonical branches do not represent a single feature. The workspace key must therefore be the purpose of the session, not the branch name.

Canonical branches include:

- `main`
- `master`
- `develop`
- `dev`
- `release/*`
- `hotfix/*`

Examples:

```text
.mana/sessions/2026-05-30T101500Z-main-repo-audit/
.mana/sessions/2026-05-30T103200Z-develop-release-readiness/
.mana/sessions/2026-05-30T110000Z-main-post-merge-learning/
```

If the current branch is canonical and no feature id is provided, the framework must create a session workspace. The session must record a `purpose`, such as:

- `repo-audit`
- `release-readiness`
- `post-merge-learning`
- `architecture-review`
- `incident-analysis`
- `dependency-review`

## Workspace Contents
Each feature or session workspace should use this internal layout:

```text
<workspace>/
  manifest.yaml
  index.md
  context/
    story-context.md
    epic-goal-contract.md
    open-questions.md
  planning/
    source-impact-map.md
    implementation-plan.md
    technical-task-breakdown.md
    risk-register.md
  agent-memory/
    story-trace.md
    partial-findings.md
    story-implementation-planner-notes.md
    branch-validation-notes.md
  skill-outputs/
    story-depth-report.md
    architecture-risk-report.md
    liquibase-risk-report.md
    pre-review-defect-report.md
  decisions/
    decision-log.md
    developer-choice-log.md
    clarification-log.md
    architecture-decisions.md
  tests/
    green-border-plan.md
    green-border-report.md
    test-gap-report.md
    test-evidence.md
    regression-selection.md
  validation/
    branch-validation-report.md
    plan-drift-report.md
    missing-tests-report.md
    risk-status-report.md
    developer-decision-review.md
  pr/
    pr-description.md
    reviewer-focus.md
    risk-report.md
    development-summary.md
    developer-handoff.md
    developer-decision-review.md
  learning/
    known-pitfalls.md
    incident-learning-report.md
    rule-update-suggestions.md
```

## Manifest
Every workspace must include a `manifest.yaml`.

Feature example:

```yaml
workspace_type: feature
workspace_id: PROJ-24342
branch: "PROJ-24342 payment-refactoring"
feature_id: PROJ-24342
purpose: story-delivery
created_at: 2026-05-30T10:15:00Z
canonical_branch: false
```

Canonical session example:

```yaml
workspace_type: session
workspace_id: 2026-05-30T101500Z-main-repo-audit
branch: main
feature_id: null
purpose: repo-audit
created_at: 2026-05-30T10:15:00Z
canonical_branch: true
```

## Agent Output Routing
Agents should write outputs into the workspace as follows:

| Agent | Default workspace location |
|---|---|
| Story Implementation Planner | `context/`, `planning/`, `skill-outputs/`, `decisions/` |
| Green Border Test Agent | `tests/`, `skill-outputs/`, `agent-memory/` |
| Git Hook Agent | `agent-memory/`, optional `tests/hook-report.md` |
| Liquibase Agent | `skill-outputs/`, `validation/` |
| Branch Validation Agent | `validation/`, `agent-memory/` |
| PR Readiness Agent | `pr/`, `validation/` |
| Learning Agent | `learning/`, `global/known-pitfalls/` when approved |

Every agent that runs against a Jira story, feature branch, release, or PR must
update or reference `agent-memory/story-trace.md` in the active workspace. This
file is the canonical story-specific Markdown trace for concise reasoning
summaries, assumptions, decisions, approvals, and handoffs. It must not contain
private chain-of-thought, secrets, raw production data, or unredacted customer
data. See `docs/standards/story-trace-standard.md`.

Developer-facing interactions that produce implementation choices must update
or reference `decisions/developer-choice-log.md`. This is the canonical log for
questions asked to developers, developer answers, confirmed choices, rejected
alternatives, owner acceptance, and follow-ups. See
`docs/standards/developer-choice-log-standard.md`.

## Codex And Junie Coordination
- Codex reads and writes planning, validation, PR, and learning artifacts in `.mana/`.
- Junie reads `.mana/<workspace>/planning/` and `.mana/<workspace>/tests/` before editing code.
- Junie writes local test evidence and fix-loop notes only inside the active workspace.
- Codex and Junie must not modify the same branch concurrently.
- Any change outside the source impact map must be recorded in `decisions/decision-log.md`.

## Git Policy
Teams may choose whether `.mana/` is committed. Recommended default:

- Commit stable planning, validation, PR, handoff, and learning artifacts when they are useful for review.
- Do not commit transient scratch files, raw logs, secrets, or large test output.
- Add project-specific ignore rules for `agent-memory/` if it contains local-only notes.

## Workspace Resolution And Initialization
The command resolves or creates an evidence workspace. It does not initialize, rename, or modify a Git branch.

Preview the workspace path without creating files:

```sh
scripts/mana-workspace.sh resolve --root /path/to/project --purpose repo-audit
```

Create the workspace and mark it as active:

```sh
scripts/mana-workspace.sh init --root /path/to/project --purpose repo-audit
```

Inspect the active workspace:

```sh
scripts/mana-workspace.sh status --root /path/to/project
```

For a feature branch containing a ticket id, the script creates:

```text
.mana/features/<ticket-id>/
```

For a canonical branch, the script creates:

```text
.mana/sessions/<timestamp>-<branch>-<purpose>/
```

The initializer is idempotent. It creates missing directories and starter files, but it does not overwrite existing manifest, index, decision log, partial findings, or service context files unless `--force` is passed for generated metadata.

`scripts/mana-workspace.sh` is the canonical workspace command. Use `init`, `resolve`, or `status` explicitly.
