#!/usr/bin/env bash
# TG05 deterministic compact checkpoint and bounded-call acceptance suite.
set -euo pipefail

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
checkpoint="$root/scripts/lib/analysis-trajectory-checkpoint.py"
state="$root/scripts/lib/analysis-trajectory-state.py"
detector="$root/scripts/lib/analysis-trajectory-drift.py"
fixture_dir="$root/tests/fixtures/analysis-trajectory-guard"
story="$fixture_dir/tg03-story-package-v1.json"
seed="$fixture_dir/tg03-mission-seed-v1.json"
drift_config="$fixture_dir/tg04-drift-config-v1.json"
shadow_config="$fixture_dir/tg05-checkpoint-governor-shadow-v1.json"
off_config="$fixture_dir/tg05-checkpoint-governor-off-v1.json"
schema_dir="$root/contracts/analysis-trajectory"
schema_test="$root/tests/lib/json_schema_subset.py"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-tg05-checkpoint.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

for file in "$checkpoint" "$state" "$detector" "$story" "$seed" "$drift_config" "$shadow_config" "$off_config"; do
  [ -f "$file" ] || fail "missing TG05 dependency: $file"
done

export MANA_ANALYSIS_TRAJECTORY_TELEMETRY=true
# shellcheck disable=SC1091
. "$root/scripts/lib/analysis-trajectory-telemetry.sh"

reset_telemetry() {
  export MANA_TRAJECTORY_TELEMETRY_ENABLED=false
  export MANA_TRAJECTORY_TELEMETRY_EVENTS=""
  export MANA_TRAJECTORY_TELEMETRY_SUMMARY=""
  export MANA_TRAJECTORY_TELEMETRY_RUN_ID=""
}

assess_invalid() {
  local expected_exit="$1" expected_status="$2" expected_error="$3" response="$4" validation="$5" calls_used="${6:-1}" code
  if python3 "$checkpoint" assess-response "$tmp/request.json" "$response" "$validation" --calls-used "$calls_used"; then
    fail "invalid response unexpectedly passed: $response"
  else
    code=$?
  fi
  [ "$code" -eq "$expected_exit" ] || fail "unexpected assessment exit $code for $response"
  jq -e --arg status "$expected_status" --arg error "$expected_error" '
    .status == $status and (.errors | map(.code) | index($error) != null)
  ' "$validation" >/dev/null || fail "missing $expected_status/$expected_error assessment"
}

mission="$tmp/mission.json"
python3 "$state" create-mission "$story" "$seed" "$mission" "$tmp/history.json"

# The main fixture keeps one open decision, one active rejection, and one
# no-evidence iteration. TG04 final-synthesis policy is the sole call trigger.
workspace="$tmp/base"; mkdir -p "$workspace/evidence" "$workspace/validation"
reset_telemetry; mana_trajectory_telemetry_init "$workspace" tg05-base v2
mana_trajectory_telemetry_emit provider_iteration_started agent_iteration inspect-scope fixture fixture-model none scope-signal-api started
mana_trajectory_telemetry_emit provider_iteration_completed agent_iteration inspect-scope fixture fixture-model none scope-signal-api completed --acceptance-criterion-refs AC-SYN-01 --evidence-gap-refs GAP-COMMIT-HOOK --evidence-added-refs EV-COMMIT-HOOK
mana_trajectory_telemetry_emit open_decision_observed provider_result identify-open-decision fixture fixture-model none scope-delivery-callback completed --decision-refs DEC-DELIVERY-MODE --evidence-gap-refs GAP-DELIVERY-GUARANTEE
mana_trajectory_telemetry_emit hypothesis_rejected host_state reject-hypothesis host none none scope-signal-store completed --reason-codes contradicted-by-fixture
mana_trajectory_telemetry_emit provider_iteration_completed agent_iteration inspect-scope fixture fixture-model none scope-profile-index completed --acceptance-criterion-refs AC-SYN-02 --evidence-gap-refs GAP-DEPENDENCY-CONTRACT
events="$workspace/evidence/analysis-trajectory-events-v1.jsonl"
ledger="$workspace/validation/ledger.json"
observation="$workspace/validation/observation.json"
recommendation="$workspace/validation/recommendation.json"
python3 "$state" derive-ledger "$mission" "$events" "$ledger"
jq -n '{schemaVersion:"mana.analysis-trajectory.drift-observation/v1",observedBoundary:"FINAL_SYNTHESIS_BOUNDARY",finalSynthesisRequested:true,nextActionProposals:[]}' >"$observation"
python3 "$detector" analyze "$mission" "$ledger" "$events" "$drift_config" "$observation" "$recommendation"
jq -e '.outcome == "CHECKPOINT_RECOMMENDED" and .reasonCodes == ["FINAL_SYNTHESIS_CHECKPOINT"] and .modelCheckpointPermittedInTG05' "$recommendation" >/dev/null || fail 'TG04 did not authorize the synthetic checkpoint trigger'

