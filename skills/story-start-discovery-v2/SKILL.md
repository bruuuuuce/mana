---
name: story-start-discovery-v2
version: 0.1.0
description: Produces a neutral, evidence-only Story Start Scope v2 discovery inventory.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
  - jira_read
  - confluence_read
  - architecture_rules_read
inputs:
  - compact_discovery_package
outputs:
  - mana.story-start.discovery-inventory/v2
risk_level: medium
model_tier: economy
execution_mode: read
delegation_group: source
parallel_safe: true
owner_role: Team Leader / Product Owner
stack:
  - any
tags:
  - planning
  - discovery
  - evidence
---

# Story Start Discovery v2

## Purpose

Produce a compact, neutral inventory of evidence for Story Start Scope v2.
Discovery can be broad; it is not authorization to plan, estimate, or select
an architecture. This is discovery, not planning.

## When To Use It

- During the internal Story Start Scope v2 discovery phase, after existing
  context collection has assembled a compact evidence package.
- When evidence, uncertainty, and provenance must be preserved before scope
  triage; never as a replacement for triage or implementation planning.

## When Not To Use It

- Do not use it to create a task breakdown, estimate, or final scope decision.
- Do not use it to reread a repository already summarized in the compact
  package, or to access data outside the approved MCP policy.

## Required Boundary

- Discover and report evidence, facts, constraints, defects, risks,
  ambiguities, readiness conditions, open questions, and decisions.
- Mark each evidence record as observed, reported, inferred, or missing.
- Cite bounded repository, ticket, Service Context, branch, or test provenance.
- Link a finding to an acceptance criterion only when the supplied evidence
  supports that relation.
- Record whether an issue appears pre-existing, introduced, aggravated, or
  unknown, and suggest an owner only when evidence supports one.
- Preserve unresolved alternatives as an open decision with options and
  `selectedOptionId: null`.

Do not decide implementation scope. Do not produce implementation tasks. Do
not estimate remediation work. Do not choose between unresolved architectures.
Do not assume a discovered defect belongs to the current story. Do not turn
missing evidence into a fabricated requirement. Missing information is an
`evidence_gap`, not a request to build a subsystem.

## Inputs And Output

Consume the compact discovery package assembled by existing repository/context
collection. Do not repeat repository traversal and do not inspect outside that
package when used through the internal SS02 phase. Emit exactly one object
conforming to `mana.story-start.discovery-inventory/v2`.

The output contains acceptance criteria, mandatory constraints, evidence,
typed findings, open questions, decisions, provenance, and validation state.
It contains no task list, effort estimate, final scope classification, selected
architecture, or total estimate.

## Outputs

- `mana.story-start.discovery-inventory/v2`, validated and normalized by the
  internal host support before any later phase consumes it.

## Decision Rules

- `blocker`: missing mandatory evidence that prevents responsible discovery;
  represent it as an evidence gap and owner-review need, not invented work.
- `warning`: ambiguity, suspected defect, stale evidence, or pending owner
  approval that requires triage or human resolution.
- `info`: observed fact, configuration, or repository constraint with bounded
  provenance and no implied implementation instruction.

## Host Boundary

`scripts/lib/story-start-scope-v2.sh` invokes the established provider synthesis
argument builder in an isolated read-only workspace, validates the response
against the SS01 discovery schema, derives deterministic IDs, sorts set-valued
collections, and validates the normalized artifact again. This skill remains
internal and non-default until SS06.

## Output Standard

Follow `docs/standards/agent-skill-output-standard.md` and the strict v2
schema. Internal reasoning must use compact caveman mode: terse,
evidence-first notes without private chain-of-thought. Maintain a context budget
with only the objective, compact evidence IDs, checked provenance, open
hypotheses, and next question; do not accumulate repository dumps or repeated
transcripts.
