---
name: story-start-implementation-planner-v2
version: 0.1.0
description: Produces a small evidence-backed base plan plus mandatory, conditional, readiness, and excluded deltas from Scope Triage v2.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - read_files
inputs:
  - normalized_story
  - mana.story-start.planning-context/v2
  - mana.story-start.scope-triage/v2
outputs:
  - mana.story-start.implementation-plan/v2
risk_level: medium
model_tier: economy
execution_mode: read
delegation_group: requirements
parallel_safe: false
owner_role: Team Leader / Developer
stack:
  - any
tags:
  - planning
  - estimation
  - scope
---

# Story Start Implementation Planner v2

## Purpose

Turn an approved Scope Triage classification into a small base plan and
explicit deltas. Preserve why work is base, mandatory, conditional, readiness,
or excluded instead of constructing one inflated superset plan.

## When To Use It

- After Discovery v2 and Scope Triage v2 are validated and normalized.
- Before Scope Governor v2 and before any public Story Start rendering.
- When scenario estimates are needed while material decisions remain open.

## When Not To Use It

- Do not read a repository, ticket system, network, or raw Discovery findings.
- Do not reclassify scope, resolve human decisions, or infer missing evidence.
- Do not produce a final committed estimate while material decisions are open.
- Do not include related defects or optional improvements without an approved
  scope-expansion record.

## Inputs

- A normalized story containing its acceptance criteria.
- A compact host-derived planning context containing only referenced ACs,
  constraints, evidence, and bounded provenance.
- One validated `mana.story-start.scope-triage/v2` artifact.

## Outputs

- One strict `mana.story-start.implementation-plan/v2` artifact.
- Independent readiness, base-plan, required-enabler, conditional-branch,
  decision, scenario, related-finding, and evidence/provenance sections.
- Explicit confidence and owner-review state.

## Planning Rules

### Base Plan

- Create tasks only from `CORE_SCOPE` classifications.
- Cite the owning classification, AC/constraint, evidence, provenance, source
  target, and direct test evidence for every task.
- A `VERIFIED_FACT` may support a task. Existing configuration is reused and
  never becomes a create/add task by itself.

### Required Enablers

- Give every `REQUIRED_ENABLER` a separate entry and `mandatory_delta`.
- Preserve the triage mandatory reason, evidence, and affected AC/constraint.
- Keep it on the critical path without rewriting it as original base scope.

### Conditional Branches

- Create branches only from `CONDITIONAL_SCOPE`, one per decision option.
- Preserve decision, option, condition, relationship, and stable exclusive
  group membership.
- Never choose the more robust option or add sibling exclusive deltas.

### Readiness And Related Findings

- Keep readiness outside implementation work with engineering effort and
  elapsed calendar impact as distinct objects.
- Pending human approval has zero default engineering effort.
- Put `RELATED_DEFECT`, `RISK_ONLY`, and `OPTIONAL_IMPROVEMENT` in the excluded
  related-findings section without tasks.

## Decision Rules

- `ready`: all planning sections and arithmetic validate and no material
  decision or evidence gap requires owner action.
- `needs_owner_review`: retain scenario-only estimates when a material decision,
  evidence gap, or readiness owner action remains open.
- `invalid`: reject category smuggling, ungrounded task provenance, illegal
  branch selection, inconsistent deltas, incorrect arithmetic, or free-form
  output; do not publish a partial plan.

## Estimate Rules

- Label base effort, mandatory deltas, conditional deltas, readiness effort,
  calendar impact, and scenario totals separately.
- A scenario selects exactly one branch from each exactly-one group and only
  combines groups that the triage contract permits.
- The scenario total is the arithmetic sum of base, all mandatory enablers,
  selected conditional branches, and approved expansion deltas.
- Represent every conditional branch in at least one scenario.
- With open material decisions, set `finalCommittedEstimate: null`, mark every
  scenario `scenario_only`, and require owner review.

## Host Boundary

`scripts/lib/story-start-scope-v2.sh` uses the existing isolated provider
synthesis dispatch with the SS01 plan schema. Host code validates the compact
context, triage references, category-to-section coverage, task provenance,
branch legality, estimate arithmetic, stable IDs, and canonical ordering. Raw
and normalized output are schema-validated. Invalid or free-form output fails
closed. This phase remains internal and non-default until SS06.

## Required Human Review

Open material decisions, unresolved evidence gaps, and pending readiness remain
owned by the roles preserved from triage. The planner reports scenarios; it
does not select an option for those owners.

## Output Standard

Follow `docs/standards/agent-skill-output-standard.md` and the strict v2 schema.
Internal reasoning must use compact caveman mode: terse, evidence-first notes
without private chain-of-thought. Maintain a context budget containing only
the story objective, artifact IDs, classified work, evidence/provenance links,
open decisions, scenario arithmetic, and owner-review reasons.
