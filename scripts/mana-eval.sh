#!/usr/bin/env bash
# Deterministic behavioural-evaluation runner.  It evaluates the governed
# execution plan and explicit fixture signals; it never invokes a model/runner.
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/profile-metadata.sh
. "$root/scripts/lib/profile-metadata.sh"
. "$root/scripts/lib/json.sh"
. "$root/scripts/lib/execution-plan.sh"
. "$root/scripts/lib/run-identity.sh"

project_root="$(pwd)"; command="run"; scenario=""; candidate=""; profile_filter=""; json=false
usage() { cat <<'USAGE'
Usage: mana eval run [<scenario>] [--profile <profile>] [--json]
       mana eval compare <baseline> <candidate> [--json]

Run performs deterministic, read-only plan checks and writes its result under
.mana/evaluations/results/. It does not invoke a model, tool, hook, or runner.
USAGE
}
fail() { echo "ERROR: $*" >&2; exit 2; }
escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r/\\r/g; s/\n/\\n/g'; }
jlist() { local first=true x; printf '['; while IFS= read -r x; do [ -n "$x" ] || continue; "$first" || printf ','; first=false; printf '"%s"' "$(escape "$x")"; done; printf ']'; }
revision() { git -C "$root" rev-parse --short HEAD 2>/dev/null || printf 'workspace'; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || fail '--project-root requires a path'; shift 2;;
    --profile) profile_filter="${2:-}"; [ -n "$profile_filter" ] || fail '--profile requires a profile'; shift 2;;
    --json) json=true; shift;; --help|-h) usage; exit 0;;
    run|compare) command="$1"; shift;;
    *) if [ -z "$scenario" ]; then scenario="$1"; elif [ "$command" = compare ] && [ -z "$candidate" ]; then candidate="$1"; else fail "unexpected argument: $1"; fi; shift;;
  esac
done
project_root="$(cd "$project_root" 2>/dev/null && pwd)" || fail "project root not found: $project_root"

