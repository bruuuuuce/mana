# Testbook Validation Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use compact caveman working notes and a context budget; preserve
only evidence, open gaps, and next checks.

## Preparation
- Resolve the project root and active Mana workspace.
- Read `.mana/global/testing-policy.md` when present.
- Read `docs/policies/testbook-execution-policy.md` before any execution.

## Discovery
1. Run `scripts/discover-testbook.sh --project-root <root> --output <workspace>/tests/testbook.discovered.yaml`.
2. Inspect only candidate evidence that needs classification or prerequisite
   clarification.
3. Preserve existing approved entries separately; discovery output remains a
   proposed catalog until reviewed.

## Execution
1. Require explicit requested IDs and approved catalog entries.
2. Run `scripts/run-testbook.sh --catalog <catalog> --test <id> --environment <name>`.
3. Add `--allow-performance` only after the explicit performance gate passed.
4. Classify failures using logs and available native artifacts; do not claim a
   product regression without evidence.

## Completion Criteria
- Each catalog entry names kind, command origin, source, environment, state,
  and approval status.
- Every executed entry has a log and machine-readable run report.
- The aggregate report distinguishes execution result from failure cause.
- Update or reference `agent-memory/story-trace.md` for an active feature,
  branch, or story workspace.
