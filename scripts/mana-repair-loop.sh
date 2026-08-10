#!/usr/bin/env bash
# Thin deterministic consumer of immutable repair_once results. It contains no
# provider execution path and can invoke the primitive at most twice.
set -u

root="$(cd "$(dirname "$0")/.." && pwd)"
. "$root/scripts/lib/verification.sh"
. "$root/scripts/lib/repair.sh"
. "$root/scripts/lib/runtime-events.sh"

project_root="$(pwd)"; from=""; check_id=""; allow_path=""; provider=""; max_iterations=""; dry_run=false; explain=false; json=false
HARD_MAX_ITERATIONS=2; LOOP_TOTAL_SECONDS="${MANA_REPAIR_LOOP_SECONDS:-900}"; LOOP_SAFETY_SECONDS=65; LOOP_MAX_CHANGED_LINES=100; LOOP_ATTEMPT_SECONDS="${MANA_REPAIR_RUNNER_SECONDS:-600}"
[ "$LOOP_TOTAL_SECONDS" -ge 1 ] 2>/dev/null && [ "$LOOP_TOTAL_SECONDS" -le 900 ] 2>/dev/null || LOOP_TOTAL_SECONDS=900
[ "$LOOP_ATTEMPT_SECONDS" -ge 1 ] 2>/dev/null && [ "$LOOP_ATTEMPT_SECONDS" -le 600 ] 2>/dev/null || LOOP_ATTEMPT_SECONDS=600
fail() { echo "ERROR: $*" >&2; exit 2; }
loop_now_ms() { perl -MTime::HiRes=time -e 'printf "%.0f\n", time()*1000' 2>/dev/null; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; shift 2;; --from) from="${2:-}"; shift 2;; --check) check_id="${2:-}"; shift 2;; --allow-path) allow_path="${2:-}"; shift 2;; --runner) provider="${2:-}"; shift 2;;
    --max-iterations) max_iterations="${2:-}"; shift 2;; --dry-run) dry_run=true; shift;; --explain) explain=true; shift;; --json) json=true; shift;; *) fail "unknown loop option: $1";;
  esac
done
[ "$max_iterations" = 2 ] || fail 'bounded loop requires explicit --max-iterations 2'; [ -n "$from" ] && [ -n "$allow_path" ] && [ -n "$provider" ] || fail 'bounded loop inputs are incomplete'
project_root="$(cd "$project_root" 2>/dev/null && pwd -P)" || fail 'project root not found'; from="$(cd "$(dirname "$from")" 2>/dev/null && pwd -P)/$(basename "$from")"
case "$from" in "$project_root"/.mana/*/evidence/verification/*/result.json) ;; *) fail 'loop evidence must be canonical project-local verification evidence';; esac
repair_safe_path "$allow_path" || fail 'unsafe loop mutation path'

