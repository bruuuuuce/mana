#!/usr/bin/env bash
# TG03 deterministic Mission Contract, Ledger, and envelope acceptance suite.
set -euo pipefail

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
state="$root/scripts/lib/analysis-trajectory-state.py"
fixture_dir="$root/tests/fixtures/analysis-trajectory-guard"
story="$fixture_dir/tg03-story-package-v1.json"
seed="$fixture_dir/tg03-mission-seed-v1.json"
checkpoint_input="$fixture_dir/tg03-checkpoint-input-v1.json"
traces="$fixture_dir/tg00-traces-v1.json"
schema_test="$root/tests/lib/json_schema_subset.py"
schema_dir="$root/contracts/analysis-trajectory"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-tg03-state.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
expect_failure() { if "$@" >"$tmp/expected-failure.out" 2>"$tmp/expected-failure.err"; then fail "command unexpectedly succeeded: $*"; fi; }

mission="$tmp/mission-r1.json"
history="$tmp/mission-history.json"
python3 "$state" create-mission "$story" "$seed" "$mission" "$history" || fail 'mission creation failed'
python3 "$state" validate-mission "$mission" || fail 'mission host validation failed'
python3 "$state" validate-history "$history" || fail 'history host validation failed'
python3 "$schema_test" "$schema_dir/mission-seed-v1.schema.json" "$seed" || fail 'mission seed schema failed'
python3 "$schema_test" "$schema_dir/mission-contract-v1.schema.json" "$mission" || fail 'mission schema failed'
python3 "$schema_test" "$schema_dir/mission-history-v1.schema.json" "$history" || fail 'history schema failed'
python3 "$schema_test" "$schema_dir/checkpoint-input-v1.schema.json" "$checkpoint_input" || fail 'checkpoint-input schema failed'
jq -e '
  .schemaVersion == "mana.analysis-trajectory.mission-contract/v1" and
  .revision == 1 and
  .provenance == {ownership:"host",generator:"analysis-trajectory-state/v1",modelAuthored:false} and
  (.contentHash | test("^sha256:[0-9a-f]{64}$")) and
  .acceptanceCriterionRefs == ["AC-SYN-01","AC-SYN-02"] and
  .mandatoryConstraintRefs == ["CONSTRAINT-AUTHZ-01"] and
  (.scopePolicy.proposedExpansionScopeRefs | index("scope-archive-search") != null) and
  (.allowedEvidenceScopeRefs | index("scope-archive-search") == null) and
  (.allowedEvidenceScopeRefs | index("scope-security-controls") != null)
' "$mission" >/dev/null || fail 'mission semantics are incomplete'

# Canonicalization makes ID/hash independent of input order and JSON layout.
jq '.normalizedStory.acceptanceCriteria |= reverse' "$story" > "$tmp/story-reordered.json"
jq '
  .authoritativeInputRefs |= reverse |
  .scopePolicy.initialStoryScopeRefs |= reverse |
  .scopePolicy.globalMandatoryScopeRefs |= reverse |
  .evidenceGaps |= reverse |
  .prohibitedActions |= reverse
' "$seed" > "$tmp/seed-reordered.json"
python3 "$state" create-mission "$tmp/story-reordered.json" "$tmp/seed-reordered.json" "$tmp/mission-repeat.json" "$tmp/history-repeat.json" || fail 'repeat mission creation failed'
cmp -s "$mission" "$tmp/mission-repeat.json" || fail 'mission generation is not deterministic/canonical'

# Hash validation detects direct mutation of host-owned content.
jq '.objective = "A model-authored replacement objective."' "$mission" > "$tmp/mission-mutated.json"
expect_failure python3 "$state" validate-mission "$tmp/mission-mutated.json"

