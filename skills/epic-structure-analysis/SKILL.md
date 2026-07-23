---
name: epic-structure-analysis
version: 1.0.0
description: Builds an evidence-backed structural map of a Jira epic and its child stories before overlap, contradiction, or delivery sequencing decisions.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - jira_read
  - read_files
  - confluence_read
inputs:
  - epic_story_pack
  - epic
  - stories
  - service_context
outputs:
  - epic_structure_report
  - story_inventory
  - evidence_gap_register
risk_level: low
owner_role: BA / PO / Team Leader
stack:
  - any
tags:
  - requirements
  - epic
  - jira
  - structure
model_tier: economy
execution_mode: read
delegation_group: requirements
parallel_safe: true
---

# Epic Structure Analysis

## Purpose
Create a compact, traceable map of an epic before judging whether stories
overlap, contradict each other, or can be delivered in a particular order.

## When To Use It
- A user asks to analyze an epic, its child stories, or their delivery shape.
- `epic-story-partitioning` or implementation sequencing needs a reliable
  inventory first.

## Outputs
- `epic_structure_report`
- `story_inventory`
- `evidence_gap_register`

## Inputs And Evidence
1. Prefer `.mana/features/<EPIC-ID>/evidence/jira/epic-story-pack.md` when it
   is fresh. Otherwise fetch it read-only with
   `./mana jira-mcp --fetch-epic-story-pack <EPIC-OR-STORY-KEY>`.
2. Record the resolved epic, all returned child stories, source timestamp, and
   every evidence gap. Do not silently treat an empty child list as complete.
3. For each story, extract only: outcome, scope, acceptance criteria,
   named services, data/contracts, links, dependencies, status, and explicit
   blockers. Read an individual complete Jira payload only when the pack is
   insufficient for a material ambiguity; record that this was done.

## Execution Logic
1. Build a story inventory and classify each item as business slice, enabling
   work, migration, contract, operational, or unclassified.
2. Establish an epic contract using `epic-goal-extraction` when its goal or
   constraints are unclear.
3. Produce an evidence-gap register for missing, inaccessible, stale, or
   conflicting Jira evidence. Missing evidence is not a negative finding.
4. Hand the normalized inventory to `epic-story-partitioning`; do not duplicate
   its overlap or contradiction judgment here.

## Decision Rules
- `blocked`: the epic cannot be resolved or required child-story evidence is
  inaccessible.
- `warning`: a material field, comment, link, or child story is missing, stale,
  or ambiguous.
- `info`: the inventory is sufficient for the next analysis stage.

## Output Rules
- Include source issue keys and artifact paths for every material claim.
- Separate `observed`, `inferred`, and `unknown` statements.
- Do not edit Jira, repositories, or service knowledge.
- Keep the report compact; link to the pack rather than reproducing Jira text.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`. Use concise
evidence-first notes, compact caveman mode, and a context budget: retain only
claim references, gaps, and next checks rather than Jira transcripts. Do not
include private reasoning.
