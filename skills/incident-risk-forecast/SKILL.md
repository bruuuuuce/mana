---
name: incident-risk-forecast
version: 1.0.0
description: Forecasts likely production incidents, escalations, alert noise, support tickets, or degraded behavior from a planned change.
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
  - logs_observability_read
  - architecture_rules_read
inputs:
  - release_scope
  - branch_diff
  - monitoring_context
  - known_pitfalls
  - test_evidence
outputs:
  - incident_risk_forecast
  - monitoring_questions
  - mitigation_actions
risk_level: medium
owner_role: Application Manager / Team Leader / SRE
tags:
  - incident
  - operations
  - production-risk
---

# Incident Risk Forecast

## Purpose
Answer the operational question: "If this change causes trouble in production, what are the most likely symptoms, triggers, blind spots, and mitigations?"

## When To Use It
- Before release or pre-commit for high-impact branches.
- When a change affects payment flows, critical jobs, error handling, retries, timeouts, idempotency, observability, or customer-visible behavior.
- When support and operations need early warning about possible incident patterns.

## Inputs
- release_scope
- branch_diff
- monitoring_context
- known_pitfalls
- test_evidence

## Outputs
- incident_risk_forecast
- monitoring_questions
- mitigation_actions

## Execution Logic
1. Inspect changed behavior, degraded-path handling, retries, timeouts, database writes, external dependencies, and observability.
2. Map likely production symptoms to root-cause candidates and detection signals.
3. Identify missing dashboards, alerts, logs, runbooks, and rollback limitations.
4. Recommend mitigations and owners without performing external changes.

## Decision Rules
- `blocker`: critical production symptom with no detection, rollback, mitigation, or owner.
- `warning`: plausible incident path with incomplete monitoring or test evidence.
- `info`: support note, runbook hint, or low-risk observation.

## Failure Modes
- Missing observability access limits confidence.
- Historical incidents may not be represented in the repository.
- The forecast is risk-oriented and may over-report plausible but unlikely failures.

## Required Human Review
Application Manager and Team Leader review operational risks. SRE/Operations reviews monitoring and runbook gaps where applicable.

## Service Context Layer
Read `.mana/global/known-pitfalls/`, `integration-map.md`, `testing-policy.md`, and `engineering-guards.md` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts.

## Example Output
```yaml
skill: incident-risk-forecast
status: warning
summary: "Most likely incident is duplicate downstream retry after timeout."
findings:
  - severity: warning
    symptom: "Increased duplicate authorization attempts"
    detection_gap: "No dashboard metric for retry deduplication outcome"
    mitigation: "Add pre-release dashboard check and support note"
human_review_required: true
```
