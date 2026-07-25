#!/usr/bin/env bash
# Project-local learning signals. Candidates are observations for the existing
# learning-agent; this command has no promotion or governed-file write path.
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"; project_root="$(pwd)"; command=""; candidate_id=""; json=false; execution=""
usage() { cat <<'USAGE' >&2
Usage: mana learning candidates [--json]
       mana learning show <candidate-id> [--json]
       mana learning review <candidate-id>
       mana learning reject <candidate-id>
       mana learning archive <candidate-id>
USAGE
}
escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r/\\r/g; s/\n/\\n/g'; }
safe() { case "${1,,}" in *token*|*secret*|*password*|*credential*|*authorization*|*bearer*|*api[_-]key*) return 1;; *) return 0;; esac; }
candidate_dir() { printf '%s/.mana/learning/candidates' "$project_root"; }
candidate_file() { printf '%s/%s.json' "$(candidate_dir)" "$1"; }
id_ok() { printf '%s' "$1" | grep -Eq '^learning-[0-9a-f]{8}$'; }
field() { sed -n "s/.*\"$2\":\"\([^\"]*\)\".*/\1/p" "$1" | head -n 1; }
stale() { local timestamp="$1" cutoff; cutoff="$(date -u -d '90 days ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-90d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)"; [ -n "$cutoff" ] && [ "$timestamp" \< "$cutoff" ]; }

