#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-inspect.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
inspect="$root/scripts/mana-inspect.sh"

project="$tmp/missing"; mkdir -p "$project"; git -C "$project" init -q
"$inspect" --project-root "$project" project --json > "$tmp/project.json"
jq -e '.schema=="mana.inspect.project/v1" and .framework.compatibility=="mana-inspect/v1" and .mana.present==false and .guarantees.model_calls==0 and .guarantees.writes==false' "$tmp/project.json" >/dev/null || fail 'missing workspace project contract failed'
! grep -Fq "$project" "$tmp/project.json" || fail 'project response leaked absolute path'
"$inspect" --project-root "$project" artifacts --json | jq -e '.schema=="mana.inspect.artifacts/v1" and .artifacts==[]' >/dev/null || fail 'missing workspace catalog failed'
"$inspect" --project-root "$project" work-items --json | jq -e '.schema=="mana.inspect.work-items/v1" and .work_items==[] and .coverage=="none"' >/dev/null || fail 'missing workspace work-item list failed'

"$root/scripts/bootstrap-project.sh" --project-root "$project" --mana-root "$root" --no-jira-env >/dev/null
"$root/scripts/mana-workspace.sh" init --root "$project" --feature FEAT-1 >/dev/null
mkdir -p "$project/.mana/sessions/session-1/validation" \
  "$project/.mana/features/FEAT-1/evidence/verification/run-1" \
  "$project/.mana/features/FEAT-1/evidence/verification/run-generated" \
  "$project/.mana/features/FEAT-1/evidence/verification/run-finished" \
  "$project/.mana/features/FEAT-1/evidence/verification/run-both" \
  "$project/.mana/features/FEAT-1/evidence/verification/run-malformed-generated" \
  "$project/.mana/features/FEAT-1/evidence/verification/run-malformed-finished"
printf '%s\n' 'workspace_type: session' 'workspace_id: session-1' > "$project/.mana/sessions/session-1/manifest.yaml"
printf '%s\n' '# Review' > "$project/.mana/sessions/session-1/validation/review.md"
printf '%s\n' '{"schemaVersion":"2","kind":"verification-result","runId":"run-1","overallResult":"passed"}' > "$project/.mana/features/FEAT-1/evidence/verification/run-1/result.json"
printf '%s\n' '{"schemaVersion":"2","kind":"verification-result","runId":"run-generated","overallResult":"passed","generatedAt":"2026-01-02T03:04:05Z"}' > "$project/.mana/features/FEAT-1/evidence/verification/run-generated/result.json"
printf '%s\n' '{"schemaVersion":"2","kind":"verification-result","runId":"run-finished","overallResult":"passed","finishedAt":"2026-01-03T04:05:06Z"}' > "$project/.mana/features/FEAT-1/evidence/verification/run-finished/result.json"
printf '%s\n' '{"schemaVersion":"2","kind":"verification-result","runId":"run-both","overallResult":"passed","generatedAt":"2026-01-04T05:06:07Z","finishedAt":"2026-01-05T06:07:08Z"}' > "$project/.mana/features/FEAT-1/evidence/verification/run-both/result.json"
printf '%s\n' '{"schemaVersion":"2","kind":"verification-result","runId":"run-malformed-generated","overallResult":"passed","generatedAt":"not-a-timestamp"}' > "$project/.mana/features/FEAT-1/evidence/verification/run-malformed-generated/result.json"
printf '%s\n' '{"schemaVersion":"2","kind":"verification-result","runId":"run-malformed-finished","overallResult":"passed","finishedAt":"not-a-timestamp"}' > "$project/.mana/features/FEAT-1/evidence/verification/run-malformed-finished/result.json"
cp "$project/.mana/features/FEAT-1/evidence/verification/run-1/result.json" "$project/.mana/features/FEAT-1/evidence/verification/run-1/latest.json"
printf '%s\n' '{not json' > "$project/.mana/legacy.json"
printf '%s\n' 'opaque legacy data' > "$project/.mana/legacy.bin"
ln -s /etc/passwd "$project/.mana/unsafe-link"
mkdir -p "$project/.mana/features/FEAT-1/context" "$project/.mana/features/FEAT-1/planning"
printf '%s\n' '# Story' > "$project/.mana/features/FEAT-1/context/story-context.md"
printf '%s\n' '# Plan' > "$project/.mana/features/FEAT-1/planning/implementation-plan.md"

