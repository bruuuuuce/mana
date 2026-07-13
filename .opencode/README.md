# OpenCode Setup

Use OpenCode for Mana profile execution when you want a project-scoped primary
orchestrator with bounded runtime subagents.

Mana installs OpenCode agents under `.opencode/agents/`:

- `mana_orchestrator`: primary agent for routing, light evidence inventory,
  low-risk checks, delegation, aggregation, and final synthesis.
- `mana_explorer`: read-only subagent for repository evidence discovery.
- `mana_full_specialist`: read-only subagent for architecture, security,
  database, contract, concurrency, production, and other high-risk judgment.
- `mana_worker`: bounded writer for profiles that explicitly permit source
  modification.

OpenCode agents are runtime capability classes only. Mana semantic agents remain
under `agents/`; Mana skills remain under `skills/`. Do not create one OpenCode
subagent per Mana skill. Batch related skills by risk domain and use at most
three direct subagents.

Run a profile with:

```bash
scripts/run-profile.sh story-start --opencode
```

OpenCode model IDs use `provider/model` format. Override defaults with
`MANA_OPENCODE_MODEL`, `MANA_OPENCODE_EXPLORER_MODEL`,
`MANA_OPENCODE_FULL_MODEL`, `MANA_OPENCODE_WORKER_MODEL`, or the matching
`--opencode-*` flags. Disable subagents with `MANA_OPENCODE_SUBAGENTS=false` or
`--no-opencode-subagents`.
