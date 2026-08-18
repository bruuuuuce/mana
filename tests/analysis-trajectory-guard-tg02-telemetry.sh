#!/usr/bin/env bash
# TG02 offline telemetry regression suite. It turns TG00's synthetic,
# host-visible trace topologies into sidecar events; no provider is invoked.
set -euo pipefail

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
fixture="$root/tests/fixtures/analysis-trajectory-guard/tg00-traces-v1.json"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-tg02-telemetry.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

MANA_ANALYSIS_TRAJECTORY_TELEMETRY=true
. "$root/scripts/lib/analysis-trajectory-telemetry.sh"
[ -f "$fixture" ] || fail "missing TG00 fixture"

for case_name in $(jq -r '.traces[].case' "$fixture"); do
  workspace="$tmp/$case_name"; mkdir -p "$workspace/evidence" "$workspace/validation"
  MANA_TRAJECTORY_TELEMETRY_ENABLED=false
  MANA_TRAJECTORY_TELEMETRY_EVENTS=""; MANA_TRAJECTORY_TELEMETRY_SUMMARY=""; MANA_TRAJECTORY_TELEMETRY_RUN_ID=""
  mana_trajectory_telemetry_init "$workspace" "$case_name" v2 || fail "telemetry init failed for $case_name"
  previous_scope=""
  while IFS= read -r step; do
    action="$(jq -r '.actionKind' <<<"$step")"
    scope="$(jq -r '.targetScopeRef' <<<"$step")"
    refs=()
    while IFS= read -r ref; do refs+=(--acceptance-criterion-refs "$ref"); done < <(jq -r '.goalRefs[]?' <<<"$step")
    while IFS= read -r ref; do refs+=(--evidence-gap-refs "$ref"); done < <(jq -r '.gapRefs[]?' <<<"$step")
    while IFS= read -r ref; do refs+=(--decision-refs "$ref"); done < <(jq -r '.decisionRefs[]?' <<<"$step")
    while IFS= read -r ref; do refs+=(--evidence-added-refs "$ref"); done < <(jq -r '.evidenceAddedRefs[]?' <<<"$step")
    mana_trajectory_telemetry_emit provider_iteration_completed "$(jq -r '.hostBoundary' <<<"$step")" "$action" fixture fixture-model none "$scope" completed "${refs[@]}" || fail "step emit failed for $case_name"
    if [ -n "$previous_scope" ] && [ "$previous_scope" != "$scope" ]; then
      mana_trajectory_telemetry_emit scope_expansion_proposed context_expansion enter-linked-scope fixture fixture-model none "$scope" completed "${refs[@]}" || fail "expansion emit failed"
    fi
    if [ "$(jq '.decisionRefs | length' <<<"$step")" -gt 0 ]; then
      mana_trajectory_telemetry_emit open_decision_observed provider_result identify-open-decision fixture fixture-model none "$scope" completed "${refs[@]}" || fail "decision emit failed"
    fi
    previous_scope="$scope"
  done < <(jq -c --arg case_name "$case_name" '.traces[] | select(.case == $case_name) | .steps[]' "$fixture")
  mana_trajectory_telemetry_emit analysis_completed public_pipeline complete host none none scope-v2/public completed || fail "terminal emit failed"
  mana_trajectory_telemetry_finish || fail "summary failed for $case_name"
  events="$workspace/evidence/analysis-trajectory-events-v1.jsonl"
  summary="$workspace/validation/analysis-trajectory-summary-v1.json"
  [ "$(wc -l < "$events" | tr -d ' ')" -ge "$(jq --arg case_name "$case_name" '[.traces[] | select(.case == $case_name) | .steps[]] | length' "$fixture")" ] || fail "missing events for $case_name"
  jq -s 'all(.[]; .schemaVersion == "mana.analysis-trajectory.event/v1") and ([.[].sequence] == [range(1; length + 1)]) and ([.[].eventId] | unique | length == length)' "$events" >/dev/null || fail "event ordering or IDs invalid for $case_name"
  while IFS= read -r event; do
    printf '%s\n' "$event" > "$tmp/event.json"
    python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/analysis-trajectory/telemetry-event-v1.schema.json" "$tmp/event.json" || fail "event schema invalid for $case_name"
  done < "$events"
  python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/analysis-trajectory/run-summary-v1.schema.json" "$summary" || fail "summary schema invalid for $case_name"
  cp "$summary" "$tmp/$case_name-summary-first.json"
  python3 "$root/scripts/lib/analysis-trajectory-telemetry.py" summarize "$events" "$summary" || fail "repeat summary failed for $case_name"
  cmp -s "$tmp/$case_name-summary-first.json" "$summary" || fail "summary is not deterministic for $case_name"
