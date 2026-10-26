# Executable Dependency Contract v1 — bounded static projection

Status: implemented **partial** contract, MODEL-EXT-01. This is a catalog of static
executable dependencies, not an executable Java IR. It cannot admit a new T01 call.
The remaining admission proposal below is not implemented or authorized by this
schema. No T01 v2 is introduced.

## Compatibility gate

The optional T01 property `executableDependencyExtension` uses its own discriminator
`mana.executable-dependency-contract/v1`. Absence preserves the existing builder,
validator and all previous conclusions. Presence requires the fields below; no
previously mandatory evidence becomes optional. The existing
`mana.java-execution-dependencies/v1` producer contract is unchanged.

T01 has a Python semantic validator, not a standalone transaction-model JSON Schema.
S01 has an exact outer key set but embeds T01 intact and calls its validator.
T01's previous validator ignores additional top-level keys: ignoring this catalog
is safe because it contributes **no** execution, continuation, resource placement
or transaction certainty. Updated validators check its consistency. A legacy
consumer cannot verify the new catalog and must not advertise verification of it.
This compatibility argument does not extend to adding executable events, branch
states or new meanings of `STRAIGHT_LINE`/`NOT_ASSERTED` under the same identifier.

| Surface | Old input/new consumer | New input/old consumer | Migration |
|---|---|---|---|
| Parse facts, member/EXEC witnesses | unchanged | unchanged | none; no parser/producer change |
| T01 without extension | same transitions and conclusions | same | none |
| T01 with catalog | checks projection and source links | ignores catalog, same execution arrays | opt in to pinned verification to use catalog |
| S01 | validates embedded T01; copies catalog intact | preserves opaque T01 property | no observation or placement from catalog |
| S02 / VIS-01 | same causal data | same causal data | no semantic migration; not newly qualified here |
| Future executable admission | unsupported here | compatibility not established | separate decision before implementation |

## Normative shape and meaning

The shape schema is `executable-dependency-contract-v1.schema.json`; the independent
semantic checks in `transactions/executable_contract.py` are also mandatory.
All extension fields are required, with no extra projection fields:

| Field | Contract |
|---|---|
| `schema` | exact extension discriminator |
| `scope` | `SELECTED_STATIC_DEPENDENCIES_ONLY` |
| `t01Entry` | unchanged T01 declaration selector |
| `entryDeclaration` | attributed canonical owner#method(parameter types), linked by the same entry evidence; no rewriting of root signatures |
| `completeness` | `INCOMPLETE`, including apparently simple selected closures |
| `records` | bounded, one record for every EXEC site, including unresolved/generated sites |
| `limits` | selected closure, unproved evaluation/reachability and interception limits |
| `witness` | entire symbol/position/hash EXEC witness; no source bodies or argument values |

A record retains caller and target canonical signatures independently of source
availability. `targetDeclaration` is nullable: a compiler-selected external method
can have no source span. `declarationAvailability` is SOURCE/UNAVAILABLE and does not
mean the binary declaration does not exist. `bodyAvailable` is an independent fact.
Binding is VERIFIED/UNRESOLVED. `relation: STATIC_BINDING` means a source call relation
is representable against the compiler-selected declaration; it does not assert a
runtime implementation. STATIC, DIRECT, CONSTRUCTOR, VIRTUAL and UNKNOWN dispatch,
and DECLARATION_EXACT/UNKNOWN certainty, are copied without refinement.

`callSite` and `targetDeclaration` use the existing file/hash/line/UTF-16-start/end
shape. Non-null sites must lie within their recovered caller. Source-site IDs are
SHA-256 of canonical JSON `[callerIdentity, siteEvidence]`, sorted object keys,
compact separators, UTF-8, Python's default ASCII escaping. Missing implicit sites
use `[callerIdentity, null, witnessOrdinal]` and `idKind: IMPLICIT_OCCURRENCE`; this
ordinal is not an execution order. No source position is invented. Duplicate source
sites or method identities are rejected. A recovered target's body/span must agree
with its site record. All witness source hashes must match the independently
provided canonical source facts/T01 evidence.

Five formally separate propositions:

1. A method declaration can be available as source (with or without a body).
2. A VERIFIED binding proves compiler selection in the pinned environment.
3. A STATIC_BINDING relation can be represented with caller/site/target provenance.
4. Reachability and call admission remain `NOT_ASSERTED` for **every** record.
5. Runtime execution remains `NOT_OBSERVED` for **every** record. `OBSERVED` is invalid.

`dependencyCompleteness` is always INCOMPLETE, `transactionInterception` and
`admission` are NOT_ASSERTED. Existing site limits are retained and the three global
limits added. Requested root selection omits other calls by construction: even a
COMPLETE recovery status is not execution completeness. Nothing here permits
absence-of-cycle/deadlock conclusions. Existing cycle markers are preserved without
introducing a second graph traversal/resolution engine.

## APIs, validation and privacy

`build_with_dependencies(facts, context, entry, witness, factory, project, files,
environment, parse_facts=..., request=...)` replays the witness against separately
pinned request, explicit source bytes, parse snapshot and offline environment,
then invokes ordinary T01 build and attaches the catalog. Pure builder users also
receive evidence hashes derived from canonical `facts.sources`, never self-certified
from witness hashes. There is no new CLI/discovery/parser mode. Source recovery,
classpath, JDK, time, heap and AST budgets are exactly EXEC-01's existing bounds.
The witness is bounded to 4 MiB; at most 32 recovered methods and 20,000 site records
are accepted. No new Java body or expression is recovered.

`validate_model` rederives the entire catalog and checks equality, containment,
source hashes and semantic levels. This is structural consistency, not source
attribution. After transport, use `verify_model_dependencies` with separately
pinned inputs to repeat attribution and reject coherent witness/catalog forgeries,
including deleted relevant dependencies. Removing both witness and projected site
can evade a structural-only validator; it cannot pass pinned source replay. The
existing independent Java test oracle has no imports from Mana and separately
checks selected declarations/spans/dispatch/body availability. Neither same-host
replay nor the oracle proves runtime execution or host authenticity.

No booleans authorizing traversal are accepted. The producer's self-reported
VERIFIED state alone is insufficient at the API boundary. Compiler errors invalidate
positive bindings. BLOCKED/CONFLICT witnesses are rejected without altering T01.
Historical witnesses/models are not rewritten. Source-bearing S01 data remains
inside the local memory boundary during the real replay; only metadata is persisted.

## Executable admission proposal — first missing premise

A later bounded admission contract would need per-site, source-linked proof of:
(a) caller entry under the T01 scenario, (b) evaluation dependencies before the site,
(c) exact declaration/dispatch or an explicit unresolved cut, (d) supported entry
semantics separate from callee body traversal, (e) all earlier calls' normal
continuation before any successor, and (f) Spring interception evidence independent
of Java binding. Missing any premise produces a frontier, never a default true.
For nonempty/unavailable bodies the caller cannot continue merely because the
callee entry is represented. A source call in a conditional branch needs a justified
branch premise; a constructor needs argument evaluation and lifecycle/abrupt-transfer
semantics. Receiver/result dataflow is not supplied by this catalog.

The current frontend records no independently checkable expression-evaluation
relation for REAL-01 line 86. This is the first missing admission premise.
No new expression parser, body recovery, branch simulator, CFG, propagation rule,
Spring rule, S02 or VIS-01 behavior is implemented to fill that gap. Future admission
is a separate design/compatibility decision; this partial extension does not prove
that every possible full extension requires v2, nor silently claim it is compatible.
