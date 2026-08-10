#!/usr/bin/env bash
# Host-owned Concept Registry v0. It generates the bounded candidate inventory
# and validates model output; it never lets a model define a concept ID.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"
index="$root/learning-kb/concept-index.tsv"
usage() { cat <<'USAGE' >&2
Usage: mana concepts <command> [options]

Commands:
  validate
  candidates [--language <id>] [--category <id>] [--framework <id>] [--limit <n>] [--json]
  prepare --snippet <file> --subject-node <journey-node-id> [candidate filters]
  validate-classification --request <file> --result <file>
  record-unresolved --request <file> --result <file>

`prepare` emits a bounded, host-generated candidate inventory. A classification
result may choose only IDs in that inventory or use `resolution: unresolved`.
USAGE
}
fail() { echo "ERROR: $*" >&2; exit 2; }
require_index() { [ -f "$index" ] || fail "missing concept index: $index"; }
positive_int() { printf '%s' "$1" | grep -Eq '^[1-9][0-9]*$'; }
validate() {
  require_index
  "$root/scripts/build-concept-index.sh" "$root" | cmp -s - "$index" || fail 'concept-index.tsv is stale; rebuild it with scripts/build-concept-index.sh'
  awk -F '\t' 'NR == 1 { if ($0 != "id\tkey\tcategory\taliases\thint\tlanguages\tframeworks") exit 1; next } !/^cpt_[0-9][0-9][0-9]\t/ || NF != 7 || seen[$1]++ || seen_key[$2]++ { exit 1 }' "$index" || fail 'invalid or duplicate concept index entries'
}
filter_index() {
  local language="$1" category="$2" framework="$3" limit="$4"
  awk -F '\t' -v language="$language" -v category="$category" -v framework="$framework" -v limit="$limit" '
    NR == 1 { next }
    (category == "" || $3 == category) && (language == "" || $6 == "" || ("|" $6 "|") ~ ("\\|" language "\\|")) && (framework == "" || $7 == "" || ("|" $7 "|") ~ ("\\|" framework "\\|")) { print; n++; if (limit > 0 && n >= limit) exit }
  ' "$index"
}
candidates() {
  local language="" category="" framework="" limit=50 output_json=false line
  while [ "$#" -gt 0 ]; do case "$1" in --language) language="${2:-}"; shift 2;; --category) category="${2:-}"; shift 2;; --framework) framework="${2:-}"; shift 2;; --limit) limit="${2:-}"; shift 2;; --json) output_json=true; shift;; *) fail "unknown candidates option: $1";; esac; done
  positive_int "$limit" || fail '--limit must be a positive integer'
  validate
  if [ "$output_json" = true ]; then
    filter_index "$language" "$category" "$framework" "$limit" | jq -Rsc 'split("\n") | map(select(length > 0) | split("\t")) | map({id:.[0],key:.[1],category:.[2],aliases:(.[3]|split("|")|map(select(length > 0))),hint:.[4],languages:(.[5]|split("|")|map(select(length > 0))),frameworks:(.[6]|split("|")|map(select(length > 0)))})'
  else
    printf 'id\tkey\tcategory\taliases\thint\n'; filter_index "$language" "$category" "$framework" "$limit" | cut -f1-5
  fi
}
prepare() {
  local snippet="" subject="" language="" category="" framework="" limit=50 body candidates_json request_id
  while [ "$#" -gt 0 ]; do case "$1" in --snippet) snippet="${2:-}"; shift 2;; --subject-node) subject="${2:-}"; shift 2;; --language) language="${2:-}"; shift 2;; --category) category="${2:-}"; shift 2;; --framework) framework="${2:-}"; shift 2;; --limit) limit="${2:-}"; shift 2;; *) fail "unknown prepare option: $1";; esac; done
  [ -f "$snippet" ] || fail '--snippet must name a readable file'; printf '%s' "$subject" | grep -Eq '^jn_[a-f0-9]{24}$' || fail '--subject-node must be a host-generated Journey node ID'; positive_int "$limit" || fail '--limit must be a positive integer'
  body="$(head -c 8000 "$snippet")"; [ "$(printf '%s' "$body" | wc -c | tr -d ' ')" -le 8000 ] || fail 'snippet exceeds the 8000-byte bound'
  candidates_json="$(candidates --language "$language" --category "$category" --framework "$framework" --limit "$limit" --json)"
  request_id="ccr_$(LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c 24)"
  jq -cn --arg id "$request_id" --arg subject "$subject" --arg snippet "$body" --arg language "$language" --arg category "$category" --arg framework "$framework" --argjson candidates "$candidates_json" '{schema:"mana.learning.concept-classifier-request/v1",id:$id,subject_node_id:$subject,budget:{max_candidates:($candidates|length),max_snippet_bytes:8000},filters:{language:$language,category:$category,framework:$framework},snippet:$snippet,candidates:$candidates}'
}
validate_classification() {
  local request="" result=""
  while [ "$#" -gt 0 ]; do case "$1" in --request) request="${2:-}"; shift 2;; --result) result="${2:-}"; shift 2;; *) fail "unknown validate-classification option: $1";; esac; done
  [ -f "$request" ] || fail '--request must name a readable file'; [ -f "$result" ] || fail '--result must name a readable file'
  jq -e '(.schema == "mana.learning.concept-classifier-request/v1") and (.id|test("^ccr_[a-f0-9]{24}$")) and (.candidates|type == "array")' "$request" >/dev/null || fail 'invalid classifier request'
  jq -e --arg request_id "$(jq -r .id "$request")" --arg subject "$(jq -r .subject_node_id "$request")" '
    (.schema == "mana.learning.concept-classification/v1") and (.request_id == $request_id) and (.classifications|type == "array") and
    all(.classifications[]; (.subject_node_id == $subject) and (.relevance|IN("primary","supporting","incidental")) and (.evidence_ids|type == "array") and all(.evidence_ids[]; type == "string" and test("^ev_[a-f0-9]{24}$")) and ((.resolution == "known" and (.concept_id|type == "string") and (has("unresolved_label")|not)) or (.resolution == "unresolved" and (has("concept_id")|not) and (.unresolved_label|type == "string" and length > 0))))
  ' "$result" >/dev/null || fail 'invalid classification result shape'
  jq -e --slurpfile request "$request" 'all(.classifications[] | select(.resolution == "known"); .concept_id as $id | ($request[0].candidates | any(.id == $id)))' "$result" >/dev/null || fail 'classification selected an ID outside the host candidate inventory'
  echo 'Concept classification valid'
}
record_unresolved() {
  local request="" result="" dir id count=0
  while [ "$#" -gt 0 ]; do case "$1" in --request) request="${2:-}"; shift 2;; --result) result="${2:-}"; shift 2;; *) fail "unknown record-unresolved option: $1";; esac; done
  validate_classification --request "$request" --result "$result" >/dev/null
  dir="$project_root/.mana/learning/unresolved-concepts"; mkdir -p "$dir"
  while IFS= read -r item; do
    id="ucp_$(LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c 24)"
    [ ! -e "$dir/$id.yaml" ] || continue
    jq -cn --arg id "$id" --arg request_id "$(jq -r .id "$request")" --argjson item "$item" '{schema:"mana.learning.unresolved-concept/v1",id:$id,request_id:$request_id,subject_node_id:$item.subject_node_id,label:$item.unresolved_label,relevance:$item.relevance,evidence_ids:$item.evidence_ids,status:"candidate"}' > "$dir/$id.yaml"
    printf '%s\n' "$id"; count=$((count + 1))
  done < <(jq -c '.classifications[] | select(.resolution == "unresolved")' "$result")
  [ "$count" -gt 0 ] || fail 'classification contains no unresolved concepts'
}

while [ "${1:-}" = "--project-root" ]; do project_root="${2:-}"; [ -n "$project_root" ] || fail '--project-root requires a path'; shift 2; done
command="${1:-}"; [ -n "$command" ] || { usage; exit 2; }; shift
case "$command" in help|--help|-h) usage;; validate) [ "$#" -eq 0 ] || fail 'validate takes no options'; validate; echo 'Concept registry valid';; candidates) candidates "$@";; prepare) prepare "$@";; validate-classification) validate_classification "$@";; record-unresolved) record_unresolved "$@";; *) fail "unknown concepts command: $command";; esac
