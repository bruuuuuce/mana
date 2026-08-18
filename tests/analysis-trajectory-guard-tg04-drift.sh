#!/usr/bin/env bash
# TG04 deterministic drift detector and advisory checkpoint-policy acceptance suite.
set -euo pipefail

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
detector="$root/scripts/lib/analysis-trajectory-drift.py"
state="$root/scripts/lib/analysis-trajectory-state.py"
telemetry="$root/scripts/lib/analysis-trajectory-telemetry.sh"
fixture_dir="$root/tests/fixtures/analysis-trajectory-guard"
traces="$fixture_dir/tg00-traces-v1.json"
story="$fixture_dir/tg03-story-package-v1.json"
seed="$fixture_dir/tg03-mission-seed-v1.json"
config="$fixture_dir/tg04-drift-config-v1.json"
expected_matrix="$fixture_dir/tg04-evaluation-matrix-v1.json"
schema_test="$root/tests/lib/json_schema_subset.py"
schema_dir="$root/contracts/analysis-trajectory"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-tg04-drift.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
expect_failure() { if "$@" >"$tmp/expected-failure.out" 2>"$tmp/expected-failure.err"; then fail "command unexpectedly succeeded: $*"; fi; }

python3 "$state" create-mission "$story" "$seed" "$tmp/mission.json" "$tmp/history.json"
python3 "$schema_test" "$schema_dir/drift-config-v1.schema.json" "$config" || fail 'drift config schema failed'

export MANA_ANALYSIS_TRAJECTORY_TELEMETRY=true
# shellcheck disable=SC1090
. "$telemetry"

reset_telemetry() {
  # Read by functions from the dynamically sourced telemetry helper.
  # shellcheck disable=SC2034
  MANA_TRAJECTORY_TELEMETRY_ENABLED=false
  # shellcheck disable=SC2034
  MANA_TRAJECTORY_TELEMETRY_EVENTS=""
  # shellcheck disable=SC2034
  MANA_TRAJECTORY_TELEMETRY_SUMMARY=""
  # shellcheck disable=SC2034
  MANA_TRAJECTORY_TELEMETRY_RUN_ID=""
}

init_case() {
  local case_id="$1"
  workspace="$tmp/cases/$case_id"
  mkdir -p "$workspace/evidence" "$workspace/validation"
  reset_telemetry
  mana_trajectory_telemetry_init "$workspace" "$case_id" v2
}

emit_trace_case() {
  local case_name="$1" workspace="$2" opaque="${3:-false}" step action scope
  local -a event_refs
  while IFS= read -r step; do
    action="$(jq -r '.actionKind' <<<"$step")"
    scope="$(jq -r '.targetScopeRef' <<<"$step")"
    event_refs=()
    while IFS= read -r ref; do event_refs+=(--acceptance-criterion-refs "$ref"); done < <(jq -r '.goalRefs[]?' <<<"$step")
    while IFS= read -r ref; do event_refs+=(--evidence-gap-refs "$ref"); done < <(jq -r '.gapRefs[]?' <<<"$step")
    while IFS= read -r ref; do event_refs+=(--decision-refs "$ref"); done < <(jq -r '.decisionRefs[]?' <<<"$step")
    if [ "$opaque" != true ]; then
      mana_trajectory_telemetry_emit provider_iteration_started "$(jq -r '.hostBoundary' <<<"$step")" "$action" fixture fixture-model none "$scope" started "${event_refs[@]}"
    fi
    while IFS= read -r ref; do event_refs+=(--evidence-added-refs "$ref"); done < <(jq -r '.evidenceAddedRefs[]?' <<<"$step")
    mana_trajectory_telemetry_emit provider_iteration_completed "$(jq -r '.hostBoundary' <<<"$step")" "$action" fixture fixture-model none "$scope" completed "${event_refs[@]}"
    if [ "$(jq '.decisionRefs | length' <<<"$step")" -gt 0 ]; then
      mana_trajectory_telemetry_emit open_decision_observed provider_result identify-open-decision fixture fixture-model none "$scope" completed "${event_refs[@]}"
    fi
  done < <(jq -c --arg case_name "$case_name" '.traces[] | select(.case == $case_name) | .steps[]' "$traces")
}

