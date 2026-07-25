# Mana Divination

`mana divination` makes a deterministic, read-only recommendation from a
natural-language delivery intent. It is a routing aid, not a profile runner.

## Current execution path and reuse

The generated project `mana` wrapper dispatches `profile` to
`scripts/run-profile.sh`. That runner loads `profiles/<name>.yaml`, resolves
its skill identifiers against `skills/index.yaml`, prepares runtime agents,
and can start Codex, Claude, or OpenCode. Divination is dispatched separately
to `scripts/divination.sh`; it sources `scripts/lib/divination.sh` and does not
call the runner or any of its agent, tool, hook, or external-command paths.

It reuses profile YAML (`name`, `trigger`, `skills`,
`human_approval_requirement`), skill front matter (`model_tier`,
`delegation_group`, `owner_role`), skill paths, and `.mana/global` Service
Context conventions. Profile access now uses the shared
`scripts/lib/profile-metadata.sh` helper, also used by the runner. The only
additions are `config/divination-domains.tsv`, a small reviewed alias table,
and an optional profile-local `divination` block. Neither changes the profile
loader, filesystem abstraction, or CLI framework.

## Optional profile metadata

Add `divination` metadata only when a profile's existing trigger and skills do
not distinguish its intended delivery domain well enough. Existing triggers
remain authoritative lifecycle evidence, and profiles without this block remain
fully supported.

```yaml
divination:
  intents:
    - contract change
  domains:
    contract: strong
    liquibase: medium
  positive_signals:
    - kafka
  negative_signals:
    - documentation only
  required_context:
    - integration-map
  conflicts_with:
    - emergency-hotfix
```

`domains` uses only the canonical domains in `config/divination-domains.tsv`;
aliases stay central in that table. Strength is `strong`, `medium`, or `weak`.
`required_context` uses a known Service Context mapping (for example
`integration-map` maps to `integration-map.md`). `conflicts_with` names another
profile. All keys are optional. The validator rejects duplicate normalized
intent terms, unknown domains/profiles/context, invalid strengths, signals that
are both positive and negative, and unknown keys—including any attempted
governance or approval override.

Good metadata is a small routing hint backed by already-declared profile skills
and context. Bad metadata lists skills to run, a shell command, `runner`,
`human_approval_requirement`, or an alternate approval rule. Skills still come
exclusively from the selected profile; governance still comes from the profile,
agents, and skills.

## Use

```bash
mana divination "Add a field to a Kafka contract and persist it in Oracle using Liquibase"
mana divination "Review a migration" --explain
mana divination "Review a migration" --json
printf '%s\n' "Review a migration" | mana divination --json
```

Human output starts with `MANA DIVINATION` and ends with `No spell has been
cast.` Errors start with `MANA MEDITATION` and name the actionable missing file
or metadata.

## Scoring and confidence

The engine normalizes case and punctuation, then matches exact normalized
aliases from `config/divination-domains.tsv`. A profile receives +20 for each
detected domain for which it declares a mapped skill and -12 for a contradictory
domain. Optional metadata adds an explicit domain weight (`strong` +25,
`medium` +15, `weak` +8), a matching positive signal (+6), a matching negative
signal (-16), a missing required-context penalty (-8), or a declared profile
conflict (-20). A matching existing profile trigger contributes +10. Candidates
are ordered by score descending, then profile name ascending. Equal top scores
are reported as `ambiguous`; no arbitrary default is used.

For a matching profile only, small conventional markers such as AsyncAPI,
Liquibase configuration/changelogs, build metadata, and test directories add
two points as repository stack confirmation. The engine performs only local
reads for those markers.

Scores are ranking factors, not probabilities. Confidence is `high` for a
recommended score of 40 or more, `medium` for a lower recommendation,
`ambiguous` for a tied top result, and `insufficient-evidence` where no profile
has enough matching evidence. Missing Service Context is reported separately
as evidence completeness.

`--explain` includes candidates' positive and negative signals, reason codes,
context gaps, unsupported terms, and the tie rule. `--json` has stable key
order; each candidate includes structured reason codes such as
`DOMAIN_EXPLICIT_MATCH`, `PROFILE_TRIGGER_MATCH`, `STACK_CONTEXT_MATCH`,
`NEGATIVE_SIGNAL_MATCH`, `REQUIRED_CONTEXT_MISSING`, and `PROFILE_CONFLICT`.

## Limitations

This MVP does not use an LLM, embeddings, a network request, MCP, or external
AI service. It cannot infer technologies absent from the intent, alias table,
skill declarations, or Service Context. Divination recommends only; it never
grants human approvals or starts execution.
# Saved recommendation compatibility

Divination JSON schema version 2 includes a `recommendationContextFingerprint`
over a sorted logical manifest of recommendation inputs. `mana cast --from`
requires this strong fingerprint and rejects older profile-only results with an
instruction to rerun divination. The fingerprint excludes timestamps, absolute
paths, generated output, runtime telemetry, and unrelated files.
