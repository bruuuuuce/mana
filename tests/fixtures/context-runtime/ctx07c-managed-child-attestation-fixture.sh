#!/usr/bin/env bash
# End-to-end provider-shaped CTX-07C-R2 fixture. It is accepted only by the
# canonical test-only runner and never by the production provider framework.
set -euo pipefail

fixture_root="${CTX07B_FIXTURE_ROOT:?}"
state_dir="${CTX07B_STATE_DIR:?}"
scenario="${CTX07C_SCENARIO:-valid}"

case "${1:-}" in
  --version)
    cat "$fixture_root/provider-capabilities/claude-child-supported/version.txt"
    exit 0
    ;;
  --help)
    cat "$fixture_root/provider-capabilities/claude-child-supported/root-help.txt"
    exit 0
    ;;
esac

mkdir -p "$state_dir"
test_adapter=false
prompt=""
for argument in "$@"; do
  [ "$argument" != --mana-ctx07c-test-attested-child ] || test_adapter=true
  prompt="$argument"
done
packet="$(printf '%s\n' "$prompt" | sed -n 's/^workerContextPacket=//p')"
[ -n "$packet" ] || exit 90
task_id="$(jq -er .delegationTask.taskId <<<"$packet")"
task_digest="$(jq -er .delegationTask.taskDigest <<<"$packet")"

if [ "$test_adapter" != true ]; then
  printf '%s\n' "$task_id" >> "$state_dir/host-worker-reached.log"
  exit 91
fi

root_id="${CTX07C_ROOT_ID:-root-fixture-001}"
child_id="${CTX07C_CHILD_ID:-child-fixture-001}"
printf '%s\n' "$root_id" >> "$state_dir/provider-root-reached.log"

if [ "$scenario" = timeout ] || [ "$scenario" = interruption ]; then
  while :; do sleep 1; done
fi

if [ "$scenario" = root-direct ]; then
  jq -cn --arg taskId "$task_id" '{structured_output:{
    schemaVersion:"mana.context-runtime.delegation-result-draft/v1",
    taskId:$taskId,status:"complete",verifiedFacts:[],findings:[],assumptions:[],
    inferences:[],openQuestions:[],evidenceGaps:[],artifactRefs:[],
    uncertainty:{level:"none",description:null,evidenceRefs:[]}
  }}'
  exit 0
fi

printf '%s\n' "$child_id" >> "$state_dir/child-reached.log"
[ "$scenario" != child-nonzero ] || exit 42

execution_id="$(jq -er .delegationTask.executionId <<<"$packet")"
execution_version="$(jq -er .delegationTask.executionVersion <<<"$packet")"
workspace_id="$(jq -er .delegationTask.workspaceId <<<"$packet")"
profile_id="$(jq -er .delegationTask.profileId <<<"$packet")"
phase_id="$(jq -er .delegationTask.phaseId <<<"$packet")"
attempt="$(jq -er .delegationTask.attempt <<<"$packet")"
plan_id="$(jq -er .delegationTask.planId <<<"$packet")"

draft="$(jq -cn --arg taskId "$task_id" '{
  schemaVersion:"mana.context-runtime.delegation-result-draft/v1",
  taskId:$taskId,status:"complete",verifiedFacts:[],findings:[],assumptions:[],
  inferences:[],openQuestions:[],evidenceGaps:[],artifactRefs:[],
  uncertainty:{level:"none",description:null,evidenceRefs:[]}
}')"
if [ "$scenario" = semantic-invalid ]; then
  draft="$(jq -cn --arg taskId "$task_id" '{
    schemaVersion:"mana.context-runtime.delegation-result-draft/v1",
    taskId:$taskId,status:"complete",
    verifiedFacts:[{
      id:"F-invalid",subject:{domain:"repository",kind:"component",identifier:"fixture"},
      predicate:"is-valid",stance:"affirmed",claim:"Unattested semantic claim.",
      severity:null,evidenceRefs:[("E-" + ("0" * 64))]
    }],
    findings:[],assumptions:[],inferences:[],openQuestions:[],evidenceGaps:[],
    artifactRefs:[],uncertainty:{level:"none",description:null,evidenceRefs:[]}
  }')"