write_observation() {
  local output="$1" boundary="$2" final="$3" actions="$4"
  jq -n --arg boundary "$boundary" --argjson final "$final" --argjson actions "$actions" '{
    schemaVersion:"mana.analysis-trajectory.drift-observation/v1",
    observedBoundary:$boundary,
    finalSynthesisRequested:$final,
    nextActionProposals:$actions
  }' >"$output"
  python3 "$schema_test" "$schema_dir/drift-observation-v1.schema.json" "$output" || fail "observation schema failed: $output"
}

analyze_case() {
  local case_id="$1" workspace="$2" mission="${3:-$tmp/mission.json}"
  local events="$workspace/evidence/analysis-trajectory-events-v1.jsonl"
  local ledger="$workspace/validation/trajectory-ledger-v1.json"
  local observation="$workspace/validation/drift-observation-v1.json"
  local output="$tmp/recommendations/$case_id.json"
  mkdir -p "$tmp/recommendations"
  python3 "$state" derive-ledger "$mission" "$events" "$ledger" || fail "ledger derivation failed: $case_id"
  python3 "$detector" analyze "$mission" "$ledger" "$events" "$config" "$observation" "$output" || fail "drift analysis failed: $case_id"
  python3 "$detector" analyze "$mission" "$ledger" "$events" "$config" "$observation" "$tmp/recommendations/$case_id.repeat.json" || fail "repeat drift analysis failed: $case_id"
  cmp -s "$output" "$tmp/recommendations/$case_id.repeat.json" || fail "drift result is not deterministic: $case_id"
  python3 "$detector" validate-recommendation "$mission" "$ledger" "$events" "$config" "$observation" "$output" || fail "recommendation validation failed: $case_id"
  python3 "$schema_test" "$schema_dir/drift-recommendation-v1.schema.json" "$output" || fail "recommendation schema failed: $case_id"
  jq -e '
    .mode == "SHADOW" and .advisory == true and
    .effects == {providerCalls:0,networkCalls:0,controlFlowChanged:false,finalArtifactsChanged:false,recommendationPublished:true} and
    ([.signalEvaluations[] | select(.status == "TRIGGERED" and (.refs | length) == 0)] | length) == 0 and
    .reasonCodes == [.signalEvaluations[] | select(.status == "TRIGGERED") | .reasonCode]
  ' "$output" >/dev/null || fail "recommendation is not advisory/reference-grounded: $case_id"
}

empty_action='[]'

# TG00 simple on-track trace.
init_case on-track-simple
emit_trace_case ON_TRACK_SIMPLE "$workspace"
write_observation "$workspace/validation/drift-observation-v1.json" ITERATION_BOUNDARY false "$empty_action"
analyze_case on-track-simple "$workspace"

# A requirement-linked dependency is legitimate and needs no scope triage.
init_case legitimate-dependency-expansion
emit_trace_case ON_TRACK_LEGITIMATE_EXPANSION "$workspace"
actions='[{"actionId":"action-dependency","targetScopeRef":"scope-profile-index","justificationGoalRefs":["AC-SYN-02"],"justificationGapRefs":["GAP-DEPENDENCY-CONTRACT"],"mandatoryConstraintRefs":[],"assumedDecisionRefs":[],"decisionEvidenceRefs":[],"supportingEventRefs":[]}]'
write_observation "$workspace/validation/drift-observation-v1.json" NEXT_ACTION_BOUNDARY false "$actions"
analyze_case legitimate-dependency-expansion "$workspace"

# TG00 unrelated bug: real finding, but the proposed continuation has no mission link and leaves accepted scope.
init_case unrelated-rabbit-hole
emit_trace_case DRIFT_RELATED_BUG "$workspace"
actions='[{"actionId":"action-rabbit-hole","targetScopeRef":"scope-archive-search","justificationGoalRefs":[],"justificationGapRefs":[],"mandatoryConstraintRefs":[],"assumedDecisionRefs":[],"decisionEvidenceRefs":[],"supportingEventRefs":[]}]'
write_observation "$workspace/validation/drift-observation-v1.json" NEXT_ACTION_BOUNDARY false "$actions"
analyze_case unrelated-rabbit-hole "$workspace"

# TG00 open architecture alternative: a host-visible action must not assume the unresolved option.
init_case unresolved-decision-assumption
emit_trace_case DRIFT_ARCHITECTURE_RABBIT_HOLE "$workspace"
actions='[{"actionId":"action-assume-delivery-mode","targetScopeRef":"scope-delivery-callback","justificationGoalRefs":["AC-SYN-01"],"justificationGapRefs":["GAP-DELIVERY-GUARANTEE"],"mandatoryConstraintRefs":[],"assumedDecisionRefs":["DEC-DELIVERY-MODE"],"decisionEvidenceRefs":[],"supportingEventRefs":[]}]'
write_observation "$workspace/validation/drift-observation-v1.json" NEXT_ACTION_BOUNDARY false "$actions"
analyze_case unresolved-decision-assumption "$workspace"

