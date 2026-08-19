# Analysis Trajectory Guard — Story Start v2 Integration (TG06)

TG06 wires the host-owned contracts from TG02–TG05 into the existing public
Story Start Scope v2 path. It does not introduce a second orchestrator and it
does not change the frozen Discovery, Triage, Planner, or Scope Governor
schemas.

## Modes and activation

The guard is available only when Story Start Scope v2 is already selected.

```text
MANA_ANALYSIS_TRAJECTORY_MODE=off       default
MANA_ANALYSIS_TRAJECTORY_MODE=shadow    observe is accepted as an alias
MANA_ANALYSIS_TRAJECTORY_MODE=enforce   explicit opt-in only
```

`off` does not initialize trajectory telemetry and publishes no Mission,
Ledger, recommendation, checkpoint, integration, or evidence-package
artifacts. The provider call count, prompts, output, and v1/v2 compatibility
behavior remain the pre-TG06 path. A separately requested legacy diagnostic
telemetry run remains possible.

`shadow` enables host telemetry, creates and validates trajectory artifacts,
and always preserves the existing control flow. A deterministic shadow
failure is reported as a warning. It does not invoke the checkpoint route.

`enforce` uses the same deterministic evaluation but applies its result. It is
never selected implicitly. Validation, provider, repair, or application
failure halts with owner-review artifacts; enforcement never falls back to an
unguarded or legacy analysis.

## Real integration boundaries

The public v2 flow now uses these host-visible boundaries:

| Boundary | TG06 behavior |
|---|---|
| Before Discovery | Build the Mission Contract from the validated project-local Story Start package and persist its revision history. |
| Discovery invocation/completion | Reuse TG02 events and route metadata already emitted by the host. |
| After validated Discovery | Derive the Ledger, evaluate TG04 at `PROVIDER_COMPLETION_BOUNDARY`, and optionally apply a TG05 checkpoint in enforce mode. |
| Before Triage | Supply the compact evidence-provenance package and, for a validated re-anchor, one transient compact header. |
| Before Planner | Supply the compact evidence-provenance package; Scope v2 remains responsible for implementation classification. |
| Publication | Preserve the existing atomic Scope v2 artifacts and publish additive trajectory sidecars in the same active workspace. |

Mana still cannot observe or intercept provider-internal file reads, tool
calls, reasoning, context expansion, retries, or native agent delegation. The
integration run declares `PROVIDER_INVOCATION_LEVEL` granularity and lists
those unsupported facts. No per-tool-call enforcement is claimed.

Current Story Start v2 has no host-owned iterative evidence-acquisition loop.
Consequently the default public observation has no structured next action and
governs the nearest real boundary after the single Discovery synthesis call.
The optional inputs below exist for a caller that really exposes a structured
boundary; TG06 does not infer one from prose.

## Mission, Ledger, and checkpoint lifecycle

Before Discovery, host code derives the immutable Mission Contract from the
validated `mana.story-start.discovery-package/v1`. It creates one evidence gap
per acceptance criterion, a bounded evidence-scope policy for the existing v2
phases, explicit stop conditions and budgets, and a hash-chained revision
history. Mission correlation is carried by every downstream trajectory
sidecar.

After Discovery, the host recomputes the Ledger from the TG02 event stream and
runs the TG04 deterministic detector. `CONTINUE_ON_TRACK` incurs no checkpoint
call. Only `CHECKPOINT_RECOMMENDED` can build a TG05 bounded request and invoke
the TG01 `trajectory-checkpoint` route.

A checkpoint uses at most one primary call and one structural repair. A
semantic rejection is final. Raw prompts, invalid provider responses, and
provider stderr remain in a temporary directory and are deleted. A validated
accepted response and sanitized validation/run records may be retained.
Provider/model/effort and the truthful unavailable-usage marker come from the
existing TG01/TG05 contracts; no hidden provider fallback is added.

## Applying outcomes

The enforce-mode mapping is closed:

| Accepted result | Host action |
|---|---|
| `ON_TRACK` | Continue without changing the handoff. |
| `REANCHOR_REQUIRED` | Add one transient header to the next Triage invocation. It contains mission identity, objective, active goal/constraint/gap refs, rejected/deferred refs, and exactly one validated action. Full history and the original prompt are absent. |
| `SCOPE_TRIAGE_REQUIRED` | Publish a structured expansion proposal. Without approval, halt for owner review. |
| `STOP_SUFFICIENT_EVIDENCE` | End upstream acquisition and proceed to downstream Scope v2 with the compact package. |
| `STOP_NO_NEW_EVIDENCE` | Proceed only when unresolved gaps remain explicit in the package; otherwise halt for owner review. |
| `STOP_HARD_BUDGET` | Halt with partial evidence and unresolved gaps; do not claim readiness. |
| `NEEDS_OWNER_REVIEW` | Halt with actionable structured artifacts. |

The transient re-anchor header is deleted after the next provider handoff. It
is never a recurring prompt and never contains the full conversation.

## Scope expansion and approval

An expansion remains a sidecar proposal until a project-local, host-validated
`mission-revision-request/v1` is supplied:

```text
MANA_ANALYSIS_TRAJECTORY_SCOPE_APPROVAL=<project-relative-approved-request.json>
```

The approval must target the active Mission ID/revision, name the exact
proposed scope in `acceptedScopeRefs`, provide an approval authority/reference,
and make that exact scope newly allowed. TG06 validates the external proposal
scope together with the TG03 transition, increments the revision, computes a
new hash, and preserves every prior revision. It never auto-approves an
expansion or changes product/implementation scope.

Callers with a real structured next-action boundary may also supply:

```text
MANA_ANALYSIS_TRAJECTORY_OBSERVATION=<project-relative-drift-observation.json>
MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_INPUT=<project-relative-checkpoint-input.json>
```

Both paths must resolve to regular non-symlink files inside the target project.
They do not enable enforcement by themselves.

## Downstream relationship and artifacts

The compact `evidence/analysis-trajectory-evidence-package-v1.json` carries
only mission/ledger correlation, stable evidence and gap refs, open decisions,
unapproved expansions, checkpoint outcome/call count, routing, and explicit
provider-opacity limitations. Triage and Planner are instructed to treat it as
provenance and limitations, never as tasks or implementation scope. Open
decisions remain open, unapproved expansions remain excluded, and mutually
exclusive branches continue to be separate Scope v2 alternatives.

When enabled, inspect these source-of-truth sidecars in the active workspace:

```text
evidence/analysis-trajectory-mission-v1.json
evidence/analysis-trajectory-events-v1.jsonl
evidence/analysis-trajectory-evidence-package-v1.json
validation/analysis-trajectory-mission-history-v1.json
validation/analysis-trajectory-ledger-v1.json
validation/analysis-trajectory-recommendation-v1.json
validation/analysis-trajectory-integration-run-v1.json
validation/analysis-trajectory-checkpoint-*.json        when triggered
validation/analysis-trajectory-scope-expansion-v1.json  when proposed
```

The existing `planning/story-start-scope-v2.md` remains the human-readable
downstream report. Structured trajectory sidecars are authoritative for guard
state. They contain no raw prompt, conversation, source body, credential,
customer data, or provider-internal trace.

## Failure and performance semantics

Shadow failure emits a diagnostic warning and leaves the analysis result
unchanged. Enforcement initialization, deterministic evaluation, checkpoint,
bounded repair, or application failure stops the guarded path and publishes
the existing Scope v2 `needs_owner_review` status plus partial trajectory
artifacts where available.

Passive telemetry, Mission/Ledger derivation, drift evaluation, and package
construction are deterministic and zero-token. Model overhead is recorded
separately as checkpoint call count. A checkpoint is signal-driven, not
periodic; on-track execution pays no model-call tax. Hard Mission budgets are
preserved by TG03–TG05 validation.

## Explicit non-goals

TG06 does not make enforcement default, add Familiar UI, observe opaque tool
calls, build a provider-internal step executor, add an autonomous model loop,
classify product scope, change frozen Scope v2 schemas, run live providers, or
perform the TG07 A/B evaluation and rollout decision.

TG07 subsequently completed that deterministic evaluation without changing
these runtime contracts or the default. Its 40-case offline matrix passes, but
no live or human pilot was executed; the current evidence-based release state
is therefore `SHADOW_PILOT_ONLY`. See
`docs/roadmap/analysis-trajectory-guard/tg07-release-readiness.md`.