once_args=(--project-root "$project_root" --from "$from" --allow-path "$allow_path" --runner "$provider" --once --json); [ -n "$check_id" ] && once_args+=(--check "$check_id")
preflight="$("$root/scripts/mana-repair.sh" "${once_args[@]}" --dry-run 2>/dev/null)"; preflight_status=$?
loop_plan="$(jq -n --argjson initial "${preflight:-null}" --arg provider "$provider" --arg path "$allow_path" '{schemaVersion:"1",kind:"repair-loop-plan",initialRepairPlan:$initial,containment:$initial.containment,staging:$initial.staging,baseline:$initial.baseline,candidateImport:$initial.candidateImport,rerun:$initial.rerun,requestedMaxIterations:2,hardMaxIterations:2,defaultIterations:1,attemptTwo:{mayRun:true,condition:"attempt 1 is fully comparable UNCHANGED with mechanically proven strict-subset partial progress",finalAttempt:true,freshWorkspaceFromCurrentLiveState:true},provider:$provider,mutationGrant:{allowedPaths:[$path],maxFiles:1,cumulativeMaxChangedLines:100,hardMaxChangedLines:500},budgets:{perAttemptMaxSeconds:600,totalLoopMaxSeconds:900,stdoutBytesPerAttempt:65536,stderrBytesPerAttempt:65536,contractBytesPerAttempt:8192},protectedSurfaceDigest:($initial.protectedSurfaceDigest//"unavailable"),stopConditions:["target_resolved","no_progress","regressed","comparison_unknown","policy_violation","integrity_violation","runner_failed","runner_timeout","verification_blocked","verification_inconclusive","repair_loop_budget_exhausted","hard_iteration_limit","human_scope_required","interrupted"],persistentEffects:false}')"
render_plan() { echo 'MANA BOUNDED REPAIR LOOP PLAN'; jq -r '"initial eligibility: "+(.initialRepairPlan.eligibility//"blocked"),"containment: "+(.containment.backend//"unavailable")+" ("+(.containment.capability//"unavailable")+"; not an adversarial boundary)","provider: "+.provider+" in a disposable project copy","attempts: default 1; explicit hard maximum 2","attempt two: fresh workspace from current live state; MAY run only after strict-subset partial progress","allowed paths: "+(.mutationGrant.allowedPaths|join(", ")),"staging exclusions: "+(.staging.exclusions//"unavailable"),"baseline: "+(.baseline.identity//"unavailable"),"import: exact regular-text target only; live drift stops with "+(.candidateImport.liveDriftStopReason//"live_target_drift"),"rerun: verifier-owned against live repository after import","budgets: 600s per attempt; 900s total; cumulative 100 changed lines","protected surface: "+.protectedSurfaceDigest,"stop conditions: "+(.stopConditions|join(", "))' <<<"$loop_plan"; }
if [ "$dry_run" = true ]; then if [ "$json" = true ]; then printf '%s\n' "$loop_plan"; else render_plan; fi; [ "$preflight_status" -eq 0 ]; exit; fi
if [ "$preflight_status" -ne 0 ] || [ "$(jq -r '.eligibility // "blocked"' <<<"$preflight")" != eligible ]; then if [ "$json" = true ]; then printf '%s\n' "$loop_plan"; else render_plan; fi; exit 1; fi
check_id="$(jq -r .checkId <<<"$preflight")"; workspace="${from%%/evidence/verification/*}"; workspace_reference="${workspace#"$project_root"/}"; loop_parent="$workspace/evidence/repair-loop"
loop_id="repair-loop-$(date -u +%Y%m%dT%H%M%SZ)-$$"; staging="$loop_parent/.${loop_id}.tmp"; final_dir="$loop_parent/$loop_id"; loop_lock="$workspace/evidence/repair/.repair-loop.lock"; project_lock="$project_root/.mana/.repair-loop.lock"; tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-repair-loop.XXXXXX")"; started_ms="$(loop_now_ms)"
[ -n "$started_ms" ] || fail 'monotonic loop clock is unavailable'
umask 077; mkdir -p "$loop_parent" "$(dirname "$loop_lock")" "$project_root/.mana" || fail 'could not prepare repair loop evidence'; mkdir "$project_lock" 2>/dev/null || fail 'another bounded repair loop is active for this repository'; mkdir "$loop_lock" 2>/dev/null || { rmdir "$project_lock" 2>/dev/null || true; fail 'another bounded repair loop is active'; }; printf '%s\n' "$loop_id" > "$loop_lock/id" || fail 'could not identify repair loop lock'; printf '%s\n' "$loop_id" > "$project_lock/id" || fail 'could not identify project repair loop lock'; mkdir "$staging" || fail 'repair loop staging collision'; mkdir "$tmp/attempts" || fail 'could not prepare repair loop scratch state'
loop_cleanup() { rm -rf "$staging" "$loop_lock" "$project_lock" "$tmp"; }
loop_interrupted() { runtime_emit repair_loop.interrupted repair-loop "$loop_id" interrupted "stopReason=interrupted" "" false || true; runtime_finish failed; loop_cleanup; trap - EXIT; exit 130; }
trap loop_cleanup EXIT; trap loop_interrupted INT TERM
runtime_init "$project_root" repair-loop || fail 'loop runtime audit initialization failed'; runtime_emit repair_loop.started repair-loop "$loop_id" started "requestedMaxIterations=2 hardMaxIterations=2 totalSeconds=900" "" false
cp -p "$project_root/$allow_path" "$tmp/original-input" || fail 'could not snapshot original loop input'; cp -p "$project_root/$allow_path" "$tmp/iteration-before"

