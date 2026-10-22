# Transaction Model v1 — T01

The Java/Spring adapter now offers a bounded **conditional static scenario** engine,
not a runtime transaction monitor. Factory generation, explicit analysis, model
validation, rendering and human skill approval remain distinct operations.

## Use

From the Mana checkout:

```sh
python3 scripts/mana-transaction.py \
  --project-root tests/fixtures/transaction-boundaries \
  --context tests/fixtures/transaction-boundaries/context.json \
  --entry 'fixture.A#independent()' \
  --output-dir /private/tmp/my-transaction-scenario
```

Use a fresh canonical external output directory. Existing outputs, target-contained
paths, discovery/configuration surfaces and output symlink aliases are rejected by
existing factory path rules. Analysis is explicitly requested by the caller, never
triggered by candidate generation/validation. Exit 0 means a structurally validated
conditional scenario, potentially containing UNKNOWN regions; inspect uncertainties.
Exit 2 means blocked input/tooling/parse/publication. No candidate is activated.

The context JSON requires these fields (existing v1 inputs remain valid):

```json
{
  "schema": "mana.transaction-context/v1",
  "initialState": "NO_TRANSACTION",
  "entryThroughProxy": true,
  "managerCapabilities": {"tx": {"suspend": true, "savepoints": true}}
}
```

`initialState` is `NO_TRANSACTION` or `UNKNOWN`. The entry proxy flag and manager
capabilities are explicit **scenario assumptions**, not facts deduced from Spring
presence or from a driver. Capability values are `true`, `false` or `null`; absent
manager capability entries mean unknown. Manager names must match source `@Bean`
declarations. Use `null` without evidence/authority to assert a capability. Setting
true models the conditional case; it is never reported as runtime qualification.
The fixture explicitly stipulates support to exercise the positive oracle and
uses `context-unknown.json` to exercise the unproven case.

F01 adds one optional field, `aspectjWeaving`, accepting `UNKNOWN` (the default)
or `ASSUMED_APPLIED`. The latter explicitly stipulates **if transactional weaving
applies to these methods**; it is never evidence that a weaver ran. A source
`mode = AdviceMode.ASPECTJ` declaration alone cannot establish weaving application.
The field cannot resolve an unknown interception mode or override PROXY semantics.
No build, runtime probe, weaving tool or evidence-verification infrastructure is
introduced. Inputs cannot claim a `PROVEN` or runtime `APPLIED` status.

## Architecture And Budgets

D02 adds the opt-in [Resource Leaf Extension v1](resource-leaf-extension-v1.md):
`resourceLeafPolicy: JDBC_LITERAL_V1` selects a closed conditional JDBC catalog.
Its versioned `RESOURCE_LEAF_CALL` witness permits normal-path caller continuation
without exploring the library. Omission/`DISABLED` preserves legacy behavior.
`UNRESOLVED_CALL` keeps its original causal-cut semantics; propagation, MR00 and
legacy IR remain unchanged. Enabled reports include source facts and require
extension-aware validation before consumption.

- `mana-transaction.py` reuses factory canonical paths, bounded JSON reads,
  technology adapter, file inventory and external temporary isolation.
- `transactions/JavaFacts.java` uses the JDK compiler AST API in **parse-only** mode.
  It never calls attribution/analysis/code generation for target sources, processes
  annotations, loads target classes, resolves dependencies or starts a build.
- `source.py` compiles only the fixed Mana helper to an external stage, copies
  bounded target source snapshots into that stage, and invokes it with fixed argv.
  Source parsing does not require Spring binaries. The JDK determines accepted
  Java syntax; the local qualification used Corretto 8u442. Syntax outside that
  parser's support blocks with a diagnostic rather than inventing facts.
- Both JDK subprocesses and temporary/cwd/system-property locations use validated
  external stages. JVM/Javac injection environment variables are removed. No host
  global environment is changed. Target scripts, wrappers and processors never run.
- `model.py` resolves a deliberately restricted annotation/call scenario; it owns
  the semantic state transitions and independent structural/lifetime validator.
