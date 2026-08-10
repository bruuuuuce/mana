#!/usr/bin/env bash
# Phase 9: bounded Git archaeology for one existing Journey anchor.
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"
fail() { echo "ERROR: $*" >&2; exit 2; }
journey() { "$root/scripts/mana-journey.sh" --project-root "$project_root" "$@"; }
usage() { cat <<'USAGE' >&2
Usage: mana history enrich --journey <journey-id> --node <node-id> --anchor <anchor-id>
                           [--max-commits <n>] [--hypothesis <hyp-id>
                            --effect strengthens|weakens|inconclusive --reason <text>]

Inspects only the selected anchor path. On unavailable Git history it appends a
failed enrichment record and exits successfully, preserving Journey validity.
USAGE
}

while [ "${1:-}" = --project-root ]; do project_root="${2:-}"; [ -n "$project_root" ] || fail '--project-root requires a value'; shift 2; done
command="${1:-}"; shift || true
[ "$command" = enrich ] || { usage; exit 2; }

jrn=""; node=""; anchor=""; max=12; hypothesis=""; effect=""; reason=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --journey) jrn="${2:-}"; shift 2 ;;
    --node) node="${2:-}"; shift 2 ;;
    --anchor) anchor="${2:-}"; shift 2 ;;
    --max-commits) max="${2:-}"; shift 2 ;;
    --hypothesis) hypothesis="${2:-}"; shift 2 ;;
    --effect) effect="${2:-}"; shift 2 ;;
    --reason) reason="${2:-}"; shift 2 ;;
    *) fail "unknown history option: $1" ;;
  esac
done
[ -n "$jrn$node$anchor" ] || fail 'history enrichment requires journey, node, and anchor'
[[ "$max" =~ ^[1-9][0-9]*$ ]] || fail '--max-commits must be a positive integer'
if [ -n "$hypothesis" ] || [ -n "$effect" ] || [ -n "$reason" ]; then
  [ -n "$hypothesis$effect$reason" ] || fail 'hypothesis assessment requires hypothesis, effect, and reason'
fi

graph="$(journey materialize "$jrn")"
anchor_json="$(printf '%s' "$graph" | jq -ce --arg node "$node" --arg anchor "$anchor" '.anchors[] | select(.id == $anchor and .node_id == $node)')" || fail 'anchor does not belong to subject node'
path="$(printf '%s' "$anchor_json" | jq -r .path)"
symbol="$(printf '%s' "$anchor_json" | jq -r '.symbol // empty')"
start="$(printf '%s' "$anchor_json" | jq -r .range.start_line)"
end="$(printf '%s' "$anchor_json" | jq -r .range.end_line)"

if ! git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  journey add-git-enrichment "$jrn" --subject "$node" --anchor "$anchor" --status failed --scope-path "$path" --reason 'Git history is unavailable for this project.'
  exit 0
fi

log_file="$(mktemp "${TMPDIR:-/tmp}/mana-history-log.XXXXXX")"
trap 'rm -f "$log_file"' EXIT
if ! git -C "$project_root" log --follow --date=iso-strict --format='%H%x09%aI%x09%s' --name-status -n "$max" -- "$path" > "$log_file" 2>/dev/null; then
  journey add-git-enrichment "$jrn" --subject "$node" --anchor "$anchor" --status failed --scope-path "$path" --reason 'Scoped Git history inspection failed.'
  exit 0
fi
if ! grep -Eq '^[a-f0-9]{40}' "$log_file"; then
  journey add-git-enrichment "$jrn" --subject "$node" --anchor "$anchor" --status failed --scope-path "$path" --reason 'No Git history was found for the selected anchor path.'
  exit 0
fi

journey add-git-enrichment "$jrn" --subject "$node" --anchor "$anchor" --status completed --scope-path "$path" >/dev/null
current_path="$path"
event_evidence=""
while IFS= read -r line || [ -n "$line" ]; do
  if printf '%s' "$line" | grep -Eq '^[a-f0-9]{40}'$'\t'; then
    commit="${line%%$'\t'*}"; rest="${line#*$'\t'}"; occurred_at="${rest%%$'\t'*}"; summary="${rest#*$'\t'}"
    historical_path="$current_path"
    if [ -n "$symbol" ]; then
      symbol_line="$(git -C "$project_root" show "$commit:$historical_path" 2>/dev/null | rg -n -F -m1 -- "$symbol" | cut -d: -f1 || true)"
      if [ -n "$symbol_line" ]; then event_start="$symbol_line"; event_end=$((symbol_line + end - start)); else event_start="$start"; event_end="$end"; fi
    else
      event_start="$start"; event_end="$end"
    fi
    historical_anchor="$(journey add-anchor "$jrn" --node "$node" --revision "$commit" --path "$historical_path" --start-line "$event_start" --end-line "$event_end" --symbol "$symbol")"
    event_evidence="$(journey add-evidence "$jrn" --kind git_commit --anchor "$historical_anchor" --summary "$summary")"
    journey add-timeline-event "$jrn" --subject "$node" --anchor "$historical_anchor" --evidence "$event_evidence" --revision "$commit" --occurred-at "$occurred_at" --summary "$summary" >/dev/null
  elif printf '%s' "$line" | grep -Eq '^R[0-9]*'$'\t'; then
    old_path="$(printf '%s' "$line" | cut -f2)"; new_path="$(printf '%s' "$line" | cut -f3)"
    [ "$new_path" = "$current_path" ] && current_path="$old_path"
  fi
done < "$log_file"

if [ -n "$hypothesis" ]; then
  journey add-hypothesis-assessment "$jrn" --hypothesis "$hypothesis" --evidence "$event_evidence" --effect "$effect" --reason "$reason"
fi
