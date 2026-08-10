#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-concepts.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

"$root/scripts/build-concept-index.sh" | cmp -s - "$root/learning-kb/concept-index.tsv" || fail 'index builder is not deterministic'
"$root/scripts/mana-concepts.sh" validate >/dev/null
java_spring="$("$root/scripts/mana-concepts.sh" candidates --language java --framework spring --json)"
printf '%s' "$java_spring" | jq -e 'any(.[]; .id == "cpt_008") and any(.[]; .id == "cpt_005") and all(.[]; .id != "cpt_009")' >/dev/null || fail 'language/framework candidate filter is incorrect'

snippet="$tmp/snippet.java"; printf '%s\n' '@Transactional PaymentService.authorize()' > "$snippet"
subject='jn_0123456789abcdef01234567'
request="$tmp/request.json"
"$root/scripts/mana-concepts.sh" prepare --snippet "$snippet" --subject-node "$subject" --language java --framework spring --limit 12 > "$request"
jq -e '.schema == "mana.learning.concept-classifier-request/v1" and (.candidates | any(.id == "cpt_008")) and (.candidates | all(.id != "cpt_009"))' "$request" >/dev/null || fail 'host-generated candidate request is invalid'

result="$tmp/result.json"
jq -n --arg request_id "$(jq -r .id "$request")" --arg subject "$subject" '{schema:"mana.learning.concept-classification/v1",request_id:$request_id,classifications:[{subject_node_id:$subject,resolution:"known",concept_id:"cpt_008",relevance:"primary",evidence_ids:["ev_0123456789abcdef01234567"]},{subject_node_id:$subject,resolution:"unresolved",unresolved_label:"custom transaction annotation",relevance:"incidental",evidence_ids:[]}]}' > "$result"
"$root/scripts/mana-concepts.sh" validate-classification --request "$request" --result "$result" >/dev/null
unresolved_id="$("$root/scripts/mana-concepts.sh" --project-root "$tmp/project" record-unresolved --request "$request" --result "$result")"
[[ "$unresolved_id" =~ ^ucp_[a-f0-9]{24}$ ]] || fail 'unresolved concept ID is not host-generated'
jq -e --arg id "$unresolved_id" '.id == $id and .status == "candidate" and .label == "custom transaction annotation"' "$tmp/project/.mana/learning/unresolved-concepts/$unresolved_id.yaml" >/dev/null || fail 'unresolved concept candidate was not persisted'
jq '.classifications[0].concept_id="cpt_009"' "$result" > "$tmp/invented.json"
if "$root/scripts/mana-concepts.sh" validate-classification --request "$request" --result "$tmp/invented.json" >/dev/null 2>&1; then fail 'ID outside host inventory was accepted'; fi

evals="$($root/scripts/evaluate-concept-index.sh)"
printf '%s\n' "$evals" | awk -F '\t' '$1 == "keyword-category-aliases" && $2 >= 0.95 && $3 >= 0.95 && $4 <= 0.10 { ok=1 } END { exit !ok }' || fail 'compact alias representation did not meet accuracy threshold'
aliases_tokens="$(printf '%s\n' "$evals" | awk -F '\t' '$1 == "keyword-category-aliases" { print $6 }')"
hints_tokens="$(printf '%s\n' "$evals" | awk -F '\t' '$1 == "keyword-category-aliases-hint" { print $6 }')"
[ "$aliases_tokens" -lt "$hints_tokens" ] || fail 'selected representation is not the smaller equivalent representation'

# Journey occurrences are now constrained to canonical registry IDs, not just
# an ID-shaped free-form string.
project="$tmp/journey-project"
jrn="$("$root/scripts/mana-journey.sh" --project-root "$project" create --title Registry --start-kind symbol --start-value Main.main --termination-kind runtime_effect --termination-condition ready)"
node="$("$root/scripts/mana-journey.sh" --project-root "$project" add-node "$jrn" --kind code)"
"$root/scripts/mana-journey.sh" --project-root "$project" add-concept-occurrence "$jrn" --concept-id cpt_005 --subject "$node" >/dev/null
if "$root/scripts/mana-journey.sh" --project-root "$project" add-concept-occurrence "$jrn" --concept-id cpt_999 --subject "$node" >/dev/null 2>&1; then fail 'unknown canonical concept ID was accepted by Journey'; fi
echo 'Mana Concept Registry v0 acceptance tests passed'