- `plantuml.py` is a pure renderer; no includes, URLs or source directives are
  emitted. Labels are sanitized and bounded. PlantUML is not invoked by analysis.

Factory inventory budgets remain 5,000 files / 1 MiB per file / 32 MiB read total.
The parser additionally requires 1–64 Java files totaling at most 2 MiB; each fixed
JDK call has a 60-second timeout, parser heap is 128 MiB and fact/result payloads
are capped at 4 MiB. Traversal stops at 16 call levels or 128 frames. Context JSON
uses the existing 1 MiB / depth-32 / 20,000-token contract. Budget limits are
explicit blocked/UNKNOWN outcomes, never evidence of complete resolution.

## Intermediate Representation

`mana.transaction-model/v1` stores:

| Field | Meaning |
|---|---|
| `entry`, `context`, `contextEvidence`, `assumptions` | Requested entry and explicit scenario inputs, hash/location and conditional premises |
| `evidence` | Relative source paths with SHA-256 snapshot hashes |
| `managers` | Source-declared manager identity/type/location and separately labelled assumed capabilities |
| `interceptionMode`, `proxyMode`, `aspectjWeaving` | PROXY/ASPECTJ/UNKNOWN mode; separate CLASS/JDK/UNKNOWN proxy configuration; explicit conditional weaving premise and runtimeApplication UNKNOWN |
| `frames` | Caller/callee method, actual source invocation location, bean/class/name evidence, proxy mode/crossing, interception, effectiveContext, manager, boundary configuration, before/during/after state and certainty |
| `logicalScopes` | Intercepted transaction scopes plus the explicitly unresolved UNKNOWN/null attempted-boundary marker (D2), which is not a definitely executed scope; unannotated executions and PROXY self-invocations create neither |
| `physicalTransactions` | Symbolic P identities, manager and begin/end frame; `runtimeIdentity` and outcome always UNKNOWN |
| `suspensions` | Retained old P, replacement P and owning scope; never conflated with a savepoint |
| `savepoints` | SP identity attached to the **same** physical P and owning nested scope |
| `events` | Ordered frame/call, logical/physical boundary, suspend/resume and savepoint events |
| `uncertainties` | Source-linked UNKNOWN/UNSUPPORTED reasons; unsupported continuation/body order is not asserted |

Source positions are JDK UTF-16 character offsets (`start`, exclusive `end`) and
1-based lines, **not byte offsets**. Every source fact carries its file hash.
A root invocation is a scenario input without a fabricated source caller/call site.
A source call site identifies syntax; proxy execution and path reachability remain
conditional. Bean bindings record the injected field location separately.

The distinct semantic kinds are `TRANSACTION_LOGICAL_SCOPE`,
`TRANSACTION_PHYSICAL`, `TRANSACTION_SUSPENDED`, `TRANSACTION_SAVEPOINT`,
`NO_TRANSACTION`, and `UNKNOWN`. Frames are method executions, not automatically
transaction logical scopes. Logical/physical IDs are never interchangeable.

Each new frame has two independent F01 observations:

- `interception.status`: `APPLIED`, `BYPASSED` or `UNKNOWN`, with a reason.
  APPLIED describes conditional advice application, not successful boundary
  creation: an unsupported capability/manager can still leave context UNKNOWN.
- `effectiveContext.before/during/after`: `ACTIVE`, `INACTIVE` or `UNKNOWN`,
  derived respectively from previous/during/after state. ACTIVE refers to the
  symbolic P under scenario premises; it does not establish a runtime identity.

BYPASSED never converts ACTIVE to INACTIVE. A known PROXY self-call inherits
the caller's P (or its known absence/uncertainty), ignoring the called annotation's
propagation. F02 composes APPLIED and BYPASSED when advice application is the only
uncertain boundary mechanism. Physical activity, identity and manager are intersected
separately; UNKNOWN advice does not itself force UNKNOWN physical context. Body
traversal remains unasserted. A following call is modeled only if an empty callee's
normal synchronous unwind preserves the caller's known context in both alternatives.
Historical v1 models without these additive fields remain readable/validatable.

