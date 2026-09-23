#!/usr/bin/env bash
# CTX-07C host-owned transport selection. This contains no provider reach.

mana_context_provider_child_adapter_available() {
  # No production provider currently exposes the complete attested transport.
  # The deterministic protocol adapter overrides this function only from the
  # canonical test-only runner entry point.
  return 1
}

mana_context_select_worker_transport() {
  local provider="$1" mode="$2" effort_required="$3" capabilities="$4" capability status
  export MANA_CONTEXT_WORKER_TRANSPORT="host-worker"
  MANA_CONTEXT_CHILD_GAPS=()
  case "$mode" in disabled) return 0 ;; prefer|require) ;; *) return 2 ;; esac
  mana_context_provider_child_adapter_available "$provider" || \
    MANA_CONTEXT_CHILD_GAPS+=("adapter:$provider:unsupported")
  for capability in freshInvocation ephemeralSession explicitModelSelection providerManagedSubagents \
    managedChildExecutionAttestation childContextInheritanceControl childModelRouting \
    recursiveDelegationPrevention maximumChildConcurrency maximumChildDepth \
    structuredOutputSchema userConfigurationIsolation
  do
    status="$(jq -er --arg capability "$capability" '.capabilities[$capability].status' "$capabilities")" || return 2
    [ "$status" = supported ] || MANA_CONTEXT_CHILD_GAPS+=("$capability:$status")
  done
  if [ "$effort_required" = true ]; then
    for capability in explicitReasoningEffort childReasoningEffortRouting; do
      status="$(jq -er --arg capability "$capability" '.capabilities[$capability].status' "$capabilities")" || return 2
      [ "$status" = supported ] || MANA_CONTEXT_CHILD_GAPS+=("$capability:$status")
    done
  fi
  if [ "${#MANA_CONTEXT_CHILD_GAPS[@]}" -eq 0 ]; then
    export MANA_CONTEXT_WORKER_TRANSPORT="provider-managed-child"
    return 0
  fi
  [ "$mode" = prefer ] && return 0
  return 1
}
