#!/usr/bin/env bash
# Deterministic, local-only CTX-00 inventory.  It deliberately does not source
# the runtime: doing so could materialize project state or invoke a provider.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd -P)"
project_root=""
output=""

usage() {
  cat <<'USAGE'
Usage: scripts/mana-context-baseline.sh [--root <Mana repository>] [--project-root <project>] [--output <file>]

Writes the baseline JSON to standard output by default.  --output is the only
mode that writes a file; no project or .mana state is created otherwise.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root) root="${2:?--root requires a path}"; root="$(cd "$root" && pwd -P)"; shift 2 ;;
    --project-root) project_root="${2:?--project-root requires a path}"; project_root="$(cd "$project_root" && pwd -P)"; shift 2 ;;
    --output) output="${2:?--output requires a path}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$project_root" ] || project_root="$root"

for required in profiles skills scripts/run-profile.sh; do
  [ -e "$root/$required" ] || { echo "ERROR: not a Mana repository: missing $required" >&2; exit 2; }
done
command -v jq >/dev/null || { echo 'ERROR: jq is required' >&2; exit 2; }

bytes() { [ -f "$1" ] && wc -c < "$1" | tr -d ' ' || printf '0'; }
tokens() { awk -v n="$1" 'BEGIN { printf "%d", int((n + 3) / 4) }'; }
size_json() {
  local path="$1" label="$2" n
  n="$(bytes "$path")"
  jq -n --arg path "$label" --argjson bytes "$n" --argjson estimatedTokens "$(tokens "$n")" \
    '{path:$path,bytes:$bytes,estimatedTokens:$estimatedTokens,tokenEstimateMethod:"bytes_divided_by_4_estimate"}'
}

