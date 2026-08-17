#!/usr/bin/env bash
# SS03 zero-token acceptance for the internal Scope Triage v2 phase.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
story="$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json"
discovery_raw="$root/tests/fixtures/story-start-scope-v2/discovery/provider-output.json"
triage_raw="$root/tests/fixtures/story-start-scope-v2/triage/provider-output.json"
discovery_schema="$root/contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json"
triage_schema="$root/contracts/story-start/scope-v2/schemas/scope-triage.schema.json"
normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-triage-v2.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/story-start-scope-v2.sh"

python3 "$normalizer" normalize-discovery "$discovery_schema" "$discovery_raw" "$tmp/discovery.json"
mana_story_start_scope_v2_validate_discovery "$tmp/discovery.json"
mana_story_start_scope_v2_validate_triage "$triage_raw"
python3 "$normalizer" normalize-triage "$triage_schema" "$tmp/discovery.json" "$triage_raw" "$tmp/triage-a.json"
mana_story_start_scope_v2_validate_triage "$tmp/triage-a.json"

# Prompt/skill regression: triage consumes compact artifacts and cannot plan.
prompt="$(mana_story_start_scope_v2_triage_prompt "$story" "$tmp/discovery.json")"
for boundary in \
  'Do not inspect the repository' \
  'Missing evidence must remain an evidence gap' \
  'Classify every discovery finding exactly once' \
  'This phase creates no task and no estimate.' \
  'Without an AC or mandatory' \
  'Preserve open decisions' \
  'Do not select a more robust'; do
  grep -Fq "$boundary" <<<"$prompt" || fail "missing Scope Triage prompt boundary: $boundary"
done
if grep -Eq 'sourceTopology|Synthetic compact evidence package' <<<"$prompt"; then
  fail 'triage received Discovery collection metadata instead of only the normalized story'
fi
grep -Fq 'Evidence found is not scope approved.' "$root/skills/story-start-scope-triage-v2/SKILL.md" || fail 'triage skill conflates discovery and scope'
grep -Fq 'No AC/constraint reference means no promotion.' "$root/skills/story-start-scope-triage-v2/SKILL.md" || fail 'triage skill omits promotion gate'

# 1. Every category exists; every discovery finding has exactly one disposition.
jq -e '
  ([.classifications[].category] | sort | unique) == ([
    "VERIFIED_FACT","CORE_SCOPE","REQUIRED_ENABLER","CONDITIONAL_SCOPE",
    "READINESS_PREREQUISITE","RELATED_DEFECT","RISK_ONLY","OPTIONAL_IMPROVEMENT"
  ] | sort) and
  ([.classifications[].findingRef] | length) == ([.classifications[].findingRef] | unique | length)
' "$tmp/triage-a.json" >/dev/null || fail 'classification coverage or category inventory is incomplete'
[ "$(jq '.classifications | length' "$tmp/triage-a.json")" = "$(jq '.findings | length' "$tmp/discovery.json")" ] || fail 'not every discovery finding was classified'

# Required regression topology maps to the expected semantic categories.
jq -e --slurpfile discovery "$tmp/discovery.json" '
  ($discovery[0].findings | map({key:.id,value:.summary}) | from_entries) as $summary |
  any(.classifications[]; .category=="READINESS_PREREQUISITE" and ($summary[.findingRef]|contains("Branch alignment"))) and
  any(.classifications[]; .category=="VERIFIED_FACT" and ($summary[.findingRef]|contains("Existing synthetic configuration"))) and
  any(.classifications[]; .category=="CONDITIONAL_SCOPE" and ($summary[.findingRef]|contains("Direct/SSO"))) and
  any(.classifications[]; .category=="CONDITIONAL_SCOPE" and ($summary[.findingRef]|contains("Best-effort"))) and
  any(.classifications[]; .category=="READINESS_PREREQUISITE" and ($summary[.findingRef]|contains("Pending business approval"))) and
  any(.classifications[]; .category=="CONDITIONAL_SCOPE" and ($summary[.findingRef]|contains("Null-semantics"))) and
  any(.classifications[]; .category=="RELATED_DEFECT" and ($summary[.findingRef]|contains("independent legacy defect"))) and
  any(.classifications[]; .category=="REQUIRED_ENABLER" and ($summary[.findingRef]|contains("pre-existing idempotency gap"))) and
  any(.classifications[]; .category=="OPTIONAL_IMPROVEMENT" and ($summary[.findingRef]|contains("refactoring")))
