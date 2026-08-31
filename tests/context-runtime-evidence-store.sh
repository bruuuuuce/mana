#!/usr/bin/env bash
# CTX-05-R1 host-owned evidence storage and bounded retrieval acceptance coverage.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd -P)"
cli="$root/scripts/mana-evidence.sh"
validator="$root/scripts/lib/context-runtime.sh"
schema="$root/contracts/context-runtime/evidence-manifest-v1.schema.json"
fixtures="$root/tests/fixtures/context-runtime/evidence-store"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-context-runtime-evidence.XXXXXX")"
tmp="$(cd "$tmp" && pwd -P)"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
mkdir -p "$project/inputs"
cp "$fixtures/source.txt" "$project/inputs/source.txt"
cp "$fixtures/normalized.txt" "$project/inputs/normalized.txt"
fail() { echo "FAIL: $*" >&2; exit 1; }
rejects() { if "$@" >/dev/null 2>&1; then fail "expected rejection: $*"; fi; }

collect() {
  "$cli" --project-root "$project" collect \
    --execution execution-evidence-fixture --kind source --source-system fixture \
    --source-locator 'https://user:password@example.test/source?access_token=secret&revision=7' \
    --input inputs/source.txt --normalized-input inputs/normalized.txt \
    --media-type text/plain --revision-id fixture-r1
}

first="$(collect)"
evidence_id="$(jq -r .evidenceId <<<"$first")"
jq -e '.deduplicated == false and .collectionStatus == "complete" and (.evidenceId | test("^E-[a-f0-9]{64}$"))' <<<"$first" >/dev/null || fail 'collection did not return canonical record metadata'
second="$(collect)"
[ "$(jq -r .evidenceId <<<"$second")" = "$evidence_id" ] || fail 'same bytes and provenance did not retain record ID'
jq -e '.deduplicated == true' <<<"$second" >/dev/null || fail 'same record was not deduplicated'

manifest="$project/.mana/runtime-evidence/executions/execution-evidence-fixture/manifest.json"
"$validator" validate-model evidence-manifest "$manifest" || fail 'manifest is not a valid CTX-03 evidence manifest'
python3 "$root/tests/lib/json_schema_subset.py" "$schema" "$manifest" || fail 'manifest failed offline schema validation'
jq -e '
  .items as $items | $items[0] as $item |
  ($items | length == 1) and
  $item.sourcePayload.localPath != $item.normalizedRepresentation.localPath and
  $item.localPath == $item.normalizedRepresentation.localPath and
  $item.evidenceId != ("E-" + ($item.digest | ltrimstr("sha256:"))) and
  $item.sourceLocator == "https://example.test/source?access_token=%5BREDACTED%5D&revision=7"
' "$manifest" >/dev/null || fail 'blob/record identity or source/normalized separation is invalid'

# Redaction happens before digest, identity, or persistence for headers,
# assignments, URI userinfo/query values, JSON fields, and forms.
printf '%s\n' \
  'Authorization: Bearer locator-credential-value' \
  'Proxy-Authorization: Basic cHJveHk=' \
  'Cookie: session=header-cookie-value' \
  'Set-Cookie: session=set-cookie-value' \
  'cookie=unredacted-cookie-value' \
  'password = plaintext-password' \
  'url=https://alice:locator-password@example.test/a?api-key=query-secret&ok=1' \
  > "$project/inputs/privacy.txt"
privacy="$($cli --project-root "$project" collect --execution execution-evidence-fixture --kind log --source-system fixture --source-locator 'https://bob:raw@example.test/log?token=locator-token' --input inputs/privacy.txt --media-type text/plain)"
privacy_id="$(jq -r .evidenceId <<<"$privacy")"
privacy_read="$($cli --project-root "$project" read "$privacy_id")"
rg -F 'Authorization: [REDACTED]' <<<"$privacy_read" >/dev/null || fail 'Authorization probe was not redacted'
rg -F 'cookie=[REDACTED]' <<<"$privacy_read" >/dev/null || fail 'cookie assignment probe was not redacted'
if rg -n 'locator-credential-value|unredacted-cookie-value|header-cookie-value|set-cookie-value|plaintext-password|locator-password|query-secret|locator-token|cHJveHk=' "$project/.mana/runtime-evidence" >/dev/null; then
  fail 'credential material reached the evidence store'
