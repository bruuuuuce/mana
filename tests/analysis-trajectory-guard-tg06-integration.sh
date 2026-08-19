#!/usr/bin/env bash
# TG06 zero-token upstream integration, enforcement, and Scope v2 compatibility.
# shellcheck disable=SC1091,SC2034
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
package="$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json"
discovery="$root/tests/fixtures/story-start-scope-v2/discovery/provider-output.json"
triage="$root/tests/fixtures/story-start-scope-v2/triage/provider-output.json"
plan="$root/tests/fixtures/story-start-scope-v2/planner/provider-output.json"
expansion_observation="$root/tests/fixtures/analysis-trajectory-guard/tg06-scope-expansion-observation-v1.json"
integration="$root/scripts/lib/analysis-trajectory-integration.py"
schema_validator="$root/tests/lib/json_schema_subset.py"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-trajectory-tg06.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

# shellcheck source=../scripts/lib/provider-dispatch.sh
. "$root/scripts/lib/provider-dispatch.sh"
# shellcheck source=../scripts/lib/story-start-stage-routing.sh
. "$root/scripts/lib/story-start-stage-routing.sh"
# shellcheck source=../scripts/lib/analysis-trajectory-telemetry.sh
. "$root/scripts/lib/analysis-trajectory-telemetry.sh"
# shellcheck source=../scripts/lib/analysis-trajectory-integration.sh
. "$root/scripts/lib/analysis-trajectory-integration.sh"
# shellcheck source=../scripts/lib/story-start-scope-v2.sh
. "$root/scripts/lib/story-start-scope-v2.sh"

provider_stub="$tmp/provider-stub"
# The single-quoted lines are the generated stub program, not expansions in
# this test process.
# shellcheck disable=SC2016
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s\n" call >> "$TG06_CALL_COUNT"' \
  'last=""; for argument in "$@"; do last="$argument"; done' \
  'printf "marker=%s discovery=%s\n" "${last:0:40}" "${TG06_DISCOVERY:-missing}" >> "$TG06_STUB_LOG"' \
  'case "$last" in' \
  '  *MANA\ TRAJECTORY\ CHECKPOINT*)' \
  '    if [ "${TG06_CHECKPOINT_MODE:-reanchor}" = invalid ]; then printf "%s\n" "{}"; exit 0; fi' \
  '    request="$(printf "%s\n" "$last" | tail -1)"' \
  '    printf "%s\n" "$request" | jq '\''{schemaVersion:"mana.analysis-trajectory.trajectory-checkpoint-response/v1",missionId:.checkpointEnvelope.missionContract.missionId,missionHash:.checkpointEnvelope.missionContract.contentHash,missionRevision:.checkpointEnvelope.missionContract.revision,outcome:"REANCHOR_REQUIRED",objectiveRestatement:.checkpointEnvelope.missionContract.objective,supportingGoalRefs:.checkpointEnvelope.nextActionProposals[0].justificationGoalRefs,supportingConstraintRefs:.checkpointEnvelope.nextActionProposals[0].mandatoryConstraintRefs,supportingGapRefs:.checkpointEnvelope.nextActionProposals[0].justificationGapRefs,supportingEvidenceRefs:[],recommendedNextAction:.checkpointEnvelope.nextActionProposals[0],scopeExpansionProposal:null,stopReason:null,discardedOrDeferredRefs:[],confidence:"HIGH"}'\''' \
  '    ;;' \
  '  *COMPACT_DISCOVERY_PACKAGE*) cat "$TG06_DISCOVERY" ;;' \
  '  *COMPACT_DISCOVERY_V2*) cat "$TG06_TRIAGE" ;;' \
  '  *INVALID_IMPLEMENTATION_PLAN_V2*) cat "$TG06_PLAN" ;;' \
  '  *SCOPE_TRIAGE_V2*) cat "$TG06_PLAN" ;;' \
  '  *) exit 9 ;;' \
  'esac' > "$provider_stub"
chmod +x "$provider_stub"
bash -n "$provider_stub" || fail 'generated provider stub has invalid shell syntax'
cp "$provider_stub" "$tmp/codex"

