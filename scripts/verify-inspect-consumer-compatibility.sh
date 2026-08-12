#!/usr/bin/env bash
# Deterministic, zero-token C00 producer/consumer inspect compatibility gate.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
familiar=""
usage() { echo "Usage: scripts/verify-inspect-consumer-compatibility.sh [--familiar-root <path>]"; }
while [ "$#" -gt 0 ]; do
  case "$1" in --familiar-root) familiar="${2:-}"; [ -n "$familiar" ] || { echo 'ERROR: --familiar-root requires a path' >&2; exit 2; }; shift 2 ;;
    --help|-h) usage; exit 0 ;; *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;; esac
done
if [ -z "$familiar" ]; then
  for candidate in "${MANA_FAMILIAR_ROOT:-}" "$root/../mana-familiar" "$root/../mana-learning-explorer"; do
    [ -n "$candidate" ] && [ -d "$candidate/.git" ] || continue
    remote="$(git -C "$candidate" remote get-url origin 2>/dev/null || true)"
    case "$remote" in *github.com/bruuuuuce/mana-familiar.git) familiar="$candidate"; break ;; esac
  done
fi
[ -n "$familiar" ] || { echo 'ERROR: Mana Familiar sibling not found; set MANA_FAMILIAR_ROOT or --familiar-root' >&2; exit 2; }
familiar="$(cd "$familiar" 2>/dev/null && pwd -P)" || { echo 'ERROR: unreadable Mana Familiar root' >&2; exit 2; }
remote="$(git -C "$familiar" remote get-url origin 2>/dev/null || true)"
case "$remote" in *github.com/bruuuuuce/mana-familiar.git) ;; *) echo "ERROR: not a Mana Familiar repository: $familiar" >&2; exit 2 ;; esac
"$root/scripts/validate-inspect-contract.sh"
for file in docs/mana-inspect-compatibility.md lib/application/mana_inspect.dart test/mana_inspect_test.dart; do
  [ -f "$familiar/$file" ] || { echo "ERROR: Familiar inspect surface missing: $file" >&2; exit 4; }
done
rg -Fq 'Mana owns the inspect contract' "$familiar/docs/mana-inspect-compatibility.md" || { echo 'ERROR: Familiar canonical ownership statement missing' >&2; exit 4; }
rg -Fq 'does not scan' "$familiar/docs/mana-inspect-compatibility.md" || { echo 'ERROR: Familiar no-parser boundary missing' >&2; exit 4; }
for schema in mana.inspect.project/v1 mana.inspect.artifacts/v1 mana.inspect.artifact/v1 mana.inspect.source/v1; do
  rg -Fq "$schema" "$familiar/lib/application/mana_inspect.dart" || { echo "ERROR: Familiar does not support $schema" >&2; exit 4; }
done
rg -Fq 'unknown additive fields' "$familiar/docs/mana-inspect-compatibility.md" || { echo 'ERROR: Familiar unknown-field behavior missing' >&2; exit 4; }
if ! command -v flutter >/dev/null 2>&1; then echo 'ERROR: flutter is required to run Familiar parser tests' >&2; exit 5; fi
(
  cd "$familiar"
  flutter test test/mana_inspect_test.dart test/observatory_model_test.dart
)
echo "C00 Mana/Familiar inspect compatibility passed"
