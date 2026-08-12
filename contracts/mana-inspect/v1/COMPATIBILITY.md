# Mana Inspect Contract Compatibility v1

Mana owns this bundle and the semantics of all artifact families. Consumers pin
`mana-inspect-contract/v1` and negotiate supported operations from
`mana.inspect.project/v1.operations`; they must not scan `.mana/` or reproduce
Mana shell logic.

## Versioning

- Additive fields and additive artifact kinds are allowed in v1 only when their
  meaning is independent of existing fields. Consumers must ignore unknown
  object fields and unknown artifact families, kinds, relation types, statuses,
  and payload fields while retaining their safe catalog summary.
- Removing, renaming, tightening the meaning of a field, changing an enum's
  existing meaning, or changing safety/identity behavior requires a new schema
  version and a new bundle directory.
- Mana keeps a released v1 contract available for at least two subsequent Mana
  minor releases and at least 90 days after a replacement is announced,
  whichever is longer. Security redaction may remove unsafe payload exposure
  earlier while preserving a machine-readable omission diagnostic.
- A client may support only `project` and `artifacts`; it must feature-detect
  `artifact` and `source`, disable unavailable views, and never treat missing
  detail/relations as evidence of safety.

## Error and Exit Model

Inspect stdout is machine-clean JSON on success. Diagnostics are stderr only.
Exit `0` means a valid response; `2` invalid input/not found/ambiguous lookup;
`3` unsupported contract; `4` malformed or unsafe workspace/source boundary;
and `5` internal failure. A client must display safe fallback state rather than
parse stderr as a contract.

## Vocabularies

Relation types are versioned strings. V1 emits only
`references-source/v1` from validated Journey anchors. It does not infer links
from prose or filenames. Source staleness is `fresh`, `stale`, `missing`,
`working_tree_only`, or `unknown`; it is never inferred from a recent mtime.

Catalog classes include `canonical`, `derived`, `ephemeral`, and `unknown`.
Unknown/malformed/quarantined entries are valid catalog outcomes. `latest`
aliases are intentionally omitted to avoid double counting a revision.

## Capability Negotiation

```json
{
  "required": ["project", "artifacts"],
  "optional": ["artifact", "source"],
  "acceptedSchemas": [
    "mana.inspect.project/v1",
    "mana.inspect.artifacts/v1",
    "mana.inspect.artifact/v1",
    "mana.inspect.source/v1"
  ]
}
```

Call `mana inspect project --json`, check `framework.compatibility` and
`operations`, then use only supported operations. Do not use an unrecognized
schema response as a partially compatible object.
