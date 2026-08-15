#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-learning-synthesis.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
hex() { printf '%064d' "$1"; }

project="$tmp/project"; state="$tmp/state"; signals="$state/user-learning/signals"
mkdir -p "$project/.mana/user-context" "$signals"
printf '%s\n' 'M3 must not change this mirror' > "$project/.mana/user-context/preferences.md"
context="$tmp/context"; mkdir -p "$context"; printf '%s\n' 'M3 must not change this source' > "$context/preferences.md"
stub="$tmp/synthesis-stub"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$M3_STUB_RESPONSE"' 'if [ -n "${M3_STUB_PROMPT:-}" ]; then printf "%s" "$*" > "$M3_STUB_PROMPT"; fi' 'printf "%s" "$*" | wc -c | tr -d " " >> "$M3_STUB_BYTES"' 'printf x >> "$M3_STUB_CALLS"' > "$stub"
chmod +x "$stub"

write_signal() {
  local n="$1" p="$2" subject="$3" choice="$4" id="user-choice-$(hex "$1")" project_id="project-$(hex "$2")"
  jq -cn --arg id "$id" --arg project "$project_id" --arg subject "$subject" --arg choice "$choice" --arg hash "$(hex 99)" --argjson ordinal "$n" \
    '{schemaVersion:"2",signalId:$id,sourceProject:{projectId:$project,repositoryRoot:"/fixture"},sourceDecision:{reference:(".mana/features/F/decisions/developer-choice-log.md#choice-"+($ordinal|tostring)),logPath:".mana/features/F/decisions/developer-choice-log.md",line:$ordinal,choiceOrdinal:$ordinal,status:"confirmed",subject:$subject,confirmedChoice:$choice,confirmedBy:"developer"},provenance:{sourceType:"developer-choice-log",sourceArtifact:{path:".mana/features/F/decisions/developer-choice-log.md",sha256:$hash},evidence:["loss affects correctness"]},capture:{processor:"deterministic-developer-choice-log-v1",modelCalls:0,capturedAt:"2026-08-08T00:00:00Z"}}' > "$signals/$id.json"
}

# Two structurally different M2 clusters share only a deterministic lexical
# preselection token. M3, not M2, makes the semantic reconciliation proposal.
write_signal 1 1 'Async failures handling' 'durable retry'
write_signal 2 2 'Async failures handling' 'durable retry'
write_signal 3 3 'Failure strategy for async work' 'persistent recoverable execution'
aggregate() { MANA_USER_STATE_HOME="$state" "$root/scripts/mana-user-learning.sh" --project-root "$project" aggregate --json; }
aggregate >/dev/null
ids_text="$(jq -r .clusterId "$state/user-learning/clusters"/*.json | LC_ALL=C sort)"
ids=(); while IFS= read -r id; do [ -n "$id" ] && ids+=("$id"); done <<EOF
$ids_text
EOF
[ "${#ids[@]}" = 2 ] || fail 'fixture did not produce two M2 clusters'
signal_ids="$(jq -sc '[.[].supportingSignalIds[]]|sort' "$state/user-learning/clusters"/*.json)"
candidate_response="$(jq -cn --arg a "${ids[0]}" --arg b "${ids[1]}" --argjson signals "$signal_ids" '{result:"CANDIDATE",guidance:"Prefer durable, observable recovery mechanisms when asynchronous loss affects correctness.",scope:"reliability",rationale:"The supplied decisions independently choose durable recovery for asynchronous failures.",limitations:["Bounded evidence is limited to the supplied projects."],relatedClusterIds:[$a,$b],supportingSignalIds:$signals}')"

