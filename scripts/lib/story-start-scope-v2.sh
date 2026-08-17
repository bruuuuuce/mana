#!/usr/bin/env bash
# Internal, non-default Story Start Scope v2 phase support. SS02-SS04 add
# discovery, triage, and planning; public integration remains reserved for SS06.

mana_story_start_scope_v2_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

mana_story_start_scope_v2_discovery_prompt() {
  local package="$1"
  cat <<'CONTRACT'
You are Mana Story Start Discovery v2. Return exactly one JSON object matching
the supplied discovery-inventory v2 schema and use only the compact evidence
package below. Discover and report evidence; distinguish observed facts from
inferences; preserve bounded provenance; relate evidence to acceptance criteria
only where the evidence supports it; record pre-existing status, ambiguities,
open questions, decisions, and a suggested owner when evidence supports one.

This is discovery, not planning. Do not decide implementation scope. Do not produce implementation tasks. Do not estimate remediation work. Do not choose between unresolved architectures. Do not assume a discovered defect belongs to the current story. Do not turn missing evidence into a fabricated requirement.
Do not inspect a repository, ticket system, network, or any data outside this
package. A missing fact is evidence_gap evidence, never a requirement.

Use findings only for neutral facts, constraints, defects, suspected defects,
risks, readiness, ambiguities, or optional opportunities. Use openQuestions
when an answer is unknown without complete decision alternatives. Use decisions
only when alternatives and an owner are evidenced. Keep an open decision's
selectedOptionId null. Do not include tasks, estimates, classifications, or a
final total: the discovery schema rejects them.

COMPACT_DISCOVERY_PACKAGE
CONTRACT
  jq -cS . "$package"
}

mana_story_start_scope_v2_validate_discovery() {
  local artifact="$1" root
  root="$(mana_story_start_scope_v2_root)"
  python3 "$root/tests/lib/json_schema_subset.py" \
    "$root/contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json" \
    "$artifact"
}