export MANA_USER_LEARNING_ALLOW_STUB=true
export MANA_USER_LEARNING_STUB_COMMAND="$provider_stub"
export TG06_DISCOVERY="$discovery" TG06_TRIAGE="$triage" TG06_PLAN="$plan"
export TG06_STUB_LOG="$tmp/stub.log"
export MANA_STORY_START_STAGE_TRAJECTORY_CHECKPOINT_MODEL=checkpoint-model
export MANA_STORY_START_STAGE_TRAJECTORY_CHECKPOINT_EFFORT=high

run_public() {
  local mode="$1" label="$2" project active
  project="$tmp/public-$label"
  mkdir -p "$project"
  cp "$package" "$project/context.json"
  TG06_CALL_COUNT="$tmp/$label.calls"
  : > "$TG06_CALL_COUNT"
  export TG06_CALL_COUNT
  if ! MANA_UPDATE_CHECK=off \
  MANA_STORY_START_SCOPE_VERSION=v2 \
  MANA_STORY_START_CONTEXT=context.json \
  MANA_ANALYSIS_TRAJECTORY_MODE="$mode" \
  MANA_ANALYSIS_TRAJECTORY_TELEMETRY=false \
  PATH="$tmp:$PATH" \
    "$root/scripts/run-profile.sh" story-start --project-root "$project" --codex \
      > "$tmp/$label.out" 2> "$tmp/$label.err"; then
    sed -n '1,160p' "$tmp/$label.err" >&2
    sed -n '1,40p' "$TG06_STUB_LOG" >&2
    fail "public $mode run failed"
  fi
  active="$(sed -n '1p' "$project/.mana/active-workspace")"
  PUBLIC_WORKSPACE="$project/$active"
  PUBLIC_CALLS="$(wc -l < "$TG06_CALL_COUNT" | tr -d ' ')"
}

# 1. OFF is the exact public compatibility path: three existing calls and no
# trajectory artifacts. The governed plan becomes the byte-level baseline.
run_public off off
[ "$PUBLIC_CALLS" = 3 ] || fail 'feature off changed the existing provider call count'
[ ! -e "$PUBLIC_WORKSPACE/evidence/analysis-trajectory-mission-v1.json" ] || fail 'feature off published a Mission Contract'
[ ! -e "$PUBLIC_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" ] || fail 'feature off published an integration sidecar'
cp "$PUBLIC_WORKSPACE/planning/story-start-implementation-plan-v2.json" "$tmp/off-plan.json"

# 2. SHADOW publishes host state and diagnostics but does not change flow or output.
run_public shadow shadow
[ "$PUBLIC_CALLS" = 3 ] || fail 'shadow mode added a checkpoint call'
cmp -s "$tmp/off-plan.json" "$PUBLIC_WORKSPACE/planning/story-start-implementation-plan-v2.json" || fail 'shadow changed the governed Scope v2 plan'
jq -e '.mode=="SHADOW" and .controlDecision=="CONTINUE" and .acceptedOutcome==null and (.effects.controlFlowChanged|not) and .effects.checkpointCalls==0' \
  "$PUBLIC_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 'shadow semantics are not passive'

# 3. An on-track ENFORCE run adds no checkpoint tax and preserves Scope v2.
run_public enforce enforce-on-track
[ "$PUBLIC_CALLS" = 3 ] || fail 'on-track enforcement added a checkpoint call'
cmp -s "$tmp/off-plan.json" "$PUBLIC_WORKSPACE/planning/story-start-implementation-plan-v2.json" || fail 'on-track enforcement changed Scope v2 semantics'
jq -e '.mode=="ENFORCE" and .acceptedOutcome=="ON_TRACK" and .controlDecision=="CONTINUE" and .effects.checkpointCalls==0' \
  "$PUBLIC_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 'on-track enforcement was not zero-checkpoint'

