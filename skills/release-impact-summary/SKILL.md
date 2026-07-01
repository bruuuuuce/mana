---
name: release-impact-summary
version: 1.0.0
description: Summarizes functional, technical, operational, rollback, and stakeholder impact for a planned release or branch.
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
  - release_scope
  - stories
  - branch_diff
  - test_evidence
  - service_context
outputs:
  - release_impact_summary
  - stakeholder_notes
  - release_risk_items
risk_level: medium
owner_role: Application Manager / Team Leader
tags:
  - release
  - operations
  - governance
---

# Release Impact Summary

## Purpose
Translate a technical change into release impact that an Application Manager can use for go/no-go discussion, communication, deployment planning, rollback planning, and support readiness.

## When To Use It
- Before release readiness, branch validation, or PR readiness for user-visible or operationally relevant changes.
- When an AM needs a concise view of affected capabilities, services, data, interfaces, jobs, reports, alerts, support procedures, and rollback constraints.
- When Jira or release notes are too implementation-heavy for operational stakeholders.

## Inputs
- release_scope
- stories
- branch_diff
- test_evidence
- service_context

## Outputs
- release_impact_summary
- stakeholder_notes
- release_risk_items

## Execution Logic
1. Identify business capability, user flow, services, jobs, APIs, events, database objects, and operational procedures affected by the change.
2. Separate confirmed impact from inferred impact and evidence gaps.
3. Summarize deployment, rollback, monitoring, support, and communication needs.
4. Highlight open decisions and owner approvals needed before release.

## Decision Rules
- `blocker`: missing release scope, unclear rollback for critical behavior, unapproved customer-visible impact, or operational dependency with no owner.
- `warning`: incomplete evidence, monitoring/support gap, manual procedure impact, or stakeholder communication needed.
- `info`: useful release note, support note, or reviewer context.

## Failure Modes
- Branch diff alone may miss configuration, scheduling, data, or external operational impact.
- Missing Jira/Confluence context can understate stakeholder impact.
- AI output is advisory; AM ownership remains mandatory.

## Required Human Review
Application Manager reviews release impact and communication items. Team Leader reviews technical scope. Architect, DBA, or Security owner reviews specialist blockers.

## Service Context Layer
Read `.mana/global/service-mission.md`, `architecture.md`, `integration-map.md`, `testing-policy.md`, and `engineering-guards.md` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts. Maintain a context budget: keep a short working summary with objective, base branch or PR, issue keys, workspace path, checked evidence, open hypotheses, discarded hypotheses, and next checks instead of accumulating raw transcripts, full diffs, repeated file dumps, or copied tool output.

## Example Output
```yaml
skill: release-impact-summary
status: warning
summary: "Release changes payment authorization retry behavior and requires support note updates."
findings:
  - severity: warning
    area: "operations"
    message: "Rollback changes behavior but not persisted retry counters; support must know expected symptoms."
    owner: "Application Manager"
outputs:
  - release_impact_summary
  - stakeholder_notes
  - release_risk_items
human_review_required: true
```