jq -n '{
  schemaVersion:"mana.analysis-trajectory.checkpoint-input/v1",
  triggerReasons:["FINAL_SYNTHESIS_CHECKPOINT"],
  nextActionProposals:[
    {actionId:"action-inspect-commit-hook",actionKind:"inspect-scope",targetScopeRef:"scope-signal-api",justificationGoalRefs:["AC-SYN-01"],justificationGapRefs:["GAP-COMMIT-HOOK"],mandatoryConstraintRefs:[],expectedEvidence:"A bounded reference to the verified after-commit seam.",decisionDependencies:[],scopeExpansionRequired:false,estimatedBudgetDelta:{providerCalls:1,tokenProxy:100}},
    {actionId:"action-assume-delivery-mode",actionKind:"inspect-decision-option",targetScopeRef:"scope-delivery-callback",justificationGoalRefs:["AC-SYN-01"],justificationGapRefs:["GAP-DELIVERY-GUARANTEE"],mandatoryConstraintRefs:[],expectedEvidence:"Evidence about the still-open delivery choice.",decisionDependencies:["DEC-DELIVERY-MODE"],scopeExpansionRequired:false,estimatedBudgetDelta:{providerCalls:1,tokenProxy:100}},
    {actionId:"action-revisit-rejected-store",actionKind:"inspect-scope",targetScopeRef:"scope-signal-store",justificationGoalRefs:["AC-SYN-01"],justificationGapRefs:["GAP-COMMIT-HOOK"],mandatoryConstraintRefs:[],expectedEvidence:"A bounded host-visible store reference.",decisionDependencies:[],scopeExpansionRequired:false,estimatedBudgetDelta:{providerCalls:1,tokenProxy:100}},
    {actionId:"action-propose-archive-search",actionKind:"inspect-scope",targetScopeRef:"scope-archive-search",justificationGoalRefs:["AC-SYN-02"],justificationGapRefs:["GAP-RESULT-VISIBILITY"],mandatoryConstraintRefs:[],expectedEvidence:"A bounded result-visibility reference if an owner approves expansion.",decisionDependencies:[],scopeExpansionRequired:true,estimatedBudgetDelta:{providerCalls:1,tokenProxy:100}}
  ]
}' >"$tmp/checkpoint-input.json"

python3 "$checkpoint" build-request "$mission" "$ledger" "$events" "$drift_config" "$observation" "$tmp/checkpoint-input.json" "$recommendation" "$tmp/request.json"
python3 "$checkpoint" validate-request "$mission" "$ledger" "$events" "$drift_config" "$observation" "$tmp/checkpoint-input.json" "$recommendation" "$tmp/request.json"

