# Git Hook Agent Playbook

## Preparation
- Confirm the trigger point: `pre_commit, pre_push`.
- Collect inputs: `staged_diff, branch_diff, local_repository`.
- Confirm MCP access is least-privilege and read-only unless approval is recorded.

## Execution
1. Detect whether an active Mana workspace already exists.
2. Do not initialize a new workspace automatically from pre-commit.
- Use the active `.mana` workspace only when it already exists.
- Run skills in the order listed in `AGENT.md`.
- Stop immediately on missing inputs or blocker findings.
- Aggregate findings into the expected outputs.
- Write optional outputs to the workspace folders defined by `AGENT.md`.
- Route approval requests to the accountable owner.

- Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- All expected artifacts exist.
- Blockers are resolved, approved, or explicitly deferred by an owner.
- Warnings are visible in the final report.
- Next steps are concrete and assigned.
