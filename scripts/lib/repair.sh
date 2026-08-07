#!/usr/bin/env bash
# Strict deterministic contracts for the one-attempt bounded repair primitive.

MANA_REPAIR_MAX_RUNNER_SECONDS="${MANA_REPAIR_RUNNER_SECONDS:-600}"
MANA_REPAIR_MAX_STREAM_BYTES=65536
MANA_REPAIR_DEFAULT_MAX_FILES=1
MANA_REPAIR_HARD_MAX_FILES=5
MANA_REPAIR_DEFAULT_MAX_CHANGED_LINES="${MANA_REPAIR_MAX_CHANGED_LINES:-100}"
MANA_REPAIR_HARD_MAX_CHANGED_LINES=500
MANA_REPAIR_MAX_CONTRACT_BYTES=8192
[ "$MANA_REPAIR_MAX_RUNNER_SECONDS" -ge 1 ] 2>/dev/null && [ "$MANA_REPAIR_MAX_RUNNER_SECONDS" -le 600 ] 2>/dev/null || MANA_REPAIR_MAX_RUNNER_SECONDS=600
[ "$MANA_REPAIR_DEFAULT_MAX_CHANGED_LINES" -ge 1 ] 2>/dev/null && [ "$MANA_REPAIR_DEFAULT_MAX_CHANGED_LINES" -le 100 ] 2>/dev/null || MANA_REPAIR_DEFAULT_MAX_CHANGED_LINES=100

repair_json_no_duplicate_keys() {
  [ -z "$(jq --stream -r 'select(length==2) | .[0] | @json' "$1" 2>/dev/null | LC_ALL=C sort | uniq -d)" ]
}

repair_safe_path() { verification_safe_repository_path "$1"; }

repair_target_validate() {
  repair_json_no_duplicate_keys "$1" || return 1
  jq -e '
    def ke($x):(keys|sort)==($x|sort); def d:type=="string" and test("^sha256:[0-9a-f]{64}$");
    def p:type=="string" and length>0 and (startswith("/")|not) and (contains("\\")|not) and (test("(^|/)\\.\\.?(/|$)")|not) and (test("[\\t\\n]")|not);
    type=="object" and ke(["concernKey","createdAt","executionPlan","failure","kind","mode","mutationGrant","origin","rerunIdentity","schemaVersion","skill","target","targetId","workspaceContext"]) and
    .schemaVersion=="1" and .kind=="repair-target" and .mode=="implementation" and
    (.targetId|test("^repair-target-sha256-[0-9a-f]{64}$")) and
    (.concernKey|test("^concern:[a-z0-9][a-z0-9-]*:[a-z0-9][a-z0-9-]*:sha256:[0-9a-f]{64}$")) and
    (.origin|ke(["checkId","resultDigest","resultReference","runId"]) and (.resultDigest|d) and (.resultReference|p) and (.runId|test("^verification-[A-Za-z0-9._-]+$"))) and
    (.skill|ke(["id","specDigest","version"]) and (.specDigest|d)) and
    (.target|ke(["inputDigest","rerunDescriptor","targetFingerprint"]) and (.inputDigest|d) and (.targetFingerprint|d) and (.rerunDescriptor|ke(["kind","path"]) and .kind=="repository_path" and (.path|p))) and
    (.failure|ke(["failureFingerprint","observations"]) and (.failureFingerprint|d) and (.observations|type=="array")) and
    (.rerunIdentity|ke(["adapter","adapterImplementationDigest","environmentClassification","environmentDigest","executableDigest","executablePath"]) and .adapter=="bash_syntax" and (.adapterImplementationDigest|d) and (.environmentDigest|d) and (.executableDigest|d)) and
    (.mutationGrant|ke(["allowedPaths","grantDigest","hardMaxChangedLines","hardMaxFiles","maxChangedLines","maxFiles"]) and (.allowedPaths|type=="array" and length==1 and all(.[];p)) and (.grantDigest|d) and .maxFiles==1 and .hardMaxFiles==5 and (.maxChangedLines|type=="number" and .>=1 and .<=100 and floor==.) and .hardMaxChangedLines==500) and
    (.workspaceContext|ke(["projectIdentity","workspaceReference"]) and (.projectIdentity|d) and (.workspaceReference|p)) and
    (.executionPlan|ke(["identity","mode","runnerInvocations","subagents"]) and (.identity|d) and .mode=="implementation" and .runnerInvocations==1 and .subagents==false)
  ' "$1" >/dev/null
}