# Isolated open-decision control keeps the target accepted and exercises owner review precedence.
init_case owner-review-open-decision
mana_trajectory_telemetry_emit open_decision_observed provider_result identify-open-decision fixture fixture-model none scope-delivery-callback completed --decision-refs DEC-DELIVERY-MODE --evidence-gap-refs GAP-DELIVERY-GUARANTEE
actions='[{"actionId":"action-owner-decision-required","targetScopeRef":"scope-delivery-callback","justificationGoalRefs":["AC-SYN-01"],"justificationGapRefs":["GAP-DELIVERY-GUARANTEE"],"mandatoryConstraintRefs":[],"assumedDecisionRefs":["DEC-DELIVERY-MODE"],"decisionEvidenceRefs":[],"supportingEventRefs":[]}]'
write_observation "$workspace/validation/drift-observation-v1.json" NEXT_ACTION_BOUNDARY false "$actions"
analyze_case owner-review-open-decision "$workspace"

# TG00 repetition: the first visit adds evidence, then two equivalent revisits add none.
init_case repeated-target
emit_trace_case DRIFT_REPEAT_NO_EVIDENCE "$workspace"
write_observation "$workspace/validation/drift-observation-v1.json" ITERATION_BOUNDARY false "$empty_action"
analyze_case repeated-target "$workspace"

# Three different targets with no evidence exercise the streak without a repetition false positive.
init_case no-new-evidence-streak
for scope in scope-signal-api scope-signal-store scope-profile-index; do
  mana_trajectory_telemetry_emit provider_iteration_started agent_iteration inspect-scope fixture fixture-model none "$scope" started
  mana_trajectory_telemetry_emit provider_iteration_completed agent_iteration inspect-scope fixture fixture-model none "$scope" completed
done
write_observation "$workspace/validation/drift-observation-v1.json" ITERATION_BOUNDARY false "$empty_action"
analyze_case no-new-evidence-streak "$workspace"

# Close every host-owned gap with evidence covering every goal and mandatory constraint.
init_case sufficient-evidence
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-access-policy completed --acceptance-criterion-refs AC-SYN-02 --evidence-gap-refs GAP-AUTHZ-CHECK --evidence-added-refs EV-CLOSE-AUTHZ
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-signal-api completed --acceptance-criterion-refs AC-SYN-01 --evidence-gap-refs GAP-COMMIT-HOOK --evidence-added-refs EV-CLOSE-COMMIT
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-delivery-callback completed --acceptance-criterion-refs AC-SYN-01 --evidence-gap-refs GAP-DELIVERY-GUARANTEE --evidence-added-refs EV-CLOSE-DELIVERY
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-profile-index completed --acceptance-criterion-refs AC-SYN-02 --evidence-gap-refs GAP-DEPENDENCY-CONTRACT --evidence-added-refs EV-CLOSE-DEPENDENCY
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-signal-api completed --acceptance-criterion-refs AC-SYN-02 --evidence-gap-refs GAP-RESULT-VISIBILITY --evidence-added-refs EV-CLOSE-VISIBILITY
write_observation "$workspace/validation/drift-observation-v1.json" ITERATION_BOUNDARY false "$empty_action"
analyze_case sufficient-evidence "$workspace"

# TG00 mandatory cross-cutting authorization expansion is positively explained, not mislabeled drift.
init_case mandatory-security-expansion
emit_trace_case MANDATORY_CROSS_CUTTING_FINDING "$workspace"
actions='[{"actionId":"action-authz-check","targetScopeRef":"scope-access-policy","justificationGoalRefs":["AC-SYN-02"],"justificationGapRefs":["GAP-AUTHZ-CHECK"],"mandatoryConstraintRefs":["CONSTRAINT-AUTHZ-01"],"assumedDecisionRefs":[],"decisionEvidenceRefs":[],"supportingEventRefs":[]}]'
write_observation "$workspace/validation/drift-observation-v1.json" NEXT_ACTION_BOUNDARY false "$actions"
analyze_case mandatory-security-expansion "$workspace"

