#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-expand.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
fixture="$root/tests/fixtures/mana-learning-scout-v0"
fail() { echo "FAIL: $*" >&2; exit 1; }

mkdir -p "$project"; cp -R "$fixture/src" "$project/"
request="$tmp/scout-request.yaml"
"$root/scripts/mana-scout.sh" --project-root "$project" request --title 'Expand payment service' --path /payments --out "$request" >/dev/null
jrn="$($root/scripts/mana-scout.sh --project-root "$project" run --request "$request")"
before="$tmp/before.json"; "$root/scripts/mana-journey.sh" --project-root "$project" materialize "$jrn" > "$before"
service="$(jq -r '.nodes[] | select(.label == "PaymentService.authorize") | .id' "$before")"
[ -n "$service" ] || fail 'fixture service node was not found'

expand_request="$tmp/expand-request.yaml"
"$root/scripts/mana-expand.sh" --project-root "$project" request --journey "$jrn" --node "$service" --out "$expand_request" --max-context-lines 10 --max-evidence 1 --max-related-nodes 1 >/dev/null
"$root/scripts/mana-expand.sh" --project-root "$project" validate-request --request "$expand_request" >/dev/null
explanation="$($root/scripts/mana-expand.sh --project-root "$project" run --request "$expand_request")"
[[ "$explanation" =~ ^exp_[a-f0-9]{24}$ ]] || fail 'expansion did not create a host explanation record'
after="$tmp/after.json"; "$root/scripts/mana-journey.sh" --project-root "$project" materialize "$jrn" > "$after"

# An explanation enriches only the chosen node: no nodes or graph edges are
# discovered, while its evidence and independent lifecycle are persisted.
jq -e --arg service "$service" --arg explanation "$explanation" --slurpfile before "$before" '
  (.nodes | length) == ($before[0].nodes | length) and
  (.edges | length) == ($before[0].edges | length) and
  (any(.explanations[]; .id == $explanation and .subject_node_id == $service and .status == "completed" and .epistemic_status == "strongly_supported" and (.evidence_ids | length == 1))) and
  ([.enrichments[] | select(.subject_node_id == $service and .kind == "explanation") | .status] | sort == ["completed", "requested"])
' "$after" >/dev/null || fail 'explanation changed unrelated graph state or lacks lifecycle/evidence'

request_id="$(jq -r .id "$expand_request")"
context="$project/.mana/learning/journeys/$jrn/derived/expansions/$request_id-context.json"
report="$project/.mana/learning/journeys/$jrn/derived/expansions/$request_id-report.json"
jq -e '(.source_snippets | map(.text | split("\n") | length) | add) <= 10 and (.anchors | length <= 1) and (.related_edges | length <= 1) and (.evidence_ids | length == 1)' "$context" >/dev/null || fail 'bounded expansion context exceeds its request budget'
jq -e '.status == "completed" and .used.evidence == 1 and .used.related_edges <= 1' "$report" >/dev/null || fail 'expansion report is incomplete'
if "$root/scripts/mana-expand.sh" --project-root "$project" run --request "$expand_request" >/dev/null 2>&1; then fail 'completed expansion request was run twice'; fi

echo 'Mana Expansion v0 acceptance tests passed'
