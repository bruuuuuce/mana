#!/usr/bin/env bash
# Passive, opt-in telemetry for host-visible Analysis Trajectory boundaries.

MANA_TRAJECTORY_TELEMETRY_ENABLED=false
MANA_TRAJECTORY_TELEMETRY_EVENTS=""
MANA_TRAJECTORY_TELEMETRY_SUMMARY=""
MANA_TRAJECTORY_TELEMETRY_RUN_ID=""

mana_trajectory_telemetry_enabled() {
  case "${MANA_ANALYSIS_TRAJECTORY_TELEMETRY:-false}" in
    1|true|TRUE|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

mana_trajectory_telemetry_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

mana_trajectory_telemetry_init() {
  local workspace="$1" story_ref="$2" root
  mana_trajectory_telemetry_enabled || return 0
  root="$(mana_trajectory_telemetry_root)"
  MANA_TRAJECTORY_TELEMETRY_RUN_ID="$(python3 "$root/scripts/lib/analysis-trajectory-telemetry.py" init "$workspace" "$story_ref" v2)" || return 1
  MANA_TRAJECTORY_TELEMETRY_EVENTS="$workspace/evidence/analysis-trajectory-events-v1.jsonl"
  MANA_TRAJECTORY_TELEMETRY_SUMMARY="$workspace/validation/analysis-trajectory-summary-v1.json"
  MANA_TRAJECTORY_TELEMETRY_ENABLED=true
}

# Arguments: event-type boundary action-kind provider model effort target-scope outcome, then optional --refs groups.
mana_trajectory_telemetry_emit() {
  [ "$MANA_TRAJECTORY_TELEMETRY_ENABLED" = true ] || return 0
  local root
  root="$(mana_trajectory_telemetry_root)"
  python3 "$root/scripts/lib/analysis-trajectory-telemetry.py" emit \
    "$MANA_TRAJECTORY_TELEMETRY_EVENTS" "$MANA_TRAJECTORY_TELEMETRY_RUN_ID" "$@"
}

mana_trajectory_telemetry_finish() {
  [ "$MANA_TRAJECTORY_TELEMETRY_ENABLED" = true ] || return 0
  local root
  root="$(mana_trajectory_telemetry_root)"
  python3 "$root/scripts/lib/analysis-trajectory-telemetry.py" summarize \
    "$MANA_TRAJECTORY_TELEMETRY_EVENTS" "$MANA_TRAJECTORY_TELEMETRY_SUMMARY"
}

# Derive only stable IDs from a host-validated v2 artifact. Text fields stay in
# the original scoped artifact and are never copied into trajectory telemetry.
mana_trajectory_telemetry_observe_artifact() {
  [ "$MANA_TRAJECTORY_TELEMETRY_ENABLED" = true ] || return 0
  local phase="$1" provider="$2" model="$3" effort="$4" target_scope_ref="$5" artifact="$6" root
  root="$(mana_trajectory_telemetry_root)"
  python3 "$root/scripts/lib/analysis-trajectory-telemetry.py" observe-artifact \
    "$MANA_TRAJECTORY_TELEMETRY_EVENTS" "$MANA_TRAJECTORY_TELEMETRY_RUN_ID" \
    "$phase" "$provider" "$model" "$effort" "$target_scope_ref" "$artifact"
}
