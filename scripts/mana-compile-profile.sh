#!/usr/bin/env bash
# CTX-04 deterministic profile compiler. Authoritative framework sources are
# resolved beneath --root; caller-provided profile/catalog copies are forbidden.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd -P)"
profile=""
execution_id=""
project_root=""
run_directory=""
compiler_args=()

usage() {
  cat <<'USAGE'
Usage: scripts/mana-compile-profile.sh <profile> --execution-id <execution-id> [options]

Options:
  --static-signal <signal>     Host-derived declared activation signal (repeatable).
  --request-skill <skill>      Declared semantic activation request (repeatable).
  --deep-load-skill <skill>    Active skill body selected for deep loading (repeatable).
  --project-root <path>        Authorized root for an explicit manifest write.
  --run-directory <relative>   Write context-manifest-v1.json below this directory.
  --root <path>                Authoritative Mana framework root (fixture support).

Without --run-directory canonical JSON is printed to stdout and no project or
.mana state is created. Legacy fallback warnings are emitted on stderr only.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 2; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --execution-id) execution_id="${2:?--execution-id requires a value}"; shift 2 ;;
    --static-signal|--request-skill|--deep-load-skill)
      compiler_args+=("$1" "${2:?$1 requires a value}")
      shift 2
      ;;
    --project-root) project_root="${2:?--project-root requires a path}"; shift 2 ;;
    --run-directory) run_directory="${2:?--run-directory requires a path}"; shift 2 ;;
    --root) root="${2:?--root requires a path}"; root="$(cd "$root" && pwd -P)"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    --*) fail "unknown argument: $1" ;;
    *) [ -z "$profile" ] || fail "multiple profiles supplied: $profile and $1"; profile="$1"; shift ;;
  esac
done

[ -n "$profile" ] || { usage >&2; fail 'profile is required'; }
[ -n "$execution_id" ] || fail '--execution-id is required'
[ -z "$run_directory" ] || [ -n "$project_root" ] || fail '--run-directory requires --project-root'

tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-compile-profile.XXXXXX")"
tmp="$(cd "$tmp" && pwd -P)"
trap 'rm -rf "$tmp"' EXIT
manifest="$tmp/context-manifest-v1.json"
validated_manifest="$tmp/context-manifest-v1.validated.json"
validated_manifest_json=""

python3 "$root/scripts/lib/context-runtime.py" compile-context-manifest \
  "$root" "$profile" "$execution_id" "${compiler_args[@]}" > "$manifest"

validated_manifest_json="$(
  python3 "$root/scripts/lib/context-runtime.py" authoritative-materialize-context-manifest \
    "$manifest" "$root" "$profile" "$execution_id" "${compiler_args[@]}"
)"

if [ -n "$run_directory" ]; then
  project_root="$(cd "$project_root" && pwd -P)"
  printf '%s\n' "$validated_manifest_json" > "$validated_manifest"
  "$root/scripts/lib/context-runtime.sh" write-model context-manifest "$validated_manifest" \
    "$project_root" "$run_directory/context-manifest-v1.json"
else
  # Emit only the in-memory value returned by authoritative validation.
  printf '%s\n' "$validated_manifest_json"
fi
