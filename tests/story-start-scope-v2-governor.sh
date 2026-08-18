#!/usr/bin/env bash
# SS05 zero-token acceptance for the deterministic host-side Scope Governor.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
story="$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json"
discovery_raw="$root/tests/fixtures/story-start-scope-v2/discovery/provider-output.json"
triage_raw="$root/tests/fixtures/story-start-scope-v2/triage/provider-output.json"
plan_raw="$root/tests/fixtures/story-start-scope-v2/planner/provider-output.json"
normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
governor="$root/scripts/lib/story-start-scope-v2-govern.py"
schema_root="$root/contracts/story-start/scope-v2/schemas"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-governor-v2.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/story-start-scope-v2.sh"

python3 "$normalizer" normalize-discovery "$schema_root/discovery-inventory.schema.json" "$discovery_raw" "$tmp/discovery.json"
python3 "$normalizer" normalize-triage "$schema_root/scope-triage.schema.json" "$tmp/discovery.json" "$triage_raw" "$tmp/triage.json"
python3 "$normalizer" build-planning-context "$tmp/discovery.json" "$tmp/triage.json" "$tmp/context.json"
python3 "$normalizer" normalize-plan "$schema_root/implementation-plan.schema.json" "$tmp/context.json" "$tmp/triage.json" "$plan_raw" "$tmp/plan.json"

