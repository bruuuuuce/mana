# Team Leader Planning Agent Playbook

## Preparation
- Confirm the trigger point: `team_planning`, `story_ready_for_dev`, or `before_development`.
- Collect epic, stories, planning artifacts, team constraints, source impact, technical breakdown, and test plan.
- Confirm whether Jira MCP or Markdown story-pack fallback is the requirement source.

## Execution
1. Resolve or initialize the active Mana workspace using `scripts/mana-workspace.sh`.
2. Load service context and team decisions.
3. Run skills in the order listed in `AGENT.md`.
4. Stop on missing start conditions or unapproved protected-area work.
5. Write planning outputs into the active workspace.
6. Route decisions and approvals to the Team Leader and specialist owners.

- Update or reference `decisions/developer-choice-log.md` when developer questions, answers, confirmed choices, rejected alternatives, or owner-accepted rationale are produced.
- Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- Each story has a start/no-start status.
- Task sequence and parallelization are explicit.
- Owners, blockers, dependencies, review focus, and test expectations are visible.
- Developer handoff exists for work ready to start.
