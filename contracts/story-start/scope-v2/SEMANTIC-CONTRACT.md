# Mana Story Start Scope Contract v2

## Status

`internal_only`. SS01 defines the machine-readable Story Start Scope v2
structures; SS02 through SS05 implement internal Discovery, Scope Triage,
Implementation Planner, and deterministic Scope Governor phases. Rendering and
public runtime selection remain inactive until SS06.

## Product Principle

Discovery may be exhaustive. Scope must be justified. Expansion must be
explicit. Humans decide.

The contract separates observed information from committed work so that a
repository finding cannot become story scope merely because it was found.

## Artifact Family

Every root artifact has:

- an exact `schemaVersion`, for example
  `mana.story-start.discovery-inventory/v2`;
- `artifactVersion: 2`;
- a stable artifact ID with a type prefix and SHA-256 identity;
- a stable story reference;
- a structured validation and owner-review state.

The bundle contains these root schemas:

| Artifact | Schema | Responsibility |
|---|---|---|
| Discovery inventory | `schemas/discovery-inventory.schema.json` | Neutral acceptance criteria, constraints, evidence, typed findings, open questions, decisions, and provenance; no tasks or estimates |
| Scope triage | `schemas/scope-triage.schema.json` | Classification and inclusion/exclusion reasoning; no implementation plan |
| Compact planning context | `schemas/planning-context.schema.json` | Host-derived AC, constraint, evidence, and provenance subset; no raw findings |
| Governance report | `schemas/governance-report.schema.json` | Deterministic structural/semantic violations, bounded correction outcome, and publication/owner-review state |
| Decision register | `schemas/decision-register.schema.json` | Open/resolved decisions and explicit options |
| Implementation plan | `schemas/implementation-plan.schema.json` | Base tasks, enablers, branches, readiness, approved expansions, related findings, and scenario estimates in separate structures |
| Scenario estimates | `schemas/scenario-estimates.schema.json` | Base, mandatory, conditional, and approved-expansion contributions with decision-sensitive finality |
| Provenance | `schemas/provenance.schema.json` | Bounded source references and evidence links |
| Shared definitions | `schemas/common.schema.json` | Strict reusable entities and value objects |

## Stable Identity Rules

Entity IDs use a semantic type prefix plus a lowercase 64-character SHA-256
digest, for example `ev_<sha256>` or `decision_<sha256>`. Producers derive the
digest from canonical JSON containing only identity-bearing semantic fields:

1. normalize strings according to the source contract without inventing text;
2. sort object keys lexically;
3. preserve ordered arrays and sort set-valued arrays lexically;
4. exclude timestamps, provider/model identity, confidence, validation state,
   mutable status, and display-only wording unless the wording is the source
   identity itself;
5. hash the UTF-8 canonical JSON with SHA-256;
6. add the entity prefix outside the hash.

Equivalent semantic inputs therefore produce the same ID. A model may propose
content but is not trusted to mint or validate deterministic IDs. SS02-SS04
normalizers derive canonical entity IDs; SS05 verifies artifact identities,
duplicate IDs, and cross-artifact reference integrity because JSON Schema
cannot prove those relations across documents.

## Scope Classifications

| Category | Meaning | Minimum evidence | Base plan | Engineering effort | Calendar impact |
|---|---|---|---|---|---|
| `VERIFIED_FACT` | Concrete observed/reported repository, story, branch, configuration, contract, or behavior evidence. It is information, not work. | At least one evidence reference. Observed versus inferred status remains explicit. | Never by itself. | None by itself. A separate classified change may carry effort. | None by itself. |
| `CORE_SCOPE` | Work directly required by an approved acceptance criterion or explicit mandatory story constraint. | At least one AC or mandatory-constraint reference plus evidence used to plan the task. | Eligible. Base tasks declare `originCategory: CORE_SCOPE`. | Yes, as `base_effort`. | Only through a separate readiness/calendar record, never the task estimate. |
| `REQUIRED_ENABLER` | Additional work not directly requested but causally necessary to satisfy an AC, prevent a story-introduced/aggravated regression, or meet a mandatory security, compliance, authorization, or data-integrity constraint. | Evidence plus at least one AC or mandatory-constraint reference and a mandatory-reason code. | Never; it has its own section. | Yes, as `mandatory_delta`. | Only through a separate readiness record if applicable. |
| `CONDITIONAL_SCOPE` | Work needed only under a decision, assumption, or external-contract outcome. | Evidence, an explicit decision reference, and a human-readable condition. | Never while conditional. | Yes, only as a `conditional_delta` inside a branch/scenario. | Separate if the condition also causes elapsed delay. |
| `READINESS_PREREQUISITE` | A condition required before implementation or before trusting the plan, such as branch alignment, approval, ownership, or external-contract availability. | Evidence, owner, status, engineering-effort object, and distinct calendar-impact object. | Never. | Only when concrete technical preparation is required; zero is valid. | Yes, known, none, or explicitly unknown. |
| `RELATED_DEFECT` | A real pre-existing issue that is independent, not required by an AC, not introduced/aggravated by the story, and separately remediable. | Evidence proving the defect and its pre-existing/independent causality. | Never. | Not in story effort unless a separate human scope-expansion record approves additional work. | Follow-up lead time may be reported outside story estimates. |
| `RISK_ONLY` | Relevant uncertainty with no certain implementation work yet. | Evidence or an explicit evidence gap, likelihood/impact rationale, and owner when known. | Never. | None until reclassified with new evidence or resolved by a decision. | May be described qualitatively; it is not an engineering estimate. |
| `OPTIONAL_IMPROVEMENT` | Useful cleanup, refactoring, observability, hardening, or architecture improvement not necessary for the story. | Evidence and an explanation that no AC or mandatory constraint requires it. | Never. | Excluded from story effort unless separately approved through scope expansion. | Excluded from story readiness by default. |

