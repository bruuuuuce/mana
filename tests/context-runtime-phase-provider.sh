#!/usr/bin/env bash
# CTX-06C deterministic fresh-provider, lifecycle, metrics, and fallback gate.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
pipeline="$root/scripts/mana-context-pipeline.sh"
runner="$root/tests/run-profile-v2-test-only.sh"
framework="$root/tests/fixtures/context-runtime/ctx06a-framework"
fixture_root="$root/tests/fixtures/context-runtime"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-context-06c.XXXXXX")"
tmp="$(cd "$tmp" && pwd -P)"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$tmp/pycache"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

ctx06c_file_mode() {
  local path="$1"
  case "$(uname -s)" in
    Darwin) stat -f '%Lp' "$path" ;;
    Linux) stat -c '%a' "$path" ;;
    *) return 1 ;;
  esac
}

# The R2.2 dispatch cases must not leave even ignored local artifacts behind.
# Preserve pre-existing user work as the baseline rather than assuming a clean
# Mana checkout.
git -C "$root" status --porcelain=v1 --ignored > "$tmp/repository-before.status"

mkdir -p "$tmp/bin"
cp "$fixture_root/ctx06c-provider-stub.sh" "$tmp/bin/codex"
chmod +x "$tmp/bin/codex"

make_project() {
  local name="$1" project
  project="$tmp/$name/project with spaces"
  mkdir -p "$project/.mana/sessions/ctx06c-fixture"
  printf '%s\n' 'workspace_type: "session"' 'workspace_id: "ctx06c-fixture"' \
    > "$project/.mana/sessions/ctx06c-fixture/manifest.yaml"
  (cd "$project" && pwd -P)
}

make_dispatch_project() {
  local name="$1" project policy
  project="$tmp/$name/project with spaces"
  mkdir -p "$project"
  "$root/scripts/bootstrap-project.sh" --project-root "$project" --mana-root "$root" \
    --no-links --no-jira-env --no-gitignore >/dev/null
  policy="$project/.mana/context-runtime/runtime-selection-v1.json"
  jq -c '.profiles={"mana-help":{"mode":"v2","failClosed":true}}' "$policy" > "$tmp/$name-policy.json"
  mv "$tmp/$name-policy.json" "$policy"
  (cd "$project" && pwd -P)
}

snapshot_project() {
  local project="$1" destination="$2"
  python3 "$root/tests/worktree-snapshot-test-only.py" "$project" > "$destination"
}

run_dispatch() {
  local project="$1"
  shift
  MANA_UPDATE_CHECK=off "$root/scripts/run-profile.sh" mana-help --project-root "$project" "$@"
}

assert_dispatch_category() {
  local stderr_path="$1" category="$2"
  grep -Fq "ERROR: $category:" "$stderr_path" || fail "dispatch did not report $category"
  [ "$(grep -Ec '^ERROR:' "$stderr_path")" = 1 ] || fail 'dispatch emitted more than one public error'
  [ "$(wc -l < "$stderr_path" | tr -d ' ')" = 1 ] || fail 'dispatch exposed output beyond its one public error'
}

initialize() {
  local project="$1" execution="$2"
  "$pipeline" initialize ctx06c-fixture --framework-root "$framework" \
    --project-root "$project" --execution-id "$execution" --provider codex \
    --workspace '.mana/sessions/ctx06c-fixture' \
    --objective 'Complete the current bounded fixture phase.' >/dev/null
}

run_fixture() {
  local project="$1" execution="$2" state="$3" scenario="$4"
  shift 4
  PATH="$tmp/bin:$PATH" CTX06C_FIXTURE_ROOT="$fixture_root" \
    CTX06C_STATE_DIR="$state" CTX06C_SCENARIO="$scenario" \
    "$runner" "$execution" --project-root "$project" \
      --profile ctx06c-fixture --provider codex \
      --codex-model economy-fixture --codex-full-model full-fixture "$@"
}

