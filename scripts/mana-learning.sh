#!/usr/bin/env bash
# Project-local learning signals. Candidates are observations; no command here
# promotes or changes governed knowledge.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"; project_root="$(pwd)"; command=""; candidate_id=""; json=false
. "$root/scripts/lib/json.sh"
usage() { cat <<'USAGE' >&2
Usage: mana learning candidates [--json]
       mana learning show <candidate-id> [--json]
       mana learning review <candidate-id>
       mana learning reject <candidate-id>
       mana learning archive <candidate-id>
       mana learning collect
USAGE
}
fail() { echo "ERROR: $*" >&2; exit 1; }
candidate_dir() { printf '%s/.mana/learning/candidates' "$project_root"; }
candidate_file() { printf '%s/%s.json' "$(candidate_dir)" "$1"; }
id_ok() { printf '%s' "$1" | grep -Eq '^learning-[0-9a-f]{8}$'; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
safe() { case "${1,,}" in *token*|*secret*|*password*|*credential*|*authorization*|*bearer*|*api[_-]key*) return 1;; *) return 0;; esac; }
validate_candidate() { mana_json_valid_object "$1" && jq -e '.schemaVersion == "2" and (.candidateId|type == "string") and (.status|IN("candidate","reviewed","rejected","archived")) and (.evidenceReferences|type == "array") and (.executions|type == "array") and all(.evidenceReferences[]; type == "string") and all(.executions[]; type == "string")' "$1" >/dev/null || fail "malformed candidate JSON: $1"; }
candidate_status() { validate_candidate "$1"; jq -r .status "$1"; }
stale() { local timestamp="$1" cutoff; cutoff="$(date -u -d '90 days ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-90d +%Y-%m-%dT%H:%M:%SZ)"; [ "$timestamp" \< "$cutoff" ]; }
write_candidate() { local file="$1" payload="$2"; printf '%s\n' "$payload" > "$file.tmp" && mv "$file.tmp" "$file"; }

collect() {
  local events lines category observation event_id execution_id timestamp profile destination key id file old status count refs execs last confidence counter created review_artifact payload
  [ -d "$project_root/.mana/runtime/events" ] || return 0; mkdir -p "$(candidate_dir)"
  # Runtime events are JSONL, parsed as JSON rather than with scalar sed.
  lines="$(find "$project_root/.mana/runtime/events" -type f -name '*.jsonl' -print 2>/dev/null | LC_ALL=C sort | while IFS= read -r f; do jq -r 'select(type=="object") | select(.eventType == "evidence.missing" or .eventType == "guard.triggered" or .eventType == "model.escalated" or .eventType == "tool.blocked" or .eventType == "profile.failed") | [(.eventType | gsub("\\."; "-")), .eventId, .executionId, .timestamp, .profileId] | @tsv' "$f"; done | awk -F'\t' '{ c=$1; sub(/^evidence-missing$/, "missing-evidence", c); sub(/^guard-triggered$/, "guard-activation", c); sub(/^model-escalated$/, "model-escalation", c); sub(/^tool-blocked$/, "blocked-tool", c); sub(/^profile-failed$/, "execution-failure", c); obs=(c=="missing-evidence"?"Required evidence was missing":c=="guard-activation"?"A governance guard was triggered":c=="model-escalation"?"Model escalation was required":c=="blocked-tool"?"A tool was blocked by policy":"A profile execution failed"); dest=(c=="missing-evidence"?"Service Context update":c=="guard-activation"?"guard proposal":c=="model-escalation"?"profile metadata update":c=="blocked-tool"?"behavioural eval":"known pitfall"); print c "|" obs "|" $2 "|" $3 "|" $4 "|" $5 "|" dest }' | LC_ALL=C sort -u)"
  [ -n "$lines" ] || return 0
  while IFS='|' read -r category observation event_id execution_id timestamp profile destination; do
    [ -n "$event_id" ] && safe "$observation $profile" || continue
    key="$category|$profile|$observation"; id="learning-$(printf '%s' "$key" | cksum | awk '{printf "%08x", $1}')"; file="$(candidate_file "$id")"
    count="$(printf '%s\n' "$lines" | awk -F'|' -v c="$category" -v p="$profile" -v o="$observation" '$1==c && $2==o && $6==p {n++} END {print n+0}')"
    refs="$(printf '%s\n' "$lines" | awk -F'|' -v c="$category" -v p="$profile" -v o="$observation" '$1==c && $2==o && $6==p {print $3}' | mana_json_array)"
    execs="$(printf '%s\n' "$lines" | awk -F'|' -v c="$category" -v p="$profile" -v o="$observation" '$1==c && $2==o && $6==p {print $4}' | mana_json_array)"
    last="$(printf '%s\n' "$lines" | awk -F'|' -v c="$category" -v p="$profile" -v o="$observation" '$1==c && $2==o && $6==p {print $5}' | LC_ALL=C sort | tail -n 1)"
    status=candidate; created="$(now)"; review_artifact=null
    if [ -f "$file" ]; then
      status="$(candidate_status "$file")"; case "$status" in rejected|archived) continue;; esac
      created="$(jq -r .createdAt "$file")"; review_artifact="$(jq -c '.reviewArtifact // null' "$file")"
    fi
    case "$count" in 1) confidence=low;; 2) confidence=medium;; *) confidence=high;; esac
    counter='No counter-evidence recorded in auditable runtime events'; find "$project_root/.mana/runtime/events" -type f -name '*.jsonl' -exec grep -l '"eventType":"profile.completed"' {} + >/dev/null 2>&1 && counter='At least one execution completed; human review must assess materiality'
    payload="$(jq -cn --arg id "$id" --arg scope "$profile" --arg obs "$observation" --arg category "$category" --argjson refs "$refs" --argjson execs "$execs" --argjson count "$count" --arg confidence "$confidence" --arg counter "$counter" --arg destination "$destination" --arg status "$status" --arg created "$created" --arg updated "$(now)" --arg last "$last" --argjson stale "$(stale "$last" && echo true || echo false)" --argjson review "$review_artifact" '{schemaVersion:"2",candidateId:$id,projectScope:$scope,observation:$obs,category:$category,evidenceReferences:$refs,executions:$execs,recurrenceCount:$count,confidence:$confidence,possibleImpact:"Review recurring operational friction before promotion.",counterEvidence:$counter,suggestedDestination:$destination,status:$status,createdAt:$created,updatedAt:$updated,lastObservedAt:$last,stale:$stale} + (if $review != null then {reviewArtifact:$review} else {} end)')"
    write_candidate "$file" "$payload"
  done <<EOF
