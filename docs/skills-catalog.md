# Skills Catalog

Reference guide for all 47 skills in the Mana framework, grouped by the
profile in which they are recommended. Skills may appear in multiple profiles.

Skills are ordered by delivery lifecycle: story intake → planning →
architecture → **development (dev-assist)** → pre-commit → pre-push →
branch validation → PR → release → team coaching → framework help.

Skills that exist in the framework but are not yet wired into a profile appear
at the end under [Standalone Skills](#standalone-skills).

---

## story-start
**Trigger:** `story_start` · **Owner:** Developer / Team Leader · **Duration:** 30 min

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`epic-goal-extraction`](../skills/epic-goal-extraction/SKILL.md) | Convert vague epic language into a structured contract: business goal, expected outcome, in/out-of-scope, architectural and quality constraints. | low | BA / PO |
| [`story-depth`](../skills/story-depth/SKILL.md) | Detect incomplete or uneven analysis across functional goal, data requirements, validations, external calls, error behavior, and acceptance criteria. | low | BA / Team Leader |
| [`story-consistency`](../skills/story-consistency/SKILL.md) | Find conflicting rules, duplicated scope, incompatible acceptance criteria, inconsistent terminology, and mismatched assumptions across related stories. | low | BA / Team Leader |
| [`acceptance-criteria-testability`](../skills/acceptance-criteria-testability/SKILL.md) | Ensure acceptance criteria can be translated into concrete tests with observable inputs, outputs, preconditions, and failure behavior. | low | BA / QA / Team Leader |
| [`source-impact-map`](../skills/source-impact-map/SKILL.md) | Identify files and components to probably modify, inspect before deciding, and avoid unless approved. | medium | Team Leader / Developer |
| [`technical-task-breakdown`](../skills/technical-task-breakdown/SKILL.md) | Create actionable tasks for developers and Junie, each with scope, candidate files, dependencies, tests, risks, and definition of done. | medium | Team Leader / Developer |
| [`architecture-risk`](../skills/architecture-risk/SKILL.md) | Review transaction boundaries, sync/async flows, idempotency, retries, feature flags, bounded contexts, and forbidden zones. | medium | Architect / Team Leader |
| [`cross-service-contract`](../skills/cross-service-contract/SKILL.md) | Check payloads, schemas, Kafka topics, error mapping, retry policy, timeout, idempotency, versioning, and ownership. | medium | Team Leader / Architect |
| [`liquibase-production-risk`](../skills/liquibase-production-risk/SKILL.md) | Detect lock risks, missing rollback, unsafe index operations, large table updates, destructive DDL, drift concerns, and traffic-aware ordering issues. | high | DBA / Team Leader |
| [`green-border-plan`](../skills/green-border-plan/SKILL.md) | Plan unit, integration, contract, regression, and legacy characterization tests needed before and during implementation. | medium | Team Leader / QA |

---

## story-ready-for-dev
**Trigger:** `story_ready_for_dev` · **Owner:** Team Leader · **Duration:** 20 min

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`acceptance-criteria-testability`](../skills/acceptance-criteria-testability/SKILL.md) | Ensure acceptance criteria can be translated into concrete tests with observable inputs, outputs, preconditions, and failure behavior. | low | BA / QA / Team Leader |
| [`developer-readiness-check`](../skills/developer-readiness-check/SKILL.md) | Prevent developers from starting work on stories that are not implementable, testable, scoped, or approved enough. | medium | Team Leader / Developer |
| [`epic-story-partitioning`](../skills/epic-story-partitioning/SKILL.md) | Review epic sibling stories for overlap, missing slices, hidden dependencies, oversized stories, and weak acceptance boundaries. | medium | BA / PO / Team Leader |
| [`source-impact-map`](../skills/source-impact-map/SKILL.md) | Identify files and components to probably modify, inspect before deciding, and avoid unless approved. | medium | Team Leader / Developer |
| [`technical-task-breakdown`](../skills/technical-task-breakdown/SKILL.md) | Create actionable tasks for developers and Junie, each with scope, candidate files, dependencies, tests, risks, and definition of done. | medium | Team Leader / Developer |
| [`delivery-risk-radar`](../skills/delivery-risk-radar/SKILL.md) | Provide a concise risk radar before scope, schedule, or quality problems become late surprises. | medium | Team Leader / Application Manager |
| [`green-border-plan`](../skills/green-border-plan/SKILL.md) | Plan unit, integration, contract, regression, and legacy characterization tests needed before and during implementation. | medium | Team Leader / QA |

