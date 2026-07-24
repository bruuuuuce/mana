---
name: gui-test-execution
version: 1.0.0
description: Executes explicitly approved Playwright GUI testbook entries in a declared isolated test environment and preserves access-controlled traces, screenshots, videos, JUnit, and redacted run metadata.
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
  - approved_gui_testbook
  - requested_test_ids
  - environment_name
outputs:
  - gui_test_run_report
  - gui_test_artifacts
risk_level: high
owner_role: Developer / QA
stack:
  - playwright
tags:
  - testing
  - gui
  - playwright
  - execution
model_tier: economy
execution_mode: write
delegation_group: tests
parallel_safe: false
---

# GUI Test Execution

## Purpose
Run a bounded, approved browser test through the controlled GUI testbook
runner. The model selects an ID only; it does not construct shell commands.

## When To Use It
Use only after a human approved a runnable GUI catalog entry for a declared
isolated test environment.

## Workflow
1. Read `docs/policies/gui-test-execution-policy.md`.
2. Verify the entry is approved, runnable, GUI-only, isolated-test-targeted,
   and has the requested environment.
3. Run `scripts/run-gui-testbook.sh` once per selected ID.
4. Preserve its report, JUnit, Playwright output, trace, screenshots, and
   video in an access-controlled local directory. Redact secrets from any
   human-readable summary.
5. Classify the result as `passed`, `failed`, `blocked`, or `inconclusive`.

## Rules
- Never run against production or an unclassified target.
- Never print, copy, or inspect secret values; secret references are checked
  only for presence in the execution environment.
- Do not perform exploratory browser actions outside approved Playwright code.
- A failed command is not enough to claim a product regression.

## Outputs
Write a run report, command-log reference, JUnit reference, and Playwright
artifact directory. Return one of `passed`, `failed`, `blocked`, or
`inconclusive`.

## Decision Rules
- `passed`: command succeeds and expected artifact locations exist.
- `failed`: the approved runner returned a non-zero code.
- `blocked`: a policy, approval, configuration, or environment gate refused execution.
- `inconclusive`: available evidence cannot isolate the cause.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use compact caveman mode and a context budget: keep metadata,
artifact paths, and cause hypotheses, not raw logs, secrets, or screenshots in
the final report.