# An ordinary non-trigger boundary cannot pay a checkpoint tax.
jq -n '{schemaVersion:"mana.analysis-trajectory.drift-observation/v1",observedBoundary:"ITERATION_BOUNDARY",finalSynthesisRequested:false,nextActionProposals:[]}' >"$tmp/non-trigger-observation.json"
python3 "$detector" analyze "$mission" "$ledger" "$events" "$drift_config" "$tmp/non-trigger-observation.json" "$tmp/non-trigger-recommendation.json"
jq -e '.outcome == "CONTINUE_ON_TRACK" and .modelCheckpointPermittedInTG05 == false' "$tmp/non-trigger-recommendation.json" >/dev/null || fail 'non-trigger fixture is not on track'
jq '.triggerReasons=[]' "$tmp/checkpoint-input.json" >"$tmp/non-trigger-input.json"
if python3 "$checkpoint" build-request "$mission" "$ledger" "$events" "$drift_config" "$tmp/non-trigger-observation.json" "$tmp/non-trigger-input.json" "$tmp/non-trigger-recommendation.json" "$tmp/non-trigger-request.json" >/dev/null 2>&1; then
  fail 'on-track execution built a checkpoint request'
fi
[ ! -e "$tmp/non-trigger-request.json" ] || fail 'on-track execution published a checkpoint request'

python3 "$schema_test" "$schema_dir/checkpoint-governor-config-v1.schema.json" "$shadow_config"
python3 "$schema_test" "$schema_dir/checkpoint-governor-config-v1.schema.json" "$off_config"
python3 "$schema_test" "$schema_dir/trajectory-checkpoint-request-v1.schema.json" "$tmp/request.json"
python3 "$checkpoint" render-prompt "$tmp/request.json" "$tmp/prompt.txt"
[ "$(wc -c <"$tmp/prompt.txt" | tr -d ' ')" -eq "$(jq '.promptMeasurements.promptBytes' "$tmp/request.json")" ] || fail 'prompt byte measurement is stale'
jq -e '
  .mode == "SHADOW" and .advisory == true and
  .callPolicy == {primaryCallsPerTrigger:1,structuralRepairCallsPerTrigger:1,semanticRetryPermitted:false,periodicCallsPermitted:false} and
  .checkpointEnvelope.missionContract.provenance.ownership == "host" and
  .hostValidationContext.openDecisionRefs == ["DEC-DELIVERY-MODE"] and
  (.hostValidationContext.activeRejectedHypotheses | length) == 1 and
  (.promptMeasurements.promptBytes <= .promptMeasurements.hardByteLimit) and
  (.promptMeasurements.promptTokenProxy <= .promptMeasurements.hardTokenProxyLimit)
' "$tmp/request.json" >/dev/null || fail 'request compact-state/call-policy semantics are incomplete'
if rg -ni '"(prompt|rawPrompt|response|conversation|fullHistory|messages|sourceContent|sourceCode|secret|credential|jiraBody|customerData)"' "$tmp/request.json" >/dev/null; then
  fail 'request contains prohibited history/raw content'
fi
for required in 'Restate the current objective' 'exactly one permitted outcome' 'owner-approved scope-expansion proposal' 'Keep every open decision open' 'Do not create implementation scope'; do
  rg -Fq "$required" "$tmp/prompt.txt" || fail "checkpoint prompt omits task: $required"
done

mission_id="$(jq -r '.checkpointEnvelope.missionContract.missionId' "$tmp/request.json")"
mission_hash="$(jq -r '.checkpointEnvelope.missionContract.contentHash' "$tmp/request.json")"
mission_revision="$(jq '.checkpointEnvelope.missionContract.revision' "$tmp/request.json")"
valid_action="$(jq -c '.checkpointEnvelope.nextActionProposals[] | select(.actionId == "action-inspect-commit-hook")' "$tmp/request.json")"
open_action="$(jq -c '.checkpointEnvelope.nextActionProposals[] | select(.actionId == "action-assume-delivery-mode")' "$tmp/request.json")"
rejected_action="$(jq -c '.checkpointEnvelope.nextActionProposals[] | select(.actionId == "action-revisit-rejected-store")' "$tmp/request.json")"