---

## team-planning
**Trigger:** `team_planning` · **Owner:** Team Leader · **Duration:** 30 min

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`developer-readiness-check`](../skills/developer-readiness-check/SKILL.md) | Prevent developers from starting work on stories that are not implementable, testable, scoped, or approved enough. | medium | Team Leader / Developer |
| [`epic-story-partitioning`](../skills/epic-story-partitioning/SKILL.md) | Review epic sibling stories for overlap, missing slices, hidden dependencies, oversized stories, and weak acceptance boundaries. | medium | BA / PO / Team Leader |
| [`team-execution-plan`](../skills/team-execution-plan/SKILL.md) | Turn scope into a practical implementation sequence with owners, parallel work, dependencies, and review gates. | medium | Team Leader |
| [`delivery-risk-radar`](../skills/delivery-risk-radar/SKILL.md) | Provide a concise risk radar before scope, schedule, or quality problems become late surprises. | medium | Team Leader / Application Manager |
| [`review-load-balancing`](../skills/review-load-balancing/SKILL.md) | Help Team Leaders and reviewers spend review time on the riskiest areas first. | low | Team Leader |
| [`source-impact-map`](../skills/source-impact-map/SKILL.md) | Identify files and components to probably modify, inspect before deciding, and avoid unless approved. | medium | Team Leader / Developer |
| [`technical-task-breakdown`](../skills/technical-task-breakdown/SKILL.md) | Create actionable tasks for developers and Junie, each with scope, candidate files, dependencies, tests, risks, and definition of done. | medium | Team Leader / Developer |
| [`green-border-plan`](../skills/green-border-plan/SKILL.md) | Plan unit, integration, contract, regression, and legacy characterization tests needed before and during implementation. | medium | Team Leader / QA |
| [`developer-handoff`](../skills/developer-handoff/SKILL.md) | Generate a practical handoff document explaining what was developed, why, how to read the change, and what future developers must know. | low | Developer / Team Leader |

---

## architecture-review
**Trigger:** `architecture_review` · **Owner:** Architect · **Duration:** 30 min

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`architecture-decision-record`](../skills/architecture-decision-record/SKILL.md) | Generate or review an ADR so architectural choices are explicit, reviewable, and reusable by later agents. | medium | Architect |
| [`non-functional-requirements-review`](../skills/non-functional-requirements-review/SKILL.md) | Make quality-attribute risk explicit before implementation or merge. | medium | Architect / Team Leader / Security |
| [`service-boundary-fit`](../skills/service-boundary-fit/SKILL.md) | Detect boundary drift before it becomes hidden coupling, duplicated ownership, unsafe data access, or ambiguous service responsibility. | medium | Architect / Team Leader |
| [`architecture-drift-detection`](../skills/architecture-drift-detection/SKILL.md) | Find where actual branch changes diverge from approved architecture and recorded decisions. | high | Architect / Team Leader |
| [`architecture-risk`](../skills/architecture-risk/SKILL.md) | Review transaction boundaries, sync/async flows, idempotency, retries, feature flags, bounded contexts, and forbidden zones. | medium | Architect / Team Leader |
| [`cross-service-contract`](../skills/cross-service-contract/SKILL.md) | Check payloads, schemas, Kafka topics, error mapping, retry policy, timeout, idempotency, versioning, and ownership. | medium | Team Leader / Architect |
| [`trust-boundary-review`](../skills/trust-boundary-review/SKILL.md) | Detect missing authorization, unsafe data propagation, insufficient validation, PII leakage, and inconsistent trust assumptions between services. | high | Security / Architect |
| [`liquibase-production-risk`](../skills/liquibase-production-risk/SKILL.md) | Detect lock risks, missing rollback, unsafe index operations, large table updates, destructive DDL, drift concerns, and traffic-aware ordering issues. | high | DBA / Team Leader |

---

## dev-assist
**Trigger:** `during_development` · **Owner:** Developer · **Duration:** 10 min · **Runner:** Junie (preferred)

Supports the developer while writing code — before any diff exists. Organized in three phases:

**Fase A — Orientamento (prima di toccare codice)**

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`source-impact-map`](../skills/source-impact-map/SKILL.md) | Prospective use: identify callers and dependent files before writing, not after. | medium | Team Leader / Developer |
| [`known-pitfalls-extraction`](../skills/known-pitfalls-extraction/SKILL.md) | Surface known project pitfalls before the developer can repeat them. | low | Team Leader / Architect |
| [`legacy-characterization`](../skills/legacy-characterization/SKILL.md) | Capture current legacy behavior before refactoring so regressions are visible. Must run before touching the code, not after. | medium | Developer |