before_project="$(find "$project" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"; before_context="$(find "$context" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"
run() { MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" MANA_USER_LEARNING_MAX_CLUSTERS_PER_UNIT=2 MANA_USER_LEARNING_MAX_SIGNALS_PER_CLUSTER=2 M3_STUB_RESPONSE="$1" M3_STUB_CALLS="$tmp/calls" M3_STUB_BYTES="$tmp/bytes" M3_STUB_PROMPT="$tmp/last-prompt" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --json; }

first="$(run "$candidate_response")"
printf '%s' "$first" | jq -e '.modelTier=="T1" and .modelCalls==1 and .candidateResults==1 and .noCandidateResults==0 and .budgets.maxEvidenceClusters==2' >/dev/null || fail 'eligible unit did not make exactly one T1 call'
[ "$(wc -c < "$tmp/calls" | tr -d ' ')" = 1 ] || fail 'unexpected model invocation count'
[ "$(cat "$tmp/bytes")" -le 14400 ] || fail 'bounded package exceeded configured input budget'
grep -Fq 'fully explained by external requirements' "$tmp/last-prompt" || fail 'M3 prompt lost the external-constraint NO_CANDIDATE contract'
grep -Fq 'Each confirmedChoice is an explicit developer choice' "$tmp/last-prompt" || fail 'M3 prompt lost explicit-choice interpretation'
grep -Fq 'Different implementations may support one higher-level principle' "$tmp/last-prompt" || fail 'M3 prompt lost semantic reconciliation guidance'
grep -Fq 'flat transport object' "$tmp/last-prompt" || fail 'M3 prompt lost the flat transport contract'
grep -Fq 'CANDIDATE: reason "", scope "unspecified" unless explicit. NO_CANDIDATE: guidance/scope/rationale ""' "$tmp/last-prompt" || fail 'M3 prompt made NO_CANDIDATE scope ambiguous'
candidate_file="$(find "$state/user-learning/candidates" -type f -name '*.json' -print -quit)"
jq -e '.kind=="user-context-candidate" and .lifecycleState=="proposed" and .synthesis.modelTier=="T1" and (.sourceClusterIds|length)==2' "$candidate_file" >/dev/null || fail 'candidate/provenance missing'
[ "$before_project" = "$(find "$project" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)" ] || fail 'M3 mutated project/User Context mirror'
[ "$before_context" = "$(find "$context" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)" ] || fail 'M3 mutated external User Context source'

second="$(run "$candidate_response")"
printf '%s' "$second" | jq -e '.modelCalls==0 and .unitsAlreadySynthesized==1 and .modelCallsAvoided>=1' >/dev/null || fail 'unchanged package was not cached'
[ "$(wc -c < "$tmp/calls" | tr -d ' ')" = 1 ] || fail 'cached synthesis invoked provider'

# New bounded source evidence changes the input fingerprint, reruns T1, and
# retains the semantic-family candidate identity (same source cluster set).
stable_candidate_id="$(jq -r .candidateId "$candidate_file")"
write_signal 4 4 'Failure strategy for async work' 'persistent recoverable execution'
aggregate >/dev/null
changed="$(run "$candidate_response")"
printf '%s' "$changed" | jq -e '.modelCalls==1 and .candidateResults==1' >/dev/null || fail 'changed evidence did not resynthesize'
[ "$(jq -r .candidateId "$candidate_file")" = "$stable_candidate_id" ] || fail 'telemetry/evidence membership changed candidate family identity'

variant="$(MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_T1_MODEL=telemetry-variant MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" M3_STUB_RESPONSE="$candidate_response" M3_STUB_CALLS="$tmp/calls" M3_STUB_BYTES="$tmp/bytes" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --force --json)"
printf '%s' "$variant" | jq -e '.model=="telemetry-variant" and .modelCalls==1' >/dev/null || fail 'provider telemetry variant did not run'
[ "$(jq -r .candidateId "$candidate_file")" = "$stable_candidate_id" ] || fail 'provider telemetry changed candidate identity'

dry="$(MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" M3_STUB_RESPONSE="$candidate_response" M3_STUB_CALLS="$tmp/calls" M3_STUB_BYTES="$tmp/bytes" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --force --dry-run --json)"
printf '%s' "$dry" | jq -e '.dryRun==true and .modelCalls==0 and .unitsReadyToCall==1' >/dev/null || fail 'dry-run did not report a bounded would-call unit'
[ "$(wc -c < "$tmp/calls" | tr -d ' ')" = 3 ] || fail 'dry-run invoked provider'

