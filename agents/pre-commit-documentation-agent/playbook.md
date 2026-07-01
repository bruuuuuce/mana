# Pre-Commit Documentation Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md`. Use compact caveman working notes while analyzing; maintain a context budget; keep final artifacts structured and free of private chain-of-thought.

## Preparation
- Confirm the trigger point: `pre_commit` or `before_commit`.
- Confirm an active Mana workspace exists for the Jira story or feature.
- Collect staged diff, branch diff, story context, test evidence, and developer choice log.

## Execution
1. Resolve the active Mana workspace using `scripts/mana-workspace.sh status`.
2. Read `manifest.yaml`, `agent-memory/story-trace.md`, and `decisions/developer-choice-log.md`.
3. Generate or refresh `pr/pre-commit-development-summary.md`.
4. Generate or refresh `pr/knowledge-transfer-brief.md`.
5. Generate or refresh `validation/developer-decision-review.md` when rationale is missing or risky.
6. Update or reference `decisions/developer-choice-log.md` for developer questions, answers, confirmed choices, rejected alternatives, or owner-accepted rationale.
7. Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- `pr/pre-commit-development-summary.md` exists or is returned as an artifact.
- `pr/knowledge-transfer-brief.md` exists or is returned as an artifact.
- Unconfirmed rationale is visible in `decisions/developer-choice-log.md` or `validation/developer-decision-review.md`.
- The artifacts distinguish confirmed choices from assumptions.