# Provider-specific phase argv is isolated from profiles and mechanically
# disables child execution. CTX-07 provider-managed children remain absent.
. "$root/scripts/lib/provider-dispatch.sh"
schema="$root/contracts/context-runtime/phase-checkpoint-v1.schema.json"
budget_helper="$root/tests/context-budget-test-only.py"
budget_policy="$framework/config/context-runtime/provider-budget-policy-v1.json"
budget_resolution="$tmp/budget-resolution.json"
python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/context-runtime/provider-budget-policy-v1.schema.json" "$budget_policy" || fail 'CTX-08 fixture budget policy violates its schema'
python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/context-runtime/provider-budget-policy-v1.schema.json" "$root/config/context-runtime/provider-budget-policy-v1.json" || fail 'CTX-08 production budget policy violates its schema'
"$budget_helper" resolve ctx06c-fixture standard > "$budget_resolution" || fail 'CTX-08 did not resolve its host policy'
jq -e '.calibration.status=="provisional-no-empirical-baseline" and .mode=="standard" and .limits.automaticCompactionThresholdTokens==100000' "$budget_resolution" >/dev/null || fail 'CTX-08 policy lost its provisional standard budget'
"$budget_helper" resolve ctx06c-fixture deep > "$tmp/budget-deep.json" || fail 'CTX-08 did not resolve deep budget'
jq -e --slurpfile standard "$budget_resolution" '.limits.automaticCompactionThresholdTokens > $standard[0].limits.automaticCompactionThresholdTokens and .limits.cumulativeInputWarningTokens > $standard[0].limits.cumulativeInputWarningTokens and .limits.childExecution=="disabled"' "$tmp/budget-deep.json" >/dev/null || fail 'deep CTX-08 budget did not increase without enabling children'
for concept in 'current human goal' 'immutable governance constraints' 'verified facts with evidence references' 'Never turn an assumption or inference into a verified fact.' 'Never remove an unresolved blocker'; do
  jq -r '.compactionPrompt.text' "$budget_policy" | grep -Fq -- "$concept" || fail "versioned compact prompt omitted required concept: $concept"
done
"$root/scripts/mana-provider-capabilities.sh" codex --fixture "$fixture_root/provider-capabilities/codex-supported" > "$tmp/codex-capabilities.json"
"$budget_helper" capability-plan "$budget_resolution" "$tmp/codex-capabilities.json" > "$tmp/codex-budget-plan.json" || fail 'CTX-08 rejected a valid Codex capability report'
jq -e '.controls.automaticCompactionThreshold == {status:"unknown",requested:100000,applied:false,reason:"capability-unknown"} and .controls.toolOutputRetentionTokenLimit.applied==false and .controls.hardSubagentDisable.applied==true' "$tmp/codex-budget-plan.json" >/dev/null || fail 'CTX-08 guessed an unsupported Codex control'
"$root/scripts/mana-provider-capabilities.sh" claude --fixture "$fixture_root/provider-capabilities/claude-supported" > "$tmp/claude-capabilities.json"
"$budget_helper" capability-plan "$budget_resolution" "$tmp/claude-capabilities.json" > "$tmp/claude-budget-plan.json" || fail 'CTX-08 rejected a valid Claude capability report'
jq -e '.controls.automaticCompactionThreshold == {status:"supported",requested:100000,applied:true,reason:"capability-supported"} and .controls.customCompactionPrompt.applied==false and .controls.compactionScope.applied==false' "$tmp/claude-budget-plan.json" >/dev/null || fail 'CTX-08 capability gating did not preserve explicit unknown controls'
mana_provider_phase_args codex '/project with spaces' economy-fixture "$schema" true || fail 'Codex phase adapter failed'
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" | grep -Fxq -- '--output-schema' || fail 'Codex native schema flag missing'
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" | grep -Fxq -- 'read-only' || fail 'Codex phase sandbox is not read-only'
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" | grep -Fxq -- '--ephemeral' || fail 'Codex phase is not ephemeral'
[ "$(printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" | grep -Fxc -- '--disable')" = 2 ] || fail 'Codex phase did not disable both child features'
! printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" | grep -Fxq -- 'on-request' || fail 'Codex phase retained interactive approval mode'
mana_provider_phase_args claude '/project with spaces' economy-fixture "$schema" true || fail 'Claude phase adapter failed'
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" | grep -Fxq -- '--safe-mode' || fail 'Claude safe mode missing'
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" | grep -Fxq -- '--json-schema' || fail 'Claude native schema flag missing'
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" | grep -Fxq -- 'Agent,Bash,Edit,Write,WebFetch,WebSearch' || fail 'Claude write/child tool deny missing'
mana_provider_phase_args claude '/project with spaces' economy-fixture "$schema" true 100000 || fail 'Claude CTX-08 compaction adapter failed'
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" | grep -Fxq -- '--autocompact' || fail 'supported Claude compaction control missing from exact argv'
awk 'previous == "--autocompact" && $0 == "100000" { found=1 } { previous=$0 } END { exit(found ? 0 : 1) }' <(printf '%s\n' "${MANA_PROVIDER_ARGS[@]}") || fail 'Claude compaction threshold was not passed exactly'
mana_provider_phase_args opencode '/project with spaces' economy-fixture "$schema" false || fail 'OpenCode phase adapter construction failed'
jq -e '.agent.mana_ctx06_phase.permission == {task:"deny",edit:"deny",bash:"deny"}' \
  <<<"$MANA_PROVIDER_OPENCODE_CONFIG_CONTENT" >/dev/null || fail 'OpenCode phase deny configuration changed'

