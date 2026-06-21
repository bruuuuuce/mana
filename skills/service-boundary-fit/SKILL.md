---
name: service-boundary-fit
version: 1.0.0
description: Checks whether a change respects service ownership, bounded context, data ownership, API/event contracts, and responsibility boundaries.
compatibility:
  - codex
  - junie
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
  - confluence_read
  - architecture_rules_read
inputs:
  - story
  - design
  - branch_diff
  - service_context
  - integration_map
outputs:
  - service_boundary_report
  - ownership_questions
  - boundary_risk_items
risk_level: medium
owner_role: Architect / Team Leader
tags:
  - architecture
  - service-boundary
  - ownership
---

# Service Boundary Fit

## Purpose
Detect boundary drift before it becomes hidden coupling, duplicated ownership, unsafe data access, or ambiguous service responsibility.

## When To Use It
- When a change touches APIs, events, domain models, shared libraries, persistence, or cross-service behavior.
- Before architecture review or branch validation.

## Inputs
- story
- design
- branch_diff
- service_context
- integration_map

## Outputs
- service_boundary_report
- ownership_questions
- boundary_risk_items

## Execution Logic
1. Compare proposed or actual changes with service mission, ownership, integration map, and engineering guards.
2. Identify data ownership violations, responsibility leakage, duplicated business logic, contract coupling, and hidden dependencies.
3. Recommend owner clarification, contract adjustment, or safer location for behavior.

## Decision Rules
- `blocker`: unapproved ownership violation, forbidden dependency, or protected-area change.
- `warning`: ambiguous responsibility or medium-risk coupling.
- `info`: documentation or contract clarity suggestion.

## Failure Modes
- Service ownership may be undocumented or split across teams.
- Runtime dependency may be hidden in configuration.

## Required Human Review
Architect confirms boundary decisions. Team Leader confirms implementation scope and ownership handoff.

## Service Context Layer
Read `.mana/global/service-mission.md`, `architecture.md`, `integration-map.md`, `domain-glossary.md`, and `engineering-guards.md` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts.

## Example Output
```yaml
skill: service-boundary-fit
status: warning
summary: "New validation logic may belong to the upstream owner service."
outputs:
  - service_boundary_report
  - ownership_questions
  - boundary_risk_items
human_review_required: true
```
