---
name: architecture-drift-detection
version: 1.0.0
description: Detects divergence between branch changes and documented architecture, engineering guards, integration map, and team decisions.
compatibility:
  - codex
  - junie
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
  - architecture_rules_read
inputs:
  - branch_diff
  - architecture_context
  - engineering_guards
  - team_decisions
outputs:
  - architecture_drift_report
  - violated_guards
  - approval_requests
risk_level: high
owner_role: Architect / Team Leader
tags:
  - architecture
  - drift
  - governance
---

# Architecture Drift Detection

## Purpose
Find where actual branch changes diverge from approved architecture and recorded decisions.

## When To Use It
- Before merge, before architecture review, or whenever a branch touches shared flows, dependencies, persistence, security, contracts, or protected modules.

## Inputs
- branch_diff
- architecture_context
- engineering_guards
- team_decisions

## Outputs
- architecture_drift_report
- violated_guards
- approval_requests

## Execution Logic
1. Load documented architecture, engineering guards, integration map, and team decisions.
2. Compare changed files, dependencies, APIs, events, DB changes, configuration, and tests against those rules.
3. Classify drift as approved, needs documentation, needs owner approval, or blocks merge.

## Decision Rules
- `blocker`: direct violation of engineering guards or protected architecture without approval.
- `warning`: undocumented drift that may be acceptable with architect approval.
- `info`: documentation drift or follow-up update.

## Failure Modes
- Stale architecture documents can create false positives.
- Generated code or dynamic wiring may hide drift.

## Required Human Review
Architect reviews architecture drift. Team Leader reviews scope drift and implementation impact.

## Service Context Layer
Read `.mana/global/architecture.md`, `engineering-guards.md`, `integration-map.md`, and `team-decisions/` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts.

## Example Output
```yaml
skill: architecture-drift-detection
status: blocker
summary: "Branch introduces a forbidden synchronous dependency without approval."
outputs:
  - architecture_drift_report
  - violated_guards
  - approval_requests
human_review_required: true
```
