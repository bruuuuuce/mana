# Mana Help Agent Playbook

Follow `docs/standards/agent-skill-output-standard.md`. Use compact caveman working notes while analyzing; maintain a context budget; keep final artifacts structured and free of private chain-of-thought.

## Preparation
- Capture the user's goal and current lifecycle phase.
- Read `.mana/active-profile` if present and include the current active profile in context.
- Check whether `.mana/active-workspace` exists.
- Check whether relevant files exist under `.mana/global/`.
- Check whether Jira MCP is available or whether the Markdown fallback is needed.

## Execution
1. If the user's message expresses intent to switch profile or phase (e.g., "switch
   to...", "I want to use...", "which profile for...", "now we are in phase..."),
   invoke `profile-selector` first to resolve, confirm, and persist the selection.
2. Classify the request as installation, workspace setup, epic intake, story
   planning, implementation guidance, branch validation, PR readiness, CI
   validation, learning, MCP troubleshooting, or fallback use.
3. Invoke `mana-usage-help`.
4. Recommend the next profile, agent, skill, template, and command sequence.
5. Identify required artifacts and missing context.
6. Identify any approval gates that apply.
7. Keep the output actionable and short.
8. For divination/cast, include the saved-result freshness and preflight
   boundary when relevant: preflight failures must not create runtime telemetry.
9. For eval/report, name the run-identified artifact path and distinguish
   Mana-local artifact writes from target-repository modifications.
10. For learning, show the canonical status transition and state that no
    automatic promotion exists.
11. For a read-model or Mana Familiar question, recommend `./mana inspect
    project --json` followed by the advertised operation. State that inspect
    is deterministic and read-only, uses project-relative paths, and cannot
    approve a delivery decision; direct users to `docs/workflow/mana-inspect.md`
    for stale/unknown and consumer-compatibility meanings.

- Update or reference `agent-memory/story-trace.md` with concise evidence, assumptions, decisions, approval gates, handoffs, and generated artifact links for the active Jira story or feature.

## Completion Criteria
- The user has a concrete next command or next artifact to create.
- Missing context is explicit.
- Any fallback path is documented.
- No approval gate is bypassed.