' "$tmp/triage-a.json" >/dev/null || fail 'synthetic regression topology was classified incorrectly'

# 2. Equivalent ordering produces byte-identical classifications and IDs.
jq '
  .classifications |= reverse | .decisions |= reverse | .optionGroups |= reverse |
  .scopeExpansions |= reverse | .decisions[].options |= reverse |
  .classifications[].evidenceRefs |= reverse |
  .classifications[].acceptanceCriterionRefs |= reverse |
  .classifications[].mandatoryConstraintRefs |= reverse |
  .optionGroups[].optionRefs |= reverse
' "$triage_raw" > "$tmp/reordered.json"
python3 "$normalizer" normalize-triage "$triage_schema" "$tmp/discovery.json" "$tmp/reordered.json" "$tmp/triage-b.json"
cmp -s "$tmp/triage-a.json" "$tmp/triage-b.json" || fail 'triage normalization changes for equivalent ordering'

# Host semantics reject unrelated evidence and incomplete decision grouping.
jq '(.classifications[] | select(.category=="OPTIONAL_IMPROVEMENT") | .evidenceRefs) =
  [(.classifications[] | select(.category=="VERIFIED_FACT") | .evidenceRefs[0])]' "$triage_raw" > "$tmp/ungrounded-evidence.json"
python3 "$normalizer" normalize-triage "$triage_schema" "$tmp/discovery.json" "$tmp/ungrounded-evidence.json" "$tmp/invalid.json" >/dev/null 2>&1 && fail 'classification accepted evidence unrelated to its finding'
jq '.optionGroups = .optionGroups[1:]' "$triage_raw" > "$tmp/missing-option-group.json"
python3 "$normalizer" normalize-triage "$triage_schema" "$tmp/discovery.json" "$tmp/missing-option-group.json" "$tmp/invalid.json" >/dev/null 2>&1 && fail 'decision without an option group was accepted'

# 3. CORE_SCOPE without an AC/constraint reference is schema-invalid.
jq '(.classifications[] | select(.category=="CORE_SCOPE") | .acceptanceCriterionRefs) = []' "$triage_raw" > "$tmp/core-without-reference.json"
python3 "$normalizer" normalize-triage "$triage_schema" "$tmp/discovery.json" "$tmp/core-without-reference.json" "$tmp/invalid.json" >/dev/null 2>&1 && fail 'CORE_SCOPE without AC/constraint was accepted'

# 4. REQUIRED_ENABLER without evidence is schema-invalid.
jq '(.classifications[] | select(.category=="REQUIRED_ENABLER") | .evidenceRefs) = []' "$triage_raw" > "$tmp/enabler-without-evidence.json"
python3 "$normalizer" normalize-triage "$triage_schema" "$tmp/discovery.json" "$tmp/enabler-without-evidence.json" "$tmp/invalid.json" >/dev/null 2>&1 && fail 'REQUIRED_ENABLER without evidence was accepted'

# 5-6. Open decisions stay unresolved and exclusive options stay separate.
jq -e '
  . as $triage |
  all(.decisions[]; .status=="open" and .selectedOptionId==null) and
  all(.decisions[]; . as $decision | any($triage.optionGroups[];
    .decisionRef==$decision.id and .relationship=="mutually_exclusive" and
    .selectionRule=="exactly_one" and
    (.optionRefs|sort)==([$decision.options[].id]|sort))) and
  ([.. | objects | keys[]] | index("tasks") | not) and
  ([.. | objects | keys[]] | index("effort") | not) and
  ([.. | objects | keys[]] | index("estimate") | not)
' "$tmp/triage-a.json" >/dev/null || fail 'open or exclusive alternatives were collapsed'

# 7. Independent defects stay outside scope.
jq -e 'all(.classifications[] | select(.category=="RELATED_DEFECT"); .includedInBasePlan==false and (.acceptanceCriterionRefs|length)==0)' "$tmp/triage-a.json" >/dev/null || fail 'independent defect entered scope'

