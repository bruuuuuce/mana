---
name: story-effort-estimation
version: 1.1.0
description: Estimates Agile story points and time ranges for stories and split technical tasks using complexity, uncertainty, risk, dependencies, and test effort. Historical calibration is optional and requires explicit user approval.
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
inputs:
  - story
  - acceptance_criteria
  - technical_task_breakdown
  - source_impact_map
  - risk_register
  - team_constraints
  - historical_calibration_approved
outputs:
  - story_effort_estimate
  - task_effort_estimates
  - estimation_rationale
  - estimation_risks
  - calibration_status
risk_level: medium
model_tier: economy
execution_mode: read
delegation_group: requirements
parallel_safe: false
owner_role: Team Leader
stack:
  - any
tags:
  - planning
  - estimation
  - team-lead
  - technical-slicing
---

# Story Effort Estimation

## Purpose
Help a Team Leader estimate story complexity with Agile story points and produce a separate time range for planning. The skill also estimates each technical task when a story is split, so task assignment and sequencing use the same estimation logic.

This skill supports planning decisions. It does not replace team planning poker, capacity planning, or accountable Team Leader judgement.

## When To Use It
- During story readiness, team planning, or refinement when a story needs a shared size estimate.
- After `technical-task-breakdown` splits a story into implementation tasks.
- When a Team Leader needs to compare sibling stories or decide whether a story is too large to start.
- When time pressure requires an explicit delivery range with uncertainty called out.

## When Not To Use It
- Do not treat the time estimate as a commitment or SLA.
- Do not estimate from title-only stories unless the output is explicitly marked `insufficient_evidence`.
- Do not hide missing requirements inside a larger estimate; report blockers or questions.
- Do not sum task story points mechanically to override the story-level estimate.

## Inputs
- story
- acceptance_criteria
- technical_task_breakdown
- source_impact_map
- risk_register
- team_constraints
- historical_calibration_approved: optional boolean, defaults to `false`. It
  permits read-only comparison with historical team-level delivery evidence.

## Outputs
- story_effort_estimate
- task_effort_estimates
- estimation_rationale
- estimation_risks
- calibration_status

## Optional Historical Calibration
The default estimate uses only the current story, technical analysis, service
context, and explicit team conventions. Do not search Jira history, Git history,
closed stories, cycle time, or delivery metrics by default.

When comparable historical evidence could materially improve the estimate,
first return the base estimate and ask the user for explicit approval. Proceed
only when `historical_calibration_approved: true` is supplied or the user
explicitly confirms it in the current interaction.

With approval, use only aggregate, team-level evidence: comparable completed
stories, their planned versus observed delivery range, recurring dependency or
test-environment delays, and documented local point conventions. Do not rank,
profile, or infer productivity for individual people. Record the sources,
comparison scope, and limitations; calibration may refine confidence or the
time range, but must not mechanically override the story-point estimate.

## Estimation Scale
Use the team's configured scale when available. If no scale is provided, use:

| Points | Meaning |
|---|---|
| 1 | Trivial, localized, well understood, very low risk. |
| 2 | Small, clear, limited files, straightforward tests. |
| 3 | Moderate, normal implementation and test effort, low uncertainty. |
| 5 | Medium-large, multiple components or notable test/risk work. |
| 8 | Large, cross-component, high uncertainty, careful review needed. |
| 13 | Very large, risky, likely needs splitting before assignment. |

Use `>13` only as a warning that the story should be split or clarified before development.

## Estimation Factors
Score using evidence, not optimism:

- Functional scope and number of acceptance criteria.
- Number and volatility of affected components.
- Unknowns, requirement ambiguity, and owner decisions still needed.
- Integration, database, concurrency, security, or architecture risk.
- Test effort: unit, integration, regression, contract, manual evidence.
- Dependencies on other stories, teams, approvals, environments, or data.
- Legacy complexity, low observability, or fragile existing behavior.

## Execution Logic
1. Confirm requirement evidence is sufficient. If not, return `insufficient_evidence` with questions instead of a confident estimate.
2. Estimate the story first using the point scale and rationale. Mark whether the story should be split.
3. If `technical_task_breakdown` is present, estimate each task separately with:
   - task name or id
   - story points when the task is independently assignable
   - time range
   - confidence
   - dependencies
   - main uncertainty driver
4. Produce a time range separately from story points. Use person-time ranges such as `0.5-1 day`, `1-2 days`, `3-5 days`, or `1-2 weeks`. Include analysis, implementation, testing, review rework, and evidence collection when relevant.
5. Explain why the time range differs from the story point signal when it does; for example, low complexity but slow external dependency.
6. Call out split recommendations when any task is too large, too risky, or not independently testable.
7. Set `calibration_status` to `not_requested` unless explicit approval was
   provided. If approved, perform the bounded team-level comparison and set it
   to `performed`, `insufficient_history`, or `access_limited`.

## Decision Rules
- `blocker`: estimate cannot be made responsibly because acceptance criteria, scope, dependency, or owner decision is missing.
- `warning`: story is `13` or `>13`, confidence is low, time range is wide, task split is uneven, or a task is not independently testable.
- `info`: estimate is usable with normal uncertainty.

## Required Output Shape
Use this structure inside the standard Mana report:

```yaml
story_estimate:
  story_points: 5
  time_range: "3-5 days"
  confidence: medium
  split_recommendation: "split optional; tasks are independently assignable"
task_estimates:
  - task: "Add API validation"
    story_points: 2
    time_range: "1-2 days"
    confidence: high
    dependencies: []
    uncertainty_driver: "error mapping details"
estimation_risks:
  - "Integration test environment may widen the time range."
calibration_status:
  state: not_requested
  reason: "Historical calibration requires explicit user approval."
```

## Failure Modes
- Teams may calibrate points differently; use local historical examples only
  after explicit approval.
- Time estimates are sensitive to developer familiarity, interruptions, CI latency, and review availability.
- Splitting can make task time additive, but story points remain relative complexity and should not be summed blindly.

## Required Human Review
The Team Leader owns the final estimate, split decision, and assignment. Product Owner, Architect, DBA, Security, or QA review is required when their domain drives a blocker or high-uncertainty estimate.

## Service Context Layer
Read `.mana/global/service-mission.md`, `architecture.md`, `engineering-guards.md`, `testing-policy.md`, and `.mana/global/team-decisions/` when available. Use team-specific estimation conventions if documented there.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/story-effort-estimate.template.md` for the dedicated estimate artifact; use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts. Maintain a context budget: keep a short working summary with objective, issue keys, workspace path, checked evidence, open hypotheses, discarded hypotheses, and next checks instead of accumulating raw transcripts, full diffs, repeated file dumps, or copied tool output.

## Example Output
```yaml
skill: story-effort-estimation
status: warning
summary: "Story is estimated at 8 points with a 5-8 day range; one integration task should be split."
story_estimate:
  story_points: 8
  time_range: "5-8 days"
  confidence: medium
  split_recommendation: "split integration setup from implementation"
outputs:
  - story_effort_estimate
  - task_effort_estimates
human_review_required: true
```