$lines
EOF
}

transition() {
  local target="$1" file="$2" current updated
  current="$(candidate_status "$file")"
  case "$current:$target" in candidate:reviewed|candidate:rejected|candidate:archived|reviewed:rejected|reviewed:archived) ;; *) fail "invalid lifecycle transition: $current -> $target (terminal candidates cannot be collected or changed)";; esac
  updated="$(jq -c --arg target "$target" --arg at "$(now)" '.status=$target | .updatedAt=$at | if $target == "reviewed" then .reviewedAt=$at elif $target == "rejected" then .rejectedAt=$at else .archivedAt=$at end' "$file")"; write_candidate "$file" "$updated"
}

while [ "$#" -gt 0 ]; do case "$1" in --project-root) project_root="${2:-}"; shift 2;; --json) json=true; shift;; --help|-h) usage; exit 0;; candidates|show|review|reject|archive|collect) [ -z "$command" ] || { usage; exit 2; }; command="$1"; shift;; *) [ -z "$candidate_id" ] || { usage; exit 2; }; candidate_id="$1"; shift;; esac; done
[ -n "$command" ] || { usage; exit 2; }; mana_json_require || exit $?
case "$command" in
 collect) collect ;;
 candidates) collect; files="$(find "$(candidate_dir)" -maxdepth 1 -name 'learning-*.json' -type f 2>/dev/null | LC_ALL=C sort)"; while IFS= read -r f; do [ -z "$f" ] || validate_candidate "$f"; done <<EOF
$files
EOF
   if [ "$json" = true ]; then if [ -n "$files" ]; then jq -cs '{schemaVersion:"2",candidates:.}' $files; else printf '{"schemaVersion":"2","candidates":[]}\n'; fi; else echo 'MANA LEARNING CANDIDATES'; while IFS= read -r f; do [ -z "$f" ] || printf '%s — %s (%s; %s)\n' "$(jq -r .candidateId "$f")" "$(jq -r .observation "$f")" "$(jq -r .confidence "$f")" "$(jq -r .status "$f")"; done <<EOF
$files
EOF
   fi ;;
 show) id_ok "$candidate_id" || fail 'invalid candidate id'; f="$(candidate_file "$candidate_id")"; [ -f "$f" ] || fail "candidate not found: $candidate_id"; validate_candidate "$f"; [ "$json" = true ] && cat "$f" || { echo 'MANA LEARNING CANDIDATE'; cat "$f"; } ;;
 review) id_ok "$candidate_id" || fail 'invalid candidate id'; f="$(candidate_file "$candidate_id")"; [ -f "$f" ] || fail "candidate not found: $candidate_id"; current="$(candidate_status "$f")"; [ "$current" = candidate ] || [ "$current" = reviewed ] || fail "invalid lifecycle transition: $current -> reviewed"; mkdir -p "$project_root/.mana/learning/reviews"; artifact="$project_root/.mana/learning/reviews/$candidate_id-review.md"; { echo "# Learning-Agent Review: $candidate_id"; echo; echo '- Status: reviewed'; echo '- Promotion: not performed'; echo; echo '## Evidence references'; jq -r '.evidenceReferences[] | "- `" + . + "`"' "$f"; echo; echo '## Executions'; jq -r '.executions[] | "- `" + . + "`"' "$f"; } > "$artifact"; updated="$(jq -c --arg artifact ".mana/learning/reviews/$candidate_id-review.md" --arg at "$(now)" '.status="reviewed" | .reviewedAt=$at | .updatedAt=$at | .reviewArtifact=$artifact' "$f")"; write_candidate "$f" "$updated"; echo "Learning-agent review artifact: $artifact" ;;
 reject|archive) id_ok "$candidate_id" || fail 'invalid candidate id'; f="$(candidate_file "$candidate_id")"; [ -f "$f" ] || fail "candidate not found: $candidate_id"; [ "$command" = reject ] && target=rejected || target=archived; transition "$target" "$f"; echo "Candidate $candidate_id marked $target" ;;
esac
