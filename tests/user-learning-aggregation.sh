#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-learning-aggregation.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

project="$tmp/project"
state="$tmp/host-state"
signals="$state/user-learning/signals"
mkdir -p "$project/.mana/user-context" "$signals"
printf '%s\n' 'unchanged User Context fixture' > "$project/.mana/user-context/preferences.md"

hex() { printf '%064d' "$1"; }
write_signal() {
  local number="$1" project_number="$2" subject="$3" choice="$4" ordinal="$5" id project_id source_hash
  id="user-choice-$(hex "$number")"; project_id="project-$(hex "$project_number")"; source_hash="$(hex 99)"
  jq -cn --arg id "$id" --arg project "$project_id" --arg subject "$subject" --arg choice "$choice" --argjson ordinal "$ordinal" --arg source_hash "$source_hash" \
    '{schemaVersion:"2",signalId:$id,sourceProject:{projectId:$project,repositoryRoot:"/fixture/project"},sourceDecision:{reference:(".mana/features/F/decisions/developer-choice-log.md#choice-" + ($ordinal|tostring)),logPath:".mana/features/F/decisions/developer-choice-log.md",line:$ordinal,choiceOrdinal:$ordinal,status:"confirmed",subject:$subject,confirmedChoice:$choice,confirmedBy:"developer"},provenance:{sourceType:"developer-choice-log",sourceArtifact:{path:".mana/features/F/decisions/developer-choice-log.md",sha256:$source_hash},evidence:[]},capture:{processor:"deterministic-developer-choice-log-v1",modelCalls:0,capturedAt:"2026-08-08T00:00:00Z"}}' > "$signals/$id.json"
}
aggregate() { MANA_USER_STATE_HOME="$state" "$root/scripts/mana-user-learning.sh" --project-root "$project" aggregate --json; }

# same structural key + selected outcome across projects: one recurring cluster.
write_signal 1 1 'Persistence   choice' 'PostgreSQL' 1
write_signal 2 2 ' Persistence choice ' 'PostgreSQL' 1
project_before="$(find "$project" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"
first="$(aggregate)"
printf '%s' "$first" | jq -e '.validSignals == 2 and .clustersProduced == 1 and .recurringClusters == 1 and .totalSupportingRelationships == 2 and .distinctProjects == 2 and .modelCalls == 0' >/dev/null || fail 'basic_cross_project_grouping failed'
cluster_id="$(printf '%s' "$first" | jq -r '.clusters[0].clusterId')"
cluster_file="$state/user-learning/clusters/$cluster_id.json"
jq -e '.occurrenceCount == 2 and .distinctProjectCount == 2 and .derivation.modelCalls == 0' "$cluster_file" >/dev/null || fail 'basic cluster metrics missing'
cp "$cluster_file" "$tmp/first-cluster.json"

# Recreate source files in reverse creation order: sorted discovery must yield
# byte-identical derived output and the same identity.
rm "$signals"/user-choice-*.json
write_signal 2 2 ' Persistence choice ' 'PostgreSQL' 1
write_signal 1 1 'Persistence   choice' 'PostgreSQL' 1
ordering="$(aggregate)"
[ "$(printf '%s' "$ordering" | jq -r '.clusters[0].clusterId')" = "$cluster_id" ] || fail 'input_ordering changed cluster identity'
cmp -s "$tmp/first-cluster.json" "$cluster_file" || fail 'input_ordering changed materialized output'

# Additional and then removed evidence updates membership but not key identity;
# full rebuild must remove stale supporting references.
write_signal 3 1 'Persistence choice' 'PostgreSQL' 2
additional="$(aggregate)"
printf '%s' "$additional" | jq -e --arg id "$cluster_id" '.clusters[] | select(.clusterId == $id and .occurrenceCount == 3 and .distinctProjectCount == 2)' >/dev/null || fail 'additional_evidence did not refresh stable cluster'
rm "$signals/user-choice-$(hex 3).json"
removed="$(aggregate)"
printf '%s' "$removed" | jq -e --arg id "$cluster_id" '.clusters[] | select(.clusterId == $id and .occurrenceCount == 2 and (.supportingSignalIds | index("user-choice-0000000000000000000000000000000000000000000000000000000000000003") | not))' >/dev/null || fail 'removed_evidence left a stale supporting reference'