# An approved expansion creates revision 2 and preserves revision 1 byte-for-byte semantically.
jq -S '.revisions[0]' "$history" > "$tmp/revision-1-before.json"
jq '{
  schemaVersion:"mana.analysis-trajectory.mission-revision-request/v1",
  missionId:.missionId,
  expectedRevision:.revision,
  changeKind:"APPROVED_SCOPE_EXPANSION",
  proposalApprovalRef:"approval-synthetic-001",
  approvalAuthority:"fixture-owner",
  acceptedScopeRefs:["scope-archive-search"],
  semanticChanges:{scopePolicy:(.scopePolicy |
    .requirementDependencyScopeRefs += ["scope-archive-search"] |
    .proposedExpansionScopeRefs -= ["scope-archive-search"])}
}' "$mission" > "$tmp/revision-request.json"
python3 "$schema_test" "$schema_dir/mission-revision-request-v1.schema.json" "$tmp/revision-request.json" || fail 'revision request schema failed'
python3 "$state" revise-mission "$history" "$tmp/revision-request.json" "$tmp/mission-r2.json" || fail 'approved revision failed'
python3 "$state" validate-history "$history" || fail 'revised history validation failed'
python3 "$schema_test" "$schema_dir/mission-contract-v1.schema.json" "$tmp/mission-r2.json" || fail 'revised mission schema failed'
jq -S '.revisions[0]' "$history" > "$tmp/revision-1-after.json"
cmp -s "$tmp/revision-1-before.json" "$tmp/revision-1-after.json" || fail 'prior mission revision was rewritten'
jq -e --arg old_hash "$(jq -r '.contentHash' "$mission")" '
  .revision == 2 and .contentHash != $old_hash and
  .revisionTransition.previousContentHash == $old_hash and
  (.allowedEvidenceScopeRefs | index("scope-archive-search") != null) and
  (.scopePolicy.proposedExpansionScopeRefs | index("scope-archive-search") == null)
' "$tmp/mission-r2.json" >/dev/null || fail 'revision/hash/scope transition is invalid'
[ "$(jq '.revisionCount' "$history")" -eq 2 ] || fail 'revision history did not append'

# A revision request cannot overwrite IDs, hashes, provenance, or other host fields.
jq --arg mission_id "$(jq -r '.missionId' "$tmp/mission-r2.json")" '{
  schemaVersion:"mana.analysis-trajectory.mission-revision-request/v1",
  missionId:$mission_id,
  expectedRevision:2,
  changeKind:"APPROVED_MISSION_CHANGE",
  proposalApprovalRef:"approval-malicious-001",
  approvalAuthority:"fixture-owner",
  acceptedScopeRefs:[],
  semanticChanges:{contentHash:"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
}' > "$tmp/revision-malicious.json"
expect_failure python3 "$state" revise-mission "$history" "$tmp/revision-malicious.json" "$tmp/mission-malicious.json"

export MANA_ANALYSIS_TRAJECTORY_TELEMETRY=true
# The repository root is resolved at runtime.
# shellcheck disable=SC1091
. "$root/scripts/lib/analysis-trajectory-telemetry.sh"

reset_telemetry() {
  export MANA_TRAJECTORY_TELEMETRY_ENABLED=false
  export MANA_TRAJECTORY_TELEMETRY_EVENTS=""
  export MANA_TRAJECTORY_TELEMETRY_SUMMARY=""
  export MANA_TRAJECTORY_TELEMETRY_RUN_ID=""
}

