# ADR: Mana Inspect Read Model v1

## Status

Accepted for the M02 implementation scope. This decision defines the architecture
only; it adds no CLI, schema file, cache, or runtime behavior.

## Context

Mana has multiple established producers below a selected project's `.mana/`
tree. Their physical layout serves persistence, evidence, runtime audit, and
bootstrap concerns; it is not a client-facing information architecture.
[Mana Artifact Taxonomy](../standards/mana-artifact-taxonomy.md) records the
current producers and their compatibility classifications.

Mana Familiar and a future IntelliJ client need one producer-owned way to
discover artifacts and navigate their explicit source relations. Familiar
already consumes the producer-owned Journey graph projection
`mana.learning.graph/v1`; it must not become a second parser for every
`.mana/` layout.

## Decision

Mana will own a versioned inspect read model. Version 1 will scan a selected
project root on demand and deterministically build a logical catalog from the
known taxonomy plus first-class `unknown` artifacts.

The v1 read model has these invariants:

- **Read-only and local:** no model calls, writes, background indexing,
  registration retrofit, network work, or mutation of source/workspace files.
- **Logical, not a file browser:** result entities represent artifact families,
  identities, status, explicit relations, and safe metadata. A path is a source
  reference, not the product's primary hierarchy.
- **Project-relative paths only:** output never contains absolute paths,
  temporary staging paths, home directories, or paths outside the selected
  project root. Invalid, traversing, symlinked, unreadable, or escaping paths
  fail closed or are reported as safe diagnostics.
- **Stable and revision identity:** every catalog item has a stable
  `artifact_id` and a separate content/revision identity. A valid producer
  intrinsic ID takes precedence: for example `journey:jrn_…`,
  `verification:<runId>`, `repair-attempt:<attemptId>`, or
  `runtime:<executionId>`. An artifact without an intrinsic ID uses a
  namespaced, project-relative path identity such as
  `file:service-context:.mana/global/architecture.md`. Its
  `revision_id` is a SHA-256 content digest or a producer-declared revision
  identity; changes to content must not change the stable `artifact_id`.
- **Explicit uncertainty:** unknown, legacy, malformed, unavailable, and
  unsupported artifacts are catalog records with a classification and safe
  diagnostic. V1 does not omit them merely because it cannot interpret them.
- **Validated semantics only:** relations come only from containment, declared
  structured references, producer schemas, and existing source-anchor
  contracts. V1 does not infer relations from arbitrary prose, filenames, or
  model output.
- **Public contracts are versioned JSON:** public responses identify their
  schema/version and validate at the producer boundary. M02 may define concrete
  `mana.inspect.* /v1` schemas but must not silently alter existing Journey,
  evidence-index, or runtime contracts.
- **Caching is future-only:** any later index/cache is derived, versioned,
  rebuildable, excluded from canonical semantics, and invalidated by scan
  inputs. V1 is on-demand scanning.

Mana therefore remains the sole semantic owner. Familiar, IntelliJ, and any
other client consume declared results and own only their presentation,
navigation, and local preferences.

## Minimum Queries

M02 must implement a vertical slice of these distinct read-only queries:

| Query | Purpose | Minimum v1 response | Boundaries |
|---|---|---|---|
| Project/capabilities | Identify selected project and supported inspect capabilities. | Contract version, project-relative `.mana` availability, known family counts/capabilities, diagnostics, and no-write/no-model declaration. | No absolute root, secret config, or claim that missing evidence is safe. |
| Artifact catalog | List logical artifacts with deterministic ordering and filtering by family/class/status where known. | `artifact_id`, family, kind, class, project-relative path, `revision_id`, known status/timestamp, and unknown diagnostics. | Metadata-first; no raw sensitive content by default; no file-browser mirroring. |
| Artifact detail | Retrieve one cataloged artifact by `artifact_id`. | Catalog metadata, declared structured fields appropriate to its family, content/reference availability, and explicit relations. | Do not expose secret-bearing bootstrap files, raw unrestricted logs, or unvalidated prose as structured facts. |
| Source relations | Retrieve only explicit source anchors and validated relations for an artifact. | Relation type, source/target IDs, source-anchor revision and project-relative path/range when the producer contract provides them. | No heuristic graph edges, full repository scan, or relation invented from Markdown/source text. |