# TG00 opaque provider trace: hidden next-action facts stay NOT_OBSERVABLE and no internal activity is invented.
init_case opaque-provider
emit_trace_case OPAQUE_PROVIDER_BOUNDARY "$workspace" true
write_observation "$workspace/validation/drift-observation-v1.json" PROVIDER_COMPLETION_BOUNDARY false "$empty_action"
analyze_case opaque-provider "$workspace"
jq -e '
  .observability.ledgerGranularity == "OPAQUE_PROVIDER_BOUNDARY" and
  .observability.nextAction == "NOT_OBSERVABLE" and
  (.observability.unsupportedFacts | index("provider-internal-tool-call") != null) and
  ([.signalEvaluations[:3][].status] | all(. == "NOT_OBSERVABLE"))
' "$tmp/recommendations/opaque-provider.json" >/dev/null || fail 'opaque provider limitations are not truthful'

# A rejected target cannot be revisited without a later evidence ref.
init_case rejected-hypothesis-reopened
mana_trajectory_telemetry_emit hypothesis_rejected host_state reject-hypothesis host none none scope-signal-store completed --reason-codes contradicted-by-evidence
mana_trajectory_telemetry_emit target_revisited iteration_boundary revisit-target host none none scope-signal-store completed
write_observation "$workspace/validation/drift-observation-v1.json" ITERATION_BOUNDARY false "$empty_action"
analyze_case rejected-hypothesis-reopened "$workspace"

# Final synthesis is an explicit boundary, not a periodic counter.
init_case final-synthesis
emit_trace_case ON_TRACK_SIMPLE "$workspace"
write_observation "$workspace/validation/drift-observation-v1.json" FINAL_SYNTHESIS_BOUNDARY true "$empty_action"
analyze_case final-synthesis "$workspace"

# Unsupported action inside an accepted scope is distinct from scope expansion.
init_case unsupported-next-action
emit_trace_case ON_TRACK_SIMPLE "$workspace"
actions='[{"actionId":"action-unjustified","targetScopeRef":"scope-signal-api","justificationGoalRefs":[],"justificationGapRefs":[],"mandatoryConstraintRefs":[],"assumedDecisionRefs":[],"decisionEvidenceRefs":[],"supportingEventRefs":[]}]'
write_observation "$workspace/validation/drift-observation-v1.json" NEXT_ACTION_BOUNDARY false "$actions"
analyze_case unsupported-next-action "$workspace"

# Smaller valid mission budgets make soft and hard policy controls cheap and deterministic to exercise.
jq '.softBudgets.maxEvents=4 | .hardBudgets.maxEvents=4' "$seed" >"$tmp/budget-seed.json"
python3 "$state" create-mission "$story" "$tmp/budget-seed.json" "$tmp/budget-mission.json" "$tmp/budget-history.json"
init_case soft-budget-pressure
for unused in 1 2 3 4; do
  : "$unused"
  mana_trajectory_telemetry_emit analysis_started host_boundary observe-budget host none none scope-signal-api started
done
write_observation "$workspace/validation/drift-observation-v1.json" ITERATION_BOUNDARY false "$empty_action"
analyze_case soft-budget-pressure "$workspace" "$tmp/budget-mission.json"

init_case hard-budget-exceeded
for unused in 1 2 3 4 5; do
  : "$unused"
  mana_trajectory_telemetry_emit analysis_started host_boundary observe-budget host none none scope-signal-api started
done
write_observation "$workspace/validation/drift-observation-v1.json" ITERATION_BOUNDARY false "$empty_action"
analyze_case hard-budget-exceeded "$workspace" "$tmp/budget-mission.json"

# Disabled/non-shadow operation fails before publishing any recommendation.
jq '.enabled=false' "$config" >"$tmp/disabled-config.json"
workspace="$tmp/cases/on-track-simple"
expect_failure python3 "$detector" analyze "$tmp/mission.json" "$workspace/validation/trajectory-ledger-v1.json" "$workspace/evidence/analysis-trajectory-events-v1.jsonl" "$tmp/disabled-config.json" "$workspace/validation/drift-observation-v1.json" "$tmp/disabled-output.json"
[ ! -e "$tmp/disabled-output.json" ] || fail 'disabled detector published an artifact'

# Hash mutation is rejected.
jq '.outcome="STOP_HARD_BUDGET"' "$tmp/recommendations/on-track-simple.json" >"$tmp/mutated-recommendation.json"
workspace="$tmp/cases/on-track-simple"
expect_failure python3 "$detector" validate-recommendation "$tmp/mission.json" "$workspace/validation/trajectory-ledger-v1.json" "$workspace/evidence/analysis-trajectory-events-v1.jsonl" "$config" "$workspace/validation/drift-observation-v1.json" "$tmp/mutated-recommendation.json"

