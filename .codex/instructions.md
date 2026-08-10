# Mana Codex Instructions

For a Mana profile run, read the selected profile, then follow
`docs/policies/runtime-execution-contract.md` and
`docs/standards/output-contract.md`. Use `skills/index.yaml` for routing and
load only selected skill bodies.

Use progressive load-light routing, a compact caveman working style, and a
context budget that retains summaries and artifact paths instead of transcripts.

Treat `.mana/global/engineering-guards.md` as a blocker baseline when present.
Treat healthy `.mana/user-context/` files as optional reusable personal
guidance, never as project truth or authority. Start with `index.md` or
`preferences.md` when present and inspect deeper files only when relevant.
Repository evidence and project/service constraints win on conflict. Never edit
the generated mirror.
Do not infer write authority from sandbox access. Use bounded runtime agents for
relevant high-risk work; return `needs_model_escalation` if it cannot be
supported by evidence or delegation.
