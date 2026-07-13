# Codex Runner

Codex should run repository analysis, story planning, branch validation, PR readiness, documentation generation, and learning workflows.

## Operating Principles
- Skills are atomic and reusable.
- Agents orchestrate skills and produce phase artifacts.
- MCP access is governed, audited, redacted, and least-privilege.
- Humans remain accountable for clarity, design, implementation, approval, and correctness.
- AI reduces churn by surfacing gaps early and preserving evidence.
- Codex should start on the configured economy model and delegate bounded difficult work to stronger custom agents only when evidence requires deep judgment.

## Model Policy
`scripts/run-profile.sh --codex` passes `--model` to `codex exec`.

Default model settings:

```bash
MANA_CODEX_MODEL=gpt-5.4-mini
MANA_CODEX_EXPLORER_MODEL=gpt-5.6-terra
MANA_CODEX_FULL_MODEL=gpt-5.6-sol
MANA_CODEX_WORKER_MODEL=gpt-5.6-terra
MANA_CODEX_MODEL_POLICY=economy-first
MANA_CODEX_SUBAGENTS=true
MANA_CODEX_MAX_THREADS=3
```

Use `--codex-model`, `--codex-explorer-model`, `--codex-full-model`,
`--codex-worker-model`, `--no-codex-subagents`, or the environment variables
above to override behavior per run. `--codex-full-model` controls the model
written into `mana_full_specialist`, not just a fallback message.

The runner identifies escalation candidate skills from the selected profile:

- skills with `risk_level: high`
- skills with optional front matter `model_tier: full`

The root model may perform routing, workspace and requirement-source
resolution, evidence inventory, low-risk checks, load-light skill inspection,
delegation planning, aggregation, and final synthesis. It must not directly do
deep architecture, security, database production, concurrency, cross-service,
transactional, production-failure, large ambiguous diff, or `model_tier: full`
judgment.

When that work is required, the root delegates to at most three direct Codex
custom agents:

- `mana_explorer`: read-only evidence discovery and inventories.
- `mana_full_specialist`: read-only high-risk/full-tier judgment.
- `mana_worker`: one serialized writer only when a Mana profile explicitly
  permits source modification. It is installed but not selected automatically by
  analysis-only profiles.

Child agents must not spawn further agents. Related Mana skills are batched by
risk domain; one subagent per skill is forbidden. Independent read-heavy groups
may run in parallel. Write-heavy work is serialized.

Fallback remains explicit. If subagents are disabled, missing, unsupported,
fail to spawn, return insufficient evidence, or cannot complete a high-risk
judgment safely, the run preserves a concise handoff artifact and returns
`needs_model_escalation` with the existing full-model override guidance.

Subagents can increase total token usage. The benefit is smaller root context
and narrower expensive-model usage.

## Delegation Groups

Mana skill metadata may include optional runner-neutral fields:

```yaml
model_tier: economy | full
execution_mode: read | write
delegation_group: requirements | source | tests | architecture | contracts | database | security | operations | documentation | implementation
parallel_safe: true | false
```

Older skills without these fields are routed by fallback evidence:
`model_tier`, `risk_level`, allowed tools, skill purpose, selected profile,
agent context, and whether work is read-heavy or write-heavy.

For `story-start`, a normal run should resemble one requirements group handled
by the root when low-risk, one repository explorer for read-heavy source/test
evidence, and one full specialist only when architecture, contracts, database,
security, or comparable risk is actually present.

## Practical Use
Use the related profiles and templates to create repeatable artifacts. Fill each artifact with project-specific evidence and route blockers to the accountable owner.
