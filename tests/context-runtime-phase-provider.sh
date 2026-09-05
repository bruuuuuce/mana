#!/usr/bin/env bash
# CTX-06C deterministic fresh-provider, lifecycle, metrics, and fallback gate.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
pipeline="$root/scripts/mana-context-pipeline.sh"
runner="$root/scripts/run-profile-v2.sh"
framework="$root/tests/fixtures/context-runtime/ctx06a-framework"
fixture_root="$root/tests/fixtures/context-runtime"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-context-06c.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

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
    "$runner" "$execution" --project-root "$project" --framework-root "$framework" \
      --profile ctx06c-fixture --provider codex \
      --codex-model economy-fixture --codex-full-model full-fixture "$@"
}

# Provider-specific phase argv is isolated from profiles and mechanically
# disables child execution. CTX-07 provider-managed children remain absent.
. "$root/scripts/lib/provider-dispatch.sh"
schema="$root/contracts/context-runtime/phase-checkpoint-v1.schema.json"
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
mana_provider_phase_args opencode '/project with spaces' economy-fixture "$schema" false || fail 'OpenCode phase adapter construction failed'
jq -e '.agent.mana_ctx06_phase.permission == {task:"deny",edit:"deny",bash:"deny"}' \
  <<<"$MANA_PROVIDER_OPENCODE_CONFIG_CONTENT" >/dev/null || fail 'OpenCode phase deny configuration changed'

# A complete two-phase run launches two separate provider processes, routes
# economy/full models from the declared policies, and advances only through
# the CTX-06B reducer/CAS protocol.
execution='execution-ctx06c-complete'
project="$(make_project complete)"
state="$tmp/complete/provider-state"
initialize "$project" "$execution"
run_fixture "$project" "$execution" "$state" complete > "$tmp/complete-result.json" || fail 'complete phase run failed'
jq -e '.status=="completed" and .providerInvocations==2 and .revision==2 and (.transitionId|test("^T-[a-f0-9]{64}$"))' \
  "$tmp/complete-result.json" >/dev/null || fail 'complete phase result is incorrect'
[ "$(cat "$state/count")" = 2 ] || fail 'phase runner did not launch exactly two fresh invocations'
grep -Fxq economy-fixture "$state/model.1" || fail 'economy phase used the wrong model'
grep -Fxq full-fixture "$state/model.2" || fail 'full phase used the wrong model'
grep -Fxq "$schema" "$state/schema.1" || fail 'phase schema was not host-owned'
grep -Fxq "$schema" "$state/schema.2" || fail 'terminal phase schema was not host-owned'
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
  [ "$(stat -f '%Lp' "$trace")" = 600 ] || fail 'debug phase trace permissions are not restrictive'
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
[ "$(stat -f '%Lp' "$concurrent_project/.mana/runtime/runs/$concurrent_execution/.provider-phase.lock")" = 600 ] || fail 'provider phase lock permissions are not restrictive'

# CTX-02 unknown/unsupported isolation cannot silently select a weaker path.
limited_execution='execution-ctx06c-capability-gap'
limited_project="$(make_project capability-gap)"
limited_state="$tmp/capability-gap/provider-state"
initialize "$limited_project" "$limited_execution"
if PATH="$tmp/bin:$PATH" CTX06C_FIXTURE_ROOT="$fixture_root" CTX06C_STATE_DIR="$limited_state" \
  CTX06C_SCENARIO=complete CTX06C_CAPABILITY_SET=codex-limited \
  "$runner" "$limited_execution" --project-root "$limited_project" --framework-root "$framework" \
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
if MANA_UPDATE_CHECK=off "$root/scripts/run-profile.sh" mana-help --project-root "$legacy_project" --codex --context-runtime v2 > "$tmp/v2-no-run.out" 2> "$tmp/v2-no-run.err"; then
  fail 'v2 selection without an initialized execution fell back to legacy'
fi
grep -Fq 'context runtime v2 requires --runtime-execution-id' "$tmp/v2-no-run.err" || fail 'v2 missing-run error is not explicit'

echo 'Context Runtime CTX-06C provider phase integration tests passed (fresh, capability-gated, privacy-preserving, zero-token)'