new_guard_workspace() {
  local label="$1" mode="$2"
  GUARD_WORKSPACE="$tmp/$label"
  mkdir -p "$GUARD_WORKSPACE/evidence" "$GUARD_WORKSPACE/validation"
  MANA_ANALYSIS_TRAJECTORY_MODE="$mode"
  MANA_ANALYSIS_TRAJECTORY_TELEMETRY=true
  export MANA_ANALYSIS_TRAJECTORY_MODE MANA_ANALYSIS_TRAJECTORY_TELEMETRY
  unset MANA_ANALYSIS_TRAJECTORY_OBSERVATION_PATH MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_INPUT_PATH MANA_ANALYSIS_TRAJECTORY_SCOPE_APPROVAL_PATH MANA_ANALYSIS_TRAJECTORY_REANCHOR_HEADER
  MANA_TRAJECTORY_TELEMETRY_ENABLED=false
  MANA_TRAJECTORY_TELEMETRY_EVENTS=""
  MANA_TRAJECTORY_TELEMETRY_SUMMARY=""
  MANA_TRAJECTORY_TELEMETRY_RUN_ID=""
  mana_trajectory_telemetry_init "$GUARD_WORKSPACE" story-synthetic-alert-001
  mana_trajectory_guard_initialize "$package" "$GUARD_WORKSPACE"
  mana_trajectory_telemetry_emit analysis_started public_pipeline start codex none none scope-v2/public started
}

emit_repeated_drift() {
  mana_trajectory_telemetry_emit provider_iteration_completed provider_result discovery codex discovery-model high scope-v2/discovery completed \
    --acceptance-criterion-refs AC-01 --evidence-added-refs evidence-initial
  mana_trajectory_telemetry_emit provider_iteration_completed provider_result discovery codex discovery-model high scope-v2/discovery completed
  mana_trajectory_telemetry_emit provider_iteration_completed provider_result discovery codex discovery-model high scope-v2/discovery completed
}

# 4. Unrelated/repeated work triggers exactly one checkpoint and its validated
# re-anchor becomes one compact transient header for the next provider handoff.
new_guard_workspace reanchor enforce
emit_repeated_drift
TG06_CALL_COUNT="$tmp/reanchor.calls"; : > "$TG06_CALL_COUNT"
TG06_CHECKPOINT_MODE=reanchor
export TG06_CALL_COUNT TG06_CHECKPOINT_MODE
mana_trajectory_guard_boundary stub root-model "$GUARD_WORKSPACE" PROVIDER_COMPLETION_BOUNDARY || fail 'valid re-anchor was not applied'
[ "$(wc -l < "$TG06_CALL_COUNT" | tr -d ' ')" = 1 ] || fail 're-anchor did not use exactly one checkpoint call'
jq -e '.acceptedOutcome=="REANCHOR_REQUIRED" and .controlDecision=="REANCHOR" and .effects.checkpointCalls==1 and .routing.model=="checkpoint-model" and .routing.effort=="high"' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 're-anchor application or TG01 route diagnostics are wrong'
jq -e '.lastCheckpoint.outcome=="REANCHOR_REQUIRED" and .lastCheckpoint.eventRef!=null' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-ledger-v1.json" >/dev/null || fail 'Ledger did not record the accepted checkpoint transition'
jq -e '.measurements.deterministic.eventCount>0 and .measurements.model.checkpointCalls==1 and .measurements.model.usageAvailability=="UNAVAILABLE"' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 'deterministic and model overhead are not separated'
[ -f "$MANA_ANALYSIS_TRAJECTORY_REANCHOR_HEADER" ] || fail 'compact re-anchor header was not produced'
jq -e 'has("objective") and (.singleRecommendedNextAction.actionId=="action-return-to-active-gap") and (keys|length)==9' \
  "$MANA_ANALYSIS_TRAJECTORY_REANCHOR_HEADER" >/dev/null || fail 're-anchor header is not compact and bounded'
mana_trajectory_guard_cleanup

# 5-6. A dependency expansion is a structured proposal. Without approval it
# halts; with a matching host approval it creates revision 2 and preserves history.
new_guard_workspace expansion-pending enforce
python3 "$integration" evaluate "$GUARD_WORKSPACE" "$MANA_TRAJECTORY_TELEMETRY_EVENTS" ENFORCE NEXT_ACTION_BOUNDARY \
  codex checkpoint-model high "$expansion_observation" -
python3 "$integration" apply-direct "$GUARD_WORKSPACE" -
jq -e '.controlDecision=="HALT_OWNER_REVIEW" and .failureCode=="scope-approval-required" and (.scopeExpanded|not)' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 'unapproved expansion did not halt for owner review'
jq -e '.approvalStatus=="PENDING" and .targetScopeRef=="scope-v2/synthetic-dependency"' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-scope-expansion-v1.json" >/dev/null || fail 'pending expansion proposal is missing'
python3 "$schema_validator" "$root/contracts/analysis-trajectory/scope-expansion-proposal-v1.schema.json" \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-scope-expansion-v1.json"

