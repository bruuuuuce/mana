# Context Runtime v2 architecture decision

Status: accepted for staged implementation (CTX-00). This document changes no runtime behavior.

## Decisions

Mana will use host-owned, finite orchestration: declared phases, bounded retrieval/retry limits, and host-enforced permissions. It will not create an autonomous planning loop.

Fresh provider invocations at phase and worker boundaries are the reliable isolation boundary. Provider-managed subagents are optional optimizations and cannot be required for correctness.

Every phase will receive an immutable, host-generated governance envelope. Models may report gates and permissions but cannot amend, grant, or weaken them.

Raw evidence will be stored once by the host and exposed through stable bounded references. Handoffs carry references and validated facts, not transcripts.

Phase handoffs will be structured checkpoints, schema-validated and evidence-backed. They retain uncertainty and cannot increase permissions.

Usage accounting will be a separate, privacy-preserving metric surface: no prompt, response, tool payload, source content, credentials, or private reasoning is persisted.

The legacy runtime remains available through rollout. Context Runtime v2 is additive until profile-specific equivalence and human release gates pass.

## CTX-00 baseline contract

`scripts/mana-context-baseline.sh` is local-only and deterministic for unchanged inputs. By default it emits JSON to stdout and creates no project or `.mana` state. `--output` is explicit opt-in for a file artifact; `--project-root` optionally supplies a project whose existing Service Context can be measured read-only. Sizes are bytes plus a clearly labelled `bytes_divided_by_4_estimate`; they are not measured provider tokens. Provider capabilities remain `unknown` until CTX-02 establishes their contract.

## CTX-02 provider capability contract

`contracts/context-runtime/provider-capabilities-v1.schema.json` is the
provider-neutral capability contract. Every named capability is explicitly
`supported`, `unsupported`, or `unknown`; `unknown` is an evidence gap and is
never promoted to support. Reports are derived from the installed provider's
version/help/config probe, or from equivalent deterministic fixtures. They do
not use version-range guesses and are not cached. Each adapter recognizes its
own authoritative help grammar. A token mentioned in prose is not evidence of
support, missing declarations in a partial or unexpected help surface remain
`unknown`, and `unsupported` requires an explicit negative declaration on a
recognized surface (or an equivalent structured negative probe result).

Provider-managed children remain optional. A report of support for child agent
definitions does not prove fresh child context, effective child model routing,
or recursive-delegation prevention. Those properties remain `unknown` unless a
local provider surface proves them. Host-launched fresh invocations remain the
reliable future isolation and model-routing boundary.

Adapters collect positive and authoritative negative evidence independently
for every capability, retaining safe probe provenance until one provider-neutral
resolver applies `0/0 -> unknown`, `1/0 -> supported`, `0/1 -> unsupported`, and
`1/1 -> unknown`. Provider help declarations are evaluated as complete semantic
blocks, so a positive prefix followed by a same-line or continuation-line
refutation cannot produce support.

Composite capabilities are resolved in a second, mechanically separate step.
Their required prerequisites are first resolved atomically to `supported`,
`unsupported`, or `unknown`; the composite consumes only those states and
cannot reopen raw evidence. All required states supported produces support, an
authoritatively unsupported required state produces unsupported, and otherwise
uncertainty propagates as unknown. Direct evidence about the composite itself
is resolved separately, and a contradiction with the derived state becomes
unknown.

The legacy `--no-codex-subagents` and `--no-claude-subagents` flags select
provider-specific mechanical denies in addition to the matching prompt policy
and an effective maximum child count of zero. OpenCode selects a unique inline
primary with `permission.task: deny`; that configures the built-in Task entry
point, but does not prove runtime recursive-delegation prevention. Merged
user/project configuration also means complete hard disable and user-config
isolation remain `unknown`. Claude safe mode proves only its declared custom
command/agent scope, so complete user-config isolation remains `unknown` there
as well. Disabled Claude and OpenCode paths do not create or rewrite persistent
managed orchestrator files.
This is an isolation correction only; CTX-02 does not introduce fresh phase
execution, delegation packets, context manifests, evidence stores, or
compaction budgets.
