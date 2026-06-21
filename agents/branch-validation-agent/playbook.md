# Branch Validation Agent Playbook

## Preparation
- Confirm the trigger point: `before_pr, branch_ready, ci_validation`.
- Collect inputs: `planning_artifacts, branch_diff, test_evidence, risk_register`.
- Confirm MCP access is least-privilege and read-only unless approval is recorded.

## Execution
1. Resolve or initialize the active Mana workspace using `scripts/mana-workspace.sh`.
2. Read `manifest.yaml` and `index.md` from the workspace.
- Create or locate the working artifact folder inside the active `.mana` workspace.
- Run skills in the order listed in `AGENT.md`.
- Stop immediately on missing inputs or blocker findings.
- Aggregate findings into the expected outputs.
- Write outputs to the workspace folders defined by `AGENT.md`.
- Route approval requests to the accountable owner.

- Update or reference `decisions/developer-choice-log.md` when developer questions, answers, confirmed choices, rejected alternatives, or owner-accepted rationale are produced.
- Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- All expected artifacts exist.
- Blockers are resolved, approved, or explicitly deferred by an owner.
- Warnings are visible in the final report.
- Next steps are concrete and assigned.
