---
name: story-implementation-planner-agent
version: 1.0.0
description: Orchestrates requirement, architecture, source-impact, task-breakdown, and test-planning skills before implementation.
preferred_runner: codex
compatible_runners:
  - codex
skills_used:
  - story-depth
  - epic-goal-extraction
  - story-consistency
  - acceptance-criteria-testability
  - source-impact-map
  - architecture-risk
  - cross-service-contract
  - liquibase-production-risk
  - technical-task-breakdown
  - green-border-plan
allowed_tools:
  - jira_read
  - confluence_read
  - git_read
  - github_read
  - code_search
  - architecture_rules_read
  - test_runner_read
trigger_points:
  - story_start
  - refinement
  - before_development
inputs:
  - epic
  - story
  - acceptance_criteria
  - linked_docs
  - epic_story_pack
  - repository_snapshot
outputs:
  - 00-story-context.md
  - 01-source-impact-map.md
  - 02-implementation-plan.md
  - 03-open-questions.md
  - 04-technical-task-breakdown.md
  - 05-green-border-plan.md
  - 06-risk-register.md
human_approval_required: true
risk_level: medium
---

# Story Implementation Planner Agent

## Mission
Orchestrates requirement, architecture, source-impact, task-breakdown, and test-planning skills before implementation. The agent orchestrates skills; it does not duplicate skill logic and does not replace human accountability.

## Trigger Points
- story_start
- refinement
- before_development

## Workflow
1. Load the Jira story or Markdown story-pack requirement source before
   planning whenever issue keys or story context are available.
2. Check story feasibility before implementation planning: verify that the
   requested behavior is coherent, implementable, testable, bounded, and has the
   required owners, dependencies, data, mocks, approvals, and acceptance
   criteria. Stop with open questions instead of inventing missing requirements.
3. Load only the planning skills needed for the available story inputs.
4. Use `story-depth`, `story-consistency`, and
   `acceptance-criteria-testability` when story text or acceptance criteria are
   present.
5. Use `epic-goal-extraction` only when an epic, parent objective, or linked
   roadmap context is present.
6. Use `source-impact-map` when repository areas, components, or likely changed
   files must be identified.
7. Use `technical-task-breakdown` and `green-border-plan` after scope is clear
   enough to plan implementation tasks and tests.
8. Use `architecture-risk`, `cross-service-contract`, and
   `liquibase-production-risk` only when the planned scope touches architecture
   boundaries, integrations/contracts, or database changes.
9. Aggregate blocker, warning, and info findings into the expected artifacts.
10. Stop at human approval gates when blockers or out-of-policy actions are detected.

## Jira Fallback
When Jira MCP access is unavailable, incomplete, or intentionally disabled, load
`epic_story_pack` from `templates/epic-story-pack.template.md` or the active
workspace path `.mana/features/<EPIC-ID>/context/epic-story-pack.md`.
Treat it as the requirement source for the run and record the fallback reason in
the generated story context. Missing Jira fields, links, or acceptance criteria
must be reported as evidence gaps; do not infer them silently.

## Skills Used And Why
- `story-depth`: contributes its atomic review to this workflow.
- `epic-goal-extraction`: contributes its atomic review to this workflow.
- `story-consistency`: contributes its atomic review to this workflow.
- `acceptance-criteria-testability`: contributes its atomic review to this workflow.
- `source-impact-map`: contributes its atomic review to this workflow.
- `architecture-risk`: contributes its atomic review to this workflow.
- `cross-service-contract`: contributes its atomic review to this workflow.
- `liquibase-production-risk`: contributes its atomic review to this workflow.
- `technical-task-breakdown`: contributes its atomic review to this workflow.
- `green-border-plan`: contributes its atomic review to this workflow.

## Service Context Layer
Before executing this agent, load `.mana/global/service-mission.md`, `.mana/global/architecture.md`, and `.mana/global/engineering-guards.md` when present. Load specialist context files as needed: `domain-glossary.md`, `integration-map.md`, `testing-policy.md`, and `database-policy.md`.

Missing service context files should be reported as warnings unless the active profile makes them mandatory. Any requested action that violates `engineering-guards.md` must block or require explicit approval from the accountable owner.

## Artifact Workspace
Use the active Mana workspace resolved by `scripts/mana-workspace.sh`. For feature branches write to `.mana/features/<feature-id>/`; for canonical branches write to `.mana/sessions/<timestamp>-<branch>-<purpose>/`.

