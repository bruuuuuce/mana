---
name: developer-readiness-check
version: 1.0.0
description: Checks whether a story is ready for development with enough requirements, impact map, test strategy, data, mocks, dependencies, and approvals.
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
  - architecture_rules_read
inputs:
  - story
  - acceptance_criteria
  - source_impact_map
  - technical_breakdown
  - risk_register
outputs:
  - developer_readiness_report
  - missing_inputs
  - start_conditions
risk_level: medium
owner_role: Team Leader / Developer
tags:
  - story-readiness
  - planning
  - team-lead
---

# Developer Readiness Check

## Purpose
Prevent developers from starting work on stories that are not implementable, testable, scoped, or approved enough.

## When To Use It
- After story planning and before implementation starts.
- When a Team Leader wants an explicit start/no-start signal for a story.

## Inputs
- story
- acceptance_criteria
- source_impact_map
- technical_breakdown
- risk_register

## Outputs
- developer_readiness_report
- missing_inputs
- start_conditions

## Execution Logic
1. Check that acceptance criteria are testable and aligned with epic goals.
2. Verify source impact, technical tasks, dependencies, test plan, data/mocks, and approval gates are clear enough.
3. Separate start blockers from follow-up warnings.
4. Produce start conditions and owner questions.

## Decision Rules
- `blocker`: missing acceptance criteria, unclear scope, missing critical dependency, missing test strategy, or unapproved high-risk area.
- `warning`: partial evidence that can be accepted with owner acknowledgement.
- `info`: implementation hint or documentation improvement.

## Failure Modes
- A story can be ready for discovery but not implementation; report that distinction clearly.
- Missing Jira context should not be silently inferred.

## Required Human Review
Team Leader owns the start decision. Developer confirms technical feasibility.

## Service Context Layer
Read `.mana/global/service-mission.md`, `architecture.md`, `testing-policy.md`, and `engineering-guards.md` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts.

## Example Output
```yaml
skill: developer-readiness-check
status: blocker
summary: "Story should not start until acceptance criteria identify error handling and test data."
outputs:
  - developer_readiness_report
  - missing_inputs
  - start_conditions
human_review_required: true
```
