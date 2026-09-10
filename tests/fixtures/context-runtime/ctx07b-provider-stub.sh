#!/usr/bin/env bash
# Deterministic Codex-shaped CTX-07B worker/provider-capability stub.
set -eu

fixture_root="${CTX07B_FIXTURE_ROOT:?}"
state_dir="${CTX07B_STATE_DIR:?}"
scenario="${CTX07B_SCENARIO:-complete}"
capability_set="${CTX07B_CAPABILITY_SET:-codex-supported}"

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
final_message=""
model=""
schema=""
previous=""
prompt=""
argv_tmp="$(mktemp "$state_dir/argv.pending.XXXXXX")"
for argument in "$@"; do
  printf '%s\n' "$argument" >> "$argv_tmp"
  case "$previous" in
    --output-last-message) final_message="$argument" ;;
    --model) model="$argument" ;;
    --output-schema) schema="$argument" ;;
  esac
  previous="$argument"
  prompt="$argument"
done
[ -n "$final_message" ] || exit 9
task_packet="$(printf '%s\n' "$prompt" | sed -n 's/^taskPacket=//p')"
task_id="$(jq -er .taskId <<<"$task_packet")"
printf '%s' "$prompt" > "$state_dir/prompt.$task_id"
printf '%s\n' "$model" > "$state_dir/model.$task_id"
printf '%s\n' "$schema" > "$state_dir/schema.$task_id"
printf '%s\n' "$$" > "$state_dir/pid.$task_id"
printf '%s\n' "${MANA_RUNTIME_EXECUTION_ID:-}" > "$state_dir/execution.$task_id"
mv "$argv_tmp" "$state_dir/argv.$task_id"

printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":7,"cached_input_tokens":2,"uncached_input_tokens":5,"output_tokens":2,"reasoning_tokens":1}}'
case "$scenario" in
  invalid)
    printf '%s\n' '{"schemaVersion":"mana.context-runtime.delegation-result-draft/v1","taskId":"T-foreign","status":"complete","verifiedFacts":[],"findings":[],"assumptions":[],"inferences":[],"openQuestions":[],"evidenceGaps":[],"artifactRefs":[],"uncertainty":{"level":"none","description":null,"evidenceRefs":[]}}' > "$final_message"
    ;;
  unauthorized)
    jq -cn --arg taskId "$task_id" '{
      schemaVersion:"mana.context-runtime.delegation-result-draft/v1",taskId:$taskId,status:"complete",
      verifiedFacts:[{id:"F-unauthorized",subject:{domain:"repository",kind:"component",identifier:"worker"},predicate:"is-safe",stance:"affirmed",claim:"The worker is safe.",severity:null,evidenceRefs:[("E-" + ("0" * 64))]}],
      findings:[],assumptions:[],inferences:[],openQuestions:[],evidenceGaps:[],artifactRefs:[],
      uncertainty:{level:"none",description:null,evidenceRefs:[]}
    }' > "$final_message"
    ;;
  complete)
    jq -cn --arg taskId "$task_id" '{
      schemaVersion:"mana.context-runtime.delegation-result-draft/v1",taskId:$taskId,status:"complete",
      verifiedFacts:[],findings:[],assumptions:[],inferences:[],openQuestions:[],evidenceGaps:[],artifactRefs:[],
      uncertainty:{level:"none",description:null,evidenceRefs:[]}
    }' > "$final_message"
    ;;
  *) exit 8 ;;
esac
