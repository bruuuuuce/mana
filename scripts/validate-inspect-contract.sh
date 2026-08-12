#!/usr/bin/env bash
# Validates a copied Mana inspect v1 bundle without a project workspace.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
bundle="$root/contracts/mana-inspect/v1"
usage() { echo "Usage: scripts/validate-inspect-contract.sh [--bundle <path>]"; }
while [ "$#" -gt 0 ]; do
  case "$1" in --bundle) bundle="${2:-}"; [ -n "$bundle" ] || { echo 'ERROR: --bundle requires a path' >&2; exit 2; }; shift 2 ;;
    --help|-h) usage; exit 0 ;; *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;; esac
done
bundle="$(cd "$bundle" 2>/dev/null && pwd -P)" || { echo 'ERROR: unreadable bundle' >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo 'ERROR: jq is required' >&2; exit 5; }
for file in bundle.json COMPATIBILITY.md fixtures/fixture-manifest.json fixtures/representative-artifacts.json schemas/project.schema.json schemas/artifacts.schema.json schemas/artifact.schema.json schemas/source.schema.json; do
  [ -f "$bundle/$file" ] || { echo "ERROR: missing bundle file: $file" >&2; exit 4; }
done
jq -e '.bundle=="mana-inspect-contract" and .version=="v1" and .owner=="Mana" and .modelCalls==0 and .network==false and (.schemas|length==4)' "$bundle/bundle.json" >/dev/null
jq -e '.schema=="mana.inspect.fixture-manifest/v1" and ([.cases[].id]|sort)==["bounded-repair","journey-concept-diagram","minimal-project","missing-source","mixed-workspaces","no-mana","pr-review-markdown","runtime-events","stale-source","unknown-and-malformed","user-learning","verification-success-and-failure"]' "$bundle/fixtures/fixture-manifest.json" >/dev/null
jq -e '([.[].family]|sort|unique)==["knowledge","learning","runtime","unknown","workspace"] and ([.[].kind]|index("repair-attempt-result") and index("verification-result") and index("runtime_events") and index("markdown") and index("journey") and index("journey_record"))' "$bundle/fixtures/representative-artifacts.json" >/dev/null
while IFS= read -r schema; do
  jq -e '."$schema"=="https://json-schema.org/draft/2020-12/schema" and .type=="object" and .additionalProperties==false' "$bundle/$schema" >/dev/null
done < <(jq -r '.schemas[]' "$bundle/bundle.json")
while IFS= read -r response; do
  [ -f "$bundle/fixtures/$response" ] || { echo "ERROR: missing fixture response: $response" >&2; exit 4; }
  jq -e 'type=="object" and (.schema|type=="string" and test("^mana\\.inspect\\."))' "$bundle/fixtures/$response" >/dev/null
  ! grep -Eq '"/(Users|home|private|tmp)/|[A-Za-z]:\\\\' "$bundle/fixtures/$response" || { echo "ERROR: absolute path in fixture: $response" >&2; exit 4; }
done < <(jq -r '.cases[].response' "$bundle/fixtures/fixture-manifest.json" | LC_ALL=C sort -u)
echo "Mana inspect v1 contract bundle validation passed"