measure_lines() { # before current; sets MEASURED_LINES and MEASUREMENT_OK
  local before="$1" current="$2" stats additions deletions; MEASURED_LINES=0; MEASUREMENT_OK=true
  [ -f "$current" ] && [ ! -L "$current" ] || { MEASUREMENT_OK=false; return; }
  stats="$(git diff --no-index --numstat -- "$before" "$current" 2>/dev/null || true)"; [ -n "$stats" ] || return
  additions="$(awk 'NR==1{print $1}' <<<"$stats")"; deletions="$(awk 'NR==1{print $2}' <<<"$stats")"
  if [[ "$additions" =~ ^[0-9]+$ ]] && [[ "$deletions" =~ ^[0-9]+$ ]]; then MEASURED_LINES=$((additions+deletions)); else MEASUREMENT_OK=false; fi
}
run_iteration() { # iteration baseline runner-seconds line-budget final output
  local iteration="$1" baseline="$2" seconds="$3" lines="$4" final="$5" output="$6" status=0
  runtime_emit repair_loop.iteration.started repair-loop "$loop_id" started "iteration=$iteration" "" false
  MANA_REPAIR_LOOP_ID="$loop_id" MANA_REPAIR_ITERATION="$iteration" MANA_REPAIR_FINAL_ATTEMPT="$final" MANA_REPAIR_RUNNER_SECONDS="$seconds" MANA_REPAIR_MAX_CHANGED_LINES="$lines" "$root/scripts/mana-repair.sh" --project-root "$project_root" --from "$baseline" --check "$check_id" --allow-path "$allow_path" --runner "$provider" --once --json > "$output" || status=$?
  return "$status"
}
resolve_evidence() { # reference digest; sets RESOLVED_FILE
  local ref="$1" expected="$2"; repair_safe_path "$ref" || return 1; RESOLVED_FILE="$project_root/$ref"; [ -f "$RESOLVED_FILE" ] && [ "$(verification_digest_file "$RESOLVED_FILE")" = "$expected" ]
}
append_attempt() { # result file iteration
  local result="$1" iteration="$2" comparison progress status stop ref digest before_ref before_digest after_ref after_digest
  comparison="$(jq -r .comparison "$result")"; progress="$(jq -r '.progress // empty' "$result")"; [ "$comparison" = RESOLVED ] && progress=complete; [ -n "$progress" ] || progress=null
  status="$(jq -r .attemptStatus "$result")"; stop="$(jq -r .stopReason "$result")"; ref="${result#"$project_root"/}"; digest="$(verification_digest_file "$result")"
  jq -n --argjson iteration "$iteration" --arg ref "$ref" --arg digest "$digest" --arg comparison "$comparison" --arg progress "$progress" --arg status "$status" --arg stop "$stop" '{iteration:$iteration,reference:$ref,digest:$digest,comparison:$comparison,progress:(if $progress=="null" then null else $progress end),attemptStatus:$status,stopReason:$stop}' > "$tmp/attempts/$iteration.json"
  before_ref="$(jq -r .beforeVerification.reference "$result")"; before_digest="$(jq -r .beforeVerification.digest "$result")"; after_ref="$(jq -r '.afterVerification.reference // empty' "$result")"; after_digest="$(jq -r '.afterVerification.digest // empty' "$result")"
  jq -n --argjson iteration "$iteration" --arg beforeRef "$before_ref" --arg beforeDigest "$before_digest" --arg afterRef "$after_ref" --arg afterDigest "$after_digest" '{iteration:$iteration,before:{reference:$beforeRef,digest:$beforeDigest},after:(if $afterRef=="" then null else {reference:$afterRef,digest:$afterDigest} end)}' > "$tmp/progression-$iteration.json"
}
map_stop() { # result second(true|false); prints reason
  local result="$1" second="$2" status comparison progress after_ref after_file check_result
  status="$(jq -r .attemptStatus "$result")"; comparison="$(jq -r .comparison "$result")"; progress="$(jq -r '.progress // empty' "$result")"
  case "$status" in policy_violation) echo policy_violation; return;; integrity_violation) echo integrity_violation; return;; runner_failed) echo runner_failed; return;; runner_timed_out) echo runner_timeout; return;; esac
  if [ "$comparison" = UNKNOWN ]; then
    after_ref="$(jq -r '.afterVerification.reference // empty' "$result")"; if [ -n "$after_ref" ] && repair_safe_path "$after_ref" && [ -f "$project_root/$after_ref" ]; then check_result="$(jq -r --arg id "$check_id" '.checks[]|select(.checkId==$id)|.result' "$project_root/$after_ref")"; [ "$check_result" = blocked ] && { echo verification_blocked; return; }; [ "$check_result" = inconclusive ] && { echo verification_inconclusive; return; }; fi
    echo comparison_unknown; return
  fi
  [ "$comparison" = RESOLVED ] && { echo target_resolved; return; }; [ "$comparison" = REGRESSED ] && { echo regressed; return; }
  if [ "$comparison" = UNCHANGED ]; then [ "$second" = true ] && echo hard_iteration_limit || { [ "$progress" = partial ] && echo comparison_unknown || echo no_progress; }; return; fi
  echo comparison_unknown
}