before="$(find "$project/.mana" -type f -exec shasum -a 256 {} + | LC_ALL=C sort)"
"$project/mana" inspect project --json > "$tmp/wrapper-project.json"
"$project/mana" inspect artifacts --json > "$tmp/catalog-one.json"
after="$(find "$project/.mana" -type f -exec shasum -a 256 {} + | LC_ALL=C sort)"
[ "$before" = "$after" ] || fail 'inspect wrote beneath .mana'
"$project/mana" inspect artifacts --json > "$tmp/catalog-two.json"
cmp -s "$tmp/catalog-one.json" "$tmp/catalog-two.json" || fail 'catalog is not byte-stable'
jq -e '
  . as $r |
  ($r.schema=="mana.inspect.artifacts/v1") and
  (([$r.artifacts[].artifact_id]|length) == ([$r.artifacts[].artifact_id]|unique|length)) and
  ($r.artifacts == ($r.artifacts|sort_by(.artifact_id,.path))) and
  any($r.artifacts[]; .artifact_id=="verification:run-1" and .status=="passed") and
  any($r.artifacts[]; .kind=="markdown" and .workspace=="session:session-1") and
  any($r.artifacts[]; .path==".mana/legacy.json" and .family=="unknown" and .status=="malformed") and
  any($r.artifacts[]; .path==".mana/legacy.bin" and .family=="unknown") and
  any($r.artifacts[]; .path==".mana/unsafe-link" and .status=="quarantined" and .diagnostic=="symlink_not_followed") and
  all($r.artifacts[]; (.path|startswith(".mana/")) and (.revision_id|test("^sha256:[0-9a-f]{64}$"))) and
  all($r.artifacts[]; .path != ".mana/features/FEAT-1/evidence/verification/run-1/latest.json")
' "$tmp/catalog-one.json" >/dev/null || fail 'catalog fields, aliases, or safety classification failed'
! grep -Fq "$project" "$tmp/catalog-one.json" || fail 'catalog leaked absolute path'

# Semantic work-item producer uses only canonical workspace roots and manifests.
"$project/mana" inspect work-items --json > "$tmp/work-items-one.json"
"$project/mana" inspect project --json | jq -e 'any(.operations[]; .name=="work-items" and .schema=="mana.inspect.work-items/v1") and any(.operations[]; .name=="work-item" and .schema=="mana.inspect.work-item/v1")' >/dev/null || fail 'semantic operations not advertised'
"$project/mana" inspect project --json | jq -e 'any(.operations[]; .name=="project-context") and any(.operations[]; .name=="activity")' >/dev/null || fail 'project context/activity not advertised'
mkdir -p "$project/.mana/global/team-decisions"
ln -s /etc/passwd "$project/.mana/global/team-decisions/unsafe.md"
"$project/mana" inspect project-context --json > "$tmp/project-context.json"
jq -e '(.schema=="mana.inspect.project-context/v1") and ([.categories[].category]|sort)==["architecture","database_policy","engineering_guards","glossary","integrations","learning_journeys","project_decisions","testing_policy"] and all(.categories[].artifacts[]; .work_item_id==null and .section_id==null and .status!="quarantined") and all(.categories[].artifacts[]; .path!=".mana/global/team-decisions/unsafe.md")' "$tmp/project-context.json" >/dev/null || fail 'project context categories or symlink containment failed'
mkdir -p "$project/.mana/runtime/events"
printf '%s\n' '{"eventId":"runtime-b","timestamp":"2026-01-01T00:00:00Z"}' '{"eventId":"runtime-a","timestamp":"2026-01-01T00:00:00Z"}' '{"eventId":"runtime-malformed","timestamp":"not-a-timestamp"}' > "$project/.mana/runtime/events/sample.jsonl"
"$project/mana" inspect activity --json > "$tmp/activity.json"
"$project/mana" inspect activity --json > "$tmp/activity-repeat.json"
cmp -s "$tmp/activity.json" "$tmp/activity-repeat.json" || fail 'activity is not byte-stable'
jq -e '
  .schema=="mana.inspect.activity/v1" and
  any(.events[]; .event_id=="runtime-a" and .timestamp.provenance=="explicit_domain_timestamp") and
  all(.events[]; .event_id!="runtime-malformed") and
  any(.events[]; .event_id=="verification:verification:run-generated" and .event_kind=="verification_completed" and .timestamp.value=="2026-01-02T03:04:05Z" and .timestamp.provenance=="explicit_domain_timestamp") and
  any(.events[]; .event_id=="verification:verification:run-finished" and .event_kind=="verification_completed" and .timestamp.value=="2026-01-03T04:05:06Z" and .timestamp.provenance=="explicit_domain_timestamp") and
  any(.events[]; .event_id=="verification:verification:run-both" and .timestamp.value=="2026-01-04T05:06:07Z") and
  (all(.events[]; .event_id != "verification:verification:run-malformed-generated" and .event_id != "verification:verification:run-malformed-finished")) and
  any(.events[]; .event_id=="artifact-update:verification:run-malformed-generated" and .timestamp.provenance=="filesystem_mtime_epoch" and .event_kind=="artifact_updated") and
  any(.events[]; .event_id=="artifact-update:verification:run-malformed-finished" and .timestamp.provenance=="filesystem_mtime_epoch" and .event_kind=="artifact_updated") and
  any(.events[]; .timestamp.provenance=="filesystem_mtime_epoch" and .event_kind=="artifact_updated") and
  (([.events[]|select(.event_id=="runtime-a" or .event_id=="runtime-b")|.event_id])==["runtime-a","runtime-b"])
