#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-scout.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
fixture="$root/tests/fixtures/mana-learning-scout-v0"
fail() { echo "FAIL: $*" >&2; exit 1; }

mkdir -p "$project"
cp -R "$fixture/src" "$project/"
scout() { "$root/scripts/mana-scout.sh" --project-root "$project" "$@"; }
request="$tmp/payment-request.yaml"
scout request --title 'Trace payment authorization' --path /payments --out "$request"
scout validate-request --request "$request" >/dev/null

jrn="$(scout run --request "$request")"
[[ "$jrn" =~ ^jrn_[a-f0-9]{24}$ ]] || fail 'scout did not return a host-generated Journey ID'
graph="$tmp/graph.json"
"$root/scripts/mana-journey.sh" --project-root "$project" materialize "$jrn" > "$graph"

# The requested route is a bounded primary traversal. The post-commit listener
# exists in the graph only as a deferred branch and no unrelated handler/work is
# expanded.
jq -e '
  .journey.scope.start.value == "POST /payments" and
  .journey.scope.termination.condition == "primary_transaction_committed" and
  ([.nodes[].label] | index("POST /payments endpoint")) and
  ([.nodes[].label] | index("PaymentController.createPayment")) and
  ([.nodes[].label] | index("PaymentService.authorize")) and
  ([.nodes[].label] | index("PaymentRepository.save")) and
  ([.nodes[].label] | index("primary transaction commit")) and
  ([.nodes[] | select(.disposition == "deferred") | .label] | index("PaymentNotifications.notifyCustomer")) and
  ([.nodes[] | select(.disposition == "deferred") | .label] | index("PaymentAudit.recordAuditEntry")) and
  ([.nodes[].label] | index("PaymentController.unrelated") | not) and
  ([.nodes[].label] | index("PaymentService.unrelatedWork") | not) and
  (.anchors | length == 6) and
  (.traversals | length == 1) and
  (.traversals[0].node_ids | length == 5) and
  ([.edges[] | select(.disposition == "deferred")] | length == 2) and
  ([.evidence[] | select(.kind == "runtime_semantic")] | length == 1)
' "$graph" >/dev/null || fail 'scout graph does not contain the bounded Spring request flow'

report="$project/.mana/learning/journeys/$jrn/derived/scout-report.json"
jq -e '.status == "completed" and .stop_reason == null and .discovered.deferred_nodes == 2' "$report" >/dev/null || fail 'scout report is incomplete'
first="$tmp/first.json"; second="$tmp/second.json"
"$root/scripts/mana-journey.sh" --project-root "$project" materialize "$jrn" > "$first"
"$root/scripts/mana-journey.sh" --project-root "$project" materialize "$jrn" > "$second"
cmp -s "$first" "$second" || fail 'scout Journey materialization is not deterministic'

# A small bound must stop explicitly rather than scanning an unrelated region.
limited="$tmp/limited.yaml"
scout request --title 'Bounded trace' --path /payments --out "$limited" --max-nodes 2
find "$project/.mana/learning/journeys" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort > "$tmp/journeys-before"
if scout run --request "$limited" >/dev/null 2>&1; then fail 'node budget was not enforced'; fi
find "$project/.mana/learning/journeys" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort > "$tmp/journeys-after"
limited_jrn="$(comm -13 "$tmp/journeys-before" "$tmp/journeys-after" | xargs basename)"
[ -n "$limited_jrn" ] || fail 'budget run did not create a reportable Journey'
jq -e '.status == "budget_exceeded" and .stop_reason == "max_nodes"' "$project/.mana/learning/journeys/$limited_jrn/derived/scout-report.json" >/dev/null || fail 'budget stop reason was not persisted'

depth_limited="$tmp/depth-limited.yaml"
scout request --title 'Depth-bounded trace' --path /payments --out "$depth_limited" --max-depth 3
find "$project/.mana/learning/journeys" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort > "$tmp/journeys-before-depth"
if scout run --request "$depth_limited" >/dev/null 2>&1; then fail 'depth budget was not enforced'; fi
find "$project/.mana/learning/journeys" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort > "$tmp/journeys-after-depth"
depth_jrn="$(comm -13 "$tmp/journeys-before-depth" "$tmp/journeys-after-depth" | xargs basename)"
jq -e '.status == "budget_exceeded" and .stop_reason == "max_depth"' "$project/.mana/learning/journeys/$depth_jrn/derived/scout-report.json" >/dev/null || fail 'depth stop reason was not persisted'

branch_limited="$tmp/branch-limited.yaml"
scout request --title 'Branch-bounded trace' --path /payments --out "$branch_limited" --max-branching-per-node 1
find "$project/.mana/learning/journeys" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort > "$tmp/journeys-before-branch"
if scout run --request "$branch_limited" >/dev/null 2>&1; then fail 'branch budget was not enforced'; fi
find "$project/.mana/learning/journeys" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort > "$tmp/journeys-after-branch"
branch_jrn="$(comm -13 "$tmp/journeys-before-branch" "$tmp/journeys-after-branch" | xargs basename)"
jq -e '.status == "budget_exceeded" and .stop_reason == "max_branching_per_node"' "$project/.mana/learning/journeys/$branch_jrn/derived/scout-report.json" >/dev/null || fail 'branch stop reason was not persisted'

edge_limited="$tmp/edge-limited.yaml"
scout request --title 'Edge-bounded trace' --path /payments --out "$edge_limited" --max-edges 2
find "$project/.mana/learning/journeys" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort > "$tmp/journeys-before-edge"
if scout run --request "$edge_limited" >/dev/null 2>&1; then fail 'edge budget was not enforced'; fi
find "$project/.mana/learning/journeys" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort > "$tmp/journeys-after-edge"
edge_jrn="$(comm -13 "$tmp/journeys-before-edge" "$tmp/journeys-after-edge" | xargs basename)"
jq -e '.status == "budget_exceeded" and .stop_reason == "max_edges"' "$project/.mana/learning/journeys/$edge_jrn/derived/scout-report.json" >/dev/null || fail 'edge stop reason was not persisted'

echo 'Mana Scout v0 acceptance tests passed'
