#!/usr/bin/env bash
# Canonical read-only execution-plan calculation shared by cast and eval.

mana_skill_metadata() {
  awk -v target="$2" '
    $1 == "-" && $2 == "id:" { if (found) { print path "|" tier "|" risk "|" mode "|" group "|" capability "|" spec; exit }; active=($3 == target); found=active; next }
    active && $1 == "path:" { path=$2 }
    active && $1 == "model_tier:" { tier=$2 }
    active && $1 == "risk_level:" { risk=$2 }
    active && $1 == "execution_mode:" { mode=$2 }
    active && $1 == "delegation_group:" { group=$2 }
    active && $1 == "capability:" { capability=$2 }
    active && $1 == "verification_spec:" { spec=$2 }
    END { if (found && active) print path "|" tier "|" risk "|" mode "|" group "|" capability "|" spec }
  ' "$1" 
}

mana_document_list() {
  awk -v wanted="$2" '
    /^---[[:space:]]*$/ { boundaries++; if (boundaries == 2) exit; next }
    boundaries == 1 && $0 ~ "^" wanted ":[[:space:]]*$" { active=1; next }
    boundaries == 1 && active && /^[a-z_]+:/ { exit }
    boundaries == 1 && active && /^  - / { sub(/^  - /, ""); print }
  ' "$1"
}

# This is the single authoritative tool classification. Tool names describe
# capabilities in agent/skill metadata; unknown tools are conservative writes.
mana_tool_capability() {
  case "$1" in
    read_files|code_search|*_read|*_search|*_list|*_get|*_show|*_status|*_validate|database_snapshot_read|liquibase_validate) printf read ;;
    *) printf write ;;
  esac
}

mana_execution_plan() {
  # $1 mana root, $2 profile file. Sets MANA_PLAN_* newline-separated globals.
  local root="$1" profile_file="$2" skill metadata skill_path tier risk mode group capability spec agent tool class runners effect
  MANA_PLAN_ERROR=""; MANA_PLAN_SKILLS="$(mana_profile_skills "$profile_file" | LC_ALL=C sort -u)"
  MANA_PLAN_AGENTS="$(mana_profile_list "$profile_file" agents | LC_ALL=C sort -u)"
  MANA_PLAN_TOOLS=""; MANA_PLAN_ARTIFACTS=""; MANA_PLAN_ROUTING=""; MANA_PLAN_EFFECTS=""; MANA_PLAN_RUNNERS="mana_orchestrator"; MANA_PLAN_WRITE_REASON=""
  for agent in $MANA_PLAN_AGENTS; do
    [ -f "$root/agents/$agent/AGENT.md" ] || { MANA_PLAN_ERROR="invalid profile metadata: unknown agent '$agent'"; return 1; }
    while IFS= read -r tool; do [ -z "$tool" ] || MANA_PLAN_TOOLS="${MANA_PLAN_TOOLS}${MANA_PLAN_TOOLS:+$'\n'}$tool"; done < <(mana_document_list "$root/agents/$agent/AGENT.md" allowed_tools)
    while IFS= read -r tool; do [ -z "$tool" ] || MANA_PLAN_ARTIFACTS="${MANA_PLAN_ARTIFACTS}${MANA_PLAN_ARTIFACTS:+$'\n'}$agent: $tool"; done < <(mana_document_list "$root/agents/$agent/AGENT.md" outputs)
  done
  for skill in $MANA_PLAN_SKILLS; do
    metadata="$(mana_skill_metadata "$root/skills/index.yaml" "$skill")"; [ -n "$metadata" ] || { MANA_PLAN_ERROR="invalid profile metadata: unknown skill '$skill'"; return 1; }
    IFS='|' read -r skill_path tier risk mode group capability spec <<EOF
$metadata
EOF
    [ -f "$root/$skill_path" ] || { MANA_PLAN_ERROR="invalid skill metadata: missing $skill_path for '$skill'"; return 1; }
    MANA_PLAN_ROUTING="${MANA_PLAN_ROUTING}${MANA_PLAN_ROUTING:+$'\n'}$skill: tier=${tier:-unspecified}, risk=${risk:-unspecified}, group=${group:-unspecified}, mode=${mode:-unspecified}"
    if [ "$capability" = verification ] && [ -f "$root/$(dirname "$skill_path")/$spec" ] && command -v jq >/dev/null 2>&1; then
      while IFS= read -r effect; do
        [ -n "$effect" ] && MANA_PLAN_EFFECTS="${MANA_PLAN_EFFECTS}${MANA_PLAN_EFFECTS:+$'\n'}$skill: $effect"
      done < <(jq -r '.checks[] | "source_tree=" + .effects.source_tree + ", mana_workspace=" + .effects.mana_workspace + ", build_outputs=" + .effects.build_outputs + ", external_state=" + .effects.external_state + ", network=" + .effects.network' "$root/$(dirname "$skill_path")/$spec")
    fi
    [ "$tier" = full ] || [ "$risk" = high ] && MANA_PLAN_RUNNERS="${MANA_PLAN_RUNNERS}"$'\n'"mana_full_specialist"
    [ "$mode" = write ] && { MANA_PLAN_RUNNERS="${MANA_PLAN_RUNNERS}"$'\n'"mana_worker"; [ -n "$MANA_PLAN_WRITE_REASON" ] || MANA_PLAN_WRITE_REASON="WRITE_SKILL_SELECTED|Selected skill $skill declares execution_mode=write"; }
    [ "$mode" = write ] || MANA_PLAN_RUNNERS="${MANA_PLAN_RUNNERS}"$'\n'"mana_explorer"
    while IFS= read -r tool; do [ -z "$tool" ] || MANA_PLAN_TOOLS="${MANA_PLAN_TOOLS}${MANA_PLAN_TOOLS:+$'\n'}$tool"; done < <(mana_document_list "$root/$skill_path" allowed_tools)
  done
  MANA_PLAN_TOOLS="$(printf '%s\n' "$MANA_PLAN_TOOLS" | sed '/^$/d' | LC_ALL=C sort -u)"
  MANA_PLAN_ARTIFACTS="$(printf '%s\n' "$MANA_PLAN_ARTIFACTS" | sed '/^$/d' | LC_ALL=C sort -u)"
  runners="$(printf '%s\n' "$MANA_PLAN_RUNNERS" | grep -vx 'mana_orchestrator' | LC_ALL=C sort -u || true)"
  # Keep orchestrator first regardless of lexical order.
  MANA_PLAN_RUNNERS="mana_orchestrator${runners:+$'\n'}$runners"
  while IFS= read -r tool; do
    [ -n "$tool" ] && [ "$(mana_tool_capability "$tool")" = write ] && { [ -n "$MANA_PLAN_WRITE_REASON" ] || MANA_PLAN_WRITE_REASON="MUTATING_TOOL_ALLOWED|Effective tool allowlist includes mutating tool $tool"; }
  done <<EOF
$MANA_PLAN_TOOLS
EOF
  return 0
}
