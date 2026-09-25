#!/usr/bin/env bash
# CTX-06C fresh-phase provider runner.  The authoritative state machine and
# publication protocol remain in context-pipeline.py (CTX-06A/06B).
set -euo pipefail
umask 077

original_argv=("$@")

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
phase_entrypoint="$root/scripts/run-profile-v2.sh"
invoked_path="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"
framework_root="$root"
budget_helper="$root/scripts/lib/context-budget.py"
if [ "$invoked_path" = "$root/tests/run-profile-v2-test-only.sh" ]; then
  [ -n "${BASH_SOURCE[1]:-}" ] || { echo 'ERROR: canonical test-only source entry point required' >&2; exit 2; }
  harness_source="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd -P)/$(basename "${BASH_SOURCE[1]}")"
  [ "$harness_source" = "$invoked_path" ] || { echo 'ERROR: canonical test-only source entry point required' >&2; exit 2; }
  framework_root="$root/tests/fixtures/context-runtime/ctx06a-framework"
  budget_helper="$root/tests/context-budget-test-only.py"
  phase_entrypoint="$root/tests/run-profile-v2-test-only.sh"
fi
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/provider-execution.sh"
. "$root/scripts/lib/runtime-events.sh"

execution_id=""
project_root=""
expected_profile=""
expected_provider=""
codex_model="${MANA_CODEX_MODEL:-gpt-6-luna}"
codex_full_model="${MANA_CODEX_FULL_MODEL:-gpt-6-sol}"
claude_model="${MANA_CLAUDE_MODEL:-claude-haiku-4-5}"
claude_full_model="${MANA_CLAUDE_FULL_MODEL:-claude-opus-5-5}"
opencode_model="${MANA_OPENCODE_MODEL:-opencode/gpt-6-luna}"
opencode_full_model="${MANA_OPENCODE_FULL_MODEL:-${MANA_OPENCODE_MODEL:-opencode/gpt-6-sol}}"
activation_args=()
budget_mode=""

usage() {
  cat <<'USAGE'
Usage: scripts/run-profile-v2.sh <execution-id> --project-root <path> [options]

Options:
  --profile <id>                Require this profile identity.
  --provider <id>               Require this provider identity.
  --codex-model <model>         Economy-tier Codex model.
  --codex-full-model <model>    Full-tier Codex model.
  --claude-model <model>        Economy-tier Claude model.
  --claude-full-model <model>   Full-tier Claude model.
  --opencode-model <model>      Economy-tier OpenCode model.
  --opencode-full-model <model> Full-tier OpenCode model.
  --static-signal <id>          Original authoritative CTX-04 input.
  --request-skill <id>          Original authoritative CTX-04 input.
  --deep-load-skill <id>        Original authoritative CTX-04 input.
  --budget-mode <mode>          Human request for compact, standard, or deep; host minimum is preserved.

The run must already exist through mana-context-pipeline.sh initialize.
The command performs no automatic semantic or transport retry.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 1; }

valid_model() {
  [ -n "$1" ] && [ "${#1}" -le 240 ] && [ "$1" = "${1//$'\n'/}" ] && [ "$1" = "${1//$'\r'/}" ]
}

for override_name in MANA_FRAMEWORK_ROOT MANA_CONTEXT_FRAMEWORK_ROOT MANA_WORKER_FRAMEWORK_ROOT MANA_BUDGET_POLICY_PATH MANA_PROVIDER_BUDGET_POLICY MANA_BUDGET_MODE MANA_CONTEXT_BUDGET_MODE MANA_BUDGET_MINIMUM_MODE; do
  [ -z "${!override_name+x}" ] || fail "caller budget authority override is forbidden: $override_name"
done

