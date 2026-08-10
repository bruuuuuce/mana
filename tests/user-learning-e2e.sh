#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-learning-e2e.XXXXXX")"
trap 'chmod -R u+w "$tmp" 2>/dev/null || true; rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

state="$tmp/host-state"; source="$tmp/external-context"; stub="$tmp/t1-stub"
mkdir -p "$source"
printf '%s\n' 'This manually authored User Context guidance must remain unchanged.' > "$source/manual.md"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$M3_STUB_RESPONSE"' 'printf x >> "$M3_STUB_CALLS"' > "$stub"
chmod +x "$stub"

make_project() {
  local name="$1" subject="$2" choice="$3" evidence="$4" project log
  project="$tmp/$name"; log="$project/.mana/features/$name/decisions/developer-choice-log.md"
  mkdir -p "$(dirname "$log")" "$project/.mana/learning/candidates"
  printf '%s\n' '{"schemaVersion":"2","candidateId":"project-local-fixture","status":"candidate","evidenceReferences":[],"executions":[]}' > "$project/.mana/learning/candidates/project-local-fixture.json"
  cat > "$log" <<EOF
# Developer Choice Log

## Choices

| Date | Story | Area | Question Or Choice | Developer Answer | Evidence | Confirmed By | Status | Follow-Up |
|---|---|---|---|---|---|---|---|---|
| 2026-08-08 | $name | reliability | $subject | $choice | $evidence | developer@example.test | confirmed | |
EOF
  git -C "$project" init -q
  git -C "$project" remote add origin "https://example.test/mana/$name.git"
}

make_project PROJECT-A 'Async failure handling' 'durable retry' 'Failures must remain recoverable.'
make_project PROJECT-B 'Async failure handling' 'durable retry' 'Work loss must be observable.'
make_project PROJECT-C 'Failure strategy for async work' 'persistent recoverable execution' 'Avoid fire-and-forget when correctness depends on eventual completion.'
project_a="$tmp/PROJECT-A"; local_candidate_before="$(cksum "$project_a/.mana/learning/candidates/project-local-fixture.json")"

capture() { MANA_USER_STATE_HOME="$state" MANA_USER_CONTEXT_ROOT="$source" "$root/scripts/mana-user-learning.sh" --project-root "$1" capture --json; }
capture "$tmp/PROJECT-A" | jq -e '.modelCalls==0 and .newlyStored==1' >/dev/null || fail 'M1 capture A failed'
capture "$tmp/PROJECT-B" | jq -e '.modelCalls==0 and .newlyStored==1' >/dev/null || fail 'M1 capture B failed'
capture "$tmp/PROJECT-C" | jq -e '.modelCalls==0 and .newlyStored==1' >/dev/null || fail 'M1 capture C failed'
signals_before="$(find "$state/user-learning/signals" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"

