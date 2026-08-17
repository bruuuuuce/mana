#!/usr/bin/env bash
# SS04 zero-token acceptance for the internal Implementation Planner v2 phase.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
story="$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json"
discovery_raw="$root/tests/fixtures/story-start-scope-v2/discovery/provider-output.json"
triage_raw="$root/tests/fixtures/story-start-scope-v2/triage/provider-output.json"
plan_raw="$root/tests/fixtures/story-start-scope-v2/planner/provider-output.json"
discovery_schema="$root/contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json"
triage_schema="$root/contracts/story-start/scope-v2/schemas/scope-triage.schema.json"
plan_schema="$root/contracts/story-start/scope-v2/schemas/implementation-plan.schema.json"
normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-planner-v2.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/story-start-scope-v2.sh"

python3 "$normalizer" normalize-discovery "$discovery_schema" "$discovery_raw" "$tmp/discovery.json"
python3 "$normalizer" normalize-triage "$triage_schema" "$tmp/discovery.json" "$triage_raw" "$tmp/triage.json"
python3 "$normalizer" build-planning-context "$tmp/discovery.json" "$tmp/triage.json" "$tmp/context.json"
python3 "$normalizer" validate-planning-context "$tmp/context.json" "$tmp/triage.json"
mana_story_start_scope_v2_validate_plan "$plan_raw"
python3 "$normalizer" normalize-plan "$plan_schema" "$tmp/context.json" "$tmp/triage.json" "$plan_raw" "$tmp/plan-a.json"
mana_story_start_scope_v2_validate_plan "$tmp/plan-a.json"

# The prompt receives only normalized story, compact context, and triage.
prompt="$(mana_story_start_scope_v2_plan_prompt "$story" "$tmp/context.json" "$tmp/triage.json")"
for boundary in \
  'Do not inspect a repository' \
  'Create basePlan tasks only for CORE_SCOPE.' \
  'Never combine mutually exclusive branch deltas' \
  'Pending approval has zero developer effort.' \
  'Every task must cite evidenceRefs, provenanceRefs' \
  'finalCommittedEstimate must be null'; do
  grep -Fq "$boundary" <<<"$prompt" || fail "missing Planner v2 prompt boundary: $boundary"
done
grep -Fq 'COMPACT_PLANNING_CONTEXT_V2' <<<"$prompt" || fail 'planner did not receive compact planning context'
grep -Fq 'SCOPE_TRIAGE_V2' <<<"$prompt" || fail 'planner did not receive triage'
grep -Fq '"findings"' <<<"$prompt" && fail 'planner received an unclassified Discovery finding dump'
grep -Fq 'Never choose the more robust option' "$root/skills/story-start-implementation-planner-v2/SKILL.md" || fail 'planner skill permits architecture preference'
grep -Fq 'finalCommittedEstimate: null' "$root/skills/story-start-implementation-planner-v2/SKILL.md" || fail 'planner skill permits an authoritative open-decision total'

# 1. Independent bug -> related finding and no implementation task.
independent_ref="$(jq -r '.classifications[] | select(.category=="RELATED_DEFECT") | .id' "$tmp/triage.json")"
jq -e --arg ref "$independent_ref" '
  any(.relatedFindings[]; .classificationRef==$ref and .originCategory=="RELATED_DEFECT" and .excludedFromBasePlan) and
  all(.basePlan[]; .classificationRef!=$ref) and
  all(.requiredEnablers[]; .classificationRef!=$ref) and
  all(.conditionalBranches[]; .classificationRef!=$ref)
' "$tmp/plan-a.json" >/dev/null || fail 'independent defect became plan work'

# 2. AC-blocking problem -> separately estimated required enabler.
blocking_ref="$(jq -r '.classifications[] | select(.category=="REQUIRED_ENABLER" and .mandatoryReason=="criterion_dependency") | .id' "$tmp/triage.json")"
jq -e --arg ref "$blocking_ref" '
  any(.requiredEnablers[]; .classificationRef==$ref and .effort.estimateKind=="mandatory_delta" and (.tasks|length)>0) and
  all(.basePlan[]; .classificationRef!=$ref)
' "$tmp/plan-a.json" >/dev/null || fail 'AC-blocking problem was not a separate mandatory delta'