# Exact subject but different outcome is a separate cluster. Similar wording
# remains separate without semantic reconciliation.
write_signal 4 3 'Persistence choice' 'MySQL' 1
write_signal 5 4 'durable retry' 'use durable outbox' 1
write_signal 6 5 'avoid fire-and-forget' 'use durable outbox' 1
printf '%s\n' '{not valid json' > "$signals/not-json.json"
printf '%s\n' '{"schemaVersion":"2","signalId":"user-choice-0000000000000000000000000000000000000000000000000000000000000007"}' > "$signals/user-choice-$(hex 7).json"
cp "$signals/user-choice-$(hex 1).json" "$signals/zz-duplicate.json"
signals_before="$(find "$signals" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"
final="$(aggregate)"
printf '%s' "$final" | jq -e '.validSignals == 5 and .skippedSignals == 3 and .duplicateSignals == 1 and .clustersProduced == 4 and .recurringClusters == 1 and .totalSupportingRelationships == 5 and .distinctProjects == 5 and .modelCalls == 0' >/dev/null || fail 'invalid or duplicate evidence inflated aggregation'
[ "$signals_before" = "$(find "$signals" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)" ] || fail 'aggregate mutated M1 signals'
[ "$project_before" = "$(find "$project" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)" ] || fail 'aggregate mutated the project or User Context'

postgres_cluster="$(printf '%s' "$final" | jq -r '.clusters[] | select(.aggregationKey.normalizedConfirmedChoice == "PostgreSQL") | .clusterId')"
mysql_cluster="$(printf '%s' "$final" | jq -r '.clusters[] | select(.aggregationKey.normalizedConfirmedChoice == "MySQL") | .clusterId')"
[ "$postgres_cluster" != "$mysql_cluster" ] || fail 'different_selected_outcomes collapsed into one cluster'
printf '%s' "$final" | jq -e '(.clusters[] | select(.clusterId == $id) | .alternativeConfirmedEvidence[] | select(.normalizedConfirmedChoice == "MySQL") | .supportingSignalIds | index("user-choice-0000000000000000000000000000000000000000000000000000000000000004")) != null' --arg id "$postgres_cluster" >/dev/null || fail 'structural alternative evidence missing'
retry_cluster="$(printf '%s' "$final" | jq -r '.clusters[] | select(.aggregationKey.normalizedSubject == "durable retry") | .clusterId')"
fire_cluster="$(printf '%s' "$final" | jq -r '.clusters[] | select(.aggregationKey.normalizedSubject == "avoid fire-and-forget") | .clusterId')"
[ "$retry_cluster" != "$fire_cluster" ] || fail 'similar_wording_is_not_semantic_equality failed'
printf '%s' "$final" | jq -e 'all(.clusters[]; .derivation.modelCalls == 0)' >/dev/null || fail 'zero_model_calls invariant missing from clusters'

# A complete rebuild removes a cluster that no longer has any valid source
# evidence, while leaving unrelated derived state untouched.
write_signal 8 6 'transient structural key' 'temporary outcome' 1
with_transient="$(aggregate)"
transient_cluster="$(printf '%s' "$with_transient" | jq -r '.clusters[] | select(.aggregationKey.normalizedSubject == "transient structural key") | .clusterId')"
[ -f "$state/user-learning/clusters/$transient_cluster.json" ] || fail 'genuinely_different_key did not produce a cluster artifact'
rm "$signals/user-choice-$(hex 8).json"
after_transient_removal="$(aggregate)"
[ ! -e "$state/user-learning/clusters/$transient_cluster.json" ] || fail 'removed_cluster_evidence left stale derived state'
printf '%s' "$after_transient_removal" | jq -e --arg id "$cluster_id" '.clusters[] | select(.clusterId == $id and .occurrenceCount == 2)' >/dev/null || fail 'unrelated cluster changed after derived-state rebuild'

echo 'User Learning aggregation tests passed'