expect_code() {
  local candidate="$1" code="$2" label="$3" report
  report="$tmp/report-$label.json"
  if python3 "$governor" validate "$tmp/discovery.json" "$tmp/triage.json" "$candidate" "$report" >/dev/null 2>&1; then
    fail "$label was accepted"
  fi
  python3 "$governor" validate-report "$report"
  jq -e --arg code "$code" '
    .status=="failed" and .validationPass==1 and
    (.violations|map(.code)|index($code)!=null) and
    ([.violations[] | [.code,.kind,.artifact,.path,(.entityId//""),(.relatedRefs|join(",")),.message]] ==
      ([.violations[] | [.code,.kind,.artifact,.path,(.entityId//""),(.relatedRefs|join(",")),.message]] | sort))
  ' "$report" >/dev/null || fail "$label did not emit deterministic code $code"
}

expect_triage_code() {
  local candidate_triage="$1" code="$2" label="$3" report
  report="$tmp/report-$label.json"
  if python3 "$governor" validate "$tmp/discovery.json" "$candidate_triage" "$tmp/plan.json" "$report" >/dev/null 2>&1; then
    fail "$label was accepted"
  fi
  python3 "$governor" validate-report "$report"
  jq -e --arg code "$code" '.status=="failed" and (.violations|map(.code)|index($code)!=null)' "$report" >/dev/null || fail "$label did not emit $code"
}

# Positive baseline: the complete normalized SS04 bundle is valid and stable.
python3 "$governor" validate "$tmp/discovery.json" "$tmp/triage.json" "$tmp/plan.json" "$tmp/valid-a.json"
python3 "$governor" validate "$tmp/discovery.json" "$tmp/triage.json" "$tmp/plan.json" "$tmp/valid-b.json"
cmp -s "$tmp/valid-a.json" "$tmp/valid-b.json" || fail 'valid governance report is not deterministic'
jq -e '
  .status=="passed" and .semanticValidation=="passed" and
  .schemaValidation=={"discovery":"valid","implementationPlan":"valid","triage":"valid"} and
  .violations==[] and .initialViolations==[] and
  .correction=={"attemptCount":0,"outcome":"not_attempted"} and
  .ownerReview.state=="not_required"
' "$tmp/valid-a.json" >/dev/null || fail 'valid bundle did not pass the governor'

# 1. Missing AC reference and wrong entity type are distinguished.
jq '.basePlan[0].acceptanceCriterionRefs=["ac_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]' "$tmp/plan.json" > "$tmp/missing-ac.json"
expect_code "$tmp/missing-ac.json" REFERENCE_AC_NOT_FOUND missing-ac
evidence_id="$(jq -r '.evidence[0].id' "$tmp/discovery.json")"
jq --arg ref "$evidence_id" '.basePlan[0].acceptanceCriterionRefs=[$ref]' "$tmp/plan.json" > "$tmp/wrong-reference-type.json"
expect_code "$tmp/wrong-reference-type.json" REFERENCE_ENTITY_TYPE_MISMATCH wrong-reference-type

# 2. Duplicate entity IDs and task IDs are rejected across plan sections.
jq '.requiredEnablers[0].tasks += [.requiredEnablers[0].tasks[0]]' "$tmp/plan.json" > "$tmp/duplicate-task.json"
expect_code "$tmp/duplicate-task.json" DUPLICATE_TASK_ID duplicate-task
jq '.conditionalBranches += [.conditionalBranches[0]]' "$tmp/plan.json" > "$tmp/duplicate-branch.json"
expect_code "$tmp/duplicate-branch.json" DUPLICATE_ID duplicate-branch

# 3-4. Related and conditional classifications cannot be smuggled into base.
related_ref="$(jq -r '.classifications[] | select(.category=="RELATED_DEFECT") | .id' "$tmp/triage.json")"
jq --arg ref "$related_ref" '.basePlan[0].classificationRef=$ref' "$tmp/plan.json" > "$tmp/related-in-base.json"
expect_code "$tmp/related-in-base.json" BASE_ORIGIN_NOT_CORE_SCOPE related-in-base
conditional_ref="$(jq -r '.classifications[] | select(.category=="CONDITIONAL_SCOPE") | .id' "$tmp/triage.json" | head -1)"
jq --arg ref "$conditional_ref" '.basePlan[0].classificationRef=$ref' "$tmp/plan.json" > "$tmp/conditional-in-base.json"
expect_code "$tmp/conditional-in-base.json" BASE_ORIGIN_NOT_CORE_SCOPE conditional-in-base

# 5. Optional improvement cannot masquerade as a required enabler.
optional_ref="$(jq -r '.classifications[] | select(.category=="OPTIONAL_IMPROVEMENT") | .id' "$tmp/triage.json")"
jq --arg ref "$optional_ref" '.requiredEnablers[0].classificationRef=$ref' "$tmp/plan.json" > "$tmp/optional-enabler.json"
expect_code "$tmp/optional-enabler.json" OPTIONAL_AS_REQUIRED_ENABLER optional-enabler
jq '.requiredEnablers[0].evidenceRefs=[]' "$tmp/plan.json" > "$tmp/enabler-no-evidence.json"
expect_code "$tmp/enabler-no-evidence.json" ENABLER_EVIDENCE_MISSING enabler-no-evidence
jq '.requiredEnablers[0].acceptanceCriterionRefs=[] | .requiredEnablers[0].mandatoryConstraintRefs=[]' "$tmp/plan.json" > "$tmp/enabler-no-requirement.json"
expect_code "$tmp/enabler-no-requirement.json" ENABLER_REQUIREMENT_REF_MISSING enabler-no-requirement

# Evidence gaps cannot be promoted into chosen work, and known pre-existing
# status cannot be rewritten while promoting a mandatory enabler.
gap_finding="$(jq -r '.findings[] | select(.findingKind=="evidence_gap") | .id' "$tmp/discovery.json")"
jq --arg ref "$gap_finding" '(.classifications[] | select(.findingRef==$ref) | .category)="CORE_SCOPE"' "$tmp/triage.json" > "$tmp/evidence-gap-promoted.json"
expect_triage_code "$tmp/evidence-gap-promoted.json" EVIDENCE_GAP_PROMOTED_TO_SCOPE evidence-gap-promoted
jq '(.classifications[] | select(.mandatoryReason=="data_integrity_constraint") | .promotionAssessment.preExistingStatus)="no"' "$tmp/triage.json" > "$tmp/preexisting-rewritten.json"
expect_triage_code "$tmp/preexisting-rewritten.json" ENABLER_PREEXISTING_STATUS_CHANGED preexisting-rewritten

# 6. An open decision cannot carry a selected option, even when schema-invalid.
jq '(.decisionRegister[0].selectedOptionId)=.decisionRegister[0].options[0].id' "$tmp/plan.json" > "$tmp/open-selected.json"
expect_code "$tmp/open-selected.json" OPEN_DECISION_SELECTED_OPTION open-selected
jq -e '.violations|map(.kind)|index("structural")!=null' "$tmp/report-open-selected.json" >/dev/null || fail 'schema and semantic diagnostics were not separated'

# 7. Branch decision/condition/group integrity is host-enforced.
jq 'del(.conditionalBranches[0].decisionRef)' "$tmp/plan.json" > "$tmp/branch-no-decision.json"
expect_code "$tmp/branch-no-decision.json" BRANCH_DECISION_REF_MISSING branch-no-decision
jq '.conditionalBranches[0].groupRef=.branchGroups[1].id' "$tmp/plan.json" > "$tmp/branch-wrong-group.json"
expect_code "$tmp/branch-wrong-group.json" BRANCH_GROUP_MEMBERSHIP_MISMATCH branch-wrong-group
branch_decision="$(jq -r '.conditionalBranches[0].decisionRef' "$tmp/plan.json")"
foreign_option="$(jq -r --arg decision "$branch_decision" '.decisionRegister[] | select(.id!=$decision) | .options[0].id' "$tmp/plan.json" | head -1)"
jq --arg ref "$foreign_option" '.conditionalBranches[0].decisionOptionRef=$ref' "$tmp/plan.json" > "$tmp/branch-foreign-option.json"
expect_code "$tmp/branch-foreign-option.json" BRANCH_OPTION_NOT_IN_DECISION branch-foreign-option

# 8. Mutually exclusive siblings cannot coexist in one scenario.
jq '
  . as $plan |
  .scenarioEstimates.scenarios[0] as $scenario |
  ([.branchGroups[] | select(([.branchRefs[] as $ref | $scenario.selectedBranchRefs[] | select(.==$ref)]|length)==1)] | .[0]) as $group |
  ($group.branchRefs - $scenario.selectedBranchRefs)[0] as $sibling |
  ($plan.conditionalBranches[] | select(.id==$sibling).effort) as $effort |
  .scenarioEstimates.scenarios[0].selectedBranchRefs += [$sibling] |
  .scenarioEstimates.scenarios[0].conditionalDeltas += [{"branchRef":$sibling,"effort":$effort}] |
  .scenarioEstimates.scenarios[0].engineeringTotal.minimumPersonHours += $effort.minimumPersonHours |
  .scenarioEstimates.scenarios[0].engineeringTotal.additionalPersonHours += $effort.additionalPersonHours
' "$tmp/plan.json" > "$tmp/exclusive-siblings.json"
expect_code "$tmp/exclusive-siblings.json" SCENARIO_EXCLUSIVE_BRANCH_CONFLICT exclusive-siblings

# Contract variants are enforced too: zero-or-one rejects two selections and
# explicitly combinable groups require every applicable branch.
jq '
  . as $plan |
  .scenarioEstimates.scenarios[0] as $scenario |
  .branchGroups[0].branchRefs as $refs |
  ($refs - $scenario.selectedBranchRefs)[0] as $sibling |
  ($plan.conditionalBranches[] | select(.id==$sibling).effort) as $effort |
  .branchGroups[0].relationship="dependent" |
  .branchGroups[0].selectionRule="zero_or_one" |
  (.conditionalBranches[] | select(.id as $id | $refs|index($id)!=null) | .relationship)="dependent" |
  .scenarioEstimates.scenarios[0].selectedBranchRefs += [$sibling] |
  .scenarioEstimates.scenarios[0].conditionalDeltas += [{"branchRef":$sibling,"effort":$effort}] |
  .scenarioEstimates.scenarios[0].engineeringTotal.minimumPersonHours += $effort.minimumPersonHours |
  .scenarioEstimates.scenarios[0].engineeringTotal.additionalPersonHours += $effort.additionalPersonHours
' "$tmp/plan.json" > "$tmp/zero-or-one-conflict.json"
expect_code "$tmp/zero-or-one-conflict.json" SCENARIO_ZERO_OR_ONE_BRANCH_CONFLICT zero-or-one-conflict
jq '
  .branchGroups[0].branchRefs as $refs |
  .branchGroups[0].relationship="combinable" |
  .branchGroups[0].selectionRule="all_applicable" |
  (.conditionalBranches[] | select(.id as $id | $refs|index($id)!=null) | .relationship)="combinable"
' "$tmp/plan.json" > "$tmp/combinable-missing.json"
expect_code "$tmp/combinable-missing.json" SCENARIO_COMBINABLE_BRANCH_MISSING combinable-missing

# 9. Branch effort hidden in the base estimate is rejected independently.
jq '.scenarioEstimates.baseEffort.minimumPersonHours += .conditionalBranches[0].effort.minimumPersonHours' "$tmp/plan.json" > "$tmp/branch-in-base-estimate.json"
expect_code "$tmp/branch-in-base-estimate.json" BASE_EFFORT_MISMATCH branch-in-base-estimate

# 10. Approval lead time remains calendar impact, never developer effort.
approval_evidence="$(jq -r '.evidence[] | select(.kind=="human_decision") | .id' "$tmp/discovery.json" | head -1)"
jq --arg ref "$approval_evidence" '(.readinessPrerequisites[] | select(.evidenceRefs|index($ref)!=null) | .engineeringEffort.minimumPersonHours)=1' "$tmp/plan.json" > "$tmp/approval-effort.json"
expect_code "$tmp/approval-effort.json" READINESS_APPROVAL_EFFORT_NONZERO approval-effort

# 11. Existing configuration cannot be converted into an add task.
config_evidence="$(jq -r '.evidence[] | select(.kind=="configuration" and .capabilityState=="already_exists") | .id' "$tmp/discovery.json")"
jq --arg ref "$config_evidence" '(.basePlan[] | select(.evidenceRefs|index($ref)!=null) | .title)="Add configuration channel"' "$tmp/plan.json" > "$tmp/create-existing-config.json"
expect_code "$tmp/create-existing-config.json" EXISTING_CAPABILITY_CREATION_TASK create-existing-config

# 12. The real security/data-integrity mandatory enabler is accepted.
data_classification="$(jq -r '.classifications[] | select(.category=="REQUIRED_ENABLER" and .mandatoryReason=="data_integrity_constraint") | .id' "$tmp/triage.json")"
jq -e --arg ref "$data_classification" 'any(.requiredEnablers[]; .classificationRef==$ref and .mandatoryReason=="data_integrity_constraint")' "$tmp/plan.json" >/dev/null || fail 'valid data-integrity enabler is absent'
jq -e '.status=="passed"' "$tmp/valid-a.json" >/dev/null || fail 'valid data-integrity enabler was rejected'

# Additional estimate/state invariants: non-negative ranges, exact totals, and no open-decision final total.
jq '.basePlan[0].effort.minimumPersonHours=-1' "$tmp/plan.json" > "$tmp/negative-effort.json"
expect_code "$tmp/negative-effort.json" EFFORT_RANGE_INVALID negative-effort
jq '.scenarioEstimates.scenarios[0].engineeringTotal.minimumPersonHours += 1' "$tmp/plan.json" > "$tmp/bad-total.json"
expect_code "$tmp/bad-total.json" SCENARIO_TOTAL_MISMATCH bad-total
jq '.scenarioEstimates.finalCommittedEstimate={"estimateKind":"final_committed_total","unit":"person_hours","minimumPersonHours":1,"additionalPersonHours":0,"confidence":"low","rationale":"Invalid final total."}' "$tmp/plan.json" > "$tmp/open-final.json"
expect_code "$tmp/open-final.json" OPEN_MATERIAL_DECISION_FINAL_TOTAL open-final

# Direct task provenance and evidence references remain cross-artifact valid.
jq '.basePlan[0].provenanceRefs=["provenance_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]' "$tmp/plan.json" > "$tmp/missing-provenance.json"
expect_code "$tmp/missing-provenance.json" REFERENCE_PROVENANCE_NOT_FOUND missing-provenance

# Equivalent invalid inputs produce byte-identical, canonically ordered reports.
jq '.scenarioEstimates.scenarios|=reverse | .decisionRegister|=reverse | .relatedFindings|=reverse' "$tmp/create-existing-config.json" > "$tmp/create-existing-config-reordered.json"
python3 "$governor" validate "$tmp/discovery.json" "$tmp/triage.json" "$tmp/create-existing-config-reordered.json" "$tmp/reordered-report.json" >/dev/null 2>&1 && fail 'reordered invalid input was accepted'
cmp -s "$tmp/report-create-existing-config.json" "$tmp/reordered-report.json" || fail 'violation ordering/codes changed for equivalent invalid input'

# Fake provider for bounded correction and internal-pipeline wiring.
stub="$tmp/governor-provider-stub"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" call >> "$GOVERNOR_STUB_COUNT"' 'printf "%s\n" "$*" > "$GOVERNOR_STUB_ARGS"' 'cat "$GOVERNOR_STUB_OUTPUT"' > "$stub"
chmod +x "$stub"

# 13. One targeted correction succeeds and publishes only the corrected plan.
: > "$tmp/correction-count"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
GOVERNOR_STUB_COUNT="$tmp/correction-count" \
GOVERNOR_STUB_ARGS="$tmp/correction-args" \
GOVERNOR_STUB_OUTPUT="$tmp/plan.json" \
mana_story_start_scope_v2_govern_with_correction stub deterministic "$tmp/discovery.json" "$tmp/triage.json" "$tmp/create-existing-config.json" "$tmp/corrected-plan.json" "$tmp/corrected-report.json"
[ "$(wc -l < "$tmp/correction-count" | tr -d ' ')" = 1 ] || fail 'successful correction was not bounded to one call'
cmp -s "$tmp/plan.json" "$tmp/corrected-plan.json" || fail 'successful correction did not publish the governed plan'
jq -e '
  .status=="passed" and .validationPass==2 and
  .correction=={"attemptCount":1,"outcome":"succeeded"} and
  .violations==[] and
  (.initialViolations|map(.code)|index("EXISTING_CAPABILITY_CREATION_TASK")!=null) and
  .ownerReview.state=="not_required"
' "$tmp/corrected-report.json" >/dev/null || fail 'successful correction report is invalid'
grep -Fq 'INVALID_IMPLEMENTATION_PLAN_V2' "$tmp/correction-args" || fail 'correction did not receive the invalid artifact'
grep -Fq 'SCOPE_GOVERNOR_VIOLATION_REPORT_V2' "$tmp/correction-args" || fail 'correction did not receive the compact violation report'
grep -Fq 'This is one bounded correction attempt, not replanning.' "$tmp/correction-args" || fail 'correction prompt permits replanning'

# 14. A second failure stops with needs_owner_review and no plan publication.
: > "$tmp/second-failure-count"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
GOVERNOR_STUB_COUNT="$tmp/second-failure-count" \
GOVERNOR_STUB_ARGS="$tmp/second-failure-args" \
GOVERNOR_STUB_OUTPUT="$tmp/create-existing-config.json" \
mana_story_start_scope_v2_govern_with_correction stub deterministic "$tmp/discovery.json" "$tmp/triage.json" "$tmp/create-existing-config.json" "$tmp/should-not-publish.json" "$tmp/owner-review.json" >/dev/null 2>&1 && fail 'second invalid artifact was accepted'
[ "$(wc -l < "$tmp/second-failure-count" | tr -d ' ')" = 1 ] || fail 'second failure triggered more than one correction call'
[ ! -e "$tmp/should-not-publish.json" ] || fail 'invalid corrected artifact was published'
jq -e '
  .status=="needs_owner_review" and .validationPass==2 and
  .correction=={"attemptCount":1,"outcome":"failed"} and
  .ownerReview.state=="required" and (.violations|length)>0 and (.initialViolations|length)>0
' "$tmp/owner-review.json" >/dev/null || fail 'second failure did not yield owner review'

# Provider failure consumes the one correction slot and also fails closed.
failing_stub="$tmp/governor-failing-stub"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" call >> "$GOVERNOR_STUB_COUNT"' 'exit 7' > "$failing_stub"
chmod +x "$failing_stub"
: > "$tmp/provider-failure-count"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$failing_stub" \
GOVERNOR_STUB_COUNT="$tmp/provider-failure-count" \
mana_story_start_scope_v2_govern_with_correction stub deterministic "$tmp/discovery.json" "$tmp/triage.json" "$tmp/create-existing-config.json" "$tmp/provider-failure-plan.json" "$tmp/provider-failure-report.json" >/dev/null 2>&1 && fail 'failed corrective provider was accepted'
[ "$(wc -l < "$tmp/provider-failure-count" | tr -d ' ')" = 1 ] || fail 'provider failure exceeded one corrective call'
[ ! -e "$tmp/provider-failure-plan.json" ] || fail 'provider failure published a plan'
jq -e '.status=="needs_owner_review" and .correction=={"attemptCount":1,"outcome":"provider_failed"} and (.violations|map(.code)|index("CORRECTION_PROVIDER_FAILED")!=null)' "$tmp/provider-failure-report.json" >/dev/null || fail 'provider failure did not yield owner review'

# 15. Free-form/legacy correction never becomes a fallback artifact.
printf '%s\n' 'legacy free-form superset plan' > "$tmp/free-form.txt"
: > "$tmp/free-form-count"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
GOVERNOR_STUB_COUNT="$tmp/free-form-count" \
GOVERNOR_STUB_ARGS="$tmp/free-form-args" \
GOVERNOR_STUB_OUTPUT="$tmp/free-form.txt" \
mana_story_start_scope_v2_govern_with_correction stub deterministic "$tmp/discovery.json" "$tmp/triage.json" "$tmp/create-existing-config.json" "$tmp/legacy-fallback.json" "$tmp/free-form-report.json" >/dev/null 2>&1 && fail 'legacy fallback was accepted'
[ "$(wc -l < "$tmp/free-form-count" | tr -d ' ')" = 1 ] || fail 'free-form failure retried more than once'
[ ! -e "$tmp/legacy-fallback.json" ] || fail 'legacy fallback artifact was published'
jq -e '.status=="needs_owner_review" and .schemaValidation.implementationPlan=="invalid" and (.violations|map(.code)|index("STRUCTURAL_JSON_INVALID")!=null)' "$tmp/free-form-report.json" >/dev/null || fail 'free-form failure lacks structural owner-review diagnostics'

# Internal v2 pipeline publishes only after governance and does not correct a valid candidate.
: > "$tmp/pipeline-count"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
GOVERNOR_STUB_COUNT="$tmp/pipeline-count" \
GOVERNOR_STUB_ARGS="$tmp/pipeline-args" \
GOVERNOR_STUB_OUTPUT="$plan_raw" \
mana_story_start_scope_v2_plan_governed stub deterministic "$story" "$tmp/discovery.json" "$tmp/context.json" "$tmp/triage.json" "$tmp/pipeline-plan.json" "$tmp/pipeline-report.json"
[ "$(wc -l < "$tmp/pipeline-count" | tr -d ' ')" = 1 ] || fail 'valid governed pipeline made an unnecessary correction call'
cmp -s "$tmp/plan.json" "$tmp/pipeline-plan.json" || fail 'internal pipeline did not publish the normalized governed plan'
jq -e '.status=="passed" and .validationPass==1' "$tmp/pipeline-report.json" >/dev/null || fail 'internal pipeline lacks a passing governance report'

# A semantic first-pass failure inside the real internal pipeline gets exactly
# one correction, then the entire normalized bundle is governed again.
jq '.basePlan[0].title="Add configuration channel"' "$plan_raw" > "$tmp/pipeline-invalid-raw.json"
sequence_stub="$tmp/governor-sequence-stub"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s\n" call >> "$GOVERNOR_STUB_COUNT"' \
  'calls="$(wc -l < "$GOVERNOR_STUB_COUNT" | tr -d " ")"' \
  'if [ "$calls" = 1 ]; then cat "$GOVERNOR_STUB_FIRST"; else cat "$GOVERNOR_STUB_SECOND"; fi' \
  > "$sequence_stub"
chmod +x "$sequence_stub"
: > "$tmp/pipeline-correction-count"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$sequence_stub" \
GOVERNOR_STUB_COUNT="$tmp/pipeline-correction-count" \
GOVERNOR_STUB_FIRST="$tmp/pipeline-invalid-raw.json" \
GOVERNOR_STUB_SECOND="$plan_raw" \
mana_story_start_scope_v2_plan_governed stub deterministic "$story" "$tmp/discovery.json" "$tmp/context.json" "$tmp/triage.json" "$tmp/pipeline-corrected-plan.json" "$tmp/pipeline-corrected-report.json"
[ "$(wc -l < "$tmp/pipeline-correction-count" | tr -d ' ')" = 2 ] || fail 'governed pipeline did not stop after one corrective call'
cmp -s "$tmp/plan.json" "$tmp/pipeline-corrected-plan.json" || fail 'governed pipeline did not publish the corrected normalized plan'
jq -e '.status=="passed" and .validationPass==2 and .correction=={"attemptCount":1,"outcome":"succeeded"}' "$tmp/pipeline-corrected-report.json" >/dev/null || fail 'governed pipeline correction result is invalid'

# 16. SS06 publication must still use this governed boundary; direct public
# Planner publication would bypass the one-correction fail-closed contract.
grep -Fq 'mana_story_start_scope_v2_plan_governed' "$root/scripts/lib/story-start-scope-v2.sh" || fail 'public pipeline lost the governed planner boundary'

echo 'Story Start Scope v2 Governor tests passed (zero provider/network calls; fake correction only)'