new_guard_workspace expansion-approved enforce
python3 "$integration" evaluate "$GUARD_WORKSPACE" "$MANA_TRAJECTORY_TELEMETRY_EVENTS" ENFORCE NEXT_ACTION_BOUNDARY \
  codex checkpoint-model high "$expansion_observation" -
mission="$GUARD_WORKSPACE/evidence/analysis-trajectory-mission-v1.json"
jq '{schemaVersion:"mana.analysis-trajectory.mission-revision-request/v1",missionId:.missionId,expectedRevision:.revision,changeKind:"APPROVED_SCOPE_EXPANSION",proposalApprovalRef:"approval-synthetic-dependency",approvalAuthority:"synthetic-owner",acceptedScopeRefs:["scope-v2/synthetic-dependency"],semanticChanges:{scopePolicy:(.scopePolicy | .requirementDependencyScopeRefs += ["scope-v2/synthetic-dependency"] | .requirementDependencyScopeRefs |= sort | .proposedExpansionScopeRefs=[])}}' \
  "$mission" > "$tmp/approval.json"
python3 "$integration" apply-direct "$GUARD_WORKSPACE" "$tmp/approval.json"
jq -e '.revision==2 and (.allowedEvidenceScopeRefs|index("scope-v2/synthetic-dependency")!=null) and .revisionTransition.proposalApprovalRef=="approval-synthetic-dependency"' \
  "$mission" >/dev/null || fail 'approved expansion did not create a host-owned mission revision'
jq -e '.revisionCount==2 and (.revisions|length)==2' "$GUARD_WORKSPACE/validation/analysis-trajectory-mission-history-v1.json" >/dev/null || fail 'mission revision history was not preserved'
jq -e '.controlDecision=="CONTINUE" and .scopeExpanded and .missionCorrelation.missionRevision==2' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 'approved expansion did not resume through the revised mission'

# 7. Sufficient evidence stops acquisition cleanly and proceeds to downstream Scope v2.
new_guard_workspace sufficient enforce
while IFS=$'\t' read -r goal gap; do
  mana_trajectory_telemetry_emit evidence_gap_closed provider_result discovery codex discovery-model high scope-v2/discovery completed \
    --acceptance-criterion-refs "$goal" --evidence-gap-refs "$gap" --evidence-added-refs "evidence-${goal}"
done < <(jq -r '.evidenceGaps[] | [.relatedAcceptanceCriterionRefs[0],.gapId] | @tsv' "$GUARD_WORKSPACE/evidence/analysis-trajectory-mission-v1.json")
python3 "$integration" evaluate "$GUARD_WORKSPACE" "$MANA_TRAJECTORY_TELEMETRY_EVENTS" ENFORCE PROVIDER_COMPLETION_BOUNDARY codex checkpoint-model high - -
python3 "$integration" apply-direct "$GUARD_WORKSPACE" -
jq -e '.recommendationCorrelation.outcome=="STOP_SUFFICIENT_EVIDENCE" and .acceptedOutcome=="STOP_SUFFICIENT_EVIDENCE" and .controlDecision=="PROCEED_DOWNSTREAM"' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 'sufficient evidence did not stop cleanly for downstream synthesis'

# 8. No-new-evidence stop retains explicit unresolved gaps in the downstream package.
new_guard_workspace no-new-evidence enforce
for _ in 1 2 3; do
  mana_trajectory_telemetry_emit provider_iteration_completed provider_result discovery codex discovery-model high scope-v2/discovery completed
done
python3 "$integration" evaluate "$GUARD_WORKSPACE" "$MANA_TRAJECTORY_TELEMETRY_EVENTS" ENFORCE PROVIDER_COMPLETION_BOUNDARY codex checkpoint-model high - -
python3 "$integration" apply-direct "$GUARD_WORKSPACE" -
jq -e '.acceptedOutcome=="STOP_NO_NEW_EVIDENCE" and .controlDecision=="PROCEED_DOWNSTREAM"' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 'no-new-evidence stop did not finalize honestly'
jq -e '(.openEvidenceGapRefs|length)==3' "$GUARD_WORKSPACE/evidence/analysis-trajectory-evidence-package-v1.json" >/dev/null || fail 'no-new-evidence package lost unresolved gaps'

