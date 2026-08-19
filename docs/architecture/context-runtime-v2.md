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
