#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/scripts/validate-inspect-contract.sh"
copy="$(mktemp -d "${TMPDIR:-/tmp}/mana-inspect-contract.XXXXXX")"
trap 'rm -rf "$copy"' EXIT
cp -R "$root/contracts/mana-inspect/v1/." "$copy/"
"$root/scripts/validate-inspect-contract.sh" --bundle "$copy"
for schema in work-items work-item project-context activity; do
  jq -e '."$schema"=="https://json-schema.org/draft/2020-12/schema" and .additionalProperties==false' "$root/contracts/mana-inspect/v1/schemas/$schema.schema.json" >/dev/null
done
grep -Fq 'mana inspect work-item <work-item-id> --json' "$root/contracts/mana-inspect/v1/SEMANTIC-CONTRACT.md"
rg -Fq 'work_items_response' "$root/scripts/mana-inspect.sh"
rg -Fq 'work_item_response' "$root/scripts/mana-inspect.sh"
echo 'Mana inspect contract clean-room tests passed'