# 8. A regression introduced by the story becomes separately mandatory work.
jq -e 'any(.classifications[];
  .category=="REQUIRED_ENABLER" and .mandatoryReason=="story_regression_prevention" and
  .promotionAssessment.storyImpact=="introduces_regression" and
  .promotionAssessment.preExistingStatus=="no")' "$tmp/triage-a.json" >/dev/null || fail 'story regression was not promoted to mandatory work'

# 9. A pre-existing data-integrity constraint remains a REQUIRED_ENABLER.
jq -e 'any(.classifications[];
  .category=="REQUIRED_ENABLER" and .mandatoryReason=="data_integrity_constraint" and
  .promotionAssessment.preExistingStatus=="yes" and
  (.promotionAssessment.failingMandatoryConstraintRefs|length)>0)' "$tmp/triage-a.json" >/dev/null || fail 'mandatory data-integrity constraint was not promoted'

# 10. Model uncertainty remains an evidence gap with owner review.
jq -e --slurpfile discovery "$tmp/discovery.json" '
  ($discovery[0].findings | map({key:.id,value:.findingKind}) | from_entries) as $kind |
  any(.classifications[]; $kind[.findingRef]=="evidence_gap" and .category=="RISK_ONLY" and .suggestedOwner!=null) and
  .validationStatus.semanticValidation=="needs_owner_review" and
  .validationStatus.ownerReview.state=="required" and
  (.validationStatus.violationCodes|index("EVIDENCE_GAP_REQUIRES_OWNER_REVIEW")!=null)
' "$tmp/triage-a.json" >/dev/null || fail 'uncertainty became fabricated certainty'
jq '(.classifications[] | select(.category=="RISK_ONLY") | .category) = "VERIFIED_FACT"' "$triage_raw" > "$tmp/fabricated-certainty.json"
python3 "$normalizer" normalize-triage "$triage_schema" "$tmp/discovery.json" "$tmp/fabricated-certainty.json" "$tmp/invalid.json" >/dev/null 2>&1 && fail 'evidence gap accepted as fabricated certainty'

jq '.storyId = "story-other"' "$story" > "$tmp/wrong-story.json"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND=/usr/bin/false \
mana_story_start_scope_v2_triage stub deterministic "$tmp/wrong-story.json" "$tmp/discovery.json" "$tmp/wrong-story-output.json" >/dev/null 2>&1 && fail 'triage accepted a normalized story for another artifact'

# Existing provider dispatch, schema path, normalization, and no fallback.
stub="$tmp/triage-provider-stub"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$*" > "$TRIAGE_STUB_ARGS"' 'cat "$TRIAGE_STUB_OUTPUT"' > "$stub"
chmod +x "$stub"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
TRIAGE_STUB_OUTPUT="$triage_raw" \
TRIAGE_STUB_ARGS="$tmp/provider-args" \
mana_story_start_scope_v2_triage stub deterministic "$story" "$tmp/discovery.json" "$tmp/triaged.json"
cmp -s "$tmp/triage-a.json" "$tmp/triaged.json" || fail 'internal phase did not publish normalized triage'
grep -Fq 'COMPACT_DISCOVERY_V2' "$tmp/provider-args" || fail 'triage did not receive compact discovery'
mana_provider_synthesis_args codex "$tmp" deterministic host-disposable-non-git "$triage_schema"
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" > "$tmp/codex-args"
grep -Fq -- '--output-schema' "$tmp/codex-args" || fail 'triage cannot use provider schema dispatch'
grep -Fq -- "$triage_schema" "$tmp/codex-args" || fail 'triage did not bind the host-owned schema'

printf '%s\n' 'free-form scope answer' > "$tmp/free-form.txt"
MANA_USER_LEARNING_ALLOW_STUB=true \
MANA_USER_LEARNING_STUB_COMMAND="$stub" \
TRIAGE_STUB_OUTPUT="$tmp/free-form.txt" \
TRIAGE_STUB_ARGS="$tmp/free-form-args" \
mana_story_start_scope_v2_triage stub deterministic "$story" "$tmp/discovery.json" "$tmp/free-form-published.json" >/dev/null 2>&1 && fail 'free-form fallback was accepted'
[ ! -e "$tmp/free-form-published.json" ] || fail 'free-form fallback was published'

# SS06 may call this phase publicly, but it still consumes only normalized
# story plus compact Discovery and cannot reread repository context.

echo 'Story Start Scope v2 Triage tests passed (zero provider/network calls)'