jq -n --arg mission_id "$mission_id" --arg mission_hash "$mission_hash" --argjson mission_revision "$mission_revision" --argjson action "$valid_action" '{
  schemaVersion:"mana.analysis-trajectory.trajectory-checkpoint-response/v1",missionId:$mission_id,missionHash:$mission_hash,missionRevision:$mission_revision,
  outcome:"ON_TRACK",objectiveRestatement:"Publish the synthetic signal after commit and expose its bounded delivery result.",
  supportingGoalRefs:["AC-SYN-01"],supportingConstraintRefs:[],supportingGapRefs:["GAP-COMMIT-HOOK"],supportingEvidenceRefs:["EV-COMMIT-HOOK"],
  recommendedNextAction:$action,scopeExpansionProposal:null,stopReason:null,discardedOrDeferredRefs:[],confidence:"HIGH"
}' >"$tmp/valid-on-track.json"
python3 "$schema_test" "$schema_dir/trajectory-checkpoint-response-v1.schema.json" "$tmp/valid-on-track.json"
python3 "$checkpoint" assess-response "$tmp/request.json" "$tmp/valid-on-track.json" "$tmp/valid-on-track.validation.json"
python3 "$schema_test" "$schema_dir/trajectory-checkpoint-validation-v1.schema.json" "$tmp/valid-on-track.validation.json"
jq -e '.status == "VALID" and .repairPermitted == false and .errors == []' "$tmp/valid-on-track.validation.json" >/dev/null || fail 'valid ON_TRACK response was rejected'

jq '.outcome="REANCHOR_REQUIRED"' "$tmp/valid-on-track.json" >"$tmp/valid-reanchor.json"
python3 "$checkpoint" assess-response "$tmp/request.json" "$tmp/valid-reanchor.json" "$tmp/valid-reanchor.validation.json"

jq -n --arg mission_id "$mission_id" --arg mission_hash "$mission_hash" --argjson mission_revision "$mission_revision" '{
  schemaVersion:"mana.analysis-trajectory.trajectory-checkpoint-response/v1",missionId:$mission_id,missionHash:$mission_hash,missionRevision:$mission_revision,
  outcome:"SCOPE_TRIAGE_REQUIRED",objectiveRestatement:"Preserve the bounded delivery-result objective while requesting owner review of a new evidence scope.",
  supportingGoalRefs:["AC-SYN-02"],supportingConstraintRefs:[],supportingGapRefs:["GAP-RESULT-VISIBILITY"],supportingEvidenceRefs:[],recommendedNextAction:null,
  scopeExpansionProposal:{proposalId:"proposal-archive-search",targetScopeRef:"scope-archive-search",reason:"The open visibility gap may require this candidate evidence scope.",relatedGoalRefs:["AC-SYN-02"],relatedConstraintRefs:[],relatedGapRefs:["GAP-RESULT-VISIBILITY"],expectedEvidence:"A bounded result-visibility reference.",estimatedBudgetDelta:{providerCalls:1,tokenProxy:100},ownerApprovalRequired:true},
  stopReason:null,discardedOrDeferredRefs:[],confidence:"MEDIUM"
}' >"$tmp/valid-scope-proposal.json"
cp "$mission" "$tmp/mission-before-scope-validation.json"
python3 "$checkpoint" assess-response "$tmp/request.json" "$tmp/valid-scope-proposal.json" "$tmp/valid-scope.validation.json"
cmp -s "$mission" "$tmp/mission-before-scope-validation.json" || fail 'scope proposal mutated the Mission Contract'

