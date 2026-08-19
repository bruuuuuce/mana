#!/usr/bin/env bash
# TG06 opt-in Story Start v2 trajectory integration at host-visible boundaries.

MANA_TRAJECTORY_GUARD_HEADER=""

mana_trajectory_guard_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

mana_trajectory_guard_atomic_copy() {
  local source="$1" target="$2" stage
  [ -f "$source" ] && [ ! -L "$target" ] || return 2
  mkdir -p "$(dirname "$target")" || return 2
  stage="$(mktemp "$(dirname "$target")/.${target##*/}.tmp.XXXXXX")" || return 2
  if ! cp "$source" "$stage" || ! mv "$stage" "$target"; then
    rm -f "$stage"
    return 2
  fi
}

mana_trajectory_guard_mode() {
  case "${MANA_ANALYSIS_TRAJECTORY_MODE:-off}" in
    off|OFF) printf '%s' OFF ;;
    shadow|SHADOW|observe|OBSERVE) printf '%s' SHADOW ;;
    enforce|ENFORCE) printf '%s' ENFORCE ;;
    *)
      echo 'ERROR: MANA_ANALYSIS_TRAJECTORY_MODE must be off, shadow/observe, or enforce' >&2
      return 2
      ;;
  esac
}

mana_trajectory_guard_initialize() {
  local package="$1" workspace="$2" root mode
  root="$(mana_trajectory_guard_root)"
  mode="$(mana_trajectory_guard_mode)" || return 2
  [ "$mode" != OFF ] || return 0
  [ "$MANA_TRAJECTORY_TELEMETRY_ENABLED" = true ] || {
    echo 'ERROR: trajectory shadow/enforce mode requires initialized host telemetry' >&2
    return 2
  }
  python3 "$root/scripts/lib/analysis-trajectory-integration.py" \
    initialize "$package" "$workspace" "$mode" || return 2
  MANA_ANALYSIS_TRAJECTORY_MISSION_PATH="$workspace/evidence/analysis-trajectory-mission-v1.json"
  MANA_ANALYSIS_TRAJECTORY_EVIDENCE_PACKAGE="$workspace/evidence/analysis-trajectory-evidence-package-v1.json"
  export MANA_ANALYSIS_TRAJECTORY_MISSION_PATH MANA_ANALYSIS_TRAJECTORY_EVIDENCE_PACKAGE
}

# Execute one schema-bound checkpoint call. Raw output and stderr remain in
# the caller-owned temporary directory.
mana_trajectory_guard_provider_call() {
  local provider="$1" model="$2" effort="$3" prompt="$4" output="$5" scratch="$6"
  local root schema program status_file timeout code _signal timed_out descendants
  root="$(mana_trajectory_guard_root)"
  schema="$root/contracts/analysis-trajectory/trajectory-checkpoint-response-v1.schema.json"
  timeout="${MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_TIMEOUT_SECONDS:-120}"
  if ! [[ "$timeout" =~ ^[1-9][0-9]*$ ]] || [ "$timeout" -gt 300 ]; then
    echo 'ERROR: trajectory checkpoint timeout must be 1..300 seconds' >&2
    return 2
  fi
  mkdir -p "$scratch/empty"
  MANA_PROVIDER_PROGRAM="$provider"
  mana_provider_synthesis_args "$provider" "$scratch/empty" "$model" \
    host-disposable-non-git "$schema" "$effort" || return 2
  program="${MANA_PROVIDER_PROGRAM:-$provider}"
  command -v "$program" >/dev/null 2>&1 || return 1
  status_file="$scratch/status.tsv"
  perl "$root/scripts/lib/verification-exec.pl" --timeout "$timeout" \
    --output-cap 131072 --stderr-cap 4096 --stdout "$output" \
    --stderr "$scratch/provider.stderr" --status "$status_file" -- \
    "$program" "${MANA_PROVIDER_ARGS[@]}" "$(< "$prompt")" || true
  if [ ! -f "$status_file" ] || \
    ! IFS=$'\t' read -r code _signal timed_out descendants _ < "$status_file" || \
    [ "$code" -ne 0 ] || [ "$timed_out" != 0 ] || [ "$descendants" != 0 ]; then
    return 1
  fi
}