`includedInBasePlan: true` is schema-legal only for `CORE_SCOPE`. Being
`CORE_SCOPE` makes a classification eligible; it does not itself create a task.
Task origin and referenced classification are checked together by SS05.

## Promotion And Causality Rules

A pre-existing issue may become mandatory only when at least one of these
causal claims is evidenced:

1. an approved AC fails without the remediation;
2. the story introduces a regression unless the remediation is performed;
3. the story materially aggravates the existing issue;
4. a mandatory security, compliance, authorization, or data-integrity
   constraint fails without the remediation.

The issue remains `pre_existing` in evidence and causality fields. Mandatory
status does not rewrite its history. It becomes a `REQUIRED_ENABLER`, stays out
of `basePlan`, and contributes a separately visible `mandatory_delta`.

A defect introduced directly by the story is story work. Work directly
implementing an AC is `CORE_SCOPE`; additional regression-prevention work that
is causally necessary but not directly requested is `REQUIRED_ENABLER` with
`mandatoryReason: story_regression_prevention`. An existing issue materially
aggravated by the story uses `mandatoryReason: aggravated_defect_remediation`.

Security, compliance, authorization, and data-integrity obligations are
represented as `mandatoryConstraint` records. They require provenance and may
make pre-existing remediation a `REQUIRED_ENABLER`; the producer must cite the
constraint and evidence rather than use a generic “safer” rationale.

## Human Scope Expansion Without Rewriting History

Human expansion is an append-only `scopeExpansion` record. It references:

- the original classification;
- a human-owned decision;
- approval evidence;
- status and resulting work references.

The original `RELATED_DEFECT`, `RISK_ONLY`, or `OPTIONAL_IMPROVEMENT`
classification remains unchanged and excluded from the base plan. Approved
additional work appears in `approvedScopeExpansions`, outside `basePlan` and
`requiredEnablers`, with an `approved_scope_delta`. This distinguishes “the
story originally required it” from “a human explicitly expanded scope.” A
later rejection or superseding decision adds another decision/evidence record;
it does not mutate the historical classification.

## Structured Entities

1. **Acceptance criterion:** stable ID, source key, exact text, approval state,
   and provenance.
2. **Evidence record:** epistemic state, capability state, pre-existing state,
   bounded summary, and provenance IDs.
3. **Finding:** typed, evidence-backed observation (fact, configuration,
   constraint, defect, risk, ambiguity, readiness, evidence gap, or optional
   opportunity) with causality, owner, AC/constraint links, and optional
   decision links.
4. **Decision and options:** owner, question, materiality, status, options, and
   selected option only when resolved.
5. **Scope classification:** category, finding/evidence links, inclusion flag,
   rationale, AC/constraint links, condition/decision for conditional work,
   mandatory reason for enablers, suggested owner, and a structural promotion
   assessment for `CORE_SCOPE` or `REQUIRED_ENABLER`.
6. **Base-plan task:** `CORE_SCOPE` origin, AC/constraint references, evidence,
   direct provenance, source targets, tests, and base effort.
7. **Required enabler:** mandatory cause, evidence, AC/constraint references,
   tasks, and mandatory delta.
8. **Conditional branch:** explicit condition, decision and decision option,
   relationship, group, tasks, and conditional delta.
9. **Branch group:** branch references plus `mutually_exclusive`, `combinable`,
   or `dependent` relationship and `exactly_one`, `zero_or_one`, or
   `all_applicable` selection rule.
