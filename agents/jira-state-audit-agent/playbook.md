# Jira State Audit Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md`. Use compact caveman
working notes while analyzing; maintain a context budget; keep final artifacts
structured and free of private chain-of-thought.

## Preparation
- Capture `jira_issue_key`, `target_branch`, `release_branch`, `fix_version`,
  and any provided PR number or release tag.
- Confirm all external access is read-only.
- Resolve the active Mana workspace if present.
- Read `docs/policies/jira-state-consistency-policy.md`.
- Check whether Jira, GitHub/GHE, remote refs, and tags are accessible. Treat
  missing access as evidence gaps, not conclusions.

## Execution
1. Resolve the issue key. Stop with `needs_human_decision` if multiple keys are
   plausible.
2. Run `jira-release-state-evidence`.
3. Build `validation/jira-state-evidence-timeline.md` with timestamp, source,
   event type, evidence strength, and reference.
4. Apply the policy using only recorded evidence.
5. Build `validation/jira-state-audit-report.md` with status, executive summary,
   decision table, findings, evidence, open questions, actions, and human
   approval.
6. Prefer `ambiguous` when release topology, fixVersion mapping, branch target,
   cherry-pick, hotfix, revert, or access gaps prevent a mechanical decision.
7. Never perform external writes or repository mutation.
8. Update or reference `agent-memory/story-trace.md` with concise evidence,
   assumptions, decisions, approval gates, handoffs, and generated artifact
   links for the active Jira story or feature.

## Completion Criteria
- The verdict is one of `coherent`, `non_coherent`, `ambiguous`, or `blocked`.
- The report names the Jira issue, state, fixVersion, target branch, release
  branch, and policy used.
- The timeline separates facts, inferences, and gaps.
- Missing evidence and access limitations are explicit.
- Human owner is named for every non-`coherent` verdict.
