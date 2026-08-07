#!/usr/bin/env bash
# Explicit execution boundary for Mana profiles. Planning/rendering lives here;
# execution remains exclusively in scripts/run-profile.sh.
set -u

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/profile-metadata.sh
. "$root/scripts/lib/profile-metadata.sh"
. "$root/scripts/lib/json.sh"
. "$root/scripts/lib/execution-plan.sh"
# shellcheck source=lib/divination.sh
. "$root/scripts/lib/divination.sh"
# shellcheck source=lib/runtime-events.sh
. "$root/scripts/lib/runtime-events.sh"

profile=""
project_root="$(pwd)"
dry_run=false
json=false
from_file=""
newline=$'\n'

usage() {
  cat <<'USAGE'
Usage:
  mana cast <profile> [--dry-run] [--json]
  mana cast --from <divination.json> [--dry-run] [--json]

Options:
  --project-root <path>  Target repository. Defaults to current directory.
  --dry-run              Print the execution plan; do not mutate or invoke a runner.
  --json                 Emit one stable JSON result to stdout.
  --from <file>          Use a saved mana divination --json recommendation.
USAGE
}

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r/\\r/g; s/\n/\\n/g'; }

error=""
fail() { error="$1"; return 1; }

json_list() {
  first=true
  printf '['
  while IFS= read -r value; do
    [ -n "$value" ] || continue
    "$first" || printf ','
    first=false
    printf '"%s"' "$(json_escape "$value")"
  done
  printf ']'
}

add_external_system() {
  case "$1" in jira_read|confluence_read|github_read|test_runner_execute_local|database_snapshot_read|liquibase_validate) ;;
    *) return 0 ;;
  esac
  if ! printf '%s\n' "$external_systems" | grep -Fxq "$1"; then
    external_systems="${external_systems}${external_systems:+$newline}$1"
  fi
}

agent_list() {
  awk -v wanted="$2" '
    /^---[[:space:]]*$/ { boundaries++; if (boundaries == 2) exit; next }
    boundaries == 1 && $0 ~ "^" wanted ":[[:space:]]*$" { active=1; next }
    boundaries == 1 && active && /^[a-z_]+:/ { exit }
    boundaries == 1 && active && /^  - / { sub(/^  - /, ""); print }
  ' "$1"
}

skill_metadata() {
  awk -v target="$2" '
    $1 == "-" && $2 == "id:" {
      if (found) { print path "|" tier "|" risk "|" mode "|" group; exit }
      active=($3 == target); found=active; next
    }
    active && $1 == "path:" { path=$2 }
    active && $1 == "model_tier:" { tier=$2 }
    active && $1 == "risk_level:" { risk=$2 }
    active && $1 == "execution_mode:" { mode=$2 }
    active && $1 == "delegation_group:" { group=$2 }
    END { if (found && active) print path "|" tier "|" risk "|" mode "|" group }
  ' "$1"
}

profile_fingerprint() {
  cksum < "$1" | awk '{print $1 "-" $2}'
}

load_divination_result() {
  [ -f "$from_file" ] || fail "divination result not found: $from_file" || return 1
  mana_json_valid_object "$from_file" || fail "malformed divination JSON: expected a JSON object in $from_file" || return 1
  jq -e '.schemaVersion == "2" and .readOnly == true and .status == "recommended" and (.recommendedProfile|type == "string") and (.recommendationContextFingerprint|type == "string") and (.fingerprintAlgorithm == "cksum-logical-manifest-v1") and (.fingerprintInputs|type == "array")' "$from_file" >/dev/null || { fail "incompatible divination result: rerun mana divination --json to create schemaVersion 2 recommendation"; return 1; }
  profile="$(jq -r .recommendedProfile "$from_file")"
  saved_fingerprint="$(jq -r .recommendationContextFingerprint "$from_file")"
  saved_fingerprint_inputs="$(jq -r '.fingerprintInputs[] | .logicalName + "|" + .digest' "$from_file" | LC_ALL=C sort)"
  [ -n "$profile" ] || fail "invalid divination result: recommendedProfile is missing in $from_file" || return 1
  [ -n "$saved_fingerprint" ] || fail "incompatible divination result: profileFingerprint is missing; run mana divination again" || return 1
  case "$profile" in *[!A-Za-z0-9_-]*|'') fail "invalid divination result: recommendedProfile is not a valid profile name"; return 1;; esac
}