10. **Readiness prerequisite:** owner/status, evidence, separate engineering
    effort, and separate calendar impact.
11. **Related finding:** excluded classification, evidence, owner/follow-up,
    and explicit `excludedFromBasePlan: true`.
12. **Effort range and confidence:** unit, non-negative lower bound,
    non-negative additional uncertainty, confidence, and rationale.
13. **Calendar impact:** distinct `none`, `known`, or `unknown` object in
    elapsed hours, never person-hours.
14. **Scenario estimate:** labeled contributions, selected branch refs,
    engineering range, and scenario finality.
15. **Validation/owner-review status:** schema and semantic validation states,
    violation codes, review state, owner, and reason.
16. **Artifact/schema version metadata:** exact root schema string,
    `artifactVersion: 2`, typed artifact ID, and story ID.
17. **Open question:** evidence-backed unknown with optional AC relation,
   suggested owner, and an explicit decision-needed flag.
18. **Scope expansion:** append-only human decision linking original
    classification to separately estimated additional work.
19. **Decision option group:** stable decision/options relationship with an
    explicit selection rule, preserving mutually exclusive alternatives.

## Internal Scope Triage Boundary

Scope Triage consumes only the compact normalized story and a validated,
normalized Discovery artifact. It does not reread the repository, raw provider
context, ticket systems, or the network. It classifies every Discovery finding
exactly once and creates no implementation task or estimate.

Before classifying work as `CORE_SCOPE` or `REQUIRED_ENABLER`, the producer
records which AC or mandatory constraint fails, the evidence supporting the
dependency, whether the issue is pre-existing, any unresolved decision, and
whether the story introduces or materially aggravates the issue. Without an
AC/constraint reference and dependency evidence, promotion is structurally
invalid. Other categories carry no promotion assessment.

Open decisions remain open with no selected option. Options are preserved as
separate records and grouped with stable IDs; `exactly_one` groups are mutually
exclusive and contain at least two options. Missing evidence remains an
evidence gap and forces explicit owner review instead of inferred certainty.
Host normalization derives artifact/entity IDs and canonical ordering, checks
Discovery reference coverage, and rejects free-form provider output.

## Internal Implementation Planner Boundary

Implementation Planner consumes only the normalized story, the validated Scope
Triage artifact, and a host-derived compact planning context. That context
contains referenced ACs, mandatory constraints, evidence, and provenance but
does not contain raw Discovery findings or repository contents.

Each triage category has one legal destination: `CORE_SCOPE` becomes base-plan
tasks, `REQUIRED_ENABLER` becomes separately estimated mandatory work,
`CONDITIONAL_SCOPE` becomes one branch per decision option,
`READINESS_PREREQUISITE` becomes readiness, and related defects, risks, and
optional improvements become excluded related findings. Verified facts may
support tasks but do not create work by themselves.

Every task cites evidence, direct provenance, provenance-backed source targets,
and test evidence. Branch groups preserve the triage relationship and selection
rule. Each scenario selects legally from those groups, includes every mandatory
delta, keeps readiness calendar impact separate, and has a host-checked
arithmetic total. Open material decisions force scenario-only estimates,
`finalCommittedEstimate: null`, and explicit owner review. Stable IDs and
canonical ordering are derived host-side; invalid/free-form output fails closed.

## Effort And Calendar Representation

An engineering range is represented as:

```json
{
  "estimateKind": "mandatory_delta",
  "unit": "person_hours",
  "minimumPersonHours": 4,
  "additionalPersonHours": 3,
  "confidence": "medium",
  "rationale": "Synthetic example."
}
```

The upper bound is `minimumPersonHours + additionalPersonHours`. This delta
form makes ordering schema-enforceable: both numbers must be non-negative, so
an inverted range cannot be represented. Scenario arithmetic adds lower bounds
and additional uncertainty independently; SS05 recomputes every total.

Calendar impact is a different tagged object. `unknown` requires a reason and
contains no numeric developer effort. A pending approval may therefore have a
zero engineering range and unknown calendar impact without inventing days.

## Reference Rules

- Classifications reference findings and evidence.
- Base tasks reference ACs and/or mandatory constraints plus evidence and
  direct provenance.
- Required enablers reference evidence and at least one AC or mandatory
  constraint.
- Conditional classifications and branches reference a decision; each branch
  also references one option of that decision.
- Branches reference a group, declare their relationship, and carry
  provenance-backed tasks.
- Scenario contributions reference the work that generated each delta.
- Provenance records link bounded source references to evidence.
- Scope expansions reference the original classification and human decision.

JSON Schema enforces reference shape and required presence. The SS05 Scope
Governor enforces cross-document existence, entity type, uniqueness,
selected-option membership, classification/task origin agreement, branch-group
membership, scenario selection, and arithmetic.