mana_trajectory_guard_checkpoint() {
  local provider="$1" base_model="$2" workspace="$3" root request config model effort scratch
  local prompt primary_raw primary_validation repair_prompt repair_raw repair_validation accepted run status
  root="$(mana_trajectory_guard_root)"
  request="$workspace/validation/analysis-trajectory-checkpoint-request-v1.json"
  config="$workspace/validation/analysis-trajectory-checkpoint-governor-config-v1.json"
  run="$workspace/validation/analysis-trajectory-checkpoint-run-v1.json"
  model="$(mana_story_start_scope_v2_stage_model trajectory-checkpoint "$base_model")" || return 2
  effort="$(mana_story_start_scope_v2_stage_effort trajectory-checkpoint)" || return 2
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-trajectory-checkpoint-tg06.XXXXXX")" || return 2
  prompt="$scratch/primary.prompt"
  primary_raw="$scratch/primary.json"
  primary_validation="$scratch/primary-validation.json"
  repair_prompt="$scratch/repair.prompt"
  repair_raw="$scratch/repair.json"
  repair_validation="$scratch/repair-validation.json"
  accepted="-"

  if ! python3 "$root/scripts/lib/analysis-trajectory-checkpoint.py" render-prompt "$request" "$prompt"; then
    rm -rf "$scratch"
    return 2
  fi
  mana_trajectory_telemetry_emit provider_iteration_started provider_invocation trajectory-checkpoint \
    "$provider" "$model" "${effort:-none}" trajectory/checkpoint started || true
  if ! mana_trajectory_guard_provider_call "$provider" "$model" "$effort" "$prompt" "$primary_raw" "$scratch/primary"; then
    python3 "$root/scripts/lib/analysis-trajectory-checkpoint.py" provider-failed \
      "$request" "$primary_validation" || true
    mana_trajectory_telemetry_emit provider_iteration_completed provider_invocation trajectory-checkpoint \
      "$provider" "$model" "${effort:-none}" trajectory/checkpoint failed --reason-codes provider-unavailable || true
  else
    python3 "$root/scripts/lib/analysis-trajectory-checkpoint.py" assess-response \
      "$request" "$primary_raw" "$primary_validation" --calls-used 1 >/dev/null 2>&1 || true
    status="$(jq -r '.status // "PROVIDER_FAILED"' "$primary_validation" 2>/dev/null)"
    mana_trajectory_telemetry_emit provider_iteration_completed provider_invocation trajectory-checkpoint \
      "$provider" "$model" "${effort:-none}" trajectory/checkpoint "$status" || true
    if [ "$status" = VALID ]; then
      accepted="$primary_raw"
    elif [ "$status" = STRUCTURAL_INVALID ] && \
      [ "$(jq -r '.repairPermitted' "$primary_validation")" = true ]; then
      python3 "$root/scripts/lib/analysis-trajectory-checkpoint.py" render-repair-prompt \
        "$request" "$primary_validation" "$repair_prompt" || { rm -rf "$scratch"; return 2; }
      mana_trajectory_telemetry_emit provider_iteration_started provider_invocation trajectory-checkpoint-repair \
        "$provider" "$model" "${effort:-none}" trajectory/checkpoint-repair started || true
      if mana_trajectory_guard_provider_call "$provider" "$model" "$effort" "$repair_prompt" "$repair_raw" "$scratch/repair"; then
        python3 "$root/scripts/lib/analysis-trajectory-checkpoint.py" assess-response \
          "$request" "$repair_raw" "$repair_validation" --calls-used 2 >/dev/null 2>&1 || true
        status="$(jq -r '.status // "PROVIDER_FAILED"' "$repair_validation" 2>/dev/null)"
        [ "$status" != VALID ] || accepted="$repair_raw"
      else
        python3 "$root/scripts/lib/analysis-trajectory-checkpoint.py" provider-failed \
          "$request" "$repair_validation" || true
        status=PROVIDER_FAILED
      fi
      mana_trajectory_telemetry_emit provider_iteration_completed provider_invocation trajectory-checkpoint-repair \
        "$provider" "$model" "${effort:-none}" trajectory/checkpoint-repair "$status" || true
    fi
  fi

  [ -f "$primary_validation" ] || {
    python3 "$root/scripts/lib/analysis-trajectory-checkpoint.py" provider-failed \
      "$request" "$primary_validation" || { rm -rf "$scratch"; return 2; }
  }
  python3 "$root/scripts/lib/analysis-trajectory-checkpoint.py" record-run \
    "$config" "$request" "$provider" "$model" "${effort:-none}" \
    "$primary_validation" "$([ -f "$repair_validation" ] && printf '%s' "$repair_validation" || printf '%s' -)" \
    "$accepted" "$run" || { rm -rf "$scratch"; return 2; }
  mana_trajectory_guard_atomic_copy "$primary_validation" \
    "$workspace/validation/analysis-trajectory-checkpoint-primary-validation-v1.json" || {
    rm -rf "$scratch"; return 2;
  }
  if [ -f "$repair_validation" ]; then
    mana_trajectory_guard_atomic_copy "$repair_validation" \
      "$workspace/validation/analysis-trajectory-checkpoint-repair-validation-v1.json" || {
      rm -rf "$scratch"; return 2;
    }
  fi
  if [ "$accepted" != - ]; then
    local response_target
    response_target="$workspace/validation/analysis-trajectory-checkpoint-response-v1.json"
    mana_trajectory_guard_atomic_copy "$accepted" "$response_target" || { rm -rf "$scratch"; return 2; }
    local accepted_outcome
    accepted_outcome="$(jq -r '.outcome' "$accepted")" || { rm -rf "$scratch"; return 2; }
    mana_trajectory_telemetry_emit compact_context_synthesis_completed trajectory_governor \
      trajectory-checkpoint-applied host "$model" "${effort:-none}" trajectory/checkpoint \
      "$accepted_outcome" --reason-codes checkpoint-response-accepted || true
    MANA_TRAJECTORY_GUARD_HEADER="$scratch/reanchor-header.json"
    if ! python3 "$root/scripts/lib/analysis-trajectory-integration.py" apply-response \
      "$workspace" "$accepted" "$run" "${MANA_ANALYSIS_TRAJECTORY_SCOPE_APPROVAL_PATH:--}" \
      "$MANA_TRAJECTORY_GUARD_HEADER"; then
      rm -rf "$scratch"
      return 2
    fi
    # A re-anchor header must survive until the next provider prompt is built.
    if [ -f "$MANA_TRAJECTORY_GUARD_HEADER" ]; then
      local persistent_header
      persistent_header="$(mktemp "${TMPDIR:-/tmp}/mana-trajectory-reanchor-tg06.json.XXXXXX")" || {
        rm -rf "$scratch"; return 2;
      }
      cp "$MANA_TRAJECTORY_GUARD_HEADER" "$persistent_header" || { rm -rf "$scratch"; return 2; }
      MANA_TRAJECTORY_GUARD_HEADER="$persistent_header"
      MANA_ANALYSIS_TRAJECTORY_REANCHOR_HEADER="$persistent_header"
      export MANA_ANALYSIS_TRAJECTORY_REANCHOR_HEADER
    else
      MANA_TRAJECTORY_GUARD_HEADER=""
      unset MANA_ANALYSIS_TRAJECTORY_REANCHOR_HEADER
    fi
  else
    python3 "$root/scripts/lib/analysis-trajectory-integration.py" mark-failure \
      "$workspace" invalid-checkpoint-after-bounded-repair || true
  fi
  rm -rf "$scratch"
}

