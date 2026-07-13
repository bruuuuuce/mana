# Codex Runner

Codex should run repository analysis, story planning, branch validation, PR readiness, documentation generation, and learning workflows.

## Operating Principles
- Skills are atomic and reusable.
- Agents orchestrate skills and produce phase artifacts.
- MCP access is governed, audited, redacted, and least-privilege.
- Humans remain accountable for clarity, design, implementation, approval, and correctness.
- AI reduces churn by surfacing gaps early and preserving evidence.
- Codex should start on the configured economy model and escalate only when the evidence requires deep judgement.

## Model Policy
`scripts/run-profile.sh --codex` passes `--model` to `codex exec`.

Default model settings:

```bash
MANA_CODEX_MODEL=gpt-5-mini
MANA_CODEX_FULL_MODEL=gpt-5
MANA_CODEX_MODEL_POLICY=economy-first
```

Use `--codex-model`, `--codex-full-model`, or the environment variables above
to override them per run.

The runner identifies escalation candidate skills from the selected profile:

- skills with `risk_level: high`
- skills with optional front matter `model_tier: full`

The initial model may perform routing, evidence inventory, low-risk checks, and
load-light skill inspection. If the evidence requires one of the full-model
candidates, or the current model cannot confidently judge architecture,
security, database, concurrency, cross-service, production, or large-diff risk,
the agent must stop with `needs_model_escalation` and tell the user to rerun the
same command with `MANA_CODEX_MODEL=$MANA_CODEX_FULL_MODEL` or
`--codex-model <full-model>`.

## Practical Use
Use the related profiles and templates to create repeatable artifacts. Fill each artifact with project-specific evidence and route blockers to the accountable owner.
