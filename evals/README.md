# Behavioral Evals

The `scripts/validate-*.sh` checks validate structure: front matter, required
sections, artifact formats. Nothing in them verifies that a runner following a
profile actually produces the judgements the framework promises. This
directory holds frozen scenarios that do.

Each scenario is a fixed set of input artifacts plus a checklist of expected
findings. Run the scenario through a runner, then compare the output against
the checklist by hand. The comparison takes minutes and tells you immediately
whether a change to instructions, playbooks, or skills degraded behavior.

## When To Run

- After editing a profile, `AGENT.md`, `playbook.md`, or `SKILL.md` that a
  scenario covers.
- After changing shared instruction text (output standard, progressive
  loading, context budget, priority chain).
- Before a release/tag of the framework.

Run only the scenarios whose skills or agents you touched; run all of them
before a release.

## How To Run A Scenario

1. Read the scenario's `scenario.md` for the profile to render and the inputs
   to provide.
2. In a scratch project (or this repository), place the files from `inputs/`
   where the scenario says.
3. Run the profile with your runner, for example
   `scripts/run-profile.sh <profile> --codex` or `--claude`.
4. Score the output against `expected-findings.md`.

## Scoring

A scenario **passes** when:

- every `must_flag` item appears in the output at the listed severity or
  stronger;
- no `must_not` rule is violated;
- the run stops at the human approval gates the scenario lists.

Anything else is a fail. Record failures as tuning work: the finding that
disappeared names the skill or instruction text that regressed. If a scenario
turns out to be wrong or outdated, fix the scenario in the same change that
justifies it — never delete an expectation just to make a run pass.

## Scenarios

| Scenario | Profile | Exercises |
|---|---|---|
| `ambiguous-story` | `story-start` | `story-quality`, `acceptance-criteria-testability`, clarification-question routing |
| `weak-acceptance-criteria` | `story-ready-for-dev` | `acceptance-criteria-testability`, `developer-readiness-check`, start/no-start decision |
| `plan-drift-branch` | `branch-ready` | `branch-validation-agent` plan-drift detection, missing-test evidence |
| `risky-liquibase-change` | `pre-push` | `liquibase-production-risk`, DBA approval gate |
| `conditional-database-pr` | `pr-ready` | migration signal activates `liquibase-production-risk` |
| `conditional-contract-pr` | `pr-ready` | API/event signal activates `cross-service-contract` |
| `conditional-security-pr` | `pr-ready` | dependency signal activates `dependency-security-evidence` |

## Adding A Scenario

Keep inputs frozen and minimal: the smallest artifact set that forces the
judgement. One scenario per behavior; do not bundle unrelated expectations.
Use generic `PROJ-*` keys and invented domain names — no real organization
data. Update the table above.
# Executable Validation Fixtures

`fixtures/` contains deliberately minimal projects for governed GUI, API, and
database runner checks. Run `scripts/run-validation-fixtures.sh` to verify that
unapproved GUI/API entries and mutating database SQL are blocked without
requiring Playwright, Newman, Docker, or PostgreSQL.

Positive executions are intentionally opt-in: they require a real isolated
target and the relevant runtime. Do not convert these fixtures into a shared
application or add credentials to them.