validate_profile() {
  profile_file="$root/profiles/$profile.yaml"
  [ -f "$profile_file" ] || fail "profile not found: $profile ($profile_file)" || return 1
  [ "$(mana_profile_value "$profile_file" name)" = "$profile" ] || fail "invalid profile metadata: name does not match requested profile in $profile_file" || return 1
  runner="$(mana_profile_value "$profile_file" runner)"
  case "$runner" in codex|claude|opencode|local/codex|junie|junie/local) ;; *) fail "invalid profile metadata: unsupported runner '$runner' in $profile_file"; return 1;; esac
  if ! divination_validate_metadata "$root"; then fail "$DIVINATION_ERROR"; return 1; fi
  skills="$(mana_profile_skills "$profile_file")"
  [ -n "$skills" ] || fail "invalid profile metadata: no skills declared in $profile_file" || return 1
  while IFS= read -r skill; do
    [ -n "$skill" ] || continue
    metadata="$(skill_metadata "$root/skills/index.yaml" "$skill")"
    [ -n "$metadata" ] || fail "invalid profile metadata: unknown skill '$skill' in $profile_file" || return 1
    skill_path="${metadata%%|*}"
    [ -f "$root/$skill_path" ] || fail "invalid skill metadata: missing $skill_path for '$skill'" || return 1
  done <<EOF
$skills
EOF
  agents="$(mana_profile_list "$profile_file" agents)"
  [ -n "$agents" ] || fail "invalid profile metadata: no agents declared in $profile_file" || return 1
  while IFS= read -r agent; do
    [ -f "$root/agents/$agent/AGENT.md" ] || fail "invalid profile metadata: unknown agent '$agent' in $profile_file" || return 1
  done <<EOF
$agents
EOF
}

validate_service_context() {
  context_root="$(mana_profile_section_value "$profile_file" service_context root)"
  [ -n "$context_root" ] || context_root=".mana/global"
  missing_context=""
  core_context="$(mana_profile_section_list "$profile_file" service_context core_files)"
  while IFS= read -r context; do
    [ -n "$context" ] || continue
    if [ ! -f "$project_root/$context_root/$context" ]; then
      missing_context="${missing_context}${missing_context:+$newline}$context_root/$context"
      [ -n "$MANA_RUNTIME_ROOT" ] && runtime_emit evidence.missing service-context "$context_root/$context" missing "reason=required-context" "$context_root/$context" false || true
    elif [ -n "$MANA_RUNTIME_ROOT" ]; then
      runtime_emit evidence.read service-context "$context_root/$context" read "source=service-context" "$context_root/$context" false || true
    fi
  done <<EOF
$core_context
EOF
  [ -z "$missing_context" ] || fail "Service Context is incomplete. Create or provide: $(printf '%s' "$missing_context" | tr '\n' ' ')" || return 1
}

collect_plan() {
  mana_execution_plan "$root" "$profile_file" || { fail "$MANA_PLAN_ERROR"; return 1; }
  semantic_agents="$MANA_PLAN_AGENTS"; skills="$MANA_PLAN_SKILLS"; allowed_tools="$MANA_PLAN_TOOLS"; artifacts="$MANA_PLAN_ARTIFACTS"; model_routing="$MANA_PLAN_ROUTING"; runner_classes="$MANA_PLAN_RUNNERS"
  external_systems=""
  while IFS= read -r tool; do add_external_system "$tool"; done <<EOF
$allowed_tools
EOF
  blocking_conditions="$(mana_profile_list "$profile_file" blocking_conditions)"
  human_gates=""; [ "$(mana_profile_value "$profile_file" human_approval_requirement)" = true ] && human_gates="profile requires human approval for its governed decision; casting does not satisfy it"
  [ -n "$blocking_conditions" ] && human_gates="${human_gates}${human_gates:+$newline}profile blockers must stop execution when evidenced"
  workspace_paths=".mana/global (existing Service Context)${newline}.mana/user-context (optional generated User Context; inspect-only)${newline}.mana/features/<feature-id> or .mana/sessions/<timestamp>-<branch>-$(mana_profile_section_value "$profile_file" artifact_workspace default_purpose)"
}

render_human() {
  if [ "$dry_run" = true ]; then echo 'MANA CAST DRY RUN'; else echo 'MANA CAST'; fi
  echo "profile: $profile"
  echo "runner: $runner"
  [ -n "$from_file" ] && echo "divination result: $from_file (advisory only)"
  echo 'Semantic agents:'; printf '%s\n' "$semantic_agents" | sed 's/^/- /'
  echo 'Selected skills:'; printf '%s\n' "$skills" | sed 's/^/- /'
  echo 'Expected runner classes:'; printf '%s\n' "$runner_classes" | sed 's/^/- /'
  echo 'Model tiers:'; printf '%s\n' "$model_routing" | sed 's/^/- /'
  echo 'Tools that may be used:'; printf '%s\n' "${allowed_tools:-none}" | sed 's/^/- /'
  echo 'Human gates:'; printf '%s\n' "${human_gates:-none}" | sed 's/^/- /'
  echo 'Expected evidence artifacts:'; printf '%s\n' "${artifacts:-none}" | sed 's/^/- /'
  echo 'Blocking conditions:'; printf '%s\n' "${blocking_conditions:-none}" | sed 's/^/- /'
  echo 'Workspace paths:'; printf '%b\n' "$workspace_paths" | sed 's/^/- /'
  echo 'External systems that may be accessed:'; printf '%s\n' "${external_systems:-none}" | sed 's/^/- /'
  if [ "$dry_run" = true ]; then echo 'No runner, tool, hook, build, test, or filesystem mutation has occurred.'; fi
}

