# Analysis Trajectory Guard — Bounded Re-anchor Governor (TG05)

TG05 adds an opt-in trajectory checkpoint sidecar. A checkpoint can be built
only from a current, host-validated TG03 Mission Contract/Ledger/envelope and
an authoritative TG04 `CHECKPOINT_RECOMMENDED` result that explicitly permits
TG05. TG05 itself did not enter the public Story Start path or apply outcomes.
TG06 now reuses this unchanged bounded protocol at the real post-Discovery
boundary and owns all control-flow application described in
`analysis-trajectory-integration.md`.

Normal tests use synthetic response fixtures and make zero provider/network
calls. The separate live smoke requires explicit enablement and preconfigured
credentials.

## Versioned contracts

TG05 defines these additive contracts under `contracts/analysis-trajectory/`:

- `checkpoint-governor-config-v1`: `OFF` or `SHADOW`, with immutable maxima of
  one primary and one structural-repair call;
- `trajectory-checkpoint-request-v1`: the compact re-anchor input;
- `trajectory-checkpoint-response-v1`: the closed model output;
- `trajectory-checkpoint-validation-v1`: sanitized structural/semantic
  validation diagnostics;
- `trajectory-checkpoint-run-v1`: route, validation status, bounded call
  counts, and usage availability.

All objects reject extra fields. IDs, hashes, revision correlation, refs,
budgets, call policy, and prompt measurements are host-owned. The request has
its own content hash and a deterministic ID derived from the Mission, Ledger,
and TG04 recommendation hashes.

## Request construction

`analysis-trajectory-checkpoint.py build-request` accepts, in order:

```text
Mission Contract
Trajectory Ledger
TG02 JSONL events
TG04 drift configuration
TG04 observable-boundary record
TG03 checkpoint input/options
TG04 recommendation
output request path
```

The helper recomputes the Ledger, TG04 recommendation, and TG03 envelope before
publishing a request. A recommendation is eligible only when its outcome is
`CHECKPOINT_RECOMMENDED`, it carries at least one reference-grounded reason,
and `modelCheckpointPermittedInTG05` is true. A forged recommendation,
mismatched trigger reason, exhausted primary-call budget, or oversized
envelope/prompt fails before request publication.

The model receives only:

- the immutable Mission Contract and hash/revision inside the bounded TG03
  envelope;
- the current compact Ledger snapshot;
- bounded evidence events added since the last checkpoint;
- TG04 trigger reasons, categorized refs, and observed boundary;
- currently observable next-action options;
- remaining host budgets and the exact call policy;
- active open-decision refs and active rejected-hypothesis target mappings;
- closed outcome/stop choices and candidate scope-expansion choices.

It does not receive conversation history, chain-of-thought, prompt chronology,
repository dumps, raw source, Jira bodies, credentials, or customer data.
Provider-internal reads, tools, delegation, reasoning, and context expansion
remain unobservable.

## Re-anchor task and response

The deterministic prompt actively asks the model to restate the objective,
name the active goal/constraint/gap, classify the trajectory, and choose
exactly one permitted outcome. A recommended action must be one of the supplied
options. A new scope must be an owner-approved proposal; it cannot mutate the
Mission. Open decisions remain open. The prompt forbids implementation scope,
planning, estimates, code, and product/architecture choice.

The closed response fields are:

```text
missionId
missionHash
missionRevision
outcome
objectiveRestatement
supportingGoalRefs
supportingConstraintRefs
supportingGapRefs
supportingEvidenceRefs
recommendedNextAction or null
scopeExpansionProposal or null
stopReason or null
discardedOrDeferredRefs
confidence
```

Allowed outcomes are `ON_TRACK`, `REANCHOR_REQUIRED`,
`SCOPE_TRIAGE_REQUIRED`, `STOP_SUFFICIENT_EVIDENCE`,
`STOP_NO_NEW_EVIDENCE`, `STOP_HARD_BUDGET`, and
`NEEDS_OWNER_REVIEW`.

Outcome fields are mutually constrained. On-track/re-anchor outcomes require
one exact supplied action. Scope triage requires one proposal and never a
recommended action. Stop/review outcomes require the corresponding closed stop
reason and cannot carry an action or expansion.

## Host validation

Structural validation checks JSON shape, schema version, exact fields, types,
bounded text, sanitized refs, hashes, closed enums, budget-delta fields, and
the absence of prohibited raw fields. Only this class of first-call failure
may receive the single repair call.