profile_from_scenario() { sed -n 's/^\*\*Profile:\*\* `\([^`]*\)`.*/\1/p' "$1" | head -n1; }
scenario_version() { [ -f "$1/eval.yaml" ] && sed -n 's/^version:[[:space:]]*//p' "$1/eval.yaml" | head -n1 || printf '1'; }
# Read compact YAML assertions. Only the constrained schema below is accepted:
# assertions:\n#   - type: must_use_skill\n#     value: cross-service-contract
manifest_assertions() {
  awk '
    /^assertions:[[:space:]]*$/ { active=1; next }
    active && /^[^[:space:]]/ { exit }
    active && /^  - type:[[:space:]]*/ { if (type) print type "|" value; type=$0; sub(/^  - type:[[:space:]]*/, "", type); value=""; next }
    active && /^    value:[[:space:]]*/ { value=$0; sub(/^    value:[[:space:]]*/, "", value); next }
    END { if (type) print type "|" value }
  ' "$1/eval.yaml"
}
legacy_assertions() {
  # Existing frozen scenarios become plan-level checks without rewriting them.
  local file="$1/expected-findings.md" skill
  [ -f "$file" ] || return 0
  grep -q '^## required_gates' "$file" && printf 'must_require_gate|blocking_conditions\n'
  # Historic Markdown scenarios were written for manual semantic review. Keep
  # them runnable as a safe baseline boundary until maintainers add eval.yaml.
  printf 'must_not_modify|true\n'
}
profile_skills() { mana_profile_skills "$root/profiles/$1.yaml" | LC_ALL=C sort -u; }
profile_tools() {
  local agent
  while IFS= read -r agent; do
    awk '/^allowed_tools:/{a=1;next} a&&/^  - /{sub(/^  - /,"");print;next} a&&/^[^ ]/{exit}' "$root/agents/$agent/AGENT.md"
  done <<EOF
$(mana_profile_list "$root/profiles/$1.yaml" agents)
EOF
}
profile_artifacts() {
  local agent
  while IFS= read -r agent; do
    awk '/^outputs:/{a=1;next} a&&/^  - /{sub(/^  - /,"");print;next} a&&/^[^ ]/{exit}' "$root/agents/$agent/AGENT.md"
  done <<EOF
$(mana_profile_list "$root/profiles/$1.yaml" agents)
EOF
}
contains() { printf '%s\n' "$1" | grep -Fqx "$2"; }
run_scenario() {
  local dir="$1" id version profile assertions skills tools artifacts result_lines='' assertion_count=0 failed=0 line type value pass reason class reason_code
  id="$(basename "$dir")"; version="$(scenario_version "$dir")"; profile="$(profile_from_scenario "$dir/scenario.md")"
  [ -n "$profile" ] || { printf 'skipped|%s|scenario.md is not a profile behavioural scenario\n' "$id"; return; }
  [ -f "$root/profiles/$profile.yaml" ] || { printf 'invalid|%s|unknown profile %s\n' "$id" "$profile"; return; }
  mana_execution_plan "$root" "$root/profiles/$profile.yaml" || { printf 'invalid|%s|%s\n' "$id" "$MANA_PLAN_ERROR"; return; }
  skills="$MANA_PLAN_SKILLS"; tools="$MANA_PLAN_TOOLS"; artifacts="$MANA_PLAN_ARTIFACTS"
  if [ -f "$dir/eval.yaml" ]; then assertions="$(manifest_assertions "$dir")"; else assertions="$(legacy_assertions "$dir")"; fi
  [ -n "$assertions" ] || { printf 'invalid|%s|no assertions: add eval.yaml assertions or expected-findings.md\n' "$id"; return; }
  while IFS='|' read -r type value; do
    [ -n "$type" ] || continue; assertion_count=$((assertion_count + 1)); pass=true; reason=""; reason_code="PASS"; class=structural
    case "$type" in
      must_use_skill) contains "$skills" "$value" || { pass=false; reason="skill is not selected by profile"; reason_code=SKILL_NOT_SELECTED; };;
      must_not_use_tool) contains "$tools" "$value" && { pass=false; reason="tool is allowed by effective plan"; reason_code=TOOL_ALLOWED; } || reason="tool is not allowed";;
      must_require_gate) grep -Fqi "$value" "$root/profiles/$profile.yaml" || { pass=false; reason="required gate or blocker is absent"; reason_code=GATE_ABSENT; }; [ -n "$reason" ] || reason="gate or blocker is declared";;
      must_produce_artifact) contains "$artifacts" "$value" || { pass=false; reason="artifact is not declared by profile agents"; reason_code=ARTIFACT_UNDECLARED; };;
      must_stop_with) grep -Fqi "$value" "$root/profiles/$profile.yaml" || { pass=false; reason="stop condition is absent"; reason_code=STOP_CONDITION_ABSENT; };;
      must_not_modify) if [ "$value" != true ]; then pass=false; reason="must_not_modify only accepts true"; reason_code=INVALID_VALUE; elif [ -n "$MANA_PLAN_WRITE_REASON" ]; then pass=false; reason_code="${MANA_PLAN_WRITE_REASON%%|*}"; reason="${MANA_PLAN_WRITE_REASON#*|}"; else reason="The governed execution plan has no write skill or mutating allowed tool"; fi;;
      max_delegation_depth) [ "$value" -ge 1 ] 2>/dev/null || { pass=false; reason="Mana delegation depth is 1"; }; [ -n "$reason" ] || reason="configured maximum is 1";;
      max_retrieval_cycles) [ "$value" -ge 3 ] 2>/dev/null || { pass=false; reason="Mana explorer maximum is 3"; }; [ -n "$reason" ] || reason="configured maximum is 3";;
      must_flag) class=fixture-backed; grep -Fqx "$value" "$dir/fixture-signals.txt" 2>/dev/null || { pass=false; reason="fixture does not provide required risk signal"; reason_code=FIXTURE_SIGNAL_ABSENT; };;
      must_not_flag) class=fixture-backed; ! grep -Fqx "$value" "$dir/fixture-signals.txt" 2>/dev/null || { pass=false; reason="fixture provides forbidden risk signal"; reason_code=FIXTURE_SIGNAL_PRESENT; };;
      *) pass=false; reason="unsupported assertion type"; reason_code=UNSUPPORTED_ASSERTION;;
    esac
    [ "$pass" = true ] || failed=$((failed + 1))
    result_lines="${result_lines}${result_lines:+$'\n'}$type|$class|$value|$pass|$reason_code|$reason"
  done <<EOF
