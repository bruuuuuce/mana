#!/usr/bin/env bash
# CTX-03 schema, containment, compatibility, and ordinary path regressors.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
validator="$root/scripts/lib/context-runtime.sh"
fixtures="$root/tests/fixtures/context-runtime/contracts"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-context-runtime-schemas.XXXXXX")"
tmp="$(cd "$tmp" && pwd -P)"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
rejects() { if "$@" >/dev/null 2>&1; then fail "expected rejection: $*"; fi; }

for kind in context-manifest evidence-manifest phase-input phase-checkpoint delegation-task delegation-result finding-validation usage-summary; do
  input="$fixtures/valid/$kind.json"
  "$validator" validate-model "$kind" "$input" || fail "valid $kind was rejected"
  python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/context-runtime/${kind}-v1.schema.json" "$input" || fail "$kind failed offline schema validation"
  jq '.unexpected = true' "$input" > "$tmp/$kind-unknown-field.json"
  rejects "$validator" validate-model "$kind" "$tmp/$kind-unknown-field.json"
done

envelope="$fixtures/valid/execution-envelope.json"
authority="$fixtures/valid/host-authority-context.json"
checkpoint="$fixtures/valid/phase-checkpoint.json"
"$validator" validate-structure execution-envelope "$envelope"
"$validator" host-validate-authority "$authority"
python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/context-runtime/host-authority-context-v1.schema.json" "$authority"

# Generic model validation and the removed boolean cannot confer host authority.
rejects "$validator" validate-model execution-envelope "$envelope"
rejects "$validator" write-model execution-envelope "$envelope" "$tmp" envelope.json
rejects "$validator" write-model phase-checkpoint "$checkpoint" "$tmp" checkpoint.json --host-governance

jq '.verifiedFacts[0].evidenceRefs = []' "$checkpoint" > "$tmp/no-provenance.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/no-provenance.json"
jq 'del(.executionVersion)' "$checkpoint" > "$tmp/missing-execution-version.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/missing-execution-version.json"
jq '.executionVersion = "v1"' "$checkpoint" > "$tmp/malformed-execution-version.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/malformed-execution-version.json"
jq '.schemaVersion = "mana.context-runtime.phase-checkpoint/v999"' "$checkpoint" > "$tmp/unknown-version.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/unknown-version.json"
rejects "$validator" validate-model phase-checkpoint "$fixtures/negative/malformed.json"

# Checkpoint structure cannot carry control objects or arbitrary nested payloads.
for expression in \
  '.permissions = {repositoryWrite:true}' \
  '.effectivePermissions = {externalWrite:true}' \
  '.approvalComplete = true' \
  '.approvalRecords = [{approvalId:"APR-fake"}]' \
  '.payload = {nested:{arbitrary:true}}'; do
  jq "$expression" "$checkpoint" > "$tmp/reserved.json"
  rejects "$validator" validate-model phase-checkpoint "$tmp/reserved.json"
done

# Structural bulk signatures, not semantic word matching, protect prose fields.
jq '.verifiedFacts[0].claim = "2026-08-23T00:00:00Z INFO start\n2026-08-23T00:00:01Z WARN retry\n2026-08-23T00:00:02Z ERROR failed"' "$checkpoint" > "$tmp/raw-log.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/raw-log.json"
jq '.verifiedFacts[0].claim = "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-old\n+new"' "$checkpoint" > "$tmp/full-diff.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/full-diff.json"
jq '.verifiedFacts[0].claim = "{\"key\":\"MANA-1\",\"fields\":{\"summary\":\"complete payload\"}}"' "$checkpoint" > "$tmp/jira.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/jira.json"
jq '.verifiedFacts[0].claim = "Reviewer: first\nAuthor: reply\nReviewer: follow-up"' "$checkpoint" > "$tmp/thread.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/thread.json"

# Every factual claim surface uses the one shared typed-domain contract.
delegation="$fixtures/valid/delegation-result.json"
finding="$fixtures/valid/finding-validation.json"
for domain in governance permissions approval control arbitrary-unknown; do
  jq --arg domain "$domain" '.verifiedFacts[0].subject.domain = $domain' "$checkpoint" > "$tmp/checkpoint-domain.json"
  rejects "$validator" validate-model phase-checkpoint "$tmp/checkpoint-domain.json"
  jq --arg domain "$domain" '.verifiedFacts[0].subject.domain = $domain' "$delegation" > "$tmp/delegation-domain.json"
  rejects "$validator" validate-model delegation-result "$tmp/delegation-domain.json"
  jq --arg domain "$domain" '.subject.domain = $domain' "$finding" > "$tmp/finding-domain.json"
  rejects "$validator" validate-model finding-validation "$tmp/finding-domain.json"
done
for surface in checkpoint delegation finding; do
  case "$surface" in
    checkpoint) jq '.verifiedFacts[0].subject.domain = "application" | .verifiedFacts[0].claim = "The approval response changed from pending to rejected."' "$checkpoint" > "$tmp/application-$surface.json"; kind='phase-checkpoint' ;;
    delegation) jq '.verifiedFacts[0].subject.domain = "application" | .verifiedFacts[0].claim = "The approval response changed from pending to rejected."' "$delegation" > "$tmp/application-$surface.json"; kind='delegation-result' ;;
    finding) jq '.subject.domain = "application" | .claim = "The approval response changed from pending to rejected."' "$finding" > "$tmp/application-$surface.json"; kind='finding-validation' ;;
  esac
  "$validator" validate-model "$kind" "$tmp/application-$surface.json" || fail "application approval prose rejected on $surface"
done

