---
name: delivery-risk-radar
version: 1.0.0
description: Detects delivery risks such as oversized scope, missing decisions, dependency gaps, test gaps, review bottlenecks, and plan drift.
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
  - planning_artifacts
  - branch_diff
  - test_evidence
outputs:
  - delivery_risk_radar
  - escalation_items
  - mitigation_plan
risk_level: medium
owner_role: Team Leader / Application Manager
tags:
  - delivery-risk
  - planning
  - governance
---

# Delivery Risk Radar

## Purpose
Provide a concise risk radar for Team Leaders and AMs before scope, schedule, or quality problems become late surprises.

## When To Use It
- During epic planning, story readiness, branch validation, release readiness, or status review.
- When multiple stories, teams, dependencies, or approval gates are involved.

## Inputs
- epic
- stories
- planning_artifacts
- branch_diff
- test_evidence

## Outputs
- delivery_risk_radar
- escalation_items
- mitigation_plan

## Execution Logic
1. Look for requirement ambiguity, oversized work, missing owners, dependency gaps, approval gaps, test gaps, review bottlenecks, and plan drift.
2. Classify risks by severity, owner, timing, and mitigation.
3. Produce a short escalation list and concrete next actions.

## Decision Rules
- `blocker`: work should not start or merge until a missing owner, approval, dependency, or critical evidence gap is resolved.
- `warning`: risk likely to cause rework, delay, or review churn.
- `info`: planning improvement or watch item.

## Failure Modes
- Delivery risk may depend on team capacity and calendar data outside Mana.
- Incomplete Jira data can understate dependency risk.

## Required Human Review
Team Leader owns delivery mitigation. AM owns release and operational escalation items.

## Service Context Layer
Read `.mana/global/service-mission.md`, `engineering-guards.md`, and `team-decisions/` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts.

## Example Output
```yaml
skill: delivery-risk-radar
status: warning
summary: "Main delivery risk is unresolved API contract approval before dependent story starts."
outputs:
  - delivery_risk_radar
  - escalation_items
  - mitigation_plan
human_review_required: true
```