render_json() {
  printf '{"status":"%s","profile":"%s","runner":"%s","dryRun":%s,"from":' "$1" "$(json_escape "$profile")" "$(json_escape "$runner")" "$dry_run"
  [ -n "$from_file" ] && printf '"%s"' "$(json_escape "$from_file")" || printf 'null'
  printf ',"semanticAgents":'; json_list <<<"$semantic_agents"
  printf ',"skills":'; json_list <<<"$skills"
  printf ',"runnerClasses":'; json_list <<<"$runner_classes"
  printf ',"modelRouting":'; json_list <<<"$model_routing"
  printf ',"tools":'; json_list <<<"$allowed_tools"
  printf ',"humanGates":'; json_list <<<"$human_gates"
  printf ',"expectedEvidence":'; json_list <<<"$artifacts"
  printf ',"blockingConditions":'; json_list <<<"$blocking_conditions"
  printf ',"workspacePaths":'; json_list < <(printf '%b\n' "$workspace_paths")
  printf ',"externalSystems":'; json_list <<<"$external_systems"
  printf ',"repositoryModified":false,"manaStateWritten":%s,"telemetryWritten":%s,"runnerInvoked":%s,"externalToolInvoked":%s' "$([ "$dry_run" = true ] && echo false || echo true)" "$([ "$dry_run" = true ] && echo false || echo true)" "$([ "$dry_run" = true ] && echo false || echo true)" "$([ "$dry_run" = true ] && echo false || echo true)"
  printf ',"readOnly":%s' "$dry_run"
  [ -n "$error" ] && printf ',"error":"%s"' "$(json_escape "$error")"
  printf '}\n'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || { error='--project-root requires a path'; break; }; shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    --json) json=true; shift ;;
    --from) from_file="${2:-}"; [ -n "$from_file" ] || { error='--from requires a file'; break; }; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    --*) error="unknown option: $1"; break ;;
    *) if [ -z "$profile" ]; then profile="$1"; shift; else error="unexpected argument: $1"; break; fi ;;
  esac
done

if [ -z "$error" ] && [ -n "$from_file" ] && [ -n "$profile" ]; then error='provide either a profile or --from, not both'; fi
if [ -z "$error" ] && [ ! -d "$project_root" ]; then error="project root not found: $project_root"; fi
if [ -z "$error" ]; then project_root="$(cd "$project_root" && pwd)"; fi
if [ -z "$error" ] && [ -n "$from_file" ]; then load_divination_result || true; fi
if [ -z "$error" ] && [ -z "$profile" ]; then error='a profile or --from divination.json is required'; fi
if [ -z "$error" ]; then validate_profile || true; fi
if [ -z "$error" ] && [ -n "$from_file" ]; then
  divination_recommendation_fingerprint "$root" "$project_root" "$profile" "$saved_fingerprint_inputs"
  current_fingerprint="$DIVINATION_RECOMMENDATION_CONTEXT_FINGERPRINT"
  if [ "$saved_fingerprint" != "$current_fingerprint" ]; then error="stale divination result: profile metadata changed (saved $saved_fingerprint, current $current_fingerprint); run mana divination again"; fi
fi
if [ -z "$error" ]; then validate_service_context || true; fi
if [ -z "$error" ]; then collect_plan; fi

# All checks above are read-only. Runtime telemetry begins only after this
# boundary, so blocked preflight never creates .mana/runtime.
if [ -z "$error" ] && [ "$dry_run" != true ]; then runtime_init "$project_root" "$profile" || echo "WARNING: $MANA_RUNTIME_WARNING" >&2; fi

if [ -n "$error" ]; then
  if [ "$json" = true ]; then
    printf '{"schemaVersion":"2","status":"blocked","profile":'; [ -n "$profile" ] && printf '"%s"' "$(json_escape "$profile")" || printf 'null'; printf ',"repositoryModified":false,"manaStateWritten":false,"telemetryWritten":false,"runnerInvoked":false,"externalToolInvoked":false,"error":"%s"}\n' "$(json_escape "$error")"
  else
    echo 'MANA CAST BLOCKED'
    echo "$error"
  fi
  exit 1