### Conditional context composition (F02)

An additive frame `contextComposition` contains source-linked execution premises,
the `APPLIED`/`BYPASSED` alternatives, and their common `duringState`/`afterState`.
The frame's states must equal those common states. Composition is confined to an
otherwise resolved synchronous boundary, known annotations and straight-line syntax;
async, unknown annotations, programmatic/control-flow hazards and unresolved dispatch
do not acquire these premises. `duringState` describes the boundary at method entry,
not proof that an untraversed body preserves it throughout execution.

Each alternative carries physical state, identity relation, logical-scope presence,
savepoint/suspension presence and boundary resolution. `IF_APPLIED` means **CONDITIONAL**
presence solely in that advice alternative; `ABSENT` and `UNKNOWN` are distinct.
`FRESH_IF_APPLIED` describes a branch-only fresh symbolic identity. It is not a
globally allocated P and must never be equated to the inherited P. These branch-only
logical/physical/savepoint/suspension effects are not materialized as unconditional
entities or events in the original v1 arrays. Thus a conditional logical scope can
coexist with ACTIVE/P1 without claiming a certain additional L entity/lifetime.

| Prior context and declared propagation | Common context at boundary | Conditional effects |
|---|---|---|
| ACTIVE/P1, same identified manager, REQUIRED | ACTIVE/P1, same manager | Logical scope IF_APPLIED |
| NO_TRANSACTION, REQUIRED | Activity/identity UNKNOWN | Fresh transaction and logical scope only if APPLIED |
| ACTIVE/P1, same manager, REQUIRES_NEW, suspend true | ACTIVE, same manager, physicalId null | APPLIED uses a fresh identity and suspends P1; BYPASSED executes in P1 |
| ACTIVE/P1, same manager, NESTED, savepoints true | ACTIVE/P1, same manager | Logical scope and savepoint IF_APPLIED on P1 |
| Unknown/unsupported capability, ambiguous/unmodeled manager, unknown prior identity or other propagation | APPLIED boundary unresolved; retain only properties common with BYPASSED | No savepoint/suspension support invented |

In F02 a `TRANSACTION_PHYSICAL` state may have `physicalId: null` when activity is
common but identity is not (REQUIRES_NEW above). This requires a validated
composition witness; null identity is never a new or externally proven transaction.
The manager can remain identified independently. `effectiveContext.during` is
ACTIVE in this case while the diagram labels `PHYSICAL_ID_UNKNOWN`.

After-state refinement is limited to source-observed empty bodies and supported
APPLIED boundaries: both alternatives restore the incoming context on **normal
synchronous unwind**. This does not prove invocation, successful return, commit or
rollback. An unasserted nonempty body or unresolved APPLIED boundary leaves the
after-state UNKNOWN. In particular the two old F01 UNKNOWN-advice empty REQUIRED
fixtures retain UNKNOWN during execution but refine after-state to INACTIVE; their
historical receipt/model artifacts remain unchanged.

The validator checks both alternatives, propagation/manager/capability consistency,
execution premises and provenance, common properties, caller-context linkage and
the lifetime of inherited P. It rejects a claimed P1 current identity in the
REQUIRES_NEW alternative, unsupported conditional savepoints, missing alternatives,
or branch-only entities emitted unconditionally. UNKNOWN/ACTIVE without a valid
composition remains invalid. This is structural/semantic consistency of supplied
source facts, not independent re-parsing of the source or a runtime qualification.

## Bounded Resolution

Positive paths use explicit Spring imports/fully qualified annotations,
`@Service`/`@Component`/`@Repository`/`@Controller` declarations, direct non-initialized
`@Autowired` concrete fields, zero-argument methods and synchronous straight-line
call statements. Optional/qualified/ambiguous injection is unresolved. Declared
subtypes, interfaces/inheritance, parameterized methods/overloads, composed or
unresolved annotations and external/dynamic wiring are not silently resolved.
The model assumes wiring closed to observed declarations and labels this premise;
it does not claim that a real Spring context could start from a static fixture.

