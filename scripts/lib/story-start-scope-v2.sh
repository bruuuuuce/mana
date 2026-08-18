#!/usr/bin/env bash
# Story Start Scope v2 phase, governance, publication, and rendering support.
# SS06 exposes the complete pipeline through the existing public profile runner
# as a versioned opt-in while the legacy v1 path remains the default.

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
# scope-triage-v2.json raw-provider-output. This helper owns the existing
# isolated provider boundary but deliberately does not validate or publish the
# candidate, so SS05 can report and correct first-pass validation failures.
mana_story_start_scope_v2_plan_candidate() {
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
  mkdir -p "$(dirname "$output")"
  [ ! -L "$output" ] || { rm -rf "$scratch"; echo "ERROR: unsafe Planner v2 output symlink: $output" >&2; return 2; }
  stage="$(mktemp "$(dirname "$output")/.${output##*/}.tmp.XXXXXX")" || { rm -rf "$scratch"; return 2; }
  cp "$output_file" "$stage" && mv "$stage" "$output" || { rm -f "$stage"; rm -rf "$scratch"; return 2; }
  rm -rf "$scratch"
}

# Arguments: provider model normalized-story.json planning-context.json
# scope-triage-v2.json normalized-plan.json.
mana_story_start_scope_v2_plan() {
  local provider="$1" model="$2" story="$3" context="$4" triage="$5" output="$6"
  local root schema normalizer scratch raw stage
  root="$(mana_story_start_scope_v2_root)"
  schema="$root/contracts/story-start/scope-v2/schemas/implementation-plan.schema.json"
  normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-plan-normalize-v2.XXXXXX")" || return 2
  raw="$scratch/provider-output.json"
  if ! mana_story_start_scope_v2_plan_candidate "$provider" "$model" "$story" "$context" "$triage" "$raw"; then
    rm -rf "$scratch"
    return 1
  fi
  mana_story_start_scope_v2_validate_plan "$raw" || { rm -rf "$scratch"; echo 'ERROR: Planner v2 provider output failed schema validation' >&2; return 1; }
  mkdir -p "$(dirname "$output")"
  [ ! -L "$output" ] || { rm -rf "$scratch"; echo "ERROR: unsafe Planner v2 output symlink: $output" >&2; return 2; }
  stage="$(mktemp "$(dirname "$output")/.${output##*/}.tmp.XXXXXX")" || { rm -rf "$scratch"; return 2; }
  if ! python3 "$normalizer" normalize-plan "$schema" "$context" "$triage" "$raw" "$stage"; then rm -f "$stage"; rm -rf "$scratch"; echo 'ERROR: Planner v2 normalization failed' >&2; return 1; fi
  mana_story_start_scope_v2_validate_plan "$stage" || { rm -f "$stage"; rm -rf "$scratch"; echo 'ERROR: normalized Planner v2 artifact failed schema validation' >&2; return 1; }
  mv "$stage" "$output"
  rm -rf "$scratch"
}

mana_story_start_scope_v2_validate_governance_report() {
  local report="$1" root
  root="$(mana_story_start_scope_v2_root)"
  python3 "$root/scripts/lib/story-start-scope-v2-govern.py" validate-report "$report"
}

# Arguments: discovery-v2.json scope-triage-v2.json implementation-plan-v2.json
# governance-report.json. The validator reads only these supplied artifacts and
# host-owned schemas. It returns 0 only for a fully governed plan, while still
# writing a compact structured report for deterministic failures.
mana_story_start_scope_v2_govern() {
  local discovery="$1" triage="$2" plan="$3" report="$4" root
  root="$(mana_story_start_scope_v2_root)"
  python3 "$root/scripts/lib/story-start-scope-v2-govern.py" \
    validate "$discovery" "$triage" "$plan" "$report"
}

mana_story_start_scope_v2_correction_prompt() {
  local invalid_plan="$1" violation_report="$2"
  cat <<'CONTRACT'
You are Mana Story Start Scope v2 artifact correction. Return exactly one JSON
object matching the supplied implementation-plan v2 schema. Correct only the
deterministic violations in the compact report. Preserve all valid story,
scope, evidence, provenance, decision, task, and estimate information.

This is one bounded correction attempt, not replanning. Use only the invalid
artifact and violation report below. Do not inspect a repository, workspace,
ticket system, network, or any other context. Do not choose an open decision,
expand scope, add unrelated work, or emit a legacy/free-form plan. If the
report does not provide enough evidence for a safe correction, preserve the
unknown rather than fabricate certainty.

INVALID_IMPLEMENTATION_PLAN_V2
CONTRACT
  if jq -e 'type == "object"' "$invalid_plan" >/dev/null 2>&1; then
    jq -cS . "$invalid_plan"
  else
    printf '%s\n' 'UNPARSED_PROVIDER_OUTPUT_JSON_STRING'
    jq -Rs . "$invalid_plan"
  fi
  printf '%s\n' 'SCOPE_GOVERNOR_VIOLATION_REPORT_V2'
  jq -cS . "$violation_report"
}

# Arguments: provider model discovery-v2.json scope-triage-v2.json
# candidate-plan-v2.json governed-plan.json final-governance-report.json.
# Exactly one corrective provider call is possible. A failed second validation
# publishes only needs_owner_review diagnostics, never an invalid or legacy plan.
mana_story_start_scope_v2_govern_with_correction() {
  local provider="$1" model="$2" discovery="$3" triage="$4" candidate="$5" output="$6" report="$7"
  local root governor normalizer plan_schema scratch initial corrected_raw corrected_normalized context prompt program status_file timeout code signal timed_out descendants stage
  root="$(mana_story_start_scope_v2_root)"
  governor="$root/scripts/lib/story-start-scope-v2-govern.py"
  normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
  plan_schema="$root/contracts/story-start/scope-v2/schemas/implementation-plan.schema.json"
  [ -f "$discovery" ] && [ -f "$triage" ] && [ -f "$candidate" ] || { echo 'ERROR: Scope Governor inputs are unavailable' >&2; return 2; }
  [ -f "$governor" ] && [ -f "$normalizer" ] && [ -f "$plan_schema" ] || { echo 'ERROR: Scope Governor runtime is unavailable' >&2; return 2; }
  [ "$(wc -c < "$candidate" | tr -d ' ')" -le 524288 ] || { echo 'ERROR: Scope Governor candidate exceeds 524288 bytes' >&2; return 2; }
  mkdir -p "$(dirname "$output")" "$(dirname "$report")"
  [ ! -L "$output" ] && [ ! -L "$report" ] || { echo 'ERROR: unsafe Scope Governor output symlink' >&2; return 2; }
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-governor-v2.XXXXXX")" || return 2
  initial="$scratch/initial-report.json"
  if python3 "$governor" validate "$discovery" "$triage" "$candidate" "$initial"; then
    stage="$(mktemp "$(dirname "$output")/.${output##*/}.tmp.XXXXXX")" || { rm -rf "$scratch"; return 2; }
    cp "$candidate" "$stage" && mv "$stage" "$output" || { rm -f "$stage"; rm -rf "$scratch"; return 2; }
    stage="$(mktemp "$(dirname "$report")/.${report##*/}.tmp.XXXXXX")" || { rm -rf "$scratch"; return 2; }
    cp "$initial" "$stage" && mv "$stage" "$report" || { rm -f "$stage"; rm -rf "$scratch"; return 2; }
    rm -rf "$scratch"
    return 0
  fi
  mana_story_start_scope_v2_validate_governance_report "$initial" || { rm -rf "$scratch"; echo 'ERROR: Scope Governor failed to produce a valid first-pass report' >&2; return 2; }

  timeout="${MANA_STORY_START_SCOPE_V2_CORRECTION_TIMEOUT_SECONDS:-120}"
  [[ "$timeout" =~ ^[1-9][0-9]*$ ]] && [ "$timeout" -le 300 ] || { rm -rf "$scratch"; echo 'ERROR: Scope Governor correction timeout must be 1..300 seconds' >&2; return 2; }
  prompt="$(mana_story_start_scope_v2_correction_prompt "$candidate" "$initial")" || { rm -rf "$scratch"; return 2; }
  mkdir -p "$scratch/empty"
  MANA_PROVIDER_PROGRAM="$provider"
  if ! mana_provider_synthesis_args "$provider" "$scratch/empty" "$model" host-disposable-non-git "$plan_schema"; then
    if ! python3 "$governor" provider-failed "$initial" "$report" 'Corrective provider arguments could not be constructed.' >/dev/null 2>&1; then
      rm -rf "$scratch"
      echo 'ERROR: Scope Governor could not publish owner-review diagnostics' >&2
      return 2
    fi
    rm -rf "$scratch"
    return 1
  fi
  program="${MANA_PROVIDER_PROGRAM:-$provider}"
  if ! command -v "$program" >/dev/null 2>&1; then
    if ! python3 "$governor" provider-failed "$initial" "$report" 'Corrective provider is unavailable.' >/dev/null 2>&1; then
      rm -rf "$scratch"
      echo 'ERROR: Scope Governor could not publish owner-review diagnostics' >&2
      return 2
    fi
    rm -rf "$scratch"
    return 1
  fi
  corrected_raw="$scratch/corrected-provider-output.json"
  status_file="$scratch/status.tsv"
  perl "$root/scripts/lib/verification-exec.pl" --timeout "$timeout" --output-cap 524288 --stderr-cap 4096 --stdout "$corrected_raw" --stderr "$scratch/provider.stderr" --status "$status_file" -- "$program" "${MANA_PROVIDER_ARGS[@]}" "$prompt" || true
  if [ ! -f "$status_file" ] || ! IFS=$'\t' read -r code signal timed_out descendants _ < "$status_file" || [ "$code" -ne 0 ] || [ "$timed_out" != 0 ] || [ "$descendants" != 0 ]; then
    if ! python3 "$governor" provider-failed "$initial" "$report" 'The single corrective provider invocation failed or exceeded its bounds.' >/dev/null 2>&1; then
      rm -rf "$scratch"
      echo 'ERROR: Scope Governor could not publish owner-review diagnostics' >&2
      return 2
    fi
    rm -rf "$scratch"
    return 1
  fi

  corrected_normalized="$scratch/corrected-normalized.json"
  context="$scratch/planning-context.json"
  if mana_story_start_scope_v2_validate_plan "$corrected_raw" >/dev/null 2>&1 && \
    python3 "$normalizer" build-planning-context "$discovery" "$triage" "$context" >/dev/null 2>&1 && \
    python3 "$normalizer" normalize-plan "$plan_schema" "$context" "$triage" "$corrected_raw" "$corrected_normalized" >/dev/null 2>&1; then
    :
  else
    corrected_normalized="$corrected_raw"
  fi

  if python3 "$governor" revalidate "$initial" "$discovery" "$triage" "$corrected_normalized" "$report"; then
    stage="$(mktemp "$(dirname "$output")/.${output##*/}.tmp.XXXXXX")" || { rm -rf "$scratch"; return 2; }
    cp "$corrected_normalized" "$stage" && mv "$stage" "$output" || { rm -f "$stage"; rm -rf "$scratch"; return 2; }
    rm -rf "$scratch"
    return 0
  fi
  if ! mana_story_start_scope_v2_validate_governance_report "$report"; then
    rm -rf "$scratch"
    echo 'ERROR: Scope Governor second pass produced no valid owner-review report' >&2
    return 2
  fi
  rm -rf "$scratch"
  return 1
}

# Internal SS05 pipeline boundary. Planner output is staged, then the complete
# Discovery/Triage/Plan set must pass the governor (with at most one correction)
# before a plan can be published. Public Story Start does not call this until SS06.
mana_story_start_scope_v2_plan_governed() {
  local provider="$1" model="$2" story="$3" discovery="$4" context="$5" triage="$6" output="$7" report="$8"
  local root schema normalizer scratch raw candidate
  root="$(mana_story_start_scope_v2_root)"
  schema="$root/contracts/story-start/scope-v2/schemas/implementation-plan.schema.json"
  normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-plan-governed-v2.XXXXXX")" || return 2
  raw="$scratch/provider-output.json"
  candidate="$scratch/candidate-plan.json"
  if ! mana_story_start_scope_v2_plan_candidate "$provider" "$model" "$story" "$context" "$triage" "$raw"; then
    rm -rf "$scratch"
    return 1
  fi
  if mana_story_start_scope_v2_validate_plan "$raw" >/dev/null 2>&1 && \
    python3 "$normalizer" normalize-plan "$schema" "$context" "$triage" "$raw" "$candidate" >/dev/null 2>&1; then
    :
  else
    cp "$raw" "$candidate" || { rm -rf "$scratch"; return 2; }
  fi
  mana_story_start_scope_v2_govern_with_correction "$provider" "$model" "$discovery" "$triage" "$candidate" "$output" "$report"
  local result=$?
  rm -rf "$scratch"
  return "$result"
}

mana_story_start_scope_v2_validate_public_context() {
  local package="$1"
  if [ ! -f "$package" ] || [ -L "$package" ]; then
    echo "ERROR: Story Start Scope v2 context is missing or unsafe: $package" >&2
    return 2
  fi
  [ "$(wc -c < "$package" | tr -d ' ')" -le 262144 ] || {
    echo 'ERROR: Story Start Scope v2 context exceeds 262144 bytes' >&2
    return 2
  }
  jq -e '
    type == "object" and
    .packageVersion == "mana.story-start.discovery-package/v1" and
    (.storyId | type == "string" and length > 0) and
    (.normalizedStory | type == "object") and
    (.normalizedStory.summary | type == "string" and length > 0) and
    (.normalizedStory.acceptanceCriteria | type == "array" and length > 0) and
    all(.normalizedStory.acceptanceCriteria[];
      type == "object" and
      ((.sourceKey // .id) | type == "string" and length > 0) and
      (.text | type == "string" and length > 0))
  ' "$package" >/dev/null || {
    echo 'ERROR: Story Start Scope v2 context does not match mana.story-start.discovery-package/v1' >&2
    return 2
  }
}

mana_story_start_scope_v2_validate_run_status() {
  local status="$1" root
  root="$(mana_story_start_scope_v2_root)"
  python3 "$root/tests/lib/json_schema_subset.py" \
    "$root/contracts/story-start/scope-v2/schemas/scope-run.schema.json" \
    "$status" &&
    python3 "$root/scripts/lib/story-start-scope-v2-render.py" validate-status "$status"
}

mana_story_start_scope_v2_atomic_copy() {
  local source="$1" target="$2" stage
  [ -f "$source" ] || { echo "ERROR: publication source is missing: $source" >&2; return 2; }
  mkdir -p "$(dirname "$target")" || return 2
  [ ! -L "$target" ] || { echo "ERROR: unsafe publication output symlink: $target" >&2; return 2; }
  stage="$(mktemp "$(dirname "$target")/.${target##*/}.tmp.XXXXXX")" || return 2
  if ! cp "$source" "$stage" || ! mv "$stage" "$target"; then
    rm -f "$stage"
    return 2
  fi
}

mana_story_start_scope_v2_render() {
  local plan="$1" governance="$2" status="$3" output="$4" root
  root="$(mana_story_start_scope_v2_root)"
  mana_story_start_scope_v2_validate_plan "$plan" >/dev/null || return 2
  mana_story_start_scope_v2_validate_governance_report "$governance" >/dev/null || return 2
  mana_story_start_scope_v2_validate_run_status "$status" >/dev/null || return 2
  python3 "$root/scripts/lib/story-start-scope-v2-render.py" render \
    "$status" "$output" --plan "$plan" --governance "$governance"
}

mana_story_start_scope_v2_render_owner_review() {
  local status="$1" output="$2" governance="${3:-}" root
  root="$(mana_story_start_scope_v2_root)"
  mana_story_start_scope_v2_validate_run_status "$status" >/dev/null || return 2
  if [ -n "$governance" ]; then
    mana_story_start_scope_v2_validate_governance_report "$governance" >/dev/null || return 2
    python3 "$root/scripts/lib/story-start-scope-v2-render.py" render \
      "$status" "$output" --governance "$governance"
  else
    python3 "$root/scripts/lib/story-start-scope-v2-render.py" render \
      "$status" "$output"
  fi
}

# Publish a terminal owner-review status and a usable Markdown diagnostic. No
# invalid or free-form plan is copied. The optional governance report is the
# only phase artifact retained when the governor itself reached a valid
# fail-closed result.
mana_story_start_scope_v2_publish_failure() {
  local workspace="$1" story_id="$2" phase="$3" reason="$4" governance="${5:-}"
  local root renderer scratch status report published_governance
  root="$(mana_story_start_scope_v2_root)"
  renderer="$root/scripts/lib/story-start-scope-v2-render.py"
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-publish-failure-v2.XXXXXX")" || return 2
  status="$scratch/run-status.json"
  report="$scratch/report.md"
  if [ -n "$governance" ]; then
    python3 "$renderer" status-failed "$story_id" "$phase" "$reason" "$status" --governance "$governance" || { rm -rf "$scratch"; return 2; }
    mana_story_start_scope_v2_render_owner_review "$status" "$report" "$governance" || { rm -rf "$scratch"; return 2; }
    published_governance="$workspace/validation/story-start-scope-governance-v2.json"
    mana_story_start_scope_v2_atomic_copy "$governance" "$published_governance" || { rm -rf "$scratch"; return 2; }
  else
    python3 "$renderer" status-failed "$story_id" "$phase" "$reason" "$status" || { rm -rf "$scratch"; return 2; }
    mana_story_start_scope_v2_render_owner_review "$status" "$report" || { rm -rf "$scratch"; return 2; }
  fi
  mana_story_start_scope_v2_atomic_copy "$report" "$workspace/planning/story-start-scope-v2.md" || { rm -rf "$scratch"; return 2; }
  # Status is the publication commit marker and is always written last.
  mana_story_start_scope_v2_atomic_copy "$status" "$workspace/validation/story-start-scope-run-v2.json" || { rm -rf "$scratch"; return 2; }
  rm -rf "$scratch"
}

# Public SS06 pipeline. The supplied package is the existing compact
# story/context boundary; every later phase consumes only normalized artifacts.
# Successful publication is additive and leaves v1 Markdown paths untouched.
# Arguments: provider model story-context-package.json active-workspace.
mana_story_start_scope_v2_run_public() {
  local provider="$1" model="$2" package="$3" workspace="$4"
  local root normalizer renderer scratch story discovery triage context plan governance status report story_id
  root="$(mana_story_start_scope_v2_root)"
  normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
  renderer="$root/scripts/lib/story-start-scope-v2-render.py"
  mana_story_start_scope_v2_validate_public_context "$package" || return 2
  if [ ! -d "$workspace" ] || [ -L "$workspace" ]; then
    echo "ERROR: active Story Start workspace is missing or unsafe: $workspace" >&2
    return 2
  fi
  story_id="$(jq -r '.storyId' "$package")"
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-public-v2.XXXXXX")" || return 2
  story="$scratch/story.json"
  discovery="$scratch/discovery.json"
  triage="$scratch/triage.json"
  context="$scratch/planning-context.json"
  plan="$scratch/implementation-plan.json"
  governance="$scratch/governance-report.json"
  status="$scratch/run-status.json"
  report="$scratch/report.md"
  jq -S '{storyId, normalizedStory}' "$package" > "$story" || { rm -rf "$scratch"; return 2; }

  if ! mana_story_start_scope_v2_discover "$provider" "$model" "$package" "$discovery"; then
    rm -rf "$scratch"
    mana_story_start_scope_v2_publish_failure "$workspace" "$story_id" discovery \
      'Discovery v2 provider failed or returned an invalid structured artifact.'
    return 1
  fi
  if ! mana_story_start_scope_v2_triage "$provider" "$model" "$story" "$discovery" "$triage"; then
    rm -rf "$scratch"
    mana_story_start_scope_v2_publish_failure "$workspace" "$story_id" triage \
      'Scope Triage v2 provider failed or returned an invalid structured artifact.'
    return 1
  fi
  if ! python3 "$normalizer" build-planning-context "$discovery" "$triage" "$context"; then
    rm -rf "$scratch"
    mana_story_start_scope_v2_publish_failure "$workspace" "$story_id" planner \
      'The host could not build the compact v2 planning context.'
    return 1
  fi
  if ! mana_story_start_scope_v2_plan_governed "$provider" "$model" "$story" "$discovery" "$context" "$triage" "$plan" "$governance"; then
    if [ -f "$governance" ] && mana_story_start_scope_v2_validate_governance_report "$governance" >/dev/null 2>&1; then
      mana_story_start_scope_v2_publish_failure "$workspace" "$story_id" governor \
        'Scope Governor rejected the plan after the single allowed correction attempt.' "$governance"
    else
      mana_story_start_scope_v2_publish_failure "$workspace" "$story_id" planner \
        'Planner v2 provider failed or returned an unusable structured candidate.'
    fi
    rm -rf "$scratch"
    return 1
  fi

  python3 "$renderer" status-passed "$discovery" "$triage" "$plan" "$governance" "$status" || { rm -rf "$scratch"; return 2; }
  mana_story_start_scope_v2_validate_run_status "$status" >/dev/null || { rm -rf "$scratch"; return 2; }
  mana_story_start_scope_v2_render "$plan" "$governance" "$status" "$report" || { rm -rf "$scratch"; return 2; }

  # Publish only fully validated artifacts. The run status is copied last and
  # acts as the cross-file publication commit marker for consumers.
  mana_story_start_scope_v2_atomic_copy "$discovery" "$workspace/evidence/story-start-discovery-v2.json" || { rm -rf "$scratch"; return 2; }
  mana_story_start_scope_v2_atomic_copy "$triage" "$workspace/planning/story-start-scope-triage-v2.json" || { rm -rf "$scratch"; return 2; }
  mana_story_start_scope_v2_atomic_copy "$plan" "$workspace/planning/story-start-implementation-plan-v2.json" || { rm -rf "$scratch"; return 2; }
  mana_story_start_scope_v2_atomic_copy "$governance" "$workspace/validation/story-start-scope-governance-v2.json" || { rm -rf "$scratch"; return 2; }
  mana_story_start_scope_v2_atomic_copy "$report" "$workspace/planning/story-start-scope-v2.md" || { rm -rf "$scratch"; return 2; }
  mana_story_start_scope_v2_atomic_copy "$status" "$workspace/validation/story-start-scope-run-v2.json" || { rm -rf "$scratch"; return 2; }
  rm -rf "$scratch"
}