fi

if [ "$dry_run" = true ]; then
  if [ "$json" = true ]; then render_json dry-run; else render_human; fi
  exit 0
fi

# The runtime event publisher is the only writer of execution telemetry.
runtime_emit profile.started profile "$profile" started "runner=$runner" "" false || true
while IFS= read -r cast_skill; do
  [ -n "$cast_skill" ] || continue
  runtime_emit skill.selected skill "$cast_skill" selected "profile=$profile" "" false || true
done <<EOF
$skills
EOF
while IFS= read -r route; do
  [ -n "$route" ] || continue
  route_skill="${route%%:*}"
  runtime_emit model.selected skill "$route_skill" selected "${route#*: }" "" false || true
done <<EOF
$model_routing
EOF
if [ -n "$human_gates" ]; then
  runtime_emit approval.required profile "$profile" required "gate=profile-governance" "" true || { echo "WARNING: $MANA_RUNTIME_WARNING" >&2; echo 'MANA CAST BLOCKED'; echo 'runtime audit storage failed while recording an approval requirement'; exit 1; }
fi

if [ "$json" = true ]; then
  # Keep stdout machine-readable. The existing runner's human transcript goes
  # to stderr; it is still the sole execution engine.
  "$root/scripts/mana-workspace.sh" init --root "$project_root" --purpose "$(mana_profile_section_value "$profile_file" artifact_workspace default_purpose)" >&2 || { error='workspace initialization failed'; runtime_emit profile.failed profile "$profile" failed "reason=workspace-initialization" "" false || true; runtime_finish failed; render_json failed; exit 1; }
  case "$runner" in codex|local/codex) "$root/scripts/run-profile.sh" "$profile" --project-root "$project_root" --codex >&2 ;;
    claude) "$root/scripts/run-profile.sh" "$profile" --project-root "$project_root" --claude >&2 ;;
    opencode) "$root/scripts/run-profile.sh" "$profile" --project-root "$project_root" --opencode >&2 ;;
    *) error="profile runner '$runner' has no CLI execution adapter; use its native runner"; runtime_emit guard.triggered runner "$runner" blocked "reason=no-cli-adapter" "" true || echo "WARNING: $MANA_RUNTIME_WARNING" >&2; runtime_emit profile.failed profile "$profile" failed "reason=no-cli-adapter" "" false || true; runtime_finish failed; render_json blocked; exit 1 ;;
  esac
  status=$?
  [ "$status" -eq 0 ] || { error="runner failed with exit status $status"; runtime_emit profile.failed profile "$profile" failed "exitStatus=$status" "" false || true; runtime_finish failed; render_json failed; exit "$status"; }
  runtime_emit profile.completed profile "$profile" completed "runner=$runner" "" false || true
  runtime_finish completed
  "$root/scripts/mana-learning.sh" --project-root "$project_root" collect >/dev/null 2>&1 || echo 'WARNING: learning-signal collection failed; execution completed without promotion' >&2
  render_json executed
else
  render_human
  "$root/scripts/mana-workspace.sh" init --root "$project_root" --purpose "$(mana_profile_section_value "$profile_file" artifact_workspace default_purpose)" || { runtime_emit profile.failed profile "$profile" failed "reason=workspace-initialization" "" false || true; runtime_finish failed; exit 1; }
  case "$runner" in codex|local/codex) "$root/scripts/run-profile.sh" "$profile" --project-root "$project_root" --codex ;;
    claude) "$root/scripts/run-profile.sh" "$profile" --project-root "$project_root" --claude ;;
    opencode) "$root/scripts/run-profile.sh" "$profile" --project-root "$project_root" --opencode ;;
    *) runtime_emit guard.triggered runner "$runner" blocked "reason=no-cli-adapter" "" true || echo "WARNING: $MANA_RUNTIME_WARNING" >&2; echo "MANA CAST BLOCKED"; echo "profile runner '$runner' has no CLI execution adapter; use its native runner"; runtime_finish failed; exit 1 ;;
  esac
  status=$?
  if [ "$status" -eq 0 ]; then runtime_emit profile.completed profile "$profile" completed "runner=$runner" "" false || true; runtime_finish completed; "$root/scripts/mana-learning.sh" --project-root "$project_root" collect >/dev/null 2>&1 || echo 'WARNING: learning-signal collection failed; execution completed without promotion' >&2; else runtime_emit profile.failed profile "$profile" failed "exitStatus=$status" "" false || true; runtime_finish failed; fi
  exit "$status"
fi
