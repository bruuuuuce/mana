#!/usr/bin/env bash
set -u

usage() {
  cat <<'USAGE'
Usage:
  scripts/run-evidence-index.sh [options]

Builds a lightweight Markdown index of evidence artifacts in the active Mana
workspace so agents can read one file first and deep-load only what is needed.

Options:
  --project-root <path>  Target project root. Defaults to current directory.
  --workspace <path>     Explicit Mana workspace path.
  --help                 Show this help.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 2; }

root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"
workspace=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || fail "--project-root requires a path"; shift 2 ;;
    --workspace) workspace="${2:-}"; [ -n "$workspace" ] || fail "--workspace requires a path"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done

project_root="$(cd "$project_root" && pwd)"
if [ -z "$workspace" ]; then
  active_file="$project_root/.mana/active-workspace"
  if [ -f "$active_file" ]; then
    active_relative="$(sed -n '1p' "$active_file")"
    workspace="$project_root/$active_relative"
  else
    workspace="$("$root/scripts/mana-workspace.sh" resolve --root "$project_root" --purpose evidence-index)"
  fi
elif [ "${workspace#/}" = "$workspace" ]; then
  workspace="$project_root/$workspace"
fi

mkdir -p "$workspace/evidence"
index="$workspace/evidence/index.md"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

section() {
  title="$1"
  dir="$2"
  echo "## $title"
  echo
  if [ -d "$dir" ]; then
    find "$dir" -type f | sort | while IFS= read -r file; do
      rel="${file#"$project_root"/}"
      updated="$(date -r "$file" -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
      echo "- \`$rel\` — updated \`$updated\`"
    done
  else
    echo "- _No evidence found._"
  fi
  echo
}

{
  echo "# Mana Evidence Index"
  echo
  echo "- Workspace: \`${workspace#"$project_root"/}\`"
  echo "- Generated at: \`$timestamp\`"
  echo
  section "Jira" "$workspace/evidence/jira"
  section "Sonar" "$workspace/evidence/sonar"
  section "Dependencies" "$workspace/evidence/dependencies"
  section "Tests" "$workspace/tests"
  section "Validation" "$workspace/validation"
  section "PR" "$workspace/pr"
  echo "## Guidance"
  echo
  echo "- Read this index before deep-loading evidence artifacts."
  echo "- Treat missing evidence as a gap, not as proof of safety."
  echo "- Prefer summaries before raw logs."
} > "$index"

echo "Evidence index written: $index"