# A complete two-phase run launches two separate provider processes, routes
# economy/full models from the declared policies, and advances only through
# the CTX-06B reducer/CAS protocol.
execution='execution-ctx06c-complete'
project="$(make_project complete)"
state="$tmp/complete/provider-state"
mkdir -p "$project/.mana/context-runtime"
printf '%s\n' '{"schemaVersion":"mana.context-runtime.rollout-policy/v1","defaultMode":"legacy","profiles":{"ctx06c-fixture":{"mode":"v2","failClosed":true}}}' \
  > "$project/.mana/context-runtime/runtime-selection-v1.json"
initialize "$project" "$execution"
workspace_id="$(jq -r .workspaceId "$project/.mana/runtime/runs/$execution/execution-envelope-v1.json")"
python3 "$root/scripts/context-runtime-rollout.py" materialize-decision \
  --project-root "$project" --profile ctx06c-fixture --execution-id "$execution" \
  --execution-version 1 --workspace-id "$workspace_id" >/dev/null || fail 'external rollout selection did not commit'
run_fixture "$project" "$execution" "$state" complete > "$tmp/complete-result.json" || fail 'complete phase run failed'
jq -e '.status=="completed" and .providerInvocations==2 and .revision==2 and (.transitionId|test("^T-[a-f0-9]{64}$"))' \
  "$tmp/complete-result.json" >/dev/null || fail 'complete phase result is incorrect'
[ "$(cat "$state/count")" = 2 ] || fail 'phase runner did not launch exactly two fresh invocations'
grep -Fxq economy-fixture "$state/model.1" || fail 'economy phase used the wrong model'
grep -Fxq full-fixture "$state/model.2" || fail 'full phase used the wrong model'
grep -Fxq "$schema" "$state/schema.1" || fail 'phase schema was not host-owned'
grep -Fxq "$schema" "$state/schema.2" || fail 'terminal phase schema was not host-owned'
! grep -Fxq -- '--autocompact' "$state/argv.1" || fail 'unknown Codex compaction control was guessed into provider argv'
! grep -Fxq -- '--autocompact' "$state/argv.2" || fail 'unknown Codex compaction control was guessed into provider argv'
grep -Fxq "$project" "$state/cwd.1" || fail 'first provider process used the wrong working directory'
grep -Fxq "$project" "$state/cwd.2" || fail 'second provider process used the wrong working directory'
jq -e '.status=="completed" and .revision==2 and .currentPhaseId=="synthesize" and .attempts=={classify:1,synthesize:1}' \
  "$project/.mana/runtime/runs/$execution/run-state-v1.json" >/dev/null || fail 'authoritative HEAD did not complete in declared order'
[ "$(find "$project/.mana/runtime/runs/$execution/transitions" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" = 2 ] || fail 'transition bundle count changed'

envelope_canonical="$(jq -cS . "$project/.mana/runtime/runs/$execution/execution-envelope-v1.json")"
for prompt in "$state/prompt.1" "$state/prompt.2"; do
  grep -Fxq "executionEnvelope=$envelope_canonical" "$prompt" || fail 'governance envelope was not re-injected exactly'
  [ "$(grep -Fc 'BEGIN_MANA_PHASE_PACKET' "$prompt")" = 1 ] || fail 'phase prompt packet boundary changed'
  ! grep -Fq 'provider response' "$prompt" || fail 'provider transcript crossed a phase boundary'
done
jq -e '.id=="classify" and .policy.modelTier=="economy"' \
  <<<"$(sed -n 's/^phasePolicy=//p' "$state/prompt.1")" >/dev/null || fail 'first prompt omitted current policy'
jq -e '.id=="synthesize" and .policy.modelTier=="full"' \
  <<<"$(sed -n 's/^phasePolicy=//p' "$state/prompt.2")" >/dev/null || fail 'second prompt carried the wrong phase policy'
jq -e '.phaseId=="classify" and .nextActionRequest.targetId=="synthesize"' \
  <<<"$(sed -n 's/^previousCheckpoint=//p' "$state/prompt.2")" >/dev/null || fail 'validated checkpoint did not cross the fresh boundary'

metrics="$project/.mana/runtime/metrics/$execution/usage-summary-v1.json"
python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/context-runtime/usage-summary-v1.schema.json" "$metrics" || fail 'phased metrics violate usage-summary-v1'
jq -e '.status=="complete" and .providerVersion=="0.148.0" and (.phases|length)==2 and
       [.phases[].phaseId]==["classify","synthesize"] and
       .totals=={input:20,cachedInput:4,uncachedInput:16,output:6,reasoning:2} and
       .rawTraceRetained==false' "$metrics" >/dev/null || fail 'phase usage was not aggregated safely'