fi

printf '%s' '{"Authorization":"Bearer json-secret","nested":{"api_key":"json-key","safe":7},"arr":[10,20]}' > "$project/inputs/data.json"
json_result="$($cli --project-root "$project" collect --execution execution-evidence-fixture --kind api --source-system fixture --source-locator json-fixture --input inputs/data.json --media-type application/json)"
json_id="$(jq -r .evidenceId <<<"$json_result")"
json_extract="$($cli --project-root "$project" extract "$json_id" --selector json:/nested/safe --max-bytes 16)"
jq -e --arg id "$json_id" '.provenance.evidenceId == $id and .encoding == "json" and .content == "7"' <<<"$json_extract" >/dev/null || fail 'JSON pointer extraction lost provenance'
rejects "$cli" --project-root "$project" extract "$json_id" --selector 'json:/a~2b'
rejects "$cli" --project-root "$project" extract "$json_id" --selector 'json:/arr/01'
rejects "$cli" --project-root "$project" extract "$json_id" --selector 'json:'

printf '%s' 'user=ok&token=form-secret&password=form-password' > "$project/inputs/form.txt"
form_result="$($cli --project-root "$project" collect --execution execution-evidence-fixture --kind api --source-system fixture --source-locator form-fixture --input inputs/form.txt --media-type application/x-www-form-urlencoded)"
form_id="$(jq -r .evidenceId <<<"$form_result")"
form_read="$($cli --project-root "$project" read "$form_id")"
rg -F 'token=%5BREDACTED%5D' <<<"$form_read" >/dev/null || fail 'form token was not redacted'
if rg -n 'json-secret|json-key|form-secret|form-password' "$project/.mana/runtime-evidence" >/dev/null; then
  fail 'structured credential material reached persistence'
fi

# Invalid structured payloads cannot be persisted as complete evidence.
printf '%s' '{"broken":' > "$project/inputs/malformed.json"
before_count="$(jq '.items | length' "$manifest")"
rejects "$cli" --project-root "$project" collect --execution execution-evidence-fixture --kind api --source-system fixture --source-locator bad-json --input inputs/malformed.json --media-type application/json
printf '%s' '<root><password>secret</password></root>' > "$project/inputs/unsafe.xml"
rejects "$cli" --project-root "$project" collect --execution execution-evidence-fixture --kind api --source-system fixture --source-locator unsafe-xml --input inputs/unsafe.xml --media-type application/xml
[ "$(jq '.items | length' "$manifest")" = "$before_count" ] || fail 'invalid structured input mutated the manifest'

# Content blob identity and evidence record identity are separate.
identity_ids="$tmp/identity-ids"
: > "$identity_ids"
for variant in \
  '--kind other --source-system fixture --source-locator stable --revision-id r1' \
  '--kind source --source-system other --source-locator stable --revision-id r1' \
  '--kind source --source-system fixture --source-locator changed --revision-id r1' \
  '--kind source --source-system fixture --source-locator stable --revision-id r2'; do
  # shellcheck disable=SC2086
  "$cli" --project-root "$project" collect --execution execution-identity $variant --input inputs/source.txt --media-type text/plain | jq -r .evidenceId >> "$identity_ids"
done
[ "$(sort -u "$identity_ids" | wc -l | tr -d ' ')" = 4 ] || fail 'provenance/revision variants collapsed to one record'

