#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-history.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

project="$tmp/project"
mkdir -p "$project/src/legacy"
git -C "$project" init -q
git -C "$project" config user.email test@mana.local
git -C "$project" config user.name 'Mana Test'
git -C "$project" config commit.gpgsign false
printf 'class PaymentRouter { void dispatch() {} }\n' > "$project/src/legacy/PaymentRouter.java"
git -C "$project" add src/legacy/PaymentRouter.java
git -C "$project" commit -qm 'Introduce payment router'
mkdir -p "$project/src/payments"
git -C "$project" mv src/legacy/PaymentRouter.java src/payments/PaymentRouter.java
git -C "$project" commit -qm 'Move payment router into payments package'
printf 'class PaymentRouter { void dispatch() { retry(); } }\n' > "$project/src/payments/PaymentRouter.java"
git -C "$project" add src/payments/PaymentRouter.java
git -C "$project" commit -qm 'Add retry dispatch behavior'

journey() { "$root/scripts/mana-journey.sh" --project-root "$project" "$@"; }
jrn="$(journey create --title history --start-kind symbol --start-value PaymentRouter.dispatch --termination-kind code --termination-condition done --revision HEAD)"
node="$(journey add-node "$jrn" --kind code --label PaymentRouter.dispatch)"
anchor="$(journey add-anchor "$jrn" --node "$node" --revision HEAD --path src/payments/PaymentRouter.java --start-line 1 --end-line 1 --symbol dispatch)"
source_evidence="$(journey add-evidence "$jrn" --kind source_range --anchor "$anchor" --summary 'Current router implementation.')"
hypothesis="$(journey add-hypothesis "$jrn" --subject "$node" --claim 'The router may preserve a compatibility boundary.' --supports "$source_evidence")"

"$root/scripts/mana-history.sh" --project-root "$project" enrich --journey "$jrn" --node "$node" --anchor "$anchor" --max-commits 10 --hypothesis "$hypothesis" --effect strengthens --reason 'The move commit shows the boundary was retained during package reorganization.' >/dev/null
graph="$tmp/graph.json"
journey materialize "$jrn" > "$graph"
jq -e --arg node "$node" --arg hypothesis "$hypothesis" '(.git_enrichments | length == 1 and .[0].status == "completed") and (.timeline_events | length >= 3) and (.timeline_events | all(.subject_node_id == $node)) and ([.evidence[] | select(.kind == "git_commit")] | length >= 3) and ([.anchors[] | select(.node_id == $node) | .path] | index("src/legacy/PaymentRouter.java") != null) and (.hypothesis_assessments | length == 1 and .[0].hypothesis_id == $hypothesis and .[0].effect == "strengthens")' "$graph" >/dev/null || fail 'Git history did not preserve historical anchors, evidence, timeline events, and assessment'
journey validate "$jrn" >/dev/null

# A project without Git still records a non-fatal failed enrichment.
nogit="$tmp/no-git"
no_jrn="$("$root/scripts/mana-journey.sh" --project-root "$nogit" create --title no-git --start-kind symbol --start-value x --termination-kind code --termination-condition done)"
no_node="$("$root/scripts/mana-journey.sh" --project-root "$nogit" add-node "$no_jrn" --kind code)"
no_anchor="$("$root/scripts/mana-journey.sh" --project-root "$nogit" add-anchor "$no_jrn" --node "$no_node" --revision WORKTREE --path source.txt --start-line 1 --end-line 1)"
"$root/scripts/mana-history.sh" --project-root "$nogit" enrich --journey "$no_jrn" --node "$no_node" --anchor "$no_anchor" >/dev/null
"$root/scripts/mana-journey.sh" --project-root "$nogit" materialize "$no_jrn" | jq -e '(.git_enrichments | length == 1 and .[0].status == "failed") and (.timeline_events | length == 0)' >/dev/null || fail 'Git failure invalidated the Journey instead of recording a failed enrichment'
"$root/scripts/mana-journey.sh" --project-root "$nogit" validate "$no_jrn" >/dev/null

echo 'Mana Git archaeology v0 acceptance tests passed'
