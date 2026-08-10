#!/usr/bin/env bash
# Phase 10: explicitly requested, derived PlantUML diagrams for a selected region.
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"
fail() { echo "ERROR: $*" >&2; exit 2; }
journey() { "$root/scripts/mana-journey.sh" --project-root "$project_root" "$@"; }
usage() { cat <<'USAGE' >&2
Usage: mana diagram generate --journey <journey-id> --kind sequence|component \
       --node <node-id> --node <node-id> [--node <node-id> ...] [--title <text>]

Generates one requested derived PlantUML asset. It never generates every
diagram type or expands the Journey: the selected nodes must already form a
connected region containing at least one Journey edge.
USAGE
}
safe_label() { jq -rn --arg value "$1" '$value | gsub("[\\r\\n]"; " ") | gsub("\\\""; "") | gsub("[{}]"; "")'; }

while [ "${1:-}" = --project-root ]; do project_root="${2:-}"; [ -n "$project_root" ] || fail '--project-root requires a value'; shift 2; done
command="${1:-}"; shift || true
[ "$command" = generate ] || { usage; exit 2; }
jrn=""; kind=""; title=""; node_lines=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --journey) jrn="${2:-}"; shift 2 ;;
    --kind) kind="${2:-}"; shift 2 ;;
    --node) node_lines="${node_lines}${2:-}\n"; shift 2 ;;
    --title) title="${2:-}"; shift 2 ;;
    *) fail "unknown diagram option: $1" ;;
  esac
done
[ -n "$jrn$kind$node_lines" ] || fail 'diagram generation requires journey, kind, and at least two --node values'
case "$kind" in sequence|component) ;; *) fail 'diagram kind must be sequence or component';; esac
nodes="$(printf '%b' "$node_lines" | jq -Rsc 'split("\n") | map(select(length > 0))')"
count="$(printf '%s' "$nodes" | jq length)"
[ "$count" -ge 2 ] || fail 'a useful diagram requires at least two selected nodes'
[ "$(printf '%s' "$nodes" | jq 'unique | length')" -eq "$count" ] || fail 'diagram nodes must be unique'
graph="$(journey materialize "$jrn")"
while IFS= read -r node; do printf '%s' "$graph" | jq -e --arg node "$node" 'any(.nodes[]; .id == $node)' >/dev/null || fail "selected node is not in Journey: $node"; done < <(printf '%s' "$nodes" | jq -r '.[]')
edges="$(printf '%s' "$graph" | jq --argjson nodes "$nodes" '[.edges[] | . as $edge | select(($nodes | index($edge.from)) != null and ($nodes | index($edge.to)) != null)] | sort_by(.id)')"
[ "$(printf '%s' "$edges" | jq length)" -gt 0 ] || fail 'selected nodes have no internal Journey edge; no useful diagram generated'

journey_dir="$project_root/.mana/learning/journeys/$jrn"
asset_name="${kind}-$(LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c 16).puml"
asset_path="assets/$asset_name"
asset_file="$journey_dir/$asset_path"
tmp_file="$(mktemp "$journey_dir/assets/.diagram.XXXXXX")"
trap 'rm -f "$tmp_file"' EXIT
diagram_title="${title:-$kind diagram for selected Journey region}"
{
  printf '%s\n' '@startuml'
  printf '%s\n' "title $(safe_label "$diagram_title")"
  printf '%s\n' "' Derived from Journey $jrn; do not edit as source of truth."
  index=0
  while IFS=$'\t' read -r node label; do
    alias="n$index"; label="$(safe_label "$label")"
    case "$kind" in
      sequence) printf 'participant "%s\\n%s" as %s\n' "$label" "$node" "$alias" ;;
      component) printf 'component "%s\\n%s" as %s\n' "$label" "$node" "$alias" ;;
    esac
    printf "' mana-node: %s\n" "$node"
    index=$((index + 1))
  done < <(printf '%s' "$graph" | jq -r --argjson nodes "$nodes" '.nodes[] | . as $node | select(($nodes | index($node.id)) != null) | [.id, (.label // .id)] | @tsv')
  while IFS=$'\t' read -r edge from to relation; do
    from_index="$(printf '%s' "$nodes" | jq -r --arg id "$from" 'index($id)')"
    to_index="$(printf '%s' "$nodes" | jq -r --arg id "$to" 'index($id)')"
    case "$kind" in
      sequence) printf 'n%s -> n%s : %s\n' "$from_index" "$to_index" "$(safe_label "$relation")" ;;
      component) printf 'n%s --> n%s : %s\n' "$from_index" "$to_index" "$(safe_label "$relation")" ;;
    esac
    printf "' mana-edge: %s\n" "$edge"
  done < <(printf '%s' "$edges" | jq -r '.[] | [.id, .from, .to, .kind] | @tsv')
  printf '%s\n' '@enduml'
} > "$tmp_file"
mv "$tmp_file" "$asset_file"
trap - EXIT
journey add-diagram "$jrn" --kind "$kind" --asset-path "$asset_path" --title "$diagram_title" --nodes $(printf '%s' "$nodes" | jq -r '.[]')
