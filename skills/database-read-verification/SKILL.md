---
name: database-read-verification
version: 1.0.0
description: Authors and executes explicitly approved PostgreSQL read-only verification queries against isolated test databases, preserving access-controlled result evidence and redacted reports.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - jira_read
  - test_runner_read
  - test_runner_execute_local
inputs:
  - database_requirements
  - database_verification_catalog
  - requested_verification_ids
  - environment_name
outputs:
  - database_verification_proposal
  - database_verification_report
  - database_learning_proposal
risk_level: high
owner_role: Developer / QA / DBA
stack:
  - postgresql
tags:
  - testing
  - database
  - postgresql
  - read-only
model_tier: economy
execution_mode: write
delegation_group: database
parallel_safe: false
---

# Database Read Verification

## Purpose
Verify expected persisted state with approved PostgreSQL read-only queries on
an isolated test database. It is not a generic database console or migration tool.

## When To Use It
Use after an approved integration/API/UI flow needs persistence evidence, or
when a defect investigation needs a bounded, non-production read verification.

## Workflow
1. Map requirements to aggregate, count, state, or referential-integrity checks.
2. Store each query in a local `.sql` file and propose a catalog entry with a
   test-only connection environment-variable reference.
3. Require DBA/owner approval for target, data classification, and entries.
4. Execute selected IDs through `scripts/run-db-verification.sh`.
5. Report only approved, non-sensitive result summaries and propose catalog
   improvements for future runs.

## Rules
- Only `SELECT` or non-mutating `WITH` queries are eligible; the runner rejects
  DDL, DML, locks, multiple statements, and non-isolated targets.
- The connection string is supplied by an environment variable and is never read
  into a Mana report.
- Queries must avoid customer data and prefer counts, IDs already approved for
  testing, and aggregate assertions.
- Production access, mutations, migrations, and arbitrary client commands are blocked.

## Outputs
Write verification proposal, machine-readable run report, access-controlled log
reference, and approval-required learning proposal. Use
`templates/database-verification.template.yaml`.

## Decision Rules
- `passed`: the read-only query completes successfully.
- `failed`: the approved query returns a non-zero client result.
- `blocked`: policy, query safety, target, approval, or client gate refuses execution.
- `inconclusive`: result cannot distinguish product state from fixture or environment cause.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use compact caveman mode and a context budget: retain query references,
approved summaries, artifacts, gaps, and decisions, never connection strings or
raw sensitive rows.