**Fase B — Progettazione e implementazione**

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`concurrency-risk`](../skills/concurrency-risk/SKILL.md) | Find race conditions, lost updates, non-idempotent retry behavior, and unsafe shared state. Maximum value before writing the concurrent code. | high | Architect / Team Leader |
| [`architecture-risk`](../skills/architecture-risk/SKILL.md) | Validate service boundaries and forbidden zones before implementing a cross-service call. | medium | Architect / Team Leader |
| [`developer-decision-review`](../skills/developer-decision-review/SKILL.md) | Challenge implementation choices while the developer can still change direction at zero cost. | medium | Developer / Team Leader |
| [`change-impact-preview`](../skills/change-impact-preview/SKILL.md) | What-if: describe a planned change in natural language and get callers impacted, contract risks, concurrency flags, tests to update, and a suggested approach — before writing a single line. | low | Developer |
| [`java-performance-smell`](../skills/java-performance-smell/SKILL.md) | Flag N+1 queries, inefficient loops, unnecessary synchronization, and blocking calls before they are committed. | medium | Team Leader / Developer |

**Fase C — Piano di test**

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`unit-test-gap`](../skills/unit-test-gap/SKILL.md) | Plan which unit tests are needed while still implementing, not after. | low | Developer |
| [`integration-test-gap`](../skills/integration-test-gap/SKILL.md) | Identify integration test needs early to avoid rework of the implementation. | medium | Developer / QA |

---

## pre-commit
**Trigger:** `pre_commit` · **Owner:** Developer · **Duration:** 8 min

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`liquibase-syntax`](../skills/liquibase-syntax/SKILL.md) | Catch malformed changelogs, duplicate identifiers, missing author/id fields, invalid include paths, and obvious structural issues before deeper review. | low | Developer |
| [`null-safety-risk`](../skills/null-safety-risk/SKILL.md) | Detect unsafe null/nil/undefined dereferences, missing null guards, optional misuse, incomplete validation, and mapper assumptions. | medium | Developer |
| [`unit-test-gap`](../skills/unit-test-gap/SKILL.md) | Verify changed branches, validators, mappers, error paths, and null handling have meaningful unit tests. | low | Developer |
| [`pre-review-defect`](../skills/pre-review-defect/SKILL.md) | Catch possible NPEs, bad error handling, missing validations, hidden side effects, suspicious mapping, and poor readability. | medium | Team Leader / Developer |
| [`liquibase-production-risk`](../skills/liquibase-production-risk/SKILL.md) | Detect lock risks, missing rollback, unsafe index operations, large table updates, destructive DDL, and traffic-aware ordering issues. | high | DBA / Team Leader |
| [`green-border-plan`](../skills/green-border-plan/SKILL.md) | Plan unit, integration, contract, regression, and legacy characterization tests needed before and during implementation. | medium | Team Leader / QA |
| [`developer-decision-review`](../skills/developer-decision-review/SKILL.md) | Challenge implementation choices by asking targeted "why" questions about non-obvious decisions, plan drift, and implicit trade-offs. | medium | Developer / Team Leader |
| [`development-summary`](../skills/development-summary/SKILL.md) | Document assumptions, decisions, clarifications, implemented changes, tests, risks, and unresolved items for team alignment. | low | Developer / Team Leader |
| [`knowledge-transfer-brief`](../skills/knowledge-transfer-brief/SKILL.md) | Create a developer-facing brief for walkthrough calls: what to inspect first, why choices were made, what risks remain, what needs confirmation. | low | Developer / Team Leader |
| [`developer-handoff`](../skills/developer-handoff/SKILL.md) | Generate a practical handoff document explaining what was developed, why, how to read the change, and what future developers must know. | low | Developer / Team Leader |

---

