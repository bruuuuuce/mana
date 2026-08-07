# Verification Skills

Verification Skills are normal Mana skills with an optional deterministic
contract beside `SKILL.md`:

```yaml
capability: verification
verification_spec: verification.yaml
```

The contract uses JSON syntax, which is valid YAML 1.2. This lets Mana validate
every executable field strictly with `jq`; executable authorization is never
parsed from Markdown prose. Contracts are capped at 64 KiB and duplicate JSON
keys, excessive nesting, general-YAML syntax, and unknown fields are rejected.

The lifecycle boundary is
`implementation → verification evidence → reviewer finding → human judgment`.
Verification selects applicable skills from the existing generated skill
index, executes fixed Mana adapters, and writes structured evidence. It does
not invoke Codex, Claude, OpenCode, Junie, or another model. It does not assign
severity, recommend merge/readiness, repair files, retry, or learn.

## CLI

```sh
mana verify
mana verify --skill shell-syntax-verification
mana verify --list
mana verify --dry-run --explain
mana verify --json
```

`--skill` is repeatable and narrows selection, but never bypasses applicability,
trust, environment, effects, or approval gates. `--dry-run` performs no Mana
workspace or runtime writes. Automatic selection occurs only after a human
invokes `mana verify`; it is not a background trigger.

## V1 Vocabulary

Applicability supports only repository availability, changed extensions,
changed path globs, required repository evidence paths, and explicit
invocation. Checks use only the registered `bash_syntax`, `mana_eval`, and
`java_approved_test` adapters. Unknown fields, predicates, adapters, effects,
and result states fail repository validation.

Results use `passed`, `failed`, `blocked`, `partial`, and `inconclusive`.
`not_applicable` is a selection result only. A failed check is evidence, not an
automatic delivery blocker.

## Initial Skills

- `shell-syntax-verification`: `bash -n` once per changed shell file.
- `mana-governance-regression-verification`: bounded existing Mana eval
  scenarios, without reimplementing eval assertions.
- `java-targeted-build-verification`: fixed Maven/Gradle test argv only when a
  matching local testbook entry is complete, uniquely identified, approved,
  runnable, and explicitly selected with `--skill`; otherwise blocked.

Evidence is stored at
`.mana/<workspace>/evidence/verification/<run-id>/`. Runtime audit and delivery
evidence remain separate and link by execution/run identifiers.

Framework maxima are five automatically selected skills, twenty checks, fifteen
minutes total, 900 seconds per check, and 16 KiB each for persisted stdout and
stderr. The executor drains excess output without retaining it and terminates
the complete child process group on timeout. Skill contracts may tighten these
values. There are no retries and an identical execution fingerprint executes
only once per run.

Repair loops, model-assisted verification, cross-run caching, skill learning,
and automatic promotion are not implemented.