repair_attempt_validate() {
  repair_json_no_duplicate_keys "$1" || return 1
  jq -e '
    def ke($x):(keys|sort)==($x|sort); def d:type=="string" and (test("^sha256:[0-9a-f]{64}$") or .=="unavailable"); def p:type=="string" and length>0 and (startswith("/")|not) and (test("(^|/)\\.\\.?(/|$)")|not);
    type=="object" and ke(["actualMutatedPaths","afterVerification","allowedPaths","attemptId","attemptStatus","beforeVerification","candidate","comparabilityReasons","comparison","evaluationSurfaceChanges","executionPlanIdentity","import","isolation","judgment","kind","limitations","newOptionalFailures","newRequiredFailures","patchDigest","persistentFailures","progress","protectedSurfaceDigest","provider","resolvedFailures","runner","runtimeExecutionId","schemaVersion","scopeViolations","stopReason","target","verificationRerunCount","wallTimeMs"]) and
    .schemaVersion=="1" and .kind=="repair-attempt-result" and (.attemptId|test("^repair-attempt-[A-Za-z0-9._-]+$")) and .judgment==null and
    (.comparison|IN("RESOLVED","UNCHANGED","REGRESSED","UNKNOWN")) and (.attemptStatus|IN("completed","policy_violation","integrity_violation","runner_failed","runner_timed_out","verification_failed","interrupted")) and
    (.target|ke(["concernKey","digest","reference","targetId"]) and (.digest|d) and (.reference|p)) and
    (.runner|ke(["descendantsTerminated","exitCode","fingerprint","inputTokens","invocationCount","outputTokens","signal","timedOut"]) and (.fingerprint|d) and .invocationCount==1 and (.timedOut|type=="boolean")) and
    (.isolation|ke(["adversarialBoundary","backend","capability","hostFilesystemIsolation","hostPatchImport","liveRepositoryProviderAccess","networkIsolation","processIsolation"]) and .capability=="faulty-contained" and .backend=="disposable-workspace" and .adversarialBoundary==false and .liveRepositoryProviderAccess==false and .hostPatchImport==true and .processIsolation==false and .hostFilesystemIsolation==false and .networkIsolation==false) and
    (.candidate|ke(["candidateDigest","changedLineCount","changedPaths","policyViolations","workspaceIdentity","workspaceIntegrity"]) and (.workspaceIdentity|d) and (.workspaceIntegrity|type=="boolean") and (.changedPaths|type=="array" and all(.[];p)) and (.candidateDigest|d) and (.changedLineCount|type=="number" and .>=0 and floor==.) and (.policyViolations|type=="array" and all(.[];type=="string"))) and
    (.import|ke(["applied","baselineContentDigest","baselineDigest","baselineMode","baselineType","evaluationSurfaceDigest","importedDigest","liveBaselineMatched","repairTargetId","workingTreeState"]) and (.baselineDigest|d) and (.baselineContentDigest|d) and .baselineType=="regular" and (.baselineMode|type=="string" and test("^[0-7]{3,4}$")) and (.workingTreeState|IN("clean","modified","untracked")) and (.evaluationSurfaceDigest|d) and (.liveBaselineMatched|IN(true,false,null)) and (.applied|type=="boolean") and (.importedDigest==null or (.importedDigest|d)) and (if .applied then .liveBaselineMatched==true and .importedDigest!=null else true end)) and
    (.allowedPaths|type=="array" and all(.[];p)) and (.actualMutatedPaths|type=="array" and all(.[];p)) and (.scopeViolations|type=="array" and all(.[];p)) and
    (.beforeVerification|ke(["digest","reference"]) and (.digest|d) and (.reference|p)) and
    (.afterVerification==null or (.afterVerification|ke(["digest","reference"]) and (.digest|d) and (.reference|p))) and
    (.verificationRerunCount|IN(0,1)) and (.wallTimeMs|type=="number" and .>=0) and
    (if .progress=="partial" then .attemptStatus=="completed" and .comparison=="UNCHANGED" and .afterVerification!=null and (.scopeViolations|length)==0 and (.evaluationSurfaceChanges|length)==0 and (.comparabilityReasons|length)==0 and (.resolvedFailures|length)>0 and (.newRequiredFailures|length)==0 and (.newOptionalFailures|length)==0 else true end) and
    (.candidate.changedPaths==.actualMutatedPaths) and
    (if .attemptStatus!="completed" then .comparison=="UNKNOWN" and .progress==null else true end) and
    (if (.attemptStatus|IN("policy_violation","integrity_violation","runner_failed","runner_timed_out")) then .verificationRerunCount==0 else true end)
  ' "$1" >/dev/null
}

