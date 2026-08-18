# Story Start Scope Contract v2 Compatibility

## Development State

This additive bundle is publicly selectable in SS06 through the established
`story-start` profile. Migration is staged: v1 remains the default and v2 is
selected with `MANA_STORY_START_SCOPE_VERSION=v2` plus a project-local compact
context path in `MANA_STORY_START_CONTEXT`. No CLI style, profile name, runner
flag, legacy agent schema, or legacy Markdown meaning changes.

## Coexistence

- Existing Story Start Markdown artifacts remain readable by path under the
  active `.mana/features/**` or `.mana/sessions/**` workspace.
- Existing agent schemas under `agents/story-implementation-planner/` remain
  unchanged. They are v1-era workflow metadata, not aliases for this bundle.
- V2 JSON artifacts identify themselves with both a schema-specific
  `schemaVersion` string and `artifactVersion: 2`.
- A successful public v2 run writes additive JSON and deterministic Markdown
  under distinct `story-start-*-v2` filenames. It never overwrites
  `planning/implementation-plan.md` or another legacy artifact.
- `validation/story-start-scope-run-v2.json` is the cross-file publication
  marker and is written last. Consumers must verify its artifact references
  and IDs before treating sibling files as one completed run.
- A consumer that does not recognize a v2 `schemaVersion` must report the
  artifact as unsupported or render only safe generic metadata. It must never
  interpret v2 branches as cumulative v1 tasks.
- Mana Familiar is not required to read the Markdown representation and is not
  changed by this bundle.

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
corrective call and an explicit owner-review terminal state. SS06 publishes a
v2 plan only after both structural schema validation and the Scope Governor
pass. A failed or unsupported v2 artifact never falls back to a free-form
legacy plan. Provider and governor failures publish only a versioned run status,
an owner-review Markdown diagnostic, and—when available—the valid governance
report.

The public status separates `ownerReview` for a failed publication pipeline
from `planningReview` for a valid plan that still has open human decisions.
Future readers must preserve that distinction.

## Future Mana Familiar Fields

A future UI can rely on the stable v2 structures `readinessPrerequisites`,
`basePlan`, `requiredEnablers`, `conditionalBranches`, `branchGroups`,
`scenarioEstimates`, `decisionRegister`, `relatedFindings`,
`evidenceAndProvenance`, `validationStatus`, and the two review states in the
public run status. Branch relationships and selection rules must remain
explicit; no consumer may flatten them into one cumulative task list.
