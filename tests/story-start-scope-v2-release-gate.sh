#!/usr/bin/env bash
# SS07 deterministic regression matrix, original-topology gate, and budgets.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
package="$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json"
discovery_raw="$root/tests/fixtures/story-start-scope-v2/discovery/provider-output.json"
triage_raw="$root/tests/fixtures/story-start-scope-v2/triage/provider-output.json"
plan_raw="$root/tests/fixtures/story-start-scope-v2/planner/provider-output.json"
schema_root="$root/contracts/story-start/scope-v2/schemas"
normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
governor="$root/scripts/lib/story-start-scope-v2-govern.py"
renderer="$root/scripts/lib/story-start-scope-v2-render.py"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-release-gate-v2.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/story-start-scope-v2.sh"

python3 "$normalizer" normalize-discovery "$schema_root/discovery-inventory.schema.json" "$discovery_raw" "$tmp/discovery.json"
python3 "$normalizer" normalize-triage "$schema_root/scope-triage.schema.json" "$tmp/discovery.json" "$triage_raw" "$tmp/triage.json"
python3 "$normalizer" build-planning-context "$tmp/discovery.json" "$tmp/triage.json" "$tmp/context.json"
python3 "$normalizer" normalize-plan "$schema_root/implementation-plan.schema.json" "$tmp/context.json" "$tmp/triage.json" "$plan_raw" "$tmp/plan.json"
python3 "$governor" validate "$tmp/discovery.json" "$tmp/triage.json" "$tmp/plan.json" "$tmp/governance.json"

# Run the captured SS00 topology through the same public SS06 boundary.
stub="$tmp/provider-stub"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "%s\n" call >> "$SS07_STUB_COUNT"' \
  'last=""; for argument in "$@"; do last="$argument"; done' \
  'case "$last" in' \
  '  *COMPACT_DISCOVERY_PACKAGE*) cat "$SS07_DISCOVERY_OUTPUT" ;;' \
  '  *COMPACT_DISCOVERY_V2*) cat "$SS07_TRIAGE_OUTPUT" ;;' \
  '  *INVALID_IMPLEMENTATION_PLAN_V2*) cat "$SS07_CORRECTION_OUTPUT" ;;' \
  '  *SCOPE_TRIAGE_V2*) cat "$SS07_PLAN_OUTPUT" ;;' \
  '  *) exit 7 ;;' \
  'esac' > "$stub"
chmod +x "$stub"
workspace="$tmp/workspace"
mkdir -p "$workspace/evidence" "$workspace/planning" "$workspace/validation"
: > "$tmp/success-count"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
SS07_STUB_COUNT="$tmp/success-count" \
SS07_DISCOVERY_OUTPUT="$discovery_raw" \
SS07_TRIAGE_OUTPUT="$triage_raw" \
SS07_PLAN_OUTPUT="$plan_raw" \
SS07_CORRECTION_OUTPUT="$plan_raw" \
mana_story_start_scope_v2_run_public stub deterministic "$package" "$workspace"
[ "$(wc -l < "$tmp/success-count" | tr -d ' ')" = 3 ] || fail 'successful path did not use exactly three provider calls'

discovery="$workspace/evidence/story-start-discovery-v2.json"
triage="$workspace/planning/story-start-scope-triage-v2.json"
plan="$workspace/planning/story-start-implementation-plan-v2.json"
report="$workspace/planning/story-start-scope-v2.md"
governance="$workspace/validation/story-start-scope-governance-v2.json"