[ "$#" -gt 0 ] || { usage >&2; exit 2; }
execution_id="$1"
shift
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || fail '--project-root requires a path'; shift 2 ;;
    --profile) expected_profile="${2:-}"; [ -n "$expected_profile" ] || fail '--profile requires an id'; shift 2 ;;
    --provider) expected_provider="${2:-}"; [ -n "$expected_provider" ] || fail '--provider requires an id'; shift 2 ;;
    --codex-model) codex_model="${2:-}"; shift 2 ;;
    --codex-full-model) codex_full_model="${2:-}"; shift 2 ;;
    --claude-model) claude_model="${2:-}"; shift 2 ;;
    --claude-full-model) claude_full_model="${2:-}"; shift 2 ;;
    --opencode-model) opencode_model="${2:-}"; shift 2 ;;
    --opencode-full-model) opencode_full_model="${2:-}"; shift 2 ;;
    --static-signal|--request-skill|--deep-load-skill)
      [ -n "${2:-}" ] || fail "$1 requires an id"
      activation_args+=("$1" "$2")
      shift 2 ;;
    --budget-mode)
      budget_mode="${2:-}"
      case "$budget_mode" in compact|standard|deep) ;; *) fail '--budget-mode must be compact, standard, or deep' ;; esac
      shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$execution_id" in execution-?*) ;; *) fail 'execution id must use the execution-* contract' ;; esac
case "$execution_id" in *[!A-Za-z0-9._-]*) fail 'execution id contains unsafe characters' ;; esac
[ -n "$project_root" ] || fail '--project-root is required'
project_root="$(cd "$project_root" 2>/dev/null && pwd -P)" || fail 'project root is unavailable'
framework_root="$(cd "$framework_root" 2>/dev/null && pwd -P)" || fail 'framework root is unavailable'
for model in "$codex_model" "$codex_full_model" "$claude_model" "$claude_full_model" "$opencode_model" "$opencode_full_model"; do
  valid_model "$model" || fail 'provider model identifiers must be non-empty bounded single-line values'
done

pipeline="$root/scripts/mana-context-pipeline.sh"
phase_helper="$root/scripts/lib/context-phase-runtime.py"
# CTX-10-R2.3 requires the authoritative CTX-06 lookup to complete before the
# provider-phase mutex is created or acquired.  This lookup is read-only and
# emits one normalized public error for missing/foreign/invalid run authority.
execution_identity_args=(
  execution-identity --project-root "$project_root" --execution-id "$execution_id"
  --framework-root "$framework_root"
)
[ -z "$expected_profile" ] || execution_identity_args+=(--profile "$expected_profile")
if ! python3 "$root/scripts/context-runtime-rollout.py" \
    "${execution_identity_args[@]}" >/dev/null; then
  exit 2
fi
if [ -e "$project_root/.mana/context-runtime/runtime-selection-v1.json" ] ||
   [ -L "$project_root/.mana/context-runtime/runtime-selection-v1.json" ]; then
  rollout_identity="$(python3 "$root/scripts/context-runtime-rollout.py" "${execution_identity_args[@]}")" || exit 2
  identity_version="$(printf '%s' "$rollout_identity" | python3 -c 'import json,sys; print(json.load(sys.stdin)["executionVersion"])')" || exit 2
  identity_workspace="$(printf '%s' "$rollout_identity" | python3 -c 'import json,sys; print(json.load(sys.stdin)["workspaceId"])')" || exit 2
  profile_for_rollout="$(printf '%s' "$rollout_identity" | python3 -c 'import json,sys; print(json.load(sys.stdin)["profileId"])')" || exit 2
  selection="$(python3 "$root/scripts/context-runtime-rollout.py" resolve \
    --project-root "$project_root" --profile "$profile_for_rollout" \
    --execution-id "$execution_id" --execution-version "$identity_version" \
    --workspace-id "$identity_workspace")" || exit 2
  selected_mode="$(printf '%s' "$selection" | python3 -c 'import json,sys; print(json.load(sys.stdin)["mode"])')" || exit 2
  [ "$selected_mode" = v2 ] || { echo 'ERROR: CTX10_DECISION_AUTHORITY_REJECTED: v2 is not the committed runtime mode' >&2; exit 2; }
fi
if [ "${MANA_CONTEXT_PHASE_LOCK_HELD:-}" != "$execution_id" ]; then
  exec "$phase_helper" with-run-lock "$project_root" "$execution_id" \
    "$phase_entrypoint" "${original_argv[@]}"