[ "$(find "$project/.mana/runtime/metrics/$execution/phases" -name '*.json' -type f | wc -l | tr -d ' ')" = 2 ] || fail 'per-phase metric snapshots are missing'
"$budget_helper" usage-check "$budget_resolution" "$metrics" > "$tmp/budget-no-warning.json" || fail 'CTX-08 could not read a measured CTX-01 aggregate'
jq -e '.measured==true and .warnings==[]' "$tmp/budget-no-warning.json" >/dev/null || fail 'CTX-08 warned below provisional thresholds'
jq -n '{usageStatus:"measured",totals:{input:360000,cachedInput:180000,uncachedInput:180000,output:1,reasoning:1}}' > "$tmp/budget-warning-summary.json"
"$budget_helper" usage-check "$budget_resolution" "$tmp/budget-warning-summary.json" > "$tmp/budget-warning.json" || fail 'CTX-08 could not evaluate measured thresholds'
jq -e '.measured==true and (.warnings|sort)==["cached-input","cumulative-input","uncached-input"] and .recommendation=="checkpoint-and-fresh-phase"' "$tmp/budget-warning.json" >/dev/null || fail 'CTX-08 did not keep cumulative, cached, and uncached warnings distinct'
events="$project/.mana/runtime/events/$execution.jsonl"
[ "$(grep -Fc '"eventType":"phase.started"' "$events")" = 2 ] || fail 'phase lifecycle start events are incomplete'
[ "$(grep -Fc '"eventType":"provider.invoked"' "$events")" = 2 ] || fail 'provider lifecycle events are incomplete'
[ "$(grep -Fc '"eventType":"phase.checkpoint.accepted"' "$events")" = 2 ] || fail 'checkpoint lifecycle events are incomplete'
! grep -R -Fq 'turn.completed' "$project/.mana/runtime/runs/$execution" "$project/.mana/runtime/metrics/$execution" "$events" || fail 'provider trace leaked into durable runtime artifacts'
! find "$project/.mana/runtime/metrics/$execution" -name 'raw-provider-events.jsonl' -print | grep -q . || fail 'raw trace survived without debug opt-in'

# Debug retention is explicit and archives one restrictive trace beside each
# immutable per-phase metric snapshot; the mutable root trace never survives.
debug_execution='execution-ctx06c-debug-trace'
debug_project="$(make_project debug-trace)"
debug_state="$tmp/debug-trace/provider-state"
initialize "$debug_project" "$debug_execution"
MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE=true \
  run_fixture "$debug_project" "$debug_execution" "$debug_state" complete > "$tmp/debug-result.json" || fail 'debug-retained phase run failed'
debug_metrics="$debug_project/.mana/runtime/metrics/$debug_execution/usage-summary-v1.json"
jq -e '.status=="complete" and .rawTraceRetained==true and
       (.phases|length)==2 and ([.phases[].rawTraceRetained]|all)' \
  "$debug_metrics" >/dev/null || fail 'debug trace retention was not aggregated by phase'
[ "$(find "$debug_project/.mana/runtime/metrics/$debug_execution/phases" -name '*-raw-provider-events.jsonl' -type f | wc -l | tr -d ' ')" = 2 ] || fail 'debug phase traces were not archived exactly once'
while IFS= read -r trace; do
  [ "$(ctx06c_file_mode "$trace")" = 600 ] || fail 'debug phase trace permissions are not restrictive'
done < <(find "$debug_project/.mana/runtime/metrics/$debug_execution/phases" -name '*-raw-provider-events.jsonl' -type f)
[ ! -e "$debug_project/.mana/runtime/metrics/$debug_execution/raw-provider-events.jsonl" ] || fail 'mutable root provider trace survived archival'

# Invalid semantic output is neither retried nor published. Metrics and a
# privacy-safe failure event remain, while authoritative revision stays zero.
invalid_execution='execution-ctx06c-invalid'
invalid_project="$(make_project invalid)"
invalid_state="$tmp/invalid/provider-state"
initialize "$invalid_project" "$invalid_execution"
if run_fixture "$invalid_project" "$invalid_execution" "$invalid_state" invalid > "$tmp/invalid.out" 2> "$tmp/invalid.err"; then
  fail 'invalid provider checkpoint was accepted'
fi
[ "$(cat "$invalid_state/count")" = 1 ] || fail 'invalid semantic output was silently retried'
jq -e '.revision==0 and .status=="active" and .latestCheckpointRef==null' \
  "$invalid_project/.mana/runtime/runs/$invalid_execution/run-state-v1.json" >/dev/null || fail 'invalid output advanced authoritative HEAD'
[ -z "$(find "$invalid_project/.mana/runtime/runs/$invalid_execution/transitions" -mindepth 1 -print -quit)" ] || fail 'invalid output published a transition bundle'
jq -e '.status=="failed" and (.phases|length)==1' \
  "$invalid_project/.mana/runtime/metrics/$invalid_execution/usage-summary-v1.json" >/dev/null || fail 'invalid-output metrics are incomplete'
