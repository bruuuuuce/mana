# Mana Learning Scout cycle hardening v0

Phase 4 hardens an already bounded Journey against cyclic and event-driven
topologies. It never runs an unbounded source scan and never creates synthetic
iteration nodes. The existing logical node is revisited; the revisit is
represented by a derived `LOOP_BACK` edge.

```bash
./mana scout harden jrn_…
```

The pass first materializes and validates the Journey, then walks primary and
deferred non-`LOOP_BACK` edges in sorted immutable-ID order. It keeps both a
visited set and an active traversal stack. An edge to an active-stack node is a
back-edge; an edge to an already completed node is not automatically a loop.
This prevents repeated expansion while retaining the actual graph topology.

## Components, joins and classification

Tarjan SCC detection derives one `CycleRegion` for every multi-node SCC and
for a self-loop. Components and their members are normalized by immutable ID;
the result is deterministic for the same persisted graph. A node with multiple
incoming edges but no SCC is reported as a `join` in derived `cycle-report.json`
and is never persisted as a cycle.

Each CycleRegion references only existing nodes and internally connected
`LOOP_BACK` edges. Its classification is a deliberately transparent v0 label
heuristic, in this precedence order: `retry`, `polling`, `event_loop`,
`state_cycle`, `recursive` (a self-loop), then `unknown`. Labels are only a
classification hint, not evidence of runtime behaviour; later expansion may
attach stronger evidence without changing node identity.

## Bounds and idempotence

`harden` accepts `--max-cycle-regions`, `--max-cycle-members`, and
`--max-back-edges` (defaults 20, 100, 100). The limits count unique graph
members and derived back-edges, never traversal iterations. A limit writes a
non-authoritative `derived/cycle-report.json`, exits non-zero and appends no
cycle record. Re-running a successful hardening pass detects the existing
component and makes no additional records.

The report conforms to `mana-learning-scout-cycles-v0.schema.json` and is
diagnostic only; Journey records remain authoritative.