fi
temporary="$(mktemp -d "${TMPDIR:-/tmp}/mana-context-phase.XXXXXX")"
temporary="$(cd "$temporary" && pwd -P)"
cleanup() { rm -rf "$temporary"; }
trap cleanup EXIT

pipeline_args=(--project-root "$project_root" --framework-root "$framework_root" "${activation_args[@]+"${activation_args[@]}"}")
if ! "$pipeline" reconcile "$execution_id" "${pipeline_args[@]}" > "$temporary/reconcile.json"; then
  fail 'authoritative transition reconciliation failed before provider execution'
fi
if ! "$pipeline" prepare-phase "$execution_id" "${pipeline_args[@]}" > "$temporary/packet.json"; then
  fail 'authoritative phase preparation failed'
fi

profile="$(jq -er .profileId "$temporary/packet.json")" || fail 'prepared phase packet omits profile identity'
provider="$(jq -er .provider "$temporary/packet.json")" || fail 'prepared phase packet omits provider identity'
run_status="$(jq -er .runStatus "$temporary/packet.json")" || fail 'prepared phase packet omits run status'
[ -z "$expected_profile" ] || [ "$profile" = "$expected_profile" ] || fail 'initialized run profile differs from the requested profile'
[ -z "$expected_provider" ] || [ "$provider" = "$expected_provider" ] || fail 'initialized run provider differs from the requested provider'

runtime_ready=true
if ! runtime_init "$project_root" "$profile" "$execution_id"; then
  runtime_ready=false
  echo "WARNING: $MANA_RUNTIME_WARNING" >&2
fi
emit() {
  [ "$runtime_ready" = true ] || return 0
  runtime_emit "$@" || echo "WARNING: $MANA_RUNTIME_WARNING" >&2
}
finish_runtime() {
  [ "$runtime_ready" = true ] || return 0
  runtime_finish "$1"
  [ -z "$MANA_RUNTIME_WARNING" ] || echo "WARNING: $MANA_RUNTIME_WARNING" >&2
}
result() {
  local status="$1" revision="$2" transition_id="$3" invocations="$4"
  jq -cn --arg schemaVersion 'mana.context-runtime.phase-run-result/v1' \
    --arg executionId "$execution_id" --arg profileId "$profile" \
    --arg provider "$provider" --arg status "$status" \
    --argjson revision "$revision" --arg transitionId "$transition_id" \
    --argjson providerInvocations "$invocations" \
    '{schemaVersion:$schemaVersion,executionId:$executionId,profileId:$profileId,
      provider:$provider,status:$status,revision:$revision,
      transitionId:(if $transitionId=="" then null else $transitionId end),
      providerInvocations:$providerInvocations}'
}

case "$run_status" in
  completed)
    result completed "$(jq -r .revision "$temporary/packet.json")" '' 0
    finish_runtime completed
    exit 0 ;;
  blocked)
    emit phase.blocked phase "$profile" blocked 'reason=host-approval-required' '' false
    finish_runtime failed
    result blocked "$(jq -r .revision "$temporary/packet.json")" '' 0
    exit 3 ;;
  interrupted) fail 'interrupted run requires host reconciliation before execution' ;;
  active) ;;
  *) fail 'prepared run has an unknown status' ;;
esac

provider_program="$(command -v "$provider" 2>/dev/null || true)"
[ -n "$provider_program" ] || {
  emit guard.triggered provider "$provider" blocked 'reason=provider-binary-missing' '' true
  finish_runtime failed
  fail "provider binary is missing from PATH: $provider"
}
if ! "$root/scripts/mana-provider-capabilities.sh" "$provider" --binary "$provider_program" > "$temporary/capabilities.json"; then
  emit guard.triggered provider "$provider" blocked 'reason=capability-probe-failed' '' true
  finish_runtime failed
  fail 'provider capability probe failed'
fi
if ! "$phase_helper" validate-capabilities "$provider" "$temporary/capabilities.json" > "$temporary/capabilities.canonical.json"; then
  emit guard.triggered provider "$provider" blocked 'reason=capability-report-invalid' '' true
  finish_runtime failed
  fail 'provider capability report failed its CTX-02 contract'