# Cases 1-12 and the original failure topology are asserted semantically.
jq -e --slurpfile discovery "$discovery" '
  ($discovery[0].findings | map({key:.id,value:.summary}) | from_entries) as $findingSummary |
  . as $triage |
  any(.classifications[]; .category=="RELATED_DEFECT" and .includedInBasePlan==false and ($findingSummary[.findingRef]|contains("independent legacy defect"))) and
  any(.classifications[]; .category=="REQUIRED_ENABLER" and .mandatoryReason=="criterion_dependency" and .promotionAssessment.preExistingStatus=="yes") and
  all(.optionGroups[]; .relationship=="mutually_exclusive" and .selectionRule=="exactly_one") and
  all(.decisions[]; if .status=="open" then .selectedOptionId==null else true end) and
  any(.classifications[]; .category=="VERIFIED_FACT" and ($findingSummary[.findingRef]|contains("Existing synthetic configuration"))) and
  any(.classifications[]; .category=="READINESS_PREREQUISITE" and ($findingSummary[.findingRef]|contains("Branch alignment"))) and
  any(.classifications[]; .category=="READINESS_PREREQUISITE" and ($findingSummary[.findingRef]|contains("Pending business approval"))) and
  any(.classifications[]; .category=="REQUIRED_ENABLER" and .mandatoryReason=="data_integrity_constraint" and (.mandatoryConstraintRefs|length)>0) and
  any(.classifications[]; .category=="OPTIONAL_IMPROVEMENT" and .includedInBasePlan==false) and
  any(.classifications[]; .category=="REQUIRED_ENABLER" and .mandatoryReason=="story_regression_prevention" and .promotionAssessment.storyImpact=="introduces_regression") and
  any(.classifications[]; .category=="RISK_ONLY" and ($findingSummary[.findingRef]|contains("Missing compatibility evidence")) and .suggestedOwner!=null) and
  .validationStatus.semanticValidation=="needs_owner_review" and
  (.validationStatus.violationCodes|index("EVIDENCE_GAP_REQUIRES_OWNER_REVIEW")!=null)
' "$triage" >/dev/null || fail 'offline cases 1-12 are not represented by triage semantics'
jq -e 'any(.openQuestions[]; .decisionNeeded==true and .suggestedOwner!=null and (.evidenceRefs|length)>0)' "$discovery" >/dev/null || fail 'case 12 lacks an evidence-backed owner question'

jq -e --slurpfile discovery "$discovery" --slurpfile triage "$triage" '
  ($triage[0].classifications | map({key:.id,value:.}) | from_entries) as $classification |
  . as $plan |
  all($plan.basePlan[].classificationRef; . as $ref | $classification[$ref].category=="CORE_SCOPE") and
  all($plan.basePlan[], $plan.requiredEnablers[].tasks[], $plan.conditionalBranches[].tasks[], $plan.approvedScopeExpansions[].tasks[];
    (.evidenceRefs|length)>0 and (.provenanceRefs|length)>0 and (.testEvidenceRefs|length)>0) and
  all($plan.branchGroups[]; . as $group | all($plan.scenarioEstimates.scenarios[];
    . as $scenario | ([$scenario.selectedBranchRefs[] as $selected |
      select($group.branchRefs|index($selected)!=null) | $selected]|length)==1)) and
  $plan.scenarioEstimates.finalCommittedEstimate==null and
  ($plan.scenarioEstimates.openMaterialDecisionRefs|length)>0 and
  all($plan.scenarioEstimates.scenarios[]; .finality=="scenario_only") and
  any($plan.readinessPrerequisites[]; .owner=="release-owner" and .engineeringEffort.minimumPersonHours==0 and .calendarImpact.status=="unknown") and
  any($plan.readinessPrerequisites[]; .owner=="Product Owner" and .engineeringEffort.minimumPersonHours==0 and .engineeringEffort.additionalPersonHours==0 and .calendarImpact.status=="unknown") and
  any($plan.relatedFindings[]; .originCategory=="RELATED_DEFECT" and .excludedFromBasePlan) and
  any($plan.relatedFindings[]; .originCategory=="OPTIONAL_IMPROVEMENT" and .excludedFromBasePlan) and
  all($plan.decisionRegister[] | select(.question|contains("missing synthetic legacy enabled flag")); .selectedOptionId==null) and
  all($plan.branchGroups[]; .relationship=="mutually_exclusive")
