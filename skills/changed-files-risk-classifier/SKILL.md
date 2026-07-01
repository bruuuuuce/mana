---
name: changed-files-risk-classifier
version: 1.0.0
description: Classifies changed files by risk domain such as production code, tests, config, database, generated code, framework noise, cross-service contract, security/auth, and documentation so agents can focus only relevant skills.
compatibility:
  - codex
  - junie
  - claude
preferred_runner: codex
allowed_tools:
  - git_read
  - code_search
  - read_files
inputs:
  - changed_files
  - branch_diff
  - engineering_guards
outputs:
  - changed_files_risk_map
  - skill_routing_recommendation
  - review_focus
risk_level: low
owner_role: Developer / Reviewer / Team Leader
tags:
  - diff
  - review
  - routing
---

# Changed Files Risk Classifier

## Purpose
Classify changed files before deep analysis so agents load only relevant skills
and reviewers focus on the risky parts of a diff.

## When To Use It
- Before `branch-ready`, `pr-ready`, or `requested-pr-review` deep analysis.
- When a diff contains mixed application, test, config, database, dependency,
  generated, documentation, or Mana/bootstrap files.
- When an agent needs to decide which specialist skills to load.

## Outputs
- `changed_files_risk_map`
- `skill_routing_recommendation`
- `review_focus`

## Execution Logic
1. Read changed-file list from branch or PR diff.
2. Exclude known Mana/bootstrap noise unless explicitly in scope:
   `.mana/**`, `AGENTS.md`, `CLAUDE.md`, `mana`, generated Mana ignore changes.
3. Classify each file: production code, test, config, database/migration,
   generated, docs, build/dependency, cross-service contract, security/auth,
   observability, or unknown.
4. Add risk tags from path, extension, package, annotations, API names, table
   names, queue/topic names, and engineering guards.
5. Recommend which skills should run and which should be skipped.

## Decision Rules
- `blocker`: protected path changed without approval, destructive DB/security
  surface changed without owner evidence, or diff base unclear.
- `warning`: risky domain touched but specialist evidence missing.
- `info`: low-risk classification and suggested reviewer focus.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`.
Internal reasoning must use compact caveman mode: terse fragments,
evidence-first notes, no long narrative, and no private chain-of-thought in
final artifacts. Maintain a context budget: keep a short working summary and
avoid accumulating raw diffs, repeated file dumps, or copied tool output.