aggregate() { MANA_USER_STATE_HOME="$state" "$root/scripts/mana-user-learning.sh" --project-root "$project_a" aggregate --json; }
aggregate | jq -e '.modelCalls==0 and .clustersProduced==2 and .distinctProjects==3' >/dev/null || fail 'M2 aggregation did not produce expected derived clusters'
clusters_before="$(find "$state/user-learning/clusters" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"
jq -e '.derivation.modelCalls==0 and .derivation.processor=="deterministic-user-learning-aggregation-v1"' "$state/user-learning/clusters"/*.json >/dev/null || fail 'M2 clusters are not deterministic derived-only artifacts'

cluster_ids="$(jq -sc '[.[].clusterId]|sort' "$state/user-learning/clusters"/*.json)"
signal_ids="$(jq -sc '[.[].supportingSignalIds[]]|sort' "$state/user-learning/clusters"/*.json)"
response="$(jq -cn --argjson clusters "$cluster_ids" --argjson signals "$signal_ids" '{result:"CANDIDATE",guidance:"Prefer durable, observable recovery when asynchronous work loss affects correctness.",scope:"reliability",rationale:"The supplied decisions explicitly choose recoverable execution across projects.",limitations:["Applies only where preserving work affects correctness."],relatedClusterIds:$clusters,supportingSignalIds:$signals}')"
synthesize() { MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" MANA_USER_LEARNING_MAX_CLUSTERS_PER_UNIT=2 MANA_USER_LEARNING_MAX_SIGNALS_PER_CLUSTER=2 M3_STUB_RESPONSE="$response" M3_STUB_CALLS="$tmp/t1-calls" "$root/scripts/mana-user-learning.sh" --project-root "$project_a" synthesize --json; }
first_synthesis="$(synthesize)"
printf '%s' "$first_synthesis" | jq -e '.modelCalls==1 and .candidateResults==1 and .providerFailures==0' >/dev/null || fail 'M3 did not make exactly one bounded fake-provider invocation'
[ "$(wc -c < "$tmp/t1-calls" | tr -d ' ')" = 1 ] || fail 'M3 fake provider invocation count is not bounded'
candidate_file="$(find "$state/user-learning/candidates" -type f -name '*.json' -print -quit)"; candidate_before="$(shasum -a 256 "$candidate_file" | awk '{print $1}')"; candidate_id="$(jq -r .candidateId "$candidate_file")"
jq -e --argjson clusters "$cluster_ids" '(.sourceClusterIds == $clusters) and (.supportingSignalIds|length)>=2' "$candidate_file" >/dev/null || fail 'M3 candidate provenance is incomplete'
jq -se --argjson candidate "$(cat "$candidate_file")" '([.[] | select(.clusterId as $id | ($candidate.sourceClusterIds | index($id))) | .supportingSignalIds[]] | unique) as $available | ($candidate.supportingSignalIds - $available | length)==0' "$state/user-learning/clusters"/*.json >/dev/null || fail 'M4 to M3 to M2 to M1 provenance is not resolvable'

run_m4() { MANA_USER_STATE_HOME="$state" MANA_USER_CONTEXT_ROOT="$source" "$root/scripts/mana-user-learning.sh" --project-root "$project_a" "$@"; }
review="$(run_m4 review "$candidate_id" --edit 'Prefer durable recovery only when loss affects correctness.' --scope reliability --json)"; review_id="$(printf '%s' "$review" | jq -r .review.reviewId)"
printf '%s' "$review" | jq -e '.modelCalls==0 and .review.action=="EDIT_AND_ACCEPT"' >/dev/null || fail 'M4 review made a model call or did not record human edit'
[ "$candidate_before" = "$(shasum -a 256 "$candidate_file" | awk '{print $1}')" ] || fail 'human review mutated original M3 candidate'
promotion="$(run_m4 promote "$review_id" --json)"
printf '%s' "$promotion" | jq -e '.modelCalls==0 and .refreshSucceeded and .promotion.status=="promoted"' >/dev/null || fail 'M4 promotion/refresh failed'
entry_id="$(printf '%s' "$promotion" | jq -r .promotion.entryId)"; entry="$source/learned/$entry_id.md"
grep -Fq 'Prefer durable recovery only when loss affects correctness.' "$entry" || fail 'human-reviewed guidance was not promoted'
if grep -Eq 'supportingSignalIds|sourceArtifact|user-choice-' "$entry"; then fail 'external active guidance contains full audit evidence'; fi
grep -Fq 'Prefer durable recovery only when loss affects correctness.' "$project_a/.mana/user-context/learned/$entry_id.md" || fail 'existing User Context refresh did not materialize promoted entry'
grep -Fxq 'This manually authored User Context guidance must remain unchanged.' "$source/manual.md" || fail 'manual User Context was modified'
[ "$local_candidate_before" = "$(cksum "$project_a/.mana/learning/candidates/project-local-fixture.json")" ] || fail 'project-local governed learning changed'
[ "$signals_before" = "$(find "$state/user-learning/signals" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)" ] || fail 'M1 source signals changed during M3/M4'
[ "$clusters_before" = "$(find "$state/user-learning/clusters" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)" ] || fail 'M2 clusters changed during M3/M4'

# Re-running the completed lifecycle is cache/idempotency only: no duplicate
# evidence, derived state, candidates, reviews, promotions, or provider calls.
capture "$tmp/PROJECT-A" | jq -e '.newlyStored==0 and .alreadyKnown==1' >/dev/null || fail 'rerun capture duplicated M1 signal'
capture "$tmp/PROJECT-B" | jq -e '.newlyStored==0 and .alreadyKnown==1' >/dev/null || fail 'rerun capture duplicated M1 signal'
capture "$tmp/PROJECT-C" | jq -e '.newlyStored==0 and .alreadyKnown==1' >/dev/null || fail 'rerun capture duplicated M1 signal'
aggregate >/dev/null
second_synthesis="$(synthesize)"; printf '%s' "$second_synthesis" | jq -e '.modelCalls==0 and .unitsAlreadySynthesized==1' >/dev/null || fail 'completed flow rerun invoked fake provider'
# A promoted fingerprint intentionally cannot be reviewed again (there is no
# supersession lifecycle); inspect it instead, then repeat the idempotent step.
run_m4 show "$candidate_id" --json | jq -e '.candidate.promoted==true' >/dev/null || fail 'completed review/promotion state is not discoverable'
run_m4 promote "$review_id" --json | jq -e '.promotion.status=="promoted"' >/dev/null || fail 'completed flow rerun was not idempotently promoted'
[ "$(find "$state/user-learning/signals" -type f | wc -l | tr -d ' ')" = 3 ] || fail 'rerun duplicated signals'
[ "$(find "$state/user-learning/clusters" -type f | wc -l | tr -d ' ')" = 2 ] || fail 'rerun duplicated clusters'
[ "$(find "$state/user-learning/candidates" -type f | wc -l | tr -d ' ')" = 1 ] || fail 'rerun duplicated candidates'
[ "$(find "$state/user-learning/reviews" -type f | wc -l | tr -d ' ')" = 1 ] || fail 'rerun duplicated reviews'
[ "$(find "$state/user-learning/promotions" -type f | wc -l | tr -d ' ')" = 1 ] || fail 'rerun duplicated promotions'

echo 'User Learning end-to-end acceptance test passed'
