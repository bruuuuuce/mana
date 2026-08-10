#!/usr/bin/env bash
# Phase 3 Scout v0: bounded, deterministic Java + Spring POST route discovery.
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"

usage() {
  cat <<'USAGE' >&2
Usage: mana scout <command> [options]

Commands:
  request --title <text> --path </route> [--source-root <path>] [--out <file>]
          [--max-nodes <n>] [--max-edges <n>] [--max-depth <n>] [--max-branching-per-node <n>]
  validate-request --request <file>
  run --request <file> [--json]
  harden <journey-id> [--max-cycle-regions <n>] [--max-cycle-members <n>] [--max-back-edges <n>] [--json]

Scout v0 supports only Java + Spring POST routes and ends at the primary
transaction commit. It writes an append-only Journey in the selected project.
`harden` is the Phase 4 graph pass: it derives CycleRegions and LOOP_BACK
edges from an existing Journey without inventing repeated nodes.
USAGE
}
fail() { echo "ERROR: $*" >&2; exit 2; }
need() { [ -n "${2:-}" ] || fail "$1 requires a value"; }
positive() { printf '%s' "$1" | grep -Eq '^[1-9][0-9]*$'; }
new_id() { printf 'srq_%s' "$(LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c 24)"; }
journey() { "$root/scripts/mana-journey.sh" --project-root "$project_root" "$@"; }

validate_request() {
  local request="$1"
  [ -f "$request" ] || fail "request not found: $request"
  jq -e '
    .schema == "mana.learning.scout-request/v1" and
    .technology == "java-spring-http-v0" and
    (.title|type == "string" and length > 0) and
    (.start.kind == "http_endpoint") and (.start.method == "POST") and
    (.start.path|type == "string" and startswith("/")) and
    (.termination.kind == "runtime_effect") and
    (.termination.condition == "primary_transaction_committed") and
    (.source_root|type == "string" and length > 0) and
    ([.budget.max_nodes,.budget.max_edges,.budget.max_depth,.budget.max_branching_per_node] | all(type == "number" and floor == . and . > 0))
  ' "$request" >/dev/null || fail 'invalid Scout v0 request'
}

method_end() {
  awk -v start="$2" 'NR >= start { opens=gsub(/\{/, "{"); closes=gsub(/\}/, "}"); balance += opens-closes; if (opens > 0) seen=1; if (seen && balance == 0) { print NR; exit } }' "$1"
}
method_after() {
  awk -v start="$2" 'NR >= start && $0 !~ /^[[:space:]]*@/ && $0 ~ /(public|protected|private)[[:space:]].*\(/ { print NR; exit }' "$1"
}
method_name() { sed -n "${2}p" "$1" | sed -E 's/.*[[:space:]]([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*\(.*/\1/'; }
class_name() { basename "$1" .java; }
symbol_for() { printf '%s.%s' "$(class_name "$1")" "$2"; }

# Tarjan finds SCCs; the second DFS emits only edges to nodes currently on its
# traversal stack.  Input order is the already materialized ID order, making
# this independent of filesystem enumeration and write time.
cycle_analysis() {
  local graph="$1"
  {
    jq -r '.nodes[] | ["N", .id] | @tsv' "$graph"
    jq -r '.edges[] | select(.kind != "LOOP_BACK") | ["E", .id, .from, .to] | @tsv' "$graph"
  } | awk -F '\t' '
    $1 == "N" { nodes[++node_count] = $2; present[$2] = 1; next }
    $1 == "E" && present[$3] && present[$4] { edge_id[++edge_count] = $2; edge_from[edge_count] = $3; edge_to[edge_count] = $4; outgoing[$3, ++out_count[$3]] = edge_count; next }
    function tarjan(v,    i,e,w,member,count) {
      idx[v] = low[v] = ++serial; stack[++stack_count] = v; on_stack[v] = 1
      for (i = 1; i <= out_count[v]; i++) { e = outgoing[v,i]; w = edge_to[e]
        if (!(w in idx)) { tarjan(w); if (low[w] < low[v]) low[v] = low[w] }
        else if (on_stack[w] && idx[w] < low[v]) low[v] = idx[w]
      }
      if (low[v] == idx[v]) { count = 0; member = ""
        do { w = stack[stack_count--]; on_stack[w] = 0; members[++count] = w; member = member (member == "" ? "" : ",") w } while (w != v)
        if (count > 1 || self_edge[v]) print "C\t" member
      }
    }
    function stack_dfs(v,    i,e,w) {
      color[v] = 1
      for (i = 1; i <= out_count[v]; i++) { e = outgoing[v,i]; w = edge_to[e]
        if (color[w] == 1) print "B\t" edge_id[e] "\t" edge_from[e] "\t" edge_to[e]
        else if (color[w] != 1 && color[w] != 2) stack_dfs(w)
      }
      color[v] = 2
    }
    END {
      for (i = 1; i <= edge_count; i++) if (edge_from[i] == edge_to[i]) self_edge[edge_from[i]] = 1
      for (i = 1; i <= node_count; i++) if (!(nodes[i] in idx)) tarjan(nodes[i])
      for (i = 1; i <= node_count; i++) if (!(nodes[i] in color)) stack_dfs(nodes[i])
    }
  '
}

