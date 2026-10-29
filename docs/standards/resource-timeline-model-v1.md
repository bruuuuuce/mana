# Resource Timeline Model v1 — T02-S01

Status: implemented foundation, conditional static analysis, pending independent
review. The current S01 mandate authorizes this bounded implementation; the older
T02 proposal remains preserved as historical local material. This model consumes
[Transaction Model v1](transaction-model-v1.md); T01 alone owns physical identities,
logical scopes, propagation, suspension, savepoints, interception and lifetime.

## Invocation and scope

```sh
python3 scripts/mana-resource-timeline.py \
  --project-root tests/fixtures/resource-timeline \
  --context tests/fixtures/resource-timeline/context.json \
  --entry 'fixture.Entry#independent()' \
  --output-dir /private/tmp/my-resource-timeline
```

Use a fresh external output directory. The CLI inherits T01's canonical path,
inventory, source snapshot, temporary isolation, applicability and JDK parse-only
rules. It uses the same single source snapshot and T01 `build`/`validate_model`,
then projects resource observations. No target build, class loading, database
query, target write or candidate activation occurs. Exit 0 means a validated
conditional model, possibly with no positioned operations; exit 2 means blocked
input, tooling, parsing, budget or publication. Inspect observations and limits.
The combined JSON has a 4 MiB publication budget. Existing output is not replaced.

## Structured format

Schema identifier: `mana.resource-timeline/v1`. The Python implementation's
`validate_timeline(report)` is the v1 semantic validator.

| Field | Contract |
|---|---|
| `status` | Always `CONDITIONAL_STATIC_SCENARIO`; never runtime qualification |
| `transactionModel` | Complete, unchanged `mana.transaction-model/v1` supplied by T01, including context/evidence/uncertainties |
| `sourceFacts` | Parse-only AST facts from the same snapshot; invocation arguments add literal kind/value and source location |
| `observations` | Ordered observation IDs O1…On, including explicitly unplaced source syntax |
| `timeline` | Contiguous sequence of unchanged T01 event wrappers and positioned resource observations |
| `limits` | Explicit fixed premises/limitations of this increment |

Each observation contains:

| Field | Meaning |
|---|---|
| `frame`, `method`, `applicationOperation` | T01 frame, enclosing Java method, receiver and invoked method |
| `callSite`, `evidence` | Relative source path, SHA-256, 1-based line and JDK UTF-16 offsets (`end` exclusive); field/argument evidence where available |
| `operationType` | `READ`, `WRITE`, `EXPLICIT_LOCK_REQUEST` or `UNKNOWN` |
| `sqlLiteral` | Supported source literal, otherwise null; unsupported SQL grammar can retain the literal with UNKNOWN resource/type |
| `resource` | Exact lexical SQL identifier or UNKNOWN; never a runtime database object identity; lock granularity always UNKNOWN |
| `transactionContext` | Copied current T01 `{kind, physicalId, manager}` at the frontier, or wholly UNKNOWN for unplaced syntax |
| `datasource` | `{status: UNKNOWN, id: null}` in S01; no connection/datasource binding resolver is qualified |
| `enlistment`, `lockAcquired` | Always UNKNOWN; enclosing P is causal context, not proof that JDBC joins that transaction |
| `certainty`, `placement` | CONDITIONAL/T01_FRONTIER or opt-in T01_RESOURCE_LEAF with `beforeT01Sequence`, or UNKNOWN/UNPLACED with null position |
| `premises`, `limits` | Conditional reachability and explicit unresolved API, datasource or traversal restrictions |

`timeline` entries have `sequence`, `kind: T01_EVENT`, and the original `event`,
or `sequence`, `kind: RESOURCE_OPERATION`, and an observation ID. T01's original
sequence numbers are not renumbered inside wrappers. Removing RESOURCE_OPERATION
entries and unwrapping yields exactly T01's events. Observation array order is
positioned observations first, followed by unplaced syntax in T01 frame/AST order;
array order is **not** chronology for unplaced syntax. UNPLACED observations have
no timeline entry and must never supply an edge to a future wait graph.

## Minimal supported reconstruction

The qualified source pattern is a direct, noninitialized, unqualified
`@Autowired JdbcTemplate` field, explicitly imported as
`org.springframework.jdbc.core.JdbcTemplate`, in a class without declared parents,
inside a T01-selected method without parser hazards (including bounded formal
parameters; see REAL-01-F01 in Transaction Model v1). `jdbc` and `this.jdbc`
receivers are supported. Optional/qualified injection, inherited members, local
aliases, other resource APIs and runtime wiring remain unresolved. Even the
qualified source field does not prove Spring can start or bind a datasource.
Formal runtime values remain UNKNOWN; a parameter named `jdbc` does not bind the
field's resource API. `sourceFacts` remains source-bearing local evidence at the
explicit output destination; default AST diagnostics exclude source expressions.