## pre-push
**Trigger:** `pre_push` · **Owner:** Developer · **Duration:** 10 min

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`liquibase-syntax`](../skills/liquibase-syntax/SKILL.md) | Catch malformed changelogs, duplicate identifiers, missing author/id fields, and invalid include paths before deeper review. | low | Developer |
| [`null-safety-risk`](../skills/null-safety-risk/SKILL.md) | Detect unsafe null/nil/undefined dereferences, missing null guards, optional misuse, incomplete validation, and mapper assumptions. | medium | Developer |
| [`unit-test-gap`](../skills/unit-test-gap/SKILL.md) | Verify changed branches, validators, mappers, error paths, and null handling have meaningful unit tests. | low | Developer |
| [`integration-test-gap`](../skills/integration-test-gap/SKILL.md) | Ensure persistence, transaction boundaries, messaging, HTTP clients, and external failures are validated beyond unit tests. | medium | Developer / QA |
| [`legacy-characterization`](../skills/legacy-characterization/SKILL.md) | Capture current behavior before refactoring or modifying legacy code so regressions are visible. | medium | Developer |
| [`flaky-failure-classification`](../skills/flaky-failure-classification/SKILL.md) | Reduce testing churn by distinguishing real failures from environment, data, timing, and setup problems. | low | Developer / QA |
| [`pre-review-defect`](../skills/pre-review-defect/SKILL.md) | Catch possible NPEs, bad error handling, missing validations, hidden side effects, suspicious mapping, and poor readability. | medium | Team Leader / Developer |
| [`liquibase-production-risk`](../skills/liquibase-production-risk/SKILL.md) | Detect lock risks, missing rollback, unsafe index operations, large table updates, destructive DDL, and traffic-aware ordering issues. | high | DBA / Team Leader |
| [`regression-selection`](../skills/regression-selection/SKILL.md) | Select a defensible subset of existing tests related to changed files and risk areas to reduce slow feedback loops. | low | Developer / QA |
| [`test-quality`](../skills/test-quality/SKILL.md) | Find assertion-free tests, overmocking, snapshot-only assertions, order dependency, excessive sleeps, and flaky patterns. | low | QA / Team Leader |
| [`green-border-plan`](../skills/green-border-plan/SKILL.md) | Plan unit, integration, contract, regression, and legacy characterization tests needed before and during implementation. | medium | Team Leader / QA |

---

## jessica-fletcher
**Trigger:** `before_commit` · **Owner:** Developer · **Duration:** 15 min

Reads Jira story evidence when issue keys are available and compares the branch
against story text and acceptance criteria before ranking production failure
hypotheses.

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`production-premortem`](../skills/production-premortem/SKILL.md) | Analyze branch changes from the incident question: "This code is causing production problems — find the reasons." Rank failure modes by plausibility and blast radius. | high | Team Leader / Architect / Developer |
| [`pre-review-defect`](../skills/pre-review-defect/SKILL.md) | Catch possible NPEs, bad error handling, missing validations, hidden side effects, suspicious mapping, and poor readability. | medium | Team Leader / Developer |
| [`architecture-risk`](../skills/architecture-risk/SKILL.md) | Review transaction boundaries, sync/async flows, idempotency, retries, feature flags, bounded contexts, and forbidden zones. | medium | Architect / Team Leader |
| [`cross-service-contract`](../skills/cross-service-contract/SKILL.md) | Check payloads, schemas, Kafka topics, error mapping, retry policy, timeout, idempotency, versioning, and ownership. | medium | Team Leader / Architect |
| [`liquibase-production-risk`](../skills/liquibase-production-risk/SKILL.md) | Detect lock risks, missing rollback, unsafe index operations, large table updates, destructive DDL, and traffic-aware ordering issues. | high | DBA / Team Leader |
| [`rollback-safety`](../skills/rollback-safety/SKILL.md) | Prevent production recovery failures caused by missing, unsafe, or untested rollback instructions. | high | DBA / Developer |
| [`test-quality`](../skills/test-quality/SKILL.md) | Find assertion-free tests, overmocking, snapshot-only assertions, order dependency, excessive sleeps, and flaky patterns. | low | QA / Team Leader |
| [`regression-selection`](../skills/regression-selection/SKILL.md) | Select a defensible subset of existing tests related to changed files and risk areas to reduce slow feedback loops. | low | Developer / QA |

---

## branch-ready
**Trigger:** `before_pr` · **Owner:** Developer / Team Leader · **Duration:** 20 min

