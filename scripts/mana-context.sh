#!/usr/bin/env bash
set -u

root="$(cd "$(dirname "$0")/.." && pwd)"
. "$root/scripts/lib/user-context.sh"

usage() {
  cat <<'USAGE'
Usage:
  scripts/mana-context.sh status [--json]
  scripts/mana-context.sh refresh [--json]
  scripts/mana-context.sh path [--source]

Options:
  --project-root <path>  Target project root. Defaults to current directory.
  --json                 Emit stable JSON for status or refresh.
  --source               With path, print the configured external source path.

`path` prints the generated project-local path by default. `path --source`
explicitly prints the personal external source path and fails when unconfigured.
USAGE
}

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r/\\r/g; s/\n/\\n/g'; }
fail() { echo "ERROR: $*" >&2; exit 2; }

command="${1:-}"
[ -n "$command" ] || { usage; exit 2; }
shift
project_root="$(pwd)"
json=false
show_source=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || fail "--project-root requires a path"; shift 2 ;;
    --json) json=true; shift ;;
    --source) show_source=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done
[ -d "$project_root" ] || fail "project root not found: $project_root"
project_root="$(cd "$project_root" && pwd)"

render_json() {
  printf '{"configured":%s,"configSource":"%s","sourceUsable":%s,"materialized":%s,"freshness":"%s","fileCount":%s,"skippedCount":%s,"generatedPath":"%s"' \
    "$MANA_UC_CONFIGURED" "$MANA_UC_CONFIG_SOURCE" "$MANA_UC_SOURCE_USABLE" "$MANA_UC_MATERIALIZED" \
    "$MANA_UC_FRESHNESS" "${MANA_UC_FILE_COUNT:-0}" "${MANA_UC_SKIPPED_COUNT:-0}" \
    "$(json_escape "$project_root/.mana/user-context")"
  [ -z "$MANA_UC_ERROR" ] || printf ',"error":"%s"' "$(json_escape "$MANA_UC_ERROR")"
  printf '}\n'
}

render_status() {
  echo "User Context: $([ "$MANA_UC_CONFIGURED" = true ] && echo configured || echo not configured)"
  echo "Configuration source: $MANA_UC_CONFIG_SOURCE"
  echo "Source usable: $MANA_UC_SOURCE_USABLE"
  echo "Local materialization: $MANA_UC_MATERIALIZED"
  echo "Freshness: $MANA_UC_FRESHNESS"
  echo "Files: ${MANA_UC_FILE_COUNT:-0} included, ${MANA_UC_SKIPPED_COUNT:-0} skipped"
  [ -z "$MANA_UC_ERROR" ] || echo "Problem: $MANA_UC_ERROR"
}

case "$command" in
  status)
    mana_user_context_status "$project_root"
    if [ "$json" = true ]; then render_json; else render_status; fi
    ;;
  refresh)
    if mana_user_context_refresh "$project_root"; then result=0; else result=$?; fi
    if [ "$json" = true ]; then render_json; else render_status; fi
    exit "$result"
    ;;
  path)
    [ "$json" = false ] || fail "--json is not supported by path"
    if [ "$show_source" = true ]; then
      mana_user_context_resolve_config || fail "$MANA_UC_ERROR"
      [ "$MANA_UC_CONFIGURED" = true ] || fail "User Context is not configured"
      printf '%s\n' "$MANA_UC_SOURCE"
    else
      printf '%s\n' "$project_root/.mana/user-context"
    fi
    ;;
  help|--help|-h) usage ;;
  *) fail "unknown command: $command" ;;
esac
