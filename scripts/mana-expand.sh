#!/usr/bin/env bash
# Phase 5: bounded, append-only explanation enrichment for an existing Journey.
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"

usage() {
  cat <<'USAGE' >&2
Usage: mana expand <command> [options]

Commands:
  request --journey <journey-id> --node <node-id> [--out <file>]
          [--max-context-lines <n>] [--max-evidence <n>] [--max-related-nodes <n>]
  validate-request --request <file>
  run --request <file> [--json]

Expansion v0 builds context only from the selected Journey node, its anchors,
existing evidence and direct graph neighbours. It does not follow source calls.
USAGE
}
fail() { echo "ERROR: $*" >&2; exit 2; }
need() { [ -n "${2:-}" ] || fail "$1 requires a value"; }
positive() { printf '%s' "$1" | grep -Eq '^[1-9][0-9]*$'; }
journey() { "$root/scripts/mana-journey.sh" --project-root "$project_root" "$@"; }
new_id() { printf 'exr_%s' "$(LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c 24)"; }

validate_request() {
  local request="$1"
  [ -f "$request" ] || fail "request not found: $request"
  jq -e '
    .schema == "mana.learning.expansion-request/v1" and
    (.id|type == "string" and test("^exr_[a-f0-9]{24}$")) and
    (.journey_id|type == "string" and test("^jrn_[a-f0-9]{24}$")) and
    (.subject_node_id|type == "string" and test("^jn_[a-f0-9]{24}$")) and
    .kind == "explanation" and
    ([.budget.max_context_lines,.budget.max_evidence,.budget.max_related_nodes] | all(type == "number" and floor == . and . > 0))
  ' "$request" >/dev/null || fail 'invalid expansion request'
}

request_path() { printf '%s/.mana/learning/expansion-requests/%s.yaml' "$project_root" "$1"; }

while [ "${1:-}" = "--project-root" ]; do project_root="${2:-}"; need --project-root "$project_root"; shift 2; done
command="${1:-}"; [ -n "$command" ] || { usage; exit 2; }; shift

