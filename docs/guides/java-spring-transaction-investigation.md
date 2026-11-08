# Java/Spring transaction investigation

## Functional baseline and implementation plan

MANA already has separate T01 source analysis and transaction rendering, S01
resource timelines, and S02/VIS structured wait analysis. The unified workflow
composes those implementations rather than creating another propagation or
resource model. Java source supplies selected methods, annotations, supported
call sites, literal JDBC SQL, and source hashes. The user supplies initial runtime
state and any proxy-entry or manager-capability assumptions; absent those inputs,
the workflow retains UNKNOWN state and evaluates both proxy-entry alternatives.

Implementation sequence: validate and snapshot the project with T01; build and
validate S01 from the same extracted Java facts; render the transaction sequence;
optionally validate caller-supplied S02 timelines and scenario premises and reuse
VIS; then publish a private report and machine-readable evidence directory. The
existing renderer is reused. Standard injected `JdbcTemplate` calls, dynamic SQL,
datasource enlistment and lock behavior are documented limitations rather than new
semantic contracts.

Use the standalone workflow when analyzing an external Java/Spring project:

```sh
python3 scripts/mana-investigate-transactions.py \
  --project-root ./project \
  --entry 'com.example.OrderService#process()'
```

Repeat `--entry` up to eight times to compare selected paths:

```sh
python3 scripts/mana-investigate-transactions.py \
  --project-root ./project \
  --entry 'com.example.OrderService#process()' \
  --entry 'com.example.OrderService#retry()'
```

Each entry is analyzed as a separate conditional scenario. Its transaction IDs
are local to that entry. The report compares coverage, while `entries.json` maps
each selected entry to its own validated model, timeline, and diagram files.
The shared `context.json` applies to every selected entry; use separate invocations
when paths require different scenario assumptions.

The command validates the supported Maven/Spring applicability boundary, parses a
bounded Java source snapshot, reconstructs the supported T01 call path, projects
the S01 resource timeline, and publishes a Markdown report, PlantUML sequence,
validated JSON models, and source/context hashes. It never builds or executes the
target project. By default it creates a fresh mode-0700 directory under the system
temporary directory. `--output-dir PATH` selects a fresh canonical external path;
it must not be inside the target, exist already, or resolve through symlinks.

Supply known scenario premises explicitly:

```sh
python3 scripts/mana-investigate-transactions.py \
  --project-root ./project \
  --context ./investigation-context.json \
  --entry 'com.example.OrderService#process()' \
  --output-dir /private/tmp/order-investigation
```

Context values are conditional assumptions, not runtime evidence. Without a
context file, the workflow runs both `entryThroughProxy=false` and
`entryThroughProxy=true` scenarios because v1 has no UNKNOWN value for that
boolean. Initial transaction state and manager capabilities remain unknown. The
report labels both alternatives; neither establishes live proxy traversal. The
validated proxy-true model, timeline, and effective context are published as
separate per-entry artifacts and indexed with their SHA-256 hashes.

When you already have explicit S02 inputs, the same invocation can reuse them for
conditional wait analysis and VIS source diagrams:

```sh
python3 scripts/mana-investigate-transactions.py \
  --project-root ./project \
  --entry 'com.example.OrderService#process()' \
  --wait-scenario ./scenario.json \
  --wait-timeline alpha=./alpha-resource-timeline.json \
  --wait-timeline beta=./beta-resource-timeline.json
```

Repeat `--wait-timeline ID=PATH` for every sidecar participant input. S02 validates
the exact-byte hashes and premises in `scenario.json`; this validates only the
supplied external timeline inputs. It does not bind them to the selected source
paths or entries, and its result is labeled `UNBOUND_EXTERNAL_SCENARIO`. The
workflow does not infer or fabricate participant schedules from the selected
entry or SQL text. It emits
`wait-*` S02 artifacts and `vis-*.puml` VIS diagrams. Their claims remain
conditional and runtime behavior remains NOT RUN.

## Output

- `report.md` explains the entry, selected call tree, symbolic physical identities,
  propagation/interception, recognized resource operations, uncertainty, and
  developer verification steps.
- `sequence.puml` is generated through the existing transaction renderer. Its
  labels and legend explain physical versus logical scope and use blue for an
  independent context, green for inherited context, yellow for savepoints, gray
  for no transaction, and red for unknown regions. SVG is added only if a local
  `plantuml` executable succeeds; `.puml` is always retained.
- `transaction-model.json` and `resource-timeline.json` are validated outputs of
  the existing T01 and S01 implementations. `evidence.json` records the source
  revision, source SHA-256 values, and context digest. `context.json` preserves the
  effective scenario input.

Source facts describe recognized syntax and conditional paths. They do not prove
that Spring interception occurred, a JDBC operation executed or enlisted in a
transaction, a lock was acquired, or a deadlock occurred. The current S01 JDBC
binding limit leaves standard injected `JdbcTemplate` calls at unresolved T01
frontiers; the investigation reports these observations and uncertainty rather
than expanding the resource-leaf contract. S02/VIS diagrams require explicit
structured premises and are not synthesized from matching SQL names.

## Existing scenario coverage

The public T01, S01, S02 and VIS A/B/C examples remain the semantic regression
corpus. Run the focused local suites with:

```sh
python3 tests/transaction-transition-contract.py
python3 tests/resource-timeline.py
python3 tests/wait-dependencies.py
python3 tests/transaction-visualization.py
python3 tests/transaction-investigation-cli.py
```

The synthetic fixture at `tests/fixtures/transaction-investigation` adds joined,
independent, nested, self-invocation, opposite source resource orders, and dynamic
SQL cases. Its expected outcomes are authored separately from analyzer output.
Automated coverage exercises REQUIRED inheritance, conditional REQUIRES_NEW
suspension, NESTED savepoint identity, self-invocation bypass, unknown dynamic SQL,
an unresolved entry, conservative proxy alternatives, and partial source coverage.

## Manual workflow comparison

On the same `process()` fixture with the same explicit context, the manual static
workflow runs T01 and S01 separately; the unified workflow runs once and also
writes the report and machine evidence. Three warm local repetitions on macOS
Python 3 measured:

| Workflow | Commands | Elapsed seconds | Median |
|---|---:|---|---:|
| Unified report, T01, S01, and transaction sequence | 1 | 0.612, 0.592, 0.585 | 0.592 |
| Manual T01 then S01 artifact generation | 2 | 1.171, 1.171, 1.148 | 1.171 |

The manual sequence has no existing report generator, so report-writing time is
not included and no time-saving claim is made for the human synthesis step. This
is command/runtime evidence on one bounded fixture, not a general performance or
correctness superiority claim. Independently specified correctness expectations
are in the fixture's `expected-outcomes.json`; the regression test checks the
selected supported outcomes and explicitly asserts unresolved coverage.
