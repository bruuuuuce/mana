# Epic Analysis Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md`; use compact caveman
working notes and a context budget that retains only evidence references, gaps,
consent state, and next checks.

## Preparation
1. Resolve the epic key from the explicit profile input. Do not use a branch
   key as a substitute when the user requested a different epic.
2. Initialize the active workspace and read core service context plus the KB
   index when present.
3. Record whether `service_discovery_approved` is true before reading source.

## Execution
1. Refresh or locate `evidence/jira/epic-story-pack.md`.
2. Produce the structure report before loading overlap or graph logic.
3. Produce the partitioning report, retaining ambiguous Jira data as evidence
   gaps rather than contradictions.
4. Build the graph from Jira and KB. If service discovery was not approved,
   do not search repositories and mark dependent edges accordingly.
5. With approval, inspect only explicitly named services and retain source
   references rather than raw code or Jira transcripts.
6. Stop on cycles, unresolved blockers, or specialist-only judgments; request
   the accountable owner or model escalation.

## Completion
- All four planning artifacts exist or the missing one has a clear blocked
  reason.
- The summary separates facts, assumptions, unknowns, and requested approvals.
- `agent-memory/story-trace.md` contains links and the discovery-consent state.
