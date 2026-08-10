#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-concept-tagging.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"; mkdir -p "$project/src/main/java/example"
cp "$root/tests/fixtures/mana-learning-concepts-v0/ProviderRouter.java" "$project/src/main/java/example/"
fail() { echo "FAIL: $*" >&2; exit 1; }
journey() { "$root/scripts/mana-journey.sh" --project-root "$project" "$@"; }
concepts() { "$root/scripts/mana-concepts.sh" --project-root "$project" "$@"; }
jrn="$(journey create --title 'Provider dispatch' --start-kind symbol --start-value ProviderRouter.authorize --termination-kind code --termination-condition returned)"
node="$(journey add-node "$jrn" --kind code --label ProviderRouter.authorize)"
journey add-anchor "$jrn" --node "$node" --revision WORKTREE --path src/main/java/example/ProviderRouter.java --start-line 9 --end-line 11 --symbol ProviderRouter.authorize >/dev/null
request="$tmp/request.json"
concepts prepare-node --journey "$jrn" --node "$node" --language java --limit 20 > "$request"
jq -e --arg j "$jrn" --arg n "$node" '.journey_id == $j and .subject_node_id == $n and (.evidence_ids|length == 1) and (.candidates | any(.id == "cpt_001"))' "$request" >/dev/null || fail 'bounded node classifier request is incomplete'
result="$tmp/result.json"
jq -n --arg id "$(jq -r .id "$request")" --arg node "$node" --arg evidence "$(jq -r '.evidence_ids[0]' "$request")" '{schema:"mana.learning.concept-classification/v1",request_id:$id,classifications:[{subject_node_id:$node,resolution:"known",concept_id:"cpt_001",relevance:"primary",evidence_ids:[$evidence]}]}' > "$result"
occurrence="$(concepts apply-classification --journey "$jrn" --request "$request" --result "$result")"
[[ "$occurrence" =~ ^occ_[a-f0-9]{24}$ ]] || fail 'known classification did not become a Journey occurrence'
labels="$(concepts labels --journey "$jrn" --node "$node" --json)"
printf '%s' "$labels" | jq -e 'length == 1 and .[0].concept_id == "cpt_001" and .[0].key == "polymorphism" and .[0].relevance == "primary"' >/dev/null || fail 'CLI concept labels are unavailable'
teaching="$(concepts teach --concept-id cpt_001 --journey "$jrn" --node "$node" --json)"
printf '%s' "$teaching" | jq -e '.concept.id == "cpt_001" and (.project_examples|length == 1) and (.project_examples[0].text | contains("provider.authorize"))' >/dev/null || fail 'on-demand concept teaching lacks the selected project example'
if concepts apply-classification --journey "$jrn" --request "$request" --result "$result" >/dev/null 2>&1; then fail 'classification request was applied twice'; fi
echo 'Mana Concept tagging and teaching v0 acceptance tests passed'
