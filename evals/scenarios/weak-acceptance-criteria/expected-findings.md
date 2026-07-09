# Expected Findings: Weak Acceptance Criteria

## must_flag

| # | Finding | Minimum Severity | Owning Skill |
|---|---|---|---|
| 1 | AC 1 "works correctly for large date ranges" has no defined range bounds, data volume, or observable outcome | blocker | acceptance-criteria-testability |
| 2 | AC 2 "handles errors gracefully" names no error classes or expected behavior per class | warning | acceptance-criteria-testability |
| 3 | AC 3 "performance is acceptable" has no measurable threshold | warning | acceptance-criteria-testability |
| 4 | AC 4 depends on an unresolved pricing decision (refunded invoices) with no named owner or deadline | blocker | developer-readiness-check |
| 5 | Story defines no current failure evidence (error rates, failing scenarios) to verify improvement against | warning | developer-readiness-check |

## must_not

- Must not recommend starting development while findings 1 and 4 are open.
- Must not translate the vague criteria into invented concrete thresholds and
  present them as requirements.

## required_gates

- No-start recommendation with clarification questions routed to BA/PO and the
  pricing decision routed to a named owner.
