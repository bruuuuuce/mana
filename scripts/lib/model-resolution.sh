#!/usr/bin/env bash
# One shell boundary for every provider model selection. Provider argument
# construction must only receive the resolved MANA_PROVIDER_MODEL_ID value.

mana_model_resolution_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

# Args: provider tier effort explicit-model project-root.
# Output globals: MANA_MODEL_RESOLUTION_JSON, MANA_PROVIDER_MODEL_ID.
mana_model_resolve() {
  local provider="$1" tier="$2" effort="$3" explicit_model="$4" project="$5"
  local root result status reason compatibility selected
  MANA_PROVIDER_MODEL_ID=""
  MANA_PROVIDER_MODEL_VARIANT=""
  MANA_MODEL_RESOLUTION_ERROR=""
  root="$(mana_model_resolution_root)" || return 2
  local args=(doctor --provider "$provider" --tier "$tier" --project "$project" --json)
  [ -z "$effort" ] || args+=(--effort "$effort")
  [ -z "$explicit_model" ] || args+=(--model "$explicit_model")
  if result="$(python3 "$root/scripts/mana-models.py" "${args[@]}" 2>/dev/null)"; then
    status=0
  else
    status=$?
  fi
  [ -n "$result" ] || {
    MANA_MODEL_RESOLUTION_ERROR="$provider/$tier discovery produced no diagnostic result"
    return 2
  }
  MANA_MODEL_RESOLUTION_JSON="$result"
  selected="$(jq -r '.selectedModel // empty' <<<"$result")" || return 2
  MANA_PROVIDER_MODEL_VARIANT="$(jq -r '.selectedVariant // empty' <<<"$result")" || return 2
  compatibility="$(jq -r '.invocationCompatibility' <<<"$result")" || return 2
  reason="$(jq -r '.fallbackReason // .selectionReason' <<<"$result")" || return 2
  local explicit_resolution_tier
  explicit_resolution_tier="$(jq -r '.requestedTier' <<<"$result")"
  local explicit_resolution_effort explicit_resolution_model
  explicit_resolution_effort="$(jq -r '.reasoningEffort // empty' <<<"$result")"
  explicit_resolution_model="$(jq -r '.explicitOverride // empty' <<<"$result")"
  if [ "$status" -ne 0 ] || {
      [ "$compatibility" != compatible ] &&
      ! { [ "$compatibility" = unknown ] && [ "$explicit_resolution_tier" != full ] &&
          [ -z "$explicit_resolution_effort" ] && [ -n "$explicit_resolution_model" ] &&
          [ "$selected" = "$explicit_resolution_model" ]; }
    }; then
    MANA_MODEL_RESOLUTION_ERROR="$provider/$tier: $reason"
    MANA_PROVIDER_MODEL_ID=""
    return 2
  fi
  MANA_PROVIDER_MODEL_ID="$selected"
  MANA_MODEL_RESOLUTION_ERROR=""
}
