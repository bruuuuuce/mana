---
name: testbook-run-report
version: 1.0.0
description: Runs explicitly approved local testbook entries through a controlled allowlist and converts command logs and structured test artifacts into an evidence-based execution report.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - read_files
  - test_runner_read
  - test_runner_execute_local
inputs:
  - approved_testbook
  - test_ids
  - environment_name
  - test_artifacts
outputs:
  - test_run_report
  - test_execution_log
risk_level: medium
owner_role: Developer / QA
stack:
  - any
tags:
  - testing
  - execution
  - report
model_tier: economy
execution_mode: write
delegation_group: tests
parallel_safe: false
---

# Testbook Run Report

## Purpose
Run a bounded local validation command and turn its evidence into a report
without expanding the command, target environment, or approval scope.

## When To Use It
Use only after a human has approved a specific testbook entry for the declared
environment.

Run only approved catalog entries through `scripts/run-testbook.sh`. The model
selects an entry ID; it must never supply, rewrite, or concatenate shell
commands.

## Workflow
1. Read `docs/policies/testbook-execution-policy.md`.
2. Verify the entry is `approved: true`, `execution_status: runnable`, and its
   declared environment matches the requested environment and timeout.
3. For performance tests, require an explicit non-production environment and
   the runner's explicit performance flag.
4. Execute one entry at a time and preserve the generated log and YAML report.
5. Parse JUnit, benchmark, or tool-native artifacts when available. Otherwise,
   report exit code and log evidence only.
6. Return `passed`, `failed`, `blocked`, `partial`, or `inconclusive`. A failed
   command is not by itself proof of a product regression.

## Rules
- Never execute unapproved or `needs_environment` entries.
- Never target production, infer credentials, alter test data, trigger CI, or
  publish results externally.
- Treat missing baseline, unavailable artifacts, or environment failure as
  `inconclusive` or `blocked`.
- Escalate performance regressions, security-sensitive test data, and ambiguous
  failure causes to the accountable human owner.

## Outputs
Write a test run report, command log reference, native artifact references, and
one of the declared verdicts. Follow
`docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard).

## Decision Rules
- `passed`: exit code and declared evidence are successful.
- `failed`: the command returned a non-zero exit code.
- `blocked`: a policy, approval, tool, or environment gate prevented execution.
- `inconclusive`: evidence cannot separate product failure from setup or data.

Use compact caveman working notes and a context budget: retain result metadata,
evidence paths, and unresolved cause hypotheses, not raw logs in the report.