# Evaluation matrix contains expected/actual outcomes, notes, and observability limitations.
jq -n '{
  schemaVersion:"mana.analysis-trajectory.drift-evaluation-input/v1",
  cases:[
    {caseId:"final-synthesis",recommendationFile:"recommendations/final-synthesis.json",expectedOutcome:"CHECKPOINT_RECOMMENDED",expectedReasonCodes:["FINAL_SYNTHESIS_CHECKPOINT"],falsePositiveNotes:"Explicit final boundary only; no periodic checkpoint.",falseNegativeNotes:"None in synthetic host-visible trace.",unsupportedObservabilityNotes:"Structured next action not observed at this boundary."},
    {caseId:"hard-budget-exceeded",recommendationFile:"recommendations/hard-budget-exceeded.json",expectedOutcome:"STOP_HARD_BUDGET",expectedReasonCodes:["SOFT_BUDGET_PRESSURE","HARD_BUDGET_EXCEEDED"],falsePositiveNotes:"Uses a deliberately small synthetic mission budget.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Structured next action not observed at this boundary."},
    {caseId:"legitimate-dependency-expansion",recommendationFile:"recommendations/legitimate-dependency-expansion.json",expectedOutcome:"CONTINUE_ON_TRACK",expectedReasonCodes:[],falsePositiveNotes:"Requirement-linked dependency remains on track.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Provider-internal activity is outside this structured action boundary."},
    {caseId:"mandatory-security-expansion",recommendationFile:"recommendations/mandatory-security-expansion.json",expectedOutcome:"CONTINUE_ON_TRACK",expectedReasonCodes:["MANDATORY_CROSS_CUTTING_EXPANSION"],falsePositiveNotes:"Positive explanation is not treated as drift.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Provider-internal activity is outside this structured action boundary."},
    {caseId:"no-new-evidence-streak",recommendationFile:"recommendations/no-new-evidence-streak.json",expectedOutcome:"STOP_NO_NEW_EVIDENCE",expectedReasonCodes:["NO_NEW_EVIDENCE_STREAK"],falsePositiveNotes:"Targets differ, preventing a repetition false positive.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Structured next action not observed at this boundary."},
    {caseId:"on-track-simple",recommendationFile:"recommendations/on-track-simple.json",expectedOutcome:"CONTINUE_ON_TRACK",expectedReasonCodes:[],falsePositiveNotes:"No signal expected.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Structured next action not observed at this boundary."},
    {caseId:"opaque-provider",recommendationFile:"recommendations/opaque-provider.json",expectedOutcome:"CONTINUE_ON_TRACK",expectedReasonCodes:[],falsePositiveNotes:"No hidden provider activity is classified.",falseNegativeNotes:"Hidden drift cannot be detected without a host boundary.",unsupportedObservabilityNotes:"Internal reads, tools, delegation, context expansion, and next action are not observable."},
    {caseId:"owner-review-open-decision",recommendationFile:"recommendations/owner-review-open-decision.json",expectedOutcome:"NEEDS_OWNER_REVIEW",expectedReasonCodes:["OPEN_DECISION_ASSUMPTION"],falsePositiveNotes:"The target remains inside accepted scope.",falseNegativeNotes:"Unstructured assumptions remain unobservable.",unsupportedObservabilityNotes:"Provider-internal reasoning is not inferred."},
    {caseId:"rejected-hypothesis-reopened",recommendationFile:"recommendations/rejected-hypothesis-reopened.json",expectedOutcome:"CHECKPOINT_RECOMMENDED",expectedReasonCodes:["REJECTED_HYPOTHESIS_REOPENED"],falsePositiveNotes:"Revisit has no intervening evidence.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Structured next action not observed at this boundary."},
    {caseId:"repeated-target",recommendationFile:"recommendations/repeated-target.json",expectedOutcome:"CHECKPOINT_RECOMMENDED",expectedReasonCodes:["REPEATED_TARGET_NO_NEW_EVIDENCE"],falsePositiveNotes:"Threshold requires three visits; last two add no evidence.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Structured next action not observed at this boundary."},
    {caseId:"soft-budget-pressure",recommendationFile:"recommendations/soft-budget-pressure.json",expectedOutcome:"CHECKPOINT_RECOMMENDED",expectedReasonCodes:["SOFT_BUDGET_PRESSURE"],falsePositiveNotes:"Uses a deliberately small synthetic mission budget.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Structured next action not observed at this boundary."},
    {caseId:"sufficient-evidence",recommendationFile:"recommendations/sufficient-evidence.json",expectedOutcome:"STOP_SUFFICIENT_EVIDENCE",expectedReasonCodes:["SUFFICIENT_EVIDENCE_REACHED"],falsePositiveNotes:"Every gap is closed and every goal/constraint meets configured sufficiency.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Structured next action not observed at this boundary."},
    {caseId:"unrelated-rabbit-hole",recommendationFile:"recommendations/unrelated-rabbit-hole.json",expectedOutcome:"SCOPE_TRIAGE_REQUIRED",expectedReasonCodes:["UNSUPPORTED_NEXT_ACTION","UNAPPROVED_SCOPE_EXPANSION"],falsePositiveNotes:"The real finding is retained but does not expand the mission.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Provider-internal activity before the proposal remains opaque."},
    {caseId:"unresolved-decision-assumption",recommendationFile:"recommendations/unresolved-decision-assumption.json",expectedOutcome:"SCOPE_TRIAGE_REQUIRED",expectedReasonCodes:["UNAPPROVED_SCOPE_EXPANSION","OPEN_DECISION_ASSUMPTION"],falsePositiveNotes:"The TG00 trace also enters the unapproved outbox alternative; scope triage has precedence.",falseNegativeNotes:"Unstructured assumptions remain unobservable.",unsupportedObservabilityNotes:"Provider-internal reasoning is not inferred."},
    {caseId:"unsupported-next-action",recommendationFile:"recommendations/unsupported-next-action.json",expectedOutcome:"CHECKPOINT_RECOMMENDED",expectedReasonCodes:["UNSUPPORTED_NEXT_ACTION"],falsePositiveNotes:"Accepted scope alone is not a mission justification.",falseNegativeNotes:"None.",unsupportedObservabilityNotes:"Provider-internal activity before the proposal remains opaque."}
  ]
}' >"$tmp/matrix-input.json"
python3 "$detector" build-matrix "$tmp/matrix-input.json" "$tmp/evaluation-matrix.json" || fail 'evaluation matrix generation failed'
python3 "$detector" build-matrix "$tmp/matrix-input.json" "$tmp/evaluation-matrix-repeat.json" || fail 'repeat evaluation matrix generation failed'
cmp -s "$tmp/evaluation-matrix.json" "$tmp/evaluation-matrix-repeat.json" || fail 'evaluation matrix is not deterministic'
python3 "$schema_test" "$schema_dir/drift-evaluation-matrix-v1.schema.json" "$tmp/evaluation-matrix.json" || fail 'evaluation matrix schema failed'
if ! jq -e '.summary == {caseCount:15,matchedCount:15,mismatchCount:0,providerCalls:0,networkCalls:0} and all(.cases[]; .matchesExpected)' "$tmp/evaluation-matrix.json" >/dev/null; then
  jq '.cases[] | select(.matchesExpected == false)' "$tmp/evaluation-matrix.json" >&2
  fail 'fixture calibration contains mismatches'
fi
jq -S . "$tmp/evaluation-matrix.json" >"$tmp/evaluation-matrix.sorted.json"
jq -S . "$expected_matrix" >"$tmp/expected-matrix.sorted.json"
cmp -s "$tmp/evaluation-matrix.sorted.json" "$tmp/expected-matrix.sorted.json" || fail 'committed TG04 evaluation matrix is stale'

# TG04 remains a zero-token shadow layer and does not enter current public control flow.
if rg -n 'analysis-trajectory-drift' "$root/scripts/run-profile.sh" "$root/scripts/lib/story-start-scope-v2.sh" >/dev/null; then fail 'TG04 changed public Story Start control flow'; fi
if rg -n 'provider-dispatch|subprocess|urllib|requests|httpx|socket|curl' "$detector" >/dev/null; then fail 'TG04 detector contains provider/network dispatch'; fi
if rg -n 'analysis-trajectory-drift|drift-recommendation' "$root/scripts/run-profile.sh" "$root/scripts/lib/story-start-scope-v2.sh" >/dev/null; then fail 'TG04 altered final artifact publication'; fi

echo 'Analysis Trajectory Guard TG04 drift tests passed (shadow, zero provider/network calls)'
