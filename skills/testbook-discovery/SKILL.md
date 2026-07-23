---
name: testbook-discovery
version: 1.0.0
description: Discovers candidate unit, integration, contract, end-to-end, and performance tests from repository layout, build files, package scripts, CI, and test tooling; produces a reviewable testbook without running commands.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
  - test_runner_read
inputs:
  - project_root
  - testing_policy
  - existing_testbook
outputs:
  - discovered_testbook
  - test_discovery_report
risk_level: low
owner_role: Developer / QA
stack:
  - any
tags:
  - testing
  - discovery
  - integration
  - performance
  - unit
model_tier: economy
execution_mode: read
delegation_group: tests
parallel_safe: true
---

# Testbook Discovery

## Purpose
Discover a reviewable, project-specific inventory of executable and
non-executable test candidates without changing the repository or running code.

## When To Use It
Use for an unfamiliar repository, after test tooling changes, or before creating
an approved catalog for local validation.

Discover candidate tests without executing them. Use
`scripts/discover-testbook.sh` for deterministic first-pass evidence, then
inspect only the files needed to resolve unclear classifications.

## Workflow
1. Read `.mana/global/testing-policy.md` and any existing testbook when present.
2. Run discovery against the target project root.
3. Inspect build files, CI definitions, test layouts, container configuration,
   and scripts referenced by candidates with medium or low confidence.
4. Classify entries as `unit`, `integration`, `contract`, `end_to_end`, or
   `performance`. Preserve the source and command origin for every entry.
5. Mark unknown prerequisites, credentials, target environment, and dynamic
   selectors as gaps. Do not invent flags, endpoints, or credentials.
6. Leave all new entries `approved: false`. Merge human-maintained testbook
   metadata rather than overwriting it.

## Rules
- A runnable command needs concrete repository evidence or deterministic tool
  convention. Naming alone is insufficient for a claim that it is runnable.
- A test that needs services, data, a target URL, or credentials is
  `needs_environment`, not runnable.
- Performance entries always require a dedicated non-production target and
  explicit approval.
- Missing tests or incomplete discovery are warnings, never proof that a test
  suite does not exist.

## Outputs
Write `testbook.discovered.yaml` and a concise report that lists discovered
entries, evidence, confidence, missing prerequisites, and human decisions
needed. Follow `docs/standards/agent-skill-output-standard.md`.

## Decision Rules
- `info`: command and classification have concrete evidence.
- `warning`: classification, prerequisites, or command evidence is incomplete.
- `blocked`: repository access or the selected project root is unavailable.

Use compact caveman working notes and a context budget: preserve only evidence,
open gaps, and next checks, never raw repository dumps.