## Schema-Enforced Invariants

The v2 schemas use exact version constants, strict objects, enums, required
fields, minimum cardinality, non-negative numbers, and conditional schemas to
enforce:

- only a `CORE_SCOPE` classification may set `includedInBasePlan: true`;
- conditional, related-defect, risk-only, optional-improvement, readiness, and
  verified-fact classifications are excluded from the base plan;
- conditional classifications and branches require a decision and condition;
- required enablers require evidence and at least one AC/constraint reference;
- core scope and required enablers require a structured promotion assessment
  with dependency evidence and at least one failing AC/mandatory constraint;
- all other classifications require `promotionAssessment: null`;
- exactly-one decision option groups are mutually exclusive and contain at
  least two options;
- base tasks declare `originCategory: CORE_SCOPE` and require AC/constraint
  references;
- every planned task requires direct evidence, provenance, source targets, and
  test evidence;
- conditional branches identify a specific option of their decision;
- open decisions have `selectedOptionId: null`; resolved decisions require a
  selected option-shaped ID;
- readiness always contains separate engineering and calendar objects;
- effort is non-negative and intrinsically ordered by lower-bound-plus-delta;
- exclusive exactly-one groups contain at least two branches;
- material open decisions force `finalCommittedEstimate: null`;
- each root artifact carries exact version metadata;
- undeclared properties and enum values are rejected.

## Host Scope Governor Boundary

The following checks deliberately remain deterministic host logic rather than
pretend JSON Schema logic:

- referenced IDs exist and have the expected entity type;
- IDs are unique across the full artifact set and match host-derived identity;
- a base task's classification reference actually resolves to `CORE_SCOPE`;
- a selected decision option belongs to that decision;
- branch references and group membership are reciprocal;
- exactly-one/zero-or-one/dependent selection is legal in each scenario;
- verified existing capability does not become an add/create task without
  separate change evidence;
- mandatory reason is causally supported by evidence;
- scenario contribution refs and arithmetic remain correct across the full
  artifact bundle (the SS04 producer already checks its local plan output);
- no authoritative final total exists anywhere while a material decision is
  open;
- legal validation and owner-review state transitions.

The pure governor reads only supplied Discovery, Scope Triage, and Planner
artifacts plus host-owned schemas. It performs no repository, workspace,
ticket, credential, provider, or network reads. Structural schema failures and
semantic failures are separate violation kinds. Violations are deduplicated and
canonically ordered by code, kind, artifact, path, entity, related references,
and message before a stable report ID is derived.

Machine-readable codes include reference-specific failures such as
`REFERENCE_AC_NOT_FOUND`, `REFERENCE_ENTITY_TYPE_MISMATCH`, and
`DUPLICATE_TASK_ID`; scope failures such as `BASE_ORIGIN_NOT_CORE_SCOPE`,
`OPTIONAL_AS_REQUIRED_ENABLER`, and `EXISTING_CAPABILITY_CREATION_TASK`;
decision/branch failures such as `OPEN_DECISION_SELECTED_OPTION`,
`BRANCH_DECISION_REF_MISSING`, and
`SCENARIO_EXCLUSIVE_BRANCH_CONFLICT`; and estimate failures such as
`BASE_EFFORT_MISMATCH`, `READINESS_APPROVAL_EFFORT_NONZERO`,
`SCENARIO_TOTAL_MISMATCH`, and `OPEN_MATERIAL_DECISION_FINAL_TOTAL`.

The internal governed-planner boundary stages Planner output and publishes it
only after a full bundle pass. On a first failure it supplies only the invalid
plan and compact violation report to the existing isolated synthesis dispatch.
Exactly one corrective call is permitted. The corrected artifact is fully
schema-validated, normalized, and governed again. A second failure produces a
versioned `needs_owner_review` report and publishes no plan. Provider failure,
free-form output, and malformed JSON follow the same fail-closed boundary;
there is no legacy fallback.

## Required Output Separation

The implementation-plan schema keeps these independent fields:

```text
readinessPrerequisites
basePlan
requiredEnablers
conditionalBranches
scenarioEstimates
decisionRegister
relatedFindings
evidenceAndProvenance
approvedScopeExpansions
validationStatus
```

The extra `approvedScopeExpansions` field preserves human expansion history and
does not weaken the required separation.

## Compatibility And Failure Behavior

See `COMPATIBILITY.md`. V2 remains additive and non-default. The internal SS02
through SS05 phases fail closed: no invalid v2 document is treated as legacy
free-form output. Semantic governance and one bounded correction are active
only in the internal pipeline; public selection and rendering remain SS06.