' "$tmp/activity.json" >/dev/null || fail 'semantic verification activity timestamps, ordering, or fallback provenance failed'
"$project/mana" inspect work-items --json > "$tmp/work-items-two.json"
cmp -s "$tmp/work-items-one.json" "$tmp/work-items-two.json" || fail 'work-item list is not byte-stable'
jq -e '
  .schema=="mana.inspect.work-items/v1" and
  ([.work_items[].work_item_id]|index("feature:FEAT-1")) and
  ([.work_items[].work_item_id]|index("session:session-1")) and
  any(.work_items[]; .work_item_id=="feature:FEAT-1" and .work_item_type=="feature") and
  any(.work_items[]; .work_item_id=="session:session-1" and .work_item_type=="session") and
  any(.work_items[]; .work_item_id=="feature:FEAT-1" and .lifecycle.state=="in_progress") and
  any(.work_items[]; .work_item_id=="session:session-1" and .lifecycle.state=="unknown") and
  all(.work_items[]; .review.state=="unknown" and (.attention_items|type=="array"))
' "$tmp/work-items-one.json" >/dev/null || fail 'semantic work-item list failed'
"$project/mana" inspect work-item feature:FEAT-1 --json > "$tmp/work-item-feature.json"
jq -e '
  .schema=="mana.inspect.work-item/v1" and .work_item.work_item_id=="feature:FEAT-1" and
  ([.sections[].section_id]|sort)==["artifacts","decisions","evidence","overview","plan","requirements","review","timeline"] and
  all(.sections[].artifacts[]; .work_item_id=="feature:FEAT-1" and (.section_id|type=="string"))
' "$tmp/work-item-feature.json" >/dev/null || fail 'semantic work-item detail failed'
jq -e '
  any(.sections[]; .section_id=="overview" and any(.artifacts[]; .path==".mana/features/FEAT-1/index.md")) and
  any(.sections[]; .section_id=="requirements" and any(.artifacts[]; .path==".mana/features/FEAT-1/context/story-context.md")) and
  any(.sections[]; .section_id=="plan" and any(.artifacts[]; .path==".mana/features/FEAT-1/planning/implementation-plan.md"))
