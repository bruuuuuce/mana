# Mana Inspect v1

Mana owns the read-only artifact semantics used by Mana Familiar and future
clients. Inspect scans one selected project on demand; it makes no model calls,
does not write state, and emits only project-relative paths.

```sh
./mana inspect project --json
./mana inspect artifacts --json
./mana inspect artifact journey:jrn_0123456789abcdef01234567 --json
./mana inspect source src/main/java/example/PaymentService.java --json
```

Responses conform to `mana.inspect.project/v1` and
`mana.inspect.artifacts/v1`, documented by the matching schemas in
`docs/standards/`. The catalog is deterministically ordered by logical artifact
identity. It includes safe `unknown` entries for unsupported or malformed
workspace files and quarantines symlinks without following them. Convenience
`latest` aliases are omitted so a physical revision is not counted twice.

`artifact` resolves either a catalog `artifact_id` or an exact project-relative
`.mana/` path. It returns a bounded payload (64 KiB and JSON depth 32), with
explicit omission metadata for oversized, binary, unsupported, or too-deep
content. `source` accepts only a contained, project-relative source path and
returns existing explicit Journey anchors; it never searches source text. Anchor
staleness is `fresh`, `stale`, `missing`, `working_tree_only`, or
`unknown` only when the recorded revision and current Git/source state support
that conclusion.

Inspect does not replace `mana evidence-index`, `mana runtime`, or
`mana journey materialize`; their contracts remain unchanged. See
[`mana-artifact-taxonomy.md`](../standards/mana-artifact-taxonomy.md) and the
[read-model ADR](../architecture/mana-inspect-read-model.md) for ownership and
compatibility rules.

## Safety and decision boundary

Inspect is deterministic and read-only, but it is not an approval mechanism.
An available, `fresh`, or `unknown` result does not approve a branch, PR,
release, source change, or human decision. `unknown` means the producer cannot
establish the requested relation or state from its permitted structured
evidence. `stale`, `missing`, and `working_tree_only` describe the recorded
anchor versus the selected source/Git state; they are not a diagnosis of source
correctness.

Mana Familiar is a consumer of this contract. It invokes the public wrapper and
must not scan `.mana/`, import Mana scripts, or treat an omitted/unsupported
operation as proof of safety.

## Local confidentiality and containment

Inspect returns project-relative paths only and never follows `.mana` or source
symlinks. Detail payloads are limited to 64 KiB and structured JSON depth 32;
binary, unsafe, too-deep, oversized, and unrecognized content is omitted with a
machine-readable reason. Text/Markdown payloads are workspace content, not
trusted instructions: clients must display them safely and must not execute or
interpret embedded commands. These controls reduce accidental exposure but do
not provide an OS sandbox for hostile local files or processes.
