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
for file in bundle.json COMPATIBILITY.md SEMANTIC-CONTRACT.md fixtures/fixture-manifest.json fixtures/representative-artifacts.json schemas/project.schema.json schemas/artifacts.schema.json schemas/artifact.schema.json schemas/source.schema.json schemas/work-items.schema.json schemas/work-item.schema.json schemas/project-context.schema.json schemas/activity.schema.json; do
  [ -f "$bundle/$file" ] || { echo "ERROR: missing bundle file: $file" >&2; exit 4; }
done
jq -e '.bundle=="mana-inspect-contract" and .version=="v1" and .owner=="Mana" and .modelCalls==0 and .network==false and (.schemas|length==8)' "$bundle/bundle.json" >/dev/null
jq -e '.schema=="mana.inspect.fixture-manifest/v1" and ([.cases[].id]|index("work-items-feature") and index("work-item-feature-full") and index("work-item-session") and index("work-item-sparse-attention-and-evidence") and index("project-context-missing-categories") and index("activity-explicit-and-filesystem-fallback") and index("empty-work-items"))' "$bundle/fixtures/fixture-manifest.json" >/dev/null
jq -e '([.[].family]|sort|unique)==["knowledge","learning","runtime","unknown","workspace"] and ([.[].kind]|index("repair-attempt-result") and index("verification-result") and index("runtime_events") and index("markdown") and index("journey") and index("journey_record"))' "$bundle/fixtures/representative-artifacts.json" >/dev/null
while IFS= read -r schema; do
  jq -e '."$schema"=="https://json-schema.org/draft/2020-12/schema" and .type=="object" and .additionalProperties==false' "$bundle/$schema" >/dev/null
done < <(jq -r '.schemas[]' "$bundle/bundle.json")
while IFS= read -r response; do
  [ -f "$bundle/fixtures/$response" ] || { echo "ERROR: missing fixture response: $response" >&2; exit 4; }
  jq -e 'type=="object" and (.schema|type=="string" and test("^mana\\.inspect\\."))' "$bundle/fixtures/$response" >/dev/null
  ! grep -Eq '"/(Users|home|private|tmp)/|[A-Za-z]:\\\\' "$bundle/fixtures/$response" || { echo "ERROR: absolute path in fixture: $response" >&2; exit 4; }
done < <(jq -r '.cases[].response' "$bundle/fixtures/fixture-manifest.json" | LC_ALL=C sort -u)
jq -e '.schema=="mana.inspect.work-items/v1" and ([.work_items[].work_item_id]|length)==([.work_items[].work_item_id]|unique|length) and all(.work_items[]; .work_item_id|test("^(feature|session):[A-Za-z0-9][A-Za-z0-9._-]*$"))' "$bundle/fixtures/work-items.json" "$bundle/fixtures/empty-work-items.json" >/dev/null
jq -e '.schema=="mana.inspect.work-item/v1" and all(.sections[]; .section_id|IN("overview","requirements","plan","decisions","evidence","review","timeline","artifacts")) and all(.attention_items[]; .category|IN("blocker","failed_verification","stale_evidence","pending_decision","owner_review","review_required","contract_diagnostic"))' "$bundle/fixtures/feature-work-item.json" "$bundle/fixtures/session-work-item.json" "$bundle/fixtures/sparse-work-item.json" >/dev/null
jq -e '.schema=="mana.inspect.project-context/v1" and ([.categories[].category]|sort|unique)==["architecture","database_policy","engineering_guards","glossary","integrations","learning_journeys","project_decisions","testing_policy"]' "$bundle/fixtures/project-context.json" >/dev/null
jq -e '.schema=="mana.inspect.activity/v1" and all(.events[]; ((.timestamp.value|length)>0) and (.timestamp.provenance|IN("explicit_domain_timestamp","filesystem_mtime_epoch")))' "$bundle/fixtures/activity.json" >/dev/null
for invalid in fixtures/invalid/unstable-work-item-id.json fixtures/invalid/unsafe-artifact-path.json fixtures/invalid/activity-no-time-basis.json fixtures/invalid/undeclared-enum.json fixtures/invalid/duplicate-event-ids.json; do
  [ -f "$bundle/$invalid" ] || { echo "ERROR: missing invalid fixture: $invalid" >&2; exit 4; }
done
jq -e '.work_items[0].work_item_id|test("^(feature|session):[A-Za-z0-9][A-Za-z0-9._-]*$")|not' "$bundle/fixtures/invalid/unstable-work-item-id.json" >/dev/null
jq -e '.work_items[0].artifacts[0].path|contains("/../")' "$bundle/fixtures/invalid/unsafe-artifact-path.json" >/dev/null
jq -e '(.events[0].timestamp.value|length)==0 or (.events[0].timestamp.provenance|IN("explicit_domain_timestamp","filesystem_mtime_epoch")|not)' "$bundle/fixtures/invalid/activity-no-time-basis.json" >/dev/null
jq -e '.events[0].event_kind|IN("workspace_created","verification_completed","review_recorded","decision_recorded","artifact_updated","unknown")|not' "$bundle/fixtures/invalid/undeclared-enum.json" >/dev/null
jq -e '([.events[].event_id]|length) != ([.events[].event_id]|unique|length)' "$bundle/fixtures/invalid/duplicate-event-ids.json" >/dev/null
echo "Mana inspect v1 contract bundle validation passed"
