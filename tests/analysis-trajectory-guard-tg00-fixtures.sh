#!/usr/bin/env bash
# TG00 zero-token integrity checks for synthetic trajectory trace topologies.
set -euo pipefail

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
fixture="$root/tests/fixtures/analysis-trajectory-guard/tg00-traces-v1.json"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

command -v jq >/dev/null 2>&1 || fail "jq is required"
[ -f "$fixture" ] || fail "missing fixture: $fixture"

jq -e '
  .schemaVersion == "mana.analysis-trajectory.trace-set/v1" and
  .fixtureSetId == "trajectory-guard-synthetic-tg00-001" and
  .fixtureRevision == 1 and
  .synthetic == true and
  .phase == "TG00" and
  .sanitization.realIdentifiersPresent == false and
  .sanitization.reservedDomainsOnly == true and
  .sanitization.productionValuesPresent == false and
  .traceContract.hostVisibleStepsOnly == true and
  .traceContract.opaqueProviderActivityMayOnlyBeSummarized == true and
  .traceContract.futureRuntimeSchema == false and
  (.traces | length) == 8
' "$fixture" >/dev/null || fail "fixture metadata or cardinality is invalid"

jq -e '
  ([.traces[].case] | sort) == ([
    "ON_TRACK_SIMPLE",
    "ON_TRACK_LEGITIMATE_EXPANSION",
    "DRIFT_RELATED_BUG",
    "DRIFT_ARCHITECTURE_RABBIT_HOLE",
    "DRIFT_REPEAT_NO_EVIDENCE",
    "STOP_SUFFICIENT_EVIDENCE",
    "MANDATORY_CROSS_CUTTING_FINDING",
    "OPAQUE_PROVIDER_BOUNDARY"
  ] | sort) and
  ([.traces[].traceId] | length) == ([.traces[].traceId] | unique | length) and
  all(.traces[]; (.steps | length) > 0 and
    ([.steps[].sequence] == [range(1; (.steps | length) + 1)]) and
    all(.steps[]; .hostObservable == true))
' "$fixture" >/dev/null || fail "required trace cases, IDs, or step ordering are invalid"

jq -e '
  .referenceCatalog as $refs |
  all(.traces[].steps[];
    (.targetScopeRef as $id | ($refs.scopeRefs | index($id)) != null) and
    all(.goalRefs[]; . as $id | ($refs.goalRefs | index($id)) != null) and
    all(.mandatoryConstraintRefs[]; . as $id | ($refs.mandatoryConstraintRefs | index($id)) != null) and
    all(.gapRefs[]; . as $id | ($refs.evidenceGapRefs | index($id)) != null) and
    all(.decisionRefs[]; . as $id | ($refs.decisionRefs | index($id)) != null) and
    all(.evidenceAddedRefs[]; . as $id | ($refs.evidenceRefs | index($id)) != null)
  )
' "$fixture" >/dev/null || fail "fixture contains a dangling reference"

jq -e '
  (.traces[] | select(.case == "ON_TRACK_SIMPLE") |
    all(.steps[]; (.goalRefs | length) > 0 and (.gapRefs | length) > 0 and .newEvidence == true) and
    ([.steps[].targetScopeRef] | unique | length) == 1) and
  (.traces[] | select(.case == "ON_TRACK_LEGITIMATE_EXPANSION") |
    ([.steps[].targetScopeRef] | unique | length) == 2 and
    (.steps[1].hostBoundary == "context_expansion") and
    (.steps[1].goalRefs | length) > 0 and (.steps[1].gapRefs | length) > 0 and .steps[1].newEvidence == true) and
  (.traces[] | select(.case == "DRIFT_RELATED_BUG") |
    .steps[0].newEvidence == true and
    all(.steps[1:][].goalRefs; length == 0) and
    all(.steps[1:][].gapRefs; length == 0) and
    all(.steps[1:][]; .newEvidence == false)) and
  (.traces[] | select(.case == "DRIFT_ARCHITECTURE_RABBIT_HOLE") |
    .steps[0].decisionRefs == ["DEC-DELIVERY-MODE"] and
    all(.steps[1:][]; .actionKind == "design_complete_alternative" and .newEvidence == false) and
    ([.steps[1:][].targetScopeRef] | unique | length) == 2) and
  (.traces[] | select(.case == "DRIFT_REPEAT_NO_EVIDENCE") |
    ([.steps[].targetScopeRef] | unique | length) == 1 and
    ([.steps[] | select(.newEvidence == false)] | length) == 2) and
  (.traces[] | select(.case == "STOP_SUFFICIENT_EVIDENCE") |
    .steps[-1].actionKind == "research_optional_hardening" and
    (.steps[-1].goalRefs | length) == 0 and (.steps[-1].gapRefs | length) == 0) and
  (.traces[] | select(.case == "MANDATORY_CROSS_CUTTING_FINDING") |
    ([.steps[].targetScopeRef] | unique | length) == 2 and
    all(.steps[]; .mandatoryConstraintRefs == ["CONSTRAINT-AUTHZ-01"] and .newEvidence == true)) and
  (.traces[] | select(.case == "OPAQUE_PROVIDER_BOUNDARY") |
    [.steps[].hostBoundary] == ["provider_invocation", "provider_completion"] and
    .opaqueInternalActivity == [
      "provider_internal_file_read",
      "provider_internal_search",
      "provider_internal_tool_retry"
    ])
' "$fixture" >/dev/null || fail "one or more required TG00 topologies regressed"

jq -e '
  [paths(scalars) as $path | ($path[-1] | tostring)] |
  all(.[];
    . != "triggerThreshold" and
    . != "checkpointOutcome" and
    . != "missionContract" and
    . != "trajectoryLedger" and
    . != "runtimeEnabled" and
    . != "providerResponse")
' "$fixture" >/dev/null || fail "TG00 fixture implements a later-phase runtime contract"

if rg -ni '(nexi|merchant|atlassian|PROJ-[0-9]+|https?://)' "$fixture" >/dev/null; then
  fail "fixture contains a prohibited real-world name, issue pattern, or endpoint"
fi

echo "Analysis Trajectory Guard TG00 fixture integrity tests passed"
