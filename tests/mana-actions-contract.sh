#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/scripts/validate-actions-contract.sh"
copy="$(mktemp -d "${TMPDIR:-/tmp}/mana-actions-contract.XXXXXX")"
trap 'rm -rf "$copy"' EXIT
cp -R "$root/contracts/mana-actions/v1/." "$copy/"
"$root/scripts/validate-actions-contract.sh" --bundle "$copy"
echo 'Mana actions contract clean-room tests passed'
