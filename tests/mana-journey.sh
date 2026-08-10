#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-journey.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
journey() { "$root/scripts/mana-journey.sh" --project-root "$project" "$@"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

jrn="$(journey create --title 'Trace payment authorization' --start-kind http_endpoint --start-value 'POST /payments' --termination-kind runtime_effect --termination-condition primary_transaction_committed --revision deadbeef)"
[[ "$jrn" =~ ^jrn_[a-f0-9]{24}$ ]] || fail 'Journey ID is not host-generated'
journey materialize "$jrn" | jq -e '.nodes == [] and .journey.id == $id' --arg id "$jrn" >/dev/null || fail 'empty Journey materialization failed'

# Linear execution and runtime effect. Adding a new source position must not
# rewrite the logical node.
controller="$(journey add-node "$jrn" --kind code)"
service="$(journey add-node "$jrn" --kind code --state expanded)"
repository="$(journey add-node "$jrn" --kind code)"
commit="$(journey add-node "$jrn" --kind runtime_effect)"
journey add-edge "$jrn" --from "$controller" --to "$service" --kind CALLS >/dev/null
journey add-edge "$jrn" --from "$service" --to "$repository" --kind CALLS >/dev/null
journey add-edge "$jrn" --from "$repository" --to "$commit" --kind EXECUTES >/dev/null
node_file="$(find "$project/.mana/learning/journeys/$jrn/records" -name "$service-node.yaml")"
node_digest_before="$(shasum -a 256 "$node_file" | awk '{print $1}')"
anchor_one="$(journey add-anchor "$jrn" --node "$service" --revision deadbeef --path src/PaymentService.java --start-line 84 --end-line 117 --symbol PaymentService.authorize)"
anchor_two="$(journey add-anchor "$jrn" --node "$service" --revision cafebabe --path src/payments/PaymentService.java --start-line 92 --end-line 125 --symbol PaymentService.authorize --fingerprint sha256:moved)"
[ "$node_digest_before" = "$(shasum -a 256 "$node_file" | awk '{print $1}')" ] || fail 'anchor update rewrote node identity'
[ "$anchor_one" != "$anchor_two" ] || fail 'source anchors must be immutable additions'
evidence="$(journey add-evidence "$jrn" --kind source_range --anchor "$anchor_two" --summary 'The service calls the repository.')"

# Branch/join, concept occurrence and calibrated rationale hypothesis.
router="$(journey add-node "$jrn" --kind code)"
provider_a="$(journey add-node "$jrn" --kind code)"
provider_b="$(journey add-node "$jrn" --kind code)"
join="$(journey add-node "$jrn" --kind runtime_effect)"
journey add-edge "$jrn" --from "$router" --to "$provider_a" --kind CALLS >/dev/null
journey add-edge "$jrn" --from "$router" --to "$provider_b" --kind CALLS >/dev/null
journey add-edge "$jrn" --from "$provider_a" --to "$join" --kind RETURNS_TO >/dev/null
journey add-edge "$jrn" --from "$provider_b" --to "$join" --kind RETURNS_TO >/dev/null
journey add-explanation "$jrn" --subject "$router" --evidence "$evidence" >/dev/null
journey add-concept-occurrence "$jrn" --concept-id cpt_005 --subject "$router" --relevance primary --evidence "$evidence" >/dev/null
journey add-hypothesis "$jrn" --subject "$router" --claim 'The provider boundary may anticipate multiple payment providers.' --confidence plausible --supports "$evidence" >/dev/null

# A cycle is one pair of nodes plus one back edge, never repeated nodes.
consume="$(journey add-node "$jrn" --kind code)"
retry="$(journey add-node "$jrn" --kind code)"
journey add-edge "$jrn" --from "$consume" --to "$retry" --kind CALLS >/dev/null
back="$(journey add-edge "$jrn" --from "$retry" --to "$consume" --kind LOOP_BACK)"
journey add-cycle-region "$jrn" --entry "$consume" --kind retry --nodes "$consume" "$retry" --back-edge "$back" >/dev/null
journey add-traversal "$jrn" --kind execution --entry "$controller" --nodes "$controller" "$service" "$repository" "$commit" >/dev/null

# Reload/materialize must be deterministic and preserve every fixture shape.
first="$tmp/first.json"; second="$tmp/second.json"
journey materialize "$jrn" > "$first"
journey validate "$jrn" >/dev/null
journey materialize "$jrn" > "$second"
cmp -s "$first" "$second" || fail 'materialized graph is not deterministic'
jq -e '(.nodes | length >= 10) and (.edges | length >= 8) and (.anchors | length == 2) and (.explanations | length == 1) and (.hypotheses | length == 1) and (.concept_occurrences | length == 1) and (.cycle_regions | length == 1) and (.cycle_regions[0].back_edge_ids | length == 1)' "$first" >/dev/null || fail 'fixture graph is incomplete'

# A correctly shaped arbitrary ID is still rejected if it has no persisted record.
bad="$project/.mana/learning/journeys/$jrn/records/je_aaaaaaaaaaaaaaaaaaaaaaaa-bad.yaml"
printf '%s\n' '{"schema":"mana.learning.record/v1","record_type":"edge","id":"je_aaaaaaaaaaaaaaaaaaaaaaaa","from":"jn_aaaaaaaaaaaaaaaaaaaaaaaa","to":"jn_bbbbbbbbbbbbbbbbbbbbbbbb","kind":"CALLS"}' > "$bad"
if journey validate "$jrn" >/dev/null 2>&1; then fail 'invalid reference was accepted'; fi
rm "$bad"
journey validate "$jrn" >/dev/null

echo 'Mana Journey Model v0 acceptance tests passed'
