# Scenario: Plan Drift Branch

**Profile:** `branch-ready`
**Exercises:** `branch-validation-agent` plan-drift detection,
`source-impact-map` comparison, missing-test evidence.

## Setup

1. Create a feature workspace `.mana/features/PROJ-301/` containing
   `planning/source-impact-map.md` and `planning/technical-task-breakdown.md`
   from `inputs/`.
2. Provide `inputs/branch-diff.md` as the branch change evidence (or replay
   the listed changes on a real scratch branch).
3. Run `branch-ready`.

## Intent

The branch implements the planned notification change but also modifies a
payment fee constant that no planning artifact mentions, and ships no test
for the new retry branch. A correct run reports the unplanned payment change
as drift requiring approval and the missing retry test as missing evidence —
it must not average these away because the planned work looks fine.