Semantic validation rejects, with sanitized codes, at least:

- wrong Mission ID/hash/revision;
- unknown goal, constraint, gap, evidence, or deferred refs;
- a new or mutated next-action option;
- an action without active Mission justification;
- direct entry into an unapproved scope;
- an action that assumes an open decision;
- a revisit to an actively rejected target without superseding evidence;
- action/proposal budget deltas beyond the remaining hard budget;
- unsupported or unapproved scope-expansion choices;
- contradictory outcome/action/proposal/stop fields;
- a sufficiency stop contradicted by open gaps or uncovered mandatory work;
- a no-evidence or hard-budget stop unsupported by current host state;
- implementation-task, code, PR, story-point, or engineering-estimate leakage.

Semantic rejection is final for this trigger: it never receives a second
semantic exploration call and produces `NEEDS_OWNER_REVIEW` in the run record.

## Exact bounded-call policy

The policy is per deterministic TG04 trigger:

```text
primary checkpoint call:           0 or 1
structural/schema repair call:      0 or 1
semantic retry/exploration call:    0
maximum total calls:                2
```

The repair prompt contains only the original bounded request plus sanitized
validation error codes. It does not include the invalid provider response and
does not permit new semantic exploration. A second invalid result, semantic
rejection, provider failure, or unavailable repair budget ends in
`NEEDS_OWNER_REVIEW`; there is no loop and no silent unguarded continuation.

Run artifacts record the call kind, provider, TG01 model/effort route,
validation result, and provider usage when available. The current generic
stdout transport does not expose trustworthy token usage, so the schema marks
it explicitly as `UNAVAILABLE` rather than inventing a count.

## Prompt and envelope budgets

TG03 envelope byte and token-proxy hard limits are validated before request
composition. TG05 then measures the canonical request and exact rendered
primary prompt, using the repository token proxy of `ceil(bytes / 4)`. Request
and prompt must both remain inside the Mission Contract's hard envelope
limits. Soft-limit pressure is recorded in `promptMeasurements`; it does not
silently relax a hard cap.

The single repair prompt is independently measured before dispatch and must
fit the same hard limits. Oversized inputs are rejected deterministically; an
extra model summarization call is never used to shrink them.

## Modes

`OFF` requires `enabled: false` and records zero calls without reading a
request or response. `SHADOW` requires `enabled: true`; fixture or explicitly
enabled smoke calls may produce advisory validation/run artifacts, but the
result does not stop, redirect, re-prompt, or modify current production
analysis. There is no TG05 enforcement mode and no default-on configuration.

## Commands

```text
analysis-trajectory-checkpoint.py build-request <mission> <ledger> <events> <drift-config> <observation> <checkpoint-input> <recommendation> <request>
analysis-trajectory-checkpoint.py validate-request <mission> <ledger> <events> <drift-config> <observation> <checkpoint-input> <recommendation> <request>
analysis-trajectory-checkpoint.py render-prompt <request> <prompt>
analysis-trajectory-checkpoint.py assess-response <request> <response> <validation> [--calls-used 1|2]
analysis-trajectory-checkpoint.py render-repair-prompt <request> <validation> <prompt>
analysis-trajectory-checkpoint.py simulate <config> <request> <primary-response> <repair-response-or-dash> <run>
```

`simulate` treats synthetic response files as bounded provider-call fixtures;
it never invokes a provider.

## Opt-in synthetic live smoke

First build and validate a compact request from the synthetic TG03/TG04
fixtures. Then run the standalone checkpoint-only harness with already
configured provider credentials:

```text
MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_LIVE=true \
MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_CREDENTIALS_READY=true \
MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_PROVIDER=codex \
scripts/analysis-trajectory-checkpoint-smoke.sh \
  /path/to/synthetic-request.json \
  /path/to/sanitized-artifacts
```

The harness refuses non-synthetic story/input refs, prints the selected TG01
`trajectory-checkpoint` provider/model/effort route, caps execution at the
primary plus one structural repair, and saves the request, route, sanitized
validation reports, accepted schema-valid response (if any), and final run
record. Invalid raw provider output and provider stderr remain temporary and
are deleted. It never asks for credentials and is not part of normal CI.

## Explicit TG05 non-goals

TG05 does not enforce an outcome in the real analysis path, change Story Start
Scope v2 semantics or frozen schemas, add periodic checkpoints, debate with
multiple agents, create implementation plans, or wire downstream evidence
publication. These remain outside TG05; TG06 has not been started.
