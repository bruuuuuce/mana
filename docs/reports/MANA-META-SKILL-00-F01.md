# MANA-META-SKILL-00-F01 — Foundation Remediation

## Verdict

**FIX_READY_FOR_REVIEW.** Local bounded verification completed on 2026-10-19.
All three R1 findings are addressed. This is remediation evidence, not acceptance
of TRANSACTION-01 or approval of any generated skill. Historical META-SKILL-00/R1
reports and receipts remain unchanged.

## Scope And Preservation

Branch remains `feature/mana-meta-skill-00`, HEAD
`ad8730ebe70f494ac24a80fbf32fcf2b30cdef35`; index remains empty. Before editing,
all 17 current work files (the 15 original files plus two R1 reports) were copied
and hashed outside the checkout. Only four existing files change in F01:
factory, existing test suite, repository validator and factory workflow document.
Thirteen initial files are byte-identical, including both R1 artifacts, original
delivery report, PetClinic example/provenance, specialist template, skill/index,
CI/suite wiring and TRANSACTION-01 proposal. No original file is deleted or loses
its executable mode. The 12 original test method ASTs are unchanged.

The [F01 diff](MANA-META-SKILL-00-F01.patch) compares implementation/tests/workflow
with the saved **uncommitted F01 input**, rather than Git HEAD, and includes the
three new adapter package files. [Results](MANA-META-SKILL-00-F01-results.json)
bind checks to file hashes, preserve pre-fix reproduction evidence and record
project immutability. No commit, merge, push, new worktree, Familiar or REL-01/A
change was made.

## Corrections

| Finding | Remediation and evidence |
|---|---|
| F01-A / temporary isolation | Resolve project and selected temp parent before writing or using `TemporaryDirectory`; reject target containment, missing parents, unresolved symlinks and discovery paths. Explicit parent selection avoids `gettempdir()` write probes. Apply to generate/validate and programmatic calls. |
| Subprocess temporary writes | Native validator gets canonical external staging as cwd and all three temp variables; shell startup variables are removed for that invocation. Host-global environment is untouched. Controlled child writes exercise actual temp/cwd paths before running the real validator. |
| F01-B / adapter boundary | Generic factory retains inventory/budgets, orchestration, validation, paths, governance and errors. Static `SkillAdapter` protocol/tuple delegates file filters, applicability, evidence, template and domain declarations to `JavaSpringAdapter`. |
| F01-C / JSON recursion | Iterative lexical budgets run before `json.loads`; malformed/value/recursion failures become blocked diagnostics, exit 2. Parse/contract failures precede staging/output creation. Generated manifests receive the same limits before writing. |

The old temporary-write and 4,011-byte recursion defects were reproduced only
on the existing disposable Spring fixture before editing; the latter failed in
`json.loads` with uncaught `RecursionError`. No unsafe reproduction used PetClinic.

Adapter additions require a trusted implementation and one static tuple entry,
without changing factory core. A test-only alternate recipe for the **same**
Java/Spring technology exercises generation and validation through that boundary.
Unsafe adapter identifiers and attempts to override governance fields block
before writing. Production still has exactly one adapter and one specialist
request. This remains a curated template generator with project observations,
not dynamic semantic knowledge generation.

## Complexity Limits

| Input budget | Maximum and boundary checks |
|---|---|
| UTF-8 JSON size | 1 MiB inclusive; valid candidate with trailing whitespace at the cap passes, cap + 1 blocks |
| Object/array nesting | 32 inclusive; depth 32 parses, depth 33 and the original depth-2000 payload block |
| Lexical complexity | 20,000 tokens; 19,999-token array parses, 20,001-token array blocks |

Tokens count strings/keys, scalar atoms and punctuation, excluding whitespace
and quoted contents. These independent budgets bound memory/collection work and
keep recursion far below parser/encoder limits for the shallow candidate contract.
Quoted brackets/escaped quotes preserve compatibility; malformed JSON, duplicate
keys and non-JSON constants block. No global recursion limit is changed. Existing
valid Java/Spring manifests retain the same schema, contents and bytes.

## Verification Results

| Check | Result |
|---|---|
| Existing 12 regressions + 11 F01 regressions | PASS — 23 tests, exit 0 |
| Native repository validation | PASS, exit 0, including explicit presence/compilation of new adapter modules |
| Existing profile activation suite | PASS, exit 0 |
| Ruff lint and format check | PASS, exit 0 each |
| Generated skill index and diff whitespace check | PASS |
| Temp paths | PASS: external, relative, spaces, external symlink, internal symlink, unresolved loop and missing parent; both generate/validate reject unsafe destinations before any observed write/subprocess |
| Pre-output failures | PASS: unsafe temp, native validation failure, unsupported request/technology, unsafe adapter/contract, pathological generated JSON; no partial candidate |
| Native subprocess effects | PASS: real controlled child temp/cwd writes remain external; target shell-startup sentinel stays unexecuted |
| Approval/registration/activation | Existing negative tests PASS; candidate state remains pending/generated, all trust/registration/execution flags false |
| Full zero-token suite / remote CI / cross-platform qualification | NOT RUN — no general QA campaign |

Python audit instrumentation observes write opens, directory creation, removal,
rename/link operations and descriptor-relative cleanup paths. Unsafe-parent tests
assert **zero attempted write operations**, not just final snapshot equality.
Positive tests observe external writes, preventing an inert observer from passing.
The child probe performs actual writes through `TMPDIR`, `TEMP`, `TMP` and cwd,
then executes the existing validator. It is confined to disposable test resources.

PetClinic at `500158f732419217507c7656904b8e6aa1bcc0d6` remains Git-clean and
unchanged across 132 files; digest remains
`7cd602986575faa0589f0b9e2177c45ecd682ceae6fd97d04666c0da36b91851`.
Generation/validation observe 31 external factory write operations and **zero**
target writes. Both candidate files match the delivered example byte-for-byte;
the delivered example also validates. The alternative Spring fixture remains
unchanged across two files, likewise with zero observed target writes. An
unsupported dependency group blocks without output or any observed writes.

## Residual Limits And Handoff

Checks assume a stable filesystem and trusted framework adapters/local tools;
they are not an OS sandbox for arbitrary hostile executables or concurrent path
replacement. Descriptor observation was exercised locally on macOS; Linux
`/proc/self/fd` instrumentation and other platforms are not qualified by this run.
Detection still supports only conventional Maven/direct Spring declarations;
there is no dependency resolution, transaction analysis or diagram generation.

Next R1 should review the three corrections and these focused regressions,
including temp-write observation and candidate byte compatibility. No repeated
general architecture reconnaissance is needed. Candidate approval/activation and
TRANSACTION-01 remain pending and outside this delivery.
