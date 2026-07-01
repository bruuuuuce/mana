---
name: architecture-guard-detector
version: 1.0.0
description: Compares branch or PR changes against .mana/global/engineering-guards.md to detect protected files, forbidden packages, disallowed patterns, required owner approvals, and architecture guard violations.
compatibility:
  - codex
  - junie
  - claude
preferred_runner: codex
allowed_tools:
  - read_files
  - git_read
  - code_search
  - architecture_rules_read
inputs:
  - engineering_guards
  - branch_diff
  - changed_files
  - owner_approvals
outputs:
  - architecture_guard_report
  - guard_violations
  - approval_requirements
risk_level: high
owner_role: Architect / Team Leader
tags:
  - architecture
  - guards
  - review
---

# Architecture Guard Detector

## Purpose
Detect whether a diff violates project engineering guards before review, merge,
or implementation continues.

## When To Use It
- When `.mana/global/engineering-guards.md` contains protected paths, owner
  gates, forbidden packages, or forbidden patterns.
- During `branch-ready`, `pr-ready`, or `requested-pr-review` when changed files
  may touch architecture-sensitive areas.
- Before claiming a guarded change is safe or review-ready.

## Outputs
- `architecture_guard_report`
- `guard_violations`
- `approval_requirements`

## Execution Logic
1. Read `.mana/global/engineering-guards.md`. If missing or placeholder-only,
   report degraded evidence.
2. Extract explicit protected paths, forbidden dependencies, forbidden packages,
   disallowed patterns, required owners, and approval gates.
3. Compare changed files and relevant diff snippets against those guards.
4. Separate actual violations from "needs owner confirmation".
5. Produce approval requirements with owner role and evidence path.

## Decision Rules
- `blocker`: explicit guard violation, protected file changed without approval,
  forbidden package/dependency introduced, or required owner approval missing.
- `warning`: guard is ambiguous, context missing, or path appears near a
  protected boundary.
- `info`: no guard hit, or documented approval present.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`.
Internal reasoning must use compact caveman mode: terse fragments,
evidence-first notes, no long narrative, and no private chain-of-thought in
final artifacts. Maintain a context budget: keep a short working summary and
avoid accumulating raw diffs, repeated file dumps, or copied tool output.
