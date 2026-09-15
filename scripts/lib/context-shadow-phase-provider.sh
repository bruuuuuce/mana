#!/usr/bin/env bash
# CTX-09C fresh-phase adapter: argv never leaves its real Bash array.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd -P)"
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/provider-execution.sh"
provider="$1" project_root="$2" profile="$3" execution="$4" model="$5" native_schema="$6" threshold="$7"
prompt="$(cat)"
mana_provider_phase_args "$provider" "$project_root" "$model" \
  "$root/contracts/context-runtime/phase-checkpoint-v1.schema.json" "$native_schema" "$threshold"
argv=("${MANA_PROVIDER_ARGS[@]}")
export MANA_RUNTIME_EXECUTION_ID="$execution" MANA_PROFILE_RUNNING=1
if [ "$provider" = opencode ] && [ -n "$MANA_PROVIDER_OPENCODE_CONFIG_CONTENT" ]; then
  OPENCODE_CONFIG_CONTENT="$MANA_PROVIDER_OPENCODE_CONFIG_CONTENT" \
    mana_provider_execute_host_policy false "$provider" "$project_root" "$profile" "$prompt" "$provider" "${argv[@]}"
else
  mana_provider_execute_host_policy false "$provider" "$project_root" "$profile" "$prompt" "$provider" "${argv[@]}"
fi