jq -n --arg mission_id "$mission_id" --arg mission_hash "$mission_hash" --argjson mission_revision "$mission_revision" '{
  schemaVersion:"mana.analysis-trajectory.trajectory-checkpoint-response/v1",missionId:$mission_id,missionHash:$mission_hash,missionRevision:$mission_revision,
  outcome:"STOP_NO_NEW_EVIDENCE",objectiveRestatement:"Stop the bounded synthetic analysis because the latest observable iteration produced no evidence.",
  supportingGoalRefs:["AC-SYN-02"],supportingConstraintRefs:[],supportingGapRefs:["GAP-DEPENDENCY-CONTRACT"],supportingEvidenceRefs:[],recommendedNextAction:null,scopeExpansionProposal:null,
  stopReason:"NO_PRODUCTIVE_NEXT_STEP",discardedOrDeferredRefs:["GAP-DEPENDENCY-CONTRACT"],confidence:"MEDIUM"
}' >"$tmp/valid-stop-no-evidence.json"
python3 "$checkpoint" assess-response "$tmp/request.json" "$tmp/valid-stop-no-evidence.json" "$tmp/valid-stop-no-evidence.validation.json"

# A second host-derived request closes every gap, while a stricter TG04 fixture
# sufficiency threshold leaves final synthesis eligible for the checkpoint.
complete="$tmp/complete"; mkdir -p "$complete/evidence" "$complete/validation"
reset_telemetry; mana_trajectory_telemetry_init "$complete" tg05-complete v2
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-access-policy completed --acceptance-criterion-refs AC-SYN-02 --evidence-gap-refs GAP-AUTHZ-CHECK --evidence-added-refs EV-AUTHZ
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-signal-api completed --acceptance-criterion-refs AC-SYN-01 --evidence-gap-refs GAP-COMMIT-HOOK --evidence-added-refs EV-COMMIT
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-delivery-callback completed --acceptance-criterion-refs AC-SYN-01 --evidence-gap-refs GAP-DELIVERY-GUARANTEE --evidence-added-refs EV-DELIVERY
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-profile-index completed --acceptance-criterion-refs AC-SYN-02 --evidence-gap-refs GAP-DEPENDENCY-CONTRACT --evidence-added-refs EV-DEPENDENCY
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-signal-api completed --acceptance-criterion-refs AC-SYN-02 --evidence-gap-refs GAP-RESULT-VISIBILITY --evidence-added-refs EV-VISIBILITY
complete_events="$complete/evidence/analysis-trajectory-events-v1.jsonl"
python3 "$state" derive-ledger "$mission" "$complete_events" "$complete/validation/ledger.json"
jq '.evidenceSufficiency.minimumEvidenceRefsPerAcceptanceCriterion=4' "$drift_config" >"$complete/validation/drift-config.json"
cp "$observation" "$complete/validation/observation.json"
python3 "$detector" analyze "$mission" "$complete/validation/ledger.json" "$complete_events" "$complete/validation/drift-config.json" "$complete/validation/observation.json" "$complete/validation/recommendation.json"
jq -n '{schemaVersion:"mana.analysis-trajectory.checkpoint-input/v1",triggerReasons:["FINAL_SYNTHESIS_CHECKPOINT"],nextActionProposals:[{actionId:"action-confirm-synthesis",actionKind:"inspect-evidence-package",targetScopeRef:"scope-signal-api",justificationGoalRefs:["AC-SYN-01"],justificationGapRefs:[],mandatoryConstraintRefs:[],expectedEvidence:"The bounded final evidence-package reference.",decisionDependencies:[],scopeExpansionRequired:false,estimatedBudgetDelta:{providerCalls:0,tokenProxy:10}}]}' >"$complete/validation/checkpoint-input.json"
python3 "$checkpoint" build-request "$mission" "$complete/validation/ledger.json" "$complete_events" "$complete/validation/drift-config.json" "$complete/validation/observation.json" "$complete/validation/checkpoint-input.json" "$complete/validation/recommendation.json" "$complete/validation/request.json"
complete_mission_id="$(jq -r '.checkpointEnvelope.missionContract.missionId' "$complete/validation/request.json")"
complete_mission_hash="$(jq -r '.checkpointEnvelope.missionContract.contentHash' "$complete/validation/request.json")"
jq -n --arg mission_id "$complete_mission_id" --arg mission_hash "$complete_mission_hash" '{
  schemaVersion:"mana.analysis-trajectory.trajectory-checkpoint-response/v1",missionId:$mission_id,missionHash:$mission_hash,missionRevision:1,
  outcome:"STOP_SUFFICIENT_EVIDENCE",objectiveRestatement:"Stop after the synthetic mission goals and mandatory constraint have bounded evidence.",
  supportingGoalRefs:["AC-SYN-01","AC-SYN-02"],supportingConstraintRefs:["CONSTRAINT-AUTHZ-01"],supportingGapRefs:["GAP-AUTHZ-CHECK","GAP-COMMIT-HOOK","GAP-DELIVERY-GUARANTEE","GAP-DEPENDENCY-CONTRACT","GAP-RESULT-VISIBILITY"],supportingEvidenceRefs:["EV-AUTHZ","EV-COMMIT","EV-DELIVERY","EV-DEPENDENCY","EV-VISIBILITY"],
  recommendedNextAction:null,scopeExpansionProposal:null,stopReason:"EVIDENCE_SUFFICIENT",discardedOrDeferredRefs:[],confidence:"HIGH"
}' >"$complete/validation/stop-sufficient.json"
python3 "$checkpoint" assess-response "$complete/validation/request.json" "$complete/validation/stop-sufficient.json" "$complete/validation/stop-sufficient.validation.json"

