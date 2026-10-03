#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
bundle="$root/contracts/mana-actions/v1"
while [ "$#" -gt 0 ]; do case "$1" in --bundle) bundle="${2:-}"; shift 2;; *) echo "ERROR: unknown argument: $1" >&2; exit 2;; esac; done
bundle="$(cd "$bundle" && pwd -P)"
jq -e '.bundle=="mana-actions-contract" and .version=="v1" and (.schemas|length)==3 and (.fixtures|length)==2 and .modelCalls==0 and .network==false and .automaticPromotion==false' "$bundle/bundle.json" >/dev/null
for schema in $(jq -r '.schemas[]' "$bundle/bundle.json"); do jq -e '."$schema"=="https://json-schema.org/draft/2020-12/schema" and .type=="object"' "$bundle/$schema" >/dev/null; done
python3 "$root/tests/lib/json_schema_subset.py" "$bundle/schemas/action-receipt.schema.json" "$bundle/fixtures/applied.json"
python3 "$root/tests/lib/json_schema_subset.py" "$bundle/schemas/action-receipt.schema.json" "$bundle/fixtures/conflict.json"
! rg -n '"/(Users|home|private|tmp)/|[A-Za-z]:\\\\' "$bundle/fixtures" >/dev/null || { echo 'ERROR: absolute path in action fixture' >&2; exit 4; }
echo 'Mana actions v1 contract bundle validation passed'
