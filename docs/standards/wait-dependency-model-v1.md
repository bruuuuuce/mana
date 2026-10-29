# Wait Dependency Model v1 — bounded S02-I01

Offline conditional static consumer. Authority is the
[D00 contract](../reports/TRANSACTION-01-T02-S02-contract.md), its
[35 manual oracles](../reports/TRANSACTION-01-T02-S02-oracles.csv), the
[I01 plan](../reports/TRANSACTION-01-T02-S02-implementation-plan.md) and
[approved D01 decisions](../reports/TRANSACTION-01-T02-S02-D01-decisions.md).
This implementation awaits independent semantic review. Runtime capture and
correlation R1–R7 are outside I01. No `OBSERVED` claim is accepted or emitted.

Use a fresh external output directory. The supplied Timeline files already
contain their authoritative T01 models. S02 validates them through the current
`validate_timeline`, including rule-2 embedded-source verification, without
executing, repairing or regenerating the target.

```sh
python3 scripts/mana-wait-dependencies.py \
  --timeline ta=docs/examples/transaction-01-t02-s02/A/inputs/ta.json \
  --timeline tb=docs/examples/transaction-01-t02-s02/A/inputs/tb.json \
  --scenario docs/examples/transaction-01-t02-s02/A/scenario.json \
  --output-dir /private/tmp/my-s02-A

python3 scripts/mana-wait-dependencies.py \
  --timeline ta=docs/examples/transaction-01-t02-s02/A/inputs/ta.json \
  --timeline tb=docs/examples/transaction-01-t02-s02/A/inputs/tb.json \
  --scenario docs/examples/transaction-01-t02-s02/A/scenario.json \
  --validate /private/tmp/my-s02-A/wait-dependency.json
```

The output includes `wait-dependency.json`, `report.md`, a database Mermaid source
for each witness cut, `application.mmd` and `cross-layer.mmd`. Without a cut,
`database.mmd` contains the isolated known identities and no wait edges. Files
are never overwritten. Exit 0 means a validated result was produced; it does not
mean the scenario has complete coverage or lacks risk. Exit 2 returns a structured
`REJECTED_INPUT` or `BUDGET_EXCEEDED`, `coverage: INCOMPLETE`, `published: false`.

## Sidecar schema: `mana.wait-scenario/v1`

The sidecar is separate JSON with exactly these keys; concrete complete examples
are in [A](../examples/transaction-01-t02-s02/A/scenario.json),
[B](../examples/transaction-01-t02-s02/B/scenario.json) and
[C](../examples/transaction-01-t02-s02/C/scenario.json).

| Field | Structure and interpretation |
|---|---|
| `schema`, `id` | Exact version above; local scenario identifier |
| `inputs` | Array of `{id, sha256}` referencing exact supplied Timeline bytes; `--timeline ID=PATH` must supply exactly this set |
| `participants` | `{id, input, independence}`; input ID plus premise ID or null. Two aliases can reference the same artifact, but each is a distinct instance and needs explicit independence for a concurrent wait claim |
| `premises` | `{id, statement, scope, state, provenance, dependsOn}`. Scope equals scenario ID; provenance is `{source, reference}` with nonempty strings. State is `EXPLICIT_ASSUMPTION`, `UNKNOWN`, or `CONTRADICTED`. Dependencies are premise IDs in an acyclic graph |
| `resources` | `{id, database, databaseRelation, objectMatch, lockTargetOverlap, granularity, premises}`. Database is an opaque alias or null. Each relation is `SAME`, `DISJOINT`, or `UNKNOWN`; granularity is `UNKNOWN` or the abstract `OPAQUE_TARGET`. Premises has separate `database`, `object`, `overlap` premise IDs or null |
| `operations` | Selected DB hypotheses `{id, participant, observation, resource, binding, request}`. Resource is opaque resource ID or null; binding is `{datasource, database, enlisted, premise}` with explicit aliases/true or unknown null; request is `{mode, premise}`. No physical/context/position override fields are accepted |
| `lockRule` | `{id, version, modes, compatibility, blockingPremise}`. Version is a positive integer; mode names are abstract, never DB modes. Compatibility entries are `{left, right, result}` with `COMPATIBLE`, `INCOMPATIBLE` or `UNKNOWN`; defined pairs must be symmetric. Missing pairs remain UNKNOWN |
| `cuts` | `{id, prefixes, pending, holdings, temporal}`. Prefixes maps every participant to an original T01 sequence boundary; pending lists selected operation IDs. Holdings entries are `{operation, acquisitionPremise, retentionPremise}` with distinct premise references. Temporal is `{kind, premise}` with kind `CONCURRENT`, `SERIAL`, `OUTER_REQUIRES_NEW`, or `UNKNOWN` |

Identifiers use `[A-Za-z][A-Za-z0-9_-]{0,63}`. No free-text premise is parsed to
infer resource identity, ordering, locks or dispatch. Explicit structured fields
state the hypothesis; provenance and qualitative state determine whether it is
usable. MODEL_EVIDENCE is generated only from validated inputs; a sidecar cannot
self-certify it or supply runtime evidence. UNKNOWN dependencies remain UNKNOWN;
CONTRADICTED dependencies exclude the associated candidate.

`prefixes[p] = n` includes T01 events with sequence **less than n**. A pending
request is at its invocation boundary n, before its normal return, and does not
complete that invocation. `len(events)+1` denotes the complete normal suffix.
Timeline sequence and T01 sequence remain separate fields. A holder acquisition
must precede the prefix, under separate acquisition and retention premises.
A pending earlier leaf cannot supply the normal return required by a later leaf.
An UNRESOLVED_CALL frontier can supply its known prefix invocation, never a
continuation beyond it. This does not qualify dispatch or create a resource leaf.