Uses story evidence, planning artifacts, and branch diff together to detect
missing requested behavior, unrequested scope, contradicted acceptance criteria,
plan drift, missing tests, and unresolved risk before PR.

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`source-impact-map`](../skills/source-impact-map/SKILL.md) | Identify files and components to probably modify, inspect before deciding, and avoid unless approved. | medium | Team Leader / Developer |
| [`technical-task-breakdown`](../skills/technical-task-breakdown/SKILL.md) | Create actionable tasks for developers and Junie, each with scope, candidate files, dependencies, tests, risks, and definition of done. | medium | Team Leader / Developer |
| [`green-border-plan`](../skills/green-border-plan/SKILL.md) | Plan unit, integration, contract, regression, and legacy characterization tests needed before and during implementation. | medium | Team Leader / QA |
| [`regression-selection`](../skills/regression-selection/SKILL.md) | Select a defensible subset of existing tests related to changed files and risk areas to reduce slow feedback loops. | low | Developer / QA |
| [`pre-review-defect`](../skills/pre-review-defect/SKILL.md) | Catch possible NPEs, bad error handling, missing validations, hidden side effects, suspicious mapping, and poor readability. | medium | Team Leader / Developer |
| [`developer-decision-review`](../skills/developer-decision-review/SKILL.md) | Challenge implementation choices by asking targeted "why" questions about non-obvious decisions, plan drift, and implicit trade-offs. | medium | Developer / Team Leader |
| [`architecture-risk`](../skills/architecture-risk/SKILL.md) | Review transaction boundaries, sync/async flows, idempotency, retries, feature flags, bounded contexts, and forbidden zones. | medium | Architect / Team Leader |
| [`cross-service-contract`](../skills/cross-service-contract/SKILL.md) | Check payloads, schemas, Kafka topics, error mapping, retry policy, timeout, idempotency, versioning, and ownership. | medium | Team Leader / Architect |
| [`liquibase-syntax`](../skills/liquibase-syntax/SKILL.md) | Catch malformed changelogs, duplicate identifiers, missing author/id fields, and invalid include paths before deeper review. | low | Developer |
| [`liquibase-production-risk`](../skills/liquibase-production-risk/SKILL.md) | Detect lock risks, missing rollback, unsafe index operations, large table updates, destructive DDL, and traffic-aware ordering issues. | high | DBA / Team Leader |
| [`rollback-safety`](../skills/rollback-safety/SKILL.md) | Prevent production recovery failures caused by missing, unsafe, or untested rollback instructions. | high | DBA / Developer |
| [`database-drift`](../skills/database-drift/SKILL.md) | Identify manual hotfixes, missing changelogs, unexpected indexes, and environment differences before deployment. | medium | DBA / Operations |
| [`test-quality`](../skills/test-quality/SKILL.md) | Find assertion-free tests, overmocking, snapshot-only assertions, order dependency, excessive sleeps, and flaky patterns. | low | QA / Team Leader |

---

## ci-validation
**Trigger:** `pull_request` · **Owner:** CI / Team Leader · **Duration:** 30 min

Same skills as `branch-ready`, plus `development-summary`:

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`source-impact-map`](../skills/source-impact-map/SKILL.md) | Identify files and components to probably modify, inspect before deciding, and avoid unless approved. | medium | Team Leader / Developer |
| [`technical-task-breakdown`](../skills/technical-task-breakdown/SKILL.md) | Create actionable tasks for developers and Junie, each with scope, candidate files, dependencies, tests, risks, and definition of done. | medium | Team Leader / Developer |
| [`green-border-plan`](../skills/green-border-plan/SKILL.md) | Plan unit, integration, contract, regression, and legacy characterization tests needed before and during implementation. | medium | Team Leader / QA |
| [`regression-selection`](../skills/regression-selection/SKILL.md) | Select a defensible subset of existing tests related to changed files and risk areas to reduce slow feedback loops. | low | Developer / QA |
| [`pre-review-defect`](../skills/pre-review-defect/SKILL.md) | Catch possible NPEs, bad error handling, missing validations, hidden side effects, suspicious mapping, and poor readability. | medium | Team Leader / Developer |
| [`architecture-risk`](../skills/architecture-risk/SKILL.md) | Review transaction boundaries, sync/async flows, idempotency, retries, feature flags, bounded contexts, and forbidden zones. | medium | Architect / Team Leader |
| [`cross-service-contract`](../skills/cross-service-contract/SKILL.md) | Check payloads, schemas, Kafka topics, error mapping, retry policy, timeout, idempotency, versioning, and ownership. | medium | Team Leader / Architect |
| [`liquibase-syntax`](../skills/liquibase-syntax/SKILL.md) | Catch malformed changelogs, duplicate identifiers, missing author/id fields, and invalid include paths before deeper review. | low | Developer |
| [`liquibase-production-risk`](../skills/liquibase-production-risk/SKILL.md) | Detect lock risks, missing rollback, unsafe index operations, large table updates, destructive DDL, and traffic-aware ordering issues. | high | DBA / Team Leader |
| [`rollback-safety`](../skills/rollback-safety/SKILL.md) | Prevent production recovery failures caused by missing, unsafe, or untested rollback instructions. | high | DBA / Developer |
| [`database-drift`](../skills/database-drift/SKILL.md) | Identify manual hotfixes, missing changelogs, unexpected indexes, and environment differences before deployment. | medium | DBA / Operations |
| [`test-quality`](../skills/test-quality/SKILL.md) | Find assertion-free tests, overmocking, snapshot-only assertions, order dependency, excessive sleeps, and flaky patterns. | low | QA / Team Leader |
| [`development-summary`](../skills/development-summary/SKILL.md) | Document assumptions, decisions, clarifications, implemented changes, tests, risks, and unresolved items for team alignment. | low | Developer / Team Leader |

