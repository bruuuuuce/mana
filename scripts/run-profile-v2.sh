#!/usr/bin/env bash
# CTX-06C fresh-phase provider runner.  The authoritative state machine and
# publication protocol remain in context-pipeline.py (CTX-06A/06B).
set -euo pipefail
umask 077

original_argv=("$@")

root="$(cd "$(dirname "$0")/.." && pwd)"
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/provider-execution.sh"
. "$root/scripts/lib/runtime-events.sh"

execution_id=""
project_root=""
framework_root="$root"
expected_profile=""
expected_provider=""
codex_model="${MANA_CODEX_MODEL:-gpt-5.4-mini}"
codex_full_model="${MANA_CODEX_FULL_MODEL:-gpt-5.6-sol}"
claude_model="${MANA_CLAUDE_MODEL:-haiku}"
claude_full_model="${MANA_CLAUDE_FULL_MODEL:-opus}"
opencode_model="${MANA_OPENCODE_MODEL:-opencode/gpt-5.1-codex}"
opencode_full_model="${MANA_OPENCODE_FULL_MODEL:-${MANA_OPENCODE_MODEL:-opencode/gpt-5.1-codex}}"
activation_args=()

usage() {
  cat <<'USAGE'
Usage: scripts/run-profile-v2.sh <execution-id> --project-root <path> [options]

Options:
  --framework-root <path>       Authoritative Mana framework root.
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

The run must already exist through mana-context-pipeline.sh initialize.
The command performs no automatic semantic or transport retry.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 1; }

valid_model() {
  [ -n "$1" ] && [ "${#1}" -le 240 ] && [ "$1" = "${1//$'\n'/}" ] && [ "$1" = "${1//$'\r'/}" ]
}

[ "$#" -gt 0 ] || { usage >&2; exit 2; }
execution_id="$1"
shift
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || fail '--project-root requires a path'; shift 2 ;;
    --framework-root) framework_root="${2:-}"; [ -n "$framework_root" ] || fail '--framework-root requires a path'; shift 2 ;;
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
if [ "${MANA_CONTEXT_PHASE_LOCK_HELD:-}" != "$execution_id" ]; then
  exec "$phase_helper" with-run-lock "$project_root" "$execution_id" \
    "$root/scripts/run-profile-v2.sh" "${original_argv[@]}"
fi
temporary="$(mktemp -d "${TMPDIR:-/tmp}/mana-context-phase.XXXXXX")"
temporary="$(cd "$temporary" && pwd -P)"
cleanup() { rm -rf "$temporary"; }
trap cleanup EXIT

pipeline_args=(--project-root "$project_root" --framework-root "$framework_root" "${activation_args[@]}")
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
  mana_provider_phase_args "$provider" "$project_root" "$model" "$schema_path" "$native_schema" || {
    finish_runtime failed
    fail "provider phase adapter rejected $provider"
  }
  provider_args=("${MANA_PROVIDER_ARGS[@]}")
  output_mode="$MANA_PROVIDER_PHASE_OUTPUT_MODE"
  if ! "$phase_helper" render-prompt "$temporary/packet.json" > "$temporary/prompt.txt"; then
    finish_runtime failed
    fail 'phase prompt rendering failed'
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
    "$phase_helper" archive-metrics "$project_root" "$execution_id" "$profile" "$provider" "$phase_id" "$ordinal" "$attempt" "$provider_version" "$metric_status" >/dev/null 2>&1 || echo 'WARNING: phase usage metrics could not be archived' >&2
    emit provider.completed provider "$provider" "$metric_status" "phase=$phase_id exitStatus=$provider_status" '' false
    emit "$event_type" phase "$phase_id" "$metric_status" "ordinal=$ordinal attempt=$attempt exitStatus=$provider_status" '' false
    finish_runtime failed
    exit "$provider_status"
  fi

  emit provider.completed provider "$provider" completed "phase=$phase_id exitStatus=0" '' false
  if ! "$phase_helper" normalize-output "$provider" "$temporary/provider-output.json" > "$temporary/checkpoint.json"; then
    "$phase_helper" archive-metrics "$project_root" "$execution_id" "$profile" "$provider" "$phase_id" "$ordinal" "$attempt" "$provider_version" failed >/dev/null 2>&1 || echo 'WARNING: phase usage metrics could not be archived' >&2
    emit phase.failed phase "$phase_id" failed "ordinal=$ordinal attempt=$attempt reason=invalid-provider-output" '' false
    finish_runtime failed
    fail "provider output for phase $phase_id is not a valid checkpoint"
  fi
  if ! transition="$($pipeline accept-checkpoint "$execution_id" "${pipeline_args[@]}" --checkpoint "$temporary/checkpoint.json")"; then
    "$phase_helper" archive-metrics "$project_root" "$execution_id" "$profile" "$provider" "$phase_id" "$ordinal" "$attempt" "$provider_version" failed >/dev/null 2>&1 || echo 'WARNING: phase usage metrics could not be archived' >&2
    emit phase.failed phase "$phase_id" failed "ordinal=$ordinal attempt=$attempt reason=checkpoint-rejected" '' false
    finish_runtime failed
    fail "checkpoint for phase $phase_id was rejected by the authoritative state machine"
  fi
  printf '%s\n' "$transition" > "$temporary/transition.json"
  transition_status="$(jq -er .status "$temporary/transition.json")"
  last_revision="$(jq -er .revision "$temporary/transition.json")"
  last_transition_id="$(jq -er '.transitionId // ""' "$temporary/transition.json")"
  checkpoint_refs="$(jq -r '.evidenceRefs | join(" ")' "$temporary/checkpoint.json")"
  "$phase_helper" archive-metrics "$project_root" "$execution_id" "$profile" "$provider" "$phase_id" "$ordinal" "$attempt" "$provider_version" complete >/dev/null 2>&1 || echo 'WARNING: phase usage metrics could not be archived' >&2
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
