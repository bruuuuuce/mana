#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-scout-cycles.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fixture="$root/tests/fixtures/mana-learning-cycles-v0/graph.tsv"
fail() { echo "FAIL: $*" >&2; exit 1; }

make_journey() {
  local project="$1" jrn kind left right relation node_id
  mkdir -p "$project"
  jrn="$($root/scripts/mana-journey.sh --project-root "$project" create --title 'Harden cyclic topology' --start-kind code --start-value fixture --termination-kind code --termination-condition bounded)"
  while IFS=$'\t' read -r kind left right relation; do
    [ "$kind" = node ] || continue
    node_id="$($root/scripts/mana-journey.sh --project-root "$project" add-node "$jrn" --kind code --label "$left")"
    printf '%s\t%s\n' "$left" "$node_id" >> "$project/ids.tsv"
  done < <(grep -v '^#' "$fixture")
  while IFS=$'\t' read -r kind left right relation; do
    [ "$kind" = edge ] || continue
    from="$(awk -F '\t' -v label="$left" '$1 == label { print $2 }' "$project/ids.tsv")"
    to="$(awk -F '\t' -v label="$right" '$1 == label { print $2 }' "$project/ids.tsv")"
    [ -n "$from$to" ] || fail "fixture edge is unresolved: $left -> $right"
    "$root/scripts/mana-journey.sh" --project-root "$project" add-edge "$jrn" --from "$from" --to "$to" --kind "$relation" >/dev/null
  done < <(grep -v '^#' "$fixture")
  printf '%s\n' "$jrn"
}

project="$tmp/project"
jrn="$(make_journey "$project")"
"$root/scripts/mana-scout.sh" --project-root "$project" harden "$jrn" >/dev/null
graph="$tmp/graph.json"
"$root/scripts/mana-journey.sh" --project-root "$project" materialize "$jrn" > "$graph"

# Five distinct loops are represented as SCC regions and back-edges. The join
# is retained only in the diagnostic report; no synthetic iteration node exists.
jq -e '
  (.nodes | length == 12) and
  (.cycle_regions | length == 5) and
  ([.edges[] | select(.kind == "LOOP_BACK")] | length == 5) and
  ([.cycle_regions[].kind] | sort == ["event_loop", "polling", "recursive", "retry", "state_cycle"]) and
  ([.nodes[].label] | index("JoinTarget")) and
  ([.cycle_regions[] | .node_ids[]] | length == 9)
' "$graph" >/dev/null || fail 'cycle regions or classifications are incomplete'
report="$project/.mana/learning/journeys/$jrn/derived/cycle-report.json"
jq -e '.status == "completed" and .detected.cycle_regions == 5 and .detected.back_edges == 5 and (.detected.joins | length == 1)' "$report" >/dev/null || fail 'join/cycle report is incorrect'

# A re-run only reuses the same stable logical nodes and existing back edges.
first="$tmp/first.json"; second="$tmp/second.json"
cp "$graph" "$first"
"$root/scripts/mana-scout.sh" --project-root "$project" harden "$jrn" >/dev/null
"$root/scripts/mana-journey.sh" --project-root "$project" materialize "$jrn" > "$second"
cmp -s "$first" "$second" || fail 'cycle hardening is not idempotent'

# Cycle budgets are evaluated before persistence, so they cannot cause an
# unbounded partial expansion.
limited="$tmp/limited"
limited_jrn="$(make_journey "$limited")"
if "$root/scripts/mana-scout.sh" --project-root "$limited" harden "$limited_jrn" --max-cycle-regions 4 >/dev/null 2>&1; then fail 'cycle-region budget was not enforced'; fi
limited_graph="$tmp/limited.json"
"$root/scripts/mana-journey.sh" --project-root "$limited" materialize "$limited_jrn" > "$limited_graph"
jq -e '(.cycle_regions | length == 0) and ([.edges[] | select(.kind == "LOOP_BACK")] | length == 0)' "$limited_graph" >/dev/null || fail 'budget failure appended cycle records'
jq -e '.status == "budget_exceeded" and .stop_reason == "max_cycle_regions"' "$limited/.mana/learning/journeys/$limited_jrn/derived/cycle-report.json" >/dev/null || fail 'cycle budget report is missing'

echo 'Mana Scout cycle hardening v0 acceptance tests passed'