# Invalid/hallucinated provenance is a synthesis failure, never a candidate.
bad="$(jq -cn --arg a "${ids[0]}" --arg b "${ids[1]}" '{result:"CANDIDATE",guidance:"invented",scope:"unspecified",rationale:"invented",limitations:[],relatedClusterIds:[$a,$b],supportingSignalIds:["user-choice-ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff","user-choice-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"]}')"
bad_result="$(MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_DIAGNOSTICS_DIR="$tmp/diagnostics" MANA_USER_LEARNING_DIAGNOSTIC_SCENARIO=invalid-provenance MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" M3_STUB_RESPONSE="$bad" M3_STUB_CALLS="$tmp/calls" M3_STUB_BYTES="$tmp/bytes" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --force --json)"
printf '%s' "$bad_result" | jq -e '.modelCalls==1 and .providerFailures==1 and .candidateResults==0' >/dev/null || fail 'hallucinated provenance was accepted'
jq -e '.scenario=="invalid-provenance" and .deterministicEligibility=="INVALID_STRUCTURED_OUTPUT" and .providerInvocationCount==1 and .structuredOutputValidation.error=="fabricated_or_unexposed_signal_id" and (.rawBoundedModelResult|length)>0 and .acceptedResult==null and (.semanticInputPackage.evidenceFamilies|length)>0' "$tmp/diagnostics"/*.json >/dev/null || fail 'invalid output diagnostic did not retain exact bounded validation evidence'

# Codex gets a flat native structured-output transport, but Mana still checks
# result-conditional semantics before canonical domain validation.
codex_stub="$tmp/codex"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\\n" "$*" > "$M3_CODEX_ARGS"' 'if [ -n "${M3_CODEX_SCHEMA_CAPTURE:-}" ]; then previous=""; for arg in "$@"; do if [ "$previous" = --output-schema ]; then cp "$arg" "$M3_CODEX_SCHEMA_CAPTURE"; break; fi; previous="$arg"; done; fi' 'printf "%s" "$M3_CODEX_RESPONSE"' > "$codex_stub"
chmod +x "$codex_stub"
codex_schema="$root/docs/standards/user-learning-m3-codex-transport.schema.json"
jq -e '.type=="object" and .additionalProperties==false and (.required|sort)==["guidance","limitations","rationale","reason","relatedClusterIds","result","scope","supportingSignalIds"] and (.properties.limitations.type=="array" and .properties.limitations.maxItems==6) and (.properties.relatedClusterIds.minItems==1 and .properties.relatedClusterIds.maxItems==8) and (.properties.supportingSignalIds.minItems==2 and .properties.supportingSignalIds.maxItems==32) and (.properties.result.enum==["CANDIDATE","NO_CANDIDATE"]) and ([.properties[]|.type]|all(. == "string" or . == "array"))' "$codex_schema" >/dev/null || fail 'Codex M3 transport schema is not flat, bounded, and stable-typed'
flat_candidate="$(jq -c '. + {reason:""}' <<<"$candidate_response")"
codex_result="$(PATH="$tmp:$PATH" MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_T1_PROVIDER=codex MANA_USER_LEARNING_T1_MODEL=fixture MANA_USER_LEARNING_CODEX_REASONING_EFFORT=high M3_CODEX_RESPONSE="$flat_candidate" M3_CODEX_ARGS="$tmp/codex-args" M3_CODEX_SCHEMA_CAPTURE="$tmp/codex-bound-schema.json" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --force --json)"
printf '%s' "$codex_result" | jq -e '.modelCalls==1 and .candidateResults==1 and .invalidProviderResponses==0' >/dev/null || fail 'flat Codex candidate transport was not accepted'
grep -Fq -- '--output-schema ' "$tmp/codex-args" || fail 'Codex M3 synthesis did not configure native output schema'
jq -e --argjson clusters "$(jq -sc '[.[].clusterId]|sort' "$state/user-learning/clusters"/*.json)" --argjson signals "$(jq -sc '[.[].supportingSignalIds[]]|unique|sort' "$state/user-learning/clusters"/*.json)" '.properties.relatedClusterIds.items.enum==$clusters and .properties.supportingSignalIds.items.enum==$signals' "$tmp/codex-bound-schema.json" >/dev/null || fail 'Codex native schema was not bound to exact exposed provenance'
grep -Fq -- '--ignore-user-config -c model_reasoning_effort="high" --disable multi_agent' "$tmp/codex-args" || fail 'Codex M3 reasoning effort override was lost behind ignore-user-config'
flat_candidate_bad="$(jq -c '.reason="must be empty for CANDIDATE"' <<<"$flat_candidate")"
codex_bad_candidate="$(PATH="$tmp:$PATH" MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_T1_PROVIDER=codex MANA_USER_LEARNING_T1_MODEL=fixture M3_CODEX_RESPONSE="$flat_candidate_bad" M3_CODEX_ARGS="$tmp/codex-args" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --force --json)"
printf '%s' "$codex_bad_candidate" | jq -e '.modelCalls==1 and .candidateResults==0 and .invalidProviderResponses==1' >/dev/null || fail 'CANDIDATE conditional host validation was weakened'

# Provenance arrays are unordered sets. The host validates them without
# deduplication, then canonicalizes only those arrays before use/persistence.
unsorted_flat="$(jq -c '.relatedClusterIds |= reverse | .supportingSignalIds |= reverse | .limitations=["Second limitation.","First limitation."]' <<<"$flat_candidate")"
unsorted_result="$(PATH="$tmp:$PATH" MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_DIAGNOSTICS_DIR="$tmp/unsorted-diagnostics" MANA_USER_LEARNING_DIAGNOSTIC_SCENARIO=unsorted-valid-provenance MANA_USER_LEARNING_T1_PROVIDER=codex MANA_USER_LEARNING_T1_MODEL=fixture M3_CODEX_RESPONSE="$unsorted_flat" M3_CODEX_ARGS="$tmp/codex-args" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --force --json)"
printf '%s' "$unsorted_result" | jq -e '.modelCalls==1 and .candidateResults==1 and .invalidProviderResponses==0' >/dev/null || fail 'unsorted_valid_provenance_is_accepted'
unsorted_diagnostic="$(jq -r 'select(.acceptedResult != null) | input_filename' "$tmp/unsorted-diagnostics"/*.json | LC_ALL=C sort | head -n 1)"
[ -n "$unsorted_diagnostic" ] || fail 'accepted unsorted diagnostic was not recorded'
jq -e '(.acceptedResult.relatedClusterIds == (.acceptedResult.relatedClusterIds|sort)) and (.acceptedResult.supportingSignalIds == (.acceptedResult.supportingSignalIds|sort))' "$unsorted_diagnostic" >/dev/null || fail 'unsorted_valid_provenance_is_canonicalized'
jq -e '.acceptedResult.limitations==["Second limitation.","First limitation."]' "$unsorted_diagnostic" >/dev/null || fail 'non_provenance_arrays_are_not_reordered'
jq -e '.supportingSignalIds == (.supportingSignalIds|sort) and .synthesis.limitations==["Second limitation.","First limitation."]' "$candidate_file" >/dev/null || fail 'canonical provenance was not persisted without reordering limitations'

sorted_flat="$(jq -c '.relatedClusterIds |= sort | .supportingSignalIds |= sort' <<<"$unsorted_flat")"
stable_result="$(PATH="$tmp:$PATH" MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_DIAGNOSTICS_DIR="$tmp/stable-diagnostics" MANA_USER_LEARNING_DIAGNOSTIC_SCENARIO=stable-canonical-provenance MANA_USER_LEARNING_T1_PROVIDER=codex MANA_USER_LEARNING_T1_MODEL=fixture M3_CODEX_RESPONSE="$sorted_flat" M3_CODEX_ARGS="$tmp/codex-args" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --force --json)"
printf '%s' "$stable_result" | jq -e '.modelCalls==1 and .candidateResults==1 and .invalidProviderResponses==0' >/dev/null || fail 'sorted provenance control response was rejected'
stable_diagnostic="$(jq -r 'select(.acceptedResult != null) | input_filename' "$tmp/stable-diagnostics"/*.json | LC_ALL=C sort | head -n 1)"
[ -n "$stable_diagnostic" ] || fail 'accepted stable diagnostic was not recorded'
[ "$(jq -cS .acceptedResult "$unsorted_diagnostic")" = "$(jq -cS .acceptedResult "$stable_diagnostic")" ] || fail 'canonical_provenance_output_is_stable'

duplicate_flat="$(jq -c '.supportingSignalIds=[.supportingSignalIds[0],.supportingSignalIds[0]]' <<<"$flat_candidate")"
duplicate_result="$(PATH="$tmp:$PATH" MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_DIAGNOSTICS_DIR="$tmp/duplicate-diagnostics" MANA_USER_LEARNING_DIAGNOSTIC_SCENARIO=duplicate-provenance MANA_USER_LEARNING_T1_PROVIDER=codex MANA_USER_LEARNING_T1_MODEL=fixture M3_CODEX_RESPONSE="$duplicate_flat" M3_CODEX_ARGS="$tmp/codex-args" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --force --json)"
printf '%s' "$duplicate_result" | jq -e '.modelCalls==1 and .candidateResults==0 and .invalidProviderResponses==1' >/dev/null || fail 'duplicate_provenance_is_rejected'
jq -e '.structuredOutputValidation.error=="duplicate_signal_id" and .acceptedResult==null' "$tmp/duplicate-diagnostics"/*.json >/dev/null || fail 'duplicate provenance was silently deduplicated'

unknown_flat="$(jq -c '.supportingSignalIds[0]="user-choice-ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"' <<<"$flat_candidate")"
unknown_result="$(PATH="$tmp:$PATH" MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_DIAGNOSTICS_DIR="$tmp/unknown-diagnostics" MANA_USER_LEARNING_DIAGNOSTIC_SCENARIO=unknown-provenance MANA_USER_LEARNING_T1_PROVIDER=codex MANA_USER_LEARNING_T1_MODEL=fixture M3_CODEX_RESPONSE="$unknown_flat" M3_CODEX_ARGS="$tmp/codex-args" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --force --json)"
printf '%s' "$unknown_result" | jq -e '.modelCalls==1 and .candidateResults==0 and .invalidProviderResponses==1' >/dev/null || fail 'unknown_provenance_is_rejected'
jq -e '.structuredOutputValidation.error=="fabricated_or_unexposed_signal_id" and .acceptedResult==null' "$tmp/unknown-diagnostics"/*.json >/dev/null || fail 'fabricated provenance became possible'

non_string_flat="$(jq -c '.supportingSignalIds[0]=123' <<<"$flat_candidate")"
non_string_result="$(PATH="$tmp:$PATH" MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_DIAGNOSTICS_DIR="$tmp/non-string-diagnostics" MANA_USER_LEARNING_DIAGNOSTIC_SCENARIO=non-string-provenance MANA_USER_LEARNING_T1_PROVIDER=codex MANA_USER_LEARNING_T1_MODEL=fixture M3_CODEX_RESPONSE="$non_string_flat" M3_CODEX_ARGS="$tmp/codex-args" "$root/scripts/mana-user-learning.sh" --project-root "$project" synthesize --force --json)"
printf '%s' "$non_string_result" | jq -e '.modelCalls==1 and .candidateResults==0 and .invalidProviderResponses==1' >/dev/null || fail 'non_string_provenance_is_rejected'
jq -e '.structuredOutputValidation.error=="non_string_signal_id" and .acceptedResult==null' "$tmp/non-string-diagnostics"/*.json >/dev/null || fail 'non-string provenance did not fail element-type validation'

# Three sparse choice clusters can be a single legitimate lexical T1 family.
# Their alternative-evidence graph must not consume the entire package budget.
sparse_state="$tmp/sparse-family-state"; sparse_project="$tmp/sparse-family-project"; mkdir -p "$sparse_state/user-learning/signals" "$sparse_project"
old_signals="$signals"; signals="$sparse_state/user-learning/signals"
write_signal 51 51 'Recovering correctness critical async work' 'durable outbox'
write_signal 52 52 'Recovering correctness critical async work' 'persistent retry'
write_signal 53 53 'Recovering correctness critical async work' 'avoid fire and forget'
signals="$old_signals"
MANA_USER_STATE_HOME="$sparse_state" "$root/scripts/mana-user-learning.sh" --project-root "$sparse_project" aggregate >/dev/null
sparse_clusters="$(jq -sc '[.[].clusterId]|sort' "$sparse_state/user-learning/clusters"/*.json)"; sparse_signals="$(jq -sc '[.[].supportingSignalIds[]]|sort' "$sparse_state/user-learning/clusters"/*.json)"
sparse_response="$(jq -cn --argjson clusters "$sparse_clusters" --argjson signals "$sparse_signals" '{result:"CANDIDATE",guidance:"Prefer recoverable handling when loss affects correctness.",scope:"reliability",rationale:"Fixture.",limitations:["Fixture."],relatedClusterIds:$clusters,supportingSignalIds:$signals}')"
sparse_result="$(MANA_USER_STATE_HOME="$sparse_state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" MANA_USER_LEARNING_MAX_INPUT_BYTES=4000 M3_STUB_RESPONSE="$sparse_response" M3_STUB_CALLS="$tmp/sparse-calls" M3_STUB_BYTES="$tmp/sparse-bytes" "$root/scripts/mana-user-learning.sh" --project-root "$sparse_project" synthesize --json)"
printf '%s' "$sparse_result" | jq -e '.modelCalls==1 and .unitsReadyToCall==1 and .unitsSkippedIrreduciblyOversized==0 and .candidateResults==1' >/dev/null || fail 'sparse related clusters did not reach one bounded T1 call'
[ "$(wc -c < "$tmp/sparse-calls" | tr -d ' ')" = 1 ] || fail 'sparse related clusters invoked T1 more than once'

# NO_CANDIDATE is a successful cached result and creates no guidance artifact.
none_state="$tmp/no-candidate-state"; none_project="$tmp/no-candidate-project"; mkdir -p "$none_state/user-learning/signals" "$none_project"
cp "$signals"/*.json "$none_state/user-learning/signals/"
MANA_USER_STATE_HOME="$none_state" "$root/scripts/mana-user-learning.sh" --project-root "$none_project" aggregate >/dev/null
none_response="$(jq -cn --arg a "${ids[0]}" --arg b "${ids[1]}" --argjson signals "$signal_ids" '{result:"NO_CANDIDATE",reason:"The bounded evidence is too context-dependent to state narrow cross-project guidance.",relatedClusterIds:[$a,$b],supportingSignalIds:$signals}')"
none_run() { MANA_USER_STATE_HOME="$none_state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" M3_STUB_RESPONSE="$none_response" M3_STUB_CALLS="$tmp/no-candidate-calls" M3_STUB_BYTES="$tmp/no-candidate-bytes" "$root/scripts/mana-user-learning.sh" --project-root "$none_project" synthesize --json; }
none_first="$(none_run)"; printf '%s' "$none_first" | jq -e '.modelCalls==1 and .noCandidateResults==1 and .candidateResults==0' >/dev/null || fail 'NO_CANDIDATE was not successful'
[ ! -d "$none_state/user-learning/candidates" ] || [ -z "$(find "$none_state/user-learning/candidates" -type f -print -quit)" ] || fail 'NO_CANDIDATE created a guidance candidate'
none_second="$(none_run)"; printf '%s' "$none_second" | jq -e '.modelCalls==0 and .unitsAlreadySynthesized==1' >/dev/null || fail 'NO_CANDIDATE did not cache unchanged package'
flat_none="$(jq -c '. + {guidance:"",scope:"",rationale:"",limitations:[]}' <<<"$none_response")"
codex_none="$(PATH="$tmp:$PATH" MANA_USER_STATE_HOME="$none_state" MANA_USER_LEARNING_T1_PROVIDER=codex MANA_USER_LEARNING_T1_MODEL=fixture M3_CODEX_RESPONSE="$flat_none" M3_CODEX_ARGS="$tmp/codex-args" "$root/scripts/mana-user-learning.sh" --project-root "$none_project" synthesize --force --json)"
printf '%s' "$codex_none" | jq -e '.modelCalls==1 and .noCandidateResults==1 and .invalidProviderResponses==0' >/dev/null || fail 'flat Codex NO_CANDIDATE transport was not accepted'
flat_none_bad="$(jq -c '.guidance="unusable for NO_CANDIDATE"' <<<"$flat_none")"
codex_bad_none="$(PATH="$tmp:$PATH" MANA_USER_STATE_HOME="$none_state" MANA_USER_LEARNING_T1_PROVIDER=codex MANA_USER_LEARNING_T1_MODEL=fixture M3_CODEX_RESPONSE="$flat_none_bad" M3_CODEX_ARGS="$tmp/codex-args" "$root/scripts/mana-user-learning.sh" --project-root "$none_project" synthesize --force --json)"
printf '%s' "$codex_bad_none" | jq -e '.modelCalls==1 and .noCandidateResults==0 and .invalidProviderResponses==1' >/dev/null || fail 'NO_CANDIDATE conditional host validation was weakened'
malformed="$(MANA_USER_STATE_HOME="$none_state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" M3_STUB_RESPONSE='not-json' M3_STUB_CALLS="$tmp/no-candidate-calls" M3_STUB_BYTES="$tmp/no-candidate-bytes" "$root/scripts/mana-user-learning.sh" --project-root "$none_project" synthesize --force --json)"
printf '%s' "$malformed" | jq -e '.modelCalls==1 and .providerFailures==1 and .candidateResults==0' >/dev/null || fail 'malformed model output was accepted'
[ ! -d "$none_state/user-learning/candidates" ] || [ -z "$(find "$none_state/user-learning/candidates" -type f -print -quit)" ] || fail 'malformed output created a candidate'

# A nonzero provider exit remains distinct from invalid structured output and
# returns bounded, redacted diagnostics to the caller.
failure_stub="$tmp/failure-stub"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\\n" "Authorization: Bearer should-not-appear" >&2' 'printf "%s\\n" "API_KEY=should-not-appear" >&2' 'exit 23' > "$failure_stub"
chmod +x "$failure_stub"
transport_failure="$(MANA_USER_STATE_HOME="$none_state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$failure_stub" "$root/scripts/mana-user-learning.sh" --project-root "$none_project" synthesize --force --json)"
printf '%s' "$transport_failure" | jq -e '.modelCalls==1 and .providerFailures==1 and .providerTransportFailures==1 and .invalidProviderResponses==0 and (.providerFailureDiagnostics|length)==1 and .providerFailureDiagnostics[0].exitCode==23 and (.providerFailureDiagnostics[0].stderr|contains("should-not-appear")|not) and (.providerFailureDiagnostics[0].stderr|contains("[REDACTED]"))' >/dev/null || fail 'provider transport diagnostics were not bounded and redacted'

# One isolated decision is below the deterministic T0 spend threshold.
isolated="$tmp/isolated"; mkdir -p "$isolated/user-learning/signals" "$tmp/isolated-project"
cp "$signals/user-choice-$(hex 1).json" "$isolated/user-learning/signals/"
MANA_USER_STATE_HOME="$isolated" "$root/scripts/mana-user-learning.sh" --project-root "$tmp/isolated-project" aggregate >/dev/null
isolated_result="$(MANA_USER_STATE_HOME="$isolated" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" M3_STUB_RESPONSE="$candidate_response" M3_STUB_CALLS="$tmp/isolated-calls" M3_STUB_BYTES="$tmp/isolated-bytes" "$root/scripts/mana-user-learning.sh" --project-root "$tmp/isolated-project" synthesize --json)"
printf '%s' "$isolated_result" | jq -e '.modelCalls==0 and .synthesisUnits==1 and .unitsReadyToCall==0' >/dev/null || fail 'isolated evidence spent T1 tokens'

# A single exact M2 recurrence is still semantically ambiguous: T1 decides
# whether it is reusable guidance or an externally imposed repeated choice.
single_state="$tmp/single-exact-state"; single_project="$tmp/single-exact-project"; mkdir -p "$single_state/user-learning/signals" "$single_project"
old_signals="$signals"; signals="$single_state/user-learning/signals"
write_signal 21 21 'Async failure handling' 'durable retry'
write_signal 22 22 'Async failure handling' 'durable retry'
write_signal 23 23 'Async failure handling' 'durable retry'
signals="$old_signals"
MANA_USER_STATE_HOME="$single_state" "$root/scripts/mana-user-learning.sh" --project-root "$single_project" aggregate >/dev/null
single_cluster="$(jq -r .clusterId "$single_state/user-learning/clusters"/*.json)"; single_signals="$(jq -sc '[.[].supportingSignalIds[]]|sort' "$single_state/user-learning/clusters"/*.json)"
single_response="$(jq -cn --arg cluster "$single_cluster" --argjson signals "$single_signals" '{result:"CANDIDATE",guidance:"Prefer durable recovery when asynchronous work loss affects correctness.",scope:"reliability",rationale:"Repeated exact decisions explicitly preserve recoverable work.",limitations:["Bounded to supplied evidence."],relatedClusterIds:[$cluster],supportingSignalIds:$signals}')"
single_result="$(MANA_USER_STATE_HOME="$single_state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" M3_STUB_RESPONSE="$single_response" M3_STUB_CALLS="$tmp/single-calls" M3_STUB_BYTES="$tmp/single-bytes" "$root/scripts/mana-user-learning.sh" --project-root "$single_project" synthesize --json)"
printf '%s' "$single_result" | jq -e '.modelCalls==1 and .candidateResults==1 and .synthesisUnits==1 and .budgets.estimatedInputTokensBudget==3600 and .budgets.hardSerializedInputBytes==12000' >/dev/null || fail 'single_exact_recurring_cluster_is_eligible did not make exactly one T1 call'
[ "$(wc -c < "$tmp/single-calls" | tr -d ' ')" = 1 ] || fail 'single exact recurrence invoked T1 more than once'
jq -e '(.sourceClusterIds|length)==1 and .synthesis.invocation.serializedInputBytes <= 12000 and .synthesis.invocation.inputTokensEstimated > 0' "$single_state/user-learning/candidates"/*.json >/dev/null || fail 'single exact recurrence candidate lost bounded input telemetry'

weak_state="$tmp/weak-single-state"; weak_project="$tmp/weak-single-project"; mkdir -p "$weak_state/user-learning/signals" "$weak_project"
old_signals="$signals"; signals="$weak_state/user-learning/signals"
write_signal 31 31 'Async failure handling' 'durable retry'
write_signal 32 32 'Async failure handling' 'durable retry'
signals="$old_signals"
MANA_USER_STATE_HOME="$weak_state" "$root/scripts/mana-user-learning.sh" --project-root "$weak_project" aggregate >/dev/null
weak_result="$(MANA_USER_STATE_HOME="$weak_state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" M3_STUB_RESPONSE="$single_response" M3_STUB_CALLS="$tmp/weak-calls" M3_STUB_BYTES="$tmp/weak-bytes" "$root/scripts/mana-user-learning.sh" --project-root "$weak_project" synthesize --json)"
printf '%s' "$weak_result" | jq -e '.modelCalls==0 and .unitsReadyToCall==0 and .synthesisUnits==1' >/dev/null || fail 'insufficient_single_cluster_is_not_eligible spent T1 tokens'
[ ! -e "$tmp/weak-calls" ] || fail 'insufficient single cluster invoked the provider'

# The host reduces optional support before enforcing its independent hard
# serialized-input bound; an irreducible package never reaches the provider.
oversize_state="$tmp/oversize-state"; oversize_project="$tmp/oversize-project"; mkdir -p "$oversize_state/user-learning/signals" "$oversize_project"
old_signals="$signals"; signals="$oversize_state/user-learning/signals"
write_signal 41 41 'Async failure handling with a deliberately long bounded subject field for package pressure' 'durable retry with a deliberately long bounded confirmed choice field for package pressure'
write_signal 42 42 'Async failure handling with a deliberately long bounded subject field for package pressure' 'durable retry with a deliberately long bounded confirmed choice field for package pressure'
write_signal 43 43 'Async failure handling with a deliberately long bounded subject field for package pressure' 'durable retry with a deliberately long bounded confirmed choice field for package pressure'
write_signal 44 44 'Async failure handling with a deliberately long bounded subject field for package pressure' 'durable retry with a deliberately long bounded confirmed choice field for package pressure'
signals="$old_signals"
MANA_USER_STATE_HOME="$oversize_state" "$root/scripts/mana-user-learning.sh" --project-root "$oversize_project" aggregate >/dev/null
oversize_cluster="$(jq -r .clusterId "$oversize_state/user-learning/clusters"/*.json)"; oversize_signals="$(jq -sc '[.[].supportingSignalIds[]]|sort|.[0:2]' "$oversize_state/user-learning/clusters"/*.json)"
oversize_response="$(jq -cn --arg cluster "$oversize_cluster" --argjson signals "$oversize_signals" '{result:"CANDIDATE",guidance:"Prefer durable recovery when loss affects correctness.",scope:"reliability",rationale:"Fixture.",limitations:["Fixture."],relatedClusterIds:[$cluster],supportingSignalIds:$signals}')"
reduced_result="$(MANA_USER_STATE_HOME="$oversize_state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" MANA_USER_LEARNING_MAX_SIGNALS_PER_CLUSTER=4 MANA_USER_LEARNING_MAX_INPUT_BYTES=3200 M3_STUB_RESPONSE="$oversize_response" M3_STUB_CALLS="$tmp/reduced-calls" M3_STUB_BYTES="$tmp/reduced-bytes" "$root/scripts/mana-user-learning.sh" --project-root "$oversize_project" synthesize --json)"
printf '%s' "$reduced_result" | jq -e '.modelCalls==1 and .unitsReducedBeforeProviderCall==1 and .unitsSkippedIrreduciblyOversized==0 and .serializedInputBytes <= 3200' >/dev/null || fail 'oversized_package_is_reduced_before_provider_call'
[ "$(wc -c < "$tmp/reduced-calls" | tr -d ' ')" = 1 ] || fail 'reduced package did not make one bounded provider call'

irreducible_state="$tmp/irreducible-state"; irreducible_project="$tmp/irreducible-project"; mkdir -p "$irreducible_state/user-learning/signals" "$irreducible_project"
cp "$oversize_state/user-learning/signals"/*.json "$irreducible_state/user-learning/signals/"
MANA_USER_STATE_HOME="$irreducible_state" "$root/scripts/mana-user-learning.sh" --project-root "$irreducible_project" aggregate >/dev/null
irreducible_result="$(MANA_USER_STATE_HOME="$irreducible_state" MANA_USER_LEARNING_T1_PROVIDER=stub MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$stub" MANA_USER_LEARNING_MAX_SIGNALS_PER_CLUSTER=4 MANA_USER_LEARNING_MAX_INPUT_BYTES=100 M3_STUB_RESPONSE="$oversize_response" M3_STUB_CALLS="$tmp/irreducible-calls" M3_STUB_BYTES="$tmp/irreducible-bytes" "$root/scripts/mana-user-learning.sh" --project-root "$irreducible_project" synthesize --json)"
printf '%s' "$irreducible_result" | jq -e '.modelCalls==0 and .unitsSkippedIrreduciblyOversized==1 and .unitsReadyToCall==0' >/dev/null || fail 'irreducibly_oversized_package_makes_zero_model_calls'
[ ! -e "$tmp/irreducible-calls" ] || fail 'irreducibly oversized package invoked provider'

echo 'User Learning synthesis tests passed'