# Host-side semantic rejections never receive a model repair call.
jq '.missionHash="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' "$tmp/valid-on-track.json" >"$tmp/wrong-hash.json"
assess_invalid 4 SEMANTIC_INVALID WRONG_MISSION_HASH "$tmp/wrong-hash.json" "$tmp/wrong-hash.validation.json"
jq '.missionRevision=2' "$tmp/valid-on-track.json" >"$tmp/wrong-revision.json"
assess_invalid 4 SEMANTIC_INVALID WRONG_MISSION_REVISION "$tmp/wrong-revision.json" "$tmp/wrong-revision.validation.json"
jq '.supportingGoalRefs=["AC-UNKNOWN"]' "$tmp/valid-on-track.json" >"$tmp/unknown-ref.json"
assess_invalid 4 SEMANTIC_INVALID UNKNOWN_GOAL_REF "$tmp/unknown-ref.json" "$tmp/unknown-ref.validation.json"
jq '.recommendedNextAction.justificationGoalRefs=[] | .recommendedNextAction.justificationGapRefs=[] | .recommendedNextAction.mandatoryConstraintRefs=[]' "$tmp/valid-on-track.json" >"$tmp/unsupported-action.json"
assess_invalid 4 SEMANTIC_INVALID UNSUPPORTED_NEXT_ACTION "$tmp/unsupported-action.json" "$tmp/unsupported-action.validation.json"
jq '.recommendedNextAction.targetScopeRef="scope-archive-search" | .recommendedNextAction.scopeExpansionRequired=false' "$tmp/valid-on-track.json" >"$tmp/unapproved-action.json"
assess_invalid 4 SEMANTIC_INVALID UNAPPROVED_SCOPE_EXPANSION "$tmp/unapproved-action.json" "$tmp/unapproved-action.validation.json"
jq --argjson action "$open_action" '.recommendedNextAction=$action | .supportingGapRefs=["GAP-DELIVERY-GUARANTEE"]' "$tmp/valid-on-track.json" >"$tmp/open-decision.json"
assess_invalid 4 SEMANTIC_INVALID OPEN_DECISION_ASSUMPTION "$tmp/open-decision.json" "$tmp/open-decision.validation.json"
jq '.objectiveRestatement="Select the architecture option for the delivery mode."' "$tmp/valid-on-track.json" >"$tmp/open-decision-prose.json"
assess_invalid 4 SEMANTIC_INVALID OPEN_DECISION_ASSUMPTION "$tmp/open-decision-prose.json" "$tmp/open-decision-prose.validation.json"
jq --argjson action "$rejected_action" '.recommendedNextAction=$action' "$tmp/valid-on-track.json" >"$tmp/rejected-reopen.json"
assess_invalid 4 SEMANTIC_INVALID REJECTED_HYPOTHESIS_REOPENED "$tmp/rejected-reopen.json" "$tmp/rejected-reopen.validation.json"
jq '.recommendedNextAction.estimatedBudgetDelta.providerCalls=1000' "$tmp/valid-on-track.json" >"$tmp/hard-budget-action.json"
assess_invalid 4 SEMANTIC_INVALID HARD_BUDGET_VIOLATION "$tmp/hard-budget-action.json" "$tmp/hard-budget-action.validation.json"
jq '.objectiveRestatement="Implement coding tasks and estimate story points."' "$tmp/valid-on-track.json" >"$tmp/implementation-leak.json"
assess_invalid 4 SEMANTIC_INVALID IMPLEMENTATION_TASK_LEAKAGE "$tmp/implementation-leak.json" "$tmp/implementation-leak.validation.json"
jq '.outcome="STOP_NO_NEW_EVIDENCE" | .stopReason="NO_PRODUCTIVE_NEXT_STEP"' "$tmp/valid-on-track.json" >"$tmp/contradictory.json"
assess_invalid 4 SEMANTIC_INVALID CONTRADICTORY_OUTCOME_FIELDS "$tmp/contradictory.json" "$tmp/contradictory.validation.json"
jq '.missionContract={objective:"attempted mutation"}' "$tmp/valid-on-track.json" >"$tmp/mission-mutation.json"
assess_invalid 3 STRUCTURAL_INVALID FIELDS_DIFFER "$tmp/mission-mutation.json" "$tmp/mission-mutation.validation.json"