# 3. Best-effort/durable remain sibling branches and are never summed.
delivery_decision="$(jq -r '.decisionRegister[] | select(.question|contains("delivery guarantee")) | .id' "$tmp/plan-a.json")"
jq -e --arg decision "$delivery_decision" '
  [.conditionalBranches[] | select(.decisionRef==$decision)] as $branches |
  ($branches|map(.id)) as $branchIds |
  ($branches[0].groupRef) as $group |
  ($branches|length)==2 and
  $branches[0].groupRef==$branches[1].groupRef and
  any(.branchGroups[]; .id==$group and .relationship=="mutually_exclusive" and .selectionRule=="exactly_one") and
  all(.scenarioEstimates.scenarios[];
    ([.selectedBranchRefs[] | select(. as $ref | $branchIds | index($ref))] | length)==1)
' "$tmp/plan-a.json" >/dev/null || fail 'delivery alternatives were combined'

# 4. Direct/SSO uncertainty is represented as branches, never assumed base work.
identity_decision="$(jq -r '.decisionRegister[] | select(.question|contains("direct and federated")) | .id' "$tmp/plan-a.json")"
jq -e --arg decision "$identity_decision" '
  [.conditionalBranches[] | select(.decisionRef==$decision)] as $branches |
  ($branches[0].classificationRef) as $classification |
  ($branches|length)==2 and
  all(.basePlan[]; .classificationRef != $classification)
' "$tmp/plan-a.json" >/dev/null || fail 'Direct/SSO decision was assumed in base work'

# 5. Existing configuration is supporting evidence, not a create task.
config_evidence="$(jq -r '.evidence[] | select(.kind=="configuration" and .capabilityState=="already_exists") | .id' "$tmp/context.json")"
jq -e --arg evidence "$config_evidence" '
  any(.basePlan[]; (.evidenceRefs|index($evidence))!=null and ((.title+" "+.description)|test("reus";"i"))) and
  all(.basePlan[], .requiredEnablers[].tasks[], .conditionalBranches[].tasks[];
    ((.title+" "+.description)|test("(add|create).*(configuration|channel)";"i")|not))
' "$tmp/plan-a.json" >/dev/null || fail 'existing configuration was planned as new work'

# 6. Stale branch is readiness, not hidden base scope.
stale_ref="$(jq -r '.classifications[] | select(.category=="READINESS_PREREQUISITE" and .suggestedOwner=="release-owner") | .id' "$tmp/triage.json")"
jq -e --arg ref "$stale_ref" '
  any(.readinessPrerequisites[]; .classificationRef==$ref) and all(.basePlan[]; .classificationRef!=$ref)
' "$tmp/plan-a.json" >/dev/null || fail 'stale branch was hidden in base scope'

# 7. Pending approval has calendar impact and zero developer effort.
jq -e '
  any(.readinessPrerequisites[];
    .owner=="Product Owner" and
    .engineeringEffort.minimumPersonHours==0 and
    .engineeringEffort.additionalPersonHours==0 and
    .calendarImpact.status=="unknown")
' "$tmp/plan-a.json" >/dev/null || fail 'pending approval became developer effort'

# 8. Optional refactor remains an excluded improvement.
optional_ref="$(jq -r '.classifications[] | select(.category=="OPTIONAL_IMPROVEMENT") | .id' "$tmp/triage.json")"
jq -e --arg ref "$optional_ref" '
  any(.relatedFindings[]; .classificationRef==$ref and .originCategory=="OPTIONAL_IMPROVEMENT" and .excludedFromBasePlan)
' "$tmp/plan-a.json" >/dev/null || fail 'optional refactor entered scope'

# 9. Story-introduced regression prevention is mandatory and provenance-backed.
regression_ref="$(jq -r '.classifications[] | select(.category=="REQUIRED_ENABLER" and .mandatoryReason=="story_regression_prevention") | .id' "$tmp/triage.json")"
jq -e --arg ref "$regression_ref" '
  any(.requiredEnablers[]; .classificationRef==$ref and .mandatoryReason=="story_regression_prevention" and
    (.evidenceRefs|length)>0 and all(.tasks[]; (.provenanceRefs|length)>0))
' "$tmp/plan-a.json" >/dev/null || fail 'story regression prevention lost mandatory provenance'

# 10. Open material decisions forbid an authoritative final total.
jq -e '
  (.scenarioEstimates.openMaterialDecisionRefs|length)==3 and
  .scenarioEstimates.finalCommittedEstimate==null and
  all(.scenarioEstimates.scenarios[]; .finality=="scenario_only") and
  .validationStatus.semanticValidation=="needs_owner_review"
' "$tmp/plan-a.json" >/dev/null || fail 'open decisions produced a final total'

