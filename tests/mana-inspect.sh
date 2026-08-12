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

"$root/scripts/bootstrap-project.sh" --project-root "$project" --mana-root "$root" --no-jira-env >/dev/null
"$root/scripts/mana-workspace.sh" init --root "$project" --feature FEAT-1 >/dev/null
mkdir -p "$project/.mana/sessions/session-1/validation" "$project/.mana/features/FEAT-1/evidence/verification/run-1"
printf '%s\n' 'workspace_type: session' 'workspace_id: session-1' > "$project/.mana/sessions/session-1/manifest.yaml"
printf '%s\n' '# Review' > "$project/.mana/sessions/session-1/validation/review.md"
printf '%s\n' '{"schemaVersion":"2","kind":"verification-result","runId":"run-1","overallResult":"passed"}' > "$project/.mana/features/FEAT-1/evidence/verification/run-1/result.json"
cp "$project/.mana/features/FEAT-1/evidence/verification/run-1/result.json" "$project/.mana/features/FEAT-1/evidence/verification/run-1/latest.json"
printf '%s\n' '{not json' > "$project/.mana/legacy.json"
printf '%s\n' 'opaque legacy data' > "$project/.mana/legacy.bin"
ln -s /etc/passwd "$project/.mana/unsafe-link"

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
