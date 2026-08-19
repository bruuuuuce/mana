#!/usr/bin/env bash
# SS06 zero-token public integration, rendering, and compatibility acceptance.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
package="$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json"
discovery_raw="$root/tests/fixtures/story-start-scope-v2/discovery/provider-output.json"
triage_raw="$root/tests/fixtures/story-start-scope-v2/triage/provider-output.json"
plan_raw="$root/tests/fixtures/story-start-scope-v2/planner/provider-output.json"
normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
renderer="$root/scripts/lib/story-start-scope-v2-render.py"
run_schema="$root/contracts/story-start/scope-v2/schemas/scope-run.schema.json"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-integration-v2.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/story-start-scope-v2.sh"

mkdir -p "$tmp/expected"
python3 "$normalizer" normalize-discovery \
  "$root/contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json" \
  "$discovery_raw" "$tmp/expected/discovery.json"
python3 "$normalizer" normalize-triage \
  "$root/contracts/story-start/scope-v2/schemas/scope-triage.schema.json" \
  "$tmp/expected/discovery.json" "$triage_raw" "$tmp/expected/triage.json"
python3 "$normalizer" build-planning-context \
  "$tmp/expected/discovery.json" "$tmp/expected/triage.json" "$tmp/expected/context.json"
python3 "$normalizer" normalize-plan \
  "$root/contracts/story-start/scope-v2/schemas/implementation-plan.schema.json" \
  "$tmp/expected/context.json" "$tmp/expected/triage.json" "$plan_raw" "$tmp/expected/plan.json"

stub="$tmp/phase-provider-stub"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s\n" call >> "$SS06_STUB_COUNT"' \
  'last=""; for argument in "$@"; do last="$argument"; done' \
  'case "$last" in' \
  '  *COMPACT_DISCOVERY_PACKAGE*) cat "$SS06_DISCOVERY_OUTPUT" ;;' \
  '  *COMPACT_DISCOVERY_V2*) cat "$SS06_TRIAGE_OUTPUT" ;;' \
  '  *INVALID_IMPLEMENTATION_PLAN_V2*) cat "$SS06_CORRECTION_OUTPUT" ;;' \
  '  *SCOPE_TRIAGE_V2*) cat "$SS06_PLAN_OUTPUT" ;;' \
  '  *) exit 0 ;;' \
  'esac' > "$stub"
chmod +x "$stub"

workspace="$tmp/workspace"
mkdir -p "$workspace/evidence" "$workspace/planning" "$workspace/validation"
printf '%s\n' '# Legacy implementation plan' 'Keep this v1 file readable.' > "$workspace/planning/implementation-plan.md"
legacy_hash_before="$(shasum -a 256 "$workspace/planning/implementation-plan.md" | awk '{print $1}')"
: > "$tmp/success-count"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
SS06_STUB_COUNT="$tmp/success-count" \
SS06_DISCOVERY_OUTPUT="$discovery_raw" \
SS06_TRIAGE_OUTPUT="$triage_raw" \
SS06_PLAN_OUTPUT="$plan_raw" \
SS06_CORRECTION_OUTPUT="$plan_raw" \
mana_story_start_scope_v2_run_public stub deterministic "$package" "$workspace"

# 1 and 3. The full zero-token pipeline publishes only governed, versioned artifacts.
[ "$(wc -l < "$tmp/success-count" | tr -d ' ')" = 3 ] || fail 'successful path did not make exactly three phase calls'
for artifact in \
  evidence/story-start-discovery-v2.json \
  planning/story-start-scope-triage-v2.json \
  planning/story-start-implementation-plan-v2.json \
  planning/story-start-scope-v2.md \
  validation/story-start-scope-governance-v2.json \
  validation/story-start-scope-run-v2.json; do
  [ -f "$workspace/$artifact" ] || fail "missing public v2 artifact: $artifact"
done
cmp -s "$tmp/expected/discovery.json" "$workspace/evidence/story-start-discovery-v2.json" || fail 'public discovery differs from normalized output'
cmp -s "$tmp/expected/triage.json" "$workspace/planning/story-start-scope-triage-v2.json" || fail 'public triage differs from normalized output'
cmp -s "$tmp/expected/plan.json" "$workspace/planning/story-start-implementation-plan-v2.json" || fail 'public plan differs from governed output'
python3 "$root/tests/lib/json_schema_subset.py" "$run_schema" "$workspace/validation/story-start-scope-run-v2.json"
jq -e '
  .schemaVersion=="mana.story-start.scope-run/v2" and .artifactVersion==2 and
  .status=="passed" and .failedPhase=="none" and
  .planningReview.state=="required" and .ownerReview.state=="not_required" and
  all(.phaseStates[]; .=="passed")
