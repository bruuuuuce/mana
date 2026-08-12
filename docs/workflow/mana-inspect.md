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
