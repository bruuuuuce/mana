---
name: epic-story-partitioning
version: 1.0.0
description: Reviews an epic story pack to detect overlapping stories, missing slices, hidden dependencies, oversized stories, and weak acceptance boundaries before planning or development.
compatibility:
  - codex
  - junie
  - claude
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
  - jira_read
  - confluence_read
  - architecture_rules_read
inputs:
  - epic_story_pack
  - epic
  - stories
  - acceptance_criteria
  - team_constraints
outputs:
  - epic_partitioning_report
  - overlap_findings
  - gap_findings
  - slicing_questions
risk_level: medium
owner_role: BA / PO / Team Leader
tags:
  - requirements
  - epic
  - planning
  - story-slicing
---

# Epic Story Partitioning

## Purpose
Check whether stories under the same epic are split into coherent, testable,
non-overlapping business slices with explicit dependencies and no obvious gaps
against the epic goal.

This skill supports planning and refinement decisions. It does not rewrite Jira,
approve scope, or decide delivery sequencing without the accountable human owner.

## When To Use It
- A Jira story key is available and the team needs to understand the parent epic
  and sibling stories.
- An `epic-story-pack.md` exists under the active Mana workspace.
- A Team Leader, BA, PO, PM, or reviewer needs evidence that stories are
  correctly partitioned before assignment or sprint planning.
- `story-ready-for-dev` or `team-planning` needs to decide whether one story is
  independently startable or should be split, merged, or clarified.

## When Not To Use It
- Do not run it with only one story title and no epic/sibling evidence.
- Do not treat missing Jira data as proof that scope is clean.
- Do not use it to transition, edit, rank, or close Jira issues.
- Do not force all stories to be independent when the epic intentionally has
  explicit ordering constraints; report the dependency instead.

## Inputs
- epic_story_pack
- epic
- stories
- acceptance_criteria
- team_constraints

## Outputs
- epic_partitioning_report
- overlap_findings
- gap_findings
- slicing_questions

## Execution Logic
1. Prefer the normalized Markdown cache at
   `.mana/features/<EPIC-ID>/evidence/jira/epic-story-pack.md` when present.
   If it is missing and Jira read access is configured, ask the runner to fetch
   it with `./mana jira-mcp --fetch-epic-story-pack <STORY-KEY>`.
2. Read the epic goal, non-goals, constraints, story summaries, descriptions,
   acceptance criteria, links, subtasks, and evidence gaps from the pack.
3. Build a scope matrix: story key, primary business outcome, owned behavior,
   data touched, contracts touched, acceptance criteria, dependencies, and test
   surface.
4. Detect overlap: duplicate acceptance criteria, two stories owning the same
   behavior, shared data mutation without ownership, conflicting statuses or
   defaults, and repeated technical work with no business boundary.
5. Detect gaps: epic goals or constraints not covered by any story, missing
   negative paths, missing operational/security/database stories, and missing
   integration or migration work.
6. Detect poor slicing: stories that are too large, purely technical without an
   acceptance boundary, untestable alone, blocked by implicit dependencies, or
   likely to create merge/review bottlenecks.
7. Produce findings by severity and owner questions. Store the report with the
   active workspace so downstream agents can reuse it.

## Decision Rules
- `blocker`: two stories contradict each other, a critical epic goal is
  uncovered, a story cannot start because scope/dependency/test boundary is
  unclear, or the proposed split would require unapproved architecture,
  database, security, or contract ownership.
- `warning`: medium overlap, partial duplicate work, unclear ordering,
  oversized story, missing non-critical acceptance detail, or stale Jira pack.
- `info`: naming, ordering, or refinement suggestion that helps planning but
  does not block assignment.

## Cache And Refresh Policy
Use the Markdown pack as the primary evidence source to avoid repeated Jira
downloads and token-heavy raw JSON. Do not fetch Jira repeatedly in the same run.
If the pack is stale, missing, or explicitly challenged by the user, request a
refresh instead of silently mixing old and new evidence.

Default cache path:

```text
.mana/features/<EPIC-ID>/evidence/jira/epic-story-pack.md
```

The pack is an artifact, not a source of truth. Jira remains authoritative when
available. The report must state the pack path, fetch timestamp, source story,
resolved epic, and any evidence gaps.

## Failure Modes
- Jira schemas differ across projects; parent epic resolution can be incomplete.
- Closed, hidden, archived, or permission-restricted stories can make the pack
  look cleaner than reality.
- Poorly written story descriptions can hide overlap that only appears in
  implementation details.
- AI can miss subtle business rule conflicts; BA/PO and Team Leader review
  remains mandatory.

## Required Human Review
BA/PO owns scope and acceptance boundaries. Team Leader owns slicing,
sequencing, assignment, and start/no-start decisions. Architect, DBA, Security,
or service owner approval remains required for specialist blockers.

## Service Context Layer
Read `service-mission.md`, `domain-glossary.md`, `architecture.md`, and
`engineering-guards.md` when available. Use them to detect terminology drift,
wrong service ownership, forbidden zones, and hidden cross-service boundaries.

## Interaction With MCP
Jira access must remain read-only. The preferred external command is:

```bash
./mana jira-mcp --fetch-epic-story-pack <STORY-KEY>
```

This writes a normalized Markdown artifact in the Mana workspace. Do not publish
comments, transition Jira issues, or edit Jira fields from this skill.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use `templates/standard-agent-skill-report.template.md` when no more
specific template exists.

Internal reasoning must use compact caveman mode: terse fragments,
evidence-first notes, no long narrative, and no private chain-of-thought in
final artifacts. Maintain a context budget: keep a short working summary with
objective, issue keys, workspace path, checked evidence, open hypotheses,
discarded hypotheses, and next checks instead of accumulating raw Jira payloads
or copied tool output.

## Example Output
```yaml
skill: epic-story-partitioning
status: warning
summary: "Epic has one uncovered error-path slice and two stories overlapping on settlement status ownership."
findings:
  - severity: warning
    area: "scope-overlap"
    evidence: "STORY-12 and STORY-14 both define settlement status recalculation."
    recommended_action: "BA/PO and Team Leader should choose one owner story and move duplicate AC out of the other."
outputs:
  - epic_partitioning_report
  - overlap_findings
  - gap_findings
  - slicing_questions
human_review_required: true
```