# Exact prose and line boundaries use the same runtime validation path.
jq '.verifiedFacts[0].claim = ("x" * 512)' "$checkpoint" > "$tmp/prose-512.json"
"$validator" validate-model phase-checkpoint "$tmp/prose-512.json" || fail '512-character prose was rejected'
jq '.verifiedFacts[0].claim = ("x" * 513)' "$checkpoint" > "$tmp/prose-513.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/prose-513.json"
jq '.verifiedFacts[0].claim = "one\ntwo\nthree\nfour"' "$checkpoint" > "$tmp/lines-4.json"
"$validator" validate-model phase-checkpoint "$tmp/lines-4.json" || fail 'four-line prose was rejected'
jq '.verifiedFacts[0].claim = "one\ntwo\nthree\nfour\nfive"' "$checkpoint" > "$tmp/lines-5.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/lines-5.json"

jq '.verifiedFacts = [range(0;32) | {id:("F-"+tostring),subject:{domain:"repository",kind:"file",identifier:("f"+tostring)},claim:"bounded",evidenceRefs:["E-001"]}]' "$checkpoint" > "$tmp/max-items.json"
"$validator" validate-model phase-checkpoint "$tmp/max-items.json" || fail 'maxItems boundary was rejected'
jq '.verifiedFacts = [range(0;33) | {id:("F-"+tostring),subject:{domain:"repository",kind:"file",identifier:("f"+tostring)},claim:"bounded",evidenceRefs:["E-001"]}]' "$checkpoint" > "$tmp/over-items.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/over-items.json"
jq '.approvalRequests = [range(0;16) | {approvalId:("APR-"+tostring),gateId:("GATE-"+tostring)}]' "$checkpoint" > "$tmp/approvals-16.json"
"$validator" validate-model phase-checkpoint "$tmp/approvals-16.json" || fail '16 approval requests were rejected'
jq '.approvalRequests = [range(0;17) | {approvalId:("APR-"+tostring),gateId:("GATE-"+tostring)}]' "$checkpoint" > "$tmp/approvals-17.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/approvals-17.json"

# CTX-01 usage-summary-v1 has no retroactive 32 KiB host cap.
jq '.providerVersion = ("v" * 40000)' "$fixtures/valid/usage-summary.json" > "$tmp/large-usage.json"
"$validator" validate-model usage-summary "$tmp/large-usage.json" || fail 'historically valid large usage summary was rejected'

mkdir -p "$tmp/project"
for unsafe_path in '../outside.json' '/tmp/outside.json' 'dir/../outside.json'; do
  rejects "$validator" write-model phase-checkpoint "$checkpoint" "$tmp/project" "$unsafe_path"
done
jq '.workspace = "../outside"' "$envelope" > "$tmp/unsafe-workspace.json"
rejects "$validator" validate-structure execution-envelope "$tmp/unsafe-workspace.json"
jq '.items[0].localPath = "/tmp/outside"' "$fixtures/valid/evidence-manifest.json" > "$tmp/unsafe-evidence.json"
rejects "$validator" validate-model evidence-manifest "$tmp/unsafe-evidence.json"
mkdir -p "$tmp/project/.mana"
ln -s "$tmp/outside" "$tmp/project/.mana/link"
rejects "$validator" write-model phase-checkpoint "$checkpoint" "$tmp/project" '.mana/link/checkpoint.json'
mkfifo "$tmp/project/pipe"
rejects "$validator" write-model phase-checkpoint "$checkpoint" "$tmp/project" pipe
rejects "$validator" validate-model phase-checkpoint "$tmp/project/pipe"
ln -s "$checkpoint" "$tmp/checkpoint-link.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/checkpoint-link.json"
mkdir -p "$tmp/read-root/normal/nested" "$tmp/read-outside/intermediate"
cp "$checkpoint" "$tmp/read-root/normal/nested/checkpoint.json"
"$validator" validate-model phase-checkpoint "$tmp/read-root/normal/nested/checkpoint.json" || fail 'normal nested input parent was rejected'
ln -s "$tmp/read-outside" "$tmp/read-root/parent-link"
cp "$checkpoint" "$tmp/read-outside/checkpoint.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/read-root/parent-link/checkpoint.json"
mkdir -p "$tmp/read-root/level-one"
ln -s "$tmp/read-outside/intermediate" "$tmp/read-root/level-one/intermediate-link"
cp "$checkpoint" "$tmp/read-outside/intermediate/checkpoint.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/read-root/level-one/intermediate-link/checkpoint.json"
mkfifo "$tmp/read-root/normal/nested/special.json"
rejects "$validator" validate-model phase-checkpoint "$tmp/read-root/normal/nested/special.json"

output="$("$validator" write-model phase-checkpoint "$checkpoint" "$tmp/project" '.mana/runtime/checkpoint.json')"
expected_output="$(realpath "$tmp/project/.mana/runtime/checkpoint.json")"
[ "$output" = "$expected_output" ] || fail 'writer returned unexpected path'
mode="$(stat -f '%Lp' "$output" 2>/dev/null || stat -c '%a' "$output")"
[ "$mode" = 600 ] || fail 'writer did not set mode 0600'
[ "$(tail -c 1 "$output" | od -An -tuC | tr -d ' ')" = 10 ] || fail 'writer output lacks final newline'

if rg -n '^[[:space:]]*(codex|claude|opencode|curl|wget|gh)([[:space:]]|$)' "$validator" "$root/scripts/lib/context-runtime.py" >/dev/null; then
  fail 'CTX-03 validator contains a provider or network invocation'
fi
echo 'Context Runtime CTX-03 schema tests passed (untrusted, bounded, zero-token)'