$assertions
EOF
  local status=passed; [ "$failed" -eq 0 ] || status=failed
  printf 'result|%s|%s|%s|%s|%s|%s\n%s\n' "$id" "$version" "$profile" "$status" "$assertion_count" "$failed" "$result_lines"
}
write_result() {
  local id="$1" version="$2" profile="$3" status="$4" count="$5" failed="$6" lines="$7" scenario_dir="$8" out dir rev project_rev run_id generated first=true type class value pass reason_code reason selected gates artifacts scenario_file profile_digest index_digest skills_digest agents_digest context_digest
  rev="$(revision)"; project_rev="$(mana_project_revision "$project_root")"; run_id="$(mana_run_id)"; generated="$(mana_generated_at)"; dir="$project_root/.mana/evaluations/results/$id/$project_rev"; mkdir -p "$dir"; out="$dir/$run_id.json"
  selected="$(profile_skills "$profile")"; artifacts="$(profile_artifacts "$profile" | LC_ALL=C sort -u)"; gates="$(grep -E '^human_approval_requirement: true|^  - .*approval' "$root/profiles/$profile.yaml" || true)"
  scenario_file="$([ -f "$scenario_dir/eval.yaml" ] && echo "$scenario_dir/eval.yaml" || echo "$scenario_dir/scenario.md")"; profile_digest="$(mana_digest_file "$root/profiles/$profile.yaml")"; index_digest="$(mana_digest_file "$root/skills/index.yaml")"; skills_digest="$(printf '%s\n' "$selected" | cksum | awk '{print $1 "-" $2}')"; agents_digest="$(mana_profile_list "$root/profiles/$profile.yaml" agents | LC_ALL=C sort | cksum | awk '{print $1 "-" $2}')"; context_digest="$(find "$project_root/.mana/global" -type f -print 2>/dev/null | LC_ALL=C sort | while IFS= read -r f; do printf '%s|%s\n' "${f#"$project_root/"}" "$(mana_digest_file "$f")"; done | cksum | awk '{print $1 "-" $2}')"
  { printf '{"schemaVersion":"2","evalRunnerSchemaVersion":"2","runId":"%s","generatedAt":"%s","manaRevision":"%s","projectRevision":"%s","projectWorkingTreeDirty":%s,"scenarioId":"%s","scenarioVersion":"%s","scenarioDigest":"%s","profileDigest":"%s","skillIndexDigest":"%s","selectedSkillsDigest":"%s","selectedAgentsDigest":"%s","serviceContextDigest":"%s","profile":"%s","status":"%s","pass":%s,"durationMs":0,"modelRouting":[],"runtimeWarnings":[],"evidenceReferences":' "$(escape "$run_id")" "$(escape "$generated")" "$(escape "$rev")" "$(escape "$project_rev")" "$(mana_project_dirty "$project_root")" "$(escape "$id")" "$(escape "$version")" "$(mana_digest_file "$scenario_file")" "$profile_digest" "$index_digest" "$skills_digest" "$agents_digest" "$context_digest" "$(escape "$profile")" "$status" "$([ "$status" = passed ] && printf true || printf false)"
    printf '["profiles/%s.yaml"]' "$(escape "$profile")"; printf ',"selectedSkills":'; jlist <<<"$selected"; printf ',"humanGates":'; jlist <<<"$gates"; printf ',"expectedEvidence":'; jlist <<<"$artifacts"; printf ',"assertions":['
    while IFS='|' read -r type class value pass reason_code reason; do [ -n "$type" ] || continue; "$first" || printf ','; first=false; printf '{"type":"%s","class":"%s","value":"%s","pass":%s,"reasonCode":"%s","reason":"%s"}' "$(escape "$type")" "$(escape "$class")" "$(escape "$value")" "$pass" "$(escape "$reason_code")" "$(escape "$reason")"; done <<EOF
$lines
EOF
    printf ']}'$'\n'; } > "$out"; cp "$out" "$dir/latest.json"
  printf '%s\n' "$out"
}
compare() {
  local a="$1" b="$2"; [ -f "$a" ] || fail "baseline not found: $a"; [ -f "$b" ] || fail "candidate not found: $b"
  local ap bp as bs av bv field_a field_b
  ap="$(grep -o '"pass":\(true\|false\)' "$a" | head -n1 | cut -d: -f2)"; bp="$(grep -o '"pass":\(true\|false\)' "$b" | head -n1 | cut -d: -f2)"
  as="$(sed -n 's/.*"scenarioId":"\([^"]*\)".*/\1/p' "$a" | head -n1)"; bs="$(sed -n 's/.*"scenarioId":"\([^"]*\)".*/\1/p' "$b" | head -n1)"
  av="$(sed -n 's/.*"scenarioVersion":"\([^"]*\)".*/\1/p' "$a" | head -n1)"; bv="$(sed -n 's/.*"scenarioVersion":"\([^"]*\)".*/\1/p' "$b" | head -n1)"
  [ "$as" = "$bs" ] || fail 'baseline and candidate are for different scenarios'
  local regression=false improvement=false; [ "$ap" = true ] && [ "$bp" = false ] && regression=true; [ "$ap" = false ] && [ "$bp" = true ] && improvement=true
  field_a="$(grep -o '"humanGates":\[[^]]*\]' "$a" | head -n1)"; field_b="$(grep -o '"humanGates":\[[^]]*\]' "$b" | head -n1)"; changed_gates=false; [ "$field_a" = "$field_b" ] || changed_gates=true
  field_a="$(grep -o '"selectedSkills":\[[^]]*\]' "$a" | head -n1)"; field_b="$(grep -o '"selectedSkills":\[[^]]*\]' "$b" | head -n1)"; changed_skills=false; [ "$field_a" = "$field_b" ] || changed_skills=true
  field_a="$(grep -o '"expectedEvidence":\[[^]]*\]' "$a" | head -n1)"; field_b="$(grep -o '"expectedEvidence":\[[^]]*\]' "$b" | head -n1)"; changed_evidence=false; [ "$field_a" = "$field_b" ] || changed_evidence=true
  stale=false; [ "$av" = "$bv" ] || stale=true
  if [ "$json" = true ]; then printf '{"scenarioId":"%s","baselinePass":%s,"candidatePass":%s,"newlyFailing":%s,"newlyPassing":%s,"staleScenarioVersion":%s,"changedWarnings":false,"changedHumanGates":%s,"changedSkills":%s,"changedModelRouting":false,"changedEvidenceOutputs":%s}\n' "$(escape "$as")" "$ap" "$bp" "$regression" "$improvement" "$stale" "$changed_gates" "$changed_skills" "$changed_evidence"; else echo 'MANA EVAL COMPARISON'; echo "scenario: $as"; echo "baseline: $ap"; echo "candidate: $bp"; [ "$stale" = true ] && echo "stale scenario version: $av -> $bv"; [ "$regression" = true ] && echo 'newly failing: yes'; [ "$improvement" = true ] && echo 'newly passing: yes'; [ "$regression" = false ] && [ "$improvement" = false ] && echo 'No pass/fail regression.'; fi
}
if [ "$command" = compare ]; then [ -n "$scenario" ] || fail 'compare requires a baseline result path'; [ -n "$candidate" ] || fail 'compare requires a candidate result path'; compare "$scenario" "$candidate"; exit 0; fi

base="$root/evals/scenarios"; [ -d "$base" ] || fail "eval scenarios missing: $base"
dirs=""; if [ -n "$scenario" ]; then if [ -d "$scenario" ]; then dirs="$(cd "$scenario" && pwd)"; elif [ -d "$base/$scenario" ]; then dirs="$base/$scenario"; else fail "scenario not found: $scenario"; fi; else dirs="$(find "$base" -mindepth 1 -maxdepth 1 -type d -print | LC_ALL=C sort)"; fi
results=''; overall=true
while IFS= read -r dir; do
  [ -n "$dir" ] || continue; record="$(run_scenario "$dir")"; kind="${record%%|*}"; rest="${record#*|}"
  if [ "$kind" = skipped ]; then continue; fi
  if [ "$kind" = invalid ]; then echo "ERROR: ${rest#*|}" >&2; overall=false; continue; fi
  header="$(printf '%s\n' "$record" | head -n1)"; IFS='|' read -r _ id version profile status count failed <<EOF
$header
EOF
  [ -z "$profile_filter" ] || [ "$profile" = "$profile_filter" ] || continue
  lines="$(printf '%s\n' "$record" | sed '1d')"; out="$(write_result "$id" "$version" "$profile" "$status" "$count" "$failed" "$lines" "$dir")"; results="${results}${results:+$'\n'}$out"; [ "$status" = passed ] || overall=false
done <<EOF
$dirs
EOF
if [ "$json" = true ]; then printf '{"schemaVersion":"2","status":"%s","results":' "$([ "$overall" = true ] && printf passed || printf failed)"; jlist <<<"$results"; printf ',"repositoryModified":false,"manaStateWritten":true,"telemetryWritten":false,"runnerInvoked":false,"externalToolInvoked":false}\n'; else echo 'MANA EVAL'; printf '%s\n' "$results"; [ "$overall" = true ] && echo 'All deterministic assertions passed.' || echo 'One or more deterministic assertions failed.'; fi
[ "$overall" = true ]
