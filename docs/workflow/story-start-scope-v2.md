# Story Start Scope v2

Story Start Scope v2 lets discovery inspect broadly without silently turning
every finding into story scope. It is available through the existing
`story-start` profile as a staged, versioned opt-in; the legacy v1 workflow
remains the default for compatibility.

## Run The Versioned Pipeline

Prepare a compact project-local context file matching
`mana.story-start.discovery-package/v1`. It must contain a stable `storyId`, a
`normalizedStory.summary`, at least one acceptance criterion, and only the
bounded story/repository context Discovery needs. Then keep the normal public
invocation and select v2 through the environment:

```bash
MANA_STORY_START_SCOPE_VERSION=v2 \
MANA_STORY_START_CONTEXT=.mana/features/PROJ-123/context/story-start-context.json \
./mana profile story-start --codex
```

The same variables work through `./mana cast story-start`. The context path
must resolve inside the target project. The provider calls are schema-bound;
Scope Triage and Planner receive compact structured artifacts rather than the
repository or an unclassified discovery dump.

Without `MANA_STORY_START_SCOPE_VERSION=v2`, the established v1 invocation and
artifact behavior are unchanged.

## Optional Analysis Trajectory Guard

TG06 can place an additive guard in front of Scope Triage at the real
Discovery provider-completion boundary:

```bash
MANA_STORY_START_SCOPE_VERSION=v2 \
MANA_STORY_START_CONTEXT=.mana/features/PROJ-123/context/story-start-context.json \
MANA_ANALYSIS_TRAJECTORY_MODE=shadow \
./mana profile story-start --codex
```

The default is `off`. `shadow` publishes a Mission Contract, Ledger,
deterministic recommendation, integration run, and compact evidence package
without changing control flow. Explicit `enforce` applies validated outcomes
and fails closed. On-track enforcement adds no checkpoint call. Optional
structured observation, checkpoint-input, and scope-approval files must be
project-local; see `docs/policies/analysis-trajectory-integration.md`.

The compact trajectory package is passed to Triage and Planner only as
provenance and limitations. It is not an implementation-task source and does
not replace Discovery, Scope Triage, Planner, or the deterministic Scope
Governor.

## What The Report Means

The generated Markdown follows this order:

1. story readiness;
2. base implementation plan;
3. required enablers;
4. conditional branches;
5. scenario estimates;
6. decisions required;
7. related findings not included in scope;
8. risks and optional improvements;
9. evidence and provenance;
10. validation and owner-review status.

The base plan contains only work directly justified by the story. A required
enabler is mandatory additional work with its own causal evidence and effort
delta. A conditional branch is work activated by a named decision and is not
part of the base estimate while that decision is open. Related defects, risks,
and optional improvements stay visibly out of scope.

Readiness engineering effort and calendar impact are always separate. Pending
approval does not become developer effort. Mutually exclusive branches are
shown as alternatives and are never summed. If an open material decision
changes scope, scenario estimates are shown and the report states that no
final committed estimate is available.

## Publication And Owner Review

After Discovery, Scope Triage, Planner, and Scope Governor pass, the host
publishes these additive files in the active workspace:

```text
evidence/story-start-discovery-v2.json
planning/story-start-scope-triage-v2.json
planning/story-start-implementation-plan-v2.json
planning/story-start-scope-v2.md
validation/story-start-scope-governance-v2.json
validation/story-start-scope-run-v2.json
```

`validation/story-start-scope-run-v2.json` is written last and is the
cross-file publication marker. It distinguishes pipeline failure review from a
valid plan that still needs a human decision. Every JSON root declares
`artifactVersion: 2` and an explicit `schemaVersion`; entity IDs remain
deterministic.

Provider or governor failure produces a versioned `needs_owner_review` status
and a usable diagnostic Markdown report. A failed plan is not published, no
free-form response is substituted, and at most one targeted correction call is
allowed.

## Compatibility

V2 never overwrites legacy filenames such as
`planning/implementation-plan.md`. Existing Markdown stays readable as-is, but
it is not reinterpreted as structured v2 data. A v1 reader must reject a v2
schema gracefully rather than flattening conditional branches into cumulative
tasks. See the contract-level details in
`contracts/story-start/scope-v2/COMPATIBILITY.md`.

Mana Familiar is not required: the deterministic Markdown report is the
immediate human interface. A future Familiar UI can use `basePlan`,
`requiredEnablers`, `conditionalBranches`, `branchGroups`,
`scenarioEstimates`, `decisionRegister`, `relatedFindings`,
`readinessPrerequisites`, and both review states in the public run status.
