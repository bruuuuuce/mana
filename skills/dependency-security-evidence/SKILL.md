---
name: dependency-security-evidence
version: 1.0.0
description: Collects and triages dependency and security evidence from local project manifests, lockfiles, build tool reports, or existing scanner output for branch validation, PR review, and release readiness.
compatibility:
  - codex
  - junie
  - claude
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
  - shell_command
inputs:
  - dependency_manifests
  - lockfiles
  - scanner_reports
  - branch_diff
outputs:
  - dependency_security_report
  - vulnerable_dependency_findings
  - dependency_followups
risk_level: medium
owner_role: Developer / Security / Team Leader
tags:
  - dependencies
  - security
  - evidence
---

# Dependency Security Evidence

## Purpose
Make dependency risk visible without turning Mana into a package manager or
security scanner.

## When To Use It
- When dependency manifests, lockfiles, build plugin files, repository sources,
  or local dependency scanner reports changed.
- During `branch-ready`, `pr-ready`, or `requested-pr-review` when dependency
  evidence may affect review risk.
- When a human needs a local inventory before running or reviewing a
  project-approved scanner.

## Outputs
- `dependency_security_report`
- `vulnerable_dependency_findings`
- `dependency_followups`

## Execution Logic
1. Prefer existing local artifacts under `.mana/**/evidence/dependencies/`.
2. Inspect changed dependency manifests and lockfiles such as `pom.xml`,
   `build.gradle`, `build.gradle.kts`, `settings.gradle`, `package.json`,
   `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, and `gradle.lockfile`.
3. If scanner output exists, summarize critical/high CVEs, license blockers,
   direct dependency changes, and transitive risk. Do not invent CVEs.
4. If no scanner output exists, report evidence gaps and recommend the
   project-approved scanner or `./mana dependency-evidence --collect` for a
   local manifest inventory.
5. Map risk to the current branch: new dependency, version upgrade/downgrade,
   removed lock, changed repository source, or security-sensitive package.

## Decision Rules
- `blocker`: known critical/high vulnerability in newly introduced dependency,
  license blocker, unaudited repository source, or removed lockfile without
  approval.
- `warning`: dependency upgrade/downgrade without test evidence, stale scanner
  output, or missing lockfile evidence.
- `info`: manifest-only inventory or follow-up recommendation.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`. Keep reports concise and
link to artifacts instead of pasting full dependency trees.
Internal reasoning must use compact caveman mode: terse fragments,
evidence-first notes, no long narrative, and no private chain-of-thought in
final artifacts. Maintain a context budget: keep a short working summary and
avoid accumulating raw dependency trees, repeated manifest dumps, or copied
scanner output.
