# Mana Learning Scout v0

Phase 3 adds a deliberately narrow, host-owned static scout for one path only:
`POST` Spring MVC endpoints through controller, service, repository/external
work, and the primary Spring transaction commit.

## Request contract

`mana scout request` writes a host-generated JSON/YAML request conforming to
`mana-learning-scout-v0.schema.json`. A request has an explicit HTTP start,
the exact `primary_transaction_committed` runtime termination, source root and
four mandatory integer budgets. v0 accepts only `java-spring-http-v0` and
`POST`; unsupported source shapes fail rather than widening the scan.

```bash
./mana scout request --title 'Trace payment' --path /payments --out request.json
./mana scout run --request request.json
```

The defaults are `100` nodes, `200` edges, depth `30`, and branching `10`.
The scout validates every limit while appending records. A limit produces a
non-zero result and a derived `scout-report.json` describing the stop reason;
it never silently follows more code.

## Discovery and evidence

The scanner recognizes a direct `@PostMapping("/path")`, anchors its handler,
then follows one conventional method invocation into a service and one into a
repository/DAO implementation. Every discovered source node has an immutable
source anchor. The commit is a `runtime_effect` node, backed by a
`runtime_semantic` evidence record when the selected service method or class is
annotated `@Transactional`.

Nodes and edges have an explicit `disposition`: `primary` is the requested
route; `deferred` is discovered but deliberately not traversed. Methods marked
`@TransactionalEventListener(...AFTER_COMMIT...)` are attached to the commit as
deferred branches. They do not become part of the execution traversal.

The Journey remains authoritative append-only state. `derived/scout-report.json`
is merely a deterministic diagnostic. Materialization is delegated to the
Journey model and therefore sorts all persisted records by immutable ID.

## Deliberate boundaries

This is not a general Java parser, call-graph engine or framework simulator.
Cycle detection, visited/stack safety, SCC derivation and loop-aware budgets
are provided after scouting by `mana scout harden <journey-id>` (Phase 4); it
operates solely on the bounded persisted Journey rather than widening source
discovery. Polymorphic dispatch, arbitrary mappings, asynchronous semantics
other than the explicit AFTER_COMMIT marker and broader repository exploration
are not guessed.
