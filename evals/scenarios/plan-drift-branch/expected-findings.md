# Expected Findings: Plan Drift Branch

## must_flag

| # | Finding | Minimum Severity | Owning Skill/Agent |
|---|---|---|---|
| 1 | `src/payment/FeeCalculator.java` changed: unplanned file inside the "Avoid Unless Approved" protected area, no story reference | blocker | branch-validation-agent / architecture-guard-detector |
| 2 | Planned tests missing: retry exhaustion, permanent-failure fast path, backoff bounds | warning | test-gap / branch-validation-agent |
| 3 | Fee rate change alters payment behavior with no test at all | blocker | branch-validation-agent |

## must_not

- Must not report the branch ready for PR while finding 1 is unresolved.
- Must not classify the `FeeCalculator` change as low-risk because the diff is
  one line.
- Must not count the single existing retry test as satisfying the planned test
  list.

## required_gates

- Payment owner approval requested for the protected-area change (or its
  removal from the branch).
- Missing-test evidence listed in the branch validation report for the
  developer to resolve before PR.
