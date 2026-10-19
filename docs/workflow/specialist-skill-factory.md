# Specialist Skill Factory v1

MANA-META-SKILL-00 generates an evidence-backed candidate. The first supported
request is `transaction-analysis` for a Java/Spring Maven project. Transaction
analysis itself belongs to TRANSACTION-01 and is not implemented.

## Usage

Run from the Mana checkout. Use a canonical candidate path outside the analyzed
project, all discovery/configuration directories, and symlink aliases. The path
must not exist; existing candidates are never overwritten.

```sh
python3 scripts/mana-skill-factory.py generate \
  --project-root /absolute/project \
  --request transaction-analysis \
  --candidate-dir /private/tmp/transaction-candidate-01

python3 scripts/mana-skill-factory.py validate \
  --project-root /absolute/project \
  --candidate-dir /private/tmp/transaction-candidate-01
```

Exit 0 means a valid, untrusted, non-executable candidate with pending human
approval. Exit 2 means blocked generation/validation or invalid CLI input.
Success is JSON on stdout; failure diagnostics go to stderr. No environment,
project configuration, registry, index or profile is written by the helper.
The only persistent writes are the explicitly selected candidate directory and
any missing parent directories. Mana metadata validation uses an isolated,
automatically removed temporary directory.

### Temporary isolation (F01)

The factory selects the first nonempty `TMPDIR`, `TEMP`, or `TMP`; without these,
POSIX uses `/tmp`. Other platforms require an explicitly configured parent.
Selection never calls `tempfile.gettempdir()`, whose discovery can itself write
probe files. Relative paths resolve from the caller's working directory. Before
creating anything, the factory canonicalizes the project and selected parent,
resolves symlinks and rejects a parent inside the project or a discovery/configuration
surface. The parent must already exist; invalid or missing parents block with
exit 2 and a diagnostic naming the selected location, without fallback or mkdir.
External symlink aliases are used only through their validated canonical target.

The native validator receives an external staging directory as both cwd and
`TMPDIR`/`TEMP`/`TMP`. Shell startup variables `BASH_ENV` and `ENV` are removed for
that subprocess. No host-global temporary-directory setting is changed. Local
adapter imports suppress bytecode cache writes. These rules apply to both
generation and validation; cleanup is not the immutability proof.

## Workflow And Evidence Contract

1. Inventory at most 5,000 files, reading only `pom.xml` and `.java` files, with
   a 1 MiB per-file and 32 MiB total read budget. Hidden/generated/vendor paths
   and symlinks are excluded. Budget overflow blocks rather than yielding a
   positive result from incomplete detection.
2. Parse Maven XML without executing anything or resolving dependencies. Require
   a direct `org.springframework:spring-*` or
   `org.springframework.boot:spring-boot-*` dependency, with compile/runtime/provided
   scope, and at least one nonempty UTF-8 `.java` file under that module's
   `src/main/java/`. Record descriptor and representative Java file SHA-256 values
   and exact dependency coordinates. Maven comments, descriptions, dependency
   management, parents, test-only dependencies and another module's sources
   cannot establish applicability.
3. Select the sole supported request/domain pair and its curated contract from
   `templates/skill-factory/java-spring-transaction-analysis.md`. Unsupported
   requests or unproven technology block. No project text becomes instructions.
4. Select existing read-only Mana tool identifiers and a deliberately unavailable
   future `transaction-analyzer` dependency. Do not advertise implemented analysis
   or infer transaction-manager, proxy, savepoint or runtime capabilities.
5. Validate native metadata through `scripts/validate-skills.sh` in isolation,
   then validate the exact candidate content, dependency/limit declarations,
   generated trust and pending approval against the curated v1 contract.
6. Present `SKILL.md` and `candidate.json` to the accountable human. Registration
   and activation remain unavailable in this factory. Validation cannot approve
   a candidate. Changed source evidence, template or contract requires a fresh
   candidate and renewed review.

`candidate.json` declares schema `mana.skill-candidate/v1`, identity, request,
technology observations, source paths/hashes, knowledge references, tools,
applicability, offered/future capabilities, limits, verification criteria,
SKILL hash and approval/trust state. This version is a closed, curated contract:
validation recomputes the manifest from project evidence and rejects missing,
additional or changed fields, duplicate keys, changed Markdown and extra bundle
files. It is intentionally not a general arbitrary-skill validator.

## Factory / Adapter Boundary (F01)

`scripts/mana-skill-factory.py` owns bounded file inventory, request selection,
bundle generation, native validation, canonical output/temp paths, error handling
and pending/untrusted governance. It contains no Java/Spring recipe, template path
or specialist request constant.

`scripts/skill_factory/contracts.py` defines `SkillAdapter`: `skill_id`, `request`,
`template`, evidence filename/suffix filters, and `specialize(files)`. Requests
must select one adapter unambiguously; skill identifiers must be safe lowercase
hyphenated names of at most 63 characters. The factory
supplies bounded, read-only file bytes; the adapter must return exactly the
declared domain fields or reject applicability. These fields cover evidence,
technology claims, offered/future capabilities, tools, knowledge references,
prerequisites, limits and verification criteria. They cannot override lifecycle,
approval, registration, executability or trust fields owned by the factory.

