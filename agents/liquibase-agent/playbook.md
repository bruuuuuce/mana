# Liquibase Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md`. Use compact caveman working notes while analyzing; keep final artifacts structured and free of private chain-of-thought.

## Preparation
- Confirm the trigger point: `db_change_detected, before_pr, ci_validation`.
- Collect inputs: `changelog_files, schema_snapshots, database_metadata, traffic_characteristics`.
- Confirm MCP access is least-privilege and read-only unless approval is recorded.

## Execution
1. Resolve or initialize the active Mana workspace using `scripts/mana-workspace.sh`.
2. Read `manifest.yaml` and `index.md` from the workspace.
- Create or locate the working artifact folder inside the active `.mana` workspace.
- Load and run only the database skills whose conditions in `AGENT.md` match the
  available changelog, rollback, production-risk, or drift inputs.
- Stop immediately on missing inputs or blocker findings.
- Aggregate findings into the expected outputs.
- Write outputs to the workspace folders defined by `AGENT.md`.
- Route approval requests to the accountable owner.

- Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- All expected artifacts exist.
- Blockers are resolved, approved, or explicitly deferred by an owner.
- Warnings are visible in the final report.
- Next steps are concrete and assigned.
