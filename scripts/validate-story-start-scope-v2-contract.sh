#!/usr/bin/env bash
# Offline structural validation for the additive Story Start Scope v2 contract.
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
bundle="$root/contracts/story-start/scope-v2"
evaluator="$root/tests/lib/json_schema_subset.py"

usage() {
  echo "Usage: scripts/validate-story-start-scope-v2-contract.sh [--bundle <path>]"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --bundle)
      bundle="${2:-}"
      [ -n "$bundle" ] || { echo 'ERROR: --bundle requires a path' >&2; exit 2; }
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

bundle="$(cd "$bundle" 2>/dev/null && pwd -P)" || {
  echo 'ERROR: unreadable bundle' >&2
  exit 2
}

command -v jq >/dev/null 2>&1 || { echo 'ERROR: jq is required' >&2; exit 5; }
command -v python3 >/dev/null 2>&1 || { echo 'ERROR: python3 is required' >&2; exit 5; }
[ -f "$evaluator" ] || { echo 'ERROR: missing offline schema evaluator' >&2; exit 4; }

for file in bundle.json COMPATIBILITY.md SEMANTIC-CONTRACT.md; do
  [ -f "$bundle/$file" ] || { echo "ERROR: missing bundle file: $file" >&2; exit 4; }
done

jq -e '
  .bundle == "mana-story-start-scope-contract" and
  .version == "v2" and
  .owner == "Mana" and
  .modelCalls == 0 and
  .network == false and
  .runtimeEnabled == false and
  (.schemas | length == 8) and
  (.fixtures | length == 6)
' "$bundle/bundle.json" >/dev/null

while IFS= read -r relative_path; do
  [ -f "$bundle/$relative_path" ] || {
    echo "ERROR: missing declared bundle file: $relative_path" >&2
    exit 4
  }
  jq empty "$bundle/$relative_path"
done < <(jq -r '.schemas[], .fixtures[]' "$bundle/bundle.json")

while IFS= read -r schema; do
  jq -e '
    ."$schema" == "https://json-schema.org/draft/2020-12/schema" and
    .type == "object" and
    .additionalProperties == false
  ' "$bundle/$schema" >/dev/null
done < <(jq -r '.schemas[]' "$bundle/bundle.json")

schema_for_fixture() {
  case "$(jq -r '.schemaVersion' "$1")" in
    mana.story-start.discovery-inventory/v2)
      echo "$bundle/schemas/discovery-inventory.schema.json"
      ;;
    mana.story-start.scope-triage/v2)
      echo "$bundle/schemas/scope-triage.schema.json"
      ;;
    mana.story-start.decision-register/v2)
      echo "$bundle/schemas/decision-register.schema.json"
      ;;
    mana.story-start.implementation-plan/v2)
      echo "$bundle/schemas/implementation-plan.schema.json"
      ;;
    mana.story-start.scenario-estimates/v2)
      echo "$bundle/schemas/scenario-estimates.schema.json"
      ;;
    mana.story-start.provenance/v2)
      echo "$bundle/schemas/provenance.schema.json"
      ;;
    *)
      echo "ERROR: unsupported fixture schemaVersion in $1" >&2
      return 1
      ;;
  esac
}

while IFS= read -r fixture; do
  fixture_path="$bundle/$fixture"
  schema_path="$(schema_for_fixture "$fixture_path")"
  python3 "$evaluator" "$schema_path" "$fixture_path"
  if grep -Eq '"/(Users|home|private|tmp)/|[A-Za-z]:\\\\' "$fixture_path"; then
    echo "ERROR: real absolute path in synthetic fixture: $fixture" >&2
    exit 4
  fi
done < <(jq -r '.fixtures[]' "$bundle/bundle.json")

discovery="$bundle/fixtures/valid/discovery-existing-configuration.json"
triage="$bundle/fixtures/valid/triage-independent-defect.json"
decisions="$bundle/fixtures/valid/decision-register-open-exclusive.json"
plan="$bundle/fixtures/valid/implementation-plan-separated-scope.json"
estimates="$bundle/fixtures/valid/scenario-estimates-open-decision.json"

# 1. An independent defect is explicit and excluded from base-plan work.
jq -e '
  any(.classifications[]; .category == "RELATED_DEFECT" and .includedInBasePlan == false)
' "$triage" >/dev/null
jq -e '
  any(.relatedFindings[]; .originCategory == "RELATED_DEFECT" and .excludedFromBasePlan == true) and
  all(.basePlan[]; .originCategory == "CORE_SCOPE")
' "$plan" >/dev/null

# 2. A required enabling fix carries evidence and an approved reason for promotion.
jq -e '
  all(.requiredEnablers[];
    .originCategory == "REQUIRED_ENABLER" and
    (.evidenceRefs | length) > 0 and
    (((.acceptanceCriterionRefs | length) > 0) or ((.mandatoryConstraintRefs | length) > 0)))
' "$plan" >/dev/null