! grep -R -Fq 'provider response' "$invalid_project" || fail 'invalid provider output was persisted'

# Interruption after one accepted checkpoint keeps that checkpoint and next
# input authoritative. A later invocation resumes the active phase without a
# transcript and completes through a new provider process.
interrupt_execution='execution-ctx06c-interrupt'
interrupt_project="$(make_project interrupt)"
interrupt_state="$tmp/interrupt/provider-state"
initialize "$interrupt_project" "$interrupt_execution"
if run_fixture "$interrupt_project" "$interrupt_execution" "$interrupt_state" interrupt-second > "$tmp/interrupt.out" 2> "$tmp/interrupt.err"; then
  fail 'interrupted provider run succeeded'
else
  interrupt_status=$?
fi
[ "$interrupt_status" = 143 ] || fail "interrupted runner returned $interrupt_status instead of 143"
jq -e '.revision==1 and .status=="active" and .currentPhaseId=="synthesize" and (.latestCheckpointRef|test("^C-"))' \
  "$interrupt_project/.mana/runtime/runs/$interrupt_execution/run-state-v1.json" >/dev/null || fail 'interruption lost the last validated checkpoint'
[ "$(find "$interrupt_project/.mana/runtime/runs/$interrupt_execution/transitions" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" = 1 ] || fail 'interruption published provider output as a transition'
jq -e '.status=="interrupted" and (.phases|length)==2' \
  "$interrupt_project/.mana/runtime/metrics/$interrupt_execution/usage-summary-v1.json" >/dev/null || fail 'interrupted phase metrics are missing'
run_fixture "$interrupt_project" "$interrupt_execution" "$interrupt_state" complete > "$tmp/resumed-result.json" || fail 'interrupted run did not resume'
jq -e '.status=="completed" and .revision==2 and .providerInvocations==1' "$tmp/resumed-result.json" >/dev/null || fail 'resumed result is incorrect'
[ "$(cat "$interrupt_state/count")" = 3 ] || fail 'resume did not use exactly one new fresh invocation'
jq -e '.status=="complete" and (.phases|length)==3' \
  "$interrupt_project/.mana/runtime/metrics/$interrupt_execution/usage-summary-v1.json" >/dev/null || fail 'resumed metrics lost prior phase attempts'
! grep -R -Fq 'turn.completed' "$interrupt_project/.mana/runtime/runs/$interrupt_execution" || fail 'interrupted provider trace entered checkpoint state'

# Concurrent hosts serialize provider work for this read-only run. The second
# host observes completed HEAD and performs no duplicate provider invocation;
# transition authority still comes only from the existing CTX-06B CAS chain.
concurrent_execution='execution-ctx06c-concurrent'
concurrent_project="$(make_project concurrent)"
concurrent_state="$tmp/concurrent/provider-state"
initialize "$concurrent_project" "$concurrent_execution"
run_fixture "$concurrent_project" "$concurrent_execution" "$concurrent_state" complete > "$tmp/concurrent-one.json" 2> "$tmp/concurrent-one.err" &
first_pid=$!
run_fixture "$concurrent_project" "$concurrent_execution" "$concurrent_state" complete > "$tmp/concurrent-two.json" 2> "$tmp/concurrent-two.err" &
second_pid=$!
wait "$first_pid" || { cat "$tmp/concurrent-one.err" >&2; fail 'first concurrent runner failed'; }
wait "$second_pid" || { cat "$tmp/concurrent-two.err" >&2; fail 'second concurrent runner failed'; }
[ "$(cat "$concurrent_state/count")" = 2 ] || fail 'concurrent hosts duplicated a provider phase'
jq -s -e '([.[].status]|all(.=="completed")) and ([.[].providerInvocations]|sort)==[0,2]' \
  "$tmp/concurrent-one.json" "$tmp/concurrent-two.json" >/dev/null || fail 'concurrent runner results did not converge'
jq -e '.revision==2 and .status=="completed"' "$concurrent_project/.mana/runtime/runs/$concurrent_execution/run-state-v1.json" >/dev/null || fail 'concurrent runner changed authoritative completion'
[ "$(ctx06c_file_mode "$concurrent_project/.mana/runtime/runs/$concurrent_execution/.provider-phase.lock")" = 600 ] || fail 'provider phase lock permissions are not restrictive'

# CTX-02 unknown/unsupported isolation cannot silently select a weaker path.
limited_execution='execution-ctx06c-capability-gap'
limited_project="$(make_project capability-gap)"
limited_state="$tmp/capability-gap/provider-state"
initialize "$limited_project" "$limited_execution"
if PATH="$tmp/bin:$PATH" CTX06C_FIXTURE_ROOT="$fixture_root" CTX06C_STATE_DIR="$limited_state" \
  CTX06C_SCENARIO=complete CTX06C_CAPABILITY_SET=codex-limited \
  "$runner" "$limited_execution" --project-root "$limited_project" \
    --profile ctx06c-fixture --provider codex > "$tmp/capability-gap.out" 2> "$tmp/capability-gap.err"; then
  fail 'capability gap silently invoked a provider phase'
