---
name: mana-governance-regression-verification
version: 1.0.0
description: Runs bounded existing Mana behavioural eval scenarios and records their structured results as verification evidence.
compatibility:
  - codex
  - claude
  - opencode
  - junie
preferred_runner: mana
allowed_tools:
  - read_files
  - code_search
inputs:
  - repository
  - changed_files
outputs:
  - verification_result
risk_level: low
owner_role: Mana Maintainer
stack:
  - mana
tags:
  - verification
  - governance
  - eval
model_tier: economy
execution_mode: write
delegation_group: tests
parallel_safe: false
capability: verification
verification_spec: verification.yaml
---

# Mana Governance Regression Verification

## Purpose
Reuse Mana's existing deterministic behavioural eval runner to verify governed
profile, skill, agent, execution-plan, and eval-definition changes. The adapter
selects bounded existing scenarios and ingests their JSON results; it does not
reimplement eval assertions.

## Selection
The skill applies only in the Mana framework repository when relevant framework
or eval definitions changed. Explicit selection still requires the Mana eval
script and scenario repository to exist.

## When To Use It
Use after relevant Mana profiles, skill definitions, semantic agents, eval
scenarios, or execution-plan logic changes.

## Outputs
Produce canonical verification evidence linking the existing eval result JSON,
exit status, selected scenario, duration, and fixed adapter argv.

## Decision Rules
- `passed`: the selected deterministic scenario reports passed.
- `failed`: the selected scenario reports failed.
- `inconclusive`: the eval tool cannot produce a reliable result.
- `blocked`: selection or an execution bound prevents the check.

## Decision Boundary
An eval pass or failure is implementation evidence about Mana. Reviewers decide
whether it affects readiness or requires changes.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`. Although the v1 adapter
makes no model call, any runner reading this normal skill must use compact
caveman reasoning mode and context budget discipline: preserve concise evidence
and artifact references, never raw logs or private chain-of-thought.