' "$plan" >/dev/null || fail 'SS00 topology produced an inflated or ungrounded plan'

# More direct checks avoid relying on report wording or titles for core semantics.
jq -e '
  . as $plan |
  all(.requiredEnablers[]; . as $enabler | any($plan.scenarioEstimates.requiredEnablerDeltas[]; .enablerRef==$enabler.id and .effort==$enabler.effort)) and
  all(.scenarioEstimates.scenarios[]; .engineeringTotal.minimumPersonHours < 40) and
  ([.basePlan[], .requiredEnablers[].tasks[], .conditionalBranches[].tasks[]] |
    all(.title | test("(?i)^add .*config") | not))
' "$plan" >/dev/null || fail 'mandatory deltas or existing-configuration reuse regressed'
grep -Fq 'do not sum them' "$report" || fail 'exclusive alternatives are not explicit in the human report'
grep -Fq 'No final committed estimate is available' "$report" || fail 'human report implies a false final total'
jq -e '.status=="passed" and .violations==[]' "$governance" >/dev/null || fail 'public topology did not pass the governor'

# Case 11: a pre-existing defect materially aggravated by the story remains a
# separate, evidence-backed REQUIRED_ENABLER rather than being relabeled core.
old_classification="$(jq -r '.classifications[] | select(.mandatoryReason=="criterion_dependency") | .id' "$tmp/triage.json")"
jq '(.classifications[] | select(.mandatoryReason=="criterion_dependency")) |=
  (.mandatoryReason="aggravated_defect_remediation" |
   .rationale="The story materially aggravates the pre-existing idempotency defect; remediation remains separate mandatory work." |
   .promotionAssessment.storyImpact="aggravates_pre_existing_issue")' "$tmp/triage.json" > "$tmp/aggravated-triage-raw.json"
python3 "$normalizer" normalize-triage "$schema_root/scope-triage.schema.json" "$tmp/discovery.json" "$tmp/aggravated-triage-raw.json" "$tmp/aggravated-triage.json"
new_classification="$(jq -r '.classifications[] | select(.mandatoryReason=="aggravated_defect_remediation") | .id' "$tmp/aggravated-triage.json")"
python3 "$normalizer" build-planning-context "$tmp/discovery.json" "$tmp/aggravated-triage.json" "$tmp/aggravated-context.json"
jq --arg old "$old_classification" --arg new "$new_classification" --arg triage_ref "$(jq -r .artifactId "$tmp/aggravated-triage.json")" '
  walk(if type=="string" and .==$old then $new else . end) |
  .sourceTriageArtifactRef=$triage_ref |
  (.requiredEnablers[] | select(.classificationRef==$new)) |=
    (.mandatoryReason="aggravated_defect_remediation" | .title="Remediate the story-aggravated idempotency defect")
' "$tmp/plan.json" > "$tmp/aggravated-plan-raw.json"
python3 "$normalizer" normalize-plan "$schema_root/implementation-plan.schema.json" "$tmp/aggravated-context.json" "$tmp/aggravated-triage.json" "$tmp/aggravated-plan-raw.json" "$tmp/aggravated-plan.json"
python3 "$governor" validate "$tmp/discovery.json" "$tmp/aggravated-triage.json" "$tmp/aggravated-plan.json" "$tmp/aggravated-report.json"
jq -e 'any(.classifications[]; .category=="REQUIRED_ENABLER" and .mandatoryReason=="aggravated_defect_remediation" and .promotionAssessment.preExistingStatus=="yes" and .promotionAssessment.storyImpact=="aggravates_pre_existing_issue")' "$tmp/aggravated-triage.json" >/dev/null || fail 'case 11 causality is not explicit'
jq -e '.status=="passed"' "$tmp/aggravated-report.json" >/dev/null || fail 'case 11 did not pass deterministic governance'