repair_loop_result_validate() {
  repair_json_no_duplicate_keys "$1" || return 1
  jq -e '
    def ke($x):(keys|sort)==($x|sort); def d:type=="string" and test("^sha256:[0-9a-f]{64}$");
    def p:type=="string" and length>0 and (startswith("/")|not) and (contains("\\")|not) and (test("(^|/)\\.\\.?(/|$)")|not) and (test("[\\t\\n]")|not);
    def evidence: type=="object" and ke(["digest","reference"]) and (.digest|d) and (.reference|p);
    .attemptsExecuted as $attemptCount |
    type=="object" and ke(["attempts","attemptsExecuted","cost","cumulativeMutation","finalResult","hardMaxIterations","judgment","kind","limitations","loopId","requestedMaxIterations","runtimeExecutionId","schemaVersion","stopReason","target","verificationProgression"]) and
    .schemaVersion=="1" and .kind=="repair-loop-result" and (.loopId|test("^repair-loop-[A-Za-z0-9._-]+$")) and
    .requestedMaxIterations==2 and .hardMaxIterations==2 and (.attemptsExecuted|IN(1,2)) and .attemptsExecuted==(.attempts|length) and
    (.runtimeExecutionId|test("^execution-[A-Za-z0-9._-]+$")) and
    (.target|type=="object" and ke(["concernKey","digest","reference"]) and (.concernKey|test("^concern:[a-z0-9][a-z0-9-]*:[a-z0-9][a-z0-9-]*:sha256:[0-9a-f]{64}$")) and (.digest|d) and (.reference|p)) and
    (.attempts|type=="array" and all(.[]; type=="object" and ke(["attemptStatus","comparison","digest","iteration","progress","reference","stopReason"]) and (.iteration|IN(1,2)) and (.reference|p) and (.digest|d) and (.comparison|IN("RESOLVED","UNCHANGED","REGRESSED","UNKNOWN")) and (.progress|IN("partial","complete",null)))) and
    ([.attempts[].iteration]|sort)==([range(1;$attemptCount+1)]) and
    (.verificationProgression|type=="array" and length==$attemptCount and all(.[]; type=="object" and ke(["after","before","iteration"]) and (.iteration|IN(1,2)) and (.before|evidence) and (.after==null or (.after|evidence)))) and
    (.finalResult|IN("RESOLVED","UNCHANGED","REGRESSED","UNKNOWN")) and
    (.stopReason|IN("target_resolved","no_progress","regressed","comparison_unknown","policy_violation","integrity_violation","runner_failed","runner_timeout","verification_blocked","verification_inconclusive","repair_loop_budget_exhausted","hard_iteration_limit","human_scope_required","interrupted")) and
    (.cumulativeMutation|type=="object" and ke(["allowedPaths","changedLines","hardMaxChangedLines","maxChangedLines","maxFiles"]) and .maxFiles==1 and .maxChangedLines==100 and .hardMaxChangedLines==500 and (.changedLines|type=="number" and .>=0 and floor==.) and (.allowedPaths|type=="array" and length==1 and all(.[];p))) and
    (.cost|type=="object" and ke(["inputTokens","outputTokens","runnerInvocations","verificationRuns","wallTimeMs"]) and (.runnerInvocations|IN(1,2)) and (.verificationRuns|type=="number" and .>=0 and .<=2 and floor==.) and (.wallTimeMs|type=="number" and .>=0 and floor==.) and .inputTokens==null and .outputTokens==null) and
    (.limitations|type=="array") and .judgment==null
  ' "$1" >/dev/null
}