Recognized invocation APIs are `execute`, `update`, and `queryForList`, each with
exactly one AST string literal argument. A deliberately closed, case-insensitive
SQL grammar recognizes the following exact forms (outer whitespace allowed):

| SQL form | Type |
|---|---|
| `SELECT * FROM identifier` | READ |
| `SELECT * FROM identifier FOR UPDATE` | EXPLICIT_LOCK_REQUEST |
| `UPDATE identifier SET column = unsigned_integer` | WRITE |
| `INSERT INTO identifier (column) VALUES (unsigned_integer)` | WRITE |
| `DELETE FROM identifier` | WRITE |

Identifiers use `[A-Za-z_][A-Za-z_0-9]*`; a name is copied from the literal only
after the whole SQL matches. `update` permits only WRITE; `queryForList` permits
READ or EXPLICIT_LOCK_REQUEST; `execute` permits all three. Qualified/quoted names,
joins, WHERE clauses, placeholders, comments, semicolons, multiple statements,
concatenation, variables and computed/dynamic SQL are outside this grammar.
These produce UNKNOWN rather than guessed names. No row identifier is emitted.
FOR UPDATE is request syntax; it does not prove database acceptance, lock mode,
row/table granularity, acquisition, retention or blocking.

## Causality, physical lifetime and uncertainty

Without the opt-in leaf extension, T01 does not resolve JDBC bodies. S01 can observe the invocation syntax at the
first T01 `UNRESOLVED_CALL` frontier and insert an observation immediately before
that event. It preserves the frontier and UNKNOWN continuation. It does not
declare the JDBC call resolved or resume traversal past it. Any unresolved
resource API at a frontier is represented with UNKNOWN type/resource.

Context starts with the frame's T01 `duringState`; a resolved child return uses
that child's T01 `afterState`. This matters when an empty REQUIRES_NEW child ends
P2 and restores P1 before a later resource invocation. P identities and manager
are copied, never allocated, inferred from JDBC, or substituted. An operation
referencing a known P must be positioned while that P is live and current.

Suspension retains P1's physical lifetime, excludes it from current operation
context and allows independent P2 operations. Ending P2 permits T01's conditional
resume of still-live P1. Savepoint creation/release leaves the same P1 alive.
The terminal T01 `PHYSICAL_END_OUTCOME_UNKNOWN` cannot be followed by a new
operation attributed to that ended P. Exact projection validation rejects
repositioned, duplicated, missing or reassigned observations and modified T01
event wrappers. No commit, rollback or lock release is derived from these markers.

For NOT_ASSERTED bodies, async calls, unknown interception/initial context, or
resource syntax after unresolved continuation, S01 can retain direct JDBC syntax
as UNPLACED observations. It assigns no P or manager even if a boundary-entry
property is known: entry context cannot establish context throughout an
untraversed body. Bodies of methods T01 never visits are not scanned as if called.
Nested calls in dynamic SQL arguments can stop T01 before the outer JDBC call;
the JDBC syntax then remains UNPLACED/UNKNOWN.

### Opt-in resource leaves (D02)

The [Resource Leaf Extension v1](resource-leaf-extension-v1.md) defines the explicit
`resourceLeafPolicy: JDBC_LITERAL_V1` scenario input, closed catalog, source witness,
validation and consumer compatibility. T02 uses the identical context input and
T01 model. A qualified `RESOURCE_LEAF_CALL` supplies the authoritative current
context and causal position; T02 places syntax immediately before that event with
`T01_RESOURCE_LEAF`, retaining the witness premises and prior normal-return
dependencies. It does not infer context for an unplaced suffix or reconstruct
propagation. A later genuine UNRESOLVED_CALL still stops the path.

Only a conditional normal path is represented. Prior leaves must return normally
for later operations to be reached; exceptional paths and runtime success are not
asserted. The extension snapshot must equal T02's source facts. Datasource,
enlistment, acquired locks and granularity remain UNKNOWN for every leaf. Existing
legacy JSON/examples remain valid and unchanged; fresh parser facts additionally
include `statementCall`, which is required to qualify a new leaf.

## Verification and trust boundary

Run `python3 tests/resource-timeline.py -v`. Literal fixture expectations and
temporal negative controls are authored independently of generated timelines.
T01 regression suites remain authoritative for transition/interception semantics.
The fixture and target snapshots are checked for read-only behavior.

Validation checks T01 first, source-hash correspondence, unique method/call-site
evidence, context/lifetime and exact projection. This checks internal consistency
of supplied facts. Like T01, an imported JSON is not independently reparsed against
the source by this validator; coordinated fabrication of sourceFacts and their
declared hashes is not authenticated by embedding them. To refresh source proof,
rerun the read-only CLI on the original project/context and compare artifacts.
Neither these tests nor the example artifacts qualify Spring runtime, database
behavior, concurrency, wait dependencies or deadlock detection.
