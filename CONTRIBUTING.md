# Contributing

Thanks for improving Mana. The project is intentionally structured around a few
hard boundaries; preserve them when contributing.

## Design Rules

- Skills stay atomic and reusable.
- Agents orchestrate skills; they should not duplicate skill logic.
- Profiles declare when and how workflows run.
- MCP integrations stay least-privilege, read-only by default, and explicit
  about approval requirements.
- Scripts must have graceful fallbacks when external systems are unavailable.
- Do not add real organization names, credentials, production data, or private
  architecture details to examples.

## Before Opening A Pull Request

Run:

```bash
scripts/validate-repo.sh
scripts/mana-doctor.sh
```

For shell changes, also run:

```bash
bash -n scripts/*.sh hooks/pre-commit hooks/pre-push
```

## Adding A Skill

Each skill must include:

- `SKILL.md` with required front matter.
- Inputs, outputs, decision rules, failure modes, MCP behavior, and human review
  gates.
- Good usage, bad usage, and sample output examples.

## Adding An Agent

Each agent must include:

- `AGENT.md`.
- `playbook.md`.
- `inputs.schema.json`.
- `outputs.schema.json`.
- At least one example run.

## Pull Request Standard

PRs should explain:

- what changed;
- which profile/agent/skill behavior is affected;
- how validation was run;
- any security, MCP, or approval-gate implications.