classify_cycle() {
  local labels="$1" count="$2"
  if printf '%s\n' "$labels" | grep -Eqi 'retry|backoff|attempt'; then printf retry
  elif printf '%s\n' "$labels" | grep -Eqi 'poll|polling'; then printf polling
  elif printf '%s\n' "$labels" | grep -Eqi 'event|listener|consumer|consume'; then printf event_loop
  elif printf '%s\n' "$labels" | grep -Eqi 'state|transition'; then printf state_cycle
  elif [ "$count" -eq 1 ]; then printf recursive
  else printf unknown
  fi
}

harden_journey() {
  local jrn="$1" max_regions="$2" max_members="$3" max_back_edges="$4" json="$5"
  local tmp graph analysis components joins report candidate_regions=0 candidate_members=0 candidate_back_edges=0
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-scout-cycles.XXXXXX")"; trap 'rm -rf "$tmp"' RETURN
  graph="$tmp/graph.json"; analysis="$tmp/analysis.tsv"; components="$tmp/components.tsv"
  journey materialize "$jrn" > "$graph"
  cycle_analysis "$graph" > "$analysis"
  while IFS=$'\t' read -r type raw; do
    [ "$type" = C ] || continue
    members="$(printf '%s\n' "$raw" | tr ',' '\n' | LC_ALL=C sort | paste -sd, -)"
    member_count="$(printf '%s' "$members" | awk -F, '{ print NF }')"
    printf '%s\t%s\n' "$members" "$member_count" >> "$components"
    candidate_regions=$((candidate_regions + 1)); candidate_members=$((candidate_members + member_count))
  done < "$analysis"
  while IFS=$'\t' read -r type edge from to; do
    [ "$type" = B ] || continue
    while IFS=$'\t' read -r members member_count; do
      if [[ ",$members," == *",$from,"* && ",$members," == *",$to,"* ]]; then candidate_back_edges=$((candidate_back_edges + 1)); break; fi
    done < "$components"
  done < "$analysis"
  joins="$(jq '[.nodes[] as $node | {id:$node.id, incoming:([.edges[] | select(.kind != "LOOP_BACK" and .to == $node.id)] | length)} | select(.incoming > 1)] | sort_by(.id)' "$graph")"
  report="$project_root/.mana/learning/journeys/$jrn/derived/cycle-report.json"
  mkdir -p "$(dirname "$report")"
  if [ "$candidate_regions" -gt "$max_regions" ] || [ "$candidate_members" -gt "$max_members" ] || [ "$candidate_back_edges" -gt "$max_back_edges" ]; then
    reason=max_cycle_regions
    [ "$candidate_regions" -le "$max_regions" ] || reason=max_cycle_regions
    [ "$candidate_regions" -gt "$max_regions" ] || { [ "$candidate_members" -gt "$max_members" ] && reason=max_cycle_members || reason=max_back_edges; }
    jq -cn --arg j "$jrn" --arg reason "$reason" --argjson regions "$candidate_regions" --argjson members "$candidate_members" --argjson back_edges "$candidate_back_edges" --argjson joins "$joins" --argjson max_regions "$max_regions" --argjson max_members "$max_members" --argjson max_back_edges "$max_back_edges" '{schema:"mana.learning.cycle-report/v1",journey_id:$j,status:"budget_exceeded",stop_reason:$reason,detected:{cycle_regions:$regions,cycle_members:$members,back_edges:$back_edges,joins:$joins},budget:{max_cycle_regions:$max_regions,max_cycle_members:$max_members,max_back_edges:$max_back_edges}}' > "$report"
    fail "cycle hardening stopped at budget $reason (journey $jrn)"
  fi
  while IFS=$'\t' read -r members member_count; do
    [ -n "$members" ] || continue
    members_json="$(printf '%s\n' "$members" | tr ',' '\n' | jq -Rsc 'split("\n") | map(select(length > 0))')"
    if jq -e --argjson members "$members_json" 'any(.cycle_regions[]?; (.node_ids | sort) == ($members | sort))' "$graph" >/dev/null; then continue; fi
    labels="$(jq -r --argjson members "$members_json" '.nodes[] | select(.id as $id | $members | index($id)) | .label' "$graph")"
    kind="$(classify_cycle "$labels" "$member_count")"
    entry="$(printf '%s' "$members" | cut -d, -f1)"; back_ids=(); back_args=()
    while IFS=$'\t' read -r type original_edge from to; do
      [ "$type" = B ] || continue
      if [[ ",$members," == *",$from,"* && ",$members," == *",$to,"* ]]; then
        existing="$(jq -r --arg from "$from" --arg to "$to" '.edges[] | select(.kind == "LOOP_BACK" and .from == $from and .to == $to) | .id' "$graph" | head -n 1)"
        if [ -z "$existing" ]; then existing="$(journey add-edge "$jrn" --from "$from" --to "$to" --kind LOOP_BACK)"; fi
        back_ids+=("$existing"); back_args+=(--back-edge "$existing")
      fi
    done < "$analysis"
    [ "${#back_ids[@]}" -gt 0 ] || fail "internal error: cycle has no traversal-stack back edge"
    journey add-cycle-region "$jrn" --entry "$entry" --kind "$kind" --nodes $(printf '%s ' "$members" | tr ',' ' ') "${back_args[@]}" >/dev/null
  done < "$components"
  jq -cn --arg j "$jrn" --argjson regions "$candidate_regions" --argjson members "$candidate_members" --argjson back_edges "$candidate_back_edges" --argjson joins "$joins" --argjson max_regions "$max_regions" --argjson max_members "$max_members" --argjson max_back_edges "$max_back_edges" '{schema:"mana.learning.cycle-report/v1",journey_id:$j,status:"completed",stop_reason:null,detected:{cycle_regions:$regions,cycle_members:$members,back_edges:$back_edges,joins:$joins},budget:{max_cycle_regions:$max_regions,max_cycle_members:$max_members,max_back_edges:$max_back_edges}}' > "$report"
  if [ "$json" = true ]; then jq -cn --arg journey_id "$jrn" --arg report "$report" '{journey_id:$journey_id,report:$report}'; else printf '%s\n' "$jrn"; fi
}

