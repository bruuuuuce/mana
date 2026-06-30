# Architecture Review Agent Playbook

## Preparation
- Confirm the trigger point: `architecture_review`, `before_development`, or `before_pr`.
- Collect story, design notes, architecture context, engineering guards, integration map, branch diff, and test evidence.
- Resolve and report the branch diff base. Prefer explicit design/PR target or
  user input, then `origin/HEAD`, then a single credible primary branch. If the
  base is missing or ambiguous, stop with `needs_human_decision` and ask which
  branch to compare against. Do not silently default to `main`.
- Identify whether database, security, cross-service, or operational concerns are in scope.

## Execution
1. Resolve or initialize the active Mana workspace using `scripts/mana-workspace.sh`.
2. Load service context and previous team decisions.
3. Run skills in the order listed in `AGENT.md`.
4. Stop on direct engineering guard violations or unapproved protected-area changes.
5. Write reports and approval questions to the active workspace.
6. Route unresolved decisions to the architect and specialist owners.

- Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- Architecture status is explicit.
- ADR or decision questions exist for material decisions.
- NFR evidence gaps are listed.
- Boundary, drift, contract, trust-boundary, and database risks are classified by owner.
