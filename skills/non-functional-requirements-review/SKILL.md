---
name: non-functional-requirements-review
version: 1.0.0
description: Reviews performance, resiliency, security, observability, scalability, auditability, operability, and compliance implications of a change.
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
  - logs_observability_read
inputs:
  - story
  - design
  - branch_diff
  - service_context
  - test_evidence
outputs:
  - nfr_review_report
  - nfr_questions
  - required_evidence
risk_level: medium
owner_role: Architect / Team Leader / Security
tags:
  - architecture
  - nfr
  - quality-attributes
---

# Non-Functional Requirements Review

## Purpose
Make quality-attribute risk explicit before implementation or merge.

## When To Use It
- When a change affects performance, resilience, security, observability, scalability, audit, compliance, or operational behavior.
- During architecture review, branch validation, release readiness, or pre-mortem.

## Inputs
- story
- design
- branch_diff
- service_context
- test_evidence

## Outputs
- nfr_review_report
- nfr_questions
- required_evidence

## Execution Logic
1. Review the change across performance, resiliency, security, observability, scalability, auditability, operability, and compliance.
2. Identify missing test, monitoring, load, failure-mode, or audit evidence.
3. Classify findings by severity and owner.
4. Recommend concrete evidence or design adjustments.

## Decision Rules
- `blocker`: high-risk NFR impact with no evidence or owner approval.
- `warning`: plausible NFR degradation with partial evidence.
- `info`: improvement or monitoring suggestion.

## Failure Modes
- Repository evidence may not include production traffic, load profiles, or compliance requirements.
- Missing telemetry can hide real operational risk.

## Required Human Review
Architect reviews architecture and resilience. Security reviews trust-boundary or compliance findings. Team Leader reviews implementation and test feasibility.

## Service Context Layer
Read `.mana/global/architecture.md`, `engineering-guards.md`, `testing-policy.md`, and `integration-map.md` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts.

## Example Output
```yaml
skill: non-functional-requirements-review
status: warning
summary: "Timeout behavior changed but failure-mode evidence is incomplete."
outputs:
  - nfr_review_report
  - nfr_questions
  - required_evidence
human_review_required: true
```
