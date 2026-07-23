# Scenario: Conditional Database PR Review

**Profile:** `pr-ready`
**Activation signal:** `migration_or_schema_change`
**Expected skill:** `liquibase-production-risk`

## Setup

1. In a scratch branch, add `inputs/changes.txt` to the filtered diff inventory.
2. Provide a normal application-code change alongside the migration so the
   profile must select a specialist based on evidence rather than profile size.
3. Run `pr-ready` with a full-tier specialist available.

## Intent

The runner starts with the baseline skills, detects a migration/schema path,
then loads `liquibase-production-risk`. It must not treat the migration as a
generic code-only review.
