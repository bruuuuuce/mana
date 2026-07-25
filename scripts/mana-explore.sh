#!/usr/bin/env bash
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"; project_root="$(pwd)"; question=""; json=false
usage() { echo 'Usage: mana explore "<question>" [--json]' >&2; }
while [ "$#" -gt 0 ]; do case "$1" in --project-root) project_root="${2:-}"; shift 2;; --json) json=true; shift;; --help|-h) usage; exit 0;; --*) echo "ERROR: unknown option: $1" >&2; exit 2;; *) [ -z "$question" ] || { echo 'ERROR: only one question is accepted' >&2; exit 2; }; question="$1"; shift;; esac; done
[ -n "$question" ] || { usage; exit 2; }
. "$root/scripts/lib/explorer-retrieval.sh"
explorer_retrieve "$project_root" "$question"
list_json() { local first=true item; printf '['; while IFS= read -r item; do [ -z "$item" ] && continue; "$first" || printf ','; first=false; printf '"%s"' "$(explorer_json_escape "$item")"; done <<EOF
$1
EOF
printf ']'; }
if [ "$json" = true ]; then
  printf '{"question":"%s","sufficiencyStatus":"%s","retrievalCycles":' "$(explorer_json_escape "$EXPLORER_QUESTION")" "$EXPLORER_STATUS"; list_json "$EXPLORER_CYCLES"; printf ',"relevantEvidence":'; list_json "$EXPLORER_EVIDENCE"; printf ',"rejectedEvidence":'; list_json "$EXPLORER_REJECTED"; printf ',"probablyModify":'; list_json "$EXPLORER_PROBABLY_MODIFY"; printf ',"inspectBeforeDeciding":'; list_json "$EXPLORER_INSPECT"; printf ',"doNotTouchUnlessApproved":'; list_json "$EXPLORER_DO_NOT_TOUCH"; printf ',"unresolvedEvidenceGaps":'; list_json "$EXPLORER_GAPS"; printf ',"recommendedNextAction":"%s"}\n' "$(explorer_json_escape "$EXPLORER_NEXT_ACTION")"
else
  echo 'MANA EXPLORER'; echo "Question: $EXPLORER_QUESTION"; echo "Sufficiency: $EXPLORER_STATUS"; echo 'Retrieval cycles:'; printf '%s\n' "$EXPLORER_CYCLES" | sed 's/|/ — /g'; echo 'Relevant evidence:'; printf '%s\n' "$EXPLORER_EVIDENCE"; echo 'Probably modify:'; printf '%s\n' "$EXPLORER_PROBABLY_MODIFY"; echo 'Inspect before deciding:'; printf '%s\n' "$EXPLORER_INSPECT"; [ -n "$EXPLORER_GAPS" ] && { echo 'Evidence gaps:'; printf '%s\n' "$EXPLORER_GAPS"; }; echo "Next action: $EXPLORER_NEXT_ACTION"
fi
