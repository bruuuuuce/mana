#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/scripts/validate-knowledge-contract.sh"
copy="$(mktemp -d "${TMPDIR:-/tmp}/mana-knowledge-contract.XXXXXX")"
trap 'rm -rf "$copy"' EXIT
cp -R "$root/contracts/mana-knowledge/v1/." "$copy/"
"$root/scripts/validate-knowledge-contract.sh" --bundle "$copy"
echo 'Mana knowledge contract clean-room tests passed'