A single explicit `@EnableTransactionManagement(proxyTargetClass=true)` with proxy
mode supports conditional public class-proxy interception. In known PROXY mode,
self/direct invocation bypasses transaction annotations and retains caller context.
Private/static/final methods are not assumed
intercepted; inaccessible external private calls are UNKNOWN. JDK proxies, nonpublic
class-proxy visibility/version variations, final classes, unknown proxy settings,
async, complex control flow, lambdas/method references and unresolved calls retain
UNKNOWN. Reflection/programmatic transactions stop confident continuation; target
code is never executed to fill the gap.

In explicitly declared ASPECTJ mode, the `ASSUMED_APPLIED` weaving premise permits
conditional advice on self/direct invocations, reusing the same REQUIRED,
REQUIRES_NEW and NESTED engine rules and manager capabilities. Without that premise,
annotated calls are UNKNOWN; a self-call is never treated as a PROXY bypass.
Interception mode UNKNOWN also leaves annotated self/direct calls UNKNOWN.
The positive AspectJ subset remains public concrete stereotype-bean methods with
the existing straight-line/annotation/manager limits; private/static/final and
other AspectJ forms are not newly qualified. `proxy.crossed` is false in AspectJ
scenarios and its reason is `NOT_APPLICABLE_ASPECTJ`: advice application is a
separate observation. The legacy `entryThroughProxy` input only affects PROXY
interception and cannot enable or disable AspectJ weaving.

Method `@Transactional` replaces class defaults. Only boundary attributes
(propagation/manager qualifier) are resolved; other annotation arguments are retained
and explicitly listed as unmodeled. No rollback, isolation compatibility, timeout,
read-only enforcement, advisor ordering, classpath or exception-path proof is claimed.
`DataSourceTransactionManager` must be source-declared for positive manager resolution.
Other types, duplicated/aliased bean names or nonunique default selection stay UNKNOWN.

## Propagation State Rules

| Configuration | Modeled conditional boundary |
|---|---|
| REQUIRED | Open a logical L; join current same-manager P or create a symbolic P when prior state is NO_TRANSACTION |
| REQUIRES_NEW | Open independent P; if an old P exists require explicit suspend support, emit SUSPEND before begin and RESUME after end |
| NESTED with an old P | Require explicit savepoint support; create SP on old P, never an independent physical transaction |
| NESTED without an old P | Start a P under the same no-transaction entry rules; no fictitious savepoint |
| Unannotated method / PROXY self-invocation | Execute in inherited context without creating a logical transaction scope; NO_TRANSACTION and UNKNOWN remain distinct |
| ASPECTJ self-invocation with ASSUMED_APPLIED weaving | Apply the conditional annotated propagation rules above; no proxy crossing is required |
| ASPECTJ without weaving premise / unknown interception mode | Annotated call stays UNKNOWN, never a proxy bypass assumption |
| Other propagation / unknown manager or prior identity | Recognize configuration, emit UNKNOWN/UNSUPPORTED; do not infer unimplemented behavior |

Physical IDs are `SYMBOLIC_SCENARIO`, certainty `CONDITIONAL`, actual runtime identity
UNKNOWN. A missing capability is not inferred from manager class name. Source facts
and context assumptions are separate. Scope end and savepoint release/resume are
normal-unwind conditional markers; transaction commit/rollback is not asserted.
Unknown body/path continuation does not become a successful return prediction.

The validator independently checks frame nesting/order, source call-site containment,
identity references, logical-to-physical mapping, entity begin/end pairs, distinct
independent identities, savepoint reuse and symbolic/runtime-unknown identity policy.
It does not prove semantic completeness or runtime correctness of the source program.

### Physical lifetime invariant (F03)

A physical transaction that has ended cannot be active in a later state on the
same path. A later active reference must identify a different, demonstrably live
transaction; a symbolic P identity cannot be reopened or recycled. This applies
to ordinary callers as well as frames with conditional context composition.