' "$workspace/validation/story-start-scope-run-v2.json" >/dev/null || fail 'public run status lost version or review state'
jq -e '
  .schemaVersion=="mana.story-start.implementation-plan/v2" and
  .artifactVersion==2 and (.artifactId|test("^plan_[0-9a-f]{64}$"))
' "$workspace/planning/story-start-implementation-plan-v2.json" >/dev/null || fail 'public plan metadata is not explicit or deterministic'
jq -e '.status=="passed" and .semanticValidation=="passed"' "$workspace/validation/story-start-scope-governance-v2.json" >/dev/null || fail 'public plan bypassed the governor'

# 2 and 5-11. Semantic Markdown checks cover layout without a brittle snapshot.
report="$workspace/planning/story-start-scope-v2.md"
previous=0
for section in \
  '## 1. Story readiness' \
  '## 2. Base implementation plan' \
  '## 3. Required enablers' \
  '## 4. Conditional branches' \
  '## 5. Scenario estimates' \
  '## 6. Decisions required' \
  '## 7. Related findings not included in scope' \
  '## 8. Risks and optional improvements' \
  '## 9. Evidence and provenance' \
  '## 10. Validation/owner-review status'; do
  line="$(grep -nF "$section" "$report" | head -1 | cut -d: -f1)"
  if [ -z "$line" ] || [ "$line" -le "$previous" ]; then
    fail "Markdown section order is invalid at: $section"
  fi
  previous="$line"
done
grep -Fq 'Base engineering effort:' "$report" || fail 'base estimate is not labeled clearly'
grep -Fq 'Mandatory additional work' "$report" || fail 'required enablers are not labeled as mandatory additions'
grep -Fq 'Conditional delta:' "$report" || fail 'conditional branch deltas are missing'
grep -Fq 'Mutually exclusive alternatives' "$report" || fail 'exclusive branches are not explicit'
grep -Fq 'do not sum them' "$report" || fail 'exclusive branch non-aggregation is not explicit'
grep -Fq 'No final committed estimate is available while material decisions remain open.' "$report" || fail 'open decisions did not suppress a committed estimate'
grep -Fq 'OUT OF SCOPE — The independent legacy defect' "$report" || fail 'related defect is not visibly out of scope'
grep -Fq 'OUT OF SCOPE `OPTIONAL_IMPROVEMENT`' "$report" || fail 'optional improvement is not visibly excluded'
grep -Fq 'Readiness engineering effort: 0–0 person-hours' "$report" || fail 'readiness engineering effort is not separate'
grep -Fq 'Readiness calendar impact: unknown' "$report" || fail 'calendar impact is not separate'
grep -Fq 'reusing the verified notifier configuration rather than creating another channel' "$report" || fail 'existing configuration reuse is not rendered'
if grep -Fiq 'grand total' "$report" || grep -Fq 'Add configuration channel' "$report"; then
  fail 'report rendered an illegal grand total or existing-configuration creation task'
fi

# Focused deterministic snapshot: rerunning equivalent inputs keeps status and report byte-identical.
cp "$report" "$tmp/report-first.md"
cp "$workspace/validation/story-start-scope-run-v2.json" "$tmp/status-first.json"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
SS06_STUB_COUNT="$tmp/success-count" \
SS06_DISCOVERY_OUTPUT="$discovery_raw" \
SS06_TRIAGE_OUTPUT="$triage_raw" \
SS06_PLAN_OUTPUT="$plan_raw" \
SS06_CORRECTION_OUTPUT="$plan_raw" \
mana_story_start_scope_v2_run_public stub deterministic "$package" "$workspace"
cmp -s "$tmp/report-first.md" "$report" || fail 'Markdown rendering is not deterministic'
cmp -s "$tmp/status-first.json" "$workspace/validation/story-start-scope-run-v2.json" || fail 'public run status is not deterministic'

# 4. Legacy Markdown is unchanged; compatibility dispatch never misreads v2 as v1.
legacy_hash_after="$(shasum -a 256 "$workspace/planning/implementation-plan.md" | awk '{print $1}')"
[ "$legacy_hash_before" = "$legacy_hash_after" ] || fail 'v2 overwrote a legacy plan'
python3 "$renderer" compatibility 2 "$workspace/planning/implementation-plan.md" > "$tmp/legacy-compat.json"
jq -e '.status=="legacy_readable" and .handling=="preserve_as_is" and .safeToInterpret==false' "$tmp/legacy-compat.json" >/dev/null || fail 'legacy Markdown compatibility is unsafe'
python3 "$renderer" compatibility 1 "$workspace/planning/story-start-implementation-plan-v2.json" > "$tmp/v1-reader.json"
jq -e '.status=="unsupported" and .safeToInterpret==false and (.reason|contains("must not reinterpret"))' "$tmp/v1-reader.json" >/dev/null || fail 'v1 reader did not reject v2 gracefully'
python3 "$renderer" compatibility 2 "$workspace/planning/story-start-implementation-plan-v2.json" > "$tmp/v2-reader.json"
jq -e '.status=="supported" and .safeToInterpret==true' "$tmp/v2-reader.json" >/dev/null || fail 'v2 reader rejected a supported plan'