# SS04 task provenance and decision-option linkage are structural invariants.
jq -e '
  all(.basePlan[]; (.provenanceRefs | length) > 0) and
  all(.requiredEnablers[].tasks[]; (.provenanceRefs | length) > 0) and
  all(.conditionalBranches[];
    (.decisionOptionRef | length) > 0 and
    all(.tasks[]; (.provenanceRefs | length) > 0))
' "$plan" >/dev/null

# 3. The open decision is represented by two mutually exclusive branches.
jq -e '
  any(.decisionRegister[];
    .status == "open" and .selectedOptionId == null and (.options | length) == 2) and
  any(.branchGroups[];
    .relationship == "mutually_exclusive" and
    .selectionRule == "exactly_one" and
    (.branchRefs | length) == 2)
' "$plan" >/dev/null

# 7. Zero engineering effort does not erase unknown calendar impact.
jq -e '
  any(.readinessPrerequisites[];
    .engineeringEffort.minimumPersonHours == 0 and
    .engineeringEffort.additionalPersonHours == 0 and
    .calendarImpact.status == "unknown")
' "$plan" >/dev/null

# 9. Existing configuration is observed evidence and a VERIFIED_FACT, never work.
jq -e '
  any(.evidence[];
    .kind == "configuration" and
    .epistemicStatus == "observed" and
    .capabilityState == "already_exists")
' "$discovery" >/dev/null
jq -e '
  any(.classifications[];
    .category == "VERIFIED_FACT" and .includedInBasePlan == false)
' "$triage" >/dev/null

# Open material decisions yield scenario-only estimates and no committed total.
jq -e '
  (.estimateSet.openMaterialDecisionRefs | length) > 0 and
  .estimateSet.finalCommittedEstimate == null and
  all(.estimateSet.scenarios[]; .finality == "scenario_only")
' "$estimates" >/dev/null

invalid_dir="$(mktemp -d "${TMPDIR:-/tmp}/mana-scope-v2-invalid.XXXXXX")"
trap 'rm -rf "$invalid_dir"' EXIT

expect_invalid() {
  label="$1"
  schema="$2"
  instance="$3"
  if python3 "$evaluator" "$schema" "$instance" >/dev/null 2>&1; then
    echo "ERROR: invalid case was accepted: $label" >&2
    exit 1
  fi
}

# 4. Conditional work cannot be smuggled into the base plan.
jq '.basePlan[0].originCategory = "CONDITIONAL_SCOPE"' "$plan" >"$invalid_dir/conditional-in-base.json"
expect_invalid \
  'conditional work in base plan' \
  "$bundle/schemas/implementation-plan.schema.json" \
  "$invalid_dir/conditional-in-base.json"

# 5. A related defect cannot be smuggled into the base plan.
jq '.basePlan[0].originCategory = "RELATED_DEFECT"' "$plan" >"$invalid_dir/related-in-base.json"
expect_invalid \
  'related defect in base plan' \
  "$bundle/schemas/implementation-plan.schema.json" \
  "$invalid_dir/related-in-base.json"

# 6. An open decision cannot carry a selected final option.
jq '.decisions[0].selectedOptionId = .decisions[0].options[0].id' "$decisions" >"$invalid_dir/open-selected.json"
expect_invalid \
  'selected option on open decision' \
  "$bundle/schemas/decision-register.schema.json" \
  "$invalid_dir/open-selected.json"

# 8a. Negative effort is invalid.
jq '.basePlan[0].effort.minimumPersonHours = -1' "$plan" >"$invalid_dir/negative-effort.json"
expect_invalid \
  'negative effort range' \
  "$bundle/schemas/implementation-plan.schema.json" \
  "$invalid_dir/negative-effort.json"

# 8b. Ranges are minimum + non-negative delta; a negative delta is inverted.
jq '
  .basePlan[0].effort.minimumPersonHours = 8 |
  .basePlan[0].effort.additionalPersonHours = -4
' "$plan" >"$invalid_dir/inverted-effort.json"
expect_invalid \
  'inverted effort range' \
  "$bundle/schemas/implementation-plan.schema.json" \
  "$invalid_dir/inverted-effort.json"

# Required-enabler evidence is a schema-level invariant.
jq '.requiredEnablers[0].evidenceRefs = []' "$plan" >"$invalid_dir/enabler-without-evidence.json"
expect_invalid \
  'required enabler without evidence' \
  "$bundle/schemas/implementation-plan.schema.json" \
  "$invalid_dir/enabler-without-evidence.json"

# 10. Version dispatch is explicit and a v1 label is rejected by the v2 schema.
jq '.schemaVersion = "mana.story-start.discovery-inventory/v1"' "$discovery" >"$invalid_dir/wrong-version.json"
expect_invalid \
  'wrong schema version' \
  "$bundle/schemas/discovery-inventory.schema.json" \
  "$invalid_dir/wrong-version.json"

echo 'Story Start Scope v2 contract validation passed (zero model/provider calls)'
