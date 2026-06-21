# Example Run: Team Coaching Report — feature/PAY-201-payment-retry

## Input

```yaml
branch_name: feature/PAY-201-payment-retry
base_branch: main
```

---

## Phase 1 — Contributor Enumeration

Agent output to Team Leader (chat):

> Found 3 contributors with commits on `feature/PAY-201-payment-retry` beyond `main`:
>
> | # | Contributor | Commits |
> |---|---|---|
> | 1 | Lucia Ferrari (lucia.ferrari@example.com) | 4 |
> | 2 | Marco Rossi (marco.rossi@example.com) | 6 |
> | 3 | Anna Bianchi (anna.bianchi@example.com) | 2 |
>
> ⚠️ Warning: Anna Bianchi has only 2 commits — pattern classification
> will have limited confidence.
>
> Confirm to proceed with all 3 contributors, or exclude any?

Team Leader response: "Proceed with all three."

---

## Phase 2 — Per-Contributor Analysis

### Lucia Ferrari — 4 commits

Skills run: `pre-review-defect`, `test-quality`, `npe-nullability`,
`java-performance-smell` (Java files present), `known-pitfalls-extraction`.

`contributor-pattern-analysis` result:

| Pattern | Classification | Severity | Occurrences |
|---|---|---|---|
| test_coverage: edge cases absent | tendency | warning | 2 |
| nullability: Optional.get() without guard | tendency | warning | 2 |

→ Saved: `agent-memory/contributor-pattern-report-lucia-ferrari.md`

---

### Marco Rossi — 6 commits

Skills run: `pre-review-defect`, `test-quality`, `npe-nullability`,
`java-performance-smell`, `known-pitfalls-extraction`.

`contributor-pattern-analysis` result:

| Pattern | Classification | Severity | Occurrences |
|---|---|---|---|
| defect_quality: exception swallowed in catch | habit | blocker | 4 |
| test_coverage: no integration test for external calls | habit | warning | 3 |
| performance: N+1 query in service loop | tendency | warning | 2 |

→ Saved: `agent-memory/contributor-pattern-report-marco-rossi.md`

---

### Anna Bianchi — 2 commits (low_commit_count)

Skills run: `pre-review-defect`, `test-quality`, `npe-nullability`.
`java-performance-smell` skipped: no non-test Java files.

`contributor-pattern-analysis` result:

| Pattern | Classification | Severity | Occurrences |
|---|---|---|---|
| test_coverage: edge cases absent | isolated | warning | 1 |

⚠️ Note: low_commit_count — pattern confidence is limited.

→ Saved: `agent-memory/contributor-pattern-report-anna-bianchi.md`

---

## Phase 3 — Team Aggregation

### Team Heatmap

| Quality Category | Lucia Ferrari | Marco Rossi | Anna Bianchi |
|---|---|---|---|
| defect_quality | — | **habit** | — |
| test_coverage | tendency | **habit** | isolated |
| nullability | tendency | — | — |
| performance | — | tendency | — |
| pitfall | — | — | — |

**Shared gap (>50% of contributors):** `test_coverage` — 2 of 3 contributors
show a test coverage pattern (Lucia: tendency, Marco: habit).

**Individual gaps:**
- Marco Rossi: `defect_quality` habit (blocker) → priority 1-to-1.
- Lucia Ferrari: `nullability` tendency → targeted code review session.
- Marco Rossi: `performance` tendency → pair programming on query patterns.

---

## Phase 4 — Team Coaching Report

**File:** `agent-memory/team-coaching-report.md`

---

