# Historical F02 guarantees and current Wait CI gates

This migration is limited to test oracles and CI selection. Production code and the public `mana.wait-dependency/v1` representation are unchanged.

## Historical fixture, not a current public-layout oracle

`tests/wait-dependencies-proof-exclusions.py` remains byte-identical to PR #20 head `4d096ad3e1b59db86aed49326d9a27f824008236` (SHA-256 `16a118beb4192b2653c9772e5b9537288b766901ff20e23b61c4344d64ffeb30`). It is a versioned F02 reproducer. Its original command still reports its historical layout conflicts; it is not marked skipped, expected-failure, or made to return success.

The mandatory CI routes are now:

- `tests/wait-dependencies-negative-evidence.py`: current source/evidence semantic negatives.
- `tests/wait-dependencies-wire-compatibility.py`: current public F03 wire, source authority, compatibility and CLI.
- The same wire script with `--diagnostic-replay`: all 24 unchanged F02 test methods against the existing internal proof representation.

The workflow retains one public F03 invocation and one internal F02 replay. The obsolete direct F02/public-layout invocation is removed from the current gate set. No continue-on-error or artificial skip is used. The ordinary F02 source is retained because both the replay and source-only oracle depend on it.

The diagnostic subclass overrides **only build**. It inherits all 24 test methods, their assertions, fixture lifecycle and CLI subprocess checks without filtering. This is sufficient for the *internal* obligations only; it is not a substitute for the separately mandatory public F03 gate. Certificate byte assertions are not relabelled as public-wire assertions.

## Three F01 oracle corrections

N11: B without pending has only possible source edge b/P1 -> a/P1, so the limited negative is justified. The acquisition-UNKNOWN dependency check in the second half is kept and explicitly asserts UNKNOWN.

N12: both B cuts have the same one-direction possible edge and their union is acyclic. The limited global negative is justified while lock unknowns and INCOMPLETE coverage remain. A fabricated complete-coverage report must still be rejected.

N15: the unresolved-frontier case stays UNKNOWN and rejects a fabricated negative. REQUIRED/NESTED share one P across frames: no inter-P edge can form, even with an incomplete cut. No lock completeness or runtime absence is inferred.

These expectations are fixed from complete source observations and an existing independent source-upper-bound oracle, not from producer result flags or certificates. The bounded independent review enumerates every possible subgraph using lifetime/frame stacks and separate reachability.

## Explicit guarantee lineage

Dnn = mandatory internal DiagnosticReplay method; Wnn = mandatory public WireCompatibility test; Nnn = current NegativeEvidence test; I01-01 = WaitTests manual-oracle matrix; R1 = bounded independent review runner. A public companion need not repeat an internal representation-specific attack; that exact attack remains mandatory in Dnn.