fi

root_event="$(jq -cn \
  --arg root "$root_id" --arg executionId "$execution_id" \
  --argjson executionVersion "$execution_version" --arg workspaceId "$workspace_id" \
  --arg profileId "$profile_id" --arg phaseId "$phase_id" \
  --argjson attempt "$attempt" --arg planId "$plan_id" \
  '{sequence:1,eventType:"root.started",rootInvocationId:$root,
    executionId:$executionId,executionVersion:$executionVersion,workspaceId:$workspaceId,
    profileId:$profileId,phaseId:$phaseId,attempt:$attempt,planId:$planId}')"
start_event="$(jq -cn --arg root "$root_id" --arg child "$child_id" \
  '{sequence:2,eventType:"child.started",rootInvocationId:$root,childInvocationId:$child}')"
bound_event="$(jq -cn --arg root "$root_id" --arg child "$child_id" \
  --arg taskId "$task_id" --arg taskDigest "$task_digest" \
  '{sequence:3,eventType:"child.task.bound",rootInvocationId:$root,
    childInvocationId:$child,taskId:$taskId,taskDigest:$taskDigest}')"
terminal_event="$(jq -cn --arg root "$root_id" --arg child "$child_id" \
  --arg taskId "$task_id" --arg taskDigest "$task_digest" \
  '{sequence:4,eventType:"child.completed",rootInvocationId:$root,
    childInvocationId:$child,taskId:$taskId,taskDigest:$taskDigest,status:"completed"}')"
events="$(jq -cn --argjson root "$root_event" --argjson start "$start_event" \
  --argjson bound "$bound_event" --argjson terminal "$terminal_event" \
  '[$root,$start,$bound,$terminal]')"

case "$scenario" in
  valid|semantic-invalid) ;;
  receipt-missing)
    jq -cn --argjson draft "$draft" '{structured_output:$draft,managedChildExecutionAttestation:null}'
    exit 0
    ;;
  completed-before-started)
    events="$(jq '[.[0], (.[3] | .sequence=2), (.[1] | .sequence=3), (.[2] | .sequence=4)]' <<<"$events")"
    ;;
  completion-without-start)
    events="$(jq '[.[0], (.[2] | .sequence=2), (.[3] | .sequence=3), (.[3] | .sequence=4)]' <<<"$events")"
    ;;
  duplicate-start)
    events="$(jq '[.[0], .[1], (.[1] | .sequence=3), .[3]]' <<<"$events")"
    ;;
  duplicate-terminal)
    events="$(jq '. + [(.[3] | .sequence=5)]' <<<"$events")"
    ;;
  same-root-child)
    events="$(jq --arg root "$root_id" 'map(if has("childInvocationId") then .childInvocationId=$root else . end)' <<<"$events")"
    ;;
  task-digest-mismatch)
    events="$(jq 'map(if has("taskDigest") then .taskDigest=("sha256:" + ("0" * 64)) else . end)' <<<"$events")"
    ;;
  foreign)
    events="$(jq '.[0].executionId="execution-foreign"' <<<"$events")"
    ;;
  stale)
    events="$(jq '.[0].attempt=(.[0].attempt + 1)' <<<"$events")"
    ;;
  sequence-gap)
    events="$(jq '.[2].sequence=9' <<<"$events")"
    ;;
  event-after-terminal)
    events="$(jq '. + [(.[2] | .sequence=5)]' <<<"$events")"
    ;;
  child-failed)
    events="$(jq '.[3].eventType="child.failed" | .[3].status="failed"' <<<"$events")"
    ;;
  *) exit 92 ;;
esac

jq -cn --argjson draft "$draft" --argjson events "$events" '{
  structured_output:$draft,
  managedChildExecutionAttestation:{
    attestationKind:"provider-native-managed-child-event-receipt/v1",
    events:$events
  }
}'