---

## pr-ready
**Trigger:** `pr_ready` · **Owner:** Developer · **Duration:** 15 min

Builds the PR package from branch evidence and story evidence, ensuring the PR
description, reviewer focus, risks, and tests reflect what the story actually
asked for.

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`development-summary`](../skills/development-summary/SKILL.md) | Document assumptions, decisions, clarifications, implemented changes, tests, risks, and unresolved items for team alignment. | low | Developer / Team Leader |
| [`developer-handoff`](../skills/developer-handoff/SKILL.md) | Generate a practical handoff document explaining what was developed, why, how to read the change, and what future developers must know. | low | Developer / Team Leader |
| [`developer-decision-review`](../skills/developer-decision-review/SKILL.md) | Challenge implementation choices by asking targeted "why" questions about non-obvious decisions, plan drift, and implicit trade-offs. | medium | Developer / Team Leader |
| [`pre-review-defect`](../skills/pre-review-defect/SKILL.md) | Catch possible NPEs, bad error handling, missing validations, hidden side effects, suspicious mapping, and poor readability. | medium | Team Leader / Developer |
| [`architecture-risk`](../skills/architecture-risk/SKILL.md) | Review transaction boundaries, sync/async flows, idempotency, retries, feature flags, bounded contexts, and forbidden zones. | medium | Architect / Team Leader |
| [`cross-service-contract`](../skills/cross-service-contract/SKILL.md) | Check payloads, schemas, Kafka topics, error mapping, retry policy, timeout, idempotency, versioning, and ownership. | medium | Team Leader / Architect |
| [`liquibase-production-risk`](../skills/liquibase-production-risk/SKILL.md) | Detect lock risks, missing rollback, unsafe index operations, large table updates, destructive DDL, and traffic-aware ordering issues. | high | DBA / Team Leader |
| [`test-quality`](../skills/test-quality/SKILL.md) | Find assertion-free tests, overmocking, snapshot-only assertions, order dependency, excessive sleeps, and flaky patterns. | low | QA / Team Leader |

---

## requested-pr-review
**Trigger:** `reviewer_requested` · **Owner:** Reviewer / Team Leader · **Duration:** 30 min

Uses read-only GitHub CLI access when available to find open PRs where the user
is a requested reviewer, or to analyze one explicit PR with `--pr <number>`,
rank them by review risk, and run only the review skills relevant to each
selected PR diff. When Jira issue keys are available from the PR branch/title or
profile input, it reads the story and compares the PR against story text and
acceptance criteria. With `--publish-high-risk-comments`, the agent may publish
one PR comment containing only blocker or high-criticality findings from that
run.

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`pre-review-defect`](../skills/pre-review-defect/SKILL.md) | Catch likely code defects and review churn before line-by-line human review. | medium | Team Leader / Developer |
| [`architecture-risk`](../skills/architecture-risk/SKILL.md) | Review transaction boundaries, sync/async flows, idempotency, retries, feature flags, bounded contexts, and forbidden zones. | medium | Architect / Team Leader |
| [`cross-service-contract`](../skills/cross-service-contract/SKILL.md) | Check payloads, schemas, Kafka topics, error mapping, retry policy, timeout, idempotency, versioning, and ownership. | medium | Team Leader / Architect |
| [`liquibase-production-risk`](../skills/liquibase-production-risk/SKILL.md) | Detect lock risks, missing rollback, unsafe index operations, large table updates, destructive DDL, drift concerns, and traffic-aware ordering issues. | high | DBA / Team Leader |
| [`test-quality`](../skills/test-quality/SKILL.md) | Find assertion-free tests, overmocking, snapshot-only assertions, order dependency, excessive sleeps, and flaky patterns. | low | QA / Team Leader |
| [`regression-selection`](../skills/regression-selection/SKILL.md) | Select a defensible subset of existing tests related to changed files and risk areas to reduce slow feedback loops. | low | Developer / QA |

