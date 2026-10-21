# MANA-TRANSACTION-01-T01 — Transaction Boundary Engine

## Status

**IMPLEMENTED_READY_FOR_REVIEW**, limited to the documented conditional static
scenario contract. This is the first boundary engine, not complete Spring/runtime
qualification. No resource/lock or deadlock analysis is implemented.

Verified clean `develop` at `378243883adb101a7a41feef71e2a66b76e7f508`, then
created `feature/mana-transaction-01` in the existing checkout. HEAD remains that
baseline; all changes are uncommitted. No merge, push, new worktree, Familiar or
REL-01/A changes were performed.

## Implementation And Architecture

The existing Java/Spring factory adapter now declares precise implemented T01
capabilities and explicit JDK prerequisites; full-domain capabilities remain
`partially_implemented`. Candidate generation still selects a curated template,
records technology evidence and validates the closed candidate contract. It never
executes analysis or changes candidate trust.

The explicit `scripts/mana-transaction.py` entry point reuses factory technology,
inventory, JSON and path/temp contracts. `transactions/source.py` invokes a fixed
Mana `JavaFacts.java` JDK AST helper; only that helper is compiled, outside the
target. Target source snapshots are parsed without attribution, generation,
class loading, processors, Maven/Gradle, target scripts, LLMs or network calls.
`model.py` computes source-linked conditional transaction events and independently
validates their identities/lifetimes; `plantuml.py` renders the ordered model.
These are Java/Spring adapter components, not a second skill registry/framework.

The [model contract and CLI usage](../standards/transaction-model-v1.md) define
caller/callee and actual source call sites, bean/proxy evidence, boundary config,
manager and capability assumptions, logical/physical scopes, prior/during/after
context, savepoints, suspensions, events and certainty. Source hashes and UTF-16
offsets/lines support traceability. Root entry has no fabricated source caller.

All physical P IDs are `SYMBOLIC_SCENARIO`; actual runtime identity and
commit/rollback outcome remain UNKNOWN. Entry proxy crossing/prior state,
closed observed wiring and suspend/savepoint capabilities are explicit premises.
They are not inferred from technology presence, a manager class or a datasource
constructor. A source manager declaration plus assumed capabilities does not
prove a working database or a Spring context that can start.

## Reference Cases And Examples

The fixture is static and parse-only; it does not build a Spring application.
[Independent oracles](../../tests/fixtures/transaction-boundaries/oracles.json)
retain expected call expressions/callees, identity relationships and uncertainty
alongside [source and context premises](../../tests/fixtures/transaction-boundaries/README.md).
Each example below contains `transaction-model.json` and `sequence.puml` with
source evidence; independent/nested SVGs are also supplied.

| Case | Expected conditional result | Example |
|---|---|---|
| A REQUIRED → B REQUIRED | L1/L2 share P1 | [required](../examples/transaction-01-t01/required/transaction-model.json) |
| A REQUIRED → B REQUIRES_NEW | Suspend P1, independent P2, resume P1 | [diagram SVG](../examples/transaction-01-t01/requires_new/sequence.svg) |
| A REQUIRED → B NESTED | SP1 on P1, no P2 | [diagram SVG](../examples/transaction-01-t01/nested/sequence.svg) |
| A unannotated → B REQUIRED | NO_TRANSACTION → P1 | [outside](../examples/transaction-01-t01/outside/transaction-model.json) |
| A REQUIRED → B unannotated | B inherits P1 without a new logical transaction scope | [inherited](../examples/transaction-01-t01/inherited/transaction-model.json) |
| Self-invocation of REQUIRES_NEW | Annotation bypassed, still P1 | [self-invocation](../examples/transaction-01-t01/self_invocation/transaction-model.json) |
| Unsupported SUPPORTS | Configuration recognized, body/continuation UNKNOWN | [unsupported](../examples/transaction-01-t01/unsupported_propagation/transaction-model.json) |
| NESTED capability not demonstrated | UNKNOWN; no savepoint or independent P invented | [unknown capability](../examples/transaction-01-t01/capability_unknown/transaction-model.json) |