# Arguments: provider model compact-package.json normalized-output.json.
# The caller owns evidence collection. This phase gives the provider only a
# compact package, so later phases need not receive a repository.
mana_story_start_scope_v2_discover() {
  local provider="$1" model="$2" package="$3" output="$4"
  local root schema normalizer scratch prompt program output_file status_file stage timeout code signal timed_out descendants
  root="$(mana_story_start_scope_v2_root)"
  schema="$root/contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json"
  normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
  [ -f "$package" ] || { echo "ERROR: missing Discovery v2 package: $package" >&2; return 2; }
  [ -f "$schema" ] && [ -f "$normalizer" ] || { echo 'ERROR: Story Start Scope v2 contract is unavailable' >&2; return 2; }
  jq -e 'type == "object"' "$package" >/dev/null || { echo 'ERROR: Discovery v2 package must be a JSON object' >&2; return 2; }
  [ "$(wc -c < "$package" | tr -d ' ')" -le 262144 ] || { echo 'ERROR: Discovery v2 package exceeds 262144 bytes' >&2; return 2; }
  timeout="${MANA_STORY_START_SCOPE_V2_DISCOVERY_TIMEOUT_SECONDS:-120}"
  [[ "$timeout" =~ ^[1-9][0-9]*$ ]] && [ "$timeout" -le 300 ] || { echo 'ERROR: Discovery v2 timeout must be 1..300 seconds' >&2; return 2; }
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-discovery-v2.XXXXXX")" || return 2
  mkdir -p "$scratch/empty"
  prompt="$(mana_story_start_scope_v2_discovery_prompt "$package")" || { rm -rf "$scratch"; return 2; }
  MANA_PROVIDER_PROGRAM="$provider"
  mana_provider_synthesis_args "$provider" "$scratch/empty" "$model" host-disposable-non-git "$schema" || { rm -rf "$scratch"; echo 'ERROR: Discovery v2 provider arguments could not be constructed' >&2; return 2; }
  program="${MANA_PROVIDER_PROGRAM:-$provider}"
  command -v "$program" >/dev/null 2>&1 || { rm -rf "$scratch"; echo "ERROR: Discovery v2 provider is unavailable: $program" >&2; return 2; }
  output_file="$scratch/provider-output.json"
  status_file="$scratch/status.tsv"
  perl "$root/scripts/lib/verification-exec.pl" --timeout "$timeout" --output-cap 262144 --stderr-cap 4096 --stdout "$output_file" --stderr "$scratch/provider.stderr" --status "$status_file" -- "$program" "${MANA_PROVIDER_ARGS[@]}" "$prompt" || true
  if [ ! -f "$status_file" ] || ! IFS=$'\t' read -r code signal timed_out descendants _ < "$status_file" || [ "$code" -ne 0 ] || [ "$timed_out" != 0 ] || [ "$descendants" != 0 ]; then
    rm -rf "$scratch"
    echo 'ERROR: Discovery v2 provider execution failed' >&2
    return 1
  fi
  mana_story_start_scope_v2_validate_discovery "$output_file" || { rm -rf "$scratch"; echo 'ERROR: Discovery v2 provider output failed schema validation' >&2; return 1; }
  mkdir -p "$(dirname "$output")"
  [ ! -L "$output" ] || { rm -rf "$scratch"; echo "ERROR: unsafe Discovery v2 output symlink: $output" >&2; return 2; }
  stage="$(mktemp "$(dirname "$output")/.${output##*/}.tmp.XXXXXX")" || { rm -rf "$scratch"; return 2; }
  if ! python3 "$normalizer" normalize-discovery "$schema" "$output_file" "$stage"; then rm -f "$stage"; rm -rf "$scratch"; echo 'ERROR: Discovery v2 normalization failed' >&2; return 1; fi
  mana_story_start_scope_v2_validate_discovery "$stage" || { rm -f "$stage"; rm -rf "$scratch"; echo 'ERROR: normalized Discovery v2 artifact failed schema validation' >&2; return 1; }
  mv "$stage" "$output"
  rm -rf "$scratch"
}

mana_story_start_scope_v2_triage_prompt() {
  local story="$1" discovery="$2"
  cat <<'CONTRACT'
You are Mana Story Start Scope Triage v2. Return exactly one JSON object matching
the supplied scope-triage v2 schema. Use only the normalized story and compact
Discovery v2 artifact below. Do not inspect the repository, ticket system,
network, or any other data. Missing evidence must remain an evidence gap with
owner review; never fabricate certainty or infer that an absent subsystem must
be built.

Classify every discovery finding exactly once as VERIFIED_FACT, CORE_SCOPE,
REQUIRED_ENABLER, CONDITIONAL_SCOPE, READINESS_PREREQUISITE, RELATED_DEFECT,
RISK_ONLY, or OPTIONAL_IMPROVEMENT. Evidence found is not scope approved.
Only CORE_SCOPE can be base-plan eligible. No other category may set
includedInBasePlan true. This phase creates no task and no estimate.

Before CORE_SCOPE or REQUIRED_ENABLER, fill every promotionAssessment answer:
the failing AC/constraint, dependency evidence, pre-existing status, unresolved
decision, and story regression/aggravation impact. Without an AC or mandatory
constraint reference, promotion is forbidden. Preserve open decisions and
selectedOptionId null. Represent mutually exclusive options in separate stable
optionGroups with selectionRule exactly_one. Do not select a more robust
architecture or combine alternatives.

NORMALIZED_STORY
CONTRACT
  jq -cS '{storyId, normalizedStory}' "$story"
  printf '%s\n' 'COMPACT_DISCOVERY_V2'
  jq -cS . "$discovery"
}

mana_story_start_scope_v2_validate_triage() {
  local artifact="$1" root
  root="$(mana_story_start_scope_v2_root)"
  python3 "$root/tests/lib/json_schema_subset.py" \
    "$root/contracts/story-start/scope-v2/schemas/scope-triage.schema.json" \
    "$artifact"
}

# Arguments: provider model normalized-story.json discovery-v2.json output.json.
mana_story_start_scope_v2_triage() {
  local provider="$1" model="$2" story="$3" discovery="$4" output="$5"
  local root schema normalizer scratch prompt program output_file status_file stage timeout code signal timed_out descendants
  root="$(mana_story_start_scope_v2_root)"
  schema="$root/contracts/story-start/scope-v2/schemas/scope-triage.schema.json"
  normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
  jq -e 'type == "object" and (.storyId | type == "string" and length > 0) and
    (.normalizedStory | type == "object") and
    (.normalizedStory.acceptanceCriteria | type == "array")' "$story" >/dev/null || { echo 'ERROR: normalized story must contain storyId and acceptance criteria' >&2; return 2; }
  mana_story_start_scope_v2_validate_discovery "$discovery" || { echo 'ERROR: Scope Triage requires a valid Discovery v2 artifact' >&2; return 2; }
  [ "$(jq -r '.storyId' "$story")" = "$(jq -r '.storyId' "$discovery")" ] || { echo 'ERROR: normalized story does not match Discovery v2 storyId' >&2; return 2; }
  [ "$(( $(wc -c < "$story") + $(wc -c < "$discovery") ))" -le 524288 ] || { echo 'ERROR: Scope Triage compact inputs exceed 524288 bytes' >&2; return 2; }
  timeout="${MANA_STORY_START_SCOPE_V2_TRIAGE_TIMEOUT_SECONDS:-120}"
  [[ "$timeout" =~ ^[1-9][0-9]*$ ]] && [ "$timeout" -le 300 ] || { echo 'ERROR: Scope Triage timeout must be 1..300 seconds' >&2; return 2; }
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-triage-v2.XXXXXX")" || return 2
  mkdir -p "$scratch/empty"
  prompt="$(mana_story_start_scope_v2_triage_prompt "$story" "$discovery")" || { rm -rf "$scratch"; return 2; }
  MANA_PROVIDER_PROGRAM="$provider"
  mana_provider_synthesis_args "$provider" "$scratch/empty" "$model" host-disposable-non-git "$schema" || { rm -rf "$scratch"; echo 'ERROR: Scope Triage provider arguments could not be constructed' >&2; return 2; }
  program="${MANA_PROVIDER_PROGRAM:-$provider}"
  command -v "$program" >/dev/null 2>&1 || { rm -rf "$scratch"; echo "ERROR: Scope Triage provider is unavailable: $program" >&2; return 2; }
  output_file="$scratch/provider-output.json"
  status_file="$scratch/status.tsv"
  perl "$root/scripts/lib/verification-exec.pl" --timeout "$timeout" --output-cap 262144 --stderr-cap 4096 --stdout "$output_file" --stderr "$scratch/provider.stderr" --status "$status_file" -- "$program" "${MANA_PROVIDER_ARGS[@]}" "$prompt" || true
  if [ ! -f "$status_file" ] || ! IFS=$'\t' read -r code signal timed_out descendants _ < "$status_file" || [ "$code" -ne 0 ] || [ "$timed_out" != 0 ] || [ "$descendants" != 0 ]; then
    rm -rf "$scratch"
    echo 'ERROR: Scope Triage provider execution failed' >&2
    return 1
  fi
  mana_story_start_scope_v2_validate_triage "$output_file" || { rm -rf "$scratch"; echo 'ERROR: Scope Triage provider output failed schema validation' >&2; return 1; }
  mkdir -p "$(dirname "$output")"
  [ ! -L "$output" ] || { rm -rf "$scratch"; echo "ERROR: unsafe Scope Triage output symlink: $output" >&2; return 2; }
  stage="$(mktemp "$(dirname "$output")/.${output##*/}.tmp.XXXXXX")" || { rm -rf "$scratch"; return 2; }
  if ! python3 "$normalizer" normalize-triage "$schema" "$discovery" "$output_file" "$stage"; then rm -f "$stage"; rm -rf "$scratch"; echo 'ERROR: Scope Triage normalization failed' >&2; return 1; fi
  mana_story_start_scope_v2_validate_triage "$stage" || { rm -f "$stage"; rm -rf "$scratch"; echo 'ERROR: normalized Scope Triage artifact failed schema validation' >&2; return 1; }
  mv "$stage" "$output"
  rm -rf "$scratch"
}

mana_story_start_scope_v2_plan_prompt() {
  local story="$1" context="$2" triage="$3"
  cat <<'CONTRACT'
You are Mana Story Start Implementation Planner v2. Return exactly one JSON
object matching the supplied implementation-plan v2 schema. Use only the
normalized story, compact planning evidence, and Scope Triage v2 artifact
below. Do not inspect a repository, ticket system, network, raw Discovery
findings, or any other context.

Create basePlan tasks only for CORE_SCOPE. Keep every REQUIRED_ENABLER in its
own requiredEnablers entry with mandatory_delta effort and its causal evidence.
Create conditionalBranches only for CONDITIONAL_SCOPE, one branch per decision
option, and retain the triage relationship and selection rule in branchGroups.
Never combine mutually exclusive branch deltas or choose a more robust option.

Keep READINESS_PREREQUISITE outside implementation scope with engineering
effort separate from calendar impact.
Pending approval has zero developer effort.
Put RELATED_DEFECT, RISK_ONLY, and OPTIONAL_IMPROVEMENT only in
relatedFindings with excludedFromBasePlan true and no tasks. A VERIFIED_FACT
may support a task, but existing configuration must be reused rather than
planned as newly created.

Every task must cite evidenceRefs, provenanceRefs, provenance-backed
sourceTargets, testEvidenceRefs, and at least one AC or mandatory constraint
through its owning base/enabler classification. Separate base effort,
mandatory deltas, conditional deltas, readiness effort, calendar impact, and
scenario totals. Scenario arithmetic must be exact. Select exactly one branch
from every exactly-one group per scenario and never sum sibling alternatives.
Represent every branch in at least one scenario. Preserve decisions exactly.
While any material decision is open, finalCommittedEstimate must be null,
every scenario is scenario_only, and owner review remains required.

NORMALIZED_STORY
CONTRACT
  jq -cS '{storyId, normalizedStory}' "$story"
  printf '%s\n' 'COMPACT_PLANNING_CONTEXT_V2'
  jq -cS . "$context"
  printf '%s\n' 'SCOPE_TRIAGE_V2'
  jq -cS . "$triage"
}

mana_story_start_scope_v2_validate_plan() {
  local artifact="$1" root
  root="$(mana_story_start_scope_v2_root)"
  python3 "$root/tests/lib/json_schema_subset.py" \
    "$root/contracts/story-start/scope-v2/schemas/implementation-plan.schema.json" \
    "$artifact"
}

# Arguments: provider model normalized-story.json planning-context.json
# scope-triage-v2.json normalized-plan.json.
mana_story_start_scope_v2_plan() {
  local provider="$1" model="$2" story="$3" context="$4" triage="$5" output="$6"
  local root schema normalizer scratch prompt program output_file status_file stage timeout code signal timed_out descendants
  root="$(mana_story_start_scope_v2_root)"
  schema="$root/contracts/story-start/scope-v2/schemas/implementation-plan.schema.json"
  normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
  jq -e 'type == "object" and (.storyId | type == "string" and length > 0) and
    (.normalizedStory | type == "object") and
    (.normalizedStory.acceptanceCriteria | type == "array")' "$story" >/dev/null || { echo 'ERROR: normalized story must contain storyId and acceptance criteria' >&2; return 2; }
  mana_story_start_scope_v2_validate_triage "$triage" || { echo 'ERROR: Planner v2 requires a valid Scope Triage artifact' >&2; return 2; }
  python3 "$normalizer" validate-planning-context "$context" "$triage" || { echo 'ERROR: Planner v2 requires a valid compact planning context' >&2; return 2; }
  [ "$(jq -r '.storyId' "$story")" = "$(jq -r '.storyId' "$triage")" ] || { echo 'ERROR: normalized story does not match Scope Triage storyId' >&2; return 2; }
  [ "$(( $(wc -c < "$story") + $(wc -c < "$context") + $(wc -c < "$triage") ))" -le 786432 ] || { echo 'ERROR: Planner v2 compact inputs exceed 786432 bytes' >&2; return 2; }
  timeout="${MANA_STORY_START_SCOPE_V2_PLANNER_TIMEOUT_SECONDS:-120}"
  [[ "$timeout" =~ ^[1-9][0-9]*$ ]] && [ "$timeout" -le 300 ] || { echo 'ERROR: Planner v2 timeout must be 1..300 seconds' >&2; return 2; }
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-planner-v2.XXXXXX")" || return 2
  mkdir -p "$scratch/empty"
  prompt="$(mana_story_start_scope_v2_plan_prompt "$story" "$context" "$triage")" || { rm -rf "$scratch"; return 2; }
  MANA_PROVIDER_PROGRAM="$provider"
  mana_provider_synthesis_args "$provider" "$scratch/empty" "$model" host-disposable-non-git "$schema" || { rm -rf "$scratch"; echo 'ERROR: Planner v2 provider arguments could not be constructed' >&2; return 2; }
  program="${MANA_PROVIDER_PROGRAM:-$provider}"
  command -v "$program" >/dev/null 2>&1 || { rm -rf "$scratch"; echo "ERROR: Planner v2 provider is unavailable: $program" >&2; return 2; }
  output_file="$scratch/provider-output.json"
  status_file="$scratch/status.tsv"
  perl "$root/scripts/lib/verification-exec.pl" --timeout "$timeout" --output-cap 524288 --stderr-cap 4096 --stdout "$output_file" --stderr "$scratch/provider.stderr" --status "$status_file" -- "$program" "${MANA_PROVIDER_ARGS[@]}" "$prompt" || true
  if [ ! -f "$status_file" ] || ! IFS=$'\t' read -r code signal timed_out descendants _ < "$status_file" || [ "$code" -ne 0 ] || [ "$timed_out" != 0 ] || [ "$descendants" != 0 ]; then
    rm -rf "$scratch"
    echo 'ERROR: Planner v2 provider execution failed' >&2
    return 1
  fi
  mana_story_start_scope_v2_validate_plan "$output_file" || { rm -rf "$scratch"; echo 'ERROR: Planner v2 provider output failed schema validation' >&2; return 1; }
  mkdir -p "$(dirname "$output")"
  [ ! -L "$output" ] || { rm -rf "$scratch"; echo "ERROR: unsafe Planner v2 output symlink: $output" >&2; return 2; }
  stage="$(mktemp "$(dirname "$output")/.${output##*/}.tmp.XXXXXX")" || { rm -rf "$scratch"; return 2; }
  if ! python3 "$normalizer" normalize-plan "$schema" "$context" "$triage" "$output_file" "$stage"; then rm -f "$stage"; rm -rf "$scratch"; echo 'ERROR: Planner v2 normalization failed' >&2; return 1; fi
  mana_story_start_scope_v2_validate_plan "$stage" || { rm -f "$stage"; rm -rf "$scratch"; echo 'ERROR: normalized Planner v2 artifact failed schema validation' >&2; return 1; }
  mv "$stage" "$output"
  rm -rf "$scratch"
}