case "$command" in
  help|--help|-h) usage ;;
  request)
    journey_id=""; node=""; out=""; max_lines=120; max_evidence=8; max_related=8
    while [ "$#" -gt 0 ]; do case "$1" in
      --journey) journey_id="${2:-}"; shift 2;; --node) node="${2:-}"; shift 2;; --out) out="${2:-}"; shift 2;;
      --max-context-lines) max_lines="${2:-}"; shift 2;; --max-evidence) max_evidence="${2:-}"; shift 2;; --max-related-nodes) max_related="${2:-}"; shift 2;;
      *) fail "unknown request option: $1";; esac; done
    [ -n "$journey_id$node" ] || fail '--journey and --node are required'
    for value in "$max_lines" "$max_evidence" "$max_related"; do positive "$value" || fail 'expansion budgets must be positive integers'; done
    journey validate "$journey_id" >/dev/null
    graph="$(journey materialize "$journey_id")"
    printf '%s\n' "$graph" | jq -e --arg node "$node" 'any(.nodes[]?; .id == $node)' >/dev/null || fail "node is not in Journey: $node"
    request_id="$(new_id)"; [ -n "$out" ] || out="$(request_path "$request_id")"; mkdir -p "$(dirname "$out")"; [ ! -e "$out" ] || fail "request already exists: $out"
    jq -cn --arg id "$request_id" --arg journey "$journey_id" --arg node "$node" --argjson lines "$max_lines" --argjson evidence "$max_evidence" --argjson related "$max_related" '{schema:"mana.learning.expansion-request/v1",id:$id,journey_id:$journey,subject_node_id:$node,kind:"explanation",budget:{max_context_lines:$lines,max_evidence:$evidence,max_related_nodes:$related}}' > "$out"
    journey add-enrichment "$journey_id" --request-id "$request_id" --subject "$node" --kind explanation --status requested >/dev/null
    printf '%s\n' "$out"
    ;;
  validate-request)
    [ "${1:-}" = --request ] || fail 'validate-request requires --request <file>'; validate_request "${2:-}"; echo 'Expansion request is valid'
    ;;
  run)
    request=""; json=false
    while [ "$#" -gt 0 ]; do case "$1" in --request) request="${2:-}"; shift 2;; --json) json=true; shift;; *) fail "unknown run option: $1";; esac; done
    [ -n "$request" ] || fail '--request is required'; validate_request "$request"
    request_id="$(jq -r .id "$request")"; journey_id="$(jq -r .journey_id "$request")"; subject="$(jq -r .subject_node_id "$request")"
    max_lines="$(jq -r .budget.max_context_lines "$request")"; max_evidence="$(jq -r .budget.max_evidence "$request")"; max_related="$(jq -r .budget.max_related_nodes "$request")"
    graph_file="$(mktemp "${TMPDIR:-/tmp}/mana-expand-graph.XXXXXX")"; trap 'rm -f "$graph_file"' EXIT
    journey materialize "$journey_id" > "$graph_file"
    jq -e --arg node "$subject" 'any(.nodes[]?; .id == $node)' "$graph_file" >/dev/null || fail "node is not in Journey: $subject"
    if jq -e --arg request "$request_id" 'any(.enrichments[]?; .request_id == $request and .status == "completed")' "$graph_file" >/dev/null; then fail "expansion request already completed: $request_id"; fi
    context_dir="$project_root/.mana/learning/journeys/$journey_id/derived/expansions"; mkdir -p "$context_dir"
    context="$context_dir/$request_id-context.json"
    anchors="$(jq -c --arg node "$subject" '[.anchors[] | select(.node_id == $node)] | sort_by(.id)' "$graph_file")"
    selected_anchors="$(printf '%s' "$anchors" | jq --argjson max "$max_evidence" '.[0:$max]')"
    related="$(jq -c --arg node "$subject" --argjson max "$max_related" '[.edges[] | select(.from == $node or .to == $node) | {id,kind,from,to,disposition}] | sort_by(.id) | .[0:$max]' "$graph_file")"
    node_label="$(jq -r --arg node "$subject" '.nodes[] | select(.id == $node) | .label' "$graph_file")"
    existing_evidence="$(jq -c --argjson anchors "$selected_anchors" '[.evidence[] | select(.anchor_id? as $anchor | $anchors | any(.id == $anchor))] | sort_by(.id)' "$graph_file")"
    evidence_ids=()
    while IFS= read -r anchor_id; do
      evidence_id="$(printf '%s' "$existing_evidence" | jq -r --arg anchor "$anchor_id" '.[] | select(.anchor_id == $anchor) | .id' | head -n 1)"
      if [ -z "$evidence_id" ]; then evidence_id="$(journey add-evidence "$journey_id" --kind source_range --anchor "$anchor_id" --summary "Source anchor for bounded explanation of $node_label.")"; fi
      evidence_ids+=("$evidence_id")
    done < <(printf '%s' "$selected_anchors" | jq -r '.[].id')
    snippets='[]'; used_lines=0
    while IFS=$'\t' read -r path start end anchor_id; do
      [ "$used_lines" -lt "$max_lines" ] || break
      case "$path" in /*|*..*) continue;; esac
      source_file="$project_root/$path"; [ -f "$source_file" ] || continue
      remaining=$((max_lines - used_lines)); actual_end="$end"; [ $((end - start + 1)) -le "$remaining" ] || actual_end=$((start + remaining - 1))
      snippet="$(sed -n "${start},${actual_end}p" "$source_file")"; taken=$((actual_end - start + 1)); used_lines=$((used_lines + taken))
      snippets="$(printf '%s' "$snippets" | jq --arg anchor "$anchor_id" --arg path "$path" --argjson start "$start" --argjson end "$actual_end" --arg text "$snippet" '. + [{anchor_id:$anchor,path:$path,range:{start_line:$start,end_line:$end},text:$text}]')"
    done < <(printf '%s' "$selected_anchors" | jq -r '.[] | [.path,.range.start_line,.range.end_line,.id] | @tsv')
    jq -n --arg request "$request_id" --arg journey "$journey_id" --arg subject "$subject" --arg label "$node_label" --argjson anchors "$selected_anchors" --argjson evidence "$(printf '%s\n' "${evidence_ids[@]:-}" | jq -Rsc 'split("\n") | map(select(length > 0))')" --argjson related "$related" --argjson snippets "$snippets" --argjson max_lines "$max_lines" --argjson max_evidence "$max_evidence" --argjson max_related "$max_related" '{schema:"mana.learning.expansion-context/v1",request_id:$request,journey_id:$journey,subject_node_id:$subject,subject_label:$label,anchors:$anchors,evidence_ids:$evidence,related_edges:$related,source_snippets:$snippets,budget:{max_context_lines:$max_lines,max_evidence:$max_evidence,max_related_nodes:$max_related}}' > "$context"
    evidence_json="$(printf '%s\n' "${evidence_ids[@]:-}" | jq -Rsc 'split("\n") | map(select(length > 0))')"
    anchor_count="$(printf '%s' "$selected_anchors" | jq length)"; relation_count="$(printf '%s' "$related" | jq length)"
    epistemic=unknown; [ "$anchor_count" -gt 0 ] && epistemic=strongly_supported
    body="This explanation is bounded to $node_label. It is supported by $anchor_count selected source anchor(s) and $relation_count direct graph relation(s). It does not infer behaviour beyond the persisted evidence and direct context."
    evidence_args=()
    for evidence_id in "${evidence_ids[@]}"; do evidence_args+=(--evidence "$evidence_id"); done
    explanation="$(journey add-explanation "$journey_id" --subject "$subject" --status completed --body "$body" --epistemic-status "$epistemic" "${evidence_args[@]}")"
    journey add-enrichment "$journey_id" --request-id "$request_id" --subject "$subject" --kind explanation --status completed >/dev/null
    report="$context_dir/$request_id-report.json"
    jq -cn --arg request "$request_id" --arg journey "$journey_id" --arg explanation "$explanation" --arg context "$context" --argjson anchors "$anchor_count" --argjson evidence "$(printf '%s' "$evidence_json" | jq length)" --argjson relations "$relation_count" '{schema:"mana.learning.expansion-report/v1",request_id:$request,journey_id:$journey,status:"completed",explanation_id:$explanation,context:$context,used:{anchors:$anchors,evidence:$evidence,related_edges:$relations}}' > "$report"
    if [ "$json" = true ]; then jq -cn --arg journey_id "$journey_id" --arg explanation_id "$explanation" --arg report "$report" '{journey_id:$journey_id,explanation_id:$explanation_id,report:$report}'; else printf '%s\n' "$explanation"; fi
    ;;
  *) fail "unknown expand command: $command" ;;
esac