# The renderer prompt is generated in scripts/run-profile.sh.  This source
# segment is a reproducible static proxy; it is not represented as live usage.
rendered_prompt_size() {
  local n
  n="$(sed -n '/^prompt="$(cat <<PROMPT$/,/^PROMPT$/p' "$root/scripts/run-profile.sh" | wc -c | tr -d ' ')"
  jq -n --arg path 'scripts/run-profile.sh:prompt-template' --argjson bytes "$n" --argjson estimatedTokens "$(tokens "$n")" \
    '{path:$path,bytes:$bytes,estimatedTokens:$estimatedTokens,tokenEstimateMethod:"bytes_divided_by_4_estimate",note:"Static rendered-root-prompt template proxy; excludes runtime substitutions."}'
}

git_head=null; dirty=false; changes='[]'
if git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git_head="$(git -C "$root" rev-parse HEAD)"
  changes="$(git -C "$root" status --porcelain=v1 --untracked-files=all | LC_ALL=C sort | jq -Rsc 'split("\n") | map(select(length > 0))')"
  [ "$changes" = '[]' ] || dirty=true
fi

profiles='[]'
while IFS= read -r -d '' file; do
  id="${file##*/}"; id="${id%.yaml}"
  declared="$(awk -F': *' '$1 == "name" {print $2; exit}' "$file")"
  metadataStatus=valid; metadataError=null
  if [ -z "$declared" ]; then metadataStatus=malformed; metadataError='missing top-level name';
  elif [ "$declared" != "$id" ]; then metadataStatus=malformed; metadataError="top-level name does not match filename"; fi
  # Classification is conservative and records the source rule, rather than
  # claiming a provider capability.  Only the explicitly publish-capable PR
  # profile is external-write-capable in the current profile metadata.
  classification=read-only-analysis; rationale='profile defaults to read-only analysis'
  case "$id" in
    tutorial|mana-help) classification=deterministic-only; rationale='help/tutorial profile has no repository-analysis requirement' ;;
    story-start|story-ready-for-dev|team-planning|epic-analysis|dev-assist|service-knowledge-capture)
      classification=planning-synthesis; rationale='profile produces planning or synthesis artifacts' ;;
    requested-pr-review) classification=external-write-capable; rationale='profile has explicit, human-approved high-risk PR comment publication option' ;;
    api-test-validation|database-read-verification|gui-test-validation|testbook-validation)
      classification=write-capable; rationale='profile may execute locally write-capable validation tooling under its existing controls' ;;
  esac
  agents="$(awk '/^agents:[[:space:]]*$/ {on=1; next} on && /^[[:space:]]*-[[:space:]]*/ {sub(/^[[:space:]]*-[[:space:]]*/, ""); print; next} on && /^[^[:space:]]/ {exit}' "$file" | jq -Rsc 'split("\n") | map(select(length > 0))')"
  skills="$(awk '/^skills:[[:space:]]*$/ {on=1; next} on && /^[[:space:]]*-[[:space:]]*/ {sub(/^[[:space:]]*-[[:space:]]*/, ""); print; next} on && /^[^[:space:]]/ {exit}' "$file" | LC_ALL=C sort -u | jq -Rsc 'split("\n") | map(select(length > 0))')"
  baseline_skills="$(awk '/^skill_activation:[[:space:]]*$/ {section=1; next} section && /^[^[:space:]]/ {exit} section && /^[[:space:]]+baseline:[[:space:]]*$/ {on=1; next} on && /^[[:space:]]+conditional:/ {exit} on && /^[[:space:]]*-[[:space:]]*/ {sub(/^[[:space:]]*-[[:space:]]*/, ""); print}' "$file" | LC_ALL=C sort -u | jq -Rsc 'split("\n") | map(select(length > 0))')"
  core="$(awk '/^service_context:[[:space:]]*$/ {section=1; next} section && /^[^[:space:]]/ {exit} section && /^[[:space:]]+core_files:[[:space:]]*$/ {on=1; next} on && /^[[:space:]]+optional_files:/ {exit} on && /^[[:space:]]*-[[:space:]]*/ {sub(/^[[:space:]]*-[[:space:]]*/, ""); print}' "$file" | jq -Rsc 'split("\n") | map(select(length > 0))')"
  selected='[]'; while IFS= read -r agent; do
    selected="$(jq --arg p "agents/$agent/AGENT.md" '. + [{path:$p,bytes:0,estimatedTokens:0,tokenEstimateMethod:"bytes_divided_by_4_estimate"}]' <<<"$selected")"
  done < <(jq -r '.[]' <<<"$agents")
  # Fill selected agent/playbook sizes deterministically.
  selected="$(jq -c --arg root "$root" '. as $a | []' <<<"$selected")"
  while IFS= read -r agent; do
    for suffix in AGENT.md playbook.md; do
      p="$root/agents/$agent/$suffix"; n="$(bytes "$p")"
      selected="$(jq -c --arg path "agents/$agent/$suffix" --argjson bytes "$n" --argjson estimatedTokens "$(tokens "$n")" '. + [{path:$path,bytes:$bytes,estimatedTokens:$estimatedTokens,tokenEstimateMethod:"bytes_divided_by_4_estimate"}]' <<<"$selected")"
    done
  done < <(jq -r '.[]' <<<"$agents")
  skill_sizes='[]'; baseline_sizes='[]'; while IFS= read -r skill; do
    p="$(awk -v id="$skill" '$1=="-" && $2=="id:" {active=($3==id)} active && $1=="path:" {print $2; exit}' "$root/skills/index.yaml")"
    n="$(bytes "$root/$p")"
    skill_sizes="$(jq -c --arg id "$skill" --arg path "$p" --argjson bytes "$n" --argjson estimatedTokens "$(tokens "$n")" '. + [{id:$id,path:$path,bytes:$bytes,estimatedTokens:$estimatedTokens,tokenEstimateMethod:"bytes_divided_by_4_estimate"}]' <<<"$skill_sizes")"
  done < <(jq -r '.[]' <<<"$skills")
  baseline_sizes="$(jq --argjson ids "$baseline_skills" '[.[] | select(.id as $id | $ids | index($id))]' <<<"$skill_sizes")"
  service_sizes='[]'; while IFS= read -r core_file; do
    # Service Context is project-owned and may not exist in the requested project.
    service_path="$project_root/.mana/global/$core_file"
    if [ -f "$service_path" ]; then
      n="$(bytes "$service_path")"
      service_sizes="$(jq -c --arg path ".mana/global/$core_file" --argjson bytes "$n" --argjson estimatedTokens "$(tokens "$n")" '. + [{path:$path,status:"present",bytes:$bytes,estimatedTokens:$estimatedTokens,tokenEstimateMethod:"bytes_divided_by_4_estimate"}]' <<<"$service_sizes")"
    else
      service_sizes="$(jq -c --arg path ".mana/global/$core_file" '. + [{path:$path,status:"missing",bytes:null,estimatedTokens:null,tokenEstimateMethod:"not_measured"}]' <<<"$service_sizes")"
    fi
  done < <(jq -r '.[]' <<<"$core")
  pbytes="$(bytes "$file")"
  profile_obj="$(jq -n --arg id "$id" --arg declared "$declared" --arg classification "$classification" --arg rationale "$rationale" --arg status "$metadataStatus" --arg error "$metadataError" --argjson agents "$agents" --argjson skills "$skills" --argjson selected "$selected" --argjson baseline "$baseline_sizes" --argjson candidate "$skill_sizes" --argjson service "$service_sizes" --argjson yamlBytes "$pbytes" --argjson yamlTokens "$(tokens "$pbytes")" \
    '{id:$id,declaredName:$declared,metadataStatus:$status,metadataError:(if $error=="null" then null else $error end),classification:$classification,classificationRationale:$rationale,agents:$agents,staticContext:{profileYaml:{path:("profiles/"+$id+".yaml"),bytes:$yamlBytes,estimatedTokens:$yamlTokens,tokenEstimateMethod:"bytes_divided_by_4_estimate"},selectedAgentAndPlaybook:$selected,baselineSkillInstructions:$baseline,allProfileCandidateSkills:$candidate,serviceContextCoreFiles:$service}}')"
  profiles="$(jq -c --argjson x "$profile_obj" '. + [$x]' <<<"$profiles")"
