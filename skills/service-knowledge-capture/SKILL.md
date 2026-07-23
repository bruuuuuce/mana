---
name: service-knowledge-capture
version: 1.0.0
description: Captures evidence-backed service behaviors, constraints, decisions, and unknowns discovered during code analysis into a progressive-load knowledge base for future Mana workflows.
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
  - test_runner_read
inputs:
  - analysis_evidence
  - service_context
  - existing_service_knowledge
  - active_workspace
outputs:
  - service_knowledge_candidates
  - service_knowledge_index_update
  - knowledge_capture_report
risk_level: medium
owner_role: Developer / Team Leader / Architect
stack:
  - any
tags:
  - knowledge-base
  - service-context
  - learning
  - evidence
model_tier: economy
execution_mode: write
delegation_group: documentation
parallel_safe: false
---

# Service Knowledge Capture

## Purpose
Turn newly discovered, reusable service knowledge into compact evidence-backed
cards without turning raw analysis transcripts into durable context.

## When To Use It
Use after a deep code investigation, incident analysis, test discovery, review,
or integration analysis reveals behavior, constraints, or unknowns that later
Mana workflows would otherwise need to rediscover.

## Inputs
- `analysis_evidence`: code, tests, configuration, tickets, ADRs, or operational
  artifacts with stable references.
- `service_context`: `.mana/global/` files and current knowledge index.
- `existing_service_knowledge`: relevant stable cards and candidate cards.
- `active_workspace`: story or session context that produced the evidence.

## Workflow
1. Read `.mana/global/knowledge/index.md` first. Progressive load only the
   domain cards relevant to the current evidence.
2. Extract a card only when it is reusable beyond the active story and has at
   least one concrete evidence reference.
3. Classify every statement as `observed`, `inferred`, `decision`, or `unknown`.
   Preserve confidence, owner, last verification date, and invalidation signals.
4. Deduplicate against existing cards. Prefer linking or updating a candidate
   over creating a near-duplicate.
5. Write new or changed findings to `.mana/global/knowledge/candidates/` with
   `promotion_state: candidate`; update the index only with a short candidate
   reference when it materially changes retrieval.
6. Promote to `.mana/global/knowledge/cards/` only with explicit owner approval
   recorded in the input. Architecture, security, data, production, and
   cross-service claims require the accountable specialist owner.
7. Link the capture report from `agent-memory/story-trace.md` in the active
   workspace. Do not copy the full card set into the story trace.

## Outputs
- `service_knowledge_candidates`: proposed cards with evidence and promotion
  status.
- `service_knowledge_index_update`: a compact, domain-oriented retrieval index.
- `knowledge_capture_report`: deduplication, promotions, stale cards, and open
  questions.

## Decision Rules
- `info`: observed evidence with a clear reusable scope.
- `warning`: inferred claim, incomplete evidence, stale card, or unclear owner.
- `blocked`: a requested stable promotion lacks explicit approval or would
  represent an unverified high-impact claim as fact.
- Never add raw logs, full diffs, credentials, customer data, or private
  reasoning to a card.

## Context Budget
Keep `index.md` below 200 lines and each card below 80 lines. Use source paths,
test names, issue keys, commit SHAs, and artifact links instead of copied text.
Use compact caveman working notes and a context budget: retain claims, evidence,
confidence, invalidation signals, and next checks only.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Follow `docs/policies/service-knowledge-policy.md` for card schema,
promotion, retrieval, and expiry rules.