fi
[ ! -f "$limited_state/count" ] || fail 'provider was invoked after a capability gate failure'
grep -Eq 'capability .* (unknown|unsupported)' "$tmp/capability-gap.err" || fail 'capability gap was not reported explicitly'
jq -e '.revision==0 and .status=="active"' "$limited_project/.mana/runtime/runs/$limited_execution/run-state-v1.json" >/dev/null || fail 'capability gap changed run state'

# Legacy remains the default. V2 selection is explicit and requires an
# existing CTX-06A execution rather than silently falling back to one session.
legacy_project="$(make_project legacy)"
MANA_UPDATE_CHECK=off "$root/scripts/run-profile.sh" mana-help --project-root "$legacy_project" --render-only > "$tmp/legacy-default.out" 2> "$tmp/legacy-default.err" || fail 'default legacy renderer failed'
grep -Fq 'Profile: mana-help' "$tmp/legacy-default.out" || fail 'default no longer uses the legacy renderer'

# CTX-10-R2.2: A is the actual missing-run boundary. The rollout policy is
# valid and v2-opted-in, and exactly one valid provider runner is selected;
# only the initialized CTX-06 identity is absent. Check the stable category
# before the bounded human context, and prove no provider or runtime artifact
# can be created before this host-owned rejection.
missing_run_project="$(make_dispatch_project missing-run)"
snapshot_project "$missing_run_project" "$tmp/missing-run-before"
if PATH="$tmp/bin:$PATH" CTX06C_FIXTURE_ROOT="$fixture_root" CTX06C_STATE_DIR="$tmp/missing-run-provider-state" \
  CTX06C_SCENARIO=complete run_dispatch "$missing_run_project" --codex --context-runtime v2 \
  > "$tmp/missing-run.out" 2> "$tmp/missing-run.err"; then
  fail 'v2 missing run with a valid runner succeeded'
else
  missing_run_status=$?
fi
[ "$missing_run_status" = 2 ] || fail "v2 missing run returned $missing_run_status instead of 2"
assert_dispatch_category "$tmp/missing-run.err" CTX10_EXECUTION_IDENTITY_REQUIRED
grep -Fq 'initialized CTX-06 execution identity' "$tmp/missing-run.err" || fail 'v2 missing run omitted bounded human context'
[ ! -s "$tmp/missing-run.out" ] || fail 'v2 missing run wrote a success or provider result to stdout'
[ ! -e "$tmp/missing-run-provider-state/count" ] || fail 'v2 missing run reached the provider stub'
! grep -Fq 'Profile: mana-help' "$tmp/missing-run.out" "$tmp/missing-run.err" || fail 'v2 missing run fell back to legacy'
! grep -Fq "$missing_run_project" "$tmp/missing-run.err" || fail 'v2 missing run exposed a project path'
! find "$missing_run_project/.mana" -path '*/runtime/*' -print -quit | grep -q . || fail 'v2 missing run created a runtime artifact'
snapshot_project "$missing_run_project" "$tmp/missing-run-after"
cmp -s "$tmp/missing-run-before" "$tmp/missing-run-after" || fail 'v2 missing run mutated its project fixture'

# B/C exercise the same public dispatch seam after its authoritative reader
# has admitted a canonical CTX-06 identity. The real CTX-06 lifecycle remains
# covered by the fresh phase cases above; this narrow reader fixture prevents a
# provider binary from becoming a second missing precondition.
reader_bin="$tmp/ctx10-reader-bin"
mkdir -p "$reader_bin"
cp "$fixture_root/ctx10-execution-identity-python-stub.sh" "$reader_bin/python3"
chmod 700 "$reader_bin/python3"
real_python="$(command -v python3)"

# B: an admitted run with no selected runner is categorically distinct from A.
runner_missing_project="$(make_dispatch_project runner-missing)"
if PATH="$reader_bin:/usr/bin:/bin" CTX10_EXECUTION_IDENTITY_TOOL="$root/scripts/context-runtime-rollout.py" \
  CTX10_REAL_PYTHON="$real_python" run_dispatch "$runner_missing_project" \
  --runtime-execution-id execution-ctx10-fixture --context-runtime v2 \
  > "$tmp/runner-missing.out" 2> "$tmp/runner-missing.err"; then
  fail 'v2 admitted run without a provider runner succeeded'
else
  runner_missing_status=$?
