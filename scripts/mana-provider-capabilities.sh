#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/provider-capabilities.sh
. "$root/scripts/lib/provider-capabilities.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/mana-provider-capabilities.sh <codex|claude|opencode> [options]

Options:
  --binary <path-or-name>  Probe this provider executable instead of the default.
  --fixture <directory>    Read deterministic version/help/config probe fixtures.
  --human                  Render a compact table instead of canonical JSON.
  -h, --help               Show this help.

The command makes no model call, stores no cache, and does not create .mana.
JSON is the canonical provider-neutral contract.
USAGE
}

[ "$#" -gt 0 ] || { usage >&2; exit 2; }
provider="$1"
shift
source=live
location=""
human=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --binary)
      [ "$source" = live ] || { echo 'ERROR: --binary and --fixture are mutually exclusive' >&2; exit 2; }
      location="${2:-}"
      [ -n "$location" ] || { echo 'ERROR: --binary requires a value' >&2; exit 2; }
      shift 2
      ;;
    --fixture)
      [ -z "$location" ] || { echo 'ERROR: --binary and --fixture are mutually exclusive' >&2; exit 2; }
      source=fixture
      location="${2:-}"
      [ -n "$location" ] || { echo 'ERROR: --fixture requires a directory' >&2; exit 2; }
      shift 2
      ;;
    --human) human=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

report="$(mana_provider_capabilities_report "$provider" "$source" "$location")" || exit $?
if [ "$human" = false ]; then
  printf '%s\n' "$report"
  exit 0
fi
printf 'Provider: %s %s (%s probe)\n' \
  "$(jq -r .provider <<<"$report")" \
  "$(jq -r .providerVersion <<<"$report")" \
  "$(jq -r .probeSource <<<"$report")"
jq -r '.capabilities | to_entries[] | [.key,.value.status,(.value.evidence|join(","))] | @tsv' <<<"$report" |
  while IFS=$'\t' read -r name status evidence; do
    printf '%-36s %-11s %s\n' "$name" "$status" "$evidence"
  done
