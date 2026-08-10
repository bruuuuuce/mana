# Mana Learning Expansion v0

Phase 5 adds one bounded, independent enrichment: an evidence-backed
explanation for an existing Journey node.

```bash
./mana expand request --journey jrn_… --node jn_… --out explanation-request.json
./mana expand run --request explanation-request.json
```

`request` validates that the selected stable node belongs to the Journey and
appends an `enrichment` lifecycle record with status `requested`. `run` builds
context only from that node's existing source anchors, evidence already linked
to those anchors, and direct incident graph edges. It then appends source-range
evidence where needed, one `explanation` record and a terminal `completed`
enrichment record. No existing Journey record is rewritten.

The request requires three positive budgets: context lines (default 120),
evidence items (8), and direct related nodes/edges (8). The resulting bounded
context is derived-only under `derived/expansions/`; it is useful for audit but
is not authoritative Journey state. Explanation records retain addressable
evidence IDs, a lifecycle status, a body and an epistemic status.

Expansion does not follow calls, scan more source files, or create primary
nodes/edges. Therefore it cannot enlarge the repository region. If a later
expansion mechanism identifies a branch worth following, it must append an
existing or newly anchored node as `discovered` with `deferred` disposition and
require a separately scoped traversal before becoming primary.

The v0 explanatory body is deliberately conservative and host-generated from
the bounded inventory. It says only what the selected anchors and direct graph
context support. Rich model-authored prose is a later enrichment consumer of
the same request/context contract, never an authority for graph identity or
references.