same_a="$($cli --project-root "$project" collect --execution execution-versioning --kind source --source-system fixture --source-locator stable --revision-id r1 --input inputs/source.txt --media-type text/plain)"
same_b="$($cli --project-root "$project" collect --execution execution-versioning --kind source --source-system fixture --source-locator stable --revision-id r1 --input inputs/source.txt --media-type text/plain)"
[ "$(jq -r .evidenceId <<<"$same_a")" = "$(jq -r .evidenceId <<<"$same_b")" ] || fail 'same raw and provenance did not deduplicate'
normalized_variant="$($cli --project-root "$project" collect --execution execution-versioning --kind source --source-system fixture --source-locator stable --revision-id r1 --input inputs/source.txt --normalized-input inputs/normalized.txt --media-type text/plain)"
[ "$(jq -r .evidenceId <<<"$same_a")" != "$(jq -r .evidenceId <<<"$normalized_variant")" ] || fail 'normalized representation did not version the record'
normalization_version="$($cli --project-root "$project" collect --execution execution-versioning --kind source --source-system fixture --source-locator stable --revision-id r1 --input inputs/source.txt --media-type text/plain --normalization-version v2)"
[ "$(jq -r .evidenceId <<<"$same_a")" != "$(jq -r .evidenceId <<<"$normalization_version")" ] || fail 'normalization version did not version the record'
printf '%s\n' 'raw changed' > "$project/inputs/changed.txt"
raw_changed="$($cli --project-root "$project" collect --execution execution-versioning --kind source --source-system fixture --source-locator stable --revision-id r1 --input inputs/changed.txt --media-type text/plain)"
[ "$(jq -r .evidenceId <<<"$same_a")" != "$(jq -r .evidenceId <<<"$raw_changed")" ] || fail 'raw change did not create a new record'
version_manifest="$project/.mana/runtime-evidence/executions/execution-versioning/manifest.json"
same_digest="$(jq --arg id "$(jq -r .evidenceId <<<"$same_a")" -r '.items[] | select(.evidenceId == $id) | .sourcePayload.digest' "$version_manifest")"
changed_digest="$(jq --arg id "$(jq -r .evidenceId <<<"$raw_changed")" -r '.items[] | select(.evidenceId == $id) | .sourcePayload.digest' "$version_manifest")"
[ "$same_digest" != "$changed_digest" ] || fail 'raw change did not create a new content blob'

# Full reads and extracts are distinct. Every range is a strict subset and
# carries source evidence provenance.
listed="$($cli --project-root "$project" list --execution execution-evidence-fixture)"
jq -e --arg id "$evidence_id" '.items | map(.evidenceId) | index($id) != null' <<<"$listed" >/dev/null || fail 'list did not return execution evidence'
shown="$($cli --project-root "$project" show "$evidence_id" --metadata)"
jq -e --arg id "$evidence_id" '.evidenceId == $id and .collectionStatus == "complete"' <<<"$shown" >/dev/null || fail 'metadata lookup failed'
range="$($cli --project-root "$project" read "$evidence_id" --lines 3:3 --max-bytes 64)"
jq -e --arg id "$evidence_id" '.provenance.evidenceId == $id and .content == "third normalized line\n"' <<<"$range" >/dev/null || fail 'range read did not return a provenance-bearing strict subset'
rejects "$cli" --project-root "$project" read "$evidence_id" --lines 1:4
rejects "$cli" --project-root "$project" extract "$evidence_id" --selector lines:1:4
payload_size="$(jq --arg id "$evidence_id" -r '.items[] | select(.evidenceId == $id) | .byteSize' "$manifest")"
rejects "$cli" --project-root "$project" extract "$evidence_id" --selector "bytes:1:$payload_size"
partial_extract="$($cli --project-root "$project" extract "$evidence_id" --selector bytes:1:4 --max-bytes 4)"
jq -e --arg id "$evidence_id" '.provenance.evidenceId == $id and .byteSize == 4 and .encoding == "base64"' <<<"$partial_extract" >/dev/null || fail 'bounded byte subset was rejected or lost provenance'
rejects "$cli" --project-root "$project" extract "$evidence_id" --selector bytes:0:1
rejects "$cli" --project-root "$project" extract "$evidence_id" --selector bytes:-1:2
rejects "$cli" --project-root "$project" extract "$evidence_id" --selector bytes:3:2
rejects "$cli" --project-root "$project" extract "$evidence_id" --selector bytes:1:999999
rejects "$cli" --project-root "$project" extract "$evidence_id" --selector lines:3:3 --max-bytes 3