# Only a structural failure can consume the single repair allowance.
jq 'del(.confidence) | .objectiveRestatement="SHOULD_NOT_ENTER_REPAIR_PROMPT"' "$tmp/valid-on-track.json" >"$tmp/structural-invalid.json"
assess_invalid 3 STRUCTURAL_INVALID FIELDS_DIFFER "$tmp/structural-invalid.json" "$tmp/structural.validation.json"
jq -e '.repairPermitted == true' "$tmp/structural.validation.json" >/dev/null || fail 'first structural failure did not permit one repair'
python3 "$checkpoint" render-repair-prompt "$tmp/request.json" "$tmp/structural.validation.json" "$tmp/repair-prompt.txt"
if rg -Fq 'SHOULD_NOT_ENTER_REPAIR_PROMPT' "$tmp/repair-prompt.txt"; then fail 'repair prompt leaked the invalid response'; fi
rg -Fq 'SANITIZED_VALIDATION_ERRORS_JSON' "$tmp/repair-prompt.txt" || fail 'repair prompt omits sanitized validation errors'
rg -Fq 'ORIGINAL_BOUNDED_REQUEST_JSON' "$tmp/repair-prompt.txt" || fail 'repair prompt omits original bounded request'
assess_invalid 3 STRUCTURAL_INVALID FIELDS_DIFFER "$tmp/structural-invalid.json" "$tmp/second-structural.validation.json" 2
jq -e '.repairPermitted == false' "$tmp/second-structural.validation.json" >/dev/null || fail 'second invalid result permitted another repair'

python3 "$checkpoint" simulate "$shadow_config" "$tmp/request.json" "$tmp/structural-invalid.json" "$tmp/valid-on-track.json" "$tmp/repaired-run.json"
python3 "$checkpoint" simulate "$shadow_config" "$tmp/request.json" "$tmp/structural-invalid.json" "$tmp/structural-invalid.json" "$tmp/failed-repair-run.json"
python3 "$checkpoint" simulate "$shadow_config" "$tmp/request.json" "$tmp/wrong-hash.json" "$tmp/valid-on-track.json" "$tmp/semantic-failure-run.json"
python3 "$checkpoint" simulate "$off_config" /not/read/request.json /not/read/primary.json /not/read/repair.json "$tmp/off-run.json"
python3 "$checkpoint" record-run "$shadow_config" "$tmp/request.json" fixture fixture-model high "$tmp/valid-on-track.validation.json" - "$tmp/valid-on-track.json" "$tmp/recorded-live-shape-run.json"
if python3 "$checkpoint" record-run "$shadow_config" "$tmp/request.json" fixture fixture-model high "$tmp/valid-on-track.validation.json" - "$tmp/valid-reanchor.json" "$tmp/mismatched-response-run.json" >/dev/null 2>&1; then
  fail 'run recorder accepted a response that did not match its validation hash'
