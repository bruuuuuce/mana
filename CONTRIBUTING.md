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
- Existing shell scripts stay in Bash, but new scripts that exceed roughly 150
  lines or need non-trivial argument parsing, state, or structured data
  handling are written in Python (stdlib only). Bash cost grows non-linearly
  with size; do not grow another `run-jira-mcp-docker.sh`.
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

For changes to profiles, agents, playbooks, skills, or shared instruction
text, run the behavioral eval scenarios in `evals/` that cover the touched
behavior (see `evals/README.md`) and report the outcome in the PR.

## Adding A Skill

Before adding a skill, check whether an existing skill can absorb the new
judgement as an extra dimension or input. A new skill is justified only when no
existing skill can cover it without losing atomicity.

Each skill must include:

- `SKILL.md` with required front matter.
- A `stack` front matter field naming the technology or tooling the target
  project must use for the skill to apply (for example `java`, `liquibase`,
  `sonar`), or `any` for stack-agnostic skills. Runners use it to discard
  non-applicable skills without deep-loading them.
- Prefer canonical `stack` values: `any`, `java`, `liquibase`, `sonar`,
  `database`, `messaging`, `api`, `security`, `frontend`, `dependency`, and
  `workflow`. Add a new value only when these would make filtering misleading.
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
