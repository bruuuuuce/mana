# C00 Mana–Familiar Inspect Compatibility Matrix

Validated contract owner: **Mana**. Consumer: **Mana Familiar**. This matrix
references the canonical bundle rather than duplicating its schemas.

| Contract | Owner | Producer support | Familiar support | Required consumer behavior | Fixture |
|---|---|---|---|---|---|
| `mana.inspect.project/v1` | Mana | M02 | v1 | Require exact schema; negotiate operations | `no-mana-project.json`, `minimal-project.json` |
| `mana.inspect.artifacts/v1` | Mana | M02 | v1 | Render recognized entries; keep partial/unknown state safe | `mixed-artifacts.json` |
| `mana.inspect.artifact/v1` | Mana | M03 | v1 optional | Request only when advertised; safely omit unsupported payloads | consumer parser fixtures |
| `mana.inspect.source/v1` | Mana | M03 | v1 optional | Render explicit anchor relations and conservative staleness | `stale-source.json`, `missing-source.json` |

## Compatibility Rules

- Mana is the sole owner of schema semantics, artifact scanning, IDs, and
  source-relation derivation. Familiar invokes public producer operations,
  parses responses, and never copies `scripts/` or scans `.mana/`.
- Clients accept additive unknown fields/types by retaining or safely ignoring
  them. An unknown top-level schema is an explicit unsupported state.
- A client that supports only project/catalog disables detail/source UI rather
  than guessing compatibility. Missing relation coverage is `unknown`, not
  evidence that no relation exists.
- Non-zero producer exits are transport/command failures. Clients never parse
  stderr as a response contract.
- The producer retains v1 under the deprecation policy in
  [the canonical bundle](../../contracts/mana-inspect/v1/COMPATIBILITY.md).

## C00 Gate

Run from Mana when the sibling is available:

    scripts/verify-inspect-consumer-compatibility.sh --familiar-root /path/to/mana-familiar

The gate validates the copied-bundle-safe producer contract, confirms Familiar's
ownership/no-parser declarations and four typed schema identifiers, then runs
Familiar's inspect parser/model tests. It is deterministic, has zero model
calls, does no network operation, and does not write a target project's
`.mana/` workspace.

F02 may proceed when this command passes against the intended Familiar branch.
