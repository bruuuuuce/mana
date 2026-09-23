#!/usr/bin/env bash
# Test-only capability and argv adapter for the generic attested child protocol.
# shellcheck disable=SC2034 # sourced adapter globals are consumed by the runner.

mana_context_provider_child_adapter_available() {
  [ "$1" = claude ]
}

mana_ctx07c_test_capability_snapshot() {
  local probed="$1" snapshot
  [ -f "$probed" ] && [ ! -L "$probed" ] || return 1
  snapshot="$(jq -c '
    if .provider != "claude" then error("fixture provider mismatch") else . end |
    .probeSource="fixture" |
    .probeEvidence=((.probeEvidence + ["fixture:ctx07c-r2-attested-adapter"]) | unique) |
    [
      "freshInvocation", "ephemeralSession", "explicitModelSelection",
      "explicitReasoningEffort", "providerManagedSubagents",
      "managedChildExecutionAttestation", "childContextInheritanceControl",
      "childModelRouting", "childReasoningEffortRouting",
      "recursiveDelegationPrevention", "maximumChildConcurrency",
      "maximumChildDepth", "structuredOutputSchema", "userConfigurationIsolation"
    ] as $required |
    reduce $required[] as $name (.;
      .capabilities[$name]={
        status:"supported",
        evidence:["fixture:ctx07c-r2-attested-adapter"]
      }
    )
  ' "$probed")" || return 1
  if [ -n "${CTX07B_STATE_DIR:-}" ]; then
    mkdir -p "$CTX07B_STATE_DIR"
    printf '%s\n' "$snapshot" > "$CTX07B_STATE_DIR/capability-snapshot.json"
    chmod 600 "$CTX07B_STATE_DIR/capability-snapshot.json"
  fi
  printf '%s\n' "$snapshot"
}

mana_provider_child_worker_args() {
  local provider="$1" project="$2" model="$3" reasoning_effort="$4" output_schema="$5"
  MANA_PROVIDER_ARGS=()
  MANA_PROVIDER_OPENCODE_CONFIG_CONTENT=""
  [ "$provider" = claude ] || return 1
  case "$reasoning_effort" in minimal|low|medium|high|xhigh|max) ;; *) return 1 ;; esac
  [ -d "$project" ] && [ ! -L "$project" ] || return 1
  [ -f "$output_schema" ] && [ ! -L "$output_schema" ] || return 1
  MANA_PROVIDER_ARGS=(
    --mana-ctx07c-test-attested-child
    --model "$model"
    --effort "$reasoning_effort"
    --output-schema "$output_schema"
  )
}