fi
[ "$runner_missing_status" = 2 ] || fail "v2 missing runner returned $runner_missing_status instead of 2"
assert_dispatch_category "$tmp/runner-missing.err" CTX10_PROVIDER_RUNNER_SELECTION_REQUIRED
[ ! -s "$tmp/runner-missing.out" ] || fail 'v2 missing runner wrote stdout'

# C: more than one runner is rejected at the same stable selection boundary.
runner_multiple_project="$(make_dispatch_project runner-multiple)"
if PATH="$reader_bin:/usr/bin:/bin" CTX10_EXECUTION_IDENTITY_TOOL="$root/scripts/context-runtime-rollout.py" \
  CTX10_REAL_PYTHON="$real_python" run_dispatch "$runner_multiple_project" --claude \
  --runtime-execution-id execution-ctx10-fixture --codex --context-runtime v2 \
  > "$tmp/runner-multiple.out" 2> "$tmp/runner-multiple.err"; then
  fail 'v2 admitted run with multiple provider runners succeeded'
else
  runner_multiple_status=$?
fi
[ "$runner_multiple_status" = 2 ] || fail "v2 multiple runners returned $runner_multiple_status instead of 2"
assert_dispatch_category "$tmp/runner-multiple.err" CTX10_PROVIDER_RUNNER_SELECTION_REQUIRED
[ ! -s "$tmp/runner-multiple.out" ] || fail 'v2 multiple runners wrote stdout'

# D is intentionally separate from A: when both values are absent, R2.1's
# contract says the missing CTX-06 identity wins deterministically.
both_missing_project="$(make_dispatch_project both-missing)"
if run_dispatch "$both_missing_project" --context-runtime v2 \
  > "$tmp/both-missing.out" 2> "$tmp/both-missing.err"; then
  fail 'v2 missing run and runner succeeded'
else
  both_missing_status=$?
fi
[ "$both_missing_status" = 2 ] || fail "v2 missing run and runner returned $both_missing_status instead of 2"
assert_dispatch_category "$tmp/both-missing.err" CTX10_EXECUTION_IDENTITY_REQUIRED
[ ! -s "$tmp/both-missing.out" ] || fail 'v2 missing run and runner wrote stdout'

# E: a syntactically valid, explicitly supplied identity that has no CTX-06
# run is categorically distinct from an omitted identity.  Invoke from an
# unrelated cwd that already contains a homonymous .mana tree and prove the
# authorized project root is the only lookup target and neither tree changes.
missing_initialized_project="$(make_dispatch_project missing-initialized)"
missing_initialized_execution='execution-valid-looking-but-absent'
outside_cwd="$tmp/external cwd"
mkdir -p "$outside_cwd/.mana/runtime/runs/$missing_initialized_execution"
printf '%s\n' 'outside-sentinel' > "$outside_cwd/.mana/runtime/runs/$missing_initialized_execution/sentinel.txt"
snapshot_project "$missing_initialized_project" "$tmp/missing-initialized-before"
snapshot_project "$outside_cwd" "$tmp/outside-cwd-before"
if (cd "$outside_cwd" && PATH="$tmp/bin:$PATH" \
    CTX06C_FIXTURE_ROOT="$fixture_root" CTX06C_STATE_DIR="$tmp/missing-initialized-provider-state" \
    CTX06C_SCENARIO=complete run_dispatch "$missing_initialized_project" \
      --runtime-execution-id "$missing_initialized_execution" --codex --context-runtime v2 \
      > "$tmp/missing-initialized.out" 2> "$tmp/missing-initialized.err"); then
  fail 'v2 valid-looking nonexistent run succeeded'
else
  missing_initialized_status=$?
fi
[ "$missing_initialized_status" = 2 ] || fail "v2 nonexistent run returned $missing_initialized_status instead of 2"
assert_dispatch_category "$tmp/missing-initialized.err" CTX10_EXECUTION_NOT_INITIALIZED
grep -Fq 'initialized CTX-06 execution identity' "$tmp/missing-initialized.err" || fail 'nonexistent run omitted bounded human context'
[ ! -s "$tmp/missing-initialized.out" ] || fail 'nonexistent run wrote stdout'
! grep -Eq 'Traceback|FileNotFoundError|scripts/|\.py", line|/' "$tmp/missing-initialized.err" || fail 'nonexistent run leaked a stack or absolute path'
[ ! -e "$tmp/missing-initialized-provider-state/count" ] || fail 'nonexistent run reached the provider'
[ ! -e "$missing_initialized_project/.mana/runtime/runs/$missing_initialized_execution" ] || fail 'nonexistent run created its run directory'
! find "$missing_initialized_project" -name '.provider-phase.lock' -print -quit | grep -q . || fail 'nonexistent run created a provider-phase lock'
! grep -Fq 'Profile: mana-help' "$tmp/missing-initialized.out" "$tmp/missing-initialized.err" || fail 'nonexistent run fell back to legacy'
snapshot_project "$missing_initialized_project" "$tmp/missing-initialized-after"
snapshot_project "$outside_cwd" "$tmp/outside-cwd-after"
cmp -s "$tmp/missing-initialized-before" "$tmp/missing-initialized-after" || fail 'nonexistent run mutated the authorized project fixture'
cmp -s "$tmp/outside-cwd-before" "$tmp/outside-cwd-after" || fail 'nonexistent run mutated the external cwd'

