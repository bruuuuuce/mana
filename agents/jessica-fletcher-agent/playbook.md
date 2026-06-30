# Jessica Fletcher Agent Playbook

## Preparation
- Confirm the trigger point: `before_commit`, `before_push`, `pre_review`, or
  `production_risk_question`.
- Resolve the repository's main branch before reading diffs:
  - Prefer an explicit user-provided base branch when supplied.
  - Otherwise read the upstream default branch, for example `origin/HEAD`.
  - If no upstream default is available, consider common primary branch names
    such as `origin/main`, `origin/master`, `main`, `master`, `develop`, or
    `dev` only when exactly one candidate is credible.
  - If multiple plausible candidates exist, or none exists, stop and ask:
    "Which main branch should Jessica compare this local branch against?"
- Use the full local branch diff against the resolved main branch. Include
  committed branch changes and uncommitted working-tree changes. Do not narrow
  analysis to staged files.
- Exclude Mana framework/bootstrap noise from production hypotheses, findings,
  evidence, missing-test lists, and failure modes: `.mana/**`, `AGENTS.md`,
  `CLAUDE.md`, `mana`, and Mana-only `.gitignore` or env ignore changes.
  Mention these only as operational setup notes when relevant.
- Load active `.mana` workspace artifacts when present.
- Load service context and engineering guards when present.

## Execution
1. Ask the incident question explicitly: "The code introduced in this branch is
   causing production problems; what are the most plausible reasons?"
2. Classify changed files by production risk domain.
3. Record the resolved main branch and diff command in the evidence section.
4. Invoke `production-premortem`.
5. Invoke specialist skills only for touched risk areas.
6. Rank each hypothesis by:
   - severity
   - plausibility
   - production blast radius
   - evidence strength
   - ease of mitigation before commit
7. Produce stop/go guidance:
   - `stop_before_commit`
   - `fix_before_push`
   - `document_for_pr`
   - `no_material_findings`
8. Write or return the expected artifacts.

- Update or reference `decisions/developer-choice-log.md` when developer questions, answers, confirmed choices, rejected alternatives, or owner-accepted rationale are produced.
- Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- Every blocker has a concrete mitigation or owner approval path.
- The report names the main branch used for comparison, or records that the run
  stopped to ask the user because the main branch was ambiguous.
- Missing tests and missing observability are listed explicitly.
- Findings cite branch evidence or state the evidence gap.
- The final recommendation tells the developer whether to stop before commit,
  fix before push, document for PR, or continue.