done < <(find "$root/profiles" -maxdepth 1 -type f -name '*.yaml' -print0 | LC_ALL=C sort -z)

generated='[]'
for path in AGENTS.md CLAUDE.md .codex/instructions.md .codex/agents/mana-explorer.toml .codex/agents/mana-full-specialist.toml .codex/agents/mana-worker.toml; do
  n="$(bytes "$root/$path")"; status=present; [ -f "$root/$path" ] || status=missing
  generated="$(jq -c --arg path "$path" --arg status "$status" --argjson bytes "$n" --argjson estimatedTokens "$(tokens "$n")" '. + [{path:$path,status:$status,bytes:$bytes,estimatedTokens:$estimatedTokens,tokenEstimateMethod:"bytes_divided_by_4_estimate"}]' <<<"$generated")"
done

root_prompt="$(rendered_prompt_size)"
result="$(jq -n --arg schemaVersion 'mana.context-runtime.baseline/v1' --arg root "$root" --arg projectRoot "$project_root" --arg head "$git_head" --argjson dirty "$dirty" --argjson changes "$changes" --argjson rootPrompt "$root_prompt" --argjson profiles "$profiles" --argjson generated "$generated" \
  '{schemaVersion:$schemaVersion,baselineKind:"static-zero-token",repository:{root:$root,projectRoot:$projectRoot,developHead:(if $head=="null" then null else $head end),dirty:$dirty,dirtyEntries:$changes},providerCapabilities:{codex:"unknown",claude:"unknown",opencode:"unknown",note:"CTX-00 does not invoke or infer provider capabilities."},staticContext:{renderedRootPrompt:$rootPrompt,generatedProjectInstructionsAndProviderDefinitions:$generated},profiles:$profiles}')"

if [ -n "$output" ]; then
  mkdir -p "$(dirname "$output")"
  printf '%s\n' "$result" > "$output"
else
  printf '%s\n' "$result"
fi
