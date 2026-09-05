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
previous=""
prompt=""
: > "$state_dir/argv.$count"
for argument in "$@"; do
  printf '%s\n' "$argument" >> "$state_dir/argv.$count"
  case "$previous" in
    --output-last-message) final_message="$argument" ;;
    --model) model="$argument" ;;
    --output-schema) schema="$argument" ;;
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
