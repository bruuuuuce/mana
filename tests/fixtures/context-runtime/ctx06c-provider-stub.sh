#!/usr/bin/env bash
# Deterministic Codex-shaped CTX-06C provider and capability probe fixture.
set -eu

fixture_root="${CTX06C_FIXTURE_ROOT:?}"
state_dir="${CTX06C_STATE_DIR:?}"
scenario="${CTX06C_SCENARIO:-complete}"
capability_set="${CTX06C_CAPABILITY_SET:-codex-supported}"

case "${1:-}" in
  --version) cat "$fixture_root/provider-capabilities/$capability_set/version.txt"; exit 0 ;;
  --help) cat "$fixture_root/provider-capabilities/$capability_set/root-help.txt"; exit 0 ;;
  exec)
    if [ "${2:-}" = --help ]; then
      cat "$fixture_root/provider-capabilities/$capability_set/run-help.txt"
      exit 0
    fi
    ;;
  features)
    if [ "${2:-}" = list ]; then
      cat "$fixture_root/provider-capabilities/$capability_set/features.txt"
      exit 0
    fi
    ;;
esac

[ -z "${MANA_CONTEXT_PHASE_LOCK_HELD:-}" ] || exit 10
mkdir -p "$state_dir"
count_file="$state_dir/count"
count="$(sed -n '1p' "$count_file" 2>/dev/null || true)"
case "$count" in ''|*[!0-9]*) count=0 ;; esac
count=$((count + 1))
printf '%s\n' "$count" > "$count_file"

final_message=""
model=""
schema=""
project_root=""
previous=""
prompt=""
: > "$state_dir/argv.$count"
for argument in "$@"; do
  printf '%s\n' "$argument" >> "$state_dir/argv.$count"
  case "$previous" in
    --output-last-message) final_message="$argument" ;;
    --model) model="$argument" ;;
    --output-schema) schema="$argument" ;;
    --cd) project_root="$argument" ;;
  esac
  previous="$argument"
  prompt="$argument"
done
printf '%s' "$prompt" > "$state_dir/prompt.$count"
printf '%s\n' "$model" > "$state_dir/model.$count"
printf '%s\n' "$schema" > "$state_dir/schema.$count"
pwd -P > "$state_dir/cwd.$count"
[ -n "$final_message" ] || exit 9

phase_input="$(printf '%s\n' "$prompt" | sed -n 's/^phaseInput=//p')"
context_manifest="$(printf '%s\n' "$prompt" | sed -n 's/^contextManifest=//p')"
execution_id="$(jq -er .executionId <<<"$phase_input")"
phase_id="$(jq -er .phaseId <<<"$phase_input")"
profile_id="$(jq -er .profileId <<<"$context_manifest")"

printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":2,"uncached_input_tokens":8,"output_tokens":3,"reasoning_tokens":1}}'
if [ "$scenario" = interrupt-second ] && [ "$count" -eq 2 ]; then
  exit 143
fi
if [ "$scenario" = invalid ]; then
  printf '%s\n' '{"not":"a checkpoint","private":"provider response"}' > "$final_message"
  exit 0
fi

if [ "$phase_id" = classify ]; then
  next_kind=next-declared-phase
  target=synthesize
else
  next_kind=stop
  target=null
fi
jq -cn \
  --arg checkpointId "C-fixture-$count" \
  --arg executionId "$execution_id" \
  --arg profileId "$profile_id" \
  --arg phaseId "$phase_id" \
  --arg kind "$next_kind" \
  --arg target "$target" \
  '{schemaVersion:"mana.context-runtime.phase-checkpoint/v1",
    checkpointId:$checkpointId,executionId:$executionId,executionVersion:1,
    profileId:$profileId,phaseId:$phaseId,status:"complete",verifiedFacts:[],
    assumptions:[],inferences:[],openQuestions:[],closedHypotheses:[],
    candidateFindings:[],approvalRequests:[],activatedSkills:[],evidenceRefs:[],
    nextActionRequest:{kind:$kind,targetId:(if $target=="null" then null else $target end),reason:"fixture transition"}}' \
  > "$final_message"

if [ "$scenario" = privacy-canary ]; then
  jq '.nextActionRequest.reason = "CTX09C_ENVIRONMENT_CANARY"' "$final_message" > "$state_dir/privacy-checkpoint"
  mv "$state_dir/privacy-checkpoint" "$final_message"
fi

# Optional typed observations are fixture input, committed by the real consumer.
if [ "$phase_id" = synthesize ] && [ -n "${CTX09C_R2A_PROJECTION_PATH:-}" ]; then
  jq --slurpfile projection "$CTX09C_R2A_PROJECTION_PATH" '. + {comparisonProjection:$projection[0]}' \
    "$final_message" > "$state_dir/projected-checkpoint"
  mv "$state_dir/projected-checkpoint" "$final_message"
fi

if [ "$phase_id" = classify ] && [ -n "${CTX09C_R2A_EARLY_PROJECTION_PATH:-}" ]; then
  jq --slurpfile projection "$CTX09C_R2A_EARLY_PROJECTION_PATH" '. + {comparisonProjection:$projection[0]}' \
    "$final_message" > "$state_dir/early-projected-checkpoint"
  mv "$state_dir/early-projected-checkpoint" "$final_message"
fi

if [ "$phase_id" = synthesize ] && [ -n "${CTX09C_R2A_MERGE_PATH:-}" ]; then
  run="$project_root/.mana/runtime/runs/$execution_id"
  merge_ref="phases/002-synthesize/delegation-merge-v1.json"
  mkdir -p "$run/phases/002-synthesize"
  chmod 700 "$run/phases/002-synthesize"
  cp "$CTX09C_R2A_MERGE_PATH" "$run/$merge_ref"
  chmod 600 "$run/$merge_ref"
  merge_digest="$(shasum -a 256 "$run/$merge_ref" | cut -d ' ' -f 1)"
  jq --arg ref "$merge_ref" --arg digest "$merge_digest" \
    '. + {comparisonMergeRef:{ref:$ref,sha256:$digest}}' "$final_message" > "$state_dir/merge-checkpoint"
  mv "$state_dir/merge-checkpoint" "$final_message"
fi