attempt1_capture="$tmp/attempt-1.json"; run_iteration 1 "$from" "$LOOP_ATTEMPT_SECONDS" "$LOOP_MAX_CHANGED_LINES" false "$attempt1_capture" || true
repair_attempt_validate "$attempt1_capture" || fail 'attempt one did not publish a valid immutable result'; attempt1_id="$(jq -r .attemptId "$attempt1_capture")"; attempt1_file="$workspace/evidence/repair/$attempt1_id/result.json"; [ -f "$attempt1_file" ] || fail 'attempt one reference is missing'; [ "$(verification_digest_file "$attempt1_capture")" = "$(verification_digest_file "$attempt1_file")" ] || fail 'attempt one output differs from canonical evidence'; target_ref="$(jq -r .target.reference "$attempt1_file")"; target_digest="$(jq -r .target.digest "$attempt1_file")"; resolve_evidence "$target_ref" "$target_digest" || fail 'attempt one Repair Target reference is missing or mismatched'; repair_target_validate "$RESOLVED_FILE" || fail 'attempt one Repair Target is invalid'; original_concern="$(jq -r .target.concernKey "$attempt1_file")"; append_attempt "$attempt1_file" 1
runtime_emit repair_loop.iteration.completed repair-loop "$loop_id" completed "iteration=1 comparison=$(jq -r .comparison "$attempt1_file")" "${attempt1_file#"$project_root"/}" false
attempts_executed=1; cumulative_invocations="$(jq -r .runner.invocationCount "$attempt1_file")"; verification_runs="$(jq -r .verificationRerunCount "$attempt1_file")"; final_result="$(jq -r .comparison "$attempt1_file")"; stop_reason="$(map_stop "$attempt1_file" false)"
measure_lines "$tmp/iteration-before" "$project_root/$allow_path"; first_lines="$MEASURED_LINES"; cumulative_lines="$first_lines"; can_continue=false

if [ "$(jq -r .attemptStatus "$attempt1_file")" = completed ] && [ "$final_result" = UNCHANGED ] && [ "$(jq -r .progress "$attempt1_file")" = partial ] && [ "$(jq '.scopeViolations|length' "$attempt1_file")" -eq 0 ] && [ "$(jq '.evaluationSurfaceChanges|length' "$attempt1_file")" -eq 0 ] && [ "$(jq '.comparabilityReasons|length' "$attempt1_file")" -eq 0 ] && [ "$(jq '.newRequiredFailures|length' "$attempt1_file")" -eq 0 ] && [ "$(jq '.newOptionalFailures|length' "$attempt1_file")" -eq 0 ] && [ "$MEASUREMENT_OK" = true ]; then
  before_ref="$(jq -r .beforeVerification.reference "$attempt1_file")"; before_digest="$(jq -r .beforeVerification.digest "$attempt1_file")"; after_ref="$(jq -r .afterVerification.reference "$attempt1_file")"; after_digest="$(jq -r .afterVerification.digest "$attempt1_file")"
  if resolve_evidence "$before_ref" "$before_digest"; then comparison_before="$RESOLVED_FILE"; else comparison_before=""; fi
  if resolve_evidence "$after_ref" "$after_digest"; then comparison_after="$RESOLVED_FILE"; else comparison_after=""; fi
  if [ -n "$comparison_before" ] && [ -n "$comparison_after" ] && [ "$(jq -r --arg id "$check_id" '.checks[]|select(.checkId==$id)|.concernKey' "$comparison_before")" = "$(jq -r --arg id "$check_id" '.checks[]|select(.checkId==$id)|.concernKey' "$comparison_after")" ]; then
    mechanical="$(repair_comparison_json "$comparison_before" "$comparison_after" "$check_id")"; [ "$(jq -r .comparison <<<"$mechanical")" = UNCHANGED ] && [ "$(jq -r .progress <<<"$mechanical")" = partial ] && can_continue=true
  fi
