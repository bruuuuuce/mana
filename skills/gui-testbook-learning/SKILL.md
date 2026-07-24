---
name: gui-testbook-learning
version: 1.0.0
description: Converts GUI test run metadata and redacted artifacts into a proposed testbook improvement, preserving uncertainty and requiring human approval before catalog changes.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - read_files
  - test_runner_read
inputs:
  - gui_test_run_report
  - gui_test_artifacts
  - approved_gui_testbook
outputs:
  - gui_test_learning_report
  - gui_testbook_change_proposal
risk_level: medium
owner_role: Developer / QA
stack:
  - any
tags:
  - testing
  - gui
  - learning
  - testbook
model_tier: economy
execution_mode: read
delegation_group: tests
parallel_safe: true
---

# GUI Testbook Learning

## Purpose
Make later GUI runs faster by proposing evidence-backed testbook improvements
without silently changing an approved catalog.

## When To Use It
Use after a GUI execution produces a report and artifacts, especially after a
failure, block, flaky result, or repeated manual setup cost.

## Workflow
1. Read only run metadata, JUnit, named artifacts, and the matching testbook
   entry. Load a screenshot or trace only for a concrete failure hypothesis.
2. Separate product failures, setup/data failures, selector drift, flakiness,
   and missing evidence.
3. Propose targeted changes: precondition, reset step, stable locator,
   assertion, artifact expectation, or new scenario.
4. Mark every proposal `approval_required: true`; retain the prior entry until
   an owner accepts the change.

## Rules
- Do not infer visual correctness from screenshots alone when a deterministic
  assertion can be added.
- Do not add sensitive data to reports or catalog changes.
- Preserve blocked and inconclusive outcomes rather than manufacturing a cause.

## Outputs
Write a learning report and an approval-required catalog change proposal with
evidence references, uncertainty, and rollback to the prior entry.

## Decision Rules
- `blocked`: no matching report, artifact, or approved catalog entry is available.
- `warning`: the proposed cause is ambiguous or needs an owner decision.
- `info`: a targeted, evidence-backed improvement is ready for review.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use compact caveman mode and a context budget: preserve only entry
metadata, named artifacts, hypotheses, and approval decisions.
