#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"; tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-learning-review.XXXXXX")"; trap 'chmod -R u+w "$tmp" 2>/dev/null || true; rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }; hex() { printf '%064d' "$1"; }
project="$tmp/project"; state="$tmp/state"; source="$tmp/context-source"; signals="$state/user-learning/signals"; mkdir -p "$project" "$signals" "$source"
write_signal() { local n p subject choice id project_id; n="$1"; p="$2"; subject="$3"; choice="$4"; id="user-choice-$(hex "$n")"; project_id="project-$(hex "$p")"; jq -cn --arg id "$id" --arg project "$project_id" --arg subject "$subject" --arg choice "$choice" --arg hash "$(hex 99)" --argjson n "$n" '{schemaVersion:"2",signalId:$id,sourceProject:{projectId:$project,repositoryRoot:"/fixture"},sourceDecision:{reference:(".mana/features/F/decisions/developer-choice-log.md#choice-"+($n|tostring)),logPath:".mana/features/F/decisions/developer-choice-log.md",line:$n,choiceOrdinal:$n,status:"confirmed",subject:$subject,confirmedChoice:$choice,confirmedBy:"developer"},provenance:{sourceType:"developer-choice-log",sourceArtifact:{path:".mana/features/F/decisions/developer-choice-log.md",sha256:$hash},evidence:["fixture"]},capture:{processor:"deterministic-developer-choice-log-v1",modelCalls:0,capturedAt:"2026-08-08T00:00:00Z"}}' > "$signals/$id.json"; }
write_signal 1 1 'Async failure handling' 'durable retry'; write_signal 2 2 'Async failure handling' 'durable retry'; write_signal 3 3 'Failure strategy for async work' 'persistent recovery'
MANA_USER_STATE_HOME="$state" "$root/scripts/mana-user-learning.sh" --project-root "$project" aggregate >/dev/null
clusters="$(jq -sc '[.[].clusterId]|sort' "$state/user-learning/clusters"/*.json)"; supported="$(jq -sc '[.[].supportingSignalIds[]]|sort' "$state/user-learning/clusters"/*.json)"
make_candidate() { local n fp file; n="$1"; fp="m3-input-$(hex "$2")"; file="$state/user-learning/candidates/user-context-candidate-$(hex "$n").json"; mkdir -p "$(dirname "$file")"; jq -cn --arg id "user-context-candidate-$(hex "$n")" --arg fp "$fp" --argjson clusters "$clusters" --argjson signals "$supported" '{schemaVersion:"1",kind:"user-context-candidate",candidateId:$id,synthesisVersion:"m3-bounded-semantic-synthesis-v1",lifecycleState:"proposed",guidance:"Prefer durable recovery.",scope:"reliability",sourceClusterIds:$clusters,supportingSignalIds:$signals,supportingProjectIds:["project-0000000000000000000000000000000000000000000000000000000000000001","project-0000000000000000000000000000000000000000000000000000000000000002"],counterEvidence:[],synthesis:{modelTier:"T1",provider:"stub",model:"fixture",inputFingerprint:$fp,invocation:{count:1},rationale:"fixture",limitations:[]},createdAt:"2026-08-08T00:00:00Z",updatedAt:"2026-08-08T00:00:00Z"}' > "$file"; }
make_candidate 1 11; candidate="user-context-candidate-$(hex 1)"
run() { MANA_USER_STATE_HOME="$state" MANA_USER_CONTEXT_ROOT="$source" "$root/scripts/mana-user-learning.sh" --project-root "$project" "$@"; }

# Inspection, unrelated commands, refresh, and omitted intent never promote.
run candidates --json | jq -e '.modelCalls==0 and .candidates[0].reviewState=="PENDING"' >/dev/null || fail 'candidate inspection missing pending state'
run show "$candidate" --json | jq -e '.modelCalls==0 and .candidate.supportingSignalCount==3' >/dev/null || fail 'candidate show missing provenance'
if run review "$candidate" --json >/dev/null 2>&1; then fail 'missing review action defaulted'; fi
MANA_USER_CONTEXT_ROOT="$source" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null
[ ! -e "$source/learned" ] || fail 'refresh implicitly promoted'

