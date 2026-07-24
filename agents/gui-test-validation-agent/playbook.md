# GUI Test Validation Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md` and
`docs/policies/gui-test-execution-policy.md`.

## Preparation
- Resolve project root and active Mana workspace.
- Read `.mana/global/testing-policy.md` and `engineering-guards.md`.
- Read provided documentation through read-only connectors; record references,
  not credentials or copied payment data.

## Authoring
1. Produce `tests/gui/context-inventory.md` and list missing environment, data,
   reset, or documentation evidence.
2. Produce `tests/gui/gui-testbook.proposed.yaml` from the GUI template.
3. Require an owner to approve each runnable entry and the isolated test
   environment before execution.

## Execution
1. Require explicit requested IDs.
2. Run `scripts/run-gui-testbook.sh --catalog <catalog> --test <id> --environment <name>`.
3. Preserve generated run metadata, JUnit, Playwright output, traces,
   screenshots, and videos under `tests/gui/runs/`.
4. Report product, setup, data, selector, dependency, and environment causes as
   separate hypotheses.

## Completion Criteria
- No secret or raw test data is present in testbook, report, or trace summary.
- Each executed entry has a machine-readable report and declared artifacts.
- Learning output is a proposal with an approval gate, not a catalog rewrite.
- Update or reference `agent-memory/story-trace.md` when a feature, branch, or
  story workspace is active.

Use compact caveman mode for working notes and a context budget: retain only
source references, selected IDs, artifacts, gaps, and next decisions. Do not
copy raw logs, documentation dumps, screenshots, or sensitive data into reports.
