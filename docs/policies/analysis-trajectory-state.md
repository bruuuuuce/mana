# Analysis Trajectory Guard — Host-owned State (TG03)

TG03 defines the state needed to re-anchor a future analysis without changing
the current analysis path. The implementation is deterministic, offline, and
zero-token. It does not dispatch a provider, classify drift, trigger a
checkpoint, block an analysis, or change Story Start Scope v2 semantics.

The structured contracts under `contracts/analysis-trajectory/` are the source
of truth. `scripts/lib/analysis-trajectory-state.py` supplies host-side semantic
validation in addition to JSON Schema validation.

## Ownership boundary

The host creates a Mission Contract from two authoritative inputs:

1. a validated `mana.story-start.discovery-package/v1`, which supplies the
   story ref, normalized objective, and bounded acceptance-criterion text;
2. a `mana.analysis-trajectory.mission-seed/v1`, which supplies deterministic
   run metadata, authoritative input refs, mandatory constraints, evidence-gap
   definitions, evidence-scope policy, stop conditions, prohibited actions,
   and budgets.

The resulting `mana.analysis-trajectory.mission-contract/v1` has canonical
ordering, a host-derived mission ID, revision number, host provenance, and a
SHA-256 hash over the complete contract except the hash field itself. A direct
edit invalidates the hash. There is no command that accepts model output as a
replacement Mission Contract, mission ID, hash, revision, or provenance.

`create-mission` also creates a `mission-history/v1` containing revision 1.
`revise-mission` is the only supplied transition. It requires an explicit
versioned request, active revision match, approval authority ref, and
proposal/approval ref. It appends revision `N+1`, links its hash to revision
`N`, and preserves every earlier revision. An approved scope-expansion
transition must accept exactly scopes already recorded as proposed. Globally
mandatory scopes cannot be removed. The command provides the state mechanism;
human approval UI and approval acquisition are outside TG03.

## Evidence-scope policy

The policy is semantic rather than a repository-path whitelist. It separates:

- initial story/component scopes;
- dependencies explicitly named by requirements;
- scopes linked to verified mandatory constraints;
- proposed but unapproved expansions;
- globally mandatory security, compliance, and data-integrity scopes.

`allowedEvidenceScopeRefs` is derived from the first, second, third, and fifth
groups. Proposed scopes are excluded until an approved host-owned revision
moves them into an accepted group. This keeps a new dependency explainable
without suppressing mandatory cross-cutting investigation.

## Evidence-gap lifecycle

Each `evidence-gap/v1` has a bounded description, related acceptance-criterion
and mandatory-constraint refs, expected evidence type, optional source hint,
status, and opening/closing event refs. Gap IDs and relations are validated
against the active Mission Contract.

Mission revisions contain immutable initial gap definitions in `OPEN` state.
The Ledger derives current state from telemetry. `evidence_gap_closed` performs
the only TG03 close transition. A repeated close or an attempt to reopen a
resolved gap is rejected. TG02 cannot safely carry a new gap description, so
an event may reference only a gap already defined by host-owned state. A later
integration phase may create such definitions from another validated
host-visible artifact; TG03 does not invent text from opaque provider work.

## Trajectory Ledger

`trajectory-ledger/v1` is recomputed from the active Mission Contract and an
ordered TG02 `event/v1` stream. Validation recomputes it and requires an exact
match, so event-derived counters and refs cannot be supplied independently.
It records:

- mission ID, hash, and revision;
- source run/event range and event-stream hash;
- covered goals and current evidence-gap states;
- current and visited scopes;
- evidence added since the last checkpoint;
- rejected-hypothesis, open-decision, and expansion-proposal event refs;
- repeated-target and no-new-evidence counters;
- provider iteration and budget-consumption counters;
- terminal state and the observed provider-boundary granularity.

TG02 has no checkpoint events, so TG03 always records `lastCheckpoint.outcome`
as `NONE`. It does not anticipate TG04 trigger or outcome semantics.

Arrays are capped by Mission Contract hard budgets. Any dropped ref count is
recorded in `truncations`, while `sourceEvents` retains the first/last event
refs, total count, and hash needed to find the detailed append-only sidecar.
The Ledger contains no prose diary and no conversation history.

For a `hypothesis_rejected` event, the event ID is the stable rejection ref and
its target is the host-visible correlation key available in TG02. The
rejection remains active until a later event contributes new evidence on the
same target. The implementation does not claim visibility into provider-
internal hypotheses or tool calls.

## Compact checkpoint envelope

`build-envelope` constructs but never sends a
`checkpoint-envelope/v1`. It contains only:

- the immutable current Mission Contract and hash;
- the current derived Ledger snapshot;
- bounded, ref-only evidence events since the last checkpoint;
- externally supplied trigger reason codes;
- validated next-action proposals, when the caller has real options.

Every next action must link to an active acceptance criterion, mandatory
constraint, or known evidence gap. A target outside the accepted evidence
scope must be marked as requiring expansion. TG03 does not accept or execute
the action.

Envelope size is measured as canonical UTF-8 JSON bytes, excluding the final
artifact newline. The token proxy is `ceil(serialized_bytes / 4)`. Soft-limit
excess is recorded; hard byte or token-proxy excess fails before publication.
Evidence-delta event count has its own hard cap and reports truncation. The
envelope contains neither mission revision history nor the full telemetry
history.

## Commands and artifacts

The helper exposes these offline operations:

```text
create-mission <story-package> <mission-seed> <mission> <history>
validate-mission <mission>
validate-history <history>
revise-mission <history> <approved-request> <new-current-mission>
derive-ledger <mission> <events-jsonl> <ledger>
validate-ledger <mission> <events-jsonl> <ledger>
build-envelope <mission> <ledger> <events-jsonl> <checkpoint-input> <envelope>
validate-envelope <mission> <ledger> <events-jsonl> <envelope>
```

TG03 does not choose runtime publication paths and is not sourced by
`run-profile.sh` or Story Start Scope v2. Runtime creation/publication belongs
to the later integration phase. Feature-disabled behavior therefore remains
exactly the pre-TG03 path.

TG06 now supplies that integration without changing the TG03 contracts. The
default `revise_mission` transition still requires a scope already recorded as
proposed. Its TG06-only call path may additionally provide the exact scope from
a validated external expansion-proposal sidecar; the separately supplied
revision request must still approve that exact scope and satisfy every normal
hash, revision, history, and newly-allowed-scope check.

## Observable limits and explicit non-goals

Mana can validate provider invocation/completion, host synthesis, publication,
and the other real boundaries emitted by TG02. For an opaque provider it can
derive a valid but less detailed Ledger and marks that granularity explicitly.
It cannot validate individual provider-internal file reads, tool calls,
delegations, hypotheses, or context changes that are not returned through a
host-visible structured boundary.

TG03 introduces no drift rules, checkpoint policy, checkpoint model call,
re-anchor behavior, enforcement mode, autonomous loop, prompt repetition,
Scope v2 schema change, or implementation-scope classification.
