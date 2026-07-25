# Behavioural Evaluations And Governance Report

Mana behavioural evaluations turn frozen scenario expectations into repeatable
repository-local results. They are a safety net for governed execution plans,
not a substitute for delivery evidence or human judgment.

## Run and compare

```bash
mana eval run
mana eval run conditional-contract-pr --json
mana eval run --profile pr-ready
mana eval compare baseline.json .mana/evaluations/results/conditional-contract-pr-v1-<revision>.json
mana report governance
```

`run` is read-only with respect to the delivery workspace: it does not invoke
models, agents, tools, hooks, builds, tests, or external systems. It evaluates
profile and skill metadata, declared agent outputs, human gates, and frozen
fixture signals. Results are local `.mana/evaluations/results/*.json` files.

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

## Deterministic and model checks

The runner checks structure deterministically. It can prove that a profile
selects a skill, declares a gate, excludes a tool, or has an artifact contract.
It cannot prove that a model understood nuanced source code. A model judge is
not included in this increment; if added later it must be opt-in, separately
identified in results, and never replace these checks.

## Governance report

`mana report governance` writes `.mana/reports/governance-<revision>.md`. It
summarizes profile/skill/gate coverage, local eval results, Service Context
gaps, metadata validation, model-tier coverage, learning candidates, and a
pointer to comparison-based regressions. It is static Markdown, local only,
and does not prove production safety, approval, or semantic correctness.
