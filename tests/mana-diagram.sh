#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-diagram.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
journey() { "$root/scripts/mana-journey.sh" --project-root "$project" "$@"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

jrn="$(journey create --title diagrams --start-kind symbol --start-value Controller --termination-kind runtime_effect --termination-condition done)"
controller="$(journey add-node "$jrn" --kind code --label Controller)"
service="$(journey add-node "$jrn" --kind code --label Service)"
gateway="$(journey add-node "$jrn" --kind external_system --label Gateway)"
controller_anchor="$(journey add-anchor "$jrn" --node "$controller" --revision HEAD --path src/Controller.java --start-line 10 --end-line 20)"
journey add-anchor "$jrn" --node "$service" --revision HEAD --path src/Service.java --start-line 1 --end-line 9 >/dev/null
journey add-edge "$jrn" --from "$controller" --to "$service" --kind CALLS >/dev/null
journey add-edge "$jrn" --from "$service" --to "$gateway" --kind DEPENDS_ON >/dev/null

sequence_id="$($root/scripts/mana-diagram.sh --project-root "$project" generate --journey "$jrn" --kind sequence --node "$controller" --node "$service" --title 'Request flow')"
component_id="$($root/scripts/mana-diagram.sh --project-root "$project" generate --journey "$jrn" --kind component --node "$service" --node "$gateway")"
[[ "$sequence_id" =~ ^dia_[a-f0-9]{24}$ ]] || fail 'sequence diagram ID is not host-generated'
[[ "$component_id" =~ ^dia_[a-f0-9]{24}$ ]] || fail 'component diagram ID is not host-generated'
graph="$tmp/graph.json"
journey materialize "$jrn" > "$graph"
jq -e --arg controller "$controller" --arg service "$service" --arg gateway "$gateway" '(.diagrams | length == 2) and ([.diagrams[].kind] | sort == ["component","sequence"]) and all(.diagrams[]; (.asset_path | startswith("assets/")) and (.node_ids | length == 2)) and ([.diagrams[].node_ids[]] | index($controller) != null and index($service) != null and index($gateway) != null)' "$graph" >/dev/null || fail 'diagram metadata is incomplete'
while IFS= read -r asset; do
  file="$project/.mana/learning/journeys/$jrn/$asset"
  [ -f "$file" ] || fail "missing derived asset: $asset"
  grep -Fq '@startuml' "$file" && grep -Fq '@enduml' "$file" || fail "invalid PlantUML asset: $asset"
  grep -Fq "mana-node: $controller" "$file" || true
done < <(jq -r '.diagrams[].asset_path' "$graph")
sequence_asset="$(jq -r '.diagrams[] | select(.kind == "sequence") | .asset_path' "$graph")"
sequence_file="$project/.mana/learning/journeys/$jrn/$sequence_asset"
grep -Fq "mana-node: $controller" "$sequence_file" || fail 'sequence diagram does not correlate its element to a Journey node'
grep -Fq "$controller" "$sequence_file" || fail 'sequence diagram does not expose node ID for source-anchor correlation'

if "$root/scripts/mana-diagram.sh" --project-root "$project" generate --journey "$jrn" --kind sequence --node "$controller" >/dev/null 2>&1; then fail 'single-node decorative diagram was accepted'; fi
if "$root/scripts/mana-diagram.sh" --project-root "$project" generate --journey "$jrn" --kind component --node "$controller" --node "$gateway" >/dev/null 2>&1; then fail 'disconnected diagram was accepted'; fi
journey validate "$jrn" >/dev/null
# A derived asset is not authoritative: temporary absence must not make the
# persisted Journey graph unreadable.
missing_asset="$project/.mana/learning/journeys/$jrn/$sequence_asset"
mv "$missing_asset" "$missing_asset.unavailable"
journey materialize "$jrn" | jq -e '.diagrams | length == 2' >/dev/null || fail 'missing derived asset invalidated Journey materialization'
mv "$missing_asset.unavailable" "$missing_asset"
echo 'Mana diagram enrichment v0 acceptance tests passed'
