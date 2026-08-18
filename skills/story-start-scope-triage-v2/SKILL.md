---
name: story-start-scope-triage-v2
version: 0.1.0
description: Classifies every Discovery v2 finding without turning discovery into implementation scope.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - read_files
inputs:
  - normalized_story
  - mana.story-start.discovery-inventory/v2
outputs:
  - mana.story-start.scope-triage/v2
risk_level: medium
model_tier: economy
execution_mode: read
delegation_group: requirements
parallel_safe: false
owner_role: Team Leader / Product Owner
stack:
  - any
tags:
  - planning
  - triage
  - scope
---

# Story Start Scope Triage v2

## Purpose

Place a deterministic classification boundary between discovery and planning.
Evidence found is not scope approved. This phase explains inclusion or
exclusion but creates no task, estimate, or final report.

## When To Use It

- After Discovery v2 has produced a schema-valid, normalized inventory.
- Before Implementation Planner v2, while findings, constraints, decisions,
  and owner-review needs are still explicit.

## When Not To Use It

- Do not use it to read the repository, ticket system, network, or raw context.
- Do not use it to create implementation tasks, estimates, or rendered output.
- Do not replace missing evidence with a proposed subsystem or assumed fact.

## Inputs

- The compact normalized story and acceptance criteria.
- One validated `mana.story-start.discovery-inventory/v2` artifact containing
  all repository/project constraints and current human decision states.

## Outputs

- One strict `mana.story-start.scope-triage/v2` object.
- Exactly one classification for every discovery finding.
- Preserved decisions and stable option groups for alternatives.
- Explicit validation and owner-review state for evidence gaps.

## Classification Rules

- `VERIFIED_FACT`: observed information; never work by itself.
- `CORE_SCOPE`: directly required by an explicit AC/requirement; the only
  category eligible for `includedInBasePlan: true`.
- `REQUIRED_ENABLER`: causally necessary for an AC, story regression, or a
  mandatory security, compliance, authorization, or data-integrity constraint.
- `CONDITIONAL_SCOPE`: relevant only under an unresolved decision, assumption,
  or external contract; always excluded from the base plan while conditional.
- `READINESS_PREREQUISITE`: needed before implementation or before trusting
  the plan; not automatically engineering scope.
- `RELATED_DEFECT`: pre-existing, independent, not aggravated by the story,
  and separately remediable.
- `RISK_ONLY`: uncertainty without certain implementation work.
- `OPTIONAL_IMPROVEMENT`: useful cleanup or hardening not required by the story.

## Promotion Test

Before `CORE_SCOPE` or `REQUIRED_ENABLER`, answer structurally:

1. Which AC or mandatory constraint fails without the work?
2. Which evidence proves that dependency?
3. Did the issue predate the story?
4. Does the work depend on an unresolved decision?
5. Would the story introduce or materially aggravate the issue?

No AC/constraint reference means no promotion. A story-introduced regression
or mandatory security/data-integrity failure is a separately visible
`REQUIRED_ENABLER`, even when the underlying issue predates the story.

## Decision Rules

- Preserve open decisions with `selectedOptionId: null`.
- Put mutually exclusive options in a stable `optionGroup` with
  `selectionRule: exactly_one`; never combine them or select the robust option.
- Route missing evidence to `RISK_ONLY` plus `needs_owner_review`, retaining an
  evidence gap and suggested owner.
- Keep independent defects and optional improvements outside base scope.

## Host Boundary

`scripts/lib/story-start-scope-v2.sh` uses the existing provider synthesis
dispatch in an isolated workspace. Host code validates the raw SS01 triage
schema, checks discovery coverage and reference provenance, derives stable IDs
and ordering, then validates again. There is no free-form fallback. The phase
remains internal and non-default until SS06.

## Output Standard

Follow `docs/standards/agent-skill-output-standard.md` and the strict v2
schema. Internal reasoning must use compact caveman mode: terse,
evidence-first notes without private chain-of-thought. Maintain a context budget
containing only the story objective, artifact IDs, evidence-backed promotion
answers, open decisions, discarded hypotheses, and next owner question.
