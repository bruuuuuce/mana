#!/usr/bin/env bash
# TG07 deterministic 8-topology x 5-variant evaluation and rollout gate.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
evaluator="$root/scripts/lib/analysis-trajectory-evaluation.py"
traces="$root/tests/fixtures/analysis-trajectory-guard/tg00-traces-v1.json"
expectations="$root/tests/fixtures/analysis-trajectory-guard/tg07-evaluation-expectations-v1.json"
story="$root/tests/fixtures/analysis-trajectory-guard/tg03-story-package-v1.json"
seed="$root/tests/fixtures/analysis-trajectory-guard/tg03-mission-seed-v1.json"
config="$root/tests/fixtures/analysis-trajectory-guard/tg04-drift-config-v1.json"
scope_plan="$root/tests/fixtures/story-start-scope-v2/planner/provider-output.json"
committed="$root/docs/roadmap/analysis-trajectory-guard/tg07-deterministic-evaluation.json"
schema="$root/contracts/analysis-trajectory/evaluation-report-v1.schema.json"
validator="$root/tests/lib/json_schema_subset.py"
live="$root/scripts/analysis-trajectory-live-pilot.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-tg07-evaluation.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

python3 "$evaluator" "$traces" "$expectations" "$story" "$seed" "$config" "$scope_plan" "$tmp/report.json" || fail 'deterministic evaluation failed'
python3 "$evaluator" "$traces" "$expectations" "$story" "$seed" "$config" "$scope_plan" "$tmp/report-repeat.json" || fail 'repeat evaluation failed'
cmp -s "$tmp/report.json" "$tmp/report-repeat.json" || fail 'evaluation report is not deterministic'
cmp -s "$tmp/report.json" "$committed" || fail 'committed TG07 evaluation report is stale'
python3 "$validator" "$schema" "$tmp/report.json" || fail 'evaluation report schema validation failed'

jq -e '
  .evaluationKind == "DETERMINISTIC_OFFLINE_ZERO_TOKEN" and
  .inputs.providerCalls == 0 and .inputs.networkCalls == 0 and
  .matrix == (.matrix | .topologyCount=8 | .variantCount=5 | .caseCount=40 | .matchedCount=40 | .mismatchCount=0) and
  ([.matrix.cases[].variant] | group_by(.) | map(length) | all(. == 8)) and
  all(.matrix.cases[]; .matchesExpected and .humanUsefulness == "NOT_ASSESSED_DETERMINISTICALLY") and
  all(.qualityProperties[]; .passed) and
  .gate.status == "PASS" and
  .rollout.recommendation == "SHADOW_PILOT_ONLY" and
  (.rollout.defaultOnAuthorized | not)
' "$tmp/report.json" >/dev/null || fail 'matrix coverage or gate result is incomplete'

# Mandatory evidence recall remains 1.0 in every mode and on-track runs pay no
# checkpoint tax, including the two variants whose response fixture is unused.
jq -e '
  all(.metricsByVariant[]; .mandatory_evidence_recall == 1) and
  all(.matrix.cases[] | select(.traceId == "trace-on-track-simple-001" or .traceId == "trace-legitimate-expansion-001" or .traceId == "trace-mandatory-cross-cutting-001" or .traceId == "trace-opaque-provider-001"); .checkpointCount == 0) and
  all(.matrix.cases[] | select(.traceId == "trace-mandatory-cross-cutting-001"); .mandatoryEvidenceExpectedRefs == .mandatoryEvidencePreservedRefs)
' "$tmp/report.json" >/dev/null || fail 'mandatory recall or on-track checkpoint tax regressed'

# The unrelated bug and architecture alternatives are deferred at their real
# next-action boundary. Failed structural repair consumes two calls and halts.
jq -e '
  all(.matrix.cases[] | select(.traceId == "trace-related-bug-001" and (.variant | startswith("ENFORCE"))); .actualTrajectoryOutcome == "SCOPE_TRIAGE_REQUIRED" and (.irrelevantExplorationAvoidedRefs | length) == 2 and .downstreamScopeV2Result.status == "NOT_REACHED_FAIL_CLOSED") and
  all(.matrix.cases[] | select(.traceId == "trace-architecture-rabbit-hole-001" and (.variant | startswith("ENFORCE"))); (.irrelevantExplorationAvoidedRefs | length) == 2) and
  (.matrix.cases[] | select(.traceId == "trace-repeat-no-evidence-001" and .variant == "ENFORCE_FAILED_REPAIR") | .checkpointCount == 2 and .actualTrajectoryOutcome == "NEEDS_OWNER_REVIEW" and (.failureBehavior | contains("NO_FALLBACK")))
' "$tmp/report.json" >/dev/null || fail 'enforce drift/failure behavior regressed'

# Scope v2 remains a separate downstream classifier and does not sum open,
# mutually exclusive alternatives. Exact provider tokens and human judgments
# stay unavailable rather than being invented.
jq -e '
  .scopeV2.basePlanCount > 0 and .scopeV2.requiredEnablerCount > 0 and
  .scopeV2.conditionalBranchCount > 0 and .scopeV2.relatedFindingCount > 0 and
  .scopeV2.exclusiveAlternativesNotSummed and .scopeV2.finalCommittedEstimate == null and
  all(.metricsByVariant[]; .tokens_per_run.availability == "UNAVAILABLE" and .wall_time.availability == "UNAVAILABLE" and .human_rejected_or_deferred_findings.availability == "UNAVAILABLE") and
  (.humanAcceptance.completed | not) and .humanAcceptance.materialsComplete
' "$tmp/report.json" >/dev/null || fail 'Scope v2 separation or unavailable metric semantics regressed'

if rg -i 'rawprompt|rawresponse|conversationhistory|chain.?of.?thought|credential|secret|jira.?body|source.?code' "$tmp/report.json" >/dev/null; then
  fail 'evaluation report contains a prohibited persisted field'
fi

# Live execution remains doubly opt-in, excluded from CI, and bounded. These
# checks stop before creating an output directory or invoking any provider.
pilot_project="$tmp/pilot-project"
mkdir -p "$pilot_project"
git -C "$pilot_project" init -q
printf '%s\n' '{"synthetic":true}' > "$pilot_project/context.json"
if "$live" --project-root "$pilot_project" --context context.json --provider codex --output-dir pilot-artifacts >"$tmp/live.out" 2>"$tmp/live.err"; then
  fail 'live pilot ran without its explicit flag'
fi
[ ! -e "$pilot_project/pilot-artifacts" ] || fail 'disabled live pilot created artifacts'
if MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT=true MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT_CREDENTIALS_READY=true CI=true \
  "$live" --project-root "$pilot_project" --context context.json --provider codex --output-dir pilot-artifacts >"$tmp/ci.out" 2>"$tmp/ci.err"; then
  fail 'live pilot ran in CI'
fi
[ ! -e "$pilot_project/pilot-artifacts" ] || fail 'CI-blocked live pilot created artifacts'
rg -q 'maximumProviderCalls:14' "$live" || fail 'live pilot lacks a total provider-call cap'
rg -q 'maximumCheckpointCalls:2' "$live" || fail 'live pilot lacks a checkpoint-call cap'
rg -q -- '--checkpoint-only' "$live" || fail 'live pilot lacks checkpoint-only mode'

echo 'Analysis Trajectory Guard TG07 evaluation passed (40 deterministic cases; zero provider/network calls; rollout SHADOW_PILOT_ONLY)'