# Evaluate the guard at one real boundary. Returns non-zero only when an
# enforced path must halt; shadow diagnostics never alter control flow.
mana_trajectory_guard_boundary() {
  local provider="$1" base_model="$2" workspace="$3" boundary="$4"
  local root mode checkpoint_model checkpoint_effort outcome decision
  root="$(mana_trajectory_guard_root)"
  mode="$(mana_trajectory_guard_mode)" || return 2
  [ "$mode" != OFF ] || return 0
  checkpoint_model="$(mana_story_start_scope_v2_stage_model trajectory-checkpoint "$base_model")" || return 2
  checkpoint_effort="$(mana_story_start_scope_v2_stage_effort trajectory-checkpoint)" || return 2
  if ! python3 "$root/scripts/lib/analysis-trajectory-integration.py" evaluate \
    "$workspace" "$MANA_TRAJECTORY_TELEMETRY_EVENTS" "$mode" "$boundary" \
    "$provider" "$checkpoint_model" "${checkpoint_effort:-none}" \
    "${MANA_ANALYSIS_TRAJECTORY_OBSERVATION_PATH:--}" \
    "${MANA_ANALYSIS_TRAJECTORY_CHECKPOINT_INPUT_PATH:--}"; then
    if [ "$mode" = SHADOW ]; then
      echo 'WARNING: trajectory shadow evaluation failed; Story Start control flow is unchanged' >&2
      return 0
    fi
    echo 'ERROR: trajectory enforcement evaluation failed closed' >&2
    return 1
  fi
  [ "$mode" = ENFORCE ] || return 0
  outcome="$(jq -r '.outcome' "$workspace/validation/analysis-trajectory-recommendation-v1.json")"
  if [ "$outcome" = CHECKPOINT_RECOMMENDED ]; then
    mana_trajectory_guard_checkpoint "$provider" "$base_model" "$workspace" || {
      python3 "$root/scripts/lib/analysis-trajectory-integration.py" mark-failure \
        "$workspace" checkpoint-execution-failed || true
    }
  else
    python3 "$root/scripts/lib/analysis-trajectory-integration.py" apply-direct \
      "$workspace" "${MANA_ANALYSIS_TRAJECTORY_SCOPE_APPROVAL_PATH:--}" || {
      python3 "$root/scripts/lib/analysis-trajectory-integration.py" mark-failure \
        "$workspace" deterministic-application-failed || true
    }
  fi
  decision="$(jq -r '.controlDecision' "$workspace/validation/analysis-trajectory-integration-run-v1.json")"
  case "$decision" in
    CONTINUE|REANCHOR|PROCEED_DOWNSTREAM) return 0 ;;
    HALT_OWNER_REVIEW|HALT_PARTIAL)
      mana_trajectory_telemetry_emit analysis_stopped trajectory_governor "$decision" \
        host none none trajectory/public "$decision" --reason-codes trajectory-enforcement-stop || true
      mana_trajectory_telemetry_finish || true
      return 1
      ;;
    *)
      echo 'ERROR: trajectory enforcement produced an unknown control decision' >&2
      return 1
      ;;
  esac
}

mana_trajectory_guard_cleanup() {
  if [ -n "$MANA_TRAJECTORY_GUARD_HEADER" ] && [ -f "$MANA_TRAJECTORY_GUARD_HEADER" ]; then
    rm -f "$MANA_TRAJECTORY_GUARD_HEADER"
  fi
  MANA_TRAJECTORY_GUARD_HEADER=""
  unset MANA_ANALYSIS_TRAJECTORY_REANCHOR_HEADER
}
