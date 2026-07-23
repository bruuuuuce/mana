# Runtime Execution Contract

## Purpose
Keep each Mana profile run small, evidence-led, and safe across Codex, Claude
Code, and OpenCode. This is the shared runtime contract; runner files should
only add provider-specific configuration.

## Start Small
1. Read the selected profile and its selected agent `AGENT.md` and playbook.
2. Read `skills/index.yaml`, not all skill bodies. Use profile activation rules
   and filtered evidence to select the minimum required skills.
3. Load only the chosen skill body. Do not load examples unless the procedure
   is unclear.
4. Read the core service context files listed by the profile when present.

## Evidence Budget
- Start with diff statistics, changed-file inventory, and narrow searches.
- Retrieve Jira fields, PR metadata, comments, logs, and file bodies only when
  they can resolve a concrete hypothesis.
- Keep a short working summary: objective, base, issue keys, evidence checked,
  open questions, and next check.
- Persist large evidence as workspace artifacts. Return paths, hashes, and
  concise findings; never copy raw transcripts or full diffs into parent
  context.

## Routing And Escalation
- The economy root routes, inventories evidence, performs low-risk checks, and
  synthesizes results.
- Delegate only bounded, relevant high-risk or `model_tier: full` work. Group
  related skills by risk domain and use no more than three direct subagents.
- `mana_explorer` is read-only discovery; `mana_full_specialist` handles deep
  architecture, security, database, concurrency, contract, production, or
  ambiguous-diff judgement; `mana_worker` is a single serialized writer only
  when the profile explicitly permits writes.
- If required high-risk judgement cannot be delegated or is not sufficiently
  evidenced, return `needs_model_escalation`; do not guess.

## Safety And Output
- Follow profile permissions and the selected agent's approval gates. Never
  infer write permission from available tools or a writable sandbox.
- Jira and GitHub are read-only unless a profile records explicit narrow
  approval for an external write.
- For code review, resolve an explicit comparison base and stop for a human
  scope decision when the filtered diff exceeds 80 files or 2,000 lines.
- Final output states status, blockers, warnings, evidence/artifact paths, and
  approvals required. Use the output-standard contract, not its extended guide,
  unless a specific template or policy change requires it.