# Cases 13-14: one correction can succeed; a second invalid result fails closed.
jq '(.basePlan[0].title)="Add configuration channel"' "$tmp/plan.json" > "$tmp/invalid-plan.json"
: > "$tmp/correction-count"
MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" \
SS07_STUB_COUNT="$tmp/correction-count" SS07_CORRECTION_OUTPUT="$tmp/plan.json" \
mana_story_start_scope_v2_govern_with_correction stub deterministic "$tmp/discovery.json" "$tmp/triage.json" "$tmp/invalid-plan.json" "$tmp/corrected-plan.json" "$tmp/corrected-report.json"
[ "$(wc -l < "$tmp/correction-count" | tr -d ' ')" = 1 ] || fail 'valid correction was not bounded to one call'
jq -e '.status=="passed" and .correction=={"attemptCount":1,"outcome":"succeeded"}' "$tmp/corrected-report.json" >/dev/null || fail 'valid correction did not succeed'
: > "$tmp/invalid-correction-count"
if MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" \
  SS07_STUB_COUNT="$tmp/invalid-correction-count" SS07_CORRECTION_OUTPUT="$tmp/invalid-plan.json" \
  mana_story_start_scope_v2_govern_with_correction stub deterministic "$tmp/discovery.json" "$tmp/triage.json" "$tmp/invalid-plan.json" "$tmp/not-published.json" "$tmp/owner-review.json"; then
  fail 'invalid correction was accepted'
fi
[ "$(wc -l < "$tmp/invalid-correction-count" | tr -d ' ')" = 1 ] || fail 'invalid correction exceeded one call'
[ ! -e "$tmp/not-published.json" ] || fail 'invalid correction silently published a fallback'
jq -e '.status=="needs_owner_review" and .correction=={"attemptCount":1,"outcome":"failed"}' "$tmp/owner-review.json" >/dev/null || fail 'invalid correction did not fail closed'

# Case 15: legacy content remains readable but is never reinterpreted as v2.
printf '%s\n' '# Legacy implementation plan' > "$tmp/legacy.md"
python3 "$renderer" compatibility 2 "$tmp/legacy.md" > "$tmp/legacy-compatibility.json"
jq -e '.status=="legacy_readable" and .handling=="preserve_as_is" and .safeToInterpret==false' "$tmp/legacy-compatibility.json" >/dev/null || fail 'legacy compatibility behavior changed'

# Case 16: a resolved human decision adds a separate approved delta while the
# original RELATED_DEFECT classification and excluded related finding survive.
raw_story_provenance="$(jq -r '.provenance[] | select(.sourceRef=="fixtures/synthetic/story") | .id' "$discovery_raw")"
jq --arg provenance "$raw_story_provenance" '
  .evidence += [{"id":"ev_7777777777777777777777777777777777777777777777777777777777777777","kind":"human_decision","epistemicStatus":"reported","summary":"The Product Owner explicitly approved adding remediation of the independent legacy defect to this story.","capabilityState":"not_applicable","preExistingStatus":"yes","provenanceRefs":[$provenance]}] |
  .decisions += [{"id":"decision_7777777777777777777777777777777777777777777777777777777777777777","question":"Should the independent legacy defect be added to the story by explicit scope expansion?","owner":"Product Owner","status":"resolved","materiality":"non_material","options":[{"id":"option_7777777777777777777777777777777777777777777777777777777777777777","label":"Keep separate","summary":"Retain the defect as separately tracked work."},{"id":"option_8888888888888888888888888888888888888888888888888888888888888888","label":"Approve expansion","summary":"Add remediation through an explicit approved scope expansion."}],"selectedOptionId":"option_8888888888888888888888888888888888888888888888888888888888888888","evidenceRefs":["ev_7777777777777777777777777777777777777777777777777777777777777777"]}]
