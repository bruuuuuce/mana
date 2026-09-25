#!/usr/bin/env bash
# Read-only preflight for a fresh Codex session. A role file alone does not
# prove that a running session loaded it; the final check is a real spawn.
set -euo pipefail

project_root=""
spawn_error_file=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; shift 2 ;;
    --spawn-error-file) spawn_error_file="${2:-}"; shift 2 ;;
    *) echo "usage: $0 --project-root DIR [--spawn-error-file FILE]" >&2; exit 2 ;;
  esac
done
[ -d "$project_root" ] || { echo 'ERROR: project root is missing' >&2; exit 2; }
[ -z "$spawn_error_file" ] || [ -f "$spawn_error_file" ] || { echo 'ERROR: spawn error file is missing' >&2; exit 2; }
command -v codex >/dev/null || { echo 'diagnosis=cli_missing remedy=install_codex_cli'; exit 1; }
project_root="$(cd "$project_root" && pwd -P)"

printf 'codex_version=%s\n' "$(codex --version 2>/dev/null | head -n 1)"
role_dir="$project_root/.codex/agents"
printf 'project_role_catalog='
if [ -d "$role_dir" ]; then
  find "$role_dir" -maxdepth 1 \( -type f -o -type l \) -name '*.toml' -print | sed 's@.*/@@' | sort | paste -sd, -
else
  printf '(none)\n'
fi

feature_output="$(cd "$project_root" && codex features list 2>/dev/null || true)"
feature_state="$(printf '%s\n' "$feature_output" | awk '$1 == "multi_agent" {print $3; exit}')"
printf 'multi_agent=%s\n' "${feature_state:-unknown}"
agents_enabled=""
for config_file in "${CODEX_HOME:-$HOME/.codex}/config.toml" "$project_root/.codex/config.toml"; do
  [ -f "$config_file" ] || continue
  configured_value="$(awk '
    /^\[agents\][[:space:]]*$/ { in_agents=1; next }
    /^\[/ { in_agents=0 }
    in_agents && /^[[:space:]]*enabled[[:space:]]*=/ {
      sub(/#.*/, ""); gsub(/[[:space:]]/, ""); split($0, parts, "="); print parts[2]
    }
  ' "$config_file" | tail -n 1)"
  [ -z "$configured_value" ] || agents_enabled="$configured_value"
done
printf 'agents_enabled=%s\n' "${agents_enabled:-default_true}"
role_file="$role_dir/mana-full-specialist.toml"
if [ ! -f "$role_file" ] || ! grep -Eq '^name = "mana_full_specialist"$' "$role_file"; then
  echo 'diagnosis=role_not_found remedy=run_mana_bootstrap_then_start_fresh_session'
elif [ "$feature_state" = false ] || [ "$agents_enabled" = false ]; then
  echo 'diagnosis=subagents_disabled remedy=enable_multi_agent_then_start_fresh_session'
elif [ -n "$spawn_error_file" ] && grep -Eiq '(model[^[:cntrl:]]*(not found|not available|unsupported|not supported|invalid|rejected|access denied)|unsupported[^[:cntrl:]]*model)' "$spawn_error_file"; then
  echo 'diagnosis=model_rejected remedy=check_account_model_access_and_role_model'
elif [ -L "$role_file" ]; then
  echo 'diagnosis=role_discovery_unconfirmed remedy=replace_managed_role_symlink_with_physical_file_then_start_fresh_session'
elif [ -n "$spawn_error_file" ] && grep -Eiq '(agent type is currently not available|unknown agent|agent[^[:cntrl:]]*not found)' "$spawn_error_file"; then
  echo 'diagnosis=role_discovery_unconfirmed remedy=check_effective_config_and_role_catalog_in_fresh_session'
elif [ "$feature_state" != true ]; then
  echo 'diagnosis=subagent_capability_unknown remedy=check_codex_features_and_effective_config'
else
  echo 'diagnosis=ready_for_spawn_verification remedy=spawn_mana_full_specialist_in_fresh_session'
fi