emit_trace_case() {
  local case_name="$1" workspace="$2" previous_scope="" step action scope
  local -a event_refs
  mkdir -p "$workspace/evidence" "$workspace/validation"
  reset_telemetry
  mana_trajectory_telemetry_init "$workspace" "$case_name" v2
  while IFS= read -r step; do
    action="$(jq -r '.actionKind' <<<"$step")"
    scope="$(jq -r '.targetScopeRef' <<<"$step")"
    event_refs=()
    while IFS= read -r ref; do event_refs+=(--acceptance-criterion-refs "$ref"); done < <(jq -r '.goalRefs[]?' <<<"$step")
    while IFS= read -r ref; do event_refs+=(--evidence-gap-refs "$ref"); done < <(jq -r '.gapRefs[]?' <<<"$step")
    while IFS= read -r ref; do event_refs+=(--decision-refs "$ref"); done < <(jq -r '.decisionRefs[]?' <<<"$step")
    while IFS= read -r ref; do event_refs+=(--evidence-added-refs "$ref"); done < <(jq -r '.evidenceAddedRefs[]?' <<<"$step")
    mana_trajectory_telemetry_emit provider_iteration_completed "$(jq -r '.hostBoundary' <<<"$step")" "$action" fixture fixture-model none "$scope" completed "${event_refs[@]}"
    if [ -n "$previous_scope" ] && [ "$previous_scope" != "$scope" ]; then
      mana_trajectory_telemetry_emit scope_expansion_proposed context_expansion enter-linked-scope fixture fixture-model none "$scope" completed "${event_refs[@]}"
    fi
    if [ "$(jq '.decisionRefs | length' <<<"$step")" -gt 0 ]; then
      mana_trajectory_telemetry_emit open_decision_observed provider_result identify-open-decision fixture fixture-model none "$scope" completed "${event_refs[@]}"
    fi
    previous_scope="$scope"
  done < <(jq -c --arg case_name "$case_name" '.traces[] | select(.case == $case_name) | .steps[]' "$traces")
  mana_trajectory_telemetry_emit analysis_completed public_pipeline complete host none none scope-v2/public completed
}

# Every TG00 topology becomes a deterministic Ledger derived from real TG02 events.
case_count=0
for case_name in $(jq -r '.traces[].case' "$traces"); do
  workspace="$tmp/traces/$case_name"
  emit_trace_case "$case_name" "$workspace" || fail "event construction failed for $case_name"
  events="$workspace/evidence/analysis-trajectory-events-v1.jsonl"
  ledger="$workspace/validation/trajectory-ledger-v1.json"
  python3 "$state" derive-ledger "$mission" "$events" "$ledger" || fail "Ledger derivation failed for $case_name"
  python3 "$state" validate-ledger "$mission" "$events" "$ledger" || fail "Ledger validation failed for $case_name"
  python3 "$schema_test" "$schema_dir/trajectory-ledger-v1.schema.json" "$ledger" || fail "Ledger schema failed for $case_name"
  python3 "$state" derive-ledger "$mission" "$events" "$workspace/validation/trajectory-ledger-repeat.json" || fail "repeat Ledger failed for $case_name"
  cmp -s "$ledger" "$workspace/validation/trajectory-ledger-repeat.json" || fail "Ledger is not deterministic for $case_name"
  jq -e --arg mission_id "$(jq -r '.missionId' "$mission")" --arg mission_hash "$(jq -r '.contentHash' "$mission")" '
    .missionId == $mission_id and .missionHash == $mission_hash and
    .missionRevision == 1 and .lastCheckpoint.outcome == "NONE" and
    (.sourceEvents.eventCount > 0) and (.ledgerHash | test("^sha256:[0-9a-f]{64}$"))
  ' "$ledger" >/dev/null || fail "Ledger correlation failed for $case_name"
  case_count=$((case_count + 1))
done
[ "$case_count" -eq 8 ] || fail 'not every TG00 trace produced a Ledger'

opaque_ledger="$tmp/traces/OPAQUE_PROVIDER_BOUNDARY/validation/trajectory-ledger-v1.json"
jq -e '.observability == "OPAQUE_PROVIDER_BOUNDARY" and .providerCounters.iterationsCompleted > 0 and .providerCounters.iterationsStarted == 0' "$opaque_ledger" >/dev/null || fail 'opaque-provider Ledger invented internal detail'
repeat_ledger="$tmp/traces/DRIFT_REPEAT_NO_EVIDENCE/validation/trajectory-ledger-v1.json"
jq -e '.noNewEvidenceStreak == 2 and (.repeatedTargetCounters | length) == 1' "$repeat_ledger" >/dev/null || fail 'repeat/no-evidence counters are wrong'
rabbit_ledger="$tmp/traces/DRIFT_ARCHITECTURE_RABBIT_HOLE/validation/trajectory-ledger-v1.json"
jq -e '(.openDecisionRefs | index("DEC-DELIVERY-MODE") != null) and (.scopeExpansionProposalRefs | length) > 0' "$rabbit_ledger" >/dev/null || fail 'open decision or expansion refs were lost'

