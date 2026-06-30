---
name: source-impact-map
version: 1.0.0
description: Maps likely repository files and components impacted by a story.
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
  - story
  - goal_contract
  - repository_snapshot
  - architecture_rules
outputs:
  - source_impact_map
  - candidate_files
  - inspection_scope
risk_level: medium
owner_role: Team Leader / Developer
tags:
  - planning
  - code-search
  - impact-analysis
---

# Source Impact Map

## Purpose
Identify files and components to probably modify, inspect before deciding, and avoid unless approved.

This skill exists to reduce delivery churn by making a narrow, reusable judgement explicit. It produces structured artifacts and recommendations; it does not perform broad autonomous actions.

## When To Use It
- During the lifecycle phase indicated by the tags and preferred runner.
- When the required inputs are available and the team needs a repeatable review.
- Before a human approval gate where missing evidence would slow the team down.
- When a related agent invokes it as one step in a larger workflow.

## When Not To Use It
- Do not use it as a replacement for the accountable human owner.
- Do not use it for unrelated files, binary artifacts, or systems outside the approved MCP policy.
- Do not use it after the decision point if the finding can no longer influence the design without rework.
- Do not use it to justify unsafe shortcuts against project rules.

## Inputs
- story
- goal_contract
- repository_snapshot
- architecture_rules

## Outputs
- source_impact_map
- candidate_files
- inspection_scope

## Execution Logic
1. Extract domain terms, requested behavior, acceptance criteria, data,
   integrations, and constraints from the Jira story or fallback story-pack when
   available.
2. Search code for domain terms, endpoints, events, entities, mappers, and tests.
3. Classify findings by confidence.
4. Respect forbidden zones and ownership boundaries.
5. Record assumptions, unrequested candidate scope, and approval gates.

## Impact Classification
- `probably_modify`: files or components strongly connected to the requested behavior and likely to need code or test changes.
- `inspect_before_deciding`: files or components that provide context, contracts, legacy behavior, or integration seams but should not be edited by default.
- `do_not_touch_unless_approved`: shared libraries, platform clients, security-sensitive modules, unrelated legacy flows, generated code, or externally owned components.
- `unknown_requires_discovery`: references found through configuration, dynamic wiring, or runtime metadata that require additional repository or MCP inspection.

## Decision Rules
- `blocker`: unresolved high-risk issue, missing critical input, unsafe database/security/architecture condition, or untestable requirement that prevents responsible delivery.
- `warning`: incomplete evidence, medium-risk design concern, missing non-critical test, or ambiguity that can be accepted by the owner.
- `info`: observation useful for reviewers, implementation, or future learning.

## Failure Modes
- Missing or stale input artifacts can produce false negatives.
- Repository search can miss dynamically configured flows or generated code.
- MCP access restrictions can prevent full validation; report the access gap explicitly.
- AI output can be incomplete; human review remains mandatory.

## Required Human Review
The owner role `Team Leader / Developer` reviews blocker and warning findings. High-risk security, database, concurrency, or architecture findings require explicit approval before implementation or merge.

## Service Context Layer
Read `architecture.md`, `integration-map.md`, and `engineering-guards.md` before classifying files as probably modify, inspect, or do not touch.

Missing context files should be reported as warnings. A violation of `.mana/global/engineering-guards.md` must be treated as a blocker or routed to the accountable owner for explicit approval.

## Interaction With Codex
Codex should run this skill for repository-level analysis, planning, validation, documentation, and report generation. Codex should prefer proposed patches and written findings over destructive edits.

## Interaction With Junie
Junie may use the output inside the IDE to implement one approved task at a time, generate local tests, or apply local fixes. Junie must not change files outside the approved impact map without asking.

## Interaction With MCP
MCP access must be least-privilege. Read-only access is preferred. Writes, destructive operations, external comments, database execution, or ticket updates require human approval and audit logging.

## Correct Usage Examples
- Run during the intended lifecycle phase with the full story, context, and linked artifacts available.
- Use the output as evidence for refinement, planning, review, or local implementation decisions.
- Escalate blocker findings to the named human owner before continuing.
- Store the generated report with the story or branch artifacts so later agents can reuse it.

## Incorrect Usage Examples
- Do not use this skill as an autonomous code-changing tool.
- Do not run it with only a title or vague one-line request and treat the result as complete.
- Do not ignore high-severity findings because the output is advisory.
- Do not use it to bypass team, architecture, DBA, security, or reviewer approval.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts.

## Diagram
```mermaid
flowchart TD
    Inputs[Required inputs] --> Skill[source-impact-map]
    Skill --> Findings[Findings by severity]
    Skill --> Artifacts[Structured outputs]
    Findings --> HumanGate[Human review gate]
    Artifacts --> NextAgent[Downstream agent or workflow]
```

## Example Output
```yaml
skill: source-impact-map
status: warning
summary: "Analysis completed with one blocker candidate and two warnings."
findings:
  - severity: warning
    area: "example"
    message: "A required detail or verification point is incomplete."
    recommended_action: "Clarify with the owner and update the related artifact."
outputs:
  - source_impact_map
  - candidate_files
  - inspection_scope
human_review_required: true
```