' "$tmp/work-item-feature.json" >/dev/null || fail 'canonical section mapping failed'
printf '%s\n' '.mana/features/does-not-exist' > "$project/.mana/active-workspace"
"$project/mana" inspect work-item feature:FEAT-1 --json | jq -e '.work_item.lifecycle.state=="unknown"' >/dev/null || fail 'invalid active workspace was not conservative'
rm "$project/.mana/active-workspace"
"$project/mana" inspect work-item feature:FEAT-1 --json | jq -e '.work_item.lifecycle.state=="unknown"' >/dev/null || fail 'missing active workspace was not conservative'
printf '%s\n' '.mana/features/FEAT-1' > "$project/.mana/active-workspace"
printf '%s\n' 'workspace_type: session' 'workspace_id: wrong-id' > "$project/.mana/sessions/session-1/manifest.yaml"
"$project/mana" inspect work-item session:session-1 --json | jq -e '.work_item.work_item_id=="session:session-1" and any(.diagnostics[]; .id=="manifest-identity")' >/dev/null || fail 'manifest/path identity disagreement failed'
if "$project/mana" inspect work-item feature:missing --json >/dev/null 2>&1; then fail 'unknown work item was accepted'; fi
if "$project/mana" inspect work-item ../unsafe --json >/dev/null 2>&1; then fail 'unsafe work item ID was accepted'; fi
printf '%s\n' '| x | needs_owner_review |' >> "$project/.mana/features/FEAT-1/decisions/developer-choice-log.md"
printf '%s\n' '{"schemaVersion":"2","kind":"verification-result","runId":"run-failed","overallResult":"failed"}' > "$project/.mana/features/FEAT-1/evidence/verification/run-failed.json"
printf '%s\n' '{"schemaVersion":"2","kind":"verification-result","runId":"run-stale","overallResult":"passed","staleness":"stale"}' > "$project/.mana/features/FEAT-1/evidence/verification/run-stale.json"
"$project/mana" inspect work-item feature:FEAT-1 --json | jq -e 'any(.attention_items[]; .category=="pending_decision") and any(.attention_items[]; .category=="failed_verification") and any(.attention_items[]; .category=="stale_evidence") and .work_item.lifecycle.state=="failed"' >/dev/null || fail 'semantic attention or lifecycle failed'
printf '%s\n' 'review decision evidence' > "$project/.mana/features/FEAT-1/unrelated-review-decision-evidence.md"
"$project/mana" inspect work-item feature:FEAT-1 --json | jq -e 'all(.sections[].artifacts[]; .path != ".mana/features/FEAT-1/unrelated-review-decision-evidence.md" or .section_id=="artifacts")' >/dev/null || fail 'lexical filename inference occurred'

mkdir -p "$project/.mana/sessions/session-1/evidence/verification/run-1"
cp "$project/.mana/features/FEAT-1/evidence/verification/run-1/result.json" "$project/.mana/sessions/session-1/evidence/verification/run-1/result.json"
if "$project/mana" inspect artifact verification:run-1 --json >/dev/null 2>&1; then fail 'ambiguous artifact ID was accepted'; fi
rm -rf "$project/.mana/sessions/session-1/evidence"