# Evidence gaps have a closed transition and cannot be silently reopened.
gap_workspace="$tmp/gap-transitions"; mkdir -p "$gap_workspace/evidence" "$gap_workspace/validation"
reset_telemetry; mana_trajectory_telemetry_init "$gap_workspace" gap-transitions v2
mana_trajectory_telemetry_emit evidence_gap_opened host_state declare-gap host none none scope-signal-api completed --evidence-gap-refs GAP-COMMIT-HOOK
mana_trajectory_telemetry_emit evidence_gap_closed host_state resolve-gap host none none scope-signal-api completed --evidence-gap-refs GAP-COMMIT-HOOK --evidence-added-refs EV-COMMIT-HOOK
mana_trajectory_telemetry_emit analysis_completed public_pipeline complete host none none scope-v2/public completed
python3 "$state" derive-ledger "$mission" "$gap_workspace/evidence/analysis-trajectory-events-v1.jsonl" "$gap_workspace/validation/ledger.json" || fail 'gap close transition failed'
jq -e '(.resolvedEvidenceGapRefs | index("GAP-COMMIT-HOOK") != null) and ([.evidenceGaps[] | select(.gapId == "GAP-COMMIT-HOOK") | .status] == ["RESOLVED"])' "$gap_workspace/validation/ledger.json" >/dev/null || fail 'resolved gap state was not derived'
jq '
  .nextActionProposals[0].justificationGoalRefs=[] |
  .nextActionProposals[0].justificationGapRefs=["GAP-COMMIT-HOOK"]
' "$checkpoint_input" > "$tmp/resolved-gap-action.json"
expect_failure python3 "$state" build-envelope "$mission" "$gap_workspace/validation/ledger.json" "$gap_workspace/evidence/analysis-trajectory-events-v1.jsonl" "$tmp/resolved-gap-action.json" "$tmp/resolved-gap-envelope.json"
head -n 2 "$gap_workspace/evidence/analysis-trajectory-events-v1.jsonl" > "$tmp/gap-reopen-events.jsonl"
jq -c '.sequence=3 | .eventId=(.runId + "-000003") | .eventType="evidence_gap_opened" | .evidenceAddedRefs=[]' "$gap_workspace/evidence/analysis-trajectory-events-v1.jsonl" | head -n 1 >> "$tmp/gap-reopen-events.jsonl"
expect_failure python3 "$state" derive-ledger "$mission" "$tmp/gap-reopen-events.jsonl" "$tmp/gap-reopen-ledger.json"

# A rejected hypothesis remains rejected until genuinely new evidence appears on its target.
hyp_workspace="$tmp/hypothesis"; mkdir -p "$hyp_workspace/evidence" "$hyp_workspace/validation"
reset_telemetry; mana_trajectory_telemetry_init "$hyp_workspace" hypothesis v2
mana_trajectory_telemetry_emit hypothesis_rejected host_state reject-hypothesis host none none scope-signal-store completed --reason-codes contradicted-by-fixture
python3 "$state" derive-ledger "$mission" "$hyp_workspace/evidence/analysis-trajectory-events-v1.jsonl" "$hyp_workspace/validation/rejected.json"
jq -e '.rejectedHypothesisRefs | length == 1' "$hyp_workspace/validation/rejected.json" >/dev/null || fail 'rejected hypothesis was lost without evidence'
mana_trajectory_telemetry_emit evidence_added provider_result inspect-scope fixture fixture-model none scope-signal-store completed --acceptance-criterion-refs AC-SYN-01 --evidence-gap-refs GAP-COMMIT-HOOK --evidence-added-refs EV-NEW-COMMIT-HOOK
python3 "$state" derive-ledger "$mission" "$hyp_workspace/evidence/analysis-trajectory-events-v1.jsonl" "$hyp_workspace/validation/reopened.json"
jq -e '.rejectedHypothesisRefs | length == 0' "$hyp_workspace/validation/reopened.json" >/dev/null || fail 'new evidence did not supersede the rejected hypothesis'

