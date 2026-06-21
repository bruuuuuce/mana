---
name: architecture-decision-record
version: 1.0.0
description: Creates or reviews Architecture Decision Records with context, decision, alternatives, consequences, owners, and approval status.
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
  - design_context
  - options_considered
  - constraints
  - branch_diff
  - architecture_rules
outputs:
  - architecture_decision_record
  - decision_questions
  - tradeoff_summary
risk_level: medium
owner_role: Architect
tags:
  - architecture
  - decision-record
  - governance
---

# Architecture Decision Record

## Purpose
Generate or review an ADR so architectural choices are explicit, reviewable, and reusable by later agents.

## When To Use It
- When a story introduces a new pattern, cross-service flow, persistence model, dependency, integration contract, or meaningful trade-off.
- When an implementation diverges from the original plan.
- Before architecture approval gates.

## Inputs
- design_context
- options_considered
- constraints
- branch_diff
- architecture_rules

## Outputs
- architecture_decision_record
- decision_questions
- tradeoff_summary

## Execution Logic
1. Capture context, decision, status, owner, date, constraints, alternatives, consequences, and follow-ups.
2. Separate confirmed facts from assumptions.
3. Check whether the decision conflicts with engineering guards or existing architecture.
4. Ask targeted questions where rationale is missing.

## Decision Rules
- `blocker`: decision violates an architecture guard or lacks owner approval for a high-risk trade-off.
- `warning`: alternatives or consequences are under-specified.
- `info`: ADR improvement, naming, or traceability suggestion.

## Failure Modes
- ADR quality depends on design context quality.
- Missing alternatives can hide better options.

## Required Human Review
Architect owns the ADR decision and approval. Team Leader reviews implementation feasibility.

## Service Context Layer
Read `.mana/global/architecture.md`, `engineering-guards.md`, and `team-decisions/` when available.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts.

## Example Output
```yaml
skill: architecture-decision-record
status: warning
summary: "ADR drafted but alternatives and rollback consequences need architect confirmation."
outputs:
  - architecture_decision_record
  - decision_questions
  - tradeoff_summary
human_review_required: true
```
