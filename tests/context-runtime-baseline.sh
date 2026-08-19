#!/usr/bin/env bash
set -euo pipefail

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
baseline="$root/scripts/mana-context-baseline.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-context-baseline.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

before="$(git -C "$root" status --porcelain=v1)"
"$baseline" > "$tmp/one.json"
"$baseline" > "$tmp/two.json"
cmp -s "$tmp/one.json" "$tmp/two.json" || fail 'baseline JSON is not stable across repeated runs'
jq -e '
  .schemaVersion == "mana.context-runtime.baseline/v1" and
  .baselineKind == "static-zero-token" and
  (.providerCapabilities | (.codex == "unknown" and .claude == "unknown" and .opencode == "unknown")) and
  ([.profiles[].id] | length == (unique | length)) and
  ([.profiles[].classification] | all(. == "deterministic-only" or . == "read-only-analysis" or . == "planning-synthesis" or . == "write-capable" or . == "external-write-capable")) and
  ([.profiles[].staticContext.profileYaml.bytes] | all(. >= 0)) and
  ([.profiles[].staticContext.selectedAgentAndPlaybook[].bytes] | all(. > 0))
' "$tmp/one.json" >/dev/null || fail 'baseline does not satisfy its required static inventory contract'
jq -e --slurpfile corpus "$root/evals/context-runtime/baseline-corpus.json" '
  . as $baseline | $corpus[0].cases[] |
  . as $case |
  ($baseline.profiles[] | select(.id == $case.profile) | .classification) == $case.expectedClassification
' "$tmp/one.json" >/dev/null || fail 'benchmark corpus does not agree with the baseline inventory'

# A root and output path with spaces exercise path handling and explicit output.
space_root="$tmp/repository with spaces"
cp -R "$root" "$space_root"
"$baseline" --root "$space_root" --output "$tmp/output with spaces/baseline.json"
[ -f "$tmp/output with spaces/baseline.json" ] || fail 'explicit output path was not written'
jq -e '.profiles | length > 0' "$tmp/output with spaces/baseline.json" >/dev/null || fail 'space-path output is invalid JSON'

# Malformed metadata is represented in the inventory, not silently guessed.
printf 'trigger: malformed\nskills:\n- mana-usage-help\n' > "$space_root/profiles/malformed.yaml"
"$baseline" --root "$space_root" > "$tmp/malformed.json"
jq -e '.profiles[] | select(.id == "malformed" and .metadataStatus == "malformed" and .metadataError == "missing top-level name")' "$tmp/malformed.json" >/dev/null || fail 'malformed profile metadata was not recorded'

after="$(git -C "$root" status --porcelain=v1)"
[ "$before" = "$after" ] || fail 'baseline generation mutated the repository'
if rg -n '^[[:space:]]*(codex|claude|opencode|curl|wget|gh)([[:space:]]|$)' "$baseline" >/dev/null; then
  fail 'baseline helper contains provider or network invocation'
fi
echo 'Context Runtime CTX-00 baseline tests passed (deterministic, zero-token, no repository mutation)'
