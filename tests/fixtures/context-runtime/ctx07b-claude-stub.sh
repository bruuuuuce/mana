#!/usr/bin/env bash
# Deterministic Claude-shaped CTX-07B routing/packet stub; never contacts a model.
set -eu

fixture_root="${CTX07B_FIXTURE_ROOT:?}"
state_dir="${CTX07B_STATE_DIR:?}"
scenario="${CTX07B_SCENARIO:-complete}"
capability_set="${CTX07B_CAPABILITY_SET:-claude-supported}"

case "${1:-}" in
  --version)
    cat "$fixture_root/provider-capabilities/$capability_set/version.txt"
    exit 0
    ;;
  --help)
    cat "$fixture_root/provider-capabilities/$capability_set/root-help.txt"
    exit 0
    ;;
esac

[ -z "${MANA_CONTEXT_PHASE_LOCK_HELD:-}" ] || exit 10
mkdir -p "$state_dir"
model=""
effort=""
previous=""
prompt=""
argv_tmp="$(mktemp "$state_dir/argv.pending.XXXXXX")"
for argument in "$@"; do
  printf '%s\n' "$argument" >> "$argv_tmp"
  case "$previous" in
    --model) model="$argument" ;;
    --effort) effort="$argument" ;;
  esac
  previous="$argument"
  prompt="$argument"
done
packet="$(printf '%s\n' "$prompt" | sed -n 's/^workerContextPacket=//p')"
task_id="$(jq -er .delegationTask.taskId <<<"$packet")"
printf '%s' "$prompt" > "$state_dir/prompt.$task_id"
printf '%s\n' "$model" > "$state_dir/model.$task_id"
printf '%s\n' "$effort" > "$state_dir/effort.$task_id"
printf '%s\n' "$$" > "$state_dir/pid.$task_id"
printf '%s\n' "$task_id" >> "$state_dir/invocations.log"
: > "$state_dir/provider-reached.$task_id"
mv "$argv_tmp" "$state_dir/argv.$task_id"

if [ "$scenario" = parallel ]; then
  : > "$state_dir/ready.$task_id"
  shopt -s nullglob
  for ((probe=0; probe<200; probe++)); do
    arrivals=("$state_dir"/ready.*)
    [ "${#arrivals[@]}" -lt 2 ] || break
    sleep 0.02
  done
  [ "${#arrivals[@]}" -ge 2 ] || exit 43
fi

[ "$scenario" != provider-reject ] || exit 42
if [ "$scenario" = stderr-secret ]; then
  printf '%s\n' 'PROVIDER-STDERR-SECRET-CANARY' >&2
  exit 42
fi
if [ "$scenario" = malformed ]; then printf '{'; exit 0; fi
if [ "$scenario" = early-exit ] || [ "$scenario" = early-failure ]; then
  (
    trap '' TERM
    (trap '' TERM; while :; do printf 'tick\n' >> "$state_dir/heartbeat"; sleep 0.05; done) &
    printf '%s\n' "$!" > "$state_dir/grandchild.pid"
    while :; do sleep 1; done
  ) &
  printf '%s\n' "$!" > "$state_dir/child.pid"
  while [ ! -f "$state_dir/heartbeat" ]; do sleep 0.01; done
  [ "$scenario" != early-failure ] || exit 42
fi
if [ "$scenario" = timeout ]; then
  (
    trap '' TERM
    (trap '' TERM; while :; do sleep 1; done) &
    printf '%s\n' "$!" > "$state_dir/grandchild.pid"
    while :; do sleep 1; done
  ) &
  printf '%s\n' "$!" > "$state_dir/child.pid"
  while :; do sleep 1; done
fi
case "$scenario" in
  invalid)
    result_task_id="T-foreign"
    ;;
  complete|unauthorized|early-exit|parallel)
    result_task_id="$task_id"
    ;;
  *) exit 8 ;;
esac
if [ "$scenario" = unauthorized ]; then
  draft="$(jq -cn --arg taskId "$result_task_id" '{
    schemaVersion:"mana.context-runtime.delegation-result-draft/v1",taskId:$taskId,status:"complete",
    verifiedFacts:[{id:"F-unauthorized",subject:{domain:"repository",kind:"component",identifier:"worker"},predicate:"is-safe",stance:"affirmed",claim:"The worker is safe.",severity:null,evidenceRefs:[("E-" + ("0" * 64))]}],
    findings:[],assumptions:[],inferences:[],openQuestions:[],evidenceGaps:[],artifactRefs:[],
    uncertainty:{level:"none",description:null,evidenceRefs:[]}
  }')"
else
  draft="$(jq -cn --arg taskId "$result_task_id" '{
    schemaVersion:"mana.context-runtime.delegation-result-draft/v1",taskId:$taskId,status:"complete",
    verifiedFacts:[],findings:[],assumptions:[],inferences:[],openQuestions:[],evidenceGaps:[],artifactRefs:[],
    uncertainty:{level:"none",description:null,evidenceRefs:[]}
  }')"
fi
jq -cn --argjson draft "$draft" '{structured_output:$draft}'