# 5. A second invalid plan is fail-closed, rendered for owner review, and never published.
jq '.basePlan[0].title="Add configuration channel"' "$plan_raw" > "$tmp/invalid-plan.json"
failed_workspace="$tmp/failed-workspace"
mkdir -p "$failed_workspace/evidence" "$failed_workspace/planning" "$failed_workspace/validation"
: > "$tmp/failed-count"
if MANA_USER_LEARNING_ALLOW_STUB=true \
  MANA_USER_LEARNING_STUB_COMMAND="$stub" \
  SS06_STUB_COUNT="$tmp/failed-count" \
  SS06_DISCOVERY_OUTPUT="$discovery_raw" \
  SS06_TRIAGE_OUTPUT="$triage_raw" \
  SS06_PLAN_OUTPUT="$tmp/invalid-plan.json" \
  SS06_CORRECTION_OUTPUT="$tmp/invalid-plan.json" \
  mana_story_start_scope_v2_run_public stub deterministic "$package" "$failed_workspace"; then
  fail 'invalid correction was publicly accepted'
fi
[ "$(wc -l < "$tmp/failed-count" | tr -d ' ')" = 4 ] || fail 'owner-review path exceeded one correction call'
[ ! -e "$failed_workspace/planning/story-start-implementation-plan-v2.json" ] || fail 'invalid plan was published'
jq -e '
  .status=="needs_owner_review" and .failedPhase=="governor" and
  .ownerReview.state=="required" and .artifactRefs.implementationPlan==null and
  .artifactRefs.governanceReport!=null
' "$failed_workspace/validation/story-start-scope-run-v2.json" >/dev/null || fail 'governor failure status is not explicit'
grep -Fq 'Owner review: **required**' "$failed_workspace/planning/story-start-scope-v2.md" || fail 'owner-review Markdown is missing'
grep -Fq 'EXISTING_CAPABILITY_CREATION_TASK' "$failed_workspace/planning/story-start-scope-v2.md" || fail 'owner-review diagnostics lost violation codes'
grep -Fq 'no legacy/free-form fallback was used' "$failed_workspace/planning/story-start-scope-v2.md" || fail 'fail-closed rendering is not explicit'

# Provider failure is also an explicit terminal state, not a silent fallback.
provider_stub="$tmp/provider-failure-stub"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" call >> "$SS06_STUB_COUNT"' 'exit 7' > "$provider_stub"
chmod +x "$provider_stub"
provider_workspace="$tmp/provider-workspace"
mkdir -p "$provider_workspace/evidence" "$provider_workspace/planning" "$provider_workspace/validation"
: > "$tmp/provider-count"
if MANA_USER_LEARNING_ALLOW_STUB=true \
  MANA_USER_LEARNING_STUB_COMMAND="$provider_stub" \
  SS06_STUB_COUNT="$tmp/provider-count" \
  mana_story_start_scope_v2_run_public stub deterministic "$package" "$provider_workspace" >/dev/null 2>&1; then
  fail 'provider failure was accepted'
fi
[ "$(wc -l < "$tmp/provider-count" | tr -d ' ')" = 1 ] || fail 'discovery provider failure was retried'
jq -e '.status=="needs_owner_review" and .failedPhase=="discovery" and .artifactRefs.implementationPlan==null' "$provider_workspace/validation/story-start-scope-run-v2.json" >/dev/null || fail 'provider failure status is not explicit'