fi
[ ! -e "$tmp/mismatched-response-run.json" ] || fail 'mismatched response published a run record'
for run in "$tmp/repaired-run.json" "$tmp/failed-repair-run.json" "$tmp/semantic-failure-run.json" "$tmp/off-run.json" "$tmp/recorded-live-shape-run.json"; do
  python3 "$schema_test" "$schema_dir/trajectory-checkpoint-run-v1.schema.json" "$run" || fail "invalid run schema: $run"
  jq -e '.callCounts.total <= 2 and .callCounts.primary <= 1 and .callCounts.structuralRepair <= 1 and .effects == {controlFlowChanged:false,finalArtifactsChanged:false,enforcementApplied:false}' "$run" >/dev/null || fail "unbounded/enforcing run: $run"
done
jq -e '.status == "ACCEPTED" and .outcome == "ON_TRACK" and .callCounts == {primary:1,structuralRepair:1,total:2} and [.calls[].validationResult] == ["STRUCTURAL_INVALID","VALID"]' "$tmp/repaired-run.json" >/dev/null || fail 'successful repair run is wrong'
jq -e '.status == "NEEDS_OWNER_REVIEW" and .outcome == "NEEDS_OWNER_REVIEW" and .callCounts.total == 2' "$tmp/failed-repair-run.json" >/dev/null || fail 'failed repair did not fail closed'
jq -e '.status == "NEEDS_OWNER_REVIEW" and .callCounts == {primary:1,structuralRepair:0,total:1}' "$tmp/semantic-failure-run.json" >/dev/null || fail 'semantic failure incorrectly received a repair'
jq -e '.mode == "OFF" and .status == "DISABLED" and .outcome == null and .calls == [] and .callCounts.total == 0' "$tmp/off-run.json" >/dev/null || fail 'OFF mode added a call'

# TG01 route is reused, but TG05 is not wired into the public runtime yet.
# shellcheck disable=SC1091
. "$root/scripts/lib/story-start-stage-routing.sh"
mana_story_start_stage_resolve codex trajectory-checkpoint '' '' false false '' '' || fail 'trajectory-checkpoint route resolution failed'
[ "$MANA_STORY_START_ROUTE_MODEL:$MANA_STORY_START_ROUTE_EFFORT" = 'gpt-5.6-terra:high' ] || fail 'TG01 trajectory-checkpoint route changed'
if rg -n 'analysis-trajectory-checkpoint|trajectory-checkpoint-request' "$root/scripts/run-profile.sh" "$root/scripts/lib/story-start-scope-v2.sh" >/dev/null; then fail 'TG05 entered public Story Start control flow'; fi
if rg -n 'subprocess|urllib|requests|httpx|socket|curl' "$checkpoint" >/dev/null; then fail 'TG05 host helper contains provider/network dispatch'; fi
smoke="$root/scripts/analysis-trajectory-checkpoint-smoke.sh"
[ -x "$smoke" ] || fail 'TG05 live smoke harness is missing or non-executable'
(
  unset MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_LIVE MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_CREDENTIALS_READY MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_PROVIDER
  if "$smoke" "$tmp/request.json" "$tmp/disabled-smoke-artifacts" >/dev/null 2>"$tmp/disabled-smoke.err"; then
    fail 'live smoke ran without explicit enablement'
  fi
)
[ ! -e "$tmp/disabled-smoke-artifacts" ] || fail 'disabled live smoke wrote artifacts'

echo 'Analysis Trajectory Guard TG05 checkpoint tests passed (bounded fixture calls, zero token/network usage)'