repair_loop_result_validate_context() {
  # Schema validation intentionally has no filesystem authority.  Consumers of
  # a published loop must additionally resolve every immutable reference and
  # reconcile its duplicated summary fields before trusting the aggregate.
  local result="$1" project="$2" ref digest attempt target_ref target_digest iteration invocations=0 reruns=0
  [ "${MANA_REPAIR_DEBUG_CONTEXT:-false}" = true ] && set -x
  repair_loop_result_validate "$result" || return 1
  project="$(cd "$project" 2>/dev/null && pwd -P)" || return 1
  ref="$(jq -r .target.reference "$result")"; digest="$(jq -r .target.digest "$result")"
  repair_safe_path "$ref" || return 1
  [ -f "$project/$ref" ] && [ "$(verification_digest_file "$project/$ref")" = "$digest" ] || return 1
  repair_target_validate "$project/$ref" || return 1
  while IFS= read -r attempt; do
    ref="$(jq -r .reference <<<"$attempt")"; digest="$(jq -r .digest <<<"$attempt")"; iteration="$(jq -r .iteration <<<"$attempt")"
    repair_safe_path "$ref" || return 1
    [ -f "$project/$ref" ] && [ "$(verification_digest_file "$project/$ref")" = "$digest" ] || return 1
    repair_attempt_validate "$project/$ref" || return 1
    invocations=$((invocations + $(jq -r .runner.invocationCount "$project/$ref")))
    reruns=$((reruns + $(jq -r .verificationRerunCount "$project/$ref")))
    [ "$(jq -r .comparison <<<"$attempt")" = "$(jq -r .comparison "$project/$ref")" ] || return 1
    expected_progress="$(jq -r '.progress // "null"' "$project/$ref")"; [ "$(jq -r .comparison "$project/$ref")" = RESOLVED ] && expected_progress=complete
    [ "$(jq -r '.progress // "null"' <<<"$attempt")" = "$expected_progress" ] || return 1
    [ "$(jq -r .attemptStatus <<<"$attempt")" = "$(jq -r .attemptStatus "$project/$ref")" ] || return 1
    [ "$(jq -r .stopReason <<<"$attempt")" = "$(jq -r .stopReason "$project/$ref")" ] || return 1
    [ "$(jq -r .target.concernKey "$project/$ref")" = "$(jq -r .target.concernKey "$result")" ] || return 1
    target_ref="$(jq -r .target.reference "$project/$ref")"; target_digest="$(jq -r .target.digest "$project/$ref")"
    repair_safe_path "$target_ref" || return 1
    [ -f "$project/$target_ref" ] && [ "$(verification_digest_file "$project/$target_ref")" = "$target_digest" ] || return 1
    repair_target_validate "$project/$target_ref" || return 1
    [ "$(jq -r .targetId "$project/$target_ref")" = "$(jq -r .target.targetId "$project/$ref")" ] || return 1
    [ "$(jq -r --argjson i "$iteration" '.verificationProgression[]|select(.iteration==$i)|.before.reference' "$result")" = "$(jq -r .beforeVerification.reference "$project/$ref")" ] || return 1
    [ "$(jq -r --argjson i "$iteration" '.verificationProgression[]|select(.iteration==$i)|.before.digest' "$result")" = "$(jq -r .beforeVerification.digest "$project/$ref")" ] || return 1
    [ "$(jq -r --argjson i "$iteration" '.verificationProgression[]|select(.iteration==$i)|(.after.reference // "null")' "$result")" = "$(jq -r '(.afterVerification.reference // "null")' "$project/$ref")" ] || return 1
    [ "$(jq -r --argjson i "$iteration" '.verificationProgression[]|select(.iteration==$i)|(.after.digest // "null")' "$result")" = "$(jq -r '(.afterVerification.digest // "null")' "$project/$ref")" ] || return 1
  done < <(jq -c '.attempts[]' "$result")
  [ "$(jq '[.attempts[]] | length' "$result")" = "$(jq -r .attemptsExecuted "$result")" ] || return 1
  [ "$invocations" = "$(jq -r .cost.runnerInvocations "$result")" ] || return 1
  [ "$reruns" = "$(jq -r .cost.verificationRuns "$result")" ] || return 1
  [ "${MANA_REPAIR_DEBUG_CONTEXT:-false}" = true ] && set +x
  return 0
}

repair_comparison_json() {
  local before="$1" after="$2" check_id="$3"
  jq -n --arg id "$check_id" --slurpfile b "$before" --slurpfile a "$after" '
    ($b[0].checks[]|select(.checkId==$id)) as $before | ($a[0].checks[]|select(.checkId==$id)) as $after |
    # Observations are verifier-defined canonical atoms.  bash_syntax emits
    # only normalized parser-error headlines (or one opaque atom), so raw
    # stderr ordering, paths, columns, excerpts and whitespace cannot qualify
    # an attempt for retry.
    def negatives:
      [ .observations[] | select(.result=="not_satisfied") |
        .id as $id | if ((.messages // [])|length)>0 then .messages[] | {id:$id,message:.} else {id:$id,message:null} end ] | unique | sort_by(.id,.message);
    ($before|negatives) as $old | ($after|negatives) as $new |
    if $after.result=="passed" then {comparison:"RESOLVED",progress:null,resolvedFailures:$old,persistentFailures:[],newRequiredFailures:[],newOptionalFailures:[],reasons:[]}
    elif $after.result!="failed" then {comparison:"UNKNOWN",progress:null,resolvedFailures:[],persistentFailures:[],newRequiredFailures:[],newOptionalFailures:[],reasons:["after_verification_not_mechanical"]}
    elif $old==$new then {comparison:"UNCHANGED",progress:null,resolvedFailures:[],persistentFailures:$old,newRequiredFailures:[],newOptionalFailures:[],reasons:[]}
    elif (($new-$old)|length)>0 then {comparison:"REGRESSED",progress:null,resolvedFailures:($old-$new),persistentFailures:[$old[] as $x | select(any($new[]; .==$x)) | $x],newRequiredFailures:($new-$old),newOptionalFailures:[],reasons:[]}
    elif (($new-$old)|length)==0 and ($new|length)<($old|length) then {comparison:"UNCHANGED",progress:"partial",resolvedFailures:($old-$new),persistentFailures:$new,newRequiredFailures:[],newOptionalFailures:[],reasons:[]}
    else {comparison:"REGRESSED",progress:null,resolvedFailures:$old,persistentFailures:[],newRequiredFailures:$new,newOptionalFailures:[],reasons:[]} end
  '
}
