# Analysis Trajectory Guard — Deterministic Shadow Policy (TG04)

TG04 adds an offline, zero-token detector over the TG03 Mission Contract and
Trajectory Ledger plus the underlying TG02 event stream. It emits only a
versioned `drift-recommendation/v1` advisory artifact. It does not stop,
redirect, re-prompt, retry, invoke a provider, mutate final analysis artifacts,
or enter the Story Start v1/v2 control flow.

The detector runs only through an explicit diagnostic invocation with a
validated `drift-config/v1` whose `enabled` value is `true` and whose mode is
`SHADOW`. A disabled or non-shadow configuration fails before publication.
There is deliberately no enforcement mode in TG04.

## Host-owned inputs and integrity

`scripts/lib/analysis-trajectory-drift.py analyze` accepts, in order:

```text
Mission Contract
Trajectory Ledger
TG02 JSONL event stream
TG04 drift configuration
TG04 observable-boundary record
output recommendation path
```

Before classification, the helper validates the Mission Contract and
recomputes the Ledger from the event stream using the TG03 state module. A
caller cannot forge mission correlation, counters, gap state, evidence state,
or budget consumption in the supplied Ledger. The recommendation carries the
mission ID/hash/revision, Ledger ID/hash, configuration hash, and its own
content hash.

The boundary record may carry structured next-action proposals only at the
real `NEXT_ACTION_BOUNDARY`. It contains IDs and refs, not provider prose. The
detector rejects unknown goals, non-open gaps, unknown constraints, unknown
decision/evidence refs, and event refs outside the correlated stream.

## Explicit signal rules

Every recommendation contains all eleven signal evaluations in canonical
order. Each evaluation is `TRIGGERED`, `CLEAR`, or `NOT_OBSERVABLE`; a triggered
signal must contain supporting refs.

| Signal | Deterministic host-visible rule |
|---|---|
| `UNSUPPORTED_NEXT_ACTION` | A structured next action has no active acceptance-criterion, open-gap, or mandatory-constraint ref. Without a structured boundary the signal is `NOT_OBSERVABLE`. |
| `UNAPPROVED_SCOPE_EXPANSION` | A structured action targets a scope absent from the active contract's `allowedEvidenceScopeRefs`. Proposed-but-unapproved scopes remain unapproved. |
| `OPEN_DECISION_ASSUMPTION` | A structured action marks a currently open decision as assumed while supplying no correlated decision-evidence ref. Provider reasoning is never inferred. |
| `REPEATED_TARGET_NO_NEW_EVIDENCE` | The configured number of visits reaches the same configured semantic target group and every revisit after the first adds no evidence. Event refs ground the finding. |
| `NO_NEW_EVIDENCE_STREAK` | The derived Ledger streak and the correlated tail of completed host-visible iterations both reach the configured threshold. |
| `REJECTED_HYPOTHESIS_REOPENED` | A rejected target is revisited at a host-visible boundary with no intervening evidence on that target. Both rejection and revisit event refs are retained. |
| `SOFT_BUDGET_PRESSURE` | Any supported consumption counter reaches the configured warning percentage of its Mission Contract soft limit. This recommends a checkpoint; it never stops TG04 execution. |
| `HARD_BUDGET_EXCEEDED` | Any supported consumption counter is greater than its Mission Contract hard limit. TG04 recommends a future hard stop but does not enforce it. |
| `SUFFICIENT_EVIDENCE_REACHED` | Every acceptance criterion has the configured evidence count, every mandatory constraint has the configured resolved-gap count, and no evidence gap remains open. |
| `MANDATORY_CROSS_CUTTING_EXPANSION` | An accepted target is a globally mandatory scope or is linked to the action's mandatory constraint. This is a positive explanation and is not drift. |
| `FINAL_SYNTHESIS_CHECKPOINT` | The caller explicitly presents the final-synthesis boundary. No elapsed counter or periodic prompt repetition can trigger it. |

Budget analysis is limited to counters with direct Mission Contract limits:
event count, provider iterations, distinct evidence refs, and distinct visited
scopes. The detector does not invent provider token consumption.

## Conservative defaults and calibration

The committed diagnostic configuration uses:

```text
repeated target visits:             3
consecutive no-evidence iterations: 3
soft-budget warning point:          80 percent
minimum evidence refs per goal:     1
minimum resolved gaps per mandatory constraint: 1
all evidence gaps must be resolved for sufficiency
```

Thresholds are versioned configuration, not constants selected inside fixture
branches. Semantic target equivalence is also explicit configuration; the
detector does not perform fuzzy text matching.

The committed `tg04-evaluation-matrix-v1.json` is regenerated from 15 actual
recommendations. It records expected and actual outcomes/reasons,
false-positive and false-negative notes, and observability limitations. The
matrix covers the TG00 on-track, dependency expansion, unrelated finding,
architecture alternative, repetition, mandatory security, and opaque-provider
topologies, plus dedicated hard/soft budget, sufficiency, rejected-hypothesis,
unsupported-action, no-evidence-streak, and final-synthesis controls.

## Recommendation policy

The closed outcome set is:

```text
CONTINUE_ON_TRACK
CHECKPOINT_RECOMMENDED
SCOPE_TRIAGE_REQUIRED
STOP_SUFFICIENT_EVIDENCE
STOP_NO_NEW_EVIDENCE
STOP_HARD_BUDGET
NEEDS_OWNER_REVIEW
```

When several explicit signals apply, the deterministic precedence is:

```text
hard budget
→ sufficient evidence
→ unapproved scope expansion
→ open decision assumption
→ no-new-evidence streak
→ checkpoint-worthy warning/final boundary
→ continue on track
```

The positive mandatory-cross-cutting signal does not by itself change
`CONTINUE_ON_TRACK`. `modelCheckpointPermittedInTG05` is true only for
`CHECKPOINT_RECOMMENDED`; this is contract metadata for a possible later phase,
not a call or permission implemented by TG04. Future enforcement-unsafety is
true only for unapproved scope, unresolved-decision review, no-evidence stop,
and hard-budget stop. Sufficient evidence is a stop recommendation because
continued work is unnecessary, not because the current shadow run is unsafe.

## Real boundaries and known limits

Supported boundaries are host-visible iteration, structured next action,
provider invocation/completion, and explicit final synthesis. Mana still cannot
observe provider-internal file reads, searches, tool calls, retries,
delegations, hypotheses, or context expansion. At an opaque provider boundary,
the artifact lists these facts as unsupported and records structured next
action as `NOT_OBSERVABLE` instead of inferring it from provider text.

TG04 itself introduced no public wiring. TG06 now imports the unchanged
detector through its integration helper and invokes it after the real Story
Start v2 Discovery completion boundary. The detector remains deterministic
and zero-token; only the TG06 host layer can apply its recommendation.

## Commands

```text
analysis-trajectory-drift.py analyze <mission> <ledger> <events> <config> <observation> <recommendation>
analysis-trajectory-drift.py validate-recommendation <mission> <ledger> <events> <config> <observation> <recommendation>
analysis-trajectory-drift.py build-matrix <matrix-input> <matrix-output>
```

`build-matrix` reads previously generated recommendations and produces only
calibration output. It does not run analysis or a provider.

## Explicit TG04 non-goals

TG04 does not invoke a checkpoint model, enforce a recommendation, build a
re-anchor governor, add correction calls, rewrite prompts, modify frozen Story
Start Scope v2 schemas, wire final Story Start control flow, or tune from live
stories. Those later-phase behaviors are neither implemented nor scaffolded.
