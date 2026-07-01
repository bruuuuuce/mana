---
name: jira-acceptance-criteria-normalizer
version: 1.0.0
description: Converts Jira story or epic-story-pack acceptance criteria into a traceable checklist of expected behavior, required evidence, implementation status, and test status for planning, branch validation, and PR review.
compatibility:
  - codex
  - junie
  - claude
preferred_runner: codex
allowed_tools:
  - read_files
  - jira_read
  - code_search
  - git_read
inputs:
  - jira_story
  - epic_story_pack
  - branch_diff
  - test_evidence
outputs:
  - acceptance_criteria_trace
  - missing_behavior_findings
  - missing_test_evidence
risk_level: low
owner_role: BA / QA / Team Leader
tags:
  - jira
  - acceptance-criteria
  - traceability
---

# Jira Acceptance Criteria Normalizer

## Purpose
Normalize messy Jira acceptance criteria into an evidence checklist that later
agents can compare against implementation and tests.

## When To Use It
- When Jira story text or an epic story pack contains acceptance criteria.
- During planning when acceptance criteria need to become implementable and
  testable checklist items.
- During branch validation, PR readiness, or requested PR review when branch or
  PR changes must be compared against story acceptance criteria.

## Outputs
- `acceptance_criteria_trace`
- `missing_behavior_findings`
- `missing_test_evidence`

## Execution Logic
1. Read Jira story evidence or `.mana/**/evidence/jira/epic-story-pack.md`.
2. Preserve acceptance criteria wording when explicit. Do not invent missing AC.
3. Split each criterion into: id, expected behavior, preconditions, observable
   result, negative/error path, required evidence, implementation evidence, test
   evidence, status, and owner question.
4. Compare with branch diff and tests only when they are available.
5. Store/report a concise `acceptance_criteria_trace` for branch-ready, pr-ready,
   and requested-pr-review.

## Decision Rules
- `blocker`: missing or untestable critical acceptance criterion, implemented
  behavior contradicts AC, or required behavior has no implementation evidence.
- `warning`: AC is ambiguous, only partially tested, or missing negative path.
- `info`: normalized checklist item ready for follow-up.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`.
Internal reasoning must use compact caveman mode: terse fragments,
evidence-first notes, no long narrative, and no private chain-of-thought in
final artifacts. Maintain a context budget: keep a short working summary and
avoid accumulating full Jira dumps, repeated diffs, or copied tool output.
