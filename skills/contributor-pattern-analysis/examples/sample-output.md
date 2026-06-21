# Sample Output: contributor-pattern-analysis

## Input Context

```yaml
contributor_email: "lucia.ferrari@example.com"
contributor_name: "Lucia Ferrari"
contributor_commits:
  - sha: "a1b2c3d"
    subject: "PAY-201 add payment validation"
    date: "2026-06-10"
  - sha: "e4f5g6h"
    subject: "PAY-201 fix edge case in retry logic"
    date: "2026-06-12"
  - sha: "i7j8k9l"
    subject: "PAY-201 add unit tests for validator"
    date: "2026-06-13"
```

---

## Output: contributor-pattern-report

```yaml
skill: contributor-pattern-analysis
status: ready
contributor: "lucia.ferrari@example.com"
contributor_name: "Lucia Ferrari"
commit_count: 3
patterns_found: 2
low_commit_count: false
warnings: []
```

---

### Pattern 1 — Test Coverage (tendency)

| Field | Value |
|---|---|
| Category | `test_coverage` |
| Classification | `tendency` |
| Occurrences | 2 |
| Severity | warning |

**Summary:** Unit tests cover the primary execution path but consistently
omit validation of error paths and boundary conditions.

**Evidence:**
- `src/test/java/payments/PaymentValidatorTest.java:31` — test `shouldValidatePayment` covers only the valid input case.
- `src/test/java/payments/RetryLogicTest.java:18` — test `shouldRetryOnFailure` does not test max-retry boundary.

**Coaching Recommendation:**
Schedule a focused code review session on test design, specifically on:
1. The "test pyramid" and when to write edge-case vs. integration tests.
2. Using `@ParameterizedTest` to cover boundary conditions efficiently.

Suggested pairing: 1 hour with a senior dev who owns the `testing-policy.md` standard.

---

### Pattern 2 — Nullability (tendency)

| Field | Value |
|---|---|
| Category | `nullability` |
| Classification | `tendency` |
| Occurrences | 2 |
| Severity | warning |

**Summary:** Optional return values passed directly to methods without
null-check guards, risking NPE under unexpected input.

**Evidence:**
- `src/main/java/payments/PaymentMapper.java:55` — `getPaymentMethod()` result used without `.isPresent()` check.
- `src/main/java/payments/ValidationService.java:88` — Optional chained with `.get()` without guard.

**Coaching Recommendation:**
Review the project's nullability conventions in `engineering-guards.md`.
Specific growth area: replace `.get()` with `.orElseThrow()` / `.orElse()`
patterns. One targeted code review walkthrough should be sufficient.

---

## Skill Status Block

```yaml
outputs:
  - contributor_pattern_report
human_review_required: true
note: "This report is for Team Leader use only. Share coaching recommendations
       with the contributor only after TL review and preparation."
```