# 9. A hard budget stop is partial and never claims downstream readiness.
new_guard_workspace hard-budget enforce
for _ in $(seq 1 33); do
  mana_trajectory_telemetry_emit provider_iteration_completed provider_result discovery codex discovery-model high scope-v2/discovery completed
done
python3 "$integration" evaluate "$GUARD_WORKSPACE" "$MANA_TRAJECTORY_TELEMETRY_EVENTS" ENFORCE PROVIDER_COMPLETION_BOUNDARY codex checkpoint-model high - -
python3 "$integration" apply-direct "$GUARD_WORKSPACE" -
jq -e '.acceptedOutcome=="STOP_HARD_BUDGET" and .controlDecision=="HALT_PARTIAL" and .failureCode=="hard-budget-reached"' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 'hard-budget stop was not partial and explicit'

# 10. Two structurally invalid checkpoint responses consume at most two calls
# and enforcement fails closed without a legacy fallback.
new_guard_workspace invalid-checkpoint enforce
emit_repeated_drift
TG06_CALL_COUNT="$tmp/invalid.calls"; : > "$TG06_CALL_COUNT"
TG06_CHECKPOINT_MODE=invalid
export TG06_CALL_COUNT TG06_CHECKPOINT_MODE
if mana_trajectory_guard_boundary stub root-model "$GUARD_WORKSPACE" PROVIDER_COMPLETION_BOUNDARY; then
  fail 'invalid checkpoint after repair continued unguarded'
fi
[ "$(wc -l < "$TG06_CALL_COUNT" | tr -d ' ')" = 2 ] || fail 'invalid checkpoint did not respect the two-call bound'
jq -e '.controlDecision=="HALT_OWNER_REVIEW" and .acceptedOutcome=="NEEDS_OWNER_REVIEW" and .effects.checkpointCalls==2 and .checkpointCorrelation.callCount==2 and (.effects.legacyFallbackUsed|not)' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 'invalid checkpoint did not fail closed'

# 11 and 14-15. Artifacts claim invocation-level observability only, expose the
# effective TG01 route, validate against versioned contracts, and contain no raw bodies.
for pair in \
  "trajectory-integration-run-v1.schema.json validation/analysis-trajectory-integration-run-v1.json" \
  "trajectory-evidence-package-v1.schema.json evidence/analysis-trajectory-evidence-package-v1.json"; do
  schema="${pair%% *}"; artifact="${pair#* }"
  python3 "$schema_validator" "$root/contracts/analysis-trajectory/$schema" "$GUARD_WORKSPACE/$artifact"
done
jq -e '.observability.granularity=="PROVIDER_INVOCATION_LEVEL" and (.observability.unsupportedFacts|index("provider-internal-tool-calls")!=null)' \
  "$GUARD_WORKSPACE/validation/analysis-trajectory-integration-run-v1.json" >/dev/null || fail 'opaque-provider boundary is overstated'
if rg -i 'rawprompt|rawresponse|conversationhistory|chain.?of.?thought|credential|secret|jira.?body|source.?code' \
  "$GUARD_WORKSPACE/evidence" "$GUARD_WORKSPACE/validation" >/dev/null; then
  fail 'trajectory artifacts leaked a prohibited raw field'
fi

# 12-13. The actual downstream plan still separates classifications and never
# aggregates mutually exclusive alternatives.
jq -e '
  (.basePlan|type=="array") and (.requiredEnablers|type=="array") and
  (.conditionalBranches|type=="array") and (.relatedFindings|type=="array") and
  ([.scenarioEstimates.scenarios[].selectedBranchRefs[]] | length > 0) and
  (.scenarioEstimates.finalCommittedEstimate==null)
' "$tmp/off-plan.json" >/dev/null || fail 'downstream Scope v2 separation or exclusive-alternative semantics regressed'

echo 'Analysis Trajectory Guard TG06 integration tests passed (zero real provider/network calls; fake providers only)'