collect() {
  local events="$project_root/.mana/runtime/events" dir key category observation event_id execution_id timestamp profile destination lines line count id file old_status status last executions references counter confidence
  [ -d "$events" ] || return 0; mkdir -p "$(candidate_dir)" || return 1
  lines="$(awk '
    function get(k,  x) { x=$0; sub(".*\\\"" k "\\\":\\\"", "", x); sub("\\\".*", "", x); return x }
    /"eventType":"evidence\.missing"/ {print "missing-evidence|Required evidence was missing|" get("eventId") "|" get("executionId") "|" get("timestamp") "|" get("profileId") "|Service Context update"}
    /"eventType":"guard\.triggered"/ {print "guard-activation|A governance guard was triggered|" get("eventId") "|" get("executionId") "|" get("timestamp") "|" get("profileId") "|guard proposal"}
    /"eventType":"model\.escalated"/ {print "model-escalation|Model escalation was required|" get("eventId") "|" get("executionId") "|" get("timestamp") "|" get("profileId") "|profile metadata update"}
    /"eventType":"tool\.blocked"/ {print "blocked-tool|A tool was blocked by policy|" get("eventId") "|" get("executionId") "|" get("timestamp") "|" get("profileId") "|behavioural eval"}
    /"eventType":"profile\.failed"/ {print "execution-failure|A profile execution failed|" get("eventId") "|" get("executionId") "|" get("timestamp") "|" get("profileId") "|known pitfall"}
  ' "$events"/*.jsonl 2>/dev/null | sort -u)"
  [ -n "$lines" ] || return 0
  while IFS='|' read -r category observation event_id execution_id timestamp profile destination; do
    [ -n "$event_id" ] || continue; safe "$observation $profile" || continue
    key="$category|$profile|$observation"; id="learning-$(printf '%s' "$key" | cksum | awk '{printf "%08x", $1}')"; file="$(candidate_file "$id")"
    count="$(printf '%s\n' "$lines" | awk -F'|' -v c="$category" -v p="$profile" -v o="$observation" '$1==c && $2==o && $6==p {n++} END {print n+0}')"
    executions="$(printf '%s\n' "$lines" | awk -F'|' -v c="$category" -v p="$profile" -v o="$observation" '$1==c && $2==o && $6==p {print $4}' | sort -u | paste -sd, -)"
    references="$(printf '%s\n' "$lines" | awk -F'|' -v c="$category" -v p="$profile" -v o="$observation" '$1==c && $2==o && $6==p {print $3}' | sort -u | paste -sd, -)"
    last="$(printf '%s\n' "$lines" | awk -F'|' -v c="$category" -v p="$profile" -v o="$observation" '$1==c && $2==o && $6==p {print $5}' | sort | tail -n 1)"
    status="candidate"; [ -f "$file" ] && status="$(field "$file" status)"; case "$status" in rejected|archived) continue;; esac
    case "$count" in 1) confidence=low;; 2) confidence=medium;; *) confidence=high;; esac
    counter="No counter-evidence recorded in auditable runtime events"; grep -q '"eventType":"profile.completed"' "$events"/*.jsonl 2>/dev/null && counter="At least one execution completed; human review must assess materiality"
    printf '{"schemaVersion":"1","candidateId":"%s","projectScope":"%s","observation":"%s","category":"%s","evidenceReferences":["%s"],"executions":["%s"],"recurrenceCount":%s,"confidence":"%s","possibleImpact":"Review recurring operational friction before promotion.","counterEvidence":"%s","suggestedDestination":"%s","status":"candidate","lastObservedAt":"%s","stale":%s}\n' \
      "$id" "$(escape "$profile")" "$(escape "$observation")" "$category" "$(escape "$references")" "$(escape "$executions")" "$count" "$confidence" "$(escape "$counter")" "$(escape "$destination")" "$last" "$(stale "$last" && echo true || echo false)" > "$file"
  done <<EOF
$lines
EOF
}

while [ "$#" -gt 0 ]; do case "$1" in --project-root) project_root="${2:-}"; shift 2;; --json) json=true; shift;; --execution) execution="${2:-}"; shift 2;; --help|-h) usage; exit 0;; candidates|show|review|reject|archive|collect) [ -z "$command" ] || { usage; exit 2; }; command="$1"; shift;; *) [ -z "$candidate_id" ] || { usage; exit 2; }; candidate_id="$1"; shift;; esac; done
[ -n "$command" ] || { usage; exit 2; }
case "$command" in
  collect) collect; exit 0 ;;
  candidates)
    collect
    files="$(find "$(candidate_dir)" -maxdepth 1 -name 'learning-*.json' -type f 2>/dev/null | sort)"
    if [ "$json" = true ]; then printf '{"candidates":['; first=true; while IFS= read -r f; do [ -n "$f" ] || continue; "$first" || printf ','; first=false; tr -d '\n' < "$f"; done <<EOF
$files
EOF
      printf ']}\n'; else echo 'MANA LEARNING CANDIDATES'; while IFS= read -r f; do [ -n "$f" ] || continue; printf '%s — %s (%s)\n' "$(field "$f" candidateId)" "$(field "$f" observation)" "$(field "$f" confidence)"; done <<EOF
$files
EOF
    fi ;;
  show)
    id_ok "$candidate_id" || { echo 'ERROR: invalid candidate id' >&2; exit 2; }; f="$(candidate_file "$candidate_id")"; [ -f "$f" ] || { echo "ERROR: candidate not found: $candidate_id" >&2; exit 1; }; [ "$json" = true ] && cat "$f" || { echo 'MANA LEARNING CANDIDATE'; cat "$f"; } ;;
  review)
    id_ok "$candidate_id" || { echo 'ERROR: invalid candidate id' >&2; exit 2; }; f="$(candidate_file "$candidate_id")"; [ -f "$f" ] || { echo "ERROR: candidate not found: $candidate_id" >&2; exit 1; }; mkdir -p "$project_root/.mana/learning/reviews"; artifact="$project_root/.mana/learning/reviews/$candidate_id-review.md"; { echo "# Learning-Agent Review: $candidate_id"; echo; printf '%s\n' "- Candidate: \`$candidate_id\`" "- Status: human review required" "- Promotion: not performed" "- Evidence: \`$(field "$f" evidenceReferences)\`"; echo; echo 'The learning-agent must validate recurrence, counter-evidence, scope, and accountable-owner approval before any separately executed promotion.'; } > "$artifact"; echo "Learning-agent review artifact: $artifact" ;;
  reject|archive)
    id_ok "$candidate_id" || { echo 'ERROR: invalid candidate id' >&2; exit 2; }; f="$(candidate_file "$candidate_id")"; [ -f "$f" ] || { echo "ERROR: candidate not found: $candidate_id" >&2; exit 1; }; sed "s/\"status\":\"candidate\"/\"status\":\"$command\"/" "$f" > "$f.tmp" && mv "$f.tmp" "$f"; echo "Candidate $candidate_id marked $command" ;;
esac
