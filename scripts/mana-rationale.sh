#!/usr/bin/env bash
# Phase 8: bounded, calibrated rationale hypotheses; never historical facts.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"; project_root="$(pwd)"
fail() { echo "ERROR: $*" >&2; exit 2; }
journey() { "$root/scripts/mana-journey.sh" --project-root "$project_root" "$@"; }
new_id() { printf 'rhq_%s' "$(LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c 24)"; }
usage() { cat <<'USAGE' >&2
Usage: mana rationale <command> [options]
  request --journey <journey-id> --node <node-id> [--max-evidence <n>] [--out <file>]
  propose --request <file>
  apply --journey <journey-id> --request <file> --result <file>
USAGE
}
validate_request() { jq -e '.schema == "mana.learning.rationale-request/v1" and (.id|test("^rhq_[a-f0-9]{24}$")) and (.journey_id|test("^jrn_[a-f0-9]{24}$")) and (.subject_node_id|test("^jn_[a-f0-9]{24}$")) and (.evidence_ids|type == "array")' "$1" >/dev/null || fail 'invalid rationale request'; }
while [ "${1:-}" = --project-root ]; do project_root="${2:-}"; shift 2; done
command="${1:-}"; shift || true
case "$command" in
  request)
    jrn=""; node=""; max=8; out=""; while [ "$#" -gt 0 ]; do case "$1" in --journey) jrn="${2:-}"; shift 2;; --node) node="${2:-}"; shift 2;; --max-evidence) max="${2:-}"; shift 2;; --out) out="${2:-}"; shift 2;; *) fail "unknown option: $1";; esac; done
    [[ "$max" =~ ^[1-9][0-9]*$ ]] || fail 'max-evidence must be positive'; graph="$(journey materialize "$jrn")"; printf '%s' "$graph" | jq -e --arg node "$node" 'any(.nodes[]; .id == $node)' >/dev/null || fail 'subject is not in Journey'
    evidence="$(printf '%s' "$graph" | jq --arg node "$node" --argjson max "$max" '[.anchors[] | select(.node_id == $node) | .id] as $anchors | [.evidence[] | select(.anchor_id? as $a | $anchors | index($a))] | sort_by(.id) | .[0:$max]')"
    if [ "$(printf '%s' "$evidence" | jq length)" -eq 0 ]; then fail 'subject has no bounded source evidence'; fi
    id="$(new_id)"; [ -n "$out" ] || out="$project_root/.mana/learning/rationale-requests/$id.yaml"; mkdir -p "$(dirname "$out")"; [ ! -e "$out" ] || fail 'request already exists'
    jq -cn --arg id "$id" --arg j "$jrn" --arg n "$node" --argjson evidence "$evidence" '{schema:"mana.learning.rationale-request/v1",id:$id,journey_id:$j,subject_node_id:$n,evidence_ids:($evidence|map(.id)),evidence:$evidence}' > "$out"; echo "$out" ;;
  propose)
    [ "${1:-}" = --request ] || fail 'propose requires --request'; request="${2:-}"; validate_request "$request"; node="$(jq -r .subject_node_id "$request")"; ids="$(jq -c .evidence_ids "$request")"
    jq -n --arg request "$(jq -r .id "$request")" --arg node "$node" --argjson ids "$ids" '{schema:"mana.learning.rationale-result/v1",request_id:$request,hypotheses:[{subject_node_id:$node,category:"planned_extensibility",claim:"The observed boundary may have been introduced to permit future variation; the current evidence does not establish original intent.",confidence:"plausible",supports:$ids,contradicts:[],verification_suggestions:["Inspect introduction commits or ADRs for an explicit extensibility decision."]},{subject_node_id:$node,category:"compatibility_boundary",claim:"The same boundary may instead isolate compatibility or integration concerns; this remains an alternative inference.",confidence:"plausible",supports:$ids,contradicts:[],verification_suggestions:["Inspect callers, configuration and historical changes for compatibility constraints."]}]}' ;;
  apply)
    jrn=""; request=""; result=""; while [ "$#" -gt 0 ]; do case "$1" in --journey) jrn="${2:-}"; shift 2;; --request) request="${2:-}"; shift 2;; --result) result="${2:-}"; shift 2;; *) fail "unknown option: $1";; esac; done
    validate_request "$request"; jq -e --arg id "$(jq -r .id "$request")" --arg node "$(jq -r .subject_node_id "$request")" --argjson allowed "$(jq -c .evidence_ids "$request")" '(.schema == "mana.learning.rationale-result/v1") and (.request_id == $id) and (.hypotheses|type == "array" and length >= 2) and all(.hypotheses[]; .subject_node_id == $node and (.category|IN("planned_extensibility","compatibility_boundary","external_constraint","unknown")) and (.confidence|IN("plausible","speculative","unknown")) and all((.supports[]?,.contradicts[]); . as $e | ($allowed | index($e) != null)) and (.verification_suggestions|type == "array" and length > 0))' "$result" >/dev/null || fail 'invalid or overconfident rationale result'
    [ "$(jq -r .journey_id "$request")" = "$jrn" ] || fail 'request belongs to another Journey'
    while IFS= read -r item; do args=(add-hypothesis "$jrn" --subject "$(printf '%s' "$item" | jq -r .subject_node_id)" --claim "$(printf '%s' "$item" | jq -r .claim)" --confidence "$(printf '%s' "$item" | jq -r .confidence)" --category "$(printf '%s' "$item" | jq -r .category)"); while IFS= read -r e; do args+=(--supports "$e"); done < <(printf '%s' "$item" | jq -r '.supports[]'); while IFS= read -r v; do args+=(--verify "$v"); done < <(printf '%s' "$item" | jq -r '.verification_suggestions[]'); journey "${args[@]}"; done < <(jq -c '.hypotheses[]' "$result") ;;
  *) usage; exit 2 ;;
esac
