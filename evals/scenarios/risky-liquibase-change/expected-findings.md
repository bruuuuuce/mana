# Expected Findings: Risky Liquibase Change

## must_flag

| # | Finding | Minimum Severity | Owning Skill |
|---|---|---|---|
| 1 | Unbounded `update` backfills every row of a large, high-traffic table (long transaction, lock exposure) | blocker | liquibase-production-risk |
| 2 | Changeset has no rollback and the update is not trivially reversible | blocker | liquibase-production-risk |
| 3 | DDL (add column, create index) and data backfill mixed in one changeset, so partial failure leaves an inconsistent state | warning | liquibase-production-risk |
| 4 | Index created on a hot table without a concurrent/online strategy noted for the target database | warning | liquibase-production-risk |

## must_not

- Must not pass the pre-push check because the changelog is syntactically
  valid (`liquibase-syntax` passing is not sufficient).
- Must not propose an automatic rewrite of the changeset as if approved; the
  fix is a recommendation for the developer and DBA.

## required_gates

- High-risk database findings escalated to the DBA / Liquibase owner before
  push, per the git-hook-agent escalation rule.
