# Application Manager Readiness Agent Playbook

## Preparation
- Confirm the trigger point: `release_ready`, `before_deploy`, or `am_review`.
- Collect release scope, linked stories, branch diff, test evidence, rollback notes, monitoring context, and known operational constraints.
- Confirm MCP access is read-only unless an external write has explicit approval.

## Execution
1. Resolve or initialize the active Mana workspace using `scripts/mana-workspace.sh`.
2. Load service context and known pitfalls.
3. Run skills in the order listed in `AGENT.md`.
4. Stop on blocker findings that affect release safety, continuity, rollback, or support readiness.
5. Write outputs to `validation/` and release notes to `pr/`.
6. Route approval requests to AM, Team Leader, Architect, DBA, Security, or Operations as appropriate.

- Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- AM readiness status is explicit: `ready`, `ready_with_warnings`, or `not_ready`.
- Blockers have owners and required decisions.
- Communication, rollback, and monitoring notes are visible.
- Evidence gaps are listed separately from confirmed risks.