---

## am-release-ready
**Trigger:** `release_ready` · **Owner:** Application Manager · **Duration:** 25 min

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`release-impact-summary`](../skills/release-impact-summary/SKILL.md) | Translate a technical change into release impact for go/no-go discussion, communication, deployment planning, rollback, and support readiness. | medium | Application Manager / Team Leader |
| [`incident-risk-forecast`](../skills/incident-risk-forecast/SKILL.md) | Answer: "If this change causes trouble in production, what are the most likely symptoms, triggers, blind spots, and mitigations?" | medium | Application Manager / Team Leader / SRE |
| [`business-continuity-check`](../skills/business-continuity-check/SKILL.md) | Detect whether a change can interrupt business operations even when code and tests appear correct. | high | Application Manager / Operations |
| [`rollback-safety`](../skills/rollback-safety/SKILL.md) | Prevent production recovery failures caused by missing, unsafe, or untested rollback instructions. | high | DBA / Developer |
| [`known-pitfalls-extraction`](../skills/known-pitfalls-extraction/SKILL.md) | Turn recurring problems into explicit knowledge that future planning, review, and testing can reuse. | low | Team Leader / Architect |
| [`delivery-risk-radar`](../skills/delivery-risk-radar/SKILL.md) | Provide a concise risk radar before scope, schedule, or quality problems become late surprises. | medium | Team Leader / Application Manager |

---

## team-coaching-review
**Trigger:** `coaching_review` · **Owner:** Team Leader · **Duration:** 30 min

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`pre-review-defect`](../skills/pre-review-defect/SKILL.md) | Catch possible NPEs, bad error handling, missing validations, hidden side effects, suspicious mapping, and poor readability — run per contributor. | medium | Team Leader / Developer |
| [`test-quality`](../skills/test-quality/SKILL.md) | Find assertion-free tests, overmocking, snapshot-only assertions, order dependency, and flaky patterns — run per contributor. | low | QA / Team Leader |
| [`null-safety-risk`](../skills/null-safety-risk/SKILL.md) | Detect unsafe null/nil/undefined dereferences, missing null guards, optional misuse, and mapper assumptions — run per contributor. | medium | Developer |
| [`java-performance-smell`](../skills/java-performance-smell/SKILL.md) | Flag N+1 queries, inefficient loops, unnecessary synchronization, blocking calls, excessive object creation, and connection pool misuse. | medium | Team Leader / Developer |
| [`known-pitfalls-extraction`](../skills/known-pitfalls-extraction/SKILL.md) | Cross-reference contributor findings against known project pitfalls documented in the team's knowledge base. | low | Team Leader / Architect |
| [`contributor-pattern-analysis`](../skills/contributor-pattern-analysis/SKILL.md) | Aggregate quality findings for a single contributor and identify recurring growth patterns (habit / tendency / isolated) for coaching purposes. | low | Team Leader |

---

## tutorial
**Trigger:** `tutorial_request` · **Owner:** Any · **Duration:** 15 min

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`mana-usage-help`](../skills/mana-usage-help/SKILL.md) | Guide a user through the framework by recommending the next profile, agent, skill, template, or fallback for their situation. | low | Developer / Team Leader |
| [`profile-selector`](../skills/profile-selector/SKILL.md) | Map a user's natural language description of their situation, role, or goal to the correct Mana profile, and optionally persist the selection. | low | Developer / Team Leader / Architect / Application Manager |

---

## mana-help
**Trigger:** `help_request` · **Owner:** Any · **Duration:** 5 min

| Skill | Description | Risk | Owner |
|---|---|---|---|
| [`mana-usage-help`](../skills/mana-usage-help/SKILL.md) | Guide a user through the framework by recommending the next profile, agent, skill, template, or fallback for their situation. | low | Developer / Team Leader |
| [`profile-selector`](../skills/profile-selector/SKILL.md) | Map a user's natural language description of their situation, role, or goal to the correct Mana profile, and optionally persist the selection. | low | Developer / Team Leader / Architect / Application Manager |

---

## Standalone Skills

These skills are implemented and available in the framework but are not yet
wired into a profile. They can be invoked directly by an agent or added to
a custom profile.