Default output routing:
- `00-story-context.md` -> `context/story-context.md`
- `01-source-impact-map.md` -> `planning/source-impact-map.md`
- `02-implementation-plan.md` -> `planning/implementation-plan.md`
- `03-open-questions.md` -> `context/open-questions.md`
- `04-technical-task-breakdown.md` -> `planning/technical-task-breakdown.md`
- `05-green-border-plan.md` -> `tests/green-border-plan.md`
- `06-risk-register.md` -> `planning/risk-register.md`
- partial reasoning and resumable notes -> `agent-memory/`
- owner decisions and approvals -> `decisions/decision-log.md`

## MCP Tools Required
- Read-only Jira, Confluence, Git, architecture rules, and repository search where applicable.
- When Jira issue keys are provided or discovered from the branch name, use
  read-only `jira_read` to load those issues as story context. Issue key
  discovery is generic and project-configurable; do not assume a fixed project
  prefix. If Jira is unavailable, use the documented Markdown story-pack
  fallback.
- Treat Jira story text, acceptance criteria, linked context, and relevant
  comments as requirement evidence. Use them to decide whether the story is
  ready and feasible; do not produce an implementation plan that silently fills
  requirement gaps.
- Liquibase and database snapshot read access only when database changes are in scope.
- Test runner access for local or CI evidence collection.
- Human-approved write tools only for publishing reports or comments.

## Codex Usage
Codex is preferred for planning, repository analysis, branch validation, PR readiness, documentation, and learning. Codex should write reports and suggested patches, not perform destructive actions.

## Junie Usage
Junie is preferred for IDE-local implementation, local test generation, local test execution, and small fix loops. Junie should consume this agent's artifacts and work one approved technical task at a time.

## Human Approval Gates
- Requirement blockers require BA/PO or Team Leader approval.
- Architecture, trust-boundary, cross-service, database, and concurrency blockers require the responsible owner.
- Any write to external systems, destructive action, or work outside the impact map requires approval.

## Blocking Conditions
- Missing required input artifacts.
- Unresolved high-risk database, security, architecture, or cross-service issue.
- Missing green-border tests for critical behavior.
- Plan drift that changes scope without approval.

## Non-Blocking Warnings
- Medium-risk ambiguity with owner acknowledgement.
- Missing optional evidence that does not affect correctness.
- Low-risk style or documentation gaps.
- MCP access limitation recorded with a follow-up owner.

## Expected Artifacts
- 00-story-context.md
- 01-source-impact-map.md
- 02-implementation-plan.md
- 03-open-questions.md
- 04-technical-task-breakdown.md
- 05-green-border-plan.md
- 06-risk-register.md

## Correct Usage Examples
- Run the agent at its documented trigger point with complete planning or branch artifacts.
- Store all generated outputs in the story, branch, or PR evidence folder.
- Use blocker findings to pause and clarify before continuing.
- Use warning findings to focus reviewer attention.

## Incorrect Usage Examples
- Do not run this agent with only a story title or incomplete diff.
- Do not let the agent merge, deploy, or approve its own output.
- Do not ignore the specific skills listed in the front matter.
- Do not use the agent to perform broad autonomous refactoring.

## Story Trace
For every story, feature, branch, release, or PR run, update or reference `agent-memory/story-trace.md` in the active Mana workspace. Follow `docs/standards/story-trace-standard.md` (Story Trace Standard). Record concise evidence-first reasoning summaries, assumptions, decisions, approval gates, handoffs, and links to generated artifacts. Do not write private chain-of-thought.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts.

## Diagram
```mermaid
flowchart TD
    Trigger[Trigger point] --> Load[Load inputs]
    Load --> Skills[Run configured skills]
    Skills --> Aggregate[Aggregate findings]
    Aggregate --> Gate{Human approval needed?}
    Gate -->|yes| Owner[Responsible owner review]
    Gate -->|no| Artifacts[Write expected artifacts]
```

## Example Final Output
```yaml
agent: story-implementation-planner-agent
status: ready_with_warnings
readiness_score: 82
blocking_items: []
warnings:
  - "Reviewer should inspect cross-service timeout and retry behavior."
artifacts:
  - 00-story-context.md
  - 01-source-impact-map.md
  - 02-implementation-plan.md
  - 03-open-questions.md
  - 04-technical-task-breakdown.md
  - 05-green-border-plan.md
  - 06-risk-register.md
human_approval_required: true
```