fi
if [ "$(jq -r .attemptStatus "$attempt1_file")" = completed ] && [ "$(jq -r .comparison "$attempt1_file")" = UNCHANGED ] && [ "$(jq -r .progress "$attempt1_file")" = partial ] && [ "$can_continue" != true ]; then final_result=UNKNOWN; stop_reason=comparison_unknown; fi

if [ "$can_continue" = true ]; then
  elapsed_ms=$(( $(loop_now_ms) - started_ms )); remaining_seconds=$(( LOOP_TOTAL_SECONDS - (elapsed_ms / 1000) - LOOP_SAFETY_SECONDS )); remaining_lines=$(( LOOP_MAX_CHANGED_LINES - first_lines ))
  if [ "$remaining_seconds" -lt 1 ]; then stop_reason=repair_loop_budget_exhausted
  elif [ "$remaining_lines" -lt 1 ]; then stop_reason=repair_loop_budget_exhausted
  else
    [ "$remaining_seconds" -le 600 ] || remaining_seconds=600; cp -p "$project_root/$allow_path" "$tmp/iteration-before-2" || { stop_reason=human_scope_required; remaining_seconds=0; }
    [ "$(verification_digest_file "$tmp/iteration-before-2" 2>/dev/null || true)" = "$(jq -r --arg id "$check_id" '.checks[]|select(.checkId==$id)|.inputDigest' "$comparison_after")" ] || { stop_reason=human_scope_required; remaining_seconds=0; }
    if [ "$remaining_seconds" -gt 0 ]; then
      attempt2_capture="$tmp/attempt-2.json"; run_iteration 2 "$comparison_after" "$remaining_seconds" "$remaining_lines" true "$attempt2_capture" || true
      repair_attempt_validate "$attempt2_capture" || fail 'attempt two did not publish a valid immutable result'; attempt2_id="$(jq -r .attemptId "$attempt2_capture")"; attempt2_file="$workspace/evidence/repair/$attempt2_id/result.json"; [ -f "$attempt2_file" ] || fail 'attempt two reference is missing'; [ "$(verification_digest_file "$attempt2_capture")" = "$(verification_digest_file "$attempt2_file")" ] || fail 'attempt two output differs from canonical evidence'; second_target_ref="$(jq -r .target.reference "$attempt2_file")"; second_target_digest="$(jq -r .target.digest "$attempt2_file")"; resolve_evidence "$second_target_ref" "$second_target_digest" || fail 'attempt two Repair Target reference is missing or mismatched'; repair_target_validate "$RESOLVED_FILE" || fail 'attempt two Repair Target is invalid'; append_attempt "$attempt2_file" 2
      runtime_emit repair_loop.iteration.completed repair-loop "$loop_id" completed "iteration=2 comparison=$(jq -r .comparison "$attempt2_file")" "${attempt2_file#"$project_root"/}" false
      attempts_executed=2; cumulative_invocations=$((cumulative_invocations+$(jq -r .runner.invocationCount "$attempt2_file"))); verification_runs=$((verification_runs+$(jq -r .verificationRerunCount "$attempt2_file"))); final_result="$(jq -r .comparison "$attempt2_file")"; stop_reason="$(map_stop "$attempt2_file" true)"
      measure_lines "$tmp/iteration-before-2" "$project_root/$allow_path"; if [ "$MEASUREMENT_OK" != true ]; then final_result=UNKNOWN; stop_reason=human_scope_required; else cumulative_lines=$((first_lines+MEASURED_LINES)); fi
      if [ "$(jq -r .target.concernKey "$attempt2_file")" != "$original_concern" ] || [ "$(jq -cS .allowedPaths "$attempt2_file")" != "$(printf '%s\n' "$allow_path" | verification_json_array_lines | jq -cS .)" ]; then final_result=UNKNOWN; stop_reason=human_scope_required; fi
      [ "$cumulative_lines" -le "$LOOP_MAX_CHANGED_LINES" ] || { final_result=UNKNOWN; stop_reason=policy_violation; }
      [ $(( ($(loop_now_ms) - started_ms) / 1000 )) -le "$LOOP_TOTAL_SECONDS" ] || { final_result=UNKNOWN; stop_reason=repair_loop_budget_exhausted; }
    fi
  fi