```markdown
# Team Coaching Report
Branch: feature/PAY-201-payment-retry
Base: main
Date: 2026-06-21
Contributors: 3 | Patterns found: 6 | Shared gaps: 1

---

## Executive Summary

- **Priority action:** Marco Rossi shows a recurring habit of swallowing
  exceptions silently (4 occurrences, blocker severity). Schedule a 1-to-1
  before the next PR.
- **Shared gap:** Test coverage is insufficient across the team — 2 of 3
  contributors consistently omit edge-case and integration tests.
- **Individual opportunity:** Lucia Ferrari tends to use `Optional.get()`
  without null guards; a short code review walkthrough would address this.
- **Anna Bianchi:** Only 2 commits on this branch; insufficient data for
  reliable pattern assessment.
- **Recommended first step:** Team session on test design (edge cases +
  integration) before next sprint, followed by Marco's 1-to-1 on exception
  handling.

---

## Team Heatmap

| Quality Category | Lucia Ferrari | Marco Rossi | Anna Bianchi |
|---|---|---|---|
| defect_quality | — | **habit** | — |
| test_coverage | tendency | **habit** | isolated |
| nullability | tendency | — | — |
| performance | — | tendency | — |

Legend: **habit** = 3+ occurrences · tendency = 2 occurrences ·
isolated = 1 blocker · — = not observed

---

## Shared Gaps (team-level action recommended)

### Test Coverage
Observed in: Lucia Ferrari (tendency), Marco Rossi (habit), Anna Bianchi
(isolated).

**Pattern:** Tests consistently cover the happy path but omit error paths,
boundary conditions, and integration scenarios with external dependencies.

**Recommended action:** 1-hour team session on test design principles:
- When to write unit vs. integration tests.
- `@ParameterizedTest` for boundary coverage.
- Mocking vs. real-database testing for external calls.

---

## Per-Contributor Sections

### Lucia Ferrari

**Patterns identified:**

**1. Test Coverage — tendency (warning)**
- Growth opportunity: strengthen test coverage for edge cases and error
  paths.
- Evidence:
  - `src/test/java/payments/PaymentValidatorTest.java:31` — happy path only.
  - `src/test/java/payments/RetryLogicTest.java:18` — max-retry boundary
    not tested.
- Coaching recommendation: pair programming session (1h) with a senior
  dev focused on boundary-value testing. Participate in team test session
  (see Shared Gaps).

**2. Nullability — tendency (warning)**
- Growth opportunity: adopt safe Optional patterns consistently.
- Evidence:
  - `src/main/java/payments/PaymentMapper.java:55` — `Optional.get()`
    without `.isPresent()` check.
  - `src/main/java/payments/ValidationService.java:88` — same pattern.
- Coaching recommendation: code review walkthrough on `Optional` best
  practices (30 min). Reference: `engineering-guards.md` nullability section.

---

### Marco Rossi

**Patterns identified:**

**1. Defect Quality — habit (blocker)**
- Growth opportunity: adopt a consistent exception handling strategy.
- Evidence:
  - `src/main/java/payments/RetryHandler.java:113` — `catch (Exception e) {}`
    with no log or rethrow.
  - `src/main/java/payments/PaymentGateway.java:78` — exception swallowed.
  - `src/main/java/payments/NotificationService.java:44` — same pattern.
  - `src/main/java/payments/AuditLogger.java:29` — same pattern.
- Coaching recommendation: **Priority 1-to-1 before next PR** (1h). Cover:
  exception taxonomy (checked vs. unchecked), logging obligations, and
  the team's error handling policy in `engineering-guards.md`.

**2. Test Coverage — habit (warning)**
- Growth opportunity: add integration tests for external service calls.
- Evidence:
  - `src/test/java/payments/PaymentGatewayTest.java` — no integration test
    for gateway timeout scenario.
  - `src/test/java/payments/NotificationServiceTest.java` — mocked only,
    no real queue test.
  - `src/test/java/payments/AuditLoggerTest.java` — assertion on log output
    missing.
- Coaching recommendation: participate in team test session; then 30-min
  follow-up on integration test patterns specific to this codebase.

**3. Performance — tendency (warning)**
- Growth opportunity: identify and eliminate N+1 query patterns.
- Evidence:
  - `src/main/java/payments/PaymentBatchService.java:67` — `findById()`
    called inside a loop over a collection.
  - `src/main/java/payments/ReconciliationService.java:112` — same pattern.
- Coaching recommendation: pair programming session (1h) on batch query
  patterns (`IN` clause, `JOIN FETCH`, or JPA `EntityGraph`).

---

### Anna Bianchi

⚠️ Limited data (2 commits). Assessment confidence is low. Observe over the
next sprint before drawing conclusions.

**Patterns identified:**

**1. Test Coverage — isolated (warning)**
- Growth opportunity: consider adding edge-case coverage.
- Evidence:
  - `src/test/java/payments/CurrencyConverterTest.java:19` — only
    EUR→USD conversion tested; other paths absent.
- Coaching recommendation: include in team test session. No 1-to-1 needed
  at this stage; re-evaluate next sprint.

---

## TL Action Plan

| Priority | Action | Format | Target | Timing |
|---|---|---|---|---|
| 1 | Exception handling: review strategy and apply to current branch | 1-to-1 (1h) | Marco Rossi | Before next PR |
| 2 | Test design: edge cases, error paths, integration | Team session (1h) | All 3 | Next sprint kickoff |
| 3 | Optional / nullability: safe patterns walkthrough | Code review (30m) | Lucia Ferrari | Within sprint |
| 4 | N+1 query patterns: batch query techniques | Pair programming (1h) | Marco Rossi | Within sprint |
| 5 | Re-assess Anna Bianchi patterns | — | Anna Bianchi | Next coaching review |

---

## Privacy Note

> This report is confidential and intended for Team Leader use only.
> The findings represent observed code patterns on the analysed branch, not
> a formal performance assessment. The Team Leader decides how, when, and
> whether to share any part of this report with individual contributors.
> Do not commit this file to the project repository.
```

---

## Agent Status Block

```yaml
agent: team-coaching-report-agent
status: ready_with_warnings
branch: feature/PAY-201-payment-retry
base_branch: main
contributors_analysed: 3
patterns_found: 6
shared_gaps: 1
warnings:
  - "Anna Bianchi: low_commit_count (2 commits) — pattern confidence limited"
  - "testing-policy.md not found in .mana/global; defaults used"
artifacts:
  - agent-memory/team-coaching-report.md
  - agent-memory/contributor-pattern-report-lucia-ferrari.md
  - agent-memory/contributor-pattern-report-marco-rossi.md
  - agent-memory/contributor-pattern-report-anna-bianchi.md
human_approval_required: true
next_step: "Team Leader reviews agent-memory/team-coaching-report.md and schedules coaching actions."
```