fi
mv "$temporary/capabilities.canonical.json" "$temporary/capabilities.json"
provider_version="$(jq -er .providerVersion "$temporary/capabilities.json")"
for capability in freshInvocation ephemeralSession explicitModelSelection hardSubagentDisable; do
  capability_status="$(jq -er --arg capability "$capability" '.capabilities[$capability].status' "$temporary/capabilities.json")"
  if [ "$capability_status" != supported ]; then
    emit guard.triggered provider "$provider" blocked "capability=$capability status=$capability_status" '' true
    finish_runtime failed
    fail "provider capability $capability is $capability_status; CTX-06C will not silently weaken isolation"
  fi
done
schema_capability="$(jq -er '.capabilities.structuredOutputSchema.status' "$temporary/capabilities.json")"
native_schema=false
if [ "$schema_capability" = supported ]; then
  native_schema=true
else
  echo "WARNING: provider structured output is $schema_capability; CTX-06C is using mandatory host validation as the explicit safe fallback." >&2
  emit provider.capability-fallback provider "$provider" selected "capability=structuredOutputSchema status=$schema_capability fallback=host-validation" '' false
fi

# CTX-08 is a host-owned advisory layer. It is resolved from the authoritative
# framework policy and CTX-02 report, never from profile prose or provider
# output. Fresh CTX-06 phase boundaries remain the correctness mechanism.
budget_request_args=()
[ -z "$budget_mode" ] || budget_request_args=(--requested-mode "$budget_mode")
"$budget_helper" decision "$execution_id" --project-root "$project_root" "${activation_args[@]+"${activation_args[@]}"}" "${budget_request_args[@]+"${budget_request_args[@]}"}" > "$temporary/budget-resolution.json" || fail 'CTX-08 provider budget decision is invalid'
"$budget_helper" capability-plan "$temporary/budget-resolution.json" "$temporary/capabilities.json" > "$temporary/budget-plan.json" || fail 'CTX-08 capability-gated budget plan is invalid'
while IFS= read -r budget_gap; do
  echo "WARNING: CTX-08 provider control is $budget_gap; it was not guessed or applied." >&2
done < <(jq -r '.controls | to_entries[] | select(.value.applied == false) | (.key + "=" + .value.status)' "$temporary/budget-plan.json")
automatic_compaction_threshold="$(jq -r '.controls.automaticCompactionThreshold | if .applied then (.requested | tostring) else "" end' "$temporary/budget-plan.json")"
archive_phase_metrics() {
  local phase_id="$1" ordinal="$2" attempt="$3" metric_status="$4" budget_check invocation_key
  "$phase_helper" archive-metrics "$project_root" "$execution_id" "$profile" "$provider" "$phase_id" "$ordinal" "$attempt" "$provider_version" "$metric_status" > "$temporary/metric-archive.json" 2>/dev/null || {
    echo 'WARNING: phase usage metrics could not be archived' >&2
    return 0
  }
  budget_check="$temporary/budget-usage-check.json"
  invocation_key="$(jq -r '.ordinal|tostring' "$temporary/metric-archive.json")-$phase_id-$attempt-$(jq -r .invocation "$temporary/metric-archive.json")"
  if "$budget_helper" advisory "$temporary/budget-resolution.json" "$project_root/$(jq -r .summaryRef "$temporary/metric-archive.json")" "$project_root" "$invocation_key" "$temporary/prompt.txt" > "$budget_check"; then
    if [ "$(jq -r '.usageCheck.warnings | length' "$budget_check")" -gt 0 ]; then
      echo 'WARNING: CTX-08 provider budget advisory (threshold or unavailable/invalid usage); preserve all required specialist, evidence, and human gates, then use the next fresh phase or request human scope.' >&2
    fi
  else
    echo 'WARNING: CTX-08 usage advisory could not be evaluated' >&2
  fi
}