fi

attempts_json="$(jq -s 'sort_by(.iteration)' "$tmp/attempts"/*.json)"; progression_json="$(jq -s 'sort_by(.iteration)' "$tmp"/progression-*.json)"; concern="$(jq -r .target.concernKey "$attempt1_file")"; wall_ms=$(( $(loop_now_ms) - started_ms ))
jq -n --arg loop "$loop_id" --arg runtime "$MANA_RUNTIME_EXECUTION_ID" --arg targetRef "$target_ref" --arg targetDigest "$target_digest" --arg concern "$concern" --arg final "$final_result" --arg stop "$stop_reason" --arg path "$allow_path" --argjson attemptsExecuted "$attempts_executed" --argjson attempts "$attempts_json" --argjson progression "$progression_json" --argjson changedLines "$cumulative_lines" --argjson invocations "$cumulative_invocations" --argjson verificationRuns "$verification_runs" --argjson wall "$wall_ms" '{schemaVersion:"1",kind:"repair-loop-result",loopId:$loop,runtimeExecutionId:$runtime,target:{concernKey:$concern,reference:$targetRef,digest:$targetDigest},requestedMaxIterations:2,hardMaxIterations:2,attemptsExecuted:$attemptsExecuted,attempts:$attempts,verificationProgression:$progression,finalResult:$final,stopReason:$stop,cumulativeMutation:{allowedPaths:[$path],maxFiles:1,maxChangedLines:100,hardMaxChangedLines:500,changedLines:$changedLines},cost:{runnerInvocations:$invocations,verificationRuns:$verificationRuns,wallTimeMs:$wall,inputTokens:null,outputTokens:null},limitations:["At most two sequential repair_once invocations; no provider retry.","Cumulative changed lines are the sum of immediate per-attempt textual deltas for the one granted path."],judgment:null}' > "$staging/.result.json.tmp" || fail 'could not construct repair loop result'
repair_loop_result_validate "$staging/.result.json.tmp" || fail 'repair loop result failed strict canonical validation'; repair_loop_result_validate_context "$staging/.result.json.tmp" "$project_root" || fail 'repair loop result did not reconcile immutable attempt evidence'; mv "$staging/.result.json.tmp" "$staging/result.json" || fail 'could not finalize repair loop result'
{ echo '# Mana Bounded Repair Loop'; echo; echo "- Loop: \`$loop_id\`"; echo "- Attempts: \`$attempts_executed\` / \`2\`"; echo "- Final result: \`$final_result\`"; echo "- Stop reason: \`$stop_reason\`"; echo; echo '## Attempts'; jq -r '.attempts[]|"- Iteration "+(.iteration|tostring)+": `"+.comparison+"`; progress `"+(.progress//"none")+"`; `"+.reference+"`."' "$staging/result.json"; echo; echo 'UNKNOWN means STOP. RESOLVED is not merge readiness, correctness, approval, or production safety.'; } > "$staging/summary.md"
chmod 600 "$staging/result.json" "$staging/summary.md" || fail 'could not protect repair loop evidence'; [ ! -e "$final_dir" ] || fail 'repair loop identity collision'; mv "$staging" "$final_dir" || fail 'could not atomically publish repair loop evidence'
runtime_emit repair_loop.stopped repair-loop "$loop_id" stopped "attempts=$attempts_executed comparison=$final_result stopReason=$stop_reason" "${workspace_reference}/evidence/repair-loop/$loop_id/result.json" false; runtime_emit repair_loop.completed repair-loop "$loop_id" completed "attempts=$attempts_executed comparison=$final_result" "${workspace_reference}/evidence/repair-loop/$loop_id/result.json" false; runtime_finish completed
rm -rf "$loop_lock"; "$root/scripts/run-evidence-index.sh" --project-root "$project_root" --workspace "$workspace" >/dev/null 2>&1 || true
if [ "$json" = true ]; then cat "$final_dir/result.json"; else echo 'MANA BOUNDED REPAIR LOOP'; echo "attempts: $attempts_executed"; echo "final result: $final_result"; echo "stop reason: $stop_reason"; echo "evidence: ${workspace_reference}/evidence/repair-loop/$loop_id/result.json"; fi
[ "$final_result" = RESOLVED ]