| Skill | Description | Risk | Owner | Agent |
|---|---|---|---|---|
| [`post-merge-incident-learning`](../skills/post-merge-incident-learning/SKILL.md) | Close the loop after incidents by identifying missed signals and updating future guardrails. | medium | Team Leader / Architect | `learning-agent` |
| [`rule-update-suggestion`](../skills/rule-update-suggestion/SKILL.md) | Convert lessons into proposed governance updates without automatically changing enforced rules. | medium | Architect / Team Leader | `learning-agent` |

> `learning-agent` uses `post-merge-incident-learning`, `rule-update-suggestion`,
> `known-pitfalls-extraction`, and `flaky-failure-classification` but no
> dedicated profile triggers it yet. Add a `learning` profile to enable it.

---

## Quick Reference: Skills by Risk Level

### High Risk
| Skill | Profiles |
|---|---|
| `architecture-drift-detection` | architecture-review |
| `business-continuity-check` | am-release-ready |
| `concurrency-risk` | dev-assist |
| `liquibase-production-risk` | story-start, architecture-review, pre-commit, jessica-fletcher, branch-ready, pr-ready, requested-pr-review, ci-validation, pre-push |
| `production-premortem` | jessica-fletcher |
| `rollback-safety` | jessica-fletcher, branch-ready, am-release-ready, ci-validation |
| `trust-boundary-review` | architecture-review |

### Medium Risk
| Skill | Profiles |
|---|---|
| `architecture-decision-record` | architecture-review |
| `architecture-risk` | story-start, architecture-review, dev-assist, jessica-fletcher, branch-ready, pr-ready, requested-pr-review, ci-validation |
| `cross-service-contract` | story-start, architecture-review, jessica-fletcher, branch-ready, pr-ready, requested-pr-review, ci-validation |
| `database-drift` | branch-ready, ci-validation |
| `delivery-risk-radar` | story-ready-for-dev, team-planning, am-release-ready |
| `developer-decision-review` | dev-assist, pre-commit, branch-ready, pr-ready |
| `developer-readiness-check` | story-ready-for-dev, team-planning |
| `epic-story-partitioning` | story-ready-for-dev, team-planning |
| `flaky-failure-classification` | pre-push |
| `green-border-plan` | story-start, story-ready-for-dev, team-planning, pre-commit, branch-ready, ci-validation, pre-push |
| `incident-risk-forecast` | am-release-ready |
| `integration-test-gap` | dev-assist, pre-push |
| `java-performance-smell` | dev-assist, team-coaching-review |
| `legacy-characterization` | dev-assist, pre-push |
| `non-functional-requirements-review` | architecture-review |
| `null-safety-risk` | pre-commit, pre-push, team-coaching-review |
| `post-merge-incident-learning` | — |
| `pre-review-defect` | pre-commit, jessica-fletcher, branch-ready, pr-ready, requested-pr-review, ci-validation, pre-push, team-coaching-review |
| `release-impact-summary` | am-release-ready |
| `rule-update-suggestion` | — |
| `service-boundary-fit` | architecture-review |
| `source-impact-map` | story-start, story-ready-for-dev, team-planning, dev-assist, branch-ready, ci-validation |
| `team-execution-plan` | team-planning |
| `technical-task-breakdown` | story-start, story-ready-for-dev, team-planning, branch-ready, ci-validation |

### Low Risk
| Skill | Profiles |
|---|---|
| `acceptance-criteria-testability` | story-start, story-ready-for-dev |
| `change-impact-preview` | dev-assist |
| `contributor-pattern-analysis` | team-coaching-review |
| `developer-handoff` | team-planning, pre-commit, pr-ready |
| `development-summary` | pre-commit, pr-ready, ci-validation |
| `epic-goal-extraction` | story-start |
| `knowledge-transfer-brief` | pre-commit |
| `known-pitfalls-extraction` | dev-assist, am-release-ready, team-coaching-review |
| `liquibase-syntax` | pre-commit, branch-ready, ci-validation, pre-push |
| `mana-usage-help` | tutorial, mana-help |
| `profile-selector` | tutorial, mana-help |
| `regression-selection` | jessica-fletcher, branch-ready, requested-pr-review, ci-validation, pre-push |
| `review-load-balancing` | team-planning |
| `story-consistency` | story-start |
| `story-depth` | story-start |
| `test-quality` | jessica-fletcher, branch-ready, pr-ready, requested-pr-review, ci-validation, pre-push, team-coaching-review |
| `unit-test-gap` | dev-assist, pre-commit, pre-push |
