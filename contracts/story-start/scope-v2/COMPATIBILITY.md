# Story Start Scope Contract v2 Compatibility

## Development State

This bundle is an additive v2 contract created in SS01 with internal-only
Discovery, Scope Triage, Implementation Planner, and host Scope Governor added
in SS02 through SS05. It does not change `profiles/story-start.yaml`,
`scripts/run-profile.sh`, the current public Story Implementation Planner agent,
its permissive input/output schemas, current Markdown filenames, or public
invocation behavior.

Until SS06, v2 artifacts are internal phase outputs and fixture material only;
no public command selects or publishes them. A current Story Start run
continues to produce the existing unversioned Markdown files. No current
consumer is allowed to infer that those Markdown files conform to v2.

## Coexistence

- Existing Story Start Markdown artifacts remain readable by path under the
  active `.mana/features/**` or `.mana/sessions/**` workspace.
- Existing agent schemas under `agents/story-implementation-planner/` remain
  unchanged. They are v1-era workflow metadata, not aliases for this bundle.
- V2 JSON artifacts identify themselves with both a schema-specific
  `schemaVersion` string and `artifactVersion: 2`.
- During SS01-SS05, no public command writes a v2 artifact.
- SS06 must publish v2 JSON alongside a deterministic human-readable report or
  provide an explicit compatibility adapter. It must not overwrite a legacy
  artifact and silently change its meaning.
- A consumer that does not recognize a v2 `schemaVersion` must report the
  artifact as unsupported or render only safe generic metadata. It must never
  interpret v2 branches as cumulative v1 tasks.
- Mana Familiar is not required to read the eventual Markdown representation
  and is not changed by this bundle.

## Versioning Policy

The directory name and each root `schemaVersion` are the contract boundary.
Adding a new optional field whose meaning is independent of existing fields may
be considered for v2. Removing or renaming a field, weakening an invariant,
changing an existing enum meaning, changing identity derivation, or changing
estimate arithmetic requires a new contract directory and schema version.

Unknown object fields are rejected by v2 schemas. A producer must negotiate a
new schema instead of sending undeclared fields. Unknown enum values are also
rejected; consumers must not map them to the closest known meaning.

## Publication Boundary

Schema validation alone is not publication approval. SS05 adds deterministic
reference, state, inclusion, and arithmetic validation with at most one
corrective call and an explicit owner-review terminal state. SS06 may publish a
v2 plan only after both structural schema validation and the Scope Governor
pass. A failed or unsupported v2 artifact must not fall back silently to a
free-form legacy plan.
