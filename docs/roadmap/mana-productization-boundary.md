# Mana Productization Boundary

## Status

Active product boundary for the Mana read-model productization track. This is a
scope and compatibility record, not a new runtime contract.

## Local Baseline Record

This record captures the M00 audit that started on 2026-08-11. It is historical
evidence rather than a claim about the checkout after later commits. Re-run the
commands below before each phase that depends on repository state.

| Check | M00 observation | Re-check command |
|---|---|---|
| Repository | `https://github.com/bruuuuuce/mana.git` | `git remote -v` |
| Starting branch and commit | `develop` at `140867a` (`v0.4.1`) | `git status --short --branch`; `git rev-parse HEAD` |
| Starting relationship to public branches | `develop`, `main`, `origin/develop`, and `origin/main` resolved to `140867a` | `git log --oneline --decorate -1`; `git rev-list --left-right --count origin/develop...HEAD` |
| Starting dirty state | clean | `git status --short` |
| Divergence from the audited public snapshot | none: the expected `v0.4.1` release commit was the local starting HEAD | compare with `AUDITED-BASELINE-2026-08-11.md` and local Git state |
| Track branch | `feature/mana-inspect-v1`, created from that clean baseline for this roadmap | `git status --short --branch` |

The authoritative state is always the local checkout. The audited public
snapshot is only a reference; later local commits, branch divergence, and dirty
work must be recorded by the phase that observes them.

## Product Boundary

Mana owns artifact meaning, governance, discovery, stable read contracts, and
deterministic query behavior. It is the only semantic producer for Mana-owned
artifacts.

Mana Familiar is a read-only, human-facing client of those producer-owned
contracts. Its existing Learning Journey experience is the Knowledge module of
the broader product. A future IntelliJ plugin is another client of the same
read model. Neither client may re-derive the meaning of `.mana/` artifacts with
an independent parser or write producer records.

Later phases must extend existing producer mechanisms rather than create a
parallel framework:

- `scripts/mana-workspace.sh` and [`docs/workflow/mana-workspace.md`](../workflow/mana-workspace.md)
  define project-local artifact routing and workspace ownership.
- `scripts/run-evidence-index.sh` provides the existing deterministic evidence
  inventory pattern.
- `scripts/mana-runtime.sh` provides repository-local, read-only runtime-event
  inspection.
- `scripts/mana-explore.sh` provides bounded read-only repository retrieval;
  it is not a public artifact read model.
- [`docs/standards/mana-familiar-v0.md`](../standards/mana-familiar-v0.md) and
  `scripts/mana-journey.sh ... materialize` establish the existing
  producer-owned `mana.learning.graph/v1` compatibility precedent.

## Feature Freeze

No unrelated macro-feature may be added while this track is active. Allowed
exceptions are limited to:

1. the versioned, deterministic read model needed by Mana Familiar and future
   clients;
2. a bounded bug-hunting workflow only after confirming that it has a distinct
   job from Jessica's branch-scoped production pre-mortem;
3. minimal, evidence-backed pilot support; and
4. hardening, documentation, and release-readiness work required by this
   roadmap.

Every exception must preserve explicit human approval gates, repository-local
determinism where applicable, and existing public-contract compatibility.

## Client and Compatibility Rules

- Mana defines and versions artifact schemas, query semantics, IDs, validation,
  and compatibility behavior.
- Clients consume declared contracts only. Client presentation, navigation, and
  local UI preferences remain client-owned.
- A producer contract change requires an explicit compatibility review before a
  consumer relies on it; supported contracts must not be silently changed.
- Existing Learning Journey compatibility remains governed by
  `mana.learning.graph/v1` and the Familiar v0 contract until a later phase
  deliberately versions or supersedes it.

## Deferred Work

- No generic `mana inspect`, artifact catalog, project snapshot, schema, or
  wrapper command is introduced by M00.
- No Mana Familiar UI expansion or Flutter changes occur in this repository.
- No IntelliJ plugin, client-specific semantic parser, or client-specific
  transport is implemented here.
- No bug-hunter implementation occurs until its overlap audit is complete.
- No unrelated cleanup, command renaming, release/version change, autonomous
  execution path, or new agent/skill/profile/runtime framework is in scope.

## Phase Order and Gates

| Order | Phase | Required compatibility gate before advancing |
|---|---|---|
| 0 | M00 — rebaseline and feature freeze | This boundary is current; local baseline and overlap inventory are recorded. |
| 1 | M01 — artifact taxonomy and read-model ADR | Semantic ownership and a versioning strategy are agreed before implementation. |
| 2 | M02 — inspect project and catalog v1 | Deterministic producer output and its contract tests are ready for consumers. |
| 3 | M03 — inspect artifact source and relations v1 | Artifact-source and relation behavior remains compatible with the approved v1 model. |
| 4 | M04 — contract bundle and consumer handoff | C00 validates producer/consumer contract compatibility. |
| 5 | M05 — bounded bug hunter | Distinct-job and non-duplication audit is satisfied before implementation. |
| 6 | M06 — pilot utility evidence | Pilot evidence supports a go/no-go decision; no marketing claim exceeds evidence. |
| 7 | M07 — hardening, documentation, and release readiness | Release checks and documented compatibility status are complete. |
| Cross-repository | C01–C04 and launch phases | Run only after their named predecessor contracts and C00 gate are satisfied. |

M01 is ready to define the artifact taxonomy and read-model ADR. It must retain
this ownership boundary and use the mechanisms listed above rather than infer a
second artifact semantics layer.
