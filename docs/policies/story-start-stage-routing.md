# Story Start Scope v2 Stage Routing

## Purpose

Story Start Scope v2 resolves a model and requested reasoning effort separately
for Discovery, Scope Triage, Implementation Planner, targeted Correction, and
the future Trajectory Checkpoint route. This policy is additive: it applies
only to `story-start` when `MANA_STORY_START_SCOPE_VERSION=v2` is selected.
The default v1 profile invocation continues to use its existing root-model
routing.

The checkpoint route is configuration-only in this release. No checkpoint
provider invocation, telemetry, Mission Contract, Ledger, or control-flow
behavior is added by this policy.

## Stage Names

| Stage | CLI segment | Environment segment |
|---|---|---|
| Discovery | `discovery` | `DISCOVERY` |
| Scope Triage | `triage` | `TRIAGE` |
| Implementation Planner | `planner` | `PLANNER` |
| Targeted Correction | `correction` | `CORRECTION` |
| Future Trajectory Checkpoint | `trajectory-checkpoint` | `TRAJECTORY_CHECKPOINT` |

## Configuration And Precedence

For each selected provider and stage, model and effort are resolved
independently in this order:

1. stage-specific CLI option;
2. provider-specific stage environment variable;
3. an explicitly supplied root provider model or root compatibility effort;
4. provider-stage default checked into Mana.

The root compatibility value intentionally precedes the default. This keeps
existing users who set only `MANA_CODEX_MODEL` or `--codex-model` on a single
model for all Scope v2 stages. With no explicit root override, the pilot stage
defaults apply. There is no separate configuration-file layer today; the
checked-in provider-stage table is the repository fallback.

Stage-specific CLI options apply only to `story-start` v2:

```text
--story-start-<stage>-model <model>
--story-start-<stage>-effort <minimal|low|medium|high|xhigh>
```

For example:

```bash
MANA_STORY_START_SCOPE_VERSION=v2 \
MANA_STORY_START_CONTEXT=.mana/features/EXAMPLE/context/story-start-context.json \
scripts/run-profile.sh story-start --codex \
  --story-start-triage-model gpt-5.6-sol \
  --story-start-triage-effort xhigh
```

Provider-specific stage environment variables use this form:

```text
MANA_<PROVIDER>_STORY_START_<STAGE>_MODEL
MANA_<PROVIDER>_STORY_START_<STAGE>_EFFORT
```

For example:

```text
MANA_CODEX_STORY_START_DISCOVERY_MODEL=gpt-5.6-terra
MANA_CODEX_STORY_START_DISCOVERY_EFFORT=high
```

The root compatibility values are `MANA_CODEX_MODEL`, `MANA_CLAUDE_MODEL`, and
`MANA_OPENCODE_MODEL`; the matching root effort variables are
`MANA_<PROVIDER>_REASONING_EFFORT`. CLI equivalents are
`--<provider>-model` and `--<provider>-reasoning-effort`. Root effort is used
only as a Scope v2 stage-routing fallback; it does not alter the v1 root
provider arguments.

## Provider-Stage Defaults

| Provider | Discovery | Triage | Planner | Correction | Trajectory checkpoint |
|---|---|---|---|---|---|
| Codex | `gpt-5.6-terra` / `high` | `gpt-5.6-sol` / `xhigh` | `gpt-5.6-sol` / `high` | `gpt-5.6-terra` / `high` | `gpt-5.6-terra` / `high` |
| Claude | `sonnet` / `high` requested | `opus` / `xhigh` requested | `opus` / `high` requested | `sonnet` / `high` requested | `sonnet` / `high` requested |
| OpenCode | `opencode/gpt-5.1-codex` / `high` requested | `opencode/gpt-5.1-codex` / `xhigh` requested | `opencode/gpt-5.1-codex` / `high` requested | `opencode/gpt-5.1-codex` / `high` requested | `opencode/gpt-5.1-codex` / `high` requested |

These are Scope v2 defaults only. They do not rewrite global defaults used by
other Mana profiles or change the Codex/Claude/OpenCode root agents in v1.

## Provider Dispatch Truthfulness

`mana_provider_synthesis_args` sends Codex's selected effort explicitly as
`model_reasoning_effort` after `--ignore-user-config`, so the host-owned route
survives isolated execution. The Codex phase call is still schema-bound,
read-only, ephemeral, and has subagents disabled.

Current Claude and OpenCode synthesis adapters accept the selected model but do
not expose a verified reasoning-effort argument. Their diagnostics report the
requested effort with `effort_dispatch=unsupported`; they do not claim it was
applied. A future adapter may add a documented provider-specific equivalent,
with a routing test, before changing this status.

There is no automatic provider fallback. A missing selected provider fails the
same bounded Scope v2 path; it never falls back to v1, another provider, or
free-form output.

## Diagnostics

At a v2 public run, `scripts/run-profile.sh` emits one line for each route:

```text
Story Start Scope v2 route: stage=triage provider=codex model=gpt-5.6-sol model_source=provider-stage-default effort=xhigh effort_source=provider-stage-default effort_dispatch=explicit
```

The line contains only stage, provider, model, requested effort, source, and
dispatch capability. It contains no prompt body, story context, token, secret,
credential, source content, or provider response. The checkpoint line is a
resolved configuration diagnostic only; it is not evidence of a checkpoint
call.

To verify routing offline, run:

```bash
tests/story-start-stage-routing.sh
```

The test covers every route, CLI/environment/root/default precedence, Codex
effort transport, unsupported-effort diagnostics, exactly three successful v2
phase calls, the unused checkpoint route, and unchanged v1 root routing.

## Compatibility

- Existing `--codex-model`, `--claude-model`, and `--opencode-model` settings
  remain a Scope v2 compatibility fallback when explicitly supplied.
- With no root or stage override, v2 uses the table above.
- The v1 default and unrelated profiles do not resolve or print stage routes.
- Stage-specific options are rejected outside `story-start` v2 so a typo cannot
  silently alter an unrelated profile.
- Story Start Scope v2 preserves its existing public CLI form, validation,
  artifact schemas, three normal provider calls, bounded correction, and
  fail-closed behavior.
