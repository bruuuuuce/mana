# Transaction Visualization v1 — VIS-01

Presentation-only extension of `scripts/skill_factory/transactions/plantuml.py`.
The renderer consumes a validated S02 report, its exact scenario sidecar and the
original S01 Timeline bytes. S01 contains the authoritative T01 model. There is
no Java parsing, SQL parsing, boundary reconstruction, lock inference or new graph
analysis in the renderer. T01, S01 and S02 retain their original semantics.

## Input and publication contract

```sh
python3 scripts/mana-transaction-visualization.py \
  --timeline t=docs/examples/transaction-01-t02-s02/C/inputs/t.json \
  --report docs/examples/transaction-01-t02-s02/C/wait-dependency.json \
  --scenario docs/examples/transaction-01-t02-s02/C/scenario.json \
  --output-dir /private/tmp/my-vis-C
```

Choose a fresh canonical external directory. The CLI reuses S02 bounded JSON
reads (duplicate keys, nonfinite numbers and excessive nesting rejected), byte
budgets, regular-file checks and exclusive publication. Existing destinations,
symlink aliases and configuration/discovery destinations are refused. Exit 0
means **SOURCE_GENERATED**, never runtime execution or successful SVG rendering.
Exit 2 means rejected input and no published visualization.

Before rendering, the explicit sidecar must equal the report's scenario.
`validate_report(report, raw_inputs)` verifies exact Timeline byte digests and
lengths, canonical embedded T01 digests, namespaces, scenario identity and the
complete source projection. It invokes the existing Timeline/T01 validators.
A changed newline in a Timeline invalidates its digest. Coordinated fabrication
of internally consistent artifacts is not authenticated source proof; rerun the
original analyzers if source freshness must be established.

The existing `render(model)` API remains compatible, including historical label
sanitization behavior. New `render(model, timeline)` validates the Timeline and
requires equality with its embedded model. `render_integrated(report, raw_inputs)`
validates the full S02 projection before returning any artifacts. The supplied
objects are not mutated. Rendering never calls target code or invokes PlantUML.

## View contract

| Artifact | Meaning |
|---|---|
| `sequence-PARTICIPANT.puml` | T01 calls, nested method/scope groups, symbolic physical identities, lifecycle events and S01 JDBC observations |
| `database-CUT.puml` | Only S02 conditional DB wait edges for one common cut; waiter to holder |
| `application.puml` | Synchronous caller-frame to callee-frame completion obligations |
| `mixed-CUT.puml` | DB edges for that cut, application frame edges and typed cross-layer relations; graph domains remain distinct |
| `evidence.json` | Visualization schema, exact validated S02 value, view inventory, positional cross-layer relation references |

Without a cut, `database.puml` and `mixed.puml` explicitly retain the limitation.
Empty graphs retain certainty/coverage labels; they never assert no dependencies.
Multiple cuts produce separate views: edges are never unioned into a purportedly
feasible cycle. Application edges are source completion obligations, independent
of the DB cut. The mixed view does not invent a physical application wait edge.

Time runs top to bottom **within each participant**. Separate sequence panels do
not imply cross-participant order, simultaneity or a measured duration. S01
observations appear before their authoritative T01 sequence boundary and carry
the separate Timeline sequence. UNPLACED observations have an explicit appendix
outside the ordered trace, without an invented position or physical identity.

Groups show method nesting, not continuous current physical activity. Explicit
PHYSICAL_BEGIN/END, SUSPEND/RESUME and SAVEPOINT events define the relevant
intervals. P1 remains live while suspended and P2 runs independently. Resume,
savepoint release and normal scope termination remain conditional. END never
means observed commit/rollback, suspension never means automatic lock release.

The T01 palette is retained: blue independent physical context, green inherited
context, yellow savepoint, gray no transaction, red unknown. Labels L/P/SP,
INDEPENDENT/INHERITED, SUSPEND and event names carry the semantics independently
of color. Source-demonstrated bean/proxy metadata and call-site references are
shown with the original certainty.

DB candidate edges are red dashed arrows, application completion edges are solid
blue arrows, and typed mixed relations are dotted purple arrows. Conflict
candidates remain explicitly UNORIENTED with holder UNKNOWN; they do not become
wait edges. Repeated typed links with the same endpoints and type share one
visual edge listing all original relation references, without semantic merging.

## Certainty and traceability

KNOWN / VERIFIED means validated static structure and references only. Actual
execution stays CONDITIONAL. UNKNOWN is not absence. INCOMPLETE and its reasons
are visible; runtime is NOT_RUN. No view asserts DEADLOCK_CONFIRMED or universal
deadlock freedom. S02 `NO_CYCLE_IN_MODELED_SCENARIO` is labelled as structural
exclusion limited to selected operations and that cut, separately from missing
premises and contradicted candidates.

Every DB arrow carries its S02 claim ID, candidate ledger ID, resource and cut.
Premise IDs appear in notes. `evidence.json.validatedS02.claims` retains full
premises, evidence, property certainty, request/holding obligations and endpoint
namespaces. The namespace preserves scenario, participant, input digest and
original P/frame ID: a/P1 and b/P1 are distinct identities. Operations retain
source paths, lines, hashes, UTF-16 spans, causal positions and leaf witnesses.
Application arrows carry their claim ID and call site. `relationRefs.Rn` maps to
the original `crossLayerRelations[n-1]`; no synthetic S02 claim is created.
Long display labels are bounded; the evidence index retains their complete values.

All input-derived diagram labels use the existing restrictive ASCII sanitizer;
identifiers used in filenames are validated by S02. Only fixed renderer code emits
directives and arrow syntax. No includes, URLs, hyperlinks, preprocessing or
untrusted PlantUML directives are accepted. Exact structured input values remain
in JSON only. Same inputs produce identical source and evidence bytes. SVG byte
identity across PlantUML/JVM/font/Graphviz versions is outside this contract.

## Rendering and verification

PlantUML invocation is a separate explicit operation, for example:

```sh
java -Djava.awt.headless=true -XX:-UsePerfData \
  -jar /Applications/plantuml-1.2024.8.jar -checkonly /private/tmp/my-vis-C/*.puml
java -Djava.awt.headless=true -XX:-UsePerfData \
  -jar /Applications/plantuml-1.2024.8.jar -tsvg /private/tmp/my-vis-C/*.puml
python3 tests/transaction-visualization.py -v
```

The renderer test uses `MANA_PLANTUML_JAR` or the local JAR path above. If unavailable,
its rendering check is explicitly skipped with NOT_RUN. Source generation and
rendering must be reported separately. Examples are delivered under
`docs/examples/transaction-01-vis-01/`.