provider_invocations=0
last_transition_id=""
last_revision="$(jq -r .revision "$temporary/packet.json")"
while :; do
  run_status="$(jq -er .runStatus "$temporary/packet.json")"
  if [ "$run_status" != active ]; then
    case "$run_status" in
      completed) finish_runtime completed; result completed "$last_revision" "$last_transition_id" "$provider_invocations"; exit 0 ;;
      blocked) finish_runtime failed; result blocked "$last_revision" "$last_transition_id" "$provider_invocations"; exit 3 ;;
      *) finish_runtime failed; fail "run became non-executable: $run_status" ;;
    esac
  fi

  phase_id="$(jq -er .phase.id "$temporary/packet.json")"
  ordinal="$(jq -er .phase.ordinal "$temporary/packet.json")"
  attempt="$(jq -er .currentAttempt "$temporary/packet.json")"
  model_tier="$(jq -er .phase.policy.modelTier "$temporary/packet.json")"
  output_schema="$(jq -er .phase.policy.outputSchema "$temporary/packet.json")"
  subagents="$(jq -er .phase.policy.subagents "$temporary/packet.json")"
  [ "$output_schema" = phase-checkpoint-v1 ] || {
    emit guard.triggered phase "$phase_id" blocked "reason=unsupported-output-schema schema=$output_schema" '' true
    finish_runtime failed
    fail "phase $phase_id declares $output_schema; CTX-06C requires phase-checkpoint-v1"
  }
  case "$model_tier" in
    economy)
      case "$provider" in codex) model="$codex_model" ;; claude) model="$claude_model" ;; opencode) model="$opencode_model" ;; esac ;;
    full)
      case "$provider" in codex) model="$codex_full_model" ;; claude) model="$claude_full_model" ;; opencode) model="$opencode_full_model" ;; esac ;;
    host)
      emit guard.triggered phase "$phase_id" blocked 'reason=host-phase-has-no-provider-adapter' '' true
      finish_runtime failed
      fail "phase $phase_id is host-owned and has no CTX-06C provider operation" ;;
    *) finish_runtime failed; fail "phase $phase_id has an invalid model tier" ;;
  esac

  schema_path="$root/contracts/context-runtime/phase-checkpoint-v1.schema.json"
  mana_provider_phase_args "$provider" "$project_root" "$model" "$schema_path" "$native_schema" "$automatic_compaction_threshold" || {
    finish_runtime failed
    fail "provider phase adapter rejected $provider"
  }
  provider_args=("${MANA_PROVIDER_ARGS[@]}")
  output_mode="$MANA_PROVIDER_PHASE_OUTPUT_MODE"
  if ! "$phase_helper" render-prompt "$temporary/packet.json" > "$temporary/prompt.txt"; then
    finish_runtime failed
    fail 'phase prompt rendering failed'
  fi
  if "$budget_helper" prompt-check "$temporary/budget-resolution.json" "$temporary/prompt.txt" > "$temporary/budget-prompt-check.json" && \
    [ "$(jq -r .warning "$temporary/budget-prompt-check.json")" = true ]; then
    echo 'WARNING: CTX-08 active-context estimate reached its provisional advisory threshold; preserve required checks and use a fresh phase if narrowing is needed.' >&2
  fi
  : > "$temporary/provider-output.json"
  : > "$temporary/checkpoint.json"
  emit phase.started phase "$phase_id" started "ordinal=$ordinal attempt=$attempt modelTier=$model_tier subagentsDeclared=$subagents subagentsEffective=forbidden" '' false
  emit provider.invoked provider "$provider" started "phase=$phase_id modelTier=$model_tier outputMode=$output_mode" '' false
  provider_invocations=$((provider_invocations + 1))
  if [ "$provider" = opencode ] && [ -n "$MANA_PROVIDER_OPENCODE_CONFIG_CONTENT" ]; then
    if (unset MANA_CONTEXT_PHASE_LOCK_HELD; cd "$project_root" || exit 1; \
      OPENCODE_CONFIG_CONTENT="$MANA_PROVIDER_OPENCODE_CONFIG_CONTENT" MANA_RUNTIME_EXECUTION_ID="$execution_id" \
      mana_provider_execute "$provider" "$project_root" "$profile" "$(cat "$temporary/prompt.txt")" "$provider_program" "${provider_args[@]}") > "$temporary/provider-output.json"; then
      provider_status=0
    else
      provider_status=$?
    fi
  else
    if (unset MANA_CONTEXT_PHASE_LOCK_HELD; cd "$project_root" || exit 1; \
      MANA_RUNTIME_EXECUTION_ID="$execution_id" \
      mana_provider_execute "$provider" "$project_root" "$profile" "$(cat "$temporary/prompt.txt")" "$provider_program" "${provider_args[@]}") > "$temporary/provider-output.json"; then
      provider_status=0
    else
      provider_status=$?
    fi
  fi

  if [ "$provider_status" -ne 0 ]; then
    case "$provider_status" in 129|130|143) metric_status=interrupted; event_type=phase.interrupted ;; *) metric_status=failed; event_type=phase.failed ;; esac
    archive_phase_metrics "$phase_id" "$ordinal" "$attempt" "$metric_status"
    emit provider.completed provider "$provider" "$metric_status" "phase=$phase_id exitStatus=$provider_status" '' false
    emit "$event_type" phase "$phase_id" "$metric_status" "ordinal=$ordinal attempt=$attempt exitStatus=$provider_status" '' false
    finish_runtime failed
    exit "$provider_status"
  fi

  emit provider.completed provider "$provider" completed "phase=$phase_id exitStatus=0" '' false
  if ! "$phase_helper" normalize-output "$provider" "$temporary/provider-output.json" > "$temporary/checkpoint.json"; then
    archive_phase_metrics "$phase_id" "$ordinal" "$attempt" failed
    emit phase.failed phase "$phase_id" failed "ordinal=$ordinal attempt=$attempt reason=invalid-provider-output" '' false
    finish_runtime failed
    fail "provider output for phase $phase_id is not a valid checkpoint"
  fi
  if ! transition="$($pipeline accept-checkpoint "$execution_id" "${pipeline_args[@]}" --checkpoint "$temporary/checkpoint.json")"; then
    archive_phase_metrics "$phase_id" "$ordinal" "$attempt" failed
    emit phase.failed phase "$phase_id" failed "ordinal=$ordinal attempt=$attempt reason=checkpoint-rejected" '' false
    finish_runtime failed
    fail "checkpoint for phase $phase_id was rejected by the authoritative state machine"
  fi
  printf '%s\n' "$transition" > "$temporary/transition.json"
  transition_status="$(jq -er .status "$temporary/transition.json")"
  last_revision="$(jq -er .revision "$temporary/transition.json")"
  last_transition_id="$(jq -er '.transitionId // ""' "$temporary/transition.json")"
  checkpoint_refs="$(jq -r '.evidenceRefs | join(" ")' "$temporary/checkpoint.json")"
  archive_phase_metrics "$phase_id" "$ordinal" "$attempt" complete
  emit phase.checkpoint.accepted checkpoint "$(jq -r .checkpointId "$temporary/checkpoint.json")" accepted "phase=$phase_id revision=$last_revision runStatus=$transition_status" "$checkpoint_refs" false
  emit phase.completed phase "$phase_id" completed "ordinal=$ordinal attempt=$attempt runStatus=$transition_status" "$checkpoint_refs" false

  case "$transition_status" in
    completed)
      finish_runtime completed
      result completed "$last_revision" "$last_transition_id" "$provider_invocations"
      exit 0 ;;
    blocked)
      emit phase.blocked phase "$phase_id" blocked 'reason=host-authority-required' "$checkpoint_refs" false
      finish_runtime failed
      result blocked "$last_revision" "$last_transition_id" "$provider_invocations"
      exit 3 ;;
    active)
      if ! "$pipeline" prepare-phase "$execution_id" "${pipeline_args[@]}" > "$temporary/packet.next.json"; then
        finish_runtime failed
        fail 'next authoritative phase preparation failed'
      fi
      mv "$temporary/packet.next.json" "$temporary/packet.json"
      ;;
    *) finish_runtime failed; fail "state machine returned an unknown run status: $transition_status" ;;
  esac
done
