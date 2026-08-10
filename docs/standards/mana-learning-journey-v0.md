# Mana Learning Journey Model v0

This is the authoritative Phase 1 persistence contract. A Journey is an
append-oriented, evidence-backed graph. It is deliberately independent of the
existing governed learning-candidate workflow at `.mana/learning/candidates/`.

## Layout

```text
.mana/learning/journeys/<journey-id>/
  journey.yaml                 # immutable Journey metadata
  records/<record-id>-<type>.yaml # one immutable addition per file
  assets/                      # reserved, derived assets only
  derived/                     # non-authoritative graph caches only
```

For v0, files have a `.yaml` extension but use JSON syntax. JSON is valid YAML,
keeps the runtime dependency-free, and is an implementation detail; consumers
must treat them as the schemas in `mana-learning-journey-v0.schema.json`.

`scripts/mana-journey.sh` owns ID allocation. IDs use a type prefix plus 24
host-generated random hexadecimal characters: `jrn_`, `jn_`, `je_`, `anc_`,
`ev_`, `exp_`, `enr_`, `hyp_`, `occ_`, `trv_`, `cyc_`, `git_`, `tle_`, and
`hya_`, and `dia_`. Callers never provide IDs.
Neither path, symbol, range, nor parent graph position participates in a node
ID. A source move therefore adds an Anchor and leaves the Node unchanged.

## Contracts and validation

The JSON Schema bundle defines Journey, JourneyNode, JourneyEdge, SourceAnchor,
Evidence, Explanation, Enrichment, Hypothesis, ConceptOccurrence, Traversal,
and CycleRegion records. Every document declares its v0 `schema` string. The CLI
performs the operational subset of that schema plus cross-record validation:

- all referenced node, anchor, edge, and evidence IDs must exist and have the
  expected record type;
- node state is only `discovered` or `expanded`;
- edge, evidence, relevance, epistemic, and cycle values are closed enums;
- malformed metadata, records, or references make materialization fail.

`materialize` validates first, then sorts every record type by immutable ID and
emits `mana.learning.graph/v1`. No directory order or record write time affects
the graph. The materialized graph is a view, never the source of truth.

`concept_id` must exist in the canonical registry introduced in Phase 2; no
classifier output or free-form text is allowed to create a record reference.

## Initial traversal contract

A Traversal names a view over existing node IDs with an existing entry node.
It does not duplicate nodes. CycleRegion identifies existing nodes and existing
back-edge records using one of `retry`, `polling`, `event_loop`, `state_cycle`,
`recursive`, or `unknown`. Phase 4 derives these regions using deterministic
SCC detection; every referenced back edge must be a `LOOP_BACK` whose endpoints
are both in the region. See `mana-learning-scout-cycles-v0.md`.

## Expansion lifecycle

Phase 5 adds append-only `enrichment` records for independently requested and
completed explanation work. An Explanation can hold a bounded body,
addressable evidence IDs and an epistemic status; it never rewrites its subject
node. The request/context contract is specified in
`mana-learning-expansion-v0.md`.

## Scope deliberately deferred

Git archaeology is an independent enrichment: it adds a `git_enrichment`
record, historical Anchors, `git_commit` Evidence and TimelineEvent records.
Timeline events refer to the same logical node as the current source anchor;
they never replace its ID. A failed Git lookup is persisted as a failed
enrichment and does not invalidate the Journey. A HypothesisAssessment can
state that selected Git evidence strengthens, weakens, or is inconclusive for
an existing hypothesis without rewriting it.

The standalone desktop consumer boundary is specified separately in
`mana-learning-explorer-v0.md`.