' "$discovery_raw" > "$tmp/expansion-discovery-raw.json"
python3 "$normalizer" normalize-discovery "$schema_root/discovery-inventory.schema.json" "$tmp/expansion-discovery-raw.json" "$tmp/expansion-discovery.json"
expansion_decision="$(jq -r '.decisions[] | select(.question|contains("explicit scope expansion")) | .id' "$tmp/expansion-discovery.json")"
approval_evidence="$(jq -r '.evidence[] | select(.summary|contains("explicitly approved adding remediation")) | .id' "$tmp/expansion-discovery.json")"
related_classification="$(jq -r '.classifications[] | select(.category=="RELATED_DEFECT") | .id' "$tmp/triage.json")"
expansion_task='task_9e13770889132f480c51308fd2c2b649ff83e5276e620d9f3cf717f616edce69'
option_refs="$(jq -c --arg decision "$expansion_decision" '.decisions[] | select(.id==$decision) | [.options[].id]' "$tmp/expansion-discovery.json")"
jq --arg source "$(jq -r .artifactId "$tmp/expansion-discovery.json")" --arg decision "$expansion_decision" --arg evidence "$approval_evidence" --arg related "$related_classification" --arg task "$expansion_task" --argjson options "$option_refs" --slurpfile discovery "$tmp/expansion-discovery.json" '
  .sourceDiscoveryArtifactRef=$source | .decisions=$discovery[0].decisions |
  .optionGroups += [{"id":"optiongroup_7777777777777777777777777777777777777777777777777777777777777777","decisionRef":$decision,"relationship":"mutually_exclusive","selectionRule":"exactly_one","optionRefs":$options}] |
  .scopeExpansions += [{"id":"expansion_7777777777777777777777777777777777777777777777777777777777777777","originalClassificationRef":$related,"decisionRef":$decision,"approvalEvidenceRefs":[$evidence],"status":"approved","resultingWorkRefs":[$task]}]
' "$tmp/triage.json" > "$tmp/expansion-triage-raw.json"
python3 "$normalizer" normalize-triage "$schema_root/scope-triage.schema.json" "$tmp/expansion-discovery.json" "$tmp/expansion-triage-raw.json" "$tmp/expansion-triage.json"
python3 "$normalizer" build-planning-context "$tmp/expansion-discovery.json" "$tmp/expansion-triage.json" "$tmp/expansion-context.json"
expansion_ref="$(jq -r '.scopeExpansions[0].id' "$tmp/expansion-triage.json")"
approval_provenance="$(jq -r --arg evidence "$approval_evidence" '.evidence[] | select(.id==$evidence) | .provenanceRefs[0]' "$tmp/expansion-discovery.json")"
jq --arg triage_ref "$(jq -r .artifactId "$tmp/expansion-triage.json")" --arg expansion "$expansion_ref" --arg related "$related_classification" --arg evidence "$approval_evidence" --arg provenance "$approval_provenance" --arg task "$expansion_task" --slurpfile triage "$tmp/expansion-triage.json" '
  .sourceTriageArtifactRef=$triage_ref | .decisionRegister=$triage[0].decisions |
  .approvedScopeExpansions += [{"scopeExpansionRef":$expansion,"originalClassificationRef":$related,"title":"Human-approved legacy defect remediation","tasks":[{"id":$task,"title":"Remediate the explicitly approved legacy defect","description":"Implement the separately approved remediation without relabeling the original related defect as core scope.","evidenceRefs":[(.relatedFindings[]|select(.classificationRef==$related)|.evidenceRefs[0])],"provenanceRefs":["provenance_07715b3deb721abb300670d8474dd8ca6f35a760aaa4475949cea53bf5c80b6c"],"sourceTargets":["fixtures/synthetic/repository-observation"],"testEvidenceRefs":[(.relatedFindings[]|select(.classificationRef==$related)|.evidenceRefs[0])]}],"effort":{"estimateKind":"approved_scope_delta","unit":"person_hours","minimumPersonHours":2,"additionalPersonHours":1,"confidence":"medium","rationale":"Explicitly approved work remains separate from original story scope."}}] |
  .scenarioEstimates.scenarios[] |= (.approvedScopeDeltas += [{"scopeExpansionRef":$expansion,"effort":{"estimateKind":"approved_scope_delta","unit":"person_hours","minimumPersonHours":2,"additionalPersonHours":1,"confidence":"medium","rationale":"Explicitly approved work remains separate from original story scope."}}] | .engineeringTotal.minimumPersonHours += 2 | .engineeringTotal.additionalPersonHours += 1) |
  .evidenceAndProvenance.evidenceRefs += [$evidence] | .evidenceAndProvenance.evidenceRefs |= unique |
  .evidenceAndProvenance.provenanceRefs += [$provenance] | .evidenceAndProvenance.provenanceRefs |= unique
