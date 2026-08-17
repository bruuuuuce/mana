# SS07 Story Start Scope v2 release readiness

## Gate result

The deterministic SS07 gate passes against the sanitized SS00 topology. The
baseline for this phase is commit `f3a3f5933bc588e8a9c5f8fada9c5d87ae8cfbe1`.
The gate uses captured provider outputs and fake provider processes; it makes
zero model and network calls.

`tests/story-start-scope-v2-release-gate.sh` covers all 16 required cases,
including positive governed variants for a materially aggravated pre-existing
defect and a human-approved scope expansion. It also runs the captured SS00
topology through the public v2 boundary and proves from structured artifacts
that:

- only `CORE_SCOPE` reaches the constrained base plan;
- existing configuration is reused and the stale branch remains readiness;
- Direct/SSO, delivery strategy, and null semantics remain decision-dependent;
- best-effort and durable delivery are mutually exclusive and never summed;
- approval has zero default developer effort and separate calendar impact;
- independent defects and optional hardening remain excluded;
- all tasks and enablers have direct evidence and provenance; and
- material open decisions keep `finalCommittedEstimate` null, so no inflated
  single one-week estimate is published.

The same gate proves one valid correction succeeds after exactly one call, an
invalid correction terminates as `needs_owner_review` without fallback, legacy
Markdown is preserved without reinterpretation, and approved expansion work
does not rewrite its original `RELATED_DEFECT` history.

## Provider independence and live-smoke disposition

The required suite compares schema-normalized semantics rather than prose.
Captured Discovery, Triage, and Planner outputs exercise the shared
provider-neutral synthesis dispatcher; provider argument contract tests cover
the already-supported Codex, Claude, and OpenCode targets.

| Provider/model | Operation | Calls/tokens | Schema/governor/semantic outcome |
|---|---|---|---|
| `stub/deterministic` | Discovery → Triage → Planner → Governor on SS00 topology | 3 calls, 0 model tokens | All schemas valid; governor passed; topology assertions passed |
| `stub/deterministic` | Invalid Planner correction | 1 correction call, 0 model tokens | Valid correction passed; repeated invalid result failed closed |
| Codex / not configured | Live Story Start v2 smoke | Not run; usage unavailable | No existing opt-in Story Start v2 live harness, explicit model/opt-in absent |
| Claude / not configured | Live Story Start v2 smoke | Not run; usage unavailable | No existing opt-in Story Start v2 live harness, explicit model/credentials/opt-in absent |
| OpenCode / not configured | Live Story Start v2 smoke | Not run; usage unavailable | No existing opt-in Story Start v2 live harness, explicit model/opt-in absent |

This is the SS07-required honest unavailable-live disposition: adding a new
provider integration solely for this phase is forbidden, and unavailable live
credentials do not invalidate deterministic offline correctness. No live call
was attempted by default.

## Performance and budgets

The release gate measures the complete captured fixture on every run. The local
SS07 measurement on 2026-08-17 was:

| Measure | Result |
|---|---:|
| Successful provider calls | 3 |
| Maximum corrective calls | 1 |
| Discovery prompt | 2,144 bytes / 536 estimated tokens |
| Triage prompt | 19,161 bytes / 4,791 estimated tokens |
| Planner prompt | 25,065 bytes / 6,267 estimated tokens |
| Correction prompt | 36,937 bytes / 9,235 estimated tokens |
| Host governor | 76 ms average over 5 fresh processes |
| Captured provider output size | 66,502 bytes |
| Published structured/Markdown bundle | 79,392 bytes |

Token estimates use serialized bytes divided by four, rounded up. They are
planning estimates for the measured context, not tokenizer limits or provider
billing telemetry. Exact provider token usage is recorded only when a live
provider exposes it, which the current provider-neutral synthesis transport
does not guarantee; the byte and output caps below are the hard bounds.

Hard runtime bounds remain:

| Phase | Compact input bound | Provider output bound | Timeout |
|---|---:|---:|---:|
| Discovery | 262,144 bytes | 262,144 bytes | 120 s default, 300 s maximum |
| Scope Triage | 524,288 aggregate bytes | 262,144 bytes | 120 s default, 300 s maximum |
| Planner | 786,432 aggregate bytes | 524,288 bytes | 120 s default, 300 s maximum |
| Governor correction | 524,288-byte candidate; measured composite prompt capped by the gate at 1 MiB | 524,288 bytes | 120 s default, 300 s maximum |

Scope Triage receives only normalized story plus compact Discovery. Planner
receives only normalized story, compact planning context, and Triage. Neither
receives the repository. The success path has three calls, correction has one
slot, supervised provider processes have fixed time/output limits, and the
Story Start shell orchestrator has no retry loop.

## Release-note draft

### Story Start Scope v2

- Added an opt-in, provider-neutral Story Start Scope v2 pipeline with
  schema-bound Discovery, Scope Triage, Implementation Planner, deterministic
  host governance, and deterministic Markdown rendering.
- Separated core work, mandatory enablers, decision-dependent alternatives,
  readiness, related defects, optional improvements, and human-approved scope
  expansion so repository discovery cannot silently inflate story scope.
- Added bounded one-shot correction, fail-closed owner review, versioned
  publication status, legacy artifact compatibility, and a 16-case zero-token
  release gate.

This draft is also represented under `CHANGELOG.md` → `Unreleased`; it has not
been published.

## Migration, compatibility, and schema notes

- V1 remains the default. Select v2 explicitly with
  `MANA_STORY_START_SCOPE_VERSION=v2` and a project-local
  `MANA_STORY_START_CONTEXT` package.
- V2 writes additive `story-start-*-v2` artifacts and never overwrites legacy
  `planning/implementation-plan.md`.
- Legacy Markdown is readable as-is but is not safe to reinterpret as v2.
  Unknown v2 schema versions and enum values fail closed.
- JSON artifacts retain `artifactVersion: 2` and their existing
  `mana.story-start.*/v2` schema identifiers. SS07 adds no field, category, enum,
  identity, or arithmetic change, so the contract schema version remains v2.
- The governor now verifies that approved expansion decisions use linked human
  evidence and that resulting task IDs preserve the expansion history.
- Mana Familiar is unchanged and is not required for the Markdown interface.

## Known limitations

- The caller must prepare the compact discovery package; v2 does not collect an
  unbounded repository snapshot itself.
- Offline captured-output tests prove host contracts and semantics, not the
  quality of every future model response. There is no existing opt-in live
  Story Start v2 harness in this repository.
- Provider-neutral transport does not guarantee exact token telemetry, so hard
  byte/output/time bounds are authoritative and token figures remain planning
  estimates when live usage is unavailable.
- Open material decisions deliberately prevent a final committed estimate and
  require a human planning decision.
- V2 remains opt-in while compatibility and human acceptance are reviewed.

## Recommended version impact and release state

The repository does not state a separate product SemVer policy. Its changelog
uses minor releases for additive public capabilities (`0.4.0`, `0.5.0`), so the
evidence-based recommendation is **0.6.0** for public Story Start Scope v2.
This is a recommendation for the release owner, not an automatic version
decision. The schema contract itself remains v2 under its documented versioning
policy.

No version was changed. No tag, push, pull request, publication, or release was
created by SS07. Human checklist completion, release-owner approval, and hosted
CI remain external release actions.
