#!/usr/bin/env bash
set -u

usage() {
  cat <<'USAGE'
Usage:
  scripts/run-dependency-evidence.sh [options]

Collects local dependency/security evidence inventory without contacting remote
registries. It records manifests, lockfiles, and existing scanner reports under
the active Mana workspace.

Options:
  --project-root <path>  Target project root. Defaults to current directory.
  --output-dir <path>    Evidence output directory.
  --check                Check likely dependency files.
  --collect              Write dependency evidence summary.
  --help                 Show this help.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 2; }

root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"
output_dir=""
mode="check"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || fail "--project-root requires a path"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; [ -n "$output_dir" ] || fail "--output-dir requires a path"; shift 2 ;;
    --check|--collect) mode="${1#--}"; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done

project_root="$(cd "$project_root" && pwd)"
patterns='pom.xml|build.gradle|build.gradle.kts|settings.gradle|settings.gradle.kts|gradle.lockfile|package.json|package-lock.json|yarn.lock|pnpm-lock.yaml|dependency-check-report.*|npm-audit.*|owasp.*'
matches="$(find "$project_root" -path "$project_root/.git" -prune -o -path "$project_root/.mana" -prune -o -type f | rg "$patterns" || true)"

if [ "$mode" = "check" ]; then
  if [ -n "$matches" ]; then
    echo "Dependency evidence candidates found:"
    printf '%s\n' "$matches" | sed "s#^$project_root/##"
    exit 0
  fi
  echo "WARN: no dependency manifests, lockfiles, or scanner reports found" >&2
  exit 1
fi

if [ -z "$output_dir" ]; then
  active_file="$project_root/.mana/active-workspace"
  if [ -f "$active_file" ]; then
    active_relative="$(sed -n '1p' "$active_file")"
    workspace="$project_root/$active_relative"
  else
    workspace="$("$root/scripts/mana-workspace.sh" resolve --root "$project_root" --purpose dependency-evidence)"
  fi
  output_dir="$workspace/evidence/dependencies"
elif [ "${output_dir#/}" = "$output_dir" ]; then
  output_dir="$project_root/$output_dir"
fi

mkdir -p "$output_dir"
summary="$output_dir/dependency-summary.md"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
{
  echo "# Dependency Security Evidence"
  echo
  echo "- Generated at: \`$timestamp\`"
  echo "- Project root: \`$project_root\`"
  echo "- Remote registry contacted: \`no\`"
  echo
  echo "## Files"
  echo
  if [ -n "$matches" ]; then
    printf '%s\n' "$matches" | sort | while IFS= read -r file; do
      rel="${file#"$project_root"/}"
      echo "- \`$rel\`"
    done
  else
    echo "- _No dependency files found._"
  fi
  echo
  echo "## Guidance"
  echo
  echo "- Use project-approved scanners for CVE truth."
  echo "- Treat changed manifests or lockfiles as review evidence."
  echo "- Do not invent vulnerabilities from manifest presence alone."
} > "$summary"

echo "Dependency evidence written: $summary"