# Malformed events cannot mutate mission-owned fields; derived counters cannot be forged.
on_track_events="$tmp/traces/ON_TRACK_SIMPLE/evidence/analysis-trajectory-events-v1.jsonl"
on_track_ledger="$tmp/traces/ON_TRACK_SIMPLE/validation/trajectory-ledger-v1.json"
jq -c '. + {missionId:"mission-aaaaaaaaaaaaaaaaaaaaaaaa"}' "$on_track_events" | head -n 1 > "$tmp/malicious-events.jsonl"
tail -n +2 "$on_track_events" >> "$tmp/malicious-events.jsonl"
expect_failure python3 "$state" derive-ledger "$mission" "$tmp/malicious-events.jsonl" "$tmp/malicious-ledger.json"
jq '.providerCounters.iterationsCompleted += 1' "$on_track_ledger" > "$tmp/forged-ledger.json"
expect_failure python3 "$state" validate-ledger "$mission" "$on_track_events" "$tmp/forged-ledger.json"

# The future checkpoint envelope is compact, derivable, measured, and never sent.
envelope="$tmp/checkpoint-envelope.json"
python3 "$state" build-envelope "$mission" "$on_track_ledger" "$on_track_events" "$checkpoint_input" "$envelope" || fail 'checkpoint envelope build failed'
python3 "$state" validate-envelope "$mission" "$on_track_ledger" "$on_track_events" "$envelope" || fail 'checkpoint envelope validation failed'
python3 "$schema_test" "$schema_dir/checkpoint-envelope-v1.schema.json" "$envelope" || fail 'checkpoint envelope schema failed'
jq -e '
  .schemaVersion == "mana.analysis-trajectory.checkpoint-envelope/v1" and
  (.measurements.serializedBytes <= .measurements.hardByteLimit) and
  (.measurements.tokenProxyEstimate <= .measurements.hardTokenProxyLimit) and
  (has("missionHistory") | not) and
  (all(.evidenceDelta[]; (keys | sort) == ["acceptanceCriterionRefs","eventRef","evidenceAddedRefs","evidenceGapRefs","sequence","targetScopeRef"]))
' "$envelope" >/dev/null || fail 'checkpoint envelope is not bounded/current-state only'
if rg -ni '"(prompt|rawPrompt|response|conversation|fullHistory|messages|sourceContent|sourceCode|secret|credential|jiraBody|customerData)"' "$envelope" >/dev/null; then fail 'checkpoint envelope contains a prohibited raw field'; fi

# Enforced byte/token-proxy limits fail before an output artifact is published.
jq '
  .softBudgets.maxEnvelopeBytes=1024 |
  .softBudgets.maxEnvelopeTokenProxy=256 |
  .hardBudgets.maxEnvelopeBytes=1024 |
  .hardBudgets.maxEnvelopeTokenProxy=256
' "$seed" > "$tmp/tight-seed.json"
python3 "$state" create-mission "$story" "$tmp/tight-seed.json" "$tmp/tight-mission.json" "$tmp/tight-history.json"
python3 "$state" derive-ledger "$tmp/tight-mission.json" "$on_track_events" "$tmp/tight-ledger.json"
expect_failure python3 "$state" build-envelope "$tmp/tight-mission.json" "$tmp/tight-ledger.json" "$on_track_events" "$checkpoint_input" "$tmp/over-budget-envelope.json"
[ ! -e "$tmp/over-budget-envelope.json" ] || fail 'over-budget envelope was published'

# TG03 remains a zero-token, non-integrated state layer; public control flow is untouched.
if rg -n 'analysis-trajectory-state' "$root/scripts/run-profile.sh" "$root/scripts/lib/story-start-scope-v2.sh" >/dev/null; then fail 'TG03 changed the public Story Start path'; fi
if rg -n 'provider-dispatch|subprocess|urllib|requests|curl' "$state" >/dev/null; then fail 'TG03 state helper contains a provider/network dispatch path'; fi

echo 'Analysis Trajectory Guard TG03 state tests passed (zero provider/network calls)'