The existing ordered trace is sufficient; no schema fields or event kinds are
added. `previousState` is checked immediately before `FRAME_ENTER` against the
initial scenario or the caller's current context. `duringState` describes the
entry boundary after its opening events: a new identity requires its owning
`PHYSICAL_BEGIN`; an inherited identity must already be live and current.
`afterState` is checked at `FRAME_EXIT`, after closing/resume events. A definite
physical after-state must restore the incoming live, unsuspended context.
UNKNOWN continuation does not permit a definite reference to an ended P.

| Existing event | Physical lifetime effect |
|---|---|
| `PHYSICAL_BEGIN` | Start a fresh, never previously started P owned by this frame |
| `LOGICAL_BEGIN` / `LOGICAL_END` | Open/close a logical scope; do not start/end its shared P |
| `SAVEPOINT_CREATE` / `SAVEPOINT_RELEASE_CONDITIONAL` | Open/close a savepoint on the same live P; do not end P |
| `SUSPEND` | Retain the live old P but exclude it from current physical states before beginning its replacement |
| `PHYSICAL_END_OUTCOME_UNKNOWN` | End P after its logical scopes/savepoints close; no later state may retain it as active |
| `RESUME_CONDITIONAL` | Restore the still-live suspended P only after its replacement has started and ended |
| `FRAME_EXIT` | Check the after-state; method exit alone does not end a physical transaction |

v1 does not distinguish physical commit from physical rollback. Both have the
same lifetime consequence represented by `PHYSICAL_END_OUTCOME_UNKNOWN`;
`outcome` remains UNKNOWN. Tests of this terminal marker do not prove either
runtime outcome. F02 branch-only fresh identities remain alternative descriptors,
not unconditional P allocations; its partial common identity still requires the
existing composition witness. The lifetime checks preserve these distinctions.

Run `python3 tests/transaction-physical-lifetime.py -v` for the immutable R3 HIGH
counterexamples, literal positive lifetime expectations and temporal negative
controls. These oracles are not inferred from engine/validator output.

### Transition contract enforcement (MR01)

The normative [MR00 contract](../reports/MANA-TRANSACTION-01-T01-MR00-contract.md)
and its [matrix](../reports/MANA-TRANSACTION-01-T01-MR00-transitions.csv) define
24 transitions and 44 independently decided ACCEPT/REJECT examples. MR01 enforces
that contract using existing v1 fields and events, without adding propagation,
manager types, capability fields, rollback paths or runtime claims.

For ordinary APPLIED frames, supported manager selection, prior context and the
capability premises determine a **closed** set of boundary effects. REQUIRED
joins P1 with one logical scope, or owns a fresh P when entering without a
transaction. REQUIRES_NEW owns a distinct P and, with prior P1, requires explicit
suspend support and restores the still-live P1 only after ending its replacement.
NESTED with P1 requires explicit compatible savepoints, shares P1 and never
allocates an independent P; without prior P it owns a fresh P without a savepoint.
Capabilities not used by a transition need not be true. The context and manager
copies must agree, including unknown capability values. Under D1, true stipulates
effective compatibility for this conditional scenario, never automatic runtime
verification or support inferred from the manager class name.

The validator checks frame-local entity cardinality, required/forbidden effects,
ownership, exact boundary event order and the position of child/body execution.
`previousState` precedes FRAME_ENTER, `duringState` follows the complete opening
prefix, and `afterState` follows all closing/restore events at FRAME_EXIT. States
use only NO_TRANSACTION, TRANSACTION_PHYSICAL or UNKNOWN, with the existing F02
partial-identity exception. Definite after-states must restore incoming context
even when NO_TRANSACTION; closing a participating L alone cannot make P1 inactive.
Only the owning frame can end a P; a terminated identity cannot be reused.
Suspension retains physical lifetime while removing P1 from current execution.