while [ "${1:-}" = "--project-root" ]; do project_root="${2:-}"; need --project-root "$project_root"; shift 2; done
command="${1:-}"; [ -n "$command" ] || { usage; exit 2; }; shift

case "$command" in
  help|--help|-h) usage; exit 0 ;;
  request)
    title=""; route=""; source_root="src/main/java"; out=""; max_nodes=100; max_edges=200; max_depth=30; max_branching=10
    while [ "$#" -gt 0 ]; do case "$1" in
      --title) title="${2:-}"; shift 2;; --path) route="${2:-}"; shift 2;; --source-root) source_root="${2:-}"; shift 2;; --out) out="${2:-}"; shift 2;;
      --max-nodes) max_nodes="${2:-}"; shift 2;; --max-edges) max_edges="${2:-}"; shift 2;; --max-depth) max_depth="${2:-}"; shift 2;; --max-branching-per-node) max_branching="${2:-}"; shift 2;;
      *) fail "unknown request option: $1";; esac; done
    [ -n "$title" ] || fail '--title is required'; [[ "$route" == /* ]] || fail '--path must start with /'
    for n in "$max_nodes" "$max_edges" "$max_depth" "$max_branching"; do positive "$n" || fail 'budgets must be positive integers'; done
    if [ -z "$out" ]; then out="$project_root/.mana/learning/scout-requests/$(new_id).yaml"; fi
    mkdir -p "$(dirname "$out")"
    [ ! -e "$out" ] || fail "request already exists: $out"
    jq -cn --arg id "$(new_id)" --arg title "$title" --arg route "$route" --arg source_root "$source_root" --argjson max_nodes "$max_nodes" --argjson max_edges "$max_edges" --argjson max_depth "$max_depth" --argjson max_branching "$max_branching" '{schema:"mana.learning.scout-request/v1",id:$id,technology:"java-spring-http-v0",title:$title,start:{kind:"http_endpoint",method:"POST",path:$route},termination:{kind:"runtime_effect",condition:"primary_transaction_committed"},source_root:$source_root,budget:{max_nodes:$max_nodes,max_edges:$max_edges,max_depth:$max_depth,max_branching_per_node:$max_branching}}' > "$out"
    printf '%s\n' "$out" ;;
  validate-request)
    [ "${1:-}" = "--request" ] || fail 'validate-request requires --request <file>'; validate_request "${2:-}"; echo 'Scout request is valid' ;;
  run)
    request=""; json=false
    while [ "$#" -gt 0 ]; do case "$1" in --request) request="${2:-}"; shift 2;; --json) json=true; shift;; *) fail "unknown run option: $1";; esac; done
    [ -n "$request" ] || fail '--request is required'; validate_request "$request"
    title="$(jq -r .title "$request")"; route="$(jq -r .start.path "$request")"; source_root="$(jq -r .source_root "$request")"; src="$project_root/$source_root"
    [ -d "$src" ] || fail "source root not found: $source_root"
    max_nodes="$(jq -r .budget.max_nodes "$request")"; max_edges="$(jq -r .budget.max_edges "$request")"; max_depth="$(jq -r .budget.max_depth "$request")"; max_branching="$(jq -r .budget.max_branching_per_node "$request")"
    revision="$(git -C "$project_root" rev-parse --short HEAD 2>/dev/null || printf WORKTREE)"
    jrn="$(journey create --title "$title" --start-kind http_endpoint --start-value "POST $route" --termination-kind runtime_effect --termination-condition primary_transaction_committed --revision "$revision")"
    primary_nodes=(); deferred_nodes=(); stop_reason=""
    # add_node/add_edge are often captured for their generated ID; inspect the
    # persisted append-only inventory so budget state is not lost in a subshell.
    budget_node() { local count; count="$(find "$project_root/.mana/learning/journeys/$jrn/records" -name '*-node.yaml' -type f | wc -l | tr -d ' ')"; if [ "$count" -ge "$max_nodes" ]; then stop_reason=max_nodes; return 1; fi; }
    budget_edge() { local count; count="$(find "$project_root/.mana/learning/journeys/$jrn/records" -name '*-edge.yaml' -type f | wc -l | tr -d ' ')"; if [ "$count" -ge "$max_edges" ]; then stop_reason=max_edges; return 1; fi; }
    budget_depth() { if [ "$1" -gt "$max_depth" ]; then stop_reason=max_depth; return 1; fi; }
    budget_branch() { local count; count="$(find "$project_root/.mana/learning/journeys/$jrn/records" -name '*-edge.yaml' -type f -exec jq -r --arg from "$1" 'select(.from == $from) | .id' {} \; | wc -l | tr -d ' ')"; if [ "$count" -ge "$max_branching" ]; then stop_reason=max_branching_per_node; return 1; fi; }
    add_node() { budget_node || return 1; journey add-node "$jrn" --kind "$1" --label "$2" --disposition "$3"; }
    add_edge() { budget_edge && budget_branch "$1" || return 1; journey add-edge "$jrn" --from "$1" --to "$2" --kind "$3" --disposition "$4" >/dev/null; }
    anchor_node() { journey add-anchor "$jrn" --node "$1" --revision "$revision" --path "$2" --start-line "$3" --end-line "$4" --symbol "$5" >/dev/null; }
    report() { local node_total edge_total; node_total="$(find "$project_root/.mana/learning/journeys/$jrn/records" -name '*-node.yaml' -type f | wc -l | tr -d ' ')"; edge_total="$(find "$project_root/.mana/learning/journeys/$jrn/records" -name '*-edge.yaml' -type f | wc -l | tr -d ' ')"; mkdir -p "$project_root/.mana/learning/journeys/$jrn/derived"; jq -cn --arg j "$jrn" --arg request_id "$(jq -r '.id // ""' "$request")" --arg reason "$stop_reason" --argjson nodes "$node_total" --argjson edges "$edge_total" --argjson deferred "${#deferred_nodes[@]}" --argjson max_nodes "$max_nodes" --argjson max_edges "$max_edges" --argjson max_depth "$max_depth" --argjson max_branching "$max_branching" '{schema:"mana.learning.scout-report/v1",journey_id:$j,request_id:$request_id,status:(if $reason == "" then "completed" else "budget_exceeded" end),stop_reason:(if $reason == "" then null else $reason end),discovered:{nodes:$nodes,edges:$edges,deferred_nodes:$deferred},budget:{max_nodes:$max_nodes,max_edges:$max_edges,max_depth:$max_depth,max_branching_per_node:$max_branching}}' > "$project_root/.mana/learning/journeys/$jrn/derived/scout-report.json"; }
    on_budget() { local current_nodes current_edges; current_nodes="$(find "$project_root/.mana/learning/journeys/$jrn/records" -name '*-node.yaml' -type f | wc -l | tr -d ' ')"; current_edges="$(find "$project_root/.mana/learning/journeys/$jrn/records" -name '*-edge.yaml' -type f | wc -l | tr -d ' ')"; if [ -z "$stop_reason" ]; then if [ "$current_nodes" -ge "$max_nodes" ]; then stop_reason=max_nodes; elif [ "$current_edges" -ge "$max_edges" ]; then stop_reason=max_edges; else stop_reason=unknown_budget; fi; fi; report; echo "ERROR: scout stopped at budget $stop_reason (journey $jrn)" >&2; exit 2; }
    trap 'report' EXIT
    match="$(rg -n --glob '*.java' -F "@PostMapping(\"$route\")" "$src" | LC_ALL=C sort | head -n 1 || true)"
    [ -n "$match" ] || fail "no direct @PostMapping found for POST $route"
    endpoint_file="${match%%:*}"; endpoint_line="${match#*:}"; endpoint_line="${endpoint_line%%:*}"
    controller_line="$(method_after "$endpoint_file" "$endpoint_line")"; [ -n "$controller_line" ] || fail "mapped handler declaration not found for $route"
    controller_end="$(method_end "$endpoint_file" "$controller_line")"; [ -n "$controller_end" ] || fail 'could not bound controller handler'
    controller_method="$(method_name "$endpoint_file" "$controller_line")"; controller_symbol="$(symbol_for "$endpoint_file" "$controller_method")"
    budget_depth 0 || on_budget; endpoint="$(add_node boundary "POST $route endpoint" primary)" || on_budget
    budget_depth 1 || on_budget; controller="$(add_node code "$controller_symbol" primary)" || on_budget
    anchor_node "$endpoint" "${endpoint_file#$project_root/}" "$endpoint_line" "$endpoint_line" "$controller_symbol"
    anchor_node "$controller" "${endpoint_file#$project_root/}" "$controller_line" "$controller_end" "$controller_symbol"
    add_edge "$endpoint" "$controller" EXECUTES primary || on_budget
    calls="$(sed -n "${controller_line},${controller_end}p" "$endpoint_file" | grep -Eo '[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*[[:space:]]*\(' | sed -E 's/[[:space:]]*\($//' | LC_ALL=C sort -u || true)"
    service_call="$(printf '%s\n' "$calls" | head -n 1)"; [ -n "$service_call" ] || fail "controller $controller_symbol has no resolvable method call"
    service_method="${service_call#*.}"
    service_file="$(rg -l --glob '*.java' -e "(public|protected|private)[^;]*[[:space:]]${service_method}[[:space:]]*\\(" "$src" | LC_ALL=C sort | head -n 1 || true)"; [ -n "$service_file" ] || fail "no Java declaration found for $service_call"
    service_line="$(rg -n -e "(public|protected|private)[^;]*[[:space:]]${service_method}[[:space:]]*\\(" "$service_file" | head -n 1 | cut -d: -f1)"; service_end="$(method_end "$service_file" "$service_line")"; service_symbol="$(symbol_for "$service_file" "$service_method")"
    budget_depth 2 || on_budget; service="$(add_node code "$service_symbol" primary)" || on_budget; primary_nodes+=("$endpoint" "$controller" "$service")
    anchor_node "$service" "${service_file#$project_root/}" "$service_line" "$service_end" "$service_symbol"; add_edge "$controller" "$service" CALLS primary || on_budget
    repo_calls="$(sed -n "${service_line},${service_end}p" "$service_file" | grep -Eo '[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*[[:space:]]*\(' | sed -E 's/[[:space:]]*\($//' | LC_ALL=C sort -u || true)"
    repo_call="$(printf '%s\n' "$repo_calls" | head -n 1)"; [ -n "$repo_call" ] || fail "service $service_symbol has no resolvable repository/external call"
    repo_method="${repo_call#*.}"
    repo_file="$(rg -l --glob '*.java' -e "(public|protected|private)[^;]*[[:space:]]${repo_method}[[:space:]]*\\(" "$src" | grep -E '(Repository|Dao)' | LC_ALL=C sort | head -n 1 || true)"
    if [ -z "$repo_file" ]; then repo_file="$(rg -l --glob '*.java' -e "(public|protected|private)[^;]*[[:space:]]${repo_method}[[:space:]]*\\(" "$src" | LC_ALL=C sort | head -n 1 || true)"; fi
    [ -n "$repo_file" ] || fail "no Java declaration found for $repo_call"
    repo_line="$(rg -n -e "(public|protected|private)[^;]*[[:space:]]${repo_method}[[:space:]]*\\(" "$repo_file" | head -n 1 | cut -d: -f1)"; repo_end="$(method_end "$repo_file" "$repo_line")"; repo_symbol="$(symbol_for "$repo_file" "$repo_method")"
    budget_depth 3 || on_budget; repo="$(add_node code "$repo_symbol" primary)" || on_budget; primary_nodes+=("$repo")
    anchor_node "$repo" "${repo_file#$project_root/}" "$repo_line" "$repo_end" "$repo_symbol"; add_edge "$service" "$repo" CALLS primary || on_budget
    if ! sed -n "1,${service_end}p" "$service_file" | grep -q '@Transactional'; then fail "service $service_symbol is not annotated @Transactional"; fi
    budget_depth 4 || on_budget; commit="$(add_node runtime_effect 'primary transaction commit' primary)" || on_budget; primary_nodes+=("$commit")
    add_edge "$repo" "$commit" EXECUTES primary || on_budget
    commit_evidence="$(journey add-evidence "$jrn" --kind runtime_semantic --summary "Spring commits the primary transaction after $service_symbol returns.")"
    journey add-traversal "$jrn" --kind execution --entry "$endpoint" --nodes "${primary_nodes[@]}" >/dev/null
    while IFS= read -r async_file; do
      [ -n "$async_file" ] || continue
      async_line="$(rg -n -F 'TransactionPhase.AFTER_COMMIT' "$async_file" | head -n 1 | cut -d: -f1)"; async_method_line="$(method_after "$async_file" "$async_line")"; async_end="$(method_end "$async_file" "$async_method_line")"; async_method="$(method_name "$async_file" "$async_method_line")"; async_symbol="$(symbol_for "$async_file" "$async_method")"
      deferred="$(add_node code "$async_symbol" deferred)" || on_budget; deferred_nodes+=("$deferred")
      anchor_node "$deferred" "${async_file#$project_root/}" "$async_method_line" "$async_end" "$async_symbol"; add_edge "$commit" "$deferred" EXECUTES deferred || on_budget
    done < <(rg -l --glob '*.java' -F 'TransactionPhase.AFTER_COMMIT' "$src" | LC_ALL=C sort || true)
    trap - EXIT; report
    if [ "$json" = true ]; then jq -cn --arg journey_id "$jrn" --arg report "$project_root/.mana/learning/journeys/$jrn/derived/scout-report.json" '{journey_id:$journey_id,report:$report}'; else printf '%s\n' "$jrn"; fi
    ;;
  harden)
    jrn="${1:-}"; shift || true; [ -n "$jrn" ] || fail 'harden requires a journey id'
    max_regions=20; max_members=100; max_back_edges=100; json=false
    while [ "$#" -gt 0 ]; do case "$1" in
      --max-cycle-regions) max_regions="${2:-}"; shift 2;; --max-cycle-members) max_members="${2:-}"; shift 2;; --max-back-edges) max_back_edges="${2:-}"; shift 2;; --json) json=true; shift;; *) fail "unknown harden option: $1";;
    esac; done
    for n in "$max_regions" "$max_members" "$max_back_edges"; do positive "$n" || fail 'cycle budgets must be positive integers'; done
    harden_journey "$jrn" "$max_regions" "$max_members" "$max_back_edges" "$json"
    ;;
  *) fail "unknown scout command: $command" ;;
esac
