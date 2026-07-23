# Claude Code Setup

Use Claude Code for planning, repository analysis, branch validation, PR readiness, documentation, development support, and learning. Claude Code can act as both a repository-level runner (like Codex) and a local implementation runner (like Junie) depending on the active profile.

Claude Code must respect MCP policies and prefer reports or proposed patches over destructive edits.

Claude Code should resolve the active `.mana` workspace before producing artifacts. Feature work belongs under `.mana/features/<feature-id>/`; canonical branch work belongs under `.mana/sessions/<timestamp>-<branch>-<purpose>/`.

## Mana Runtime Agents

Mana installs project-scoped Claude Code agents under `.claude/agents/`:

- `mana-orchestrator`: economy root for routing, light evidence inventory,
  low-risk checks, delegation, aggregation, and final synthesis.
- `mana-explorer`: read-only repository evidence discovery on `sonnet` by
  default.
- `mana-full-specialist`: read-only architecture, security, database,
  concurrency, contract, production, and full-tier judgment on `opus` by
  default.
- `mana-worker`: serialized bounded writing on `sonnet` only when a selected
  profile explicitly permits source modification.

The root defaults to `haiku`. Override models with `MANA_CLAUDE_MODEL`,
`MANA_CLAUDE_EXPLORER_MODEL`, `MANA_CLAUDE_FULL_MODEL`,
`MANA_CLAUDE_WORKER_MODEL`, or the corresponding `--claude-*-model` flags.
Disable delegation with `MANA_CLAUDE_SUBAGENTS=false` or
`--no-claude-subagents`.

These are runtime capability classes, not Mana semantic agents. Do not create
one subagent per Mana skill: batch related work by risk domain and use at most
three direct subagents. The root agent can invoke only these three capability
classes; child agents do not receive the `Agent` tool, so they cannot delegate
further. If delegation is disabled, unavailable, or insufficient for a
high-risk judgment, return `needs_model_escalation` with a concise handoff
artifact rather than letting the economy root make that judgment.

For Jira and Confluence access, configure the MCP server using `mcp/config/claude-jira-mcp.json`. See `docs/deployment/jira-mcp-docker-wrapper.md`.
