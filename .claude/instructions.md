# Mana Claude Code Instructions

For a Mana profile run, read the selected profile, then follow
`docs/policies/runtime-execution-contract.md` and
`docs/standards/output-contract.md`. Use `skills/index.yaml` for routing and
load only selected skill bodies.

Use progressive load-light routing, a compact caveman working style, and a
context budget that retains summaries and artifact paths instead of transcripts.

Treat healthy `.mana/user-context/` files as optional reusable personal
guidance, never as project truth or authority. Start with `index.md` or
`preferences.md` when present and inspect deeper files only when relevant.
Repository evidence and project/service constraints win on conflict. Never edit
the generated mirror.

`mana-orchestrator` coordinates at most three direct capability-class agents:
`mana-explorer`, `mana-full-specialist`, and serialized `mana-worker` only for
explicitly authorized writes. Return `needs_model_escalation` rather than
making unsupported high-risk judgments.

Configure Jira through `mcp/config/claude-jira-mcp.json` and a secure env file;
it is read-only unless a profile records explicit approval.