# 11. Scenario totals are exact and each exclusive group contributes once.
jq -e '
  . as $plan |
  all(.scenarioEstimates.scenarios[];
    . as $scenario |
    ($scenario.baseEffort.minimumPersonHours + ([ $scenario.mandatoryDeltas[].effort.minimumPersonHours ]|add) +
      ([ $scenario.conditionalDeltas[].effort.minimumPersonHours ]|add) +
      ([ $scenario.approvedScopeDeltas[].effort.minimumPersonHours ]|add // 0)) == $scenario.engineeringTotal.minimumPersonHours and
    ($scenario.baseEffort.additionalPersonHours + ([ $scenario.mandatoryDeltas[].effort.additionalPersonHours ]|add) +
      ([ $scenario.conditionalDeltas[].effort.additionalPersonHours ]|add) +
      ([ $scenario.approvedScopeDeltas[].effort.additionalPersonHours ]|add // 0)) == $scenario.engineeringTotal.additionalPersonHours and
    all($plan.branchGroups[] | select(.selectionRule=="exactly_one");
      ([.branchRefs[] as $branch | $scenario.selectedBranchRefs[] | select(.==$branch)]|length)==1))
' "$tmp/plan-a.json" >/dev/null || fail 'scenario arithmetic or exclusive selection is invalid'

# 12. Every task has evidence, provenance, source targets, and test evidence.
jq -e '
  [ .basePlan[], .requiredEnablers[].tasks[], .conditionalBranches[].tasks[], .approvedScopeExpansions[].tasks[] ] |
  length>0 and all(.[];
    (.evidenceRefs|length)>0 and (.provenanceRefs|length)>0 and
    (.sourceTargets|length)>0 and (.testEvidenceRefs|length)>0)
' "$tmp/plan-a.json" >/dev/null || fail 'a task lacks provenance'

# Equivalent provider ordering produces a byte-identical normalized plan.
jq '
  .readinessPrerequisites|=reverse | .basePlan|=reverse |
  .requiredEnablers|=reverse | .requiredEnablers[].tasks|=reverse |
  .conditionalBranches|=reverse | .conditionalBranches[].tasks|=reverse |
  .branchGroups|=reverse | .branchGroups[].branchRefs|=reverse |
  .scenarioEstimates.requiredEnablerDeltas|=reverse |
  .scenarioEstimates.openMaterialDecisionRefs|=reverse |
  .scenarioEstimates.scenarios|=reverse |
  .scenarioEstimates.scenarios[].selectedBranchRefs|=reverse |
  .scenarioEstimates.scenarios[].mandatoryDeltas|=reverse |
  .scenarioEstimates.scenarios[].conditionalDeltas|=reverse |
  .scenarioEstimates.scenarios[].calendarImpacts|=reverse |
  .decisionRegister|=reverse | .decisionRegister[].options|=reverse |
  .relatedFindings|=reverse | .evidenceAndProvenance.evidenceRefs|=reverse |
  .evidenceAndProvenance.provenanceRefs|=reverse
' "$plan_raw" > "$tmp/reordered.json"
python3 "$normalizer" normalize-plan "$plan_schema" "$tmp/context.json" "$tmp/triage.json" "$tmp/reordered.json" "$tmp/plan-b.json"
cmp -s "$tmp/plan-a.json" "$tmp/plan-b.json" || fail 'plan normalization changes for equivalent ordering'

# Host-side failures: category smuggling, approval effort, exclusivity, totals, provenance, and context integrity.
jq --arg ref "$independent_ref" '.basePlan[0].classificationRef=$ref' "$plan_raw" > "$tmp/defect-in-base.json"
python3 "$normalizer" normalize-plan "$plan_schema" "$tmp/context.json" "$tmp/triage.json" "$tmp/defect-in-base.json" "$tmp/invalid.json" >/dev/null 2>&1 && fail 'related defect was accepted in base plan'
jq '(.readinessPrerequisites[] | select(.owner=="Product Owner") | .engineeringEffort.minimumPersonHours)=1' "$plan_raw" > "$tmp/approval-effort.json"
python3 "$normalizer" normalize-plan "$plan_schema" "$tmp/context.json" "$tmp/triage.json" "$tmp/approval-effort.json" "$tmp/invalid.json" >/dev/null 2>&1 && fail 'pending approval developer effort was accepted'
jq '.scenarioEstimates.scenarios[0].engineeringTotal.minimumPersonHours += 1' "$plan_raw" > "$tmp/bad-total.json"
python3 "$normalizer" normalize-plan "$plan_schema" "$tmp/context.json" "$tmp/triage.json" "$tmp/bad-total.json" "$tmp/invalid.json" >/dev/null 2>&1 && fail 'incorrect scenario total was accepted'
jq '
  .scenarioEstimates.scenarios[0].selectedBranchRefs += ["branch_4444444444444444444444444444444444444444444444444444444444444444"] |
  .scenarioEstimates.scenarios[0].conditionalDeltas += [{"branchRef":"branch_4444444444444444444444444444444444444444444444444444444444444444","effort":{"estimateKind":"conditional_delta","unit":"person_hours","minimumPersonHours":5,"additionalPersonHours":2,"confidence":"low","rationale":"Durable recovery adds five to seven person-hours."}}] |
  .scenarioEstimates.scenarios[0].engineeringTotal.minimumPersonHours += 5 |
  .scenarioEstimates.scenarios[0].engineeringTotal.additionalPersonHours += 2
' "$plan_raw" > "$tmp/summed-exclusive-siblings.json"
python3 "$normalizer" normalize-plan "$plan_schema" "$tmp/context.json" "$tmp/triage.json" "$tmp/summed-exclusive-siblings.json" "$tmp/invalid.json" >/dev/null 2>&1 && fail 'scenario summed mutually exclusive siblings'
jq '.basePlan[0].provenanceRefs=[]' "$plan_raw" > "$tmp/no-provenance.json"
mana_story_start_scope_v2_validate_plan "$tmp/no-provenance.json" >/dev/null 2>&1 && fail 'task without provenance was schema-valid'
jq '.scenarioEstimates.finalCommittedEstimate={"estimateKind":"final_committed_total","unit":"person_hours","minimumPersonHours":12,"additionalPersonHours":8,"confidence":"medium","rationale":"Invalid while decisions are open."}' "$plan_raw" > "$tmp/open-final.json"
mana_story_start_scope_v2_validate_plan "$tmp/open-final.json" >/dev/null 2>&1 && fail 'open decisions accepted a final total'
jq '.findings=[] | .contextId="planningcontext_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' "$tmp/context.json" > "$tmp/raw-findings-context.json"
python3 "$normalizer" validate-planning-context "$tmp/raw-findings-context.json" "$tmp/triage.json" >/dev/null 2>&1 && fail 'planning context accepted raw findings'

# Existing provider dispatch, schema transport, host normalization, and no fallback.
stub="$tmp/planner-provider-stub"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$*" > "$PLANNER_STUB_ARGS"' 'cat "$PLANNER_STUB_OUTPUT"' > "$stub"
chmod +x "$stub"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
PLANNER_STUB_OUTPUT="$plan_raw" \
PLANNER_STUB_ARGS="$tmp/provider-args" \
mana_story_start_scope_v2_plan stub deterministic "$story" "$tmp/context.json" "$tmp/triage.json" "$tmp/planned.json"
cmp -s "$tmp/plan-a.json" "$tmp/planned.json" || fail 'internal phase did not publish normalized plan'
grep -Fq 'COMPACT_PLANNING_CONTEXT_V2' "$tmp/provider-args" || fail 'provider did not receive compact planning context'
grep -Fq 'SCOPE_TRIAGE_V2' "$tmp/provider-args" || fail 'provider did not receive triage'
mana_provider_synthesis_args codex "$tmp" deterministic host-disposable-non-git "$plan_schema"
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" > "$tmp/codex-args"
grep -Fq -- '--output-schema' "$tmp/codex-args" || fail 'planner cannot use provider schema dispatch'
grep -Fq -- "$plan_schema" "$tmp/codex-args" || fail 'planner did not bind the host-owned schema'

printf '%s\n' 'free-form implementation superset' > "$tmp/free-form.txt"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
PLANNER_STUB_OUTPUT="$tmp/free-form.txt" \
PLANNER_STUB_ARGS="$tmp/free-form-args" \
mana_story_start_scope_v2_plan stub deterministic "$story" "$tmp/context.json" "$tmp/triage.json" "$tmp/free-form-published.json" >/dev/null 2>&1 && fail 'free-form fallback was accepted'
[ ! -e "$tmp/free-form-published.json" ] || fail 'free-form fallback was published'

# SS04 remains internal/non-default and does not begin SS05.
if rg -q 'story-start-implementation-planner-v2|mana_story_start_scope_v2_plan' "$root/scripts/run-profile.sh" "$root/scripts/cast.sh" "$root/profiles/story-start.yaml"; then
  fail 'SS04 was wired into a public Story Start path'
fi
if rg -q 'mana_story_start_scope_v2_govern|story-start-scope-governor-v2' "$root/scripts/lib/story-start-scope-v2.sh" "$root/skills/story-start-implementation-planner-v2"; then
  fail 'SS05 Scope Governor was started during SS04'
fi

echo 'Story Start Scope v2 Planner tests passed (zero provider/network calls)'
