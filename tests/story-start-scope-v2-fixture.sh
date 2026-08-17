#!/usr/bin/env bash
set -euo pipefail

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
fixture="$root/tests/fixtures/story-start-scope-v2/regression-topology-v1.json"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

command -v jq >/dev/null 2>&1 || fail "jq is required"
[ -f "$fixture" ] || fail "missing fixture: $fixture"

jq -e '
  .schemaVersion == "mana.story-start.regression-topology/v1" and
  .fixtureId == "story-start-synthetic-scope-leakage-001" and
  .fixtureRevision == 1 and
  .synthetic == true and
  .sanitization == {
    realIdentifiersPresent: false,
    reservedDomainsOnly: true,
    productionValuesPresent: false,
    notes: "All names, refs, hashes, paths, values, and ownership labels are invented for this fixture."
  } and
  (.story.fixtureStoryId | startswith("story-synthetic-")) and
  (.story.acceptanceCriteria | length) == 3 and
  (.decisions | length) == 3 and
  (.evidence | length) == 9 and
  (.conditionInventory | length) == 9
' "$fixture" >/dev/null || fail "fixture metadata or cardinality is invalid"

jq -e '
  ([.story.acceptanceCriteria[].id] | length) == ([.story.acceptanceCriteria[].id] | unique | length) and
  ([.decisions[].id] | length) == ([.decisions[].id] | unique | length) and
  ([.evidence[].id] | length) == ([.evidence[].id] | unique | length) and
  ([.conditionInventory[].conditionId] | length) == ([.conditionInventory[].conditionId] | unique | length) and
  ([.conditionInventory[].semanticCondition] | sort) == ([
    "best_effort_versus_durable_delivery_decision",
    "configuration_already_exists",
    "direct_and_federated_user_ambiguity",
    "implementation_branch_behind_baseline",
    "independent_pre_existing_bug",
    "legacy_null_semantics_inconsistency",
    "optional_hardening_or_refactoring",
    "pending_readiness_approval",
    "pre_existing_problem_conditionally_mandatory_by_criterion"
  ] | sort)
' "$fixture" >/dev/null || fail "fixture IDs or required semantic conditions are incomplete"

jq -e '
  . as $fixture |
  all(.conditionInventory[];
    all(.evidenceRefs[]; . as $id | any($fixture.evidence[]; .id == $id)) and
    all(.acceptanceCriterionRefs[]; . as $id | any($fixture.story.acceptanceCriteria[]; .id == $id)) and
    all(.decisionRefs[]; . as $id | any($fixture.decisions[]; .id == $id))
  )
' "$fixture" >/dev/null || fail "fixture contains a dangling reference"

jq -e '
  (.evidence[] | select(.id == "EV-BRANCH-01") | .facts.commitsBehind >= 10) and
  (.evidence[] | select(.id == "EV-CONFIG-01") | .facts.state == "already_present" and (.facts.entries | length) >= 2) and
  (.decisions[] | select(.id == "DEC-IDENTITY-01") | .status == "open") and
  (.decisions[] | select(.id == "DEC-DELIVERY-01") | .status == "open" and .optionRelationship == "mutually_exclusive" and (.options | length) == 2) and
  (.story.requirementApproval.status == "pending") and
  (.evidence[] | select(.id == "EV-NULL-01") | .facts.readerA.missingValueBehavior != .facts.readerB.missingValueBehavior) and
  (.evidence[] | select(.id == "EV-UNRELATED-BUG-01") | .facts.introducedBeforeStory == true and (.facts.affectedAcceptanceCriteria | length) == 0) and
  (.evidence[] | select(.id == "EV-AC-GAP-01") | .facts.introducedBeforeStory == true and .facts.affectedAcceptanceCriteria == ["AC-03"]) and
  (.evidence[] | select(.id == "EV-HARDENING-01") | (.facts.requiredByAcceptanceCriteria | length) == 0)
' "$fixture" >/dev/null || fail "fixture evidence does not preserve the required regression topology"

jq -e '
  [paths(scalars) as $path | ($path[-1] | tostring)] |
  all(.[]; . != "implementationTasks" and . != "effortEstimate" and . != "expectedClassification" and . != "expectedPlan")
' "$fixture" >/dev/null || fail "SS00 fixture encodes later-phase behavior"

echo "Story Start Scope v2 fixture integrity tests passed"
