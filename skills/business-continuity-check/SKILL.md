---
name: business-continuity-check
version: 1.0.0
description: Checks whether a change can disrupt cutoffs, batches, reconciliation, SLA, manual procedures, reporting, or operational continuity.
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
  - operational_calendar
  - branch_diff
  - service_context
outputs:
  - business_continuity_report
  - cutoff_and_batch_risks
  - continuity_actions
risk_level: high
owner_role: Application Manager / Operations
tags:
  - continuity
  - release
  - operations
---

# Business Continuity Check

## Purpose
Detect whether a change can interrupt business operations even when code and tests appear correct.

## When To Use It
- Before releases touching payment lifecycle, settlement, reconciliation, reporting, batch, notifications, manual back-office procedures, or operational calendars.
- When cut-off windows, SLA, or manual support flows matter.

## Inputs
- release_scope
- stories
- operational_calendar
- branch_diff
- service_context

## Outputs
- business_continuity_report
- cutoff_and_batch_risks
- continuity_actions

## Execution Logic
1. Identify scheduled jobs, cutoffs, reconciliation, reporting, data extracts, manual interventions, and support flows affected by the change.
2. Check deployment timing, rollback timing, data compatibility, and partial-failure behavior.
3. Flag operational dependencies that need owner confirmation.
4. Produce continuity actions and go/no-go questions.

## Decision Rules
- `blocker`: unresolved risk to critical cutoff, settlement, reconciliation, SLA, or manual recovery path.
- `warning`: incomplete operational evidence or timing dependency requiring AM acknowledgement.
- `info`: release note, support note, or deployment-window consideration.

## Failure Modes
- Operational calendars and manual procedures may live outside the repository.
- A clean test suite does not prove business continuity.

## Required Human Review
Application Manager or Operations owner must approve blocker and warning items before release.

## Service Context Layer
Read `.mana/global/service-mission.md`, `integration-map.md`, `database-policy.md`, and `engineering-guards.md` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts. Maintain a context budget: keep a short working summary with objective, base branch or PR, issue keys, workspace path, checked evidence, open hypotheses, discarded hypotheses, and next checks instead of accumulating raw transcripts, full diffs, repeated file dumps, or copied tool output.

## Example Output
```yaml
skill: business-continuity-check
status: blocker
summary: "Settlement export behavior changes without confirmation of cutoff impact."
findings:
  - severity: blocker
    area: "cutoff"
    owner: "Application Manager"
    recommended_action: "Confirm deployment window and rollback procedure before release."
human_review_required: true
```
