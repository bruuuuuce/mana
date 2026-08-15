# Story Implementation Planner Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md`. Use compact caveman working notes while analyzing; maintain a context budget; keep final artifacts structured and free of private chain-of-thought.

## Preparation
- Confirm the trigger point: `story_start, refinement, before_development`.
- Collect inputs: `epic, story, acceptance_criteria, linked_docs, repository_snapshot`,
  and optional `implementation_contract, estimation_requested`.
- Confirm MCP access is least-privilege and read-only unless approval is recorded.
- If Jira MCP is unavailable, collect `epic_story_pack` from `templates/epic-story-pack.template.md` and record the fallback reason.
- If supplied, load the implementation contract before planning. Treat its
  authoritative inputs and forbidden reads/changes as binding. Record a
  conflict as a blocker; do not invent an alternate design.

## Execution
1. Resolve or initialize the active Mana workspace using `scripts/mana-workspace.sh`.
2. Read `manifest.yaml` and `index.md` from the workspace.
- If `epic_story_pack` is provided, load it as the requirement source before invoking requirement skills.
- Report missing Jira fields, links, or acceptance criteria as evidence gaps instead of inventing them.
- Create or locate the working artifact folder inside the active `.mana` workspace.
- Load and run only the planning skills whose `skill_activation` signal in the
  active profile matches filtered evidence.
- Stop immediately on missing inputs or blocker findings.
- Do not create a technical task unless it cites a story requirement or
  acceptance criterion, a candidate file or seam, and direct test evidence.
  Keep approvals, branch alignment, and evidence collection outside technical
  tasks and implementation effort.
- Run `story-effort-estimation` only when `estimation_requested: true`, scope
  is confirmed, and no blocker remains. Otherwise write `not_requested` or
  `not_estimable` without a numerical range.
- Aggregate findings only into artifacts justified by the confirmed scope.
- Write outputs to the workspace folders defined by `AGENT.md`.
- Route approval requests to the accountable owner.

- Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- Required evidence artifacts exist; conditional planning artifacts exist only
  when their activation conditions are met.
- Blockers are resolved, approved, or explicitly deferred by an owner.
- Warnings are visible in the final report.
- Next steps are concrete and assigned.
