# Codex Setup

Use Codex for planning, repository analysis, branch validation, PR readiness, documentation, and learning. Codex must respect MCP policies and prefer reports or proposed patches over destructive edits.

Codex should resolve the active `.mana` workspace before producing artifacts. Feature work belongs under `.mana/features/<feature-id>/`; canonical branch work belongs under `.mana/sessions/<timestamp>-<branch>-<purpose>/`.

## Mana Runtime Agents

Mana installs three Codex custom agents under `.codex/agents/`:

- `mana_explorer`: read-only evidence discovery.
- `mana_full_specialist`: read-only high-risk/full-tier judgment.
- `mana_worker`: bounded serialized writing only when a selected Mana profile explicitly permits source modification.

These are runtime capability classes, not Mana semantic agents. Mana semantic
agents remain under `agents/`, and reusable skills remain under `skills/`.
Do not create one Codex subagent per Mana skill. Batch related work by risk
domain and spawn at most three direct child agents with depth one.

If custom agents are disabled, missing, fail, or leave high-risk evidence
unsupported, return `needs_model_escalation` with a concise handoff artifact
instead of performing deep high-risk judgment on the small root model.