A cut containing simultaneous incompatible acquisitions, progress past a pending
return, serial nonoverlapping lifetimes or a frontier crossing is contradicted.
It produces exclusions and explanations, not conditional DB edges. END before
cut excludes its P. END in the future normal suffix does not erase the live P
at the cut. L/SP ends do not determine lock retention; SUSPEND preserves modeled
P lifetime but proves neither acquisition nor retention.

## Report and certainty

`mana.wait-dependency/v1` contains the D00 envelope plus `waitCandidates` (W1–W8
ledgers) and `assessment` (per-cut and aggregate results). `scenario` is the exact
sidecar object, copied without interpretation changes. Original Timeline/T01
artifacts are referenced, never rewritten. `inputs` records exact Timeline byte
hash/length and a separately declared canonical digest/length of its embedded T01:
`sorted-compact-ascii-json/v1` is JSON with sorted keys, compact separators,
ASCII escaping and no nonfinite numbers. It is not a claim about the bytes of
an original standalone T01 file that was not supplied.

Every inventory operation retains the complete original S01 observation, its
namespace, original Timeline/T01 sequences, original event and leaf witness,
structured normal-return dependencies, P lifetime events, and suspension records
and interval events. Null identity carries UNKNOWN; absent identified suspension
carries ABSENT. `selectedForDatabase` distinguishes selected hypotheses from the
remaining inventory. All original Java/SQL/hash/path/line/UTF-16 source evidence
is accessible through these references.

Claims carry category, rule/version, certainty, property certainty, premise IDs,
source operation references, generated model premises with provenance and excluded
properties. Operation references provide the original endpoints, resource descriptor,
causal position, lifetime and suspension without duplicating or changing their
semantics. Application claims instead carry exact caller/callee frame namespaces,
call site, contexts and normal-return dependencies. Their resource is
`FRAME_COMPLETION` / `FRAME`, with database `NOT_APPLICABLE`.

The five categories remain distinct. READ/WRITE alone yields RESOURCE_OPERATION.
FOR UPDATE adds only a STATIC_SYNTAX request candidate with UNKNOWN mode,
acquisition and retention. Explicit scenario rules may add separate CONDITIONAL
abstract requests/conflicts. Conflicts are unoriented and do not supply a holder.
Each DB wait edge has an independently inspectable W1–W8 ledger, references to
both request and holding, separate acquisition/retention premises and one cut.
No missing or contradicted obligation qualifies an edge.

Graph node identity retains the tuple `(scenarioId, participantId, inputDigest,
originalPhysicalId)`; frames use `originalFrameId` in a distinct graph/domain.
`databaseGraph` contains only conditional waiter→blocker edges between identified
distinct P. `applicationGraph` contains resolved synchronous caller→callee
completion obligations, including calls whose transaction boundary is unresolved.
Async does not receive a synchronous obligation. Typed cross-layer links remain
outside both wait edge sets. The validator checks invariants and reprojects the
full report against validated input bytes; independent manual oracles supply
semantic expectations rather than producer/validator self-agreement.

Cycles are qualified per common cut. A structural cycle only in the union of
separate cuts is `CYCLE_FEASIBILITY_UNKNOWN`. A feasible conditional DB cycle is
`CONDITIONAL_CYCLE_RISK`. A resolved suspended-outer/replacement completion circuit
is `CONDITIONAL_CROSS_LAYER_COMPLETION_RISK`, with no fabricated DB return edge.
`NO_CYCLE_IN_MODELED_SCENARIO` applies only to the selected scope and listed cuts;
unknown data is reported separately and no global safety conclusion is asserted.

## Bounds and verification

I01 models one/two input artifacts, at most two participant instances, two opaque
resources, four selected DB operations, one nested suspension level, and one
explicit cut per hypothesis. Multiple hypotheses retain separate cut IDs; they
are not combined into a feasible cycle. Other observations remain in inventory.
Exceeding these scope limits gives `scopeStatus: UNSUPPORTED`, coverage INCOMPLETE
and result UNKNOWN, with no partial DB graph claimed to cover the excess scope.
Unselected observations, unplaced syntax, unresolved data, absent cuts and T01
uncertainties are also reported as coverage limitations.

Hard budgets: 4 MiB per Timeline, 4 MiB per embedded canonical T01, 8 MiB combined
unique supplied Timeline bytes (embedded T01 counted once), 2 MiB for each scenario
sidecar and S02 report (also checked in its actual CLI serialization),
100,000 candidate comparisons and 5,000 serialized edges. The edge count
conservatively includes typed cross-layer relations. Reading rejects excess bytes
before publication; comparisons/edge construction stop on excess, never truncate.
JSON additionally rejects duplicate keys, nonfinite numbers and nesting over 128;
abstract compatibility has at most eight modes. Existing S02 reports also have the
2 MiB read cap for CLI validation. These are I01 budgets, not new
release requirements. No schedule enumeration, general SQL resolver or exception
path reconstruction is attempted.

Run `python3 tests/wait-dependencies.py -v`. The dedicated synthetic Java source,
manual [oracle expectations](../../tests/fixtures/wait-dependencies/oracles.json)
and [scenario builder](../../tests/fixtures/wait-dependencies/scenarios.py) are
versioned separately from all historical fixtures. Expectations are transcribed
from D00 before S02 execution. Reference lookup against T01 only binds input IDs
and sequences; it does not produce expected verdicts. All 30 static A–I cases and
J05 are exercised. J01–J04 retain DEFERRED status; no runtime adapter is simulated
and no runtime claim is qualified. Tests also consume the three canonical legacy
S01 examples read-only. General T01/S01 QA, CI, runtime and external renderer
qualification are separate gates.
