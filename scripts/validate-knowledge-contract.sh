#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
bundle="$root/contracts/mana-knowledge/v1"
while [ "$#" -gt 0 ]; do case "$1" in --bundle) bundle="${2:-}"; shift 2;; *) echo "ERROR: unknown argument: $1" >&2; exit 2;; esac; done
bundle="$(cd "$bundle" && pwd -P)"
for file in bundle.json schemas/index-status.schema.json schemas/index-build.schema.json schemas/search.schema.json schemas/passage.schema.json schemas/capabilities.schema.json schemas/documents.schema.json schemas/document.schema.json schemas/learning-review-queue.schema.json fixtures/search.json fixtures/passage.json fixtures/capabilities.json fixtures/documents.json fixtures/document.json fixtures/learning-review-queue.json; do [ -f "$bundle/$file" ] || { echo "ERROR: missing $file" >&2; exit 4; }; done
jq -e '.bundle=="mana-knowledge-contract" and .version=="v1" and .owner=="Mana" and (.schemas|length)==8 and (.fixtures|length)==6 and .modelCalls==0 and .network==false' "$bundle/bundle.json" >/dev/null
while IFS= read -r schema; do jq -e '."$schema"=="https://json-schema.org/draft/2020-12/schema" and .type=="object" and .additionalProperties==false' "$bundle/$schema" >/dev/null; done < <(jq -r '.schemas[]' "$bundle/bundle.json")
jq -e '.schema=="mana.knowledge.search/v1" and (.results|length)<=.limits.results and .returned_bytes<=.limits.returned_bytes and all(.results[]; (.source_reference|startswith(".mana/") or startswith("mana://framework/")) and (.rank.algorithm=="sqlite-fts5-bm25/v1")) and .guarantees=={generated_answer:false,model_calls:0,network_calls:0}' "$bundle/fixtures/search.json" >/dev/null
jq -e '.schema=="mana.knowledge.passage/v1" and .passage.source_scope=="project" and (.passage.body|type=="string")' "$bundle/fixtures/passage.json" >/dev/null
python3 "$root/tests/lib/json_schema_subset.py" "$bundle/schemas/capabilities.schema.json" "$bundle/fixtures/capabilities.json"
python3 "$root/tests/lib/json_schema_subset.py" "$bundle/schemas/documents.schema.json" "$bundle/fixtures/documents.json"
python3 "$root/tests/lib/json_schema_subset.py" "$bundle/schemas/document.schema.json" "$bundle/fixtures/document.json"
python3 "$root/tests/lib/json_schema_subset.py" "$bundle/schemas/learning-review-queue.schema.json" "$bundle/fixtures/learning-review-queue.json"
! rg -n '"/(Users|home|private|tmp)/|[A-Za-z]:\\\\' "$bundle/fixtures" >/dev/null || { echo 'ERROR: absolute path in fixture' >&2; exit 4; }
echo 'Mana knowledge v1 contract bundle validation passed'