done

on_track="$tmp/ON_TRACK_SIMPLE/validation/analysis-trajectory-summary-v1.json"
rabbit="$tmp/DRIFT_ARCHITECTURE_RABBIT_HOLE/validation/analysis-trajectory-summary-v1.json"
repeat="$tmp/DRIFT_REPEAT_NO_EVIDENCE/validation/analysis-trajectory-summary-v1.json"
opaque="$tmp/OPAQUE_PROVIDER_BOUNDARY/evidence/analysis-trajectory-events-v1.jsonl"
jq -e '.maxConsecutiveIterationsWithoutEvidence == 0 and .scopeExpansionCount == 0' "$on_track" >/dev/null || fail 'on-track telemetry became a drift classification'
jq -e '.openDecisionObservationCount > 0 and .scopeExpansionCount > 0' "$rabbit" >/dev/null || fail 'architecture topology was not observable'
jq -e '.repeatedTargetScopeRefs | length == 1' "$repeat" >/dev/null || fail 'revisit topology was not aggregated'
jq -s -e 'all(.[]; .boundary == "provider_invocation" or .boundary == "provider_completion" or .boundary == "public_pipeline")' "$opaque" >/dev/null || fail 'opaque trace invented an internal boundary'
if rg -ni '"(prompt|response|chain.of.thought|note|source.content|token|secret|credential)"' "$tmp" >/dev/null; then fail 'telemetry contains a prohibited raw field'; fi

MANA_ANALYSIS_TRAJECTORY_TELEMETRY=false
MANA_TRAJECTORY_TELEMETRY_ENABLED=false; MANA_TRAJECTORY_TELEMETRY_EVENTS=""; MANA_TRAJECTORY_TELEMETRY_SUMMARY=""; MANA_TRAJECTORY_TELEMETRY_RUN_ID=""
disabled="$tmp/disabled"; mkdir -p "$disabled"
mana_trajectory_telemetry_init "$disabled" disabled v2 || fail 'disabled telemetry init changed control flow'
[ ! -e "$disabled/evidence/analysis-trajectory-events-v1.jsonl" ] || fail 'disabled telemetry wrote an artifact'

MANA_ANALYSIS_TRAJECTORY_TELEMETRY=true
failed="$tmp/failed"; mkdir -p "$failed/evidence" "$failed/validation"
MANA_TRAJECTORY_TELEMETRY_ENABLED=false; MANA_TRAJECTORY_TELEMETRY_EVENTS=""; MANA_TRAJECTORY_TELEMETRY_SUMMARY=""; MANA_TRAJECTORY_TELEMETRY_RUN_ID=""
mana_trajectory_telemetry_init "$failed" failed-run v2 || fail 'failed-run telemetry init failed'
mana_trajectory_telemetry_emit provider_iteration_started provider_invocation discovery fixture fixture-model none scope-v2/discovery started || fail 'failed-run start emit failed'
mana_trajectory_telemetry_emit analysis_failed public_pipeline discovery host none none scope-v2/public failed --reason-codes synthetic-provider-failure || fail 'failed-run terminal emit failed'
mana_trajectory_telemetry_finish || fail 'failed-run summary failed'
jq -e '.runOutcome == "failed" and .partial == false' "$failed/validation/analysis-trajectory-summary-v1.json" >/dev/null || fail 'failed run was not explicit in the summary'

echo 'Analysis Trajectory Guard TG02 telemetry tests passed'