The sole production adapter, `java_spring.py`, holds the existing Maven detection
and curated transaction recipe. `skill_factory/__init__.py` is a small static tuple
of trusted framework adapters. A future adapter can implement the protocol and
be added there without changing factory orchestration/validation. No discovery
or import from the analyzed project is allowed. A test-only second recipe uses
the same Java/Spring technology to exercise this seam; it adds no supported domain.

Generation is explicitly template based. Project-derived information remains
dependency/source observations and hashes; it is not dynamically generated
transaction knowledge. The candidate format and existing Java/Spring template
are unchanged.

## JSON Complexity Contract (F01)

Candidate JSON and generated manifests have three independent limits:

| Budget | Maximum | Reason |
|---|---|---|
| Encoded size | 1 MiB, inclusive | Preserves the existing per-file cap and bounds lexical/parser memory |
| Container depth | 32 open objects/arrays, inclusive | Well above the shallow candidate manifest; below Python parser/encoder recursion limits |
| Lexical complexity | 20,000 tokens, inclusive | Bounds collection/key/value work independently of file size |

An iterative preflight counts one token per string (including keys), scalar atom
and punctuation character (`{}[]:,`), excluding whitespace and string contents.
Escaped quotes/brackets inside strings do not affect nesting. Only then is the
standard JSON parser used, with duplicate keys and non-JSON constants rejected.
Malformed input and parser value/recursion failures produce a controlled blocked
diagnostic and exit 2, never an uncaught traceback. Limits apply before native
validation or candidate output writes; oversized generated manifests also block
before any staging/output creation. Existing valid manifests, including equivalent
JSON with whitespace up to the byte cap, remain compatible. Closed-contract
validation still rejects semantically changed fields even when JSON budgets pass.

## Governance And Existing Extensions

| Existing mechanism | Extension used |
|---|---|
| `skills/*/SKILL.md`, `scripts/validate-skills.sh` | Normal metadata for the factory and isolated validation for its candidate |
| `scripts/build-skill-index.sh`, `skills/index.yaml` | Only the factory is indexed; candidates are outside `skills/` |
| `scripts/mana-compile-profile.sh`, `scripts/lib/context-runtime.py` | Existing authoritative profile/skill allowlists; candidate requests stay undeclared |
| `docs/standards/agent-skill-output-standard.md` | Reviewable instructions, model routing, read/write effects and output conventions |
| `scripts/run-profile-v2.sh`, `scripts/lib/provider-dispatch.sh` | Existing LLM execution layer; no provider invocation needed for this deterministic vertical |
| `scripts/mana-learning.sh`, `scripts/mana-actions.py` | Existing candidate review is not human approval or skill promotion; no reuse of learning schemas as executable skills |
| `scripts/mana-verify.sh`, `scripts/lib/verification.sh`, `skills/*/verification.yaml` | Existing executable verification contract; factory candidates do not declare `capability: verification` or an executable spec |
| `docs/policies/verification-execution-policy.md` | `generated` trust is never executable in v1 |

The factory is standalone and can be selected explicitly; no existing profile
activation set is expanded. This is a generator extension, not another registry,
provider runner, approval service or qualification framework. Candidate artifacts
are not Verification Skill results: `valid` says nothing about transaction
analysis correctness, provider qualification or release readiness.

## Boundaries

Detection supports conventional Maven layout and direct declarations only.
Gradle, inherited-only/project-property dependency coordinates, activated profiles,
resolved versions and nonstandard roots are unsupported. Java file presence does
not establish compilability. The evidence inventory is not a semantic index or
complete project snapshot. There is no classpath resolution, call graph, method
identification, propagation computation, diagram rendering or runtime probe.

Filesystem checks guard normal local use, not hostile concurrent filesystem
replacement. Detection/validation should run against a stable checkout. The
validator and local toolchain are trusted framework components; setting their
temporary environment/cwd is not an OS sandbox for arbitrary hostile executables.
Write instrumentation in the existing regression suite observes parent filesystem
operations (including descriptor-relative cleanup) and actual temporary/cwd writes
from a controlled child before invoking the real validator. Qualification is local;
the instrumentation uses macOS descriptor paths or Linux `/proc/self/fd`.
The factory is not a system-wide policy preventing someone from manually installing
files through unrelated tools. Human review must precede any future manual
registration; this version has no supported installation path and approval alone
does not implement the missing analyzer.

## Verification

```sh
python3 tests/mana-skill-factory.py
scripts/validate-skills.sh
scripts/validate-output-standard.sh
scripts/validate-repo.sh
```

The focused suite uses the existing unittest/native validation path and CI job,
without new qualification infrastructure or network/model calls. The checked-in
[PetClinic example](../examples/mana-meta-skill-00/java-spring-transaction-analysis/SKILL.md)
is a generated review artifact outside discovery; see the
[delivery report](../reports/MANA-META-SKILL-00.md) for provenance and results.