# Detail and source navigation use only producer-owned Journey anchors.
mkdir -p "$project/src/main/java/example"
printf '%s\n' 'class PaymentService {}' > "$project/src/main/java/example/PaymentService.java"
git -C "$project" -c user.name=Mana -c user.email=mana@example.invalid add src
git -C "$project" -c user.name=Mana -c user.email=mana@example.invalid -c commit.gpgsign=false commit -qm source-fixture
revision="$(git -C "$project" rev-parse HEAD)"
journey="$($root/scripts/mana-journey.sh --project-root "$project" create --title 'Inspect source' --start-kind http_endpoint --start-value /payments --termination-kind runtime_effect --termination-condition committed --revision "$revision")"
node="$($root/scripts/mana-journey.sh --project-root "$project" add-node "$journey" --kind code)"
anchor="$($root/scripts/mana-journey.sh --project-root "$project" add-anchor "$journey" --node "$node" --revision "$revision" --path src/main/java/example/PaymentService.java --start-line 1 --end-line 1 --symbol PaymentService)"
"$project/mana" inspect artifact "journey:$journey" --json > "$tmp/journey-detail.json"
jq -e --arg journey "$journey" --arg anchor "$anchor" '.schema=="mana.inspect.artifact/v1" and .artifact.artifact_id==("journey:"+$journey) and .payload.included==true and any(.relations[]; .anchor_id==$anchor and .staleness=="fresh")' "$tmp/journey-detail.json" >/dev/null || fail 'Journey detail relation failed'
"$project/mana" inspect source src/main/java/example/PaymentService.java --json > "$tmp/source-detail.json"
jq -e --arg anchor "$anchor" '.schema=="mana.inspect.source/v1" and .coverage=="explicit_journey_anchors" and any(.relations[]; (.anchor_id==$anchor) and (.source.revision|test("^[0-9a-f]{40}$")))' "$tmp/source-detail.json" >/dev/null || fail 'source relation failed'
printf '%s\n' '// dirty' >> "$project/src/main/java/example/PaymentService.java"
"$project/mana" inspect source src/main/java/example/PaymentService.java --json | jq -e '.relations[0].staleness=="working_tree_only"' >/dev/null || fail 'working-tree staleness failed'
rm "$project/src/main/java/example/PaymentService.java"
"$project/mana" inspect source src/main/java/example/PaymentService.java --json | jq -e '.source.availability=="missing" and .relations[0].staleness=="missing"' >/dev/null || fail 'missing-source staleness failed'

printf '%s' 'payload' > "$project/.mana/small.txt"
printf 'text\000more' > "$project/.mana/binary.txt"
dd if=/dev/zero of="$project/.mana/oversized.txt" bs=65537 count=1 2>/dev/null
deep="$project/.mana/deep.json"; printf '{"schema":"mana.learning.record/v1","v":' > "$deep"; for _ in $(seq 1 33); do printf '{"v":' >> "$deep"; done; printf '0' >> "$deep"; for _ in $(seq 0 33); do printf '}' >> "$deep"; done
printf '%s\n' '{"schema":"future.inspect/v99"}' > "$project/.mana/future.json"
"$project/mana" inspect artifact .mana/oversized.txt --json | jq -e '.payload.included==false and .payload.reason=="payload_too_large"' >/dev/null || fail 'oversized payload limit failed'
"$project/mana" inspect artifact .mana/binary.txt --json | jq -e '.payload.included==false and .payload.reason=="unsupported_or_binary_content"' >/dev/null || fail 'binary payload handling failed'
"$project/mana" inspect artifact .mana/deep.json --json | jq -e '.payload.included==false and .payload.reason=="json_depth_exceeded"' >/dev/null || fail 'JSON depth limit failed'
"$project/mana" inspect artifact .mana/future.json --json | jq -e '.payload.included==false and .payload.reason=="unsupported_schema"' >/dev/null || fail 'unsupported schema handling failed'
if "$project/mana" inspect artifact .mana/../outside --json >/dev/null 2>&1; then fail 'artifact traversal was accepted'; fi
if "$project/mana" inspect source ../outside --json >/dev/null 2>&1; then fail 'source traversal was accepted'; fi

printf '%s\n' dirty > "$project/dirty.txt"
"$project/mana" inspect project --json | jq -e '.mana.present==true and .git.working_tree_dirty==true and (.project_id|test("^project:[0-9a-f]{64}$"))' >/dev/null || fail 'dirty project state failed'

unsafe="$tmp/unsafe"; mkdir -p "$unsafe"; ln -s /etc "$unsafe/.mana"
if "$inspect" --project-root "$unsafe" artifacts --json >/dev/null 2>&1; then fail 'symlinked .mana was accepted'; else [ "$?" -eq 4 ] || fail 'symlinked .mana exit code changed'; fi

for schema in "$root/docs/standards/mana-inspect-project-v1.schema.json" "$root/docs/standards/mana-inspect-artifacts-v1.schema.json" "$root/docs/standards/mana-inspect-artifact-v1.schema.json" "$root/docs/standards/mana-inspect-source-v1.schema.json"; do
  jq -e '."$schema"=="https://json-schema.org/draft/2020-12/schema" and .type=="object" and .additionalProperties==false' "$schema" >/dev/null || fail "invalid schema: $schema"
done
echo 'Mana inspect v1 tests passed'
