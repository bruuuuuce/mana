#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
bundle="$root/contracts/mana-review-scheduler/v1"
while [ "$#" -gt 0 ]; do case "$1" in --bundle) bundle="${2:-}"; shift 2;; *) echo "ERROR: unknown argument: $1" >&2; exit 2;; esac; done
bundle="$(cd "$bundle" && pwd -P)"
jq -e '.bundle=="mana-review-scheduler-contract" and .version=="v1" and (.schemas|length)==6 and (.fixtures|length)==3 and .credentialsStored==false and .implicitPublication==false' "$bundle/bundle.json" >/dev/null
for schema in $(jq -r '.schemas[]' "$bundle/bundle.json"); do jq -e '."$schema"=="https://json-schema.org/draft/2020-12/schema" and .type=="object" and .additionalProperties==false' "$bundle/$schema" >/dev/null; done
python3 "$root/tests/lib/json_schema_subset.py" "$bundle/schemas/status.schema.json" "$bundle/fixtures/status.json"
python3 "$root/tests/lib/json_schema_subset.py" "$bundle/schemas/inbox.schema.json" "$bundle/fixtures/inbox.json"
python3 "$root/tests/lib/json_schema_subset.py" "$bundle/schemas/run.schema.json" "$bundle/fixtures/run.json"
! rg -n '"/(Users|home|private|tmp)/|[A-Za-z]:\\\\|token|credential[^s]' "$bundle/fixtures" >/dev/null || { echo 'ERROR: unsafe scheduler fixture content' >&2; exit 4; }
echo 'Mana review scheduler v1 contract bundle validation passed'
