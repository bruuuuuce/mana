# TRANSACTION-01 — Proposed Java/Spring Transaction Analysis

Status: proposal only. MANA-META-SKILL-00 supplies a candidate contract and
technology evidence; it supplies no transaction analyzer or execution approval.

T01 update: the bounded conditional static engine is now implemented under
`MANA-TRANSACTION-01-T01`, subject to review. See
`docs/standards/transaction-model-v1.md` and the T01 delivery report for exact
limits/evidence. The original broad proposal below is not a claim of complete
analysis or candidate approval. Resource/lock work remains out of scope.

## Objective

Implement a bounded static Java/Spring analyzer capable of substantiating the
capabilities declared in the factory candidate. Preserve an explicit boundary
between syntax observations, possible calls and runtime transaction behavior.

## Proposed Work

1. Agree the supported Java/Spring versions, build layouts, annotation/configuration
   forms, transaction managers and imperative/reactive scope with the human owner.
   Choose dependencies from repository evidence before adding parser infrastructure.
2. Extract methods and transactional declarations with file, symbol and location
   provenance. Cover method/class defaults, overrides, composed annotations and
   explicit configuration only within the agreed resolution scope.
3. Resolve bounded candidate call paths. Mark unresolved receiver type, proxy
   interception, self-invocation, reflection, async/thread changes, reactive flows
   and multiple-manager selection as uncertainty; never imply runtime reachability
   from a syntactic call edge alone.
4. Model REQUIRED, REQUIRES_NEW, NESTED, SUPPORTS, MANDATORY, NOT_SUPPORTED and
   NEVER under explicit entry-state/manager assumptions. Distinguish logical
   method scopes, reused physical transactions, suspension/resumption, independent
   transactions and conditional savepoint regions. Do not assume NESTED support.
5. Render sequence diagrams with overlapping logical/physical transaction regions,
   stable identities, legend, evidence links and visible unknowns. Select and
   verify renderer syntax; this proposal does not commit to Mermaid or PlantUML.
6. Reuse Mana verification evidence/governance contracts for qualification.
   Define a concrete review/promotion handoff bound to exact content, dependencies
   and test evidence, with explicit human approval before registration/activation.

## Acceptance Evidence

Use existing test infrastructure with small, reviewable positive and negative
fixtures for each supported propagation mode, reused/independent/nested regions,
transaction entry/exit and uncertain paths. Verify diagram region membership and
identity against expected semantic facts, plus actual rendering for the selected
format. Include inherited/composed declarations, self-invocation, dynamic dispatch,
multiple managers, unsupported nesting, missing classpath/configuration and thread
boundaries as supported cases or explicit unresolved outcomes.

Keep analyzed repositories unchanged and retain source hashes. A local static
fixture PASS does not prove real proxy behavior, runtime commit/rollback,
provider autonomy or production correctness. Runtime claims require separately
approved evidence. Missing checks remain NOT RUN/BLOCKED/INCONCLUSIVE as applicable.

## Decision Gate

The accountable Architect / Team Leader approves scope, dependency choices,
known limits, evidence and exact promotion content. No TRANSACTION-01 work,
analyzer capability, candidate trust or execution is authorized by this proposal.
