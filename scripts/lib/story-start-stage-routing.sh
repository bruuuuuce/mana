#!/usr/bin/env bash
# Explicit Story Start Scope v2 stage routing.  This file resolves requested
# model/effort metadata only; provider invocation remains in provider-dispatch.

MANA_STORY_START_ROUTE_MODEL=""
MANA_STORY_START_ROUTE_EFFORT=""
MANA_STORY_START_ROUTE_MODEL_SOURCE=""
MANA_STORY_START_ROUTE_EFFORT_SOURCE=""
MANA_STORY_START_ROUTE_EFFORT_DISPATCH=""

mana_story_start_stage_valid() {
  case "$1" in discovery|triage|planner|correction|trajectory-checkpoint) return 0 ;; *) return 1 ;; esac
}

mana_story_start_stage_valid_effort() {
  case "$1" in minimal|low|medium|high|xhigh) return 0 ;; *) return 1 ;; esac
}

mana_story_start_stage_default_model() {
  local provider="$1" stage="$2"
  mana_story_start_stage_valid "$stage" || return 1
  case "$provider:$stage" in
    codex:discovery|codex:correction|codex:trajectory-checkpoint) printf '%s\n' 'gpt-5.6-terra' ;;
    codex:triage|codex:planner) printf '%s\n' 'gpt-5.6-sol' ;;
    claude:discovery|claude:correction|claude:trajectory-checkpoint) printf '%s\n' 'sonnet' ;;
    claude:triage|claude:planner) printf '%s\n' 'opus' ;;
    opencode:*) printf '%s\n' 'opencode/gpt-5.1-codex' ;;
    *) return 1 ;;
  esac
}

mana_story_start_stage_default_effort() {
  local provider="$1" stage="$2"
  mana_story_start_stage_valid "$stage" || return 1
  case "$provider:$stage" in
    *:discovery|*:correction|*:trajectory-checkpoint) printf '%s\n' 'high' ;;
    *:triage) printf '%s\n' 'xhigh' ;;
    *:planner) printf '%s\n' 'high' ;;
    *) return 1 ;;
  esac
}

mana_story_start_stage_effort_dispatch() {
  case "$1" in codex) printf '%s\n' 'explicit' ;; claude|opencode) printf '%s\n' 'unsupported' ;; *) return 1 ;; esac
}

mana_story_start_stage_env_value() {
  local provider="$1" stage="$2" field="$3" normalized_stage variable_name
  normalized_stage="$(printf '%s' "$stage" | tr '[:lower:]-' '[:upper:]_')"
  variable_name="MANA_$(printf '%s' "$provider" | tr '[:lower:]' '[:upper:]')_STORY_START_${normalized_stage}_${field}"
  printf '%s' "${!variable_name:-}"
}

# Arguments: provider stage root-model root-effort root-model-explicit(true|false)
# root-effort-explicit(true|false) stage-cli-model stage-cli-effort.
# Outputs are the MANA_STORY_START_ROUTE_* globals.  Explicit root values remain
# a compatibility fallback, while stage-specific values always take precedence.
mana_story_start_stage_resolve() {
  local provider="$1" stage="$2" root_model="$3" root_effort="$4" root_model_explicit="$5" root_effort_explicit="$6" cli_model="$7" cli_effort="$8"
  local env_model env_effort default_model default_effort
  mana_story_start_stage_valid "$stage" || return 1
  case "$provider" in codex|claude|opencode) ;; *) return 1 ;; esac
  case "$root_model_explicit:$root_effort_explicit" in true:true|true:false|false:true|false:false) ;; *) return 1 ;; esac
  [ -z "$root_effort" ] || mana_story_start_stage_valid_effort "$root_effort" || return 1
  [ -z "$cli_effort" ] || mana_story_start_stage_valid_effort "$cli_effort" || return 1

  env_model="$(mana_story_start_stage_env_value "$provider" "$stage" MODEL)" || return 1
  env_effort="$(mana_story_start_stage_env_value "$provider" "$stage" EFFORT)" || return 1
  [ -z "$env_effort" ] || mana_story_start_stage_valid_effort "$env_effort" || return 1
  default_model="$(mana_story_start_stage_default_model "$provider" "$stage")" || return 1
  default_effort="$(mana_story_start_stage_default_effort "$provider" "$stage")" || return 1

  if [ -n "$cli_model" ]; then
    MANA_STORY_START_ROUTE_MODEL="$cli_model"
    MANA_STORY_START_ROUTE_MODEL_SOURCE="stage-cli"
  elif [ -n "$env_model" ]; then
    MANA_STORY_START_ROUTE_MODEL="$env_model"
    MANA_STORY_START_ROUTE_MODEL_SOURCE="stage-environment"
  elif [ "$root_model_explicit" = true ]; then
    MANA_STORY_START_ROUTE_MODEL="$root_model"
    MANA_STORY_START_ROUTE_MODEL_SOURCE="root-compatibility-override"
  else
    MANA_STORY_START_ROUTE_MODEL="$default_model"
    MANA_STORY_START_ROUTE_MODEL_SOURCE="provider-stage-default"
  fi

  if [ -n "$cli_effort" ]; then
    MANA_STORY_START_ROUTE_EFFORT="$cli_effort"
    MANA_STORY_START_ROUTE_EFFORT_SOURCE="stage-cli"
  elif [ -n "$env_effort" ]; then
    MANA_STORY_START_ROUTE_EFFORT="$env_effort"
    MANA_STORY_START_ROUTE_EFFORT_SOURCE="stage-environment"
  elif [ "$root_effort_explicit" = true ]; then
    MANA_STORY_START_ROUTE_EFFORT="$root_effort"
    MANA_STORY_START_ROUTE_EFFORT_SOURCE="root-compatibility-override"
  else
    MANA_STORY_START_ROUTE_EFFORT="$default_effort"
    MANA_STORY_START_ROUTE_EFFORT_SOURCE="provider-stage-default"
  fi
  MANA_STORY_START_ROUTE_EFFORT_DISPATCH="$(mana_story_start_stage_effort_dispatch "$provider")" || return 1
}

mana_story_start_stage_route_diagnostic() {
  local provider="$1" stage="$2"
  printf 'Story Start Scope v2 route: stage=%s provider=%s model=%s model_source=%s effort=%s effort_source=%s effort_dispatch=%s\n' \
    "$stage" "$provider" "$MANA_STORY_START_ROUTE_MODEL" "$MANA_STORY_START_ROUTE_MODEL_SOURCE" \
    "$MANA_STORY_START_ROUTE_EFFORT" "$MANA_STORY_START_ROUTE_EFFORT_SOURCE" "$MANA_STORY_START_ROUTE_EFFORT_DISPATCH"
}