' "$tmp/plan.json" > "$tmp/expansion-plan-raw.json"
python3 "$normalizer" normalize-plan "$schema_root/implementation-plan.schema.json" "$tmp/expansion-context.json" "$tmp/expansion-triage.json" "$tmp/expansion-plan-raw.json" "$tmp/expansion-plan.json"
python3 "$governor" validate "$tmp/expansion-discovery.json" "$tmp/expansion-triage.json" "$tmp/expansion-plan.json" "$tmp/expansion-report.json"
jq -e --arg related "$related_classification" --arg expansion "$expansion_ref" '
  any(.relatedFindings[]; .classificationRef==$related and .originCategory=="RELATED_DEFECT" and .excludedFromBasePlan) and
  any(.approvedScopeExpansions[]; .scopeExpansionRef==$expansion and .originalClassificationRef==$related and .effort.estimateKind=="approved_scope_delta") and
  all(.scenarioEstimates.scenarios[]; any(.approvedScopeDeltas[]; .scopeExpansionRef==$expansion)) and
  all(.basePlan[]; .classificationRef!=$related)
' "$tmp/expansion-plan.json" >/dev/null || fail 'case 16 rewrote history or hid the approved expansion'
jq -e '.status=="passed"' "$tmp/expansion-report.json" >/dev/null || fail 'case 16 did not pass deterministic governance'
jq '(.approvedScopeExpansions[0].tasks[0].id)="task_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' "$tmp/expansion-plan.json" > "$tmp/expansion-history-broken.json"
if python3 "$governor" validate "$tmp/expansion-discovery.json" "$tmp/expansion-triage.json" "$tmp/expansion-history-broken.json" "$tmp/expansion-history-report.json" >/dev/null 2>&1; then
  fail 'broken human expansion history was accepted'
fi
jq -e '.violations | map(.code) | index("SCOPE_EXPANSION_WORK_HISTORY_MISMATCH")!=null' "$tmp/expansion-history-report.json" >/dev/null || fail 'scope-expansion history mismatch has no deterministic violation'

# Performance and budget gate. Token figures are byte/4 planning estimates,
# not tokenizer or provider billing telemetry; live usage is unavailable here.
discovery_prompt_bytes="$(mana_story_start_scope_v2_discovery_prompt "$package" | wc -c | tr -d ' ')"
triage_prompt_bytes="$(mana_story_start_scope_v2_triage_prompt "$package" "$tmp/discovery.json" | wc -c | tr -d ' ')"
planner_prompt_bytes="$(mana_story_start_scope_v2_plan_prompt "$package" "$tmp/context.json" "$tmp/triage.json" | wc -c | tr -d ' ')"
correction_prompt_bytes="$(mana_story_start_scope_v2_correction_prompt "$tmp/invalid-plan.json" "$tmp/owner-review.json" | wc -c | tr -d ' ')"
[ "$(wc -c < "$package" | tr -d ' ')" -le 262144 ] || fail 'Discovery context byte budget exceeded'
[ "$(( $(wc -c < "$package") + $(wc -c < "$tmp/discovery.json") ))" -le 524288 ] || fail 'Triage input byte budget exceeded'
[ "$(( $(wc -c < "$package") + $(wc -c < "$tmp/context.json") + $(wc -c < "$tmp/triage.json") ))" -le 786432 ] || fail 'Planner input byte budget exceeded'
[ "$(wc -c < "$tmp/plan.json" | tr -d ' ')" -le 524288 ] || fail 'Governor candidate byte budget exceeded'
[ "$correction_prompt_bytes" -le 1048576 ] || fail 'bounded correction prompt exceeded one MiB'

