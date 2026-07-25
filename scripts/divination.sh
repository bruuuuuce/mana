#!/usr/bin/env bash
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"; project_root="$(pwd)"; intent=""; explain=false; json=false
usage() { echo 'Usage: mana divination "<intent>" [--explain] [--json]' >&2; }
while [ "$#" -gt 0 ]; do case "$1" in --project-root) project_root="${2:-}"; shift 2;; --explain) explain=true; shift;; --json) json=true; shift;; --help|-h) usage; exit 0;; --*) echo "MANA MEDITATION"; echo "Unknown option: $1"; exit 2;; *) [ -z "$intent" ] || { echo "MANA MEDITATION"; echo "Only one intent is accepted."; exit 2; }; intent="$1"; shift;; esac; done
if [ -z "$intent" ] && [ ! -t 0 ]; then intent="$(cat)"; fi
# shellcheck source=lib/profile-metadata.sh
. "$root/scripts/lib/profile-metadata.sh"
# shellcheck source=lib/divination.sh
. "$root/scripts/lib/divination.sh"
divination_recommend "$root" "$project_root" "$intent"; result=$?
json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
json_list() { local first=true x; printf '['; while IFS= read -r x; do [ -z "$x" ] && continue; $first || printf ','; first=false; printf '"%s"' "$(json_escape "$x")"; done <<EOF
$1
EOF
printf ']'; }
json_reasons() { local first=true reason code points detail; printf '['; IFS=','; for reason in $1; do [ -z "$reason" ] && continue; code="${reason%%@*}"; points="${reason#*@}"; points="${points%%@*}"; detail="${reason#*@*@}"; $first || printf ','; first=false; printf '{"code":"%s","points":%s,"detail":"%s"}' "$(json_escape "$code")" "$points" "$(json_escape "$detail")"; done; unset IFS; printf ']'; }
json_candidates() { local first=true name score positive negative skills reasons; printf '['; while IFS='|' read -r name score positive negative skills reasons; do [ -z "$name" ] && continue; $first || printf ','; first=false; printf '{"profile":"%s","score":%s,"positiveSignals":' "$(json_escape "$name")" "$score"; json_list "$(printf '%s' "$positive" | sed 's/, /\n/g')"; printf ',"negativeSignals":'; json_list "$(printf '%s' "$negative" | sed 's/, /\n/g')"; printf ',"skills":'; json_list "$(printf '%s' "$skills" | tr ',' '\n')"; printf ',"reasons":'; json_reasons "$reasons"; printf '}'; done <<EOF
$DIVINATION_CANDIDATES
EOF
printf ']'; }
json_domains() { local first=true name state risk context; printf '['; while IFS='|' read -r name state risk context; do [ -z "$name" ] && continue; $first || printf ','; first=false; printf '{"id":"%s","signal":"%s","risk":"%s","contextFiles":' "$(json_escape "$name")" "$state" "$risk"; json_list "$(printf '%s' "$context" | tr ',' '\n')"; printf '}'; done <<EOF
$DIVINATION_DOMAINS
EOF
printf ']'; }
json_routing() { local first=true skill tier group; printf '['; while IFS='|' read -r skill tier group; do [ -z "$skill" ] && continue; $first || printf ','; first=false; printf '{"skill":"%s","tier":"%s","group":"%s"}' "$(json_escape "$skill")" "$tier" "$group"; done <<EOF
$DIVINATION_ROUTING
EOF
printf ']'; }
if [ "$json" = true ]; then
  printf '{"intent":"%s","status":"%s","recommendedProfile":' "$(json_escape "$DIVINATION_INTENT")" "${DIVINATION_STATUS:-error}"
  [ -n "$DIVINATION_PROFILE" ] && printf '"%s"' "$DIVINATION_PROFILE" || printf 'null'
  printf ',"profileFingerprint":'
  [ -n "${DIVINATION_PROFILE_FINGERPRINT:-}" ] && printf '"%s"' "$DIVINATION_PROFILE_FINGERPRINT" || printf 'null'
  printf ',"confidence":"%s","candidates":' "$DIVINATION_CONFIDENCE"; json_candidates; printf ',"domains":'; json_domains; printf ',"skills":'; json_list "$(printf '%s' "$DIVINATION_SKILLS" | tr ',' '\n')"; printf ',"modelRouting":'; json_routing; printf ',"humanGates":'; json_list "$DIVINATION_GATES"; printf ',"missingEvidence":'; json_list "$DIVINATION_MISSING"; printf ',"nextCommand":'
  [ -n "$DIVINATION_PROFILE" ] && printf '"mana cast %s"' "$DIVINATION_PROFILE" || printf 'null'
  printf ',"readOnly":true'; [ -n "$DIVINATION_ERROR" ] && printf ',"error":"%s"' "$(json_escape "$DIVINATION_ERROR")"; printf '}\n'; exit "$result"
fi
if [ "$result" -ne 0 ]; then echo 'MANA MEDITATION'; echo "$DIVINATION_ERROR"; exit "$result"; fi
echo 'MANA DIVINATION'; [ "$DIVINATION_STATUS" = ambiguous ] && echo 'The signs point to multiple profiles:' || echo 'The signs point to:'; [ -n "$DIVINATION_PROFILE" ] && echo "profile: $DIVINATION_PROFILE"; echo "confidence: $DIVINATION_CONFIDENCE"; echo "Domains detected: $(printf '%s' "$DIVINATION_DOMAINS" | cut -d'|' -f1 | tr '\n' ' ')"; echo "Recommended skills: ${DIVINATION_SKILLS//,/ }"; echo 'Suggested model routing:'; printf '%s\n' "$DIVINATION_ROUTING" | sed '/^$/d; s/|/ — /g'; [ -n "$DIVINATION_GATES" ] && { echo 'Human gates:'; printf '%s\n' "$DIVINATION_GATES"; }; [ -n "$DIVINATION_MISSING" ] && { echo 'Missing evidence:'; printf '%s\n' "$DIVINATION_MISSING"; }; [ -n "$DIVINATION_PROFILE" ] && echo "Next invocation: mana cast $DIVINATION_PROFILE"
if [ "$explain" = true ]; then echo 'Explanation:'; echo 'Candidates considered (name | score | positive signals | negative signals):'; printf '%s\n' "$DIVINATION_CANDIDATES"; echo "Ignored or unsupported terms: ${DIVINATION_IGNORED:-none}"; [ "$DIVINATION_STATUS" = ambiguous ] && echo 'Tie-breaking decision: equal scores are intentionally not broken; candidates remain ranked alphabetically.'; fi
echo 'No spell has been cast.'
