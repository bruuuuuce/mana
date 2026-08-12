#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/scripts/validate-inspect-contract.sh"
copy="$(mktemp -d "${TMPDIR:-/tmp}/mana-inspect-contract.XXXXXX")"
trap 'rm -rf "$copy"' EXIT
cp -R "$root/contracts/mana-inspect/v1/." "$copy/"
"$root/scripts/validate-inspect-contract.sh" --bundle "$copy"
echo 'Mana inspect contract clean-room tests passed'