# Human edit remains separate from the M3 proposal and needs a second explicit promotion command.
review="$(run review "$candidate" --edit 'Prefer durable recovery only when loss affects correctness.' --scope reliability --json)"; review_id="$(printf '%s' "$review" | jq -r .review.reviewId)"
printf '%s' "$review" | jq -e '.modelCalls==0 and .review.action=="EDIT_AND_ACCEPT" and .promotionRequired==true' >/dev/null || fail 'edit review failed'
jq -e '.guidance=="Prefer durable recovery."' "$state/user-learning/candidates/$candidate.json" >/dev/null || fail 'review mutated original candidate'
[ ! -e "$source/learned" ] || fail 'review implicitly promoted'
dry="$(run promote "$review_id" --dry-run --json)"; printf '%s' "$dry" | jq -e '.dryRun and .modelCalls==0 and .targetState=="new"' >/dev/null || fail 'promotion dry-run failed'; [ ! -e "$source/learned" ] || fail 'dry-run mutated source'
promoted="$(run promote "$review_id" --json)"; printf '%s' "$promoted" | jq -e '.modelCalls==0 and .refreshSucceeded and .promotion.status=="promoted"' >/dev/null || fail 'accepted review did not promote'
grep -Fq 'Prefer durable recovery only when loss affects correctness.' "$source/learned"/*.md || fail 'human edit not in external source'
grep -Fq 'Prefer durable recovery only when loss affects correctness.' "$project/.mana/user-context/learned"/*.md || fail 'existing refresh did not materialize promoted entry'
[ "$(find "$source/learned" -type f | wc -l | tr -d ' ')" = 1 ] || fail 'wrong managed entry count'
entry_id="$(printf '%s' "$promoted" | jq -r .promotion.entryId)"; entry_file="$source/learned/$entry_id.md"
[[ "${entry_file##*/}" =~ ^user-learning-entry-[0-9a-f]{64}\.md$ ]] || fail 'managed filename omitted stable promotion identity'
[ -f "$entry_file" ] && [ "$(wc -c < "$entry_file" | tr -d ' ')" -le 2048 ] || fail 'promoted User Context entry is not compact'
grep -Fq "reviewId: $review_id" "$entry_file" || fail 'compact promoted entry lost bounded provenance'
if grep -Eq 'supportingSignalIds|alternativeConfirmedEvidence|sourceArtifact|user-choice-' "$entry_file"; then fail 'promoted entry injected the M1/M2/M3 audit payload'; fi
run promote "$review_id" --json | jq -e '.promotion.status=="promoted"' >/dev/null || fail 'repeat promotion was not idempotent'
[ "$(find "$source/learned" -type f | wc -l | tr -d ' ')" = 1 ] || fail 'repeat promotion duplicated entry'
if run promote 'review-' --json >/dev/null 2>&1; then fail 'empty/malformed review identity resolved to a managed target'; fi

# Changed M3 evidence means the old acceptance cannot be promoted again.
jq '.synthesis.inputFingerprint="m3-input-" + ("0" * 63) + "9"' "$state/user-learning/candidates/$candidate.json" > "$tmp/candidate-change"; mv "$tmp/candidate-change" "$state/user-learning/candidates/$candidate.json"
if run promote "$review_id" --json >/dev/null 2>&1; then fail 'stale review was promoted'; fi
run candidates --json | jq -e '.candidates[0].reviewState=="PENDING"' >/dev/null || fail 'changed evidence reused old review'

# Rejection and deferral are persisted lifecycle decisions, never negative learning or source writes.
reject="$(run review "$candidate" --reject --json)"; printf '%s' "$reject" | jq -e '.review.action=="REJECT" and .modelCalls==0' >/dev/null || fail 'reject failed'
[ "$(find "$source/learned" -type f | wc -l | tr -d ' ')" = 1 ] || fail 'reject changed source'
if run review "$candidate" --accept --json >/dev/null 2>&1; then fail 'rejected candidate accepted without explicit override'; fi
make_candidate 2 12; candidate2="user-context-candidate-$(hex 2)"; run review "$candidate2" --defer --json | jq -e '.review.action=="DEFER" and .modelCalls==0' >/dev/null || fail 'defer failed'
run candidates --json | jq -e '[.candidates[]|select(.candidateId==$id)|.reviewState][0]=="DEFER"' --arg id "$candidate2" >/dev/null || fail 'deferred candidate not discoverable'

# A manually-owned target collision fails closed.
make_candidate 3 13; candidate3="user-context-candidate-$(hex 3)"; review3="$(run review "$candidate3" --accept --json)"; review3_id="$(printf '%s' "$review3" | jq -r .review.reviewId)"; entry3="user-learning-entry-$(jq -cn --arg review "$review3_id" '{identityVersion:"1",reviewId:$review}' | tr -d '\n' | shasum -a 256 | awk '{print $1}')"; printf '%s\n' 'manual context file' > "$source/learned/$entry3.md"
if run promote "$review3_id" --json >/dev/null 2>&1; then fail 'manual managed-target collision was overwritten'; fi
grep -Fxq 'manual context file' "$source/learned/$entry3.md" || fail 'manual collision content changed'

# Refresh failure reports a precise partial state: source survives, mirror is not directly written.
make_candidate 4 14; candidate4="user-context-candidate-$(hex 4)"; review4="$(run review "$candidate4" --accept --json)"; review4_id="$(printf '%s' "$review4" | jq -r .review.reviewId)"; mkdir -p "$project/.mana/user-context-refresh.lock"; printf '%s\n' "$$" > "$project/.mana/user-context-refresh.lock/pid"
partial="$(run promote "$review4_id" --json || true)"; printf '%s' "$partial" | jq -e '.refreshSucceeded==false and .promotion.status=="source_published_refresh_failed"' >/dev/null || fail 'refresh failure was not reported precisely'
rm -rf "$project/.mana/user-context-refresh.lock"; find "$source/learned" -type f -name '*.md' -exec grep -Fl "$review4_id" {} + | grep -q . || fail 'source entry lost after refresh failure'

# Different accepted reviews have different stable targets, and refresh keeps
# the managed entry compact rather than expanding it into its audit chain.
make_candidate 5 15; candidate5="user-context-candidate-$(hex 5)"; review5="$(run review "$candidate5" --accept --json)"; review5_id="$(printf '%s' "$review5" | jq -r .review.reviewId)"; promoted5="$(run promote "$review5_id" --json)"; entry5="$(printf '%s' "$promoted5" | jq -r .promotion.entryId)"
[ "$entry5" != "$entry_id" ] || fail 'separate accepted reviews resolved to the same managed target'
[ -f "$source/learned/$entry5.md" ] || fail 'separate accepted review did not create its managed target'
[ "$(wc -c < "$project/.mana/user-context/learned/$entry5.md" | tr -d ' ')" -le 2048 ] || fail 'refresh expanded managed entry into full audit payload'

echo 'User Learning review tests passed'
