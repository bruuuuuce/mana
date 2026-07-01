---
name: sonar-evidence-triage
version: 1.0.0
description: Triage existing Mana Sonar evidence for branch validation or PR review by separating new/touched findings from pre-existing noise, mapping severity to Mana risk, and deciding which Sonar findings deserve human attention.
compatibility:
  - codex
  - junie
  - claude
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
inputs:
  - sonar_evidence
  - branch_diff
  - changed_files
  - story_context
outputs:
  - sonar_triage_report
  - high_signal_findings
  - ignored_sonar_noise
risk_level: medium
owner_role: Reviewer / Team Leader
tags:
  - sonar
  - review
  - quality
---

# Sonar Evidence Triage

## Purpose
Turn existing Sonar output into high-signal review evidence. Separate findings
that matter for the current branch or PR from old, unrelated, or low-value
noise.

## When To Use It
- When `.mana/**/evidence/sonar/sonar-summary.md` or related Sonar evidence
  already exists.
- During branch validation or PR review when Sonar findings need triage against
  changed files.
- When the human asks which Sonar issues matter for the current branch.

## Outputs
- `sonar_triage_report`
- `high_signal_findings`
- `ignored_sonar_noise`

## Execution Logic
1. Read existing `.mana/**/evidence/sonar/sonar-summary.md` and related logs or
   exported issue summaries. Do not run `sonar-scanner` unless the human asks.
2. Map Sonar findings to changed files and touched methods when possible.
3. Classify findings as `new_or_touched`, `pre_existing_but_relevant`,
   `pre_existing_noise`, or `out_of_scope`.
4. Escalate only findings tied to production paths, security, database,
   cross-service contracts, missing tests, high complexity, or branch-changed
   behavior.
5. Produce a short triage report and a list of findings suitable for human
   review. Never paste large raw scanner logs.

## Decision Rules
- `blocker`: high-confidence bug/security issue in changed production path, or
  quality gate failure that project policy treats as blocking.
- `warning`: changed/touched issue with plausible maintainability, reliability,
  or testability impact.
- `info`: pre-existing or low-risk issue useful for follow-up but not blocking.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`. Use compact caveman
working notes and keep final output evidence-first. Maintain a context budget:
keep a short working summary and avoid accumulating raw scanner logs, repeated
issue dumps, or copied tool output.
