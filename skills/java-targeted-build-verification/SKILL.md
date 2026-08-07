---
name: java-targeted-build-verification
version: 1.0.0
description: Produces bounded Java or Kotlin build/test evidence only from an approved testbook entry and fixed Maven or Gradle adapter.
compatibility:
  - codex
  - claude
  - opencode
  - junie
preferred_runner: mana
allowed_tools:
  - read_files
  - code_search
  - test_runner_read
  - test_runner_execute_local
inputs:
  - repository
  - changed_files
  - approved_testbook
outputs:
  - verification_result
risk_level: medium
owner_role: Developer / QA
stack:
  - java
tags:
  - verification
  - java
  - kotlin
  - tests
model_tier: economy
execution_mode: write
delegation_group: tests
parallel_safe: false
capability: verification
verification_spec: verification.yaml
---

# Java Targeted Build Verification

## Purpose
Run a fixed Maven or Gradle unit-test action only when the repository has Java
or Kotlin changes, the skill is explicitly selected, and one complete matching
testbook entry is approved. Automatic and derived actions are reported as
blocked; inferred commands are never executed.

## When To Use It
Use after Java or Kotlin files change in a Maven or Gradle repository and a
bounded local test result would reduce implementation uncertainty.

## Outputs
Produce canonical verification evidence containing applicability, approval and
trust provenance, fixed argv, build/test result, bounded logs, effects, and
limitations.

## Trust Boundary
Mana constructs argv from a fixed adapter. A repository wrapper is still
repository code, and its provenance and conservative effects are recorded. The
catalog command must match the fixed structured action, but is never evaluated
as shell text by this verifier.

## Decision Rules
- `passed`: the approved fixed build/test action exits successfully.
- `failed`: the approved action exits non-zero.
- `blocked`: no matching approved runnable local catalog entry exists.
- `inconclusive`: the build tool, timeout, environment, or source mutation
  prevents a reliable pass/fail result.

## Decision Boundary
Build and test outcomes are evidence, not merge or readiness judgments.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`. Although the v1 adapter
makes no model call, any runner reading this normal skill must use compact
caveman reasoning mode and context budget discipline: preserve concise evidence
and artifact references, never raw logs or private chain-of-thought.