# 12. The actual public invocation keeps v1 as default and selects v2 without a new CLI style.
fake_bin="$tmp/bin"
mkdir -p "$fake_bin"
cp "$stub" "$fake_bin/codex"
public_project="$tmp/public-project"
mkdir -p "$public_project"
cp "$package" "$public_project/story-context.json"
: > "$tmp/public-count"
MANA_UPDATE_CHECK=off \
MANA_ANALYSIS_TRAJECTORY_TELEMETRY=true \
MANA_STORY_START_SCOPE_VERSION=v2 \
MANA_STORY_START_CONTEXT=story-context.json \
SS06_STUB_COUNT="$tmp/public-count" \
SS06_DISCOVERY_OUTPUT="$discovery_raw" \
SS06_TRIAGE_OUTPUT="$triage_raw" \
SS06_PLAN_OUTPUT="$plan_raw" \
SS06_CORRECTION_OUTPUT="$plan_raw" \
PATH="$fake_bin:$PATH" \
"$root/scripts/run-profile.sh" story-start --project-root "$public_project" --codex > "$tmp/public.out" 2> "$tmp/public.err"
[ "$(wc -l < "$tmp/public-count" | tr -d ' ')" = 3 ] || fail 'public v2 invocation did not execute the three host phases'
grep -Fq 'Story Start Scope pipeline: v2' "$tmp/public.out" || fail 'public renderer did not expose v2 selection'
grep -Fq 'Story Start Scope v2 status: passed' "$tmp/public.out" || fail 'public v2 invocation did not report success'
public_active="$(sed -n '1p' "$public_project/.mana/active-workspace")"
jq -e '.status=="passed"' "$public_project/$public_active/validation/story-start-scope-run-v2.json" >/dev/null || fail 'public command did not publish v2 status'
telemetry_events="$public_project/$public_active/evidence/analysis-trajectory-events-v1.jsonl"
telemetry_summary="$public_project/$public_active/validation/analysis-trajectory-summary-v1.json"
[ -f "$telemetry_events" ] && [ -f "$telemetry_summary" ] || fail 'opt-in telemetry sidecars were not published'
python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/analysis-trajectory/run-summary-v1.schema.json" "$telemetry_summary" || fail 'public telemetry summary is invalid'
jq -s '([.[].sequence] == [range(1; length + 1)]) and ([.[] | select(.eventType == "provider_iteration_started")] | length == 3)' "$telemetry_events" >/dev/null || fail 'telemetry did not record exactly the existing three provider calls'

# The cast preflight reaches the same guarded run-profile boundary.
cast_project="$tmp/cast-project"
mkdir -p "$cast_project/.mana/global"
for context_file in service-mission.md architecture.md engineering-guards.md; do
  printf '# Synthetic %s\n\nOffline SS06 test context.\n' "$context_file" > "$cast_project/.mana/global/$context_file"
done
cp "$package" "$cast_project/story-context.json"
: > "$tmp/cast-count"
MANA_UPDATE_CHECK=off \
MANA_STORY_START_SCOPE_VERSION=v2 \
MANA_STORY_START_CONTEXT=story-context.json \
SS06_STUB_COUNT="$tmp/cast-count" \
SS06_DISCOVERY_OUTPUT="$discovery_raw" \
SS06_TRIAGE_OUTPUT="$triage_raw" \
SS06_PLAN_OUTPUT="$plan_raw" \
SS06_CORRECTION_OUTPUT="$plan_raw" \
PATH="$fake_bin:$PATH" \
"$root/scripts/cast.sh" story-start --project-root "$cast_project" > "$tmp/cast.out" 2> "$tmp/cast.err"
[ "$(wc -l < "$tmp/cast-count" | tr -d ' ')" = 3 ] || fail 'cast did not reach the guarded three-phase v2 path'
cast_active="$(sed -n '1p' "$cast_project/.mana/active-workspace")"
jq -e '.status=="passed"' "$cast_project/$cast_active/validation/story-start-scope-run-v2.json" >/dev/null || fail 'cast did not publish the validated v2 status'
[ ! -e "$cast_project/$cast_active/evidence/analysis-trajectory-events-v1.jsonl" ] || fail 'telemetry-disabled v2 run changed artifacts'

legacy_project="$tmp/legacy-project"
mkdir -p "$legacy_project"
: > "$tmp/legacy-public-count"
MANA_UPDATE_CHECK=off \
SS06_STUB_COUNT="$tmp/legacy-public-count" \
SS06_DISCOVERY_OUTPUT="$discovery_raw" \
SS06_TRIAGE_OUTPUT="$triage_raw" \
SS06_PLAN_OUTPUT="$plan_raw" \
SS06_CORRECTION_OUTPUT="$plan_raw" \
PATH="$fake_bin:$PATH" \
"$root/scripts/run-profile.sh" story-start --project-root "$legacy_project" --codex > "$tmp/legacy-public.out" 2> "$tmp/legacy-public.err"
grep -Fq 'Story Start Scope pipeline: v1' "$tmp/legacy-public.out" || fail 'legacy public invocation is no longer the default'
[ "$(wc -l < "$tmp/legacy-public-count" | tr -d ' ')" = 1 ] || fail 'legacy invocation was collapsed into the v2 pipeline'
[ ! -e "$legacy_project/.mana/active-workspace" ] || fail 'legacy profile unexpectedly published v2 workspace state'

echo 'Story Start Scope v2 SS06 integration tests passed (zero real provider/network calls; fake providers only)'
