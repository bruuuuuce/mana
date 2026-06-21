# Jessica Fletcher Agent Playbook

## Preparation
- Confirm the trigger point: `before_commit`, `before_push`, `pre_review`, or
  `production_risk_question`.
- Prefer staged diff for pre-commit analysis.
- If staged diff is empty, use branch diff against the configured base branch.
- Load active `.mana` workspace artifacts when present.
- Load service context and engineering guards when present.

## Execution
1. Ask the incident question explicitly: "The code introduced in this branch is
   causing production problems; what are the most plausible reasons?"
2. Classify changed files by production risk domain.
3. Invoke `production-premortem`.
4. Invoke specialist skills only for touched risk areas.
5. Rank each hypothesis by:
   - severity
   - plausibility
   - production blast radius
   - evidence strength
   - ease of mitigation before commit
6. Produce stop/go guidance:
   - `stop_before_commit`
   - `fix_before_push`
   - `document_for_pr`
   - `no_material_findings`
7. Write or return the expected artifacts.

- Update or reference `decisions/developer-choice-log.md` when developer questions, answers, confirmed choices, rejected alternatives, or owner-accepted rationale are produced.
- Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- Every blocker has a concrete mitigation or owner approval path.
- Missing tests and missing observability are listed explicitly.
- Findings cite branch evidence or state the evidence gap.
- The final recommendation tells the developer whether to stop before commit,
  fix before push, document for PR, or continue.
