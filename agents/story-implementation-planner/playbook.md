# Story Implementation Planner Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md`. Use compact caveman working notes while analyzing; keep final artifacts structured and free of private chain-of-thought.

## Preparation
- Confirm the trigger point: `story_start, refinement, before_development`.
- Collect inputs: `epic, story, acceptance_criteria, linked_docs, repository_snapshot`.
- Confirm MCP access is least-privilege and read-only unless approval is recorded.
- If Jira MCP is unavailable, collect `epic_story_pack` from `templates/epic-story-pack.template.md` and record the fallback reason.

## Execution
1. Resolve or initialize the active Mana workspace using `scripts/mana-workspace.sh`.
2. Read `manifest.yaml` and `index.md` from the workspace.
- If `epic_story_pack` is provided, load it as the requirement source before invoking requirement skills.
- Report missing Jira fields, links, or acceptance criteria as evidence gaps instead of inventing them.
- Create or locate the working artifact folder inside the active `.mana` workspace.
- Load and run only the planning skills whose conditions in `AGENT.md` match the
  available story, epic, repository, architecture, integration, database, or
  test-planning inputs.
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
