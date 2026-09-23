#!/usr/bin/env bash
# CTX-07B fresh host-launched workers plus the optional CTX-07C provider-child
# adapter. Plans/results remain CTX-07A data; CTX-06B HEAD remains the sole
# runtime authority and CTX-07B remains the correctness fallback.
set -euo pipefail
umask 077

script_path="${BASH_SOURCE[0]}"
while [ -L "$script_path" ]; do
  script_directory="$(cd "$(dirname "$script_path")" && pwd -P)"
  script_target="$(readlink "$script_path")"
  case "$script_target" in
    /*) script_path="$script_target" ;;
    *) script_path="$script_directory/$script_target" ;;
  esac
done
root="$(cd "$(dirname "$script_path")/.." && pwd -P)"
invoked_path="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"
test_entrypoint="$root/tests/run-context-workers-test-only.sh"
retain_test_entrypoint="$root/tests/run-context-workers-retain-test-only.sh"
attested_child_test_entrypoint="$root/tests/run-context-provider-child-test-only.sh"
test_only=false
retain_test_only=false
attested_child_test_only=false
framework_root="$root"
if [ "$invoked_path" = "$test_entrypoint" ] || [ "$invoked_path" = "$retain_test_entrypoint" ] || [ "$invoked_path" = "$attested_child_test_entrypoint" ]; then
  [ -n "${BASH_SOURCE[1]:-}" ] || { echo 'ERROR: canonical test-only source entry point required' >&2; exit 2; }
  harness_source="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd -P)/$(basename "${BASH_SOURCE[1]}")"
  [ "$harness_source" = "$invoked_path" ] || { echo 'ERROR: canonical test-only source entry point required' >&2; exit 2; }
  # This branch is reachable only through the host-owned test harness at the
  # exact canonical repository path.  The production entry point never reads
  # a framework authority from CLI or environment.
  test_only=true
  framework_root="$root/tests/fixtures/context-runtime/ctx06a-framework"
  [ "$invoked_path" != "$retain_test_entrypoint" ] || retain_test_only=true
  [ "$invoked_path" != "$attested_child_test_entrypoint" ] || attested_child_test_only=true
fi
# shellcheck source=scripts/lib/provider-dispatch.sh
. "$root/scripts/lib/provider-dispatch.sh"
# shellcheck source=scripts/lib/provider-execution.sh
. "$root/scripts/lib/provider-execution.sh"
# shellcheck source=scripts/lib/worker-isolation.sh
. "$root/scripts/lib/worker-isolation.sh"
# shellcheck source=scripts/lib/context-worker-transport.sh
. "$root/scripts/lib/context-worker-transport.sh"
if [ "$attested_child_test_only" = true ]; then
  # shellcheck source=tests/fixtures/context-runtime/ctx07c-managed-child-adapter-test-only.sh
  . "$root/tests/fixtures/context-runtime/ctx07c-managed-child-adapter-test-only.sh"
fi

execution_id=""
project_root=""
plan_path=""
expected_profile=""
expected_provider=""
max_parallel=""
provider_children="disabled"
budget_mode=""
activation_args=()

usage() {
  cat <<'USAGE'
Usage: scripts/run-context-workers.sh <execution-id> --project-root <path> --plan <bound-plan.json> [options]

Options:
  --profile <id>                Require this profile identity.
  --provider <id>               Require this provider identity.
  --max-parallel <count>        Host concurrency cap (default: manifest directWorkers).
  --provider-children <mode>    disabled (default), prefer, or require.
  --budget-mode <mode>          CTX-08 provisional host budget: compact, standard (default), or deep.
  --static-signal <id>          Original authoritative CTX-04 input.
  --request-skill <id>          Original authoritative CTX-04 input.
  --deep-load-skill <id>        Original authoritative CTX-04 input.

By default each task is one fresh, read-only CTX-07B provider process. `prefer`
selects a CTX-07C managed child only when every required capability is proven,
otherwise it falls back before invocation. `require` fails closed on any gap.
The command performs no retry and emits one CTX-07A delegation-merge-v1 object.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 1; }

# Worker model and effort are never caller configuration. Reject the legacy
# per-run variables explicitly so an operator cannot believe they took effect.
for override_name in \
  MANA_BUDGET_POLICY_PATH MANA_PROVIDER_BUDGET_POLICY MANA_BUDGET_MODE MANA_CONTEXT_BUDGET_MODE MANA_BUDGET_MINIMUM_MODE \
  MANA_FRAMEWORK_ROOT MANA_CONTEXT_FRAMEWORK_ROOT MANA_WORKER_FRAMEWORK_ROOT MANA_WORKER_POLICY_PATH \
  MANA_MODEL MANA_WORKER_MODEL MANA_WORKER_REASONING_EFFORT \
  MANA_RUNTIME_EXECUTION_ID MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE \
  MANA_RETAIN_RAW_TRACE MANA_WORKER_RETAIN_RAW_TRACE \
  MANA_PROVIDER_CHILDREN MANA_WORKER_PROVIDER_CHILDREN \
  MANA_WORKER_TIMEOUT_SECONDS MANA_WORKER_KILL_GRACE_SECONDS \
  MANA_CODEX_MODEL MANA_CODEX_FULL_MODEL MANA_CODEX_REASONING_EFFORT \
  MANA_CLAUDE_MODEL MANA_CLAUDE_FULL_MODEL MANA_CLAUDE_REASONING_EFFORT \
  MANA_OPENCODE_MODEL MANA_OPENCODE_FULL_MODEL MANA_OPENCODE_REASONING_EFFORT
do
  [ -z "${!override_name+x}" ] || fail "caller worker authority override is forbidden: $override_name"
done

[ "$#" -gt 0 ] || { usage >&2; exit 2; }
execution_id="$1"
shift
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || fail '--project-root requires a path'; shift 2 ;;
    --plan) plan_path="${2:-}"; [ -n "$plan_path" ] || fail '--plan requires a path'; shift 2 ;;
    --profile) expected_profile="${2:-}"; [ -n "$expected_profile" ] || fail '--profile requires an id'; shift 2 ;;
    --provider) expected_provider="${2:-}"; [ -n "$expected_provider" ] || fail '--provider requires an id'; shift 2 ;;
    --max-parallel) max_parallel="${2:-}"; shift 2 ;;
    --provider-children)
      provider_children="${2:-}"
      case "$provider_children" in disabled|prefer|require) ;; *) fail '--provider-children must be disabled, prefer, or require' ;; esac
      shift 2 ;;
    --budget-mode)
      budget_mode="${2:-}"
      case "$budget_mode" in compact|standard|deep) ;; *) fail '--budget-mode must be compact, standard, or deep' ;; esac
      shift 2 ;;
    --static-signal|--request-skill|--deep-load-skill)
      [ -n "${2:-}" ] || fail "$1 requires an id"
      activation_args+=("$1" "$2")
      shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$execution_id" in execution-?*) ;; *) fail 'execution id must use the execution-* contract' ;; esac
case "$execution_id" in *[!A-Za-z0-9._-]*) fail 'execution id contains unsafe characters' ;; esac
[ -n "$project_root" ] || fail '--project-root is required'
[ -n "$plan_path" ] || fail '--plan is required'
project_root="$(cd "$project_root" 2>/dev/null && pwd -P)" || fail 'project root is unavailable'
case "$max_parallel" in ''|*[!0-9]*) [ -z "$max_parallel" ] || fail '--max-parallel must be a positive integer' ;; 0) fail '--max-parallel must be positive' ;; esac

phase_helper="$root/scripts/lib/context-phase-runtime.py"
worker_helper="$root/scripts/lib/context-worker-runtime.py"
delegation="$root/scripts/mana-context-delegation.sh"
test_delegation_args=()
if [ "$test_only" = true ]; then
  if [ "$retain_test_only" = true ]; then
    worker_helper="$root/tests/context-worker-runtime-retain-test-only.py"
  else
    worker_helper="$root/tests/context-worker-runtime-test-only.py"
  fi
  test_delegation_args=(--framework-root "$framework_root")
fi
export MANA_PROVIDER_SESSION_LAUNCHER="$root/scripts/lib/provider-process-session.py"
# CTX-07B-R1C intentionally does not take the CTX-06 phase-wide lock.  The
# host claim below is per deterministic task execution key, so independent
# tasks retain parallelism while equal tasks converge to one provider call.

temporary="$(mktemp -d "${TMPDIR:-/tmp}/mana-context-workers.XXXXXX")"
temporary="$(cd "$temporary" && pwd -P)"
cleanup() {
  # Capsule files are intentionally immutable while a worker runs; restore
  # host ownership permissions before removal on every exit path.
  find "$temporary" -type d -exec chmod u+rwx {} + 2>/dev/null || true
  find "$temporary" -type f -exec chmod u+rw {} + 2>/dev/null || true
  rm -rf "$temporary"
}
trap cleanup EXIT
mkdir "$temporary/workers"

common_args=("$execution_id" --project-root "$project_root" "${test_delegation_args[@]}" "${activation_args[@]}")
worker_common_args=("$execution_id" --project-root "$project_root" "${activation_args[@]}")
if ! "$worker_helper" prepare-plan "${worker_common_args[@]}" --plan "$plan_path" > "$temporary/prepared.json"; then
  fail 'delegation plan is not valid for the current authoritative phase'
fi
jq -cS '.plan' "$temporary/prepared.json" > "$temporary/plan.json"
profile="$(jq -er .profileId "$temporary/prepared.json")" || fail 'prepared worker plan omits profile identity'
provider="$(jq -er .provider "$temporary/prepared.json")" || fail 'prepared worker plan omits provider identity'
direct_worker_limit="$(jq -er .directWorkerLimit "$temporary/prepared.json")" || fail 'prepared worker plan omits its worker limit'
retain_raw_trace="$(jq -er '.debugPolicy.retainRawTrace | if type != "boolean" then error("invalid") elif . then "true" else "false" end' "$temporary/prepared.json")" || fail 'prepared worker plan omits its host debug policy'
[ -z "$expected_profile" ] || [ "$profile" = "$expected_profile" ] || fail 'worker plan profile differs from the requested profile'
[ -z "$expected_provider" ] || [ "$provider" = "$expected_provider" ] || fail 'worker plan provider differs from the requested provider'
[ -n "$max_parallel" ] || max_parallel="$direct_worker_limit"
[ "$max_parallel" -le "$direct_worker_limit" ] || fail '--max-parallel exceeds the authoritative direct worker limit'

provider_program="$(command -v "$provider" 2>/dev/null || true)"
[ -n "$provider_program" ] || fail "needs_model_escalation: provider binary is missing from PATH: $provider"
if [ "$test_only" = true ]; then
  [ "$execution_id" = execution-ctx07b ] || fail 'test-only worker harness accepts only its fixed fixture execution'
  [ "$provider" = claude ] || fail 'test-only worker harness accepts only the zero-token Claude stub'
  [ ! -L "$provider_program" ] || fail 'test-only worker provider must not be a symlink'
  expected_test_provider="$root/tests/fixtures/context-runtime/ctx07b-claude-stub.sh"
  [ "$attested_child_test_only" = false ] || expected_test_provider="$root/tests/fixtures/context-runtime/ctx07c-managed-child-attestation-fixture.sh"
  cmp -s "$provider_program" "$expected_test_provider" || \
    fail 'test-only worker harness refuses non-fixture provider binaries'
fi
if ! "$root/scripts/mana-provider-capabilities.sh" "$provider" --binary "$provider_program" > "$temporary/capabilities.probed.json"; then
  fail 'needs_model_escalation: provider capability probe failed'
fi
if [ "$attested_child_test_only" = true ]; then
  mana_ctx07c_test_capability_snapshot "$temporary/capabilities.probed.json" > "$temporary/capabilities.json" || \
    fail 'needs_model_escalation: test-only attested capability snapshot failed'
else
  mv "$temporary/capabilities.probed.json" "$temporary/capabilities.json"
fi
if ! "$phase_helper" validate-capabilities "$provider" "$temporary/capabilities.json" > "$temporary/capabilities.canonical.json"; then
  fail 'needs_model_escalation: provider capability report failed its CTX-02 contract'
fi
mv "$temporary/capabilities.canonical.json" "$temporary/capabilities.json"
budget_helper="$root/scripts/lib/context-budget.py"
[ "$test_only" = false ] || budget_helper="$root/tests/context-budget-test-only.py"
budget_request_args=()
[ -z "$budget_mode" ] || budget_request_args=(--requested-mode "$budget_mode")
"$budget_helper" decision "$execution_id" --project-root "$project_root" "${activation_args[@]}" "${budget_request_args[@]}" > "$temporary/budget-resolution.json" || fail 'needs_model_escalation: CTX-08 provider budget decision is invalid'
"$budget_helper" capability-plan "$temporary/budget-resolution.json" "$temporary/capabilities.json" > "$temporary/budget-plan.json" || fail 'needs_model_escalation: CTX-08 capability-gated budget plan is invalid'
while IFS= read -r budget_gap; do
  echo "WARNING: CTX-08 provider control is $budget_gap; it was not guessed or applied." >&2
done < <(jq -r '.controls | to_entries[] | select(.value.applied == false) | (.key + "=" + .value.status)' "$temporary/budget-plan.json")
automatic_compaction_threshold="$(jq -r '.controls.automaticCompactionThreshold | if .applied then (.requested | tostring) else "" end' "$temporary/budget-plan.json")"
effort_required="$(jq -r '[.workers[].contextPacket.modelSelection.reasoningEffort != null] | any' "$temporary/prepared.json")"
if mana_context_select_worker_transport "$provider" "$provider_children" "$effort_required" "$temporary/capabilities.json"; then
  worker_transport="$MANA_CONTEXT_WORKER_TRANSPORT"
else
  fail "needs_model_escalation: provider-managed child contract is not proven (${MANA_CONTEXT_CHILD_GAPS[*]})"
fi
if [ "$provider_children" = prefer ] && [ "${#MANA_CONTEXT_CHILD_GAPS[@]}" -ne 0 ]; then
  echo "WARNING: provider-managed child contract is not proven (${MANA_CONTEXT_CHILD_GAPS[*]}); using correctness-critical CTX-07B fresh host worker fallback." >&2
fi

native_schema=false
if [ "$worker_transport" = provider-managed-child ]; then
  # Native structured output is a mandatory CTX-07C capability, not a host-
  # validation substitute. The unchanged host validator still runs afterward.
  native_schema=true
else
  for capability in freshInvocation ephemeralSession explicitModelSelection hardSubagentDisable; do
    capability_status="$(jq -er --arg capability "$capability" '.capabilities[$capability].status' "$temporary/capabilities.json")"
    [ "$capability_status" = supported ] || fail "needs_model_escalation: provider capability $capability is $capability_status; CTX-07B will not weaken worker isolation"
  done
  if [ "$effort_required" = true ]; then
    effort_status="$(jq -er '.capabilities.explicitReasoningEffort.status' "$temporary/capabilities.json")"
    [ "$effort_status" = supported ] || fail "needs_model_escalation: provider capability explicitReasoningEffort is $effort_status but host worker policy requires it"
  fi
  schema_capability="$(jq -er '.capabilities.structuredOutputSchema.status' "$temporary/capabilities.json")"
  if [ "$schema_capability" = supported ]; then
    native_schema=true
  else
    echo "WARNING: provider structured output is $schema_capability; CTX-07B is using mandatory host validation." >&2
  fi
fi

failures=0
overall_status=1
active_pids=()
active_tasks=()

interrupt_workers() {
  local signal_name="$1" signal_status="$2" child_pid
  trap - INT TERM
  for child_pid in "${active_pids[@]}"; do
    kill -"$signal_name" "$child_pid" 2>/dev/null || true
  done
  for child_pid in "${active_pids[@]}"; do
    wait "$child_pid" 2>/dev/null || true
  done
  exit "$signal_status"
}
trap 'interrupt_workers INT 130' INT
trap 'interrupt_workers TERM 143' TERM

test_crash_at() {
  local point="$1"
  [ "$test_only" = true ] || return 0
  [ "${MANA_CTX07B_TEST_CRASH_POINT:-}" = "$point" ] || return 0
  [ -n "${CTX07B_STATE_DIR:-}" ] && [ -d "$CTX07B_STATE_DIR" ] || return 90
  printf '%s\n' "$point" > "$CTX07B_STATE_DIR/fault.$point"
  chmod 600 "$CTX07B_STATE_DIR/fault.$point"
  kill -KILL "$BASHPID"
}

run_worker() {
  local task_id="$1" worker_dir="$temporary/workers/$1" capsule="$temporary/capsules/$1" scratch="$temporary/scratch/$1" model effort provider_status capsule_schema claim action task_execution_key invocation_id timeout_seconds kill_grace_seconds terminal_status usage_summary raw_trace bind_command
  local -a usage_args=()
  mkdir "$worker_dir"
  mkdir -p "$temporary/capsules" "$temporary/scratch"
  mkdir "$scratch"
  mkdir "$scratch/provider-output"
  jq -cS --arg task_id "$task_id" '.workers[] | select(.taskId == $task_id) | .contextPacket' "$temporary/prepared.json" > "$worker_dir/packet.json"
  jq -cS '.delegationTask' "$worker_dir/packet.json" > "$worker_dir/task.json"
  # Claim/reuse is before capsule creation and provider work.  A loser never
  # creates an invocation; it waits only for the owning task, not globally.
  while :; do
    claim="$("$worker_helper" claim-task --project-root "$project_root" --prepared "$temporary/prepared.json" --task "$worker_dir/task.json")" || return 1
    action="$(jq -er .action <<<"$claim")"
    task_execution_key="$(jq -er .taskExecutionKey <<<"$claim")"
    case "$action" in
      reused)
        jq -cS '.resultObject' <<<"$claim" > "$worker_dir/result.json"
        return 0
        ;;
      claimed)
        invocation_id="$(jq -er .invocationId <<<"$claim")"
        timeout_seconds="$(jq -er .timeoutSeconds <<<"$claim")"
        kill_grace_seconds="$(jq -er .killGraceSeconds <<<"$claim")"
        "$worker_helper" worker-event --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --event worker.started
        break
        ;;
      wait) sleep 1 ;;
      *) return 1 ;;
    esac
  done
  model="$(jq -er '.modelSelection.modelId' "$worker_dir/packet.json")"
  effort="$(jq -er '.modelSelection.reasoningEffort' "$worker_dir/packet.json")"
  if ! "$worker_helper" materialize-capsule --packet "$worker_dir/packet.json" --project-root "$project_root" --capsule "$capsule" > "$worker_dir/capsule-manifest.json"; then
    "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status failed || true
    return 1
  fi
  if [ "$test_only" = true ] && [ "${MANA_CTX07B_TEST_FORCE_ISOLATION_UNAVAILABLE:-0}" != 1 ] && mana_worker_isolation_prepare_test_only "$capsule" "$scratch/provider-output" "$root/tests/fixtures/context-runtime/isolation-pass-through.sh"; then
    isolation_enabled=true
  elif [ "$test_only" = false ] && mana_worker_isolation_prepare "$capsule" "$scratch/provider-output" "$provider_program"; then
    isolation_enabled=true
  else
    "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status failed || true
    jq -cn --arg provider "$provider" --arg invocationId "$invocation_id" \
      '{category:"worker_isolation_unavailable",provider:$provider,invocationId:$invocationId}' \
      > "$worker_dir/public-error.json"
    return 1
  fi
  capsule_schema="$capsule/output-schema.json"
  prompt_command=render-prompt
  [ "$worker_transport" != provider-managed-child ] || prompt_command=render-child-prompt
  "$worker_helper" "$prompt_command" --packet "$worker_dir/packet.json" > "$worker_dir/prompt.txt" || {
    "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status failed || true
    return 1
  }
  if [ "$worker_transport" = provider-managed-child ]; then
    mana_provider_child_worker_args "$provider" "$capsule" "$model" "$effort" "$capsule_schema"
  else
    mana_provider_worker_args "$provider" "$capsule" "$model" "$effort" "$capsule_schema" "$native_schema" "$automatic_compaction_threshold"
  fi || {
    echo "ERROR: provider worker adapter rejected $provider" >&2
    "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status failed || true
    return 1
  }
  provider_args=("${MANA_PROVIDER_ARGS[@]}")
  : > "$worker_dir/provider-output.json"
  if [ "$provider" = opencode ] && [ -n "$MANA_PROVIDER_OPENCODE_CONFIG_CONTENT" ]; then
    unset MANA_CONTEXT_PHASE_LOCK_HELD MANA_EVIDENCE_WORKSPACE
    cd "$capsule" || return 1
    if OPENCODE_CONFIG_CONTENT="$MANA_PROVIDER_OPENCODE_CONFIG_CONTENT" \
      MANA_CTX07B_ISOLATION_ENABLED="$isolation_enabled" MANA_PROVIDER_EXEC_TEMP_DIR="$scratch/provider-output" \
      MANA_RUNTIME_EXECUTION_ID="execution-$invocation_id" \
      MANA_WORKER_TIMEOUT_SECONDS="$timeout_seconds" MANA_WORKER_KILL_GRACE_SECONDS="$kill_grace_seconds" mana_provider_execute_host_policy "$retain_raw_trace" "$provider" "$scratch" "$profile" "$(cat "$worker_dir/prompt.txt")" "$provider_program" "${provider_args[@]}" > "$worker_dir/provider-output.json"; then
      provider_status=0
    else
      provider_status=$?
    fi
  else
    unset MANA_CONTEXT_PHASE_LOCK_HELD MANA_EVIDENCE_WORKSPACE
    cd "$capsule" || return 1
    if MANA_CTX07B_ISOLATION_ENABLED="$isolation_enabled" MANA_PROVIDER_EXEC_TEMP_DIR="$scratch/provider-output" \
      MANA_RUNTIME_EXECUTION_ID="execution-$invocation_id" \
      MANA_WORKER_TIMEOUT_SECONDS="$timeout_seconds" MANA_WORKER_KILL_GRACE_SECONDS="$kill_grace_seconds" mana_provider_execute_host_policy "$retain_raw_trace" "$provider" "$scratch" "$profile" "$(cat "$worker_dir/prompt.txt")" "$provider_program" "${provider_args[@]}" > "$worker_dir/provider-output.json"; then
      provider_status=0
    else
      provider_status=$?
    fi
  fi
  usage_summary="$scratch/.mana/runtime/metrics/execution-$invocation_id/usage-summary-v1.json"
  if [ -f "$usage_summary" ]; then
    if "$budget_helper" advisory "$temporary/budget-resolution.json" "$usage_summary" "$project_root" "$invocation_id" "$worker_dir/prompt.txt" > "$worker_dir/budget-advisory.json"; then
      if jq -e '(.usageCheck.warnings|length)>0 or .promptCheck.warning' "$worker_dir/budget-advisory.json" >/dev/null; then
        echo 'WARNING: CTX-08 worker budget advisory; preserve all required specialist, evidence and human gates; use a fresh phase or human scope decision.' >&2
      fi
    else
      : > "$worker_dir/budget-advisory-unavailable"
      echo 'WARNING: CTX-08 worker usage advisory unavailable; usage was not treated as below budget.' >&2
    fi
  fi
  if [ -f "$usage_summary" ] && [ ! -L "$usage_summary" ]; then usage_args=(--usage-summary "$usage_summary"); fi
  raw_trace="$scratch/.mana/runtime/metrics/execution-$invocation_id/raw-provider-events.jsonl"
  if [ -f "$raw_trace" ] && [ ! -L "$raw_trace" ]; then usage_args+=(--raw-trace "$raw_trace"); fi
  [ "$provider_status" -eq 0 ] || {
    if [ "$provider_status" -eq 124 ]; then
      terminal_status=timed_out
    elif [ "$provider_status" -eq 130 ] || [ "$provider_status" -eq 143 ]; then
      terminal_status=interrupted
    else
      terminal_status=failed
    fi
    "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status "$terminal_status" "${usage_args[@]}" || true
    jq -cn --arg provider "$provider" --arg invocationId "$invocation_id" \
      --argjson exitStatus "$provider_status" \
      '{category:"transport_failure",provider:$provider,invocationId:$invocationId,exitStatus:$exitStatus}' \
      > "$worker_dir/public-error.json"
    return "$provider_status"
  }
  test_crash_at after-provider
  if [ "$worker_transport" = provider-managed-child ]; then
    "$worker_helper" publish-managed-child-receipt --project-root "$project_root" \
      --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" \
      --provider "$provider" --output "$worker_dir/provider-output.json" \
      --prepared "$temporary/prepared.json" --task "$worker_dir/task.json" \
      > "$worker_dir/receipt-publication.json" || {
      "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status failed "${usage_args[@]}" || true
      return 1
    }
    if [ "$(jq -er '.receiptObject.terminalStatus' "$worker_dir/receipt-publication.json")" != completed ]; then
      "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status failed "${usage_args[@]}" || true
      return 1
    fi
    test_crash_at after-managed-receipt
    "$worker_helper" normalize-output "$provider" --output "$worker_dir/provider-output.json" --task "$worker_dir/task.json" > "$worker_dir/draft.json" || {
      "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status failed "${usage_args[@]}" || true
      return 1
    }
    bind_command=bind-managed-child-result
  else
    "$worker_helper" normalize-output "$provider" --output "$worker_dir/provider-output.json" --task "$worker_dir/task.json" > "$worker_dir/draft.json" || {
      "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status failed "${usage_args[@]}" || true
      return 1
    }
    bind_command=bind-host-worker-result
  fi
  test_crash_at before-bind
  "$worker_helper" "$bind_command" --project-root "$project_root" \
    --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" \
    --draft "$worker_dir/draft.json" --prepared "$temporary/prepared.json" \
    --task "$worker_dir/task.json" > "$worker_dir/result.pending.json" || {
    "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status failed "${usage_args[@]}" || true
    return 1
  }
  test_crash_at after-bind
  "$worker_helper" publish-task-result --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --result "$worker_dir/result.pending.json" --prepared "$temporary/prepared.json" --task "$worker_dir/task.json" "${usage_args[@]}" > "$worker_dir/publication.json" || {
    "$worker_helper" finalize-task --project-root "$project_root" --task-execution-key "$task_execution_key" --invocation-id "$invocation_id" --status publication_failed "${usage_args[@]}" || true
    return 1
  }
  jq -cS '.resultObject' "$worker_dir/publication.json" > "$worker_dir/result.json"
}

wait_batch() {
  local index task_id worker_status
  for index in "${!active_pids[@]}"; do
    task_id="${active_tasks[$index]}"
    if wait "${active_pids[$index]}"; then
      worker_status=0
    else
      worker_status=$?
      failures=$((failures + 1))
      case "$worker_status" in 124|130|143) overall_status="$worker_status" ;; esac
      if [ -f "$temporary/workers/$task_id/public-error.json" ]; then
        jq -r 'if .category == "transport_failure" then
          "ERROR: transport_failure provider=" + .provider + " invocationId=" + .invocationId + " exitStatus=" + (.exitStatus|tostring)
          else "ERROR: needs_model_escalation category=" + .category + " provider=" + .provider + " invocationId=" + .invocationId end' \
          "$temporary/workers/$task_id/public-error.json" >&2
      else
        printf 'ERROR: worker_failure exitStatus=%s\n' "$worker_status" >&2
      fi
    fi
    if [ -f "$temporary/workers/$task_id/budget-advisory.json" ]; then
      if jq -e '(.usageCheck.warnings|length)>0 or .promptCheck.warning' "$temporary/workers/$task_id/budget-advisory.json" >/dev/null; then
        echo 'WARNING: CTX-08 worker budget advisory; preserve all required specialist, evidence and human gates; use a fresh phase or human scope decision.' >&2
      fi
    elif [ -f "$temporary/workers/$task_id/budget-advisory-unavailable" ]; then
      echo 'WARNING: CTX-08 worker usage advisory unavailable; usage was not treated as below budget.' >&2
    fi
  done
  active_pids=()
  active_tasks=()
}

while IFS= read -r task_id; do
  run_worker "$task_id" 2> "$temporary/workers/$task_id.stderr.log" &
  pid=$!
  active_pids+=("$pid")
  active_tasks+=("$task_id")
  if [ "${#active_pids[@]}" -ge "$max_parallel" ]; then
    wait_batch
  fi
done < <(jq -r '.workers[].taskId' "$temporary/prepared.json")
if [ "${#active_pids[@]}" -gt 0 ]; then
  wait_batch
fi

if [ "$worker_transport" = provider-managed-child ]; then
  "$worker_helper" merge-authoritative-results --project-root "$project_root" \
    --prepared "$temporary/prepared.json"
else
  merge_args=(merge-results "${common_args[@]}" --plan "$temporary/plan.json")
  while IFS= read -r result_path; do
    merge_args+=(--result "$result_path")
  done < <(find "$temporary/workers" -type f -name result.json -print | sort)
  "$delegation" "${merge_args[@]}"
fi
if [ "$failures" -ne 0 ]; then
  echo "ERROR: $failures fresh worker invocation(s) failed; incomplete merge emitted" >&2
  exit "$overall_status"
fi
