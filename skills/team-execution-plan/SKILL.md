---
name: team-execution-plan
version: 1.0.0
description: Converts epic and story scope into an execution plan with sequencing, ownership, parallelization, dependencies, and review gates.
compatibility:
  - codex
  - junie
  - claude
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
  - jira_read
  - confluence_read
inputs:
  - epic
  - stories
  - technical_breakdown
  - source_impact_map
  - team_constraints
outputs:
  - team_execution_plan
  - sequencing_recommendation
  - dependency_and_owner_map
risk_level: medium
owner_role: Team Leader
tags:
  - planning
  - team-lead
  - execution
---

# Team Execution Plan

## Purpose
Help a Team Leader turn scope into a practical implementation sequence with owners, parallel work, dependencies, and review gates.

## When To Use It
- During planning for an epic with multiple stories or a story with multiple technical tasks.
- When deciding task order, split strategy, reviewer needs, and delivery risk.

## Inputs
- epic
- stories
- technical_breakdown
- source_impact_map
- team_constraints

## Outputs
- team_execution_plan
- sequencing_recommendation
- dependency_and_owner_map

## Execution Logic
1. Group tasks by dependency, ownership, risk, testability, and review surface.
2. Identify work that can run in parallel versus work that must be serialized.
3. Recommend checkpoints, review gates, and owner assignments.
4. Call out scope that is too large or under-specified.

## Decision Rules
- `blocker`: task cannot start because requirement, dependency, owner, or approval is missing.
- `warning`: sequencing risk, review bottleneck, oversized task, or unclear owner.
- `info`: planning suggestion or parallelization opportunity.

## Failure Modes
- Team capacity and ownership may be unavailable or outdated.
- Technical decomposition may hide shared-file conflicts.

## Required Human Review
Team Leader owns final assignment, sequencing, and scope decisions.

## Service Context Layer
Read `.mana/global/service-mission.md`, `architecture.md`, `engineering-guards.md`, and `team-decisions/` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts. Maintain a context budget: keep a short working summary with objective, base branch or PR, issue keys, workspace path, checked evidence, open hypotheses, discarded hypotheses, and next checks instead of accumulating raw transcripts, full diffs, repeated file dumps, or copied tool output.

## Example Output
```yaml
skill: team-execution-plan
status: warning
summary: "Two stories can run in parallel after API contract approval."
outputs:
  - team_execution_plan
  - sequencing_recommendation
  - dependency_and_owner_map
human_review_required: true
```
