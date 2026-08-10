# Verification Execution Policy

`mana verify` is a deterministic evidence collector. It never starts a model
runner and never accepts a free-form executable command.

## Trust Origins

- `framework_declared`: fixed Mana adapter logic; executable after preflight.
- `project_approved`: executable only through matching catalog, environment,
  and effect gates.
- `derived`: may be proposed, but is blocked until it matches an approved
  structured action.
- `repository_script`: repository code execution; provenance and effects must
  be explicit.
- `generated`: never executable in v1.

The Java adapter may use an approved, runnable, local `maven-unit-test` or
`gradle-unit-test` testbook entry only after explicit skill invocation. The
entry must be unique and match the expected unit kind, manifest source,
discovery origin, prerequisite, safety, timeout, environment, and fixed command
shape. Mana validates the command for identity but constructs argv itself; it
never evaluates catalog text. Active-workspace catalogs must resolve below the
project's `.mana` directory. This stricter verifier rule does not change manual
`run-testbook.sh` compatibility.

## Effects

V1 distinguishes source-tree mutation, Mana evidence writes, local build/cache
writes, isolated test external state, and network use. The vocabulary is not a
general filesystem policy language. Existing `execution_mode: read|write`
remains the compatibility summary.

Tests and build tools are writes even when source mutation is forbidden.
Verification snapshots tracked file contents and source-like untracked paths
before execution. Unexpected new mutation is recorded, remaining checks stop,
and Mana never resets, deletes, repairs, or hides the change.

Java builds conservatively declare local build writes, possible isolated test
state writes, and possible network access. V1 records these effects and requires
explicit invocation; it does not claim to sandbox Maven or Gradle internals.
Approved repository wrappers run without an OS sandbox. The bounded executor
terminates their process group, but a deliberately detached process can escape
v1 containment; repository-script evidence records this limitation explicitly.

## Evidence and Judgment

Exit codes, parser diagnostics, eval results, durations, provenance, effects,
and bounded logs are evidence. Reviewer findings, severity, merge readiness,
and human approval are outside verification. Raw stdout and stderr artifacts
are capped at 16 KiB each, may contain unredacted command output, and are stored
with owner-only permissions. Result excerpts redact common credential forms.
Runtime events carry compact metadata and artifact references, never raw output.
