# Analysis Trajectory Guard — TG07 release readiness

## Gate and rollout result

The TG07 deterministic gate passes: all 40 cases in the eight-topology by
five-variant matrix match their expected result. The evaluation is offline,
uses captured/synthetic provider responses, and made zero provider and network
calls. The machine-readable evidence is
`tg07-deterministic-evaluation.json` in this directory.

**No live pilot and no human acceptance review was executed during TG07.**
Consequently, the evidence-based rollout recommendation is
`SHADOW_PILOT_ONLY`. Global or default-on enforcement is not authorized.

The gate proves:

- mandatory evidence recall is `1.0` in off, shadow, and every enforce
  response variant;
- on-track, legitimate dependency, mandatory cross-cutting, and opaque
  provider fixtures use zero checkpoint calls;
- unrelated-bug and architecture-rabbit-hole continuations are deferred at a
  real next-action boundary in enforce mode;
- repeated no-evidence work gets one re-anchor within the configured policy;
- a structural failure followed by a failed repair halts after two checkpoint
  calls and never resumes unguarded;
- sufficient evidence proceeds to downstream synthesis without optional extra
  research; and
- captured Scope v2 output still contains a base plan, three required
  enablers, seven conditional branches in three mutually exclusive groups,
  and three related findings, with no committed estimate while decisions are
  open.

## Deterministic matrix and metrics

Every TG00 topology runs through `OFF`, `SHADOW`, `ENFORCE_VALID`,
`ENFORCE_INVALID_VALID_REPAIR`, and `ENFORCE_FAILED_REPAIR`. Invalid-response
fixtures are consumed only when deterministic drift policy actually permits a
checkpoint; an on-track case therefore stays at zero calls in all three
enforce variants.

The report records expected/actual outcomes, checkpoint and provider-call
counts, evidence and mandatory-evidence refs, avoided work, unresolved gaps,
expansion proposals, Scope v2 disposition, serialized sizes/token proxies,
and failure behavior for every case.

| Variant | Provider calls/run | Checkpoints/run | Evidence/provider iteration | Mandatory recall | False re-anchor | False stop |
|---|---:|---:|---:|---:|---:|---:|
| Off | 2.250 | 0 | 0.667 | 1.000 | 0 | 0 |
| Shadow | 2.250 | 0 | 0.667 | 1.000 | 0 | 0 |
| Enforce, valid | 1.750 | 0.125 | 0.923 | 1.000 | 0 | 0 |
| Enforce, invalid then valid repair | 1.875 | 0.250 | 0.923 | 1.000 | 0 | 0 |
| Enforce, failed repair | 1.875 | 0.250 | 0.923 | 1.000 | 0 | 0 |

These are fixture averages, not production forecasts. Provider calls in the
matrix are trace-level comparison counts; the evaluation program itself made
zero provider calls. Exact tokens, wall time, and human rejected/deferred
findings are explicitly unavailable. Token proxies are serialized byte
estimates, not provider billing data.

## Model and cost comparison

The checkpoint route remains Terra high. Captured Terra-high checkpoint
fixtures show no false `ON_TRACK`, semantic invalidity, missed mandatory
constraint, or inability to select and justify the permitted next action.
Therefore Sol high was not executed merely to compare prose quality.

| Route | Evidence | Calls | Checkpoint token proxy | Exact usage | Decision |
|---|---|---:|---:|---|---|
| Terra high, valid | Captured valid re-anchor | 1 | 3,221 | Unavailable | Keep as pilot default |
| Terra high, structural repair succeeds | Captured invalid then valid | 2 | 6,291 | Unavailable | Bounded repair works |
| Terra high, structural repair fails | Two captured invalid results | 2 | 6,291 | Unavailable | Fail closed |
| Sol high | Not run | 0 | Not measured | Unavailable | No material escalation trigger |

Escalate a future comparable checkpoint pilot to Sol high only after a
measured false `ON_TRACK`, unjustified valid-action selection, repeated
semantic invalidity, or missed mandatory cross-cutting constraint. A more
polished explanation is not sufficient evidence.

## Provisional pilot thresholds

These are fixture-derived pilot proposals, not universal defaults:

| Signal | Pilot value | Evidence and safety rationale |
|---|---:|---|
| Repeated target visits | 3 | Two useful visits remain on track; the third equivalent visit without evidence triggers one bounded re-anchor. |
| Consecutive no-new-evidence completions | 3 | Avoids stopping after only two empty iterations while bounding sustained empty work. |
| Unapproved scope expansion | 1 | The first proposal changes Mission scope and must be explicit and owner-approved. |
| Unsupported open-decision assumption | 1 | One assumption can incorrectly commit mutually exclusive architecture work. |
| Soft-budget warning | 80% | Retains the TG04 measured warning point until live baseline data supports adjustment. |

Do not tune these values from prose impressions or change fixtures to improve
the result. Confirm false re-anchor/stop rates, evidence recall, call overhead,
and reviewer usefulness on live pilot pairs before considering enforce rollout.

## Known limitations and unresolved risks

- Provider-internal file reads, tools, delegation, context expansion, and
  reasoning remain opaque. The guard evaluates provider invocation/completion
  and explicit next-action/final-synthesis boundaries only.
- Synthetic/captured responses prove host policy and bounded failure behavior,
  not future provider quality or non-determinism.
- No live baseline exists for exact token usage, wall time, or comparative
  human usefulness.
- Human reviewers have not yet scored false stops, missed dependencies,
  actionability, focus, or trust.
- Fixture-derived thresholds may need project-specific calibration. They must
  not be presented as universal product policy.
- Scope v2 remains a separate downstream classifier; trajectory findings do
  not become implementation tasks by being present in a sidecar.

## Migration and rollback

1. Leave the feature off by default. Existing v1/v2 behavior remains the
   compatibility baseline when `MANA_ANALYSIS_TRAJECTORY_MODE` is unset or
   `off`.
2. For the first human pilot, set the mode to `shadow`; retain current
   provider/stage routes and compare the same approved input and revision.
3. Consider an `enforce` pilot only after shadow review, with an owner present
   for scope expansion and owner-review stops. This is per-run opt-in, not a
   global setting.
4. Roll back immediately by unsetting the mode or setting it to `off`.
   Trajectory contracts and workspace sidecars are additive, so rollback does
   not require modifying frozen Story Start Scope v2 schemas or reinterpreting
   existing Scope v2 artifacts.
5. Preserve prior pilot artifacts for audit according to repository retention
   policy. Do not feed them back as automatic approval evidence.

## Release-note draft

### Analysis Trajectory Guard (shadow pilot)

- Added an opt-in host-owned Mission Contract, passive trajectory telemetry,
  deterministic drift signals, a bounded re-anchor checkpoint, and a compact
  evidence handoff to Story Start Scope v2.
- Added a 40-case zero-token TG07 evaluation across off, shadow, valid enforce,
  repaired enforce, and failed-repair enforce behavior.
- Added an explicitly enabled live A/B/C pilot harness, human acceptance
  checklist, provisional threshold guidance, and fail-closed rollback policy.
- Kept enforcement disabled by default; current release evidence authorizes at
  most a supervised shadow pilot.

This is a draft for the release owner. TG07 changed no version, tag, release,
global default, or external publication.
