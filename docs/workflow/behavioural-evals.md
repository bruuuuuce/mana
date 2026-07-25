# Behavioural Evaluations And Governance Report

Mana behavioural evaluations turn frozen scenario expectations into repeatable
repository-local results. They are a safety net for governed execution plans,
not a substitute for delivery evidence or human judgment.

## Run and compare

```bash
mana eval run
mana eval run conditional-contract-pr --json
mana eval run --profile pr-ready
mana eval compare baseline.json .mana/evaluations/results/conditional-contract-pr/<project-revision>/latest.json
mana report governance
```

`run` does not invoke models, agents, tools, hooks, builds, tests, or external
systems, and it does not modify the target repository. It does persist a local
evaluation result, so its mutation contract is `repositoryModified: false` and
`manaStateWritten: true` rather than a blanket `readOnly` claim. Results use
schema version 2 and are stored as
`.mana/evaluations/results/<scenario-id>/<project-revision>/<run-id>.json`,
with a copied `latest.json`.

## Writing an automated assertion

Add an optional `eval.yaml` beside `scenario.md`:

```yaml
version: 1
assertions:
  - type: must_use_skill
    value: cross-service-contract
  - type: must_not_use_tool
    value: database_write
  - type: must_require_gate
    value: owner approval
  - type: must_produce_artifact
    value: pr-readiness-report.md
  - type: must_stop_with
    value: unresolved blocker findings
  - type: must_not_modify
    value: true
  - type: max_delegation_depth
    value: 1
  - type: max_retrieval_cycles
    value: 3
```

Use `fixture-signals.txt` for exact, safe deterministic risk facts required by
`must_flag` or prohibited by `must_not_flag`. Keep it minimal and free of
secrets. Bump `version` when the intended assertion semantics change; retain
the old result as a comparison baseline.

Assertions report a class. `structural` assertions inspect the governed plan;
`fixture-backed` assertions inspect only frozen fixture signals. `runtime` is
reserved for future verified execution traces. In particular,
`must_not_modify: true` is structural: it fails for a selected write-mode
skill, mutating effective tool, planned `mana_worker`, or declared repository
mutation. A fixture signal cannot make that structural failure pass.

## Deterministic and model checks

The runner checks structure deterministically. It can prove that a profile
selects a skill, declares a gate, excludes a tool, or has an artifact contract.
It cannot prove that a model understood nuanced source code. A model judge is
not included in this increment; if added later it must be opt-in, separately
identified in results, and never replace these checks.

## Governance report

`mana report governance` writes schema-version-2 report artifacts under
`.mana/reports/governance/<project-revision>/<run-id>.md`, with a copied
`latest.md`. It separates inventory from calculated profile, skill, human-gate,
risk-level, and model-tier coverage; it also reports the current pass rate,
stale result count, and learning candidates by lifecycle status. These are
structural measures and do not prove semantic model quality, production safety,
or human approval.
