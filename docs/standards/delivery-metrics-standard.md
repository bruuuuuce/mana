# Delivery Metrics Standard

Mana produces evidence at every lifecycle gate, but evidence only earns its
cost if it changes outcomes. This standard defines the small set of metrics
that close the loop between evidence produced and delivery results, so the
team can see which skills reduce churn and which need tuning or retirement.

The canonical metrics file lives in the Service Context Layer:

```text
.mana/global/metrics/delivery-metrics.md
```

Per-story raw events are recorded in the feature workspace as they happen:

```text
.mana/features/<FEATURE-ID>/learning/metrics-events.md
```

Use `templates/delivery-metrics.template.md` to initialize the global file.

## Core Metrics

Track exactly these three metrics before adding others. Each is cheap to
record at a gate the team already passes through.

### 1. Story Rework Rate

A story counts as reworked when it is sent back for requirement clarification,
splitting, or re-scoping after `story-ready-for-dev` or `story-start` reported
it ready.

- **Signal:** readiness checks that pass stories which later bounce are too
  permissive; stories blocked that needed no clarification are too strict.
- **Recorded when:** a started story is returned to BA/PO or re-planned.

### 2. Finding Hit / Miss Rate

For every defect found in human review, CI, or production, record whether a
Mana skill run on that branch had already flagged it (`hit`) or had the
opportunity and did not (`miss`). Also record findings that reviewers marked
as noise (`false_positive`).

- **Signal:** the miss list is the direct tuning backlog for skills; a rising
  false-positive share means a skill is producing review load instead of
  removing it.
- **Recorded when:** a PR review, CI failure, or incident closes.

### 3. Open Question Answer Rate

Profiles generate open questions routed to BA/PO, Team Leader, Architect, or
DBA. Record how many receive an owner answer before implementation starts.

- **Signal:** unanswered questions mean the evidence flow stops at the human
  boundary; the framework is producing questions nobody consumes.
- **Recorded when:** implementation of the related story starts.

## Event Format

Append one row per event to the feature workspace `metrics-events.md`:

| Date | Metric | Story | Event | Related Skill/Profile | Evidence Link |
|---|---|---|---|---|---|

`Event` values: `rework`, `hit`, `miss`, `false_positive`, `question_answered`,
`question_unanswered`.

## Aggregation

The `learning-agent` aggregates feature-workspace events into
`.mana/global/metrics/delivery-metrics.md` at its trigger points (post-merge,
incident closed, recurring failure). Aggregation is additive and
human-approved like every other promotion to `.mana/global/`.

Each aggregation period keeps one summary row per metric:

| Period | Metric | Events | Rate | Trend | Top Contributing Skill | Action |
|---|---|---|---|---|---|---|

`Action` names the concrete follow-up: tune a skill, retire a skill, adjust a
profile, escalate a process gap, or none.

## Rules

- Record events, not narratives. One row per event.
- A `miss` must name the skill that had the opportunity, or `none` when no
  skill covers that defect class — that distinction separates tuning work from
  coverage gaps.
- Do not use metrics to evaluate individual developers; contributor-level
  analysis stays inside `team-coaching-review` with its confidentiality rules.
- Do not let agents mark a story reworked, a finding missed, or a question
  answered without human confirmation of the underlying event.
- Missing metrics evidence is a warning, never a blocker for delivery work.
