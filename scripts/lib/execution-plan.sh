#!/usr/bin/env bash
# Canonical execution-plan projection. Activation and routing metadata come
# only from one already compiled, authoritatively validated context manifest.
# shellcheck disable=SC2034

mana_skill_catalog_record() {
  awk -v target="$2" '
    $1 == "-" && $2 == "id:" { if (found) { print path "|" capability "|" spec; found=0; active=0; exit }; active=($3 == target); found=active; next }
    active && $1 == "path:" { path=$2 }
    active && $1 == "capability:" { capability=$2 }
    active && $1 == "verification_spec:" { spec=$2 }
    END { if (found && active) print path "|" capability "|" spec }
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
    read_files|code_search|*_read|*_search|*_list|*_get|*_show|*_status|*_validate) printf read ;;
    *) printf write ;;
  esac
}

mana_execution_plan_json() {
  # $1 Mana root, $2 immutable canonical context-manifest-v1 JSON.
  # Callers that cross an authority boundary must pass the exact bytes emitted
  # by authoritative-materialize-context-manifest rather than reopening the
  # caller-controlled pathname after validation.
  local root="$1" manifest_json="$2" skill record skill_path capability spec agent tool runners effect
  local tier risk mode group parallel
  # These globals are the function's public projection consumed by cast,
  # run-profile, and eval rather than by this library in isolation.
  # shellcheck disable=SC2034
  MANA_PLAN_ERROR=""
  jq -e '.schemaVersion == "mana.context-runtime.context-manifest/v1"' <<<"$manifest_json" >/dev/null 2>&1 || {
    MANA_PLAN_ERROR="canonical context manifest is malformed"; return 1;
  }
  # shellcheck disable=SC2034
  MANA_PLAN_CANDIDATE_SKILLS="$(jq -r '.declaredCandidateSkills[]' <<<"$manifest_json")"
  # shellcheck disable=SC2034
  MANA_PLAN_SKILLS="$(jq -r '.activatedSkills[].id' <<<"$manifest_json")"
  # shellcheck disable=SC2034
  MANA_PLAN_INACTIVE_SKILLS="$(jq -r '.inactiveSkills[]' <<<"$manifest_json")"
  # shellcheck disable=SC2034
  MANA_PLAN_AVAILABLE_CONDITIONALS="$(jq -r '.availableConditionalSkills[] | .signal + ": " + .skill' <<<"$manifest_json")"
  # shellcheck disable=SC2034
  MANA_PLAN_DEEP_LOADED_SKILLS="$(jq -r '.deepLoadedSkills[].id' <<<"$manifest_json")"
  MANA_PLAN_AGENTS="$(jq -r '.semanticAgents[]' <<<"$manifest_json")"
  MANA_PLAN_TOOLS=""
  MANA_PLAN_ARTIFACTS=""
  MANA_PLAN_ROUTING=""
  MANA_PLAN_EFFECTS=""
  MANA_PLAN_RUNNERS="mana_orchestrator"
  MANA_PLAN_WRITE_REASON=""

  for agent in $MANA_PLAN_AGENTS; do
    [ -f "$root/agents/$agent/AGENT.md" ] || { MANA_PLAN_ERROR="authoritative manifest references missing agent '$agent'"; return 1; }
    while IFS= read -r tool; do
      [ -z "$tool" ] || MANA_PLAN_TOOLS="${MANA_PLAN_TOOLS}${MANA_PLAN_TOOLS:+$'\n'}$tool"
    done < <(mana_document_list "$root/agents/$agent/AGENT.md" allowed_tools)
    while IFS= read -r artifact; do
      [ -n "$artifact" ] || continue
      if jq -e --arg artifact "$artifact" '.requiredArtifacts | index($artifact) != null' <<<"$manifest_json" >/dev/null; then
        MANA_PLAN_ARTIFACTS="${MANA_PLAN_ARTIFACTS}${MANA_PLAN_ARTIFACTS:+$'\n'}$agent: $artifact"
      fi
    done < <(mana_document_list "$root/agents/$agent/AGENT.md" outputs)
  done

  while IFS='|' read -r skill tier risk mode group parallel; do
    [ -n "$skill" ] || continue
    MANA_PLAN_ROUTING="${MANA_PLAN_ROUTING}${MANA_PLAN_ROUTING:+$'\n'}$skill: tier=$tier, risk=$risk, group=$group, mode=$mode, parallel_safe=$parallel"
    if [ "$tier" = full ] || [ "$risk" = high ]; then
      MANA_PLAN_RUNNERS="${MANA_PLAN_RUNNERS}"$'\n'"mana_full_specialist"
    fi
    if [ "$mode" = write ]; then
      MANA_PLAN_RUNNERS="${MANA_PLAN_RUNNERS}"$'\n'"mana_worker"
      [ -n "$MANA_PLAN_WRITE_REASON" ] || MANA_PLAN_WRITE_REASON="WRITE_SKILL_SELECTED|Selected skill $skill declares execution_mode=write"
    else
      MANA_PLAN_RUNNERS="${MANA_PLAN_RUNNERS}"$'\n'"mana_explorer"
    fi

    record="$(mana_skill_catalog_record "$root/skills/index.yaml" "$skill")"
    [ -n "$record" ] || { MANA_PLAN_ERROR="authoritative manifest references unknown active skill '$skill'"; return 1; }
    IFS='|' read -r skill_path capability spec <<EOF
$record
EOF
    [ -f "$root/$skill_path" ] || { MANA_PLAN_ERROR="active skill body is missing for '$skill'"; return 1; }
    while IFS= read -r tool; do
      [ -z "$tool" ] || MANA_PLAN_TOOLS="${MANA_PLAN_TOOLS}${MANA_PLAN_TOOLS:+$'\n'}$tool"
    done < <(mana_document_list "$root/$skill_path" allowed_tools)
    if [ "$capability" = verification ] && [ -f "$root/$(dirname "$skill_path")/$spec" ] && command -v jq >/dev/null 2>&1; then
      while IFS= read -r effect; do
        [ -n "$effect" ] && MANA_PLAN_EFFECTS="${MANA_PLAN_EFFECTS}${MANA_PLAN_EFFECTS:+$'\n'}$skill: $effect"
      done < <(jq -r '.checks[] | "source_tree=" + .effects.source_tree + ", mana_workspace=" + .effects.mana_workspace + ", build_outputs=" + .effects.build_outputs + ", external_state=" + .effects.external_state + ", network=" + .effects.network' "$root/$(dirname "$skill_path")/$spec")
    fi
  done < <(jq -r '.activatedSkills[] | [.id,.modelTier,.riskLevel,.executionMode,.delegationGroup,(.parallelSafe|tostring)] | join("|")' <<<"$manifest_json")

  MANA_PLAN_TOOLS="$(printf '%s\n' "$MANA_PLAN_TOOLS" | sed '/^$/d' | LC_ALL=C sort -u)"
  MANA_PLAN_ARTIFACTS="$(printf '%s\n' "$MANA_PLAN_ARTIFACTS" | sed '/^$/d' | LC_ALL=C sort -u)"
  runners="$(printf '%s\n' "$MANA_PLAN_RUNNERS" | grep -vx 'mana_orchestrator' | LC_ALL=C sort -u || true)"
  MANA_PLAN_RUNNERS="mana_orchestrator${runners:+$'\n'}$runners"
  while IFS= read -r tool; do
    if [ -n "$tool" ] && [ "$(mana_tool_capability "$tool")" = write ]; then
      [ -n "$MANA_PLAN_WRITE_REASON" ] || MANA_PLAN_WRITE_REASON="MUTATING_TOOL_ALLOWED|Effective tool allowlist includes mutating tool $tool"
    fi
  done <<EOF
$MANA_PLAN_TOOLS
EOF
  return 0
}

mana_execution_plan() {
  # Compatibility wrapper for non-authoritative callers and focused tests.
  # Runtime callers use mana_execution_plan_json so validation and consumption
  # cannot be separated by a second read of a mutable pathname.
  local root="$1" manifest="$2" manifest_json
  [ -f "$manifest" ] || { MANA_PLAN_ERROR="canonical context manifest not found: $manifest"; return 1; }
  manifest_json="$(command cat "$manifest")" || {
    MANA_PLAN_ERROR="canonical context manifest could not be read: $manifest"
    return 1
  }
  mana_execution_plan_json "$root" "$manifest_json"
}