printf '%b' '\0\1binary\n' > "$project/inputs/binary.bin"
binary="$($cli --project-root "$project" collect --execution execution-evidence-fixture --kind attachment --source-system fixture --source-locator binary-fixture --input inputs/binary.bin --media-type application/octet-stream)"
binary_id="$(jq -r .evidenceId <<<"$binary")"
rejects "$cli" --project-root "$project" read "$binary_id"
binary_extract="$($cli --project-root "$project" extract "$binary_id" --selector bytes:1:2 --max-bytes 8)"
jq -e --arg id "$binary_id" '.provenance.evidenceId == $id and .encoding == "base64" and .content == "AAE="' <<<"$binary_extract" >/dev/null || fail 'binary extraction was not explicit and bounded'

python3 -c 'print("short"); print("x" * 16385)' > "$project/inputs/large.txt"
large="$($cli --project-root "$project" collect --execution execution-evidence-fixture --kind source --source-system fixture --source-locator large-fixture --input inputs/large.txt --media-type text/plain)"
large_id="$(jq -r .evidenceId <<<"$large")"
rejects "$cli" --project-root "$project" read "$large_id"
"$cli" --project-root "$project" extract "$large_id" --selector lines:1:1 --max-bytes 8 >/dev/null || fail 'explicit bounded large extract failed'

# All collection states are representable and only complete is retrievable.
partial="$($cli --project-root "$project" collect --execution execution-status --kind api --source-system fixture --source-locator partial-fixture --status partial --error-code truncated --error-message 'Response truncated before completion' --gap 'bytes after offset 20 unavailable' --input inputs/source.txt --media-type text/plain)"
partial_id="$(jq -r .evidenceId <<<"$partial")"
failed="$($cli --project-root "$project" collect --execution execution-status --kind api --source-system fixture --source-locator failed-fixture --status failed --error-code collection_failed --error-message 'Collector returned no payload' --media-type text/plain)"
failed_id="$(jq -r .evidenceId <<<"$failed")"
unavailable="$($cli --project-root "$project" collect --execution execution-status --kind external --source-system fixture --source-locator unavailable-fixture --unavailable --media-type text/plain)"
unavailable_id="$(jq -r .evidenceId <<<"$unavailable")"
status_manifest="$project/.mana/runtime-evidence/executions/execution-status/manifest.json"
jq -e '[.items[].collectionStatus] | sort == ["failed","partial","unavailable"]' "$status_manifest" >/dev/null || fail 'partial/failed/unavailable statuses are not represented'
rejects "$cli" --project-root "$project" read "$partial_id"
rejects "$cli" --project-root "$project" extract "$failed_id" --selector bytes:1:1
rejects "$cli" --project-root "$project" read "$unavailable_id"
rejects "$cli" --project-root "$project" collect --execution execution-status --kind api --source-system fixture --source-locator false-complete --status complete --error-code invalid --error-message unsafe --input inputs/source.txt --media-type text/plain

