---
name: sonar-change-risk
version: 1.0.0
description: Estimates how risky it is to modify a specific class or file by combining local Sonar evidence with git churn, test evidence, ownership/criticality, story scope, and architecture guards. Use before changing a class, during dev-assist, or in review when a modified file looks fragile.
compatibility:
  - codex
  - junie
  - claude
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
  - test_runner_read
  - architecture_rules_read
inputs:
  - target_class_or_file
  - sonar_evidence
  - git_history
  - test_evidence
  - story_context
  - engineering_guards
outputs:
  - change_risk_report
  - safe_change_strategy
  - characterization_test_recommendations
risk_level: medium
owner_role: Developer / Team Leader
tags:
  - sonar
  - change-risk
  - dev-assist
  - review
---

# Sonar Change Risk

## Purpose
Estimate how risky it is to modify a specific class or file, then recommend a
safe change strategy before implementation or review.

Sonar is one signal, not the decision engine. Combine static quality evidence
with repository context, tests, story scope, ownership, and engineering guards.

## When To Use It
- Before modifying a class, service, mapper, controller, repository, job, or
  integration client.
- When a branch or PR touches a file that appears fragile, complex, untested, or
  production-critical.
- When Sonar evidence exists under `.mana/**/evidence/sonar/`.
- When a developer asks "quanto e' rischioso toccare questa classe?" or wants a
  safe strategy before editing.

## When Not To Use It
- Do not run it as a generic full-repository quality review.
- Do not treat Sonar issues outside the target file/change scope as blockers.
- Do not recommend broad refactoring unless the story explicitly allows it.
- Do not use this skill to justify bypassing tests, review, or owner approval.

## Inputs
- target_class_or_file
- sonar_evidence
- git_history
- test_evidence
- story_context
- engineering_guards

## Outputs
- change_risk_report
- safe_change_strategy
- characterization_test_recommendations

## Execution Logic
1. Resolve the exact target file/class. If ambiguous, ask which class/file to
   assess.
2. Load existing Sonar evidence if present:
   `.mana/**/evidence/sonar/sonar-summary.md`, scanner logs, and any exported
   issue/metric summaries. Do not run `sonar-scanner` unless the human asks for
   fresh evidence.
3. Gather local risk signals:
   - file size and main responsibilities;
   - cognitive/cyclomatic complexity when available from Sonar;
   - bugs, vulnerabilities, security hotspots, smells, duplication, and coverage
     signals tied to the target file;
   - git churn, recent edits, conflicting ownership, and recent bug-fix commits;
   - direct tests, characterization tests, integration tests, and regression
     evidence;
   - production path, database, external contract, async/concurrency, auth, or
     payment-critical involvement;
   - engineering guard or protected-area rules.
4. Separate existing debt from change-specific risk. Existing debt matters when
   it makes the intended change harder, less testable, or more likely to break
   production behavior.
5. Classify risk:
   - `low`: simple file, low complexity, good tests, narrow story scope, no
     critical path.
   - `medium`: some complexity/churn/test gaps, but change can be contained with
     focused tests.
   - `high`: high complexity, low coverage, critical path, unclear behavior,
     strong churn, or multiple risk domains.
   - `blocker`: protected area, missing owner approval, untestable critical
     behavior, or change would mix refactor and behavior in unsafe scope.
6. Recommend a safe strategy: smallest viable change, characterization tests
   first, split refactor from behavior, add guard tests, ask owner approval, or
   defer risky cleanup.

## Decision Rules
- `blocker`: target is protected by engineering guards, no safe test boundary
  exists for critical behavior, Sonar/test evidence shows uncontained risk on a
  production path, or story scope does not justify touching the file.
- `warning`: target has high complexity, low coverage, repeated churn, old debt,
  weak ownership, or missing characterization tests.
- `info`: useful local guidance, candidate tests, or refactoring note that does
  not change the start decision.

## Required Evidence
Report which evidence was available and which was missing:

```text
Sonar evidence: present/missing/stale
Git churn: checked/not checked
Direct tests: present/missing
Story scope: present/missing
Engineering guards: present/missing
```

Missing Sonar evidence must not block the skill. Continue with git/test/source
signals and recommend `./mana sonar --analyze` only when it would materially
improve the decision.

## Output Shape
Use a concise report:

```yaml
skill: sonar-change-risk
target: "src/main/java/.../RefundReconciliationService.java"
status: warning
change_risk: high
top_risk_factors:
  - "High complexity and low direct test evidence."
  - "Recent churn in settlement matching behavior."
safe_change_strategy:
  - "Add characterization tests around current matching behavior first."
  - "Change one branch only; avoid cleanup/refactor in the same PR."
  - "Run ./mana sonar --analyze after build and attach evidence."
human_review_required: true
```

## Human Approval
Developer owns the local strategy. Team Leader owns high-risk start/continue
decisions. Architect, DBA, Security, or service owner approval remains required
when the target file touches their guarded area.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use `templates/standard-agent-skill-report.template.md` when no more
specific template exists.

Internal reasoning must use compact caveman mode: terse fragments,
evidence-first notes, no long narrative, and no private chain-of-thought in
final artifacts. Maintain a context budget: keep a short working summary with
target file, intended change, Sonar evidence path, git/test checks, risk
signals, discarded risks, and next checks.
