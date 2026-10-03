#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/scripts/validate-review-scheduler-contract.sh"
copy="$(mktemp -d "${TMPDIR:-/tmp}/mana-review-scheduler-contract.XXXXXX")"
trap 'rm -rf "$copy"' EXIT
cp -R "$root/contracts/mana-review-scheduler/v1/." "$copy/"
"$root/scripts/validate-review-scheduler-contract.sh" --bundle "$copy"
echo 'Mana review scheduler contract clean-room tests passed'