Under D2, the legacy L with `certainty: UNKNOWN` and `physicalId: null` is retained
only as a marker of the attempted/unresolved capability boundary. Its paired
LOGICAL_BEGIN/END delimit the marker, **not a definitely executed scope**, a
successful transaction or a certain source of transactional effects. It cannot
own concrete P/SP/S effects. Validator, renderer and consumers must preserve this
meaning; PlantUML labels it UNRESOLVED_LOGICAL_MARKER, with execution/effects not
established. Known physical lifetime remains separate from the unresolved marker.

Under D3, historical v1 without the additive F01 fields remains supported when
its recorded proxy mode, crossing and source-linked configuration premises permit
reliable classification. Annotation or effect presence alone never establishes
APPLIED. Unclassifiable boundaries cannot receive positive certification of
transactional effects. F02 still validates both alternatives and their exact
common properties, without materializing branch-only entities or body execution.

Under D4, after UNKNOWN requires an actually unresolved, motivated continuation:
a source-linked bounded limit, unresolved source call or unresolved child return.
A bare UNKNOWN flag cannot erase an otherwise known return context. All certain
facts about physical starts, retained/suspended lifetime and terminal identities
remain separately enforced, even when current/return context is unknown. Neither
UNKNOWN nor a well-formed lifetime can legalize incompatible propagation effects.

Run `python3 tests/transaction-transition-contract.py -v` for individual O01–O44,
additional positive coverage of all 24 transitions, exact R4 payload regressions
and D2/D3/D4 consumer constraints. Fixtures are complete, explicitly synthetic
supplied IR with manual expectations, not automatically generated engine oracles.

## PlantUML Notation And Overlap Limit

Groups follow the ordered method stack, with green/shared P, blue/new P,
yellow/savepoint, gray/no transaction and red/unknown regions. Every region also
has textual kind/ID labels; color is supplementary. BEGIN/END, SUSPEND/RESUME and
SP notes have explicit identifiers and event positions, with a legend.
F01 notes separately label interception and effective context, plus INHERITED or
INDEPENDENT physical identity. AspectJ notes state the conditional weaving premise.
F02 notes additionally distinguish a known inherited P, ACTIVE with unknown current
identity, conditional logical scope/savepoint, and an unknown physical context.
Known P1 stays in a shared-context region even when advice is UNKNOWN. The notes
show the alternatives and normal-unwind/body premises; conditional effects are not
rendered as unconditional BEGIN/END or savepoint events.
Original v1 diagrams/models remain unchanged; the renderer can read historical
models using their existing logical/physical state when additive fields are absent.

Sequence `group` fragments are nested method regions; they are not a faithful
arbitrary overlapping multi-participant resource-region notation. In particular,
a suspended P1's retained lifetime overlaps P2 while P1 is not executing. The
renderer preserves the enclosing method region and explicitly annotates SUSPEND
P1 → BEGIN P2 → END P2 → RESUME P1. It does not portray that as a nested savepoint
or two simultaneously executing physical transactions. The JSON event model is
the authoritative testable temporal/identity record.

## References And Verification

Semantic reference: [Spring transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html),
[Spring annotation/proxy rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html),
[DataSourceTransactionManager contract](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html).
Notation: [PlantUML sequence syntax](https://plantuml.com/sequence-diagram).
These explain the intended semantics; local static fixtures do not certify runtime behavior.

Run `python3 tests/transaction-boundaries.py` and the affected factory regressions.
Run `python3 tests/transaction-self-invocation.py -v` for the eight F01 oracles,
capability/uncertainty negatives, target immutability and historical rendering.
Run `python3 tests/transaction-context-alternatives.py -v` for the exact R2
counterexample, literal F02 alternative oracles, validator tampering negatives,
context/continuation preservation and conditional diagrams.
Set `MANA_PLANTUML_JAR` to an existing local jar for real syntax/SVG checks. Missing
PlantUML marks that test NOT RUN/skipped; it is never a syntax PASS. No renderer or
Java dependencies are downloaded. No deadlock/resource/lock analysis is included.