A Journey detail may continue to refer to its existing
`mana.learning.graph/v1` materialization rather than duplicate graph parsing.
The inspect contract is additive; it is not a replacement Journey consumer API.

## Reuse of Existing Commands

| Existing surface | Reuse decision | Compatibility rule |
|---|---|---|
| `scripts/run-evidence-index.sh` | Reuse its workspace resolution and evidence-family knowledge as implementation evidence, not its Markdown output as the inspect API. | Preserve `evidence/index.md` generation and format. Inspect publishes separately versioned JSON and does not require regenerating the index. |
| `scripts/mana-runtime.sh` | Reuse validated execution-ID handling and runtime event/session layout. | Preserve current `sessions`, `events`, `show`, and dry-run prune behavior and output. Runtime entries remain operational audit, distinct from delivery evidence. |
| `scripts/mana-workspace.sh` | Reuse workspace path/manifest resolution and canonical-vs-feature/session semantics. | Do not require a new manifest or rewrite old workspaces. Missing/legacy workspace content is cataloged as unknown. |
| `scripts/mana-journey.sh materialize` | Reuse producer validation and deterministic graph materialization for Journey semantics. | Do not parse Journey records independently or change `mana.learning.graph/v1`. |
| Existing verification, repair, eval, and governance schemas | Reuse their IDs, schema versions, digests, and explicit references where validated. | No generic manifest registration or schema migration is required for v1. |

## Decision Table

| Area | Decision | Evidence / rationale | Consequence |
|---|---|---|---|
| Scan versus cache | On-demand deterministic scan for v1 | Existing workspace data has mixed canonical, derived, and ephemeral lifecycles. | Fresh local view; large-workspace performance is a measured future concern. |
| Catalog shape | Logical artifact catalog | Physical directories are producer storage, not a product UI. | Clients navigate family/identity/relation metadata rather than mirror paths. |
| Identity without producer IDs | Namespaced project-relative path stable ID plus separate digest revision | Many established Markdown artifacts have no embedded ID. | Rename changes identity; content change does not. This is transparent, not an invented durable semantic ID. |
| Unknown files | First-class `unknown` records | Old workspaces and future producer versions must remain visible. | No migration/rewrite; clients can show uncertainty safely. |
| Relations | Explicit, validated only | Prose and filenames are unsafe semantic sources. | Some useful-looking links remain unavailable until a producer declares them. |
| Markdown and logs | Content remains opaque by default | They may hold sensitive or unstructured claims. | Detail can expose a controlled reference/preview policy later; M02 does not promise full text. |
| Bootstrap and User Context | Catalog as restricted/ephemeral metadata or exclude secret-bearing detail | `.mana/jira-mcp.env` and personal material are not public product data. | Clients never receive secrets or implicit authority from those files. |
| External User Learning | Do not scan external host state | It is intentionally outside the selected project boundary. | Only safe project-local mirror metadata can appear. |
| Existing convenience outputs | Keep contracts unchanged | Evidence index and runtime commands already have documented consumers. | Inspect is additive, never a silent replacement. |

## Consequences

Positive consequences:

- Clients share Mana's artifact semantics and compatibility policy.
- Existing workspaces, including incomplete and legacy ones, remain readable.
- Stable logical identity enables UI selection and relation lookup without
  coupling clients to storage layout.
- Source navigation is bounded to declared anchors and project-relative paths.

Costs and limits:

- The first implementation must classify mixed-format data conservatively.
- Path-based IDs are only stable while their path remains stable when a producer
  has no intrinsic ID.
- V1 has no cache and may need performance measurements before broad rollout.
- Unknown artifacts may be visible with limited detail; this is intentional.

## Explicit Non-Goals

This ADR does not authorize a CLI implementation, generic producer manifest,
workspace migration, old-workspace rewrite, Familiar UI change, IntelliJ
plugin, heuristic prose parser, model call, write path, or hidden cache.

## M02 Readiness Gate

M02 may proceed when its implementation proves all of the following:

1. responses are deterministic JSON with explicit v1 versioning;
2. every emitted path is project-relative and contained safely beneath the
   selected project root;
3. known producer entries preserve their existing contracts and unknown files
   remain visible;
4. stable `artifact_id` and distinct `revision_id` are covered by tests;
5. the four minimum queries are exercised against representative existing and
   legacy/unknown workspace fixtures; and
6. no inspect command writes, invokes a model, or changes existing
   `evidence-index`, runtime, or Journey outputs.