| Historical F02 test | Retained guarantee | Canonical destination | Public companion / boundary |
|---|---|---|---|
| `test_01_four_justified_degradations_remain_unknown` | UNKNOWN A/C, partial A and frontier | `DiagnosticReplay.test_01_four_justified_degradations_remain_unknown` | W04; N01/N14/N15 |
| `test_02_four_unnecessary_degradations_recovered` | Four justified structural negatives | `DiagnosticReplay.test_02_four_unnecessary_degradations_recovered` | W03; N11/N12/N15 |
| `test_03_complete_acyclic_evidence_route` | Evidence-complete acyclic B | `DiagnosticReplay.test_03_complete_acyclic_evidence_route` | W01; N03 |
| `test_04_positive_cycles_and_cross_layer_unchanged` | Positive DB and cross-layer cycles preserved | `DiagnosticReplay.test_04_positive_cycles_and_cross_layer_unchanged` | W01; N04/N10 |
| `test_05_forged_empty_structural_proof_A_rejected` | Forged empty A proof rejected before reprojection | `DiagnosticReplay.test_05_forged_empty_structural_proof_A_rejected` | W04/W05/W06; N02 |
| `test_06_forged_C_cannot_ignore_application_completion` | C application completion cannot be ignored | `DiagnosticReplay.test_06_forged_C_cannot_ignore_application_completion` | W04/W05/W06; N02/N10 |
| `test_07_exact_but_cyclic_certificate_rejected_independently` | Exact cyclic certificate rejected | `DiagnosticReplay.test_07_exact_but_cyclic_certificate_rejected_independently` | W06 public authority boundary; D07 exact internal attack |
| `test_08_removed_edge_from_valid_proof_rejected` | Removed structural bound edge rejected | `DiagnosticReplay.test_08_removed_edge_from_valid_proof_rejected` | W06 public authority boundary; D08 exact internal certificate |
| `test_09_proof_scope_and_prefix_tampering_rejected` | Certificate scope, prefix and kind tampering | `DiagnosticReplay.test_09_proof_scope_and_prefix_tampering_rejected` | W06/W10; D09 exact internal fields |
| `test_10_missing_evidence_stays_visible` | Incomplete coverage and unknowns cannot be cleared | `DiagnosticReplay.test_10_missing_evidence_stays_visible` | W07; N12/N15 |
| `test_11_null_or_unplaced_identity_no_structural_proof` | Null/unplaced identities cannot prove exclusion | `DiagnosticReplay.test_11_null_or_unplaced_identity_no_structural_proof` | I01-01 O-F07/O-G01/O-G03; D11 |
| `test_12_partial_inventory_preserves_enlistment_unknown` | Partial inventory keeps enlistment UNKNOWN | `DiagnosticReplay.test_12_partial_inventory_preserves_enlistment_unknown` | I01-01 O-F02; D12 |
| `test_13_same_P_minimal_no_assumptions` | Same-P exclusion needs no invented lock assumptions | `DiagnosticReplay.test_13_same_P_minimal_no_assumptions` | W03; D13 exact minimal internal case |
| `test_14_same_P_without_cut_independent_validator` | No-cut same-P validator independent of producer flag | `DiagnosticReplay.test_14_same_P_without_cut_independent_validator` | W08 related cut path; D14 exact no-cut internal case |
| `test_15_unknown_acquisition_and_dependencies_still_block_A` | UNKNOWN acquisition and dependency chain remain blocking in A | `DiagnosticReplay.test_15_unknown_acquisition_and_dependencies_still_block_A` | N11 second half; D15 |
| `test_16_no_sidecar_can_self_certify_model_evidence` | Sidecar MODEL_EVIDENCE cannot self-certify | `DiagnosticReplay.test_16_no_sidecar_can_self_certify_model_evidence` | N09; W10 malformed shape/value rejection |
| `test_17_budget_guards_include_serialized_proof_edges` | Internal proof work charged to budgets; public counters remain wire-v1 | `DiagnosticReplay.test_17_budget_guards_include_serialized_proof_edges` | W02/W09 public counters; R1 budget checks; D17 internal budget |
| `test_18_incompatible_cuts_and_holdings_still_distinct` | Incompatible cuts and holdings remain distinct | `DiagnosticReplay.test_18_incompatible_cuts_and_holdings_still_distinct` | W11; I01-01 O-B02/O-B03/O-G04; D18 |
| `test_19_cli_proof_unknown_budget_and_altered_sidecar` | Real CLI, altered sidecar and budgets | `DiagnosticReplay.test_19_cli_proof_unknown_budget_and_altered_sidecar` | W09; N13; D19 |
| `test_20_structural_union_cannot_promote_incompatible_directions` | Cyclic union of incompatible structural cuts cannot become global negative | `DiagnosticReplay.test_20_structural_union_cannot_promote_incompatible_directions` | W11 complementary evidence-complete union; D20 exact structural union |
| `test_21_namespace_never_merges_replicated_local_P1` | Replicated local P1 remains namespaced | `DiagnosticReplay.test_21_namespace_never_merges_replicated_local_P1` | W01 source-report equality; D21 exact two-node count |
| `test_22_validator_does_not_call_structural_producer` | Validator structural check independent of producer proof builder | `DiagnosticReplay.test_22_validator_does_not_call_structural_producer` | W08; D22 |
| `test_23_historical_example_semantics_and_diagrams_preserved` | Historical examples and diagrams preserved | `DiagnosticReplay.test_23_historical_example_semantics_and_diagrams_preserved` | W01/W09 direct canonical equality; D23 private normalization |
| `test_24_evidence_complete_cannot_hide_cross_layer_circuit` | Evidence-complete label cannot hide cross-layer cycle | `DiagnosticReplay.test_24_evidence_complete_cannot_hide_cross_layer_circuit` | W04/W05/W06; D24 |

The full diagnostic route, public route and corrected Negative Evidence suite must all succeed. Original run #49 remains failed; local candidate regressions do not retroactively change that run or authorize either PR merge.
