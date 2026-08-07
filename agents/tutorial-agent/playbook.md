# Tutorial Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md`. Use compact caveman working notes while analyzing; maintain a context budget; keep final artifacts structured and free of private chain-of-thought.

## Preparation
- Read `.mana/active-profile` if present and note the currently active profile.
- Read `profiles/*.yaml` to build the profile catalogue for Phase 1.
- Read `docs/workflow/user-context-layer.md` when onboarding covers reusable
  personal guidance, context precedence, setup, or diagnostics.
- Do not initialize a new workspace automatically.
- Confirm MCP access is read-only and limited to local framework files only.
- Never read or request direct access to the external User Context source.

## Execution

### Phase 0 — Discovery
- Ask at most two questions. Stop after two even if context is still incomplete.
- If `user_role` is supplied in input, skip the role question.
- If `selected_profile` is supplied, skip Phase 0 and Phase 1 entirely.
- Acknowledge the active profile from `.mana/active-profile` if found.

### Phase 0A — Context Layers
- Explain framework knowledge, User Context, Service Context, task/session
  context, and repository evidence as distinct layers.
- State that human instructions and governance remain authoritative and use
  `repository evidence > project/service context > user context` for project
  claims.
- Explain that User Context is optional, advisory, potentially stale, mirrored
  under `.mana/user-context/`, and loaded only through relevant entry points or
  targeted retrieval.
- For setup, show the user-level `MANA_USER_CONTEXT_ROOT` configuration from
  the guide. Do not suggest project-local storage of the personal absolute path.
- For diagnostics, show `mana context status`, `mana context refresh`, and
  `mana doctor`. Describe `mana context path --source` as explicit disclosure.

### Phase 1 — Profile Overview
- Build the overview table from `profiles/*.yaml`.
- Order rows by lifecycle: story-start → story-ready-for-dev → team-planning
  → architecture-review → pre-commit → jessica-fletcher → branch-ready
  → pr-ready → requested-pr-review → am-release-ready → ci-validation
  → tutorial → mana-help.
- Include `expected_max_duration` and `human_approval_requirement` from each
  profile YAML.
- When explaining profiles that use story context, show
  `./mana jira-mcp --get-issue <KEY>` as the fast read-only story command and
  `./mana jira-mcp --fetch-epic-story-pack <KEY>` as the reusable Markdown
  cache for epic and sibling-story evidence. Explain that planning checks
  feasibility and story partitioning while review/validation compares branch or
  PR changes against the story.
- Explain that story estimates are based on current-story evidence by default.
  Historical delivery calibration is a separate, read-only team-level step and
  requires explicit user approval after the base estimate.
- After presenting the table, ask one question: "Which profile do you want to
  explore in depth?"

### Phase 2 — Deep-Dive
- Invoke `profile-selector` to confirm the selection and optionally write
  `.mana/active-profile`.
- Read in order:
  1. The profile YAML.
  2. The AGENT.md of the primary agent listed in the profile.
  3. The primary agent playbook.
  4. For each listed skill, only the front matter plus Purpose, When To Use It,
     When Not To Use It, Outputs, and Decision Rules sections.
  5. Full SKILL.md files or examples only for the primary skill, for a user
     requested skill, or when the concise sections do not explain the profile.
- Produce the Mermaid flow before the skill list.
- For each skill, write two sentences: what it does and why it is in this profile.
- Show an annotated sample output only when an existing relevant example was
  read; otherwise show the expected artifact names and approval gates.
- List human approval gates explicitly: who approves and what evidence is needed.
- For `story-start`, `story-ready-for-dev`, and `team-planning`, identify
  historical calibration as an optional approval gate rather than a default
  prerequisite.

### Phase 3 — Starter Checklist
- Checklist format: `- [ ] Owner: action, artifact or path`.
- Group by: prerequisites → workspace setup → service context → run command →
  post-run review.
- Add an optional User Context health check when configured. Never make User
  Context mandatory for profiles that previously worked without it.
- Include the exact `run-profile.sh` command with `--project-root`.
- Link relevant templates from `templates/`.

### Phase 4 — Governed Tooling Boundaries
- Use actual command semantics, not a generic "read-only" label. Divination
  and cast dry-run write no state; eval and governance report runs persist
  Mana-local results; a non-dry cast can write Mana-local state/telemetry and
  invoke a runner.
- Show a saved-divination example with `recommendationContextFingerprint` and
  explain that `mana cast --from` rejects old or stale JSON until divination is
  rerun.
- Explain that cast validates profile, saved recommendation, Service Context,
  plan, and governance constraints before it initializes telemetry.
- Show eval result locations as
  `.mana/evaluations/results/<scenario>/<project-revision>/<run-id>.json` and
  report locations as `.mana/reports/governance/<project-revision>/<run-id>.md`.
- Explain assertion classes and limits: structural coverage does not prove
  semantic model quality; fixture-backed success does not prove autonomous
  detection; approval remains a human responsibility.
- Teach learning as the terminal-safe lifecycle `candidate → reviewed →
  rejected|archived`; never describe review as promotion.

## Completion Criteria
- The user has seen a profile overview table with all profiles.
- A first-time user understands the context-layer and authority distinctions.
- The user has seen a Mermaid flow and annotated sample output for the selected profile.
- The user has a concrete starter checklist with the run command.
- No approval gate has been bypassed or hidden.

- Update or reference `agent-memory/story-trace.md` with concise evidence,
  assumptions, decisions, approval gates, handoffs, and generated artifact links
  for the active Jira story or feature.
