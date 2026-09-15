#!/usr/bin/env bash
# Internal packet consumer transport; no compilation or argv reconstruction.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd -P)"
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/provider-execution.sh"
provider="$1" project_root="$2" profile="$3" execution="$4"
shift 4
prompt="$(cat)"
MANA_RUNTIME_EXECUTION_ID="$execution" MANA_PROFILE_RUNNING=1 \
  mana_provider_execute_host_policy false "$provider" "$project_root" "$profile" "$prompt" "$provider" "$@"