# Every load validates schema and semantic identity. A failed update leaves the
# malformed manifest untouched instead of replacing it with another value.
cp "$manifest" "$tmp/manifest-good.json"
for mutation in \
  '.items = ["not-a-record"]' \
  '.items[0].revisionId = ("r" * 257)' \
  '.items[0].unknownField = true' \
  '.schemaVersion = "mana.context-runtime.evidence-manifest/v999"' \
  '.items[0].evidenceId = "E-0000000000000000000000000000000000000000000000000000000000000000"'; do
  jq "$mutation" "$tmp/manifest-good.json" > "$manifest"
  rejects "$cli" --project-root "$project" list --execution execution-evidence-fixture
  rejects "$cli" --project-root "$project" show "$evidence_id" --metadata --execution execution-evidence-fixture
  rejects "$cli" --project-root "$project" read "$evidence_id" --execution execution-evidence-fixture
  rejects "$cli" --project-root "$project" extract "$evidence_id" --execution execution-evidence-fixture --selector bytes:1:2
done
printf '%s' '{malformed' > "$manifest"
rejects "$cli" --project-root "$project" list --execution execution-evidence-fixture
rejects "$cli" --project-root "$project" read "$evidence_id" --execution execution-evidence-fixture
rejects "$cli" --project-root "$project" extract "$evidence_id" --execution execution-evidence-fixture --selector bytes:1:2
rejects collect
rg -F '{malformed' "$manifest" >/dev/null || fail 'failed collection replaced a malformed manifest'
cp "$tmp/manifest-good.json" "$manifest"

# Blob tampering/collision is detected before deduplication or retrieval.
tamper_record="$($cli --project-root "$project" collect --execution execution-tamper --kind source --source-system fixture --source-locator tamper --input inputs/source.txt --media-type text/plain)"
tamper_id="$(jq -r .evidenceId <<<"$tamper_record")"
tamper_manifest="$project/.mana/runtime-evidence/executions/execution-tamper/manifest.json"
tamper_blob_rel="$(jq -r '.items[0].sourcePayload.localPath' "$tamper_manifest")"
printf '%s' 'tampered' > "$project/$tamper_blob_rel"
rejects "$cli" --project-root "$project" show "$tamper_id" --metadata --execution execution-tamper
rejects "$cli" --project-root "$project" collect --execution execution-tamper --kind source --source-system fixture --source-locator tamper --input inputs/source.txt --media-type text/plain

# Input paths and symlinks cannot escape the authorized project workspace.
cp "$fixtures/source.txt" "$tmp/outside-source.txt"
rejects "$cli" --project-root "$project" collect --execution execution-other --kind source --source-system fixture --source-locator outside --input "$tmp/outside-source.txt" --media-type text/plain
ln -s "$tmp/outside-source.txt" "$project/inputs/source-link.txt"
rejects "$cli" --project-root "$project" collect --execution execution-other --kind source --source-system fixture --source-locator unsafe-link --input inputs/source-link.txt --media-type text/plain

"$root/scripts/run-evidence-index.sh" --project-root "$project" --workspace .mana/features/evidence-index >/dev/null
rg -F '## Context Runtime Evidence' "$project/.mana/features/evidence-index/evidence/index.md" >/dev/null || fail 'existing evidence index omitted CTX-05 evidence'

wrapper_project="$tmp/wrapper-project"
mkdir -p "$wrapper_project/inputs"
cp "$fixtures/source.txt" "$wrapper_project/inputs/source.txt"
"$root/scripts/bootstrap-project.sh" --project-root "$wrapper_project" >/dev/null
"$wrapper_project/mana" evidence collect --execution execution-wrapper --kind source --source-system fixture --source-locator wrapper-fixture --input inputs/source.txt --media-type text/plain >/dev/null
"$wrapper_project/mana" evidence list --execution execution-wrapper | jq -e '.items | length == 1' >/dev/null || fail 'generated mana wrapper did not expose evidence API'
if rg -n '(^|[^[:alnum:]_])(codex|claude|opencode|curl|wget|gh)([[:space:]]|$)' "$cli" "$root/scripts/lib/evidence-store.sh" "$root/scripts/lib/evidence-store.py" >/dev/null; then
  fail 'CTX-05 evidence store contains provider or network dispatch'
fi
echo 'Context Runtime CTX-05-R1 evidence store tests passed (race-safe, redacted, versioned, bounded, zero-token)'
