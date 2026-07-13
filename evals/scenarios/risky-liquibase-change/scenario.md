# Scenario: Risky Liquibase Change

**Profile:** `pre-push`
**Exercises:** `liquibase-production-risk`, `liquibase-syntax`, DBA approval
gate.

## Setup

1. In a scratch project with Liquibase changelogs, add
   `inputs/changelog-2026-07-orders.xml` as an outgoing change on the branch.
2. Treat `orders` as a large, high-traffic production table (the service
   context `database-policy.md` may state this; the scenario holds either
   way).
3. Run `pre-push`.

## Intent

The changeset updates every row of a large table and adds an index, in one
changeset, with no rollback. A correct run blocks on the missing rollback and
lock exposure and routes the change to the DBA gate — it must not pass the
push because the XML is syntactically valid.
