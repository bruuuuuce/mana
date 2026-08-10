# Mana Learning Explorer consumer contract v0

Mana is the authoritative producer of Learning Journey artifacts. Mana Learning
Explorer is a separate desktop consumer maintained in the
`mana-learning-explorer` repository; no Flutter application code lives here.

## Stable producer boundary

The authoritative persistence model and schema are:

- `mana-learning-journey-v0.md`
- `mana-learning-journey-v0.schema.json`

For a selected project root, Mana stores Journey records under
`.mana/learning/journeys/<journey-id>/`. The supported consumer graph API is:

```bash
scripts/mana-journey.sh --project-root /path/to/project materialize <journey-id>
```

It validates the append-only records and emits deterministic
`mana.learning.graph/v1` JSON. Consumers must use that materialized graph
rather than parse or write individual Journey record files.

The Explorer may also call these producer-owned operations:

```bash
scripts/mana-concepts.sh --project-root /path/to/project labels \
  --journey <journey-id> --node <node-id> --json
scripts/mana-expand.sh --project-root /path/to/project request \
  --journey <journey-id> --node <node-id>
```

Mana owns IDs, record persistence, validation, evidence, concepts, and
expansion semantics. The Explorer owns rendering, navigation, source display,
and its own local UI preferences. It may watch a selected Journey directory
and read producer-declared diagram assets, but it never creates or changes
Journey records.

## Compatibility

Changes to `mana.learning.graph/v1`, the Journey schema, or the commands above
are producer compatibility changes. Update this document and the authoritative
schema with any such change, and coordinate a corresponding Explorer release.
The Explorer is launched with explicit `--project-root` and `--mana-root`
arguments, so it does not rely on Mana's internal repository layout.
