---
name: review-load-balancing
version: 1.0.0
description: Recommends reviewer focus, review order, specialist involvement, and review load distribution based on change risk and ownership.
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
  - branch_diff
  - source_impact_map
  - risk_register
  - ownership_context
outputs:
  - review_load_plan
  - reviewer_focus_map
  - specialist_review_requests
risk_level: low
owner_role: Team Leader
tags:
  - review
  - team-lead
  - pr-readiness
---

# Review Load Balancing

## Purpose
Help Team Leaders and reviewers spend review time on the riskiest areas first.

## When To Use It
- Before PR creation or when a large branch needs reviewer assignment.
- When a change crosses domains, services, database, security, operations, or architecture boundaries.

## Inputs
- branch_diff
- source_impact_map
- risk_register
- ownership_context

## Outputs
- review_load_plan
- reviewer_focus_map
- specialist_review_requests

## Execution Logic
1. Classify changed areas by risk, ownership, complexity, and required specialist review.
2. Recommend review order and focused questions per reviewer role.
3. Flag review bottlenecks, missing reviewers, and areas that need architect/DBA/security/AM attention.

## Decision Rules
- `blocker`: required specialist review missing for high-risk database, security, architecture, or operational change.
- `warning`: review surface too broad, unclear owner, or overloaded reviewer.
- `info`: review ordering or focus suggestion.

## Failure Modes
- Reviewer availability is usually outside repository evidence.
- Ownership maps may be stale.

## Required Human Review
Team Leader owns reviewer assignment and final review strategy.

## Service Context Layer
Read `.mana/global/architecture.md`, `engineering-guards.md`, and `team-decisions/` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts.

## Example Output
```yaml
skill: review-load-balancing
status: warning
summary: "DBA and AM review are needed before standard code review."
outputs:
  - review_load_plan
  - reviewer_focus_map
  - specialist_review_requests
human_review_required: true
```
