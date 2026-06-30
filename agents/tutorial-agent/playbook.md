# Tutorial Agent Playbook

## Preparation
- Read `.mana/active-profile` if present and note the currently active profile.
- Read `profiles/*.yaml` to build the profile catalogue for Phase 1.
- Do not initialize a new workspace automatically.
- Confirm MCP access is read-only and limited to local framework files only.

## Execution

### Phase 0 — Discovery
- Ask at most two questions. Stop after two even if context is still incomplete.
- If `user_role` is supplied in input, skip the role question.
- If `selected_profile` is supplied, skip Phase 0 and Phase 1 entirely.
- Acknowledge the active profile from `.mana/active-profile` if found.

### Phase 1 — Profile Overview
- Build the overview table from `profiles/*.yaml`.
- Order rows by lifecycle: story-start → story-ready-for-dev → team-planning
  → architecture-review → pre-commit → jessica-fletcher → branch-ready
  → pr-ready → requested-pr-review → am-release-ready → ci-validation
  → tutorial → mana-help.
- Include `expected_max_duration` and `human_approval_requirement` from each
  profile YAML.
- After presenting the table, ask one question: "Which profile do you want to
  explore in depth?"

### Phase 2 — Deep-Dive
- Invoke `profile-selector` to confirm the selection and optionally write
  `.mana/active-profile`.
- Read in order:
  1. The profile YAML.
  2. The AGENT.md of the primary agent listed in the profile.
  3. The SKILL.md of each skill listed in the profile.
  4. `examples/sample-output.md` for each skill (skip silently if missing).
- Produce the Mermaid flow before the skill list.
- For each skill, write two sentences: what it does and why it is in this profile.
- Show the annotated sample output in a fenced block with inline comments
  explaining each section.
- List human approval gates explicitly: who approves and what evidence is needed.

### Phase 3 — Starter Checklist
- Checklist format: `- [ ] Owner: action, artifact or path`.
- Group by: prerequisites → workspace setup → service context → run command →
  post-run review.
- Include the exact `run-profile.sh` command with `--project-root`.
- Link relevant templates from `templates/`.

## Completion Criteria
- The user has seen a profile overview table with all profiles.
- The user has seen a Mermaid flow and annotated sample output for the selected profile.
- The user has a concrete starter checklist with the run command.
- No approval gate has been bypassed or hidden.

- Update or reference `agent-memory/story-trace.md` with concise evidence,
  assumptions, decisions, approval gates, handoffs, and generated artifact links
  for the active Jira story or feature.