start_ms="$(perl -MTime::HiRes=time -e 'print int(time * 1000)')"
for iteration in 1 2 3 4 5; do
  python3 "$governor" validate "$tmp/discovery.json" "$tmp/triage.json" "$tmp/plan.json" "$tmp/performance-$iteration.json"
done
end_ms="$(perl -MTime::HiRes=time -e 'print int(time * 1000)')"
governor_average_ms="$(( (end_ms - start_ms + 4) / 5 ))"
[ "$governor_average_ms" -le 5000 ] || fail 'host governor average runtime exceeded 5000 ms'

captured_bytes="$(( $(wc -c < "$discovery_raw") + $(wc -c < "$triage_raw") + $(wc -c < "$plan_raw") ))"
published_bytes=0
for artifact in "$discovery" "$triage" "$plan" "$report" "$governance" "$workspace/validation/story-start-scope-run-v2.json"; do
  artifact_bytes="$(wc -c < "$artifact" | tr -d ' ')"
  [ "$artifact_bytes" -le 1048576 ] || fail "published artifact exceeds one MiB: $artifact"
  published_bytes="$((published_bytes + artifact_bytes))"
done
[ "$published_bytes" -le 2097152 ] || fail 'published Story Start v2 bundle exceeds two MiB'
if rg --case-sensitive -n '^[[:space:]]*(while|until)[[:space:]]' "$root/scripts/lib/story-start-scope-v2.sh" >/dev/null; then
  fail 'Story Start v2 shell orchestration contains an unbounded loop'
fi

# Human acceptance and release preparation are release-gate artifacts, not
# prose that can disappear independently of the executable regressions.
checklist="$root/docs/roadmap/story-start-scope-v2/ss07-human-acceptance-checklist.md"
release_readiness="$root/docs/roadmap/story-start-scope-v2/ss07-release-readiness.md"
for phrase in \
  'base plan contain only the change requested' \
  'every required enabler genuinely unavoidable' \
  'conditional branches correspond to real unresolved' \
  'independent pre-existing defects, risks, and optional' \
  'understandable and' \
  'silently promoted' \
  'evidence that a simpler plan missed' \
  'without selecting architecture, approval, or scope implicitly'; do
  grep -Fq "$phrase" "$checklist" || fail "human acceptance checklist lost: $phrase"
done
for phrase in \
  'Release-note draft' \
  'Migration, compatibility, and schema notes' \
  'Known limitations' \
  '0.6.0' \
  'No version was changed. No tag, push, pull request, publication, or release was'; do
  grep -Fq "$phrase" "$release_readiness" || fail "release preparation lost: $phrase"
done
grep -Fq '16-case zero-token release gate' "$root/CHANGELOG.md" || fail 'Unreleased changelog entry is missing'

printf '%s\n' \
  "SS07_METRICS provider_calls_success=3 maximum_correction_calls=1" \
  "SS07_METRICS prompt_bytes discovery=$discovery_prompt_bytes triage=$triage_prompt_bytes planner=$planner_prompt_bytes correction=$correction_prompt_bytes" \
  "SS07_METRICS estimated_prompt_tokens discovery=$(( (discovery_prompt_bytes + 3) / 4 )) triage=$(( (triage_prompt_bytes + 3) / 4 )) planner=$(( (planner_prompt_bytes + 3) / 4 )) correction=$(( (correction_prompt_bytes + 3) / 4 ))" \
  "SS07_METRICS governor_average_ms=$governor_average_ms samples=5" \
  "SS07_METRICS artifact_bytes captured_provider_outputs=$captured_bytes published_bundle=$published_bytes"
echo 'Story Start Scope v2 SS07 release gate passed (16 zero-token cases; no real provider/network calls)'