# The direct v2 entry point enforces the same read-only gate before its
# with-run-lock bootstrap, so bypassing run-profile.sh cannot create the lock.
direct_missing_project="$(make_project direct-missing-initialized)"
snapshot_project "$direct_missing_project" "$tmp/direct-missing-before"
if (cd "$outside_cwd" && run_fixture "$direct_missing_project" \
    "$missing_initialized_execution" "$tmp/direct-missing-provider-state" complete \
    > "$tmp/direct-missing.out" 2> "$tmp/direct-missing.err"); then
  fail 'direct v2 runner accepted a nonexistent run'
else
  direct_missing_status=$?
fi
[ "$direct_missing_status" = 2 ] || fail "direct nonexistent run returned $direct_missing_status instead of 2"
assert_dispatch_category "$tmp/direct-missing.err" CTX10_EXECUTION_NOT_INITIALIZED
[ ! -s "$tmp/direct-missing.out" ] || fail 'direct nonexistent run wrote stdout'
[ ! -e "$direct_missing_project/.mana/runtime/runs/$missing_initialized_execution" ] || fail 'direct nonexistent run created its run directory'
! find "$direct_missing_project" -name '.provider-phase.lock' -print -quit | grep -q . || fail 'direct nonexistent run created a provider-phase lock'
[ ! -e "$tmp/direct-missing-provider-state/count" ] || fail 'direct nonexistent run reached the provider'
snapshot_project "$direct_missing_project" "$tmp/direct-missing-after"
cmp -s "$tmp/direct-missing-before" "$tmp/direct-missing-after" || fail 'direct nonexistent run mutated its project fixture'

# A coherent v2 -> shadow rewrite of the decision JSON must not authenticate
# itself.  The external bundle-manifest plus parent HEAD commitment rejects it
# before shadow or any provider is selected, and the public category stays stable.
tamper_project="$(make_dispatch_project decision-tamper)"
tamper_execution='execution-ctx10-fixture'
tamper_workspace="W-$(printf 'a%.0s' {1..64})"
python3 "$root/scripts/context-runtime-rollout.py" materialize-decision \
  --project-root "$tamper_project" --profile mana-help \
  --execution-id "$tamper_execution" --execution-version 1 \
  --workspace-id "$tamper_workspace" >/dev/null
tamper_decision="$(find "$tamper_project/.mana/context-runtime/decisions" -name decision-v1.json -type f -print -quit)"
jq -cS '.configuredMode="shadow" | .effectiveMode="shadow"' "$tamper_decision" > "$tmp/tampered-decision.json"
mv "$tmp/tampered-decision.json" "$tamper_decision"
if PATH="$reader_bin:/usr/bin:/bin" CTX10_EXECUTION_IDENTITY_TOOL="$root/scripts/context-runtime-rollout.py" \
  CTX10_REAL_PYTHON="$real_python" CTX06C_STATE_DIR="$tmp/tamper-provider-state" \
  run_dispatch "$tamper_project" --runtime-execution-id "$tamper_execution" \
    --codex --context-runtime v2 > "$tmp/tamper.out" 2> "$tmp/tamper.err"; then
  fail 'coherently tampered v2-to-shadow decision succeeded'
else
  tamper_status=$?
fi
[ "$tamper_status" = 2 ] || fail "tampered decision returned $tamper_status instead of 2"
assert_dispatch_category "$tmp/tamper.err" CTX10_DECISION_AUTHORITY_REJECTED
[ ! -s "$tmp/tamper.out" ] || fail 'tampered decision wrote stdout'
[ ! -e "$tmp/tamper-provider-state/count" ] || fail 'tampered decision reached a provider'
! grep -Fq 'shadow' "$tmp/tamper.out" || fail 'tampered decision selected shadow'

# The complete fresh run above is the nominal valid-run plus valid-runner
# control: it still executes two provider phases through run-profile-v2.sh.
git -C "$root" status --porcelain=v1 --ignored > "$tmp/repository-after.status"
cmp -s "$tmp/repository-before.status" "$tmp/repository-after.status" || fail 'CTX-10-R2.2 dispatch cases mutated the Mana repository'

echo 'Context Runtime CTX-06C provider phase integration tests passed (fresh, capability-gated, privacy-preserving, zero-token)'
