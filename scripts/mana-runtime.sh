#!/usr/bin/env bash
# Read-only inspection and bounded retention for repository-local Mana events.
set -u

project_root="$(pwd)"; json=false; retain_days="${MANA_RUNTIME_RETENTION_DAYS:-30}"; command=""; argument=""; dry_run=false
usage() { cat <<'USAGE'
Usage: mana runtime sessions [--json]
       mana runtime show <execution-id> [--json]
       mana runtime events <execution-id> [--json]
       mana runtime prune --dry-run [--retain-days <days>] [--json]
USAGE
}
while [ "$#" -gt 0 ]; do case "$1" in --project-root) project_root="${2:-}"; shift 2;; --json) json=true; shift;; --retain-days) retain_days="${2:-}"; shift 2;; --dry-run) dry_run=true; shift;; --help|-h) usage; exit 0;; *) if [ -z "$command" ]; then command="$1"; elif [ -z "$argument" ]; then argument="$1"; else echo "ERROR: unexpected argument: $1" >&2; exit 2; fi; shift;; esac; done
case "$command" in sessions|show|events|prune) ;; *) usage; exit 2;; esac
case "$retain_days" in *[!0-9]*|'') echo 'ERROR: --retain-days must be a non-negative integer' >&2; exit 2;; esac
runtime="$project_root/.mana/runtime"; events="$runtime/events"; sessions="$runtime/sessions"
json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
if [ "$command" = sessions ]; then
  list="$(find "$sessions" -maxdepth 1 -type f -name '*.json' -print 2>/dev/null | LC_ALL=C sort)"
  if [ "$json" = true ]; then printf '{"sessions":['; first=true; while IFS= read -r f; do [ -n "$f" ] || continue; "$first" || printf ','; first=false; cat "$f"; done <<EOF
$list
EOF
    printf ']}\n'; else [ -n "$list" ] && while IFS= read -r f; do [ -n "$f" ] && cat "$f"; done <<EOF
$list
EOF
  fi
elif [ "$command" = events ] || [ "$command" = show ]; then
  [ -n "${argument:-}" ] || { echo "ERROR: $command requires an execution id" >&2; exit 2; }
  case "$argument" in *[!A-Za-z0-9._-]*|'') echo 'ERROR: invalid execution id' >&2; exit 2;; esac
  file="$events/$argument.jsonl"; [ -f "$file" ] || { echo "ERROR: runtime execution not found: $argument" >&2; exit 1; }
  if [ "$json" = true ]; then printf '{"executionId":"%s","events":[' "$(json_escape "$argument")"; awk 'BEGIN { first=1 } { if (!first) printf ","; first=0; printf "%s", $0 } END { print "]}" }' "$file"; else cat "$file"; fi
else
  [ "${dry_run:-false}" = true ] || { echo 'ERROR: runtime prune requires --dry-run in this increment' >&2; exit 2; }
  candidates="$(find "$events" "$sessions" -type f \( -name '*.jsonl' -o -name '*.json' \) -mtime "+$retain_days" -print 2>/dev/null | LC_ALL=C sort)"
  if [ "$json" = true ]; then printf '{"dryRun":true,"retainDays":%s,"wouldPrune":[' "$retain_days"; first=true; while IFS= read -r f; do [ -n "$f" ] || continue; "$first" || printf ','; first=false; printf '"%s"' "$(json_escape "${f#$project_root/}")"; done <<EOF
$candidates
EOF
    printf ']}\n'; else echo 'MANA RUNTIME PRUNE DRY RUN'; [ -n "$candidates" ] && printf '%s\n' "$candidates" || echo 'No runtime files exceed retention.'; fi
fi