Additional negatives cover ambiguous managers, missing proxy configuration, JDK
proxy limitations, visibility, class/method precedence, unannotated intermediate
calls, repeated-call restoration, direct entry, async, reflection/dynamic calls,
complex control flow, lambdas, comment/string false calls and corrupted models.

PlantUML regions follow method nesting and carry L/P/S/SP labels as well as colors.
Physical BEGIN/END and SUSPEND/RESUME notes represent retained lifetime overlap
explicitly. Arbitrary crossing multi-lane resource regions cannot be represented
exactly as ordinary sequence `group` fragments; no such exact geometry is claimed.
In particular, an independent P2 inside a retained/suspended P1 method region is
not labelled as a nested savepoint. The JSON event trace is authoritative.

## Verification Results

| Verification | Result / scope |
|---|---|
| `python3 tests/transaction-boundaries.py -v` | PASS: 16 targeted tests, including all eight independent oracles |
| `python3 tests/mana-skill-factory.py -v` | PASS: 23 affected factory regressions; expected recipe statuses updated for T01 |
| `scripts/validate-repo.sh` | PASS; new helper/modules/entry point/tests are checked in existing validation |
| `tests/profile-skill-activation.sh` | PASS |
| Ruff lint / formatting and `git diff --check` | PASS |
| Real PlantUML syntax and SVG generation | PASS for all eight diagrams in regressions; all delivered `.puml` files also checked |
| CLI example generation / independent oracle comparison | PASS for eight examples |
| Target immutability | PASS for six fixture files before/after example generation; audit observations see external stage writes and no target writes |
| Native subprocess containment | PASS: all JDK argv use snapshots outside target, temp/cwd external; internal TMPDIR blocks before subprocess invocation |
| Candidate generation/validation | PASS; pending approval, untrusted/unregistered/non-executable |
| Broad Mana QA / remote CI / cross-platform / real Spring runtime | NOT RUN, outside this qualification |

Local tools: Amazon Corretto JDK 8u442; PlantUML 1.2024.8 from an existing local
jar, with headless mode. No dependencies/projects were downloaded. A local PNG
preview was visually inspected; its JVM emitted a nonfatal CodeCache warning
despite exit 0. Syntax/SVG checks succeeded; this is not a JVM performance claim.
Raw logs, tool hash, example hashes, source snapshots and final Git state are
retained in [the evidence receipt](MANA-TRANSACTION-01-T01-results.json).

## Limits And Governance

Positive resolution is intentionally restricted to explicit imports, concrete
stereotype beans/direct `@Autowired` fields, a single declared class-proxy config,
public zero-argument straight-line methods and source-declared concrete
DataSourceTransactionManager selection. No classpath/type attribution, full bean
discovery, interface/composed/inherited transaction resolution, XML/profile/advisor
resolution, async continuation, programmatic transactions or exception-path proof
is claimed. Such paths are blocked or represented as UNKNOWN, not guessed.

Budgets and normal-unwind assumptions are documented in the model contract.
Static syntax does not prove compilability, runtime dispatch, driver savepoints,
actual transaction identity or commit. Filesystem checks assume stable paths and
trusted JDK/framework components; they are not an OS sandbox for hostile tools.
Qualification is local macOS; remote CI/cross-platform/runtime outcomes remain open.

The [updated candidate](../examples/transaction-01-t01/candidate/SKILL.md) explicitly
states implemented subsets and prerequisites. Its manifest remains generated,
pending, nontrusted, unregistered and non-executable. The manual analyzer is a
framework helper authorized by explicit invocation, not execution/activation of
candidate instructions. Historical META-SKILL-00 reports/examples are unchanged;
their old exact-template candidates require regeneration for current validation.

## Next Phase

Review this bounded implementation and its assumptions before accepting it.
[T02 Resource & Lock Analysis](../roadmap/TRANSACTION-01-T02.md) is a proposal only;
no T02/T03 implementation or deadlock qualification is included here.
