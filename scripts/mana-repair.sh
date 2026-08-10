#!/usr/bin/env bash
# One bounded evidence-driven repair attempt, with an explicit handoff to the
# separate thin two-attempt governor when --max-iterations 2 is requested.
set -u

root="$(cd "$(dirname "$0")/.." && pwd)"
. "$root/scripts/lib/verification.sh"
. "$root/scripts/lib/repair.sh"
. "$root/scripts/lib/repair-containment.sh"
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/runtime-events.sh"

project_root="$(pwd)"; from=""; check_id=""; allow_path=""; provider=""; once=false; max_iterations=1; max_iterations_set=false; dry_run=false; explain=false; json=false
usage() { cat <<'USAGE'
Usage: mana repair --from <verification-result.json> [--check <id>]
       --allow-path <repository-relative-file> --runner <codex|claude|opencode>
       [--max-iterations <1|2>] [--dry-run] [--explain] [--json]

Defaults to exactly one bounded implementation repair attempt. --once and
--max-iterations 1 preserve that behavior. An explicit --max-iterations 2
permits a final second repair_once invocation only after mechanically proven
partial progress. Automatic eligibility remains limited to
shell-syntax-verification/bash_syntax failures.
USAGE
}
fail() { echo "ERROR: $*" >&2; exit 2; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || fail '--project-root requires a path'; shift 2 ;;
    --from) from="${2:-}"; [ -n "$from" ] || fail '--from requires a path'; shift 2 ;;
    --check) check_id="${2:-}"; [ -n "$check_id" ] || fail '--check requires an id'; shift 2 ;;
    --allow-path) allow_path="${2:-}"; [ -n "$allow_path" ] || fail '--allow-path requires an exact path'; shift 2 ;;
    --runner) provider="${2:-}"; [ -n "$provider" ] || fail '--runner requires a provider'; shift 2 ;;
    --once) once=true; shift ;;
    --max-iterations) max_iterations="${2:-}"; max_iterations_set=true; shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    --explain) explain=true; shift ;;
    --json) json=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done
command -v jq >/dev/null 2>&1 || fail 'jq is required for mana repair'
[ "${MANA_REPAIR_RUNNING:-}" != 1 ] || fail 'nested Mana repair is prohibited while a provider repair invocation is active'
[ -n "$from" ] || fail '--from is required'; [ -n "$allow_path" ] || fail '--allow-path is required'; [ -n "$provider" ] || fail '--runner is required'
[[ "$max_iterations" =~ ^[0-9]+$ ]] || fail '--max-iterations must be 1 or 2'; [ "$max_iterations" -ge 1 ] && [ "$max_iterations" -le 2 ] || fail '--max-iterations must be between 1 and the hard limit 2'
[ "$once" != true ] || [ "$max_iterations_set" != true ] || [ "$max_iterations" -eq 1 ] || fail '--once cannot be combined with --max-iterations 2'
[ "$once" != true ] || max_iterations=1
loop_context_id="${MANA_REPAIR_LOOP_ID:-}"; loop_iteration="${MANA_REPAIR_ITERATION:-1}"; loop_final="${MANA_REPAIR_FINAL_ATTEMPT:-false}"
if [ -n "$loop_context_id" ]; then [[ "$loop_context_id" =~ ^repair-loop-[A-Za-z0-9._-]+$ ]] || fail 'invalid internal repair loop identity'; [[ "$loop_iteration" =~ ^[12]$ ]] || fail 'invalid internal repair loop iteration'; case "$loop_final" in true|false) ;; *) fail 'invalid internal final-attempt marker';; esac; [ "$loop_iteration" != 2 ] || [ "$loop_final" = true ] || fail 'iteration two must be marked as the final attempt'; fi
project_root="$(cd "$project_root" 2>/dev/null && pwd -P)" || fail "project root not found: $project_root"
if [ -d "$project_root/.mana/.repair-loop.lock" ]; then
  [ -n "$loop_context_id" ] && [ "$(sed -n '1p' "$project_root/.mana/.repair-loop.lock/id" 2>/dev/null)" = "$loop_context_id" ] || fail 'a bounded repair loop owns this repository'
fi
repair_safe_path "$allow_path" || fail '--allow-path must be one exact safe repository-relative path (no absolute path, traversal, glob, or directory)'
case "$allow_path" in *'*'*|*'?'*|'['*|*'['*) fail '--allow-path does not accept globs' ;; esac
[ -f "$from" ] || fail "verification evidence not found: $from"
from="$(cd "$(dirname "$from")" && pwd -P)/$(basename "$from")"
case "$from" in "$project_root"/.mana/*/evidence/verification/*/result.json) ;; *) fail '--from must reference canonical project-local verification evidence' ;; esac

if [ "$max_iterations" -eq 2 ]; then
  loop_args=(--project-root "$project_root" --from "$from" --allow-path "$allow_path" --runner "$provider" --max-iterations 2)
  [ -n "$check_id" ] && loop_args+=(--check "$check_id"); [ "$dry_run" = true ] && loop_args+=(--dry-run); [ "$explain" = true ] && loop_args+=(--explain); [ "$json" = true ] && loop_args+=(--json)
  exec "$root/scripts/mana-repair-loop.sh" "${loop_args[@]}"
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-repair.XXXXXX")"; cleanup() { rm -rf "$tmp"; }; trap cleanup EXIT
eligibility=eligible; eligibility_reason="eligible for one deterministic shell-syntax repair attempt"
if ! repair_json_no_duplicate_keys "$from" || ! verification_result_validate "$from"; then eligibility=blocked; eligibility_reason='verification evidence is malformed, non-canonical, or contains duplicate keys'
elif [ "$(jq -r .schemaVersion "$from")" != 2 ]; then eligibility=not_repairable; eligibility_reason='verification evidence predates repair-capable schema; rerun verification first'
fi
from_digest="$(verification_digest_file "$from")"
if [ "$eligibility" = eligible ] && { [ ! -f "$(dirname "$from")/result.sha256" ] || [ "$(sed -n '1p' "$(dirname "$from")/result.sha256")" != "$from_digest" ]; }; then eligibility=blocked; eligibility_reason='verification evidence integrity digest is missing or mismatched'; fi

if [ "$eligibility" = eligible ]; then
  failed_count="$(jq '[.checks[]|select(.result=="failed")]|length' "$from")"
  if [ -z "$check_id" ]; then
    if [ "$failed_count" -eq 1 ]; then check_id="$(jq -r '.checks[]|select(.result=="failed")|.checkId' "$from")"
    else eligibility=requires_human; eligibility_reason='multiple or zero failed checks require explicit --check selection'; fi
  fi
fi
if [ "$eligibility" = eligible ]; then
  selected_count="$(jq --arg id "$check_id" '[.checks[]|select(.checkId==$id)]|length' "$from")"
  [ "$selected_count" = 1 ] || { eligibility=blocked; eligibility_reason='selected check is missing or ambiguous in originating evidence'; }
fi
if [ "$eligibility" = eligible ]; then
  check_json="$(jq -c --arg id "$check_id" '.checks[]|select(.checkId==$id)' "$from")"
  adapter="$(jq -r .adapter <<<"$check_json")"; skill_id="$(jq -r .skillId <<<"$check_json")"
  if [ "$adapter" != bash_syntax ] || [ "$skill_id" != shell-syntax-verification ]; then eligibility=requires_human; eligibility_reason="automatic repair is unsupported for $skill_id/$adapter; human repair is required"; fi
fi
if [ "$eligibility" = eligible ]; then
  descriptor_kind="$(jq -r .rerunDescriptor.kind <<<"$check_json")"; target_path="$(jq -r .rerunDescriptor.path <<<"$check_json")"
  if [ "$descriptor_kind" != repository_path ] || ! repair_safe_path "$target_path"; then eligibility=blocked; eligibility_reason='structured rerun descriptor is unsafe or unsupported'
  elif [ "$target_path" != "$allow_path" ]; then eligibility=blocked; eligibility_reason='explicit mutation grant does not exactly match the inferred repair target'
  elif [ ! -f "$project_root/$target_path" ] || [ -L "$project_root/$target_path" ]; then eligibility=blocked; eligibility_reason='repair target is missing, not a regular file, or is a symlink'
  fi
fi
if [ "$eligibility" = eligible ]; then
  target_parent="${target_path%/*}"; [ "$target_parent" != "$target_path" ] || target_parent=.
  canonical_parent="$(cd "$project_root/$target_parent" 2>/dev/null && pwd -P)" || canonical_parent=unavailable
  expected_parent="$project_root"; [ "$target_parent" = . ] || expected_parent="$project_root/$target_parent"
  target_index_mode="$(git -C "$project_root" ls-files -s -- "$target_path" 2>/dev/null | awk 'NR==1{print $1}')"
  if [ "$canonical_parent" != "$expected_parent" ] || [ ! -f "$canonical_parent/$(basename "$target_path")" ] || [ -L "$canonical_parent/$(basename "$target_path")" ]; then
    eligibility=blocked; eligibility_reason='repair target cannot be resolved unambiguously as a regular file beneath the project root'
  elif [ "$target_index_mode" = 160000 ]; then
    eligibility=blocked; eligibility_reason='repair target is a submodule and cannot be repaired automatically'
  elif ! repair_supported_text_file "$project_root/$target_path"; then
    eligibility=blocked; eligibility_reason='repair target is not a supported regular text file'
  fi
fi
if [ "$eligibility" = eligible ]; then
  if [ "$(jq -r .result <<<"$check_json")" != failed ] || [ "$(jq -r .required <<<"$check_json")" != true ]; then eligibility=not_repairable; eligibility_reason='selected check must be required and exactly failed'
  elif [ "$(jq --arg skill "$skill_id" '[.selections[]|select(.skillId==$skill and .selected==true and .applicability=="applicable")]|length' "$from")" != 1 ]; then eligibility=blocked; eligibility_reason='originating required check is not owned by one selected applicable skill'
  elif [ "$(jq -r .trustOrigin <<<"$check_json")" != framework_declared ] || [ "$(jq -r .commandOrigin <<<"$check_json")" = repository_script ]; then eligibility=requires_human; eligibility_reason='repository-script-backed or non-framework-declared checks require human repair'
  elif [ "$(jq -r .timedOut <<<"$check_json")" != false ] || [ "$(jq -r .descendantsTerminated <<<"$check_json")" != false ]; then eligibility=blocked; eligibility_reason='timed-out or descendant-containment evidence is not repairable'
  elif [ "$(jq -r .observedEffects.unexpectedSourceMutation <<<"$check_json")" != false ] || [ "$(jq -r .observedEffects.unexpectedSourceMutation "$from")" != false ]; then eligibility=blocked; eligibility_reason='originating verifier unexpectedly mutated source'
  elif [ "$(jq -r '.output.stdoutTruncated or .output.stderrTruncated' <<<"$check_json")" = true ]; then eligibility=requires_human; eligibility_reason='materially truncated failure evidence requires human interpretation'
  elif [ "$(jq '.limitations|length' <<<"$check_json")" -ne 0 ]; then eligibility=requires_human; eligibility_reason='verification limitations make automatic repair confidence insufficient'
  elif ! jq -e --arg path "$target_path" '(.evaluationSurface|map(select(.role=="mutable_input" and .path==$path and .protected==false))|length)==1 and (.evaluationSurface|map(select(.role=="oracle" and .protected==true))|length)==1 and (.evaluationSurface|map(select(.role=="verifier" and .protected==true))|length)==1' <<<"$check_json" >/dev/null; then eligibility=blocked; eligibility_reason='evaluation surface is not adequately described for automatic shell repair'
  fi
fi

if [ "$eligibility" = eligible ]; then
  skill_file="$root/skills/$skill_id/SKILL.md"; spec_file="$root/skills/$skill_id/verification.yaml"
  current_version="$(verification_frontmatter_field "$skill_file" version)"; current_spec_digest="$(verification_digest_file "$spec_file")"
  current_adapter_digest="$(cat "$root/scripts/mana-verify.sh" "$root/scripts/lib/verification.sh" | verification_digest_text)"
  bash_path="$(command -v bash 2>/dev/null || true)"; current_executable_digest="$([ -f "$bash_path" ] && verification_digest_file "$bash_path" || printf unavailable)"; current_environment_digest="$(verification_environment_digest)"
  current_target_fingerprint="$(verification_target_fingerprint bash_syntax "$(jq -cn --arg path "$target_path" '["bash","-n","--",$path]')" "$project_root" "$(jq -r .scope <<<"$check_json")")"
  if [ "$current_version" != "$(jq -r .skillVersion <<<"$check_json")" ] || [ "$current_spec_digest" != "$(jq -r .specDigest <<<"$check_json")" ] || [ "$current_adapter_digest" != "$(jq -r .adapterImplementationDigest <<<"$check_json")" ] || [ "$current_target_fingerprint" != "$(jq -r .targetFingerprint <<<"$check_json")" ]; then eligibility=blocked; eligibility_reason='current skill, verification spec, adapter, or target identity differs from originating evidence'
  elif [ "$current_executable_digest" != "$(jq -r .executable.digest <<<"$check_json")" ] || [ "$current_environment_digest" != "$(jq -r .environmentDigest <<<"$check_json")" ]; then eligibility=blocked; eligibility_reason='current executable or environment identity differs from originating evidence'
  elif [ "$(verification_digest_file "$project_root/$target_path")" != "$(jq -r .inputDigest <<<"$check_json")" ]; then eligibility=blocked; eligibility_reason='repair target no longer matches the originating failed input baseline'
  fi
fi

workspace="${from%%/evidence/verification/*}"; workspace_reference="${workspace#"$project_root"/}"; from_reference="${from#"$project_root"/}"
protected_manifest="$tmp/protected.jsonl"; : > "$protected_manifest"
add_protected() { local label="$1" file="$2"; [ -e "$file" ] || return 0; local digest; if [ -L "$file" ]; then digest="$(readlink "$file" | verification_digest_text)"; elif [ -f "$file" ]; then digest="$(verification_digest_file "$file")"; else digest=unavailable; fi; jq -cn --arg label "$label" --arg file "$file" --arg digest "$digest" '{label:$label,file:$file,digest:$digest}' >> "$protected_manifest"; }
if [ "$eligibility" = eligible ]; then
  add_protected verifier "$root/scripts/mana-verify.sh"; add_protected verifier-library "$root/scripts/lib/verification.sh"; add_protected oracle "$spec_file"; add_protected skill "$skill_file"; add_protected evidence "$from"; add_protected evidence-digest "$(dirname "$from")/result.sha256"
  for protected in .gitignore .gitattributes .gitmodules .mana/active-workspace .mana/global/engineering-guards.md .mana/global/testing-policy.md .mana/global/hooks-config.yaml; do add_protected "$protected" "$project_root/$protected"; done
  protected_surface="$(jq -s 'sort_by(.label,.file)|map({label,digest})' "$protected_manifest")"; protected_digest="$(printf '%s' "$protected_surface" | verification_digest_text)"
  concern_key="$(jq -r .concernKey <<<"$check_json")"; target_fingerprint="$(jq -r .targetFingerprint <<<"$check_json")"; failure_fingerprint="$(jq -r .failureFingerprint <<<"$check_json")"
  grant_digest="$(printf 'path=%s\nmaxFiles=1\nmaxLines=%s\n' "$allow_path" "$MANA_REPAIR_DEFAULT_MAX_CHANGED_LINES" | verification_digest_text)"
  plan_identity="$(printf 'mode=implementation\nprovider=%s\ngrant=%s\nonce=true\nsubagents=false\nloop=%s\niteration=%s\n' "$provider" "$grant_digest" "${loop_context_id:-none}" "$loop_iteration" | verification_digest_text)"
  target_id="repair-target-sha256-$(printf '%s\n%s\n%s\n' "$concern_key" "$from_digest" "$check_id" | verification_digest_text | cut -d: -f2)"
  project_identity="$(printf '%s\n%s\n' "$(git -C "$project_root" rev-parse --show-toplevel 2>/dev/null || printf repository)" "$(git -C "$project_root" rev-parse HEAD 2>/dev/null || printf workspace)" | verification_digest_text)"
  created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  jq -n --arg created "$created_at" --arg targetId "$target_id" --arg concern "$concern_key" --arg ref "$from_reference" --arg digest "$from_digest" --arg run "$(jq -r .runId "$from")" --arg check "$check_id" --arg skill "$skill_id" --arg version "$(jq -r .skillVersion <<<"$check_json")" --arg spec "$(jq -r .specDigest <<<"$check_json")" --arg targetFingerprint "$target_fingerprint" --arg inputDigest "$(jq -r .inputDigest <<<"$check_json")" --arg adapterDigest "$(jq -r .adapterImplementationDigest <<<"$check_json")" --arg environmentClassification "$(jq -r .environmentClassification <<<"$check_json")" --arg environmentDigest "$(jq -r .environmentDigest <<<"$check_json")" --arg executablePath "$(jq -r .executable.path <<<"$check_json")" --arg executableDigest "$(jq -r .executable.digest <<<"$check_json")" --arg failureFingerprint "$failure_fingerprint" --arg path "$target_path" --arg grantDigest "$grant_digest" --arg workspace "$workspace_reference" --arg projectIdentity "$project_identity" --arg planIdentity "$plan_identity" --argjson maxLines "$MANA_REPAIR_DEFAULT_MAX_CHANGED_LINES" --argjson observations "$(jq -c .observations <<<"$check_json")" '{schemaVersion:"1",kind:"repair-target",targetId:$targetId,createdAt:$created,mode:"implementation",origin:{resultReference:$ref,resultDigest:$digest,runId:$run,checkId:$check},concernKey:$concern,skill:{id:$skill,version:$version,specDigest:$spec},target:{targetFingerprint:$targetFingerprint,inputDigest:$inputDigest,rerunDescriptor:{kind:"repository_path",path:$path}},failure:{failureFingerprint:$failureFingerprint,observations:$observations},rerunIdentity:{adapter:"bash_syntax",adapterImplementationDigest:$adapterDigest,executablePath:$executablePath,executableDigest:$executableDigest,environmentClassification:$environmentClassification,environmentDigest:$environmentDigest},mutationGrant:{allowedPaths:[$path],grantDigest:$grantDigest,maxFiles:1,hardMaxFiles:5,maxChangedLines:$maxLines,hardMaxChangedLines:500},workspaceContext:{workspaceReference:$workspace,projectIdentity:$projectIdentity},executionPlan:{identity:$planIdentity,mode:"implementation",runnerInvocations:1,subagents:false}}' > "$tmp/target.json"
  repair_target_validate "$tmp/target.json" || { eligibility=blocked; eligibility_reason='constructed Repair Target failed strict canonical validation'; }
fi

baseline_digest=unavailable; baseline_mode=unavailable; baseline_worktree_state=unknown
if [ "$eligibility" = eligible ]; then
  baseline_target_digest="$(verification_digest_file "$project_root/$target_path")"
  baseline_mode="$(repair_file_mode "$project_root/$target_path")"
  target_status="$(git -C "$project_root" status --porcelain=v1 --untracked-files=all -- "$target_path" 2>/dev/null || true)"
  case "$target_status" in '') baseline_worktree_state=clean;; '?? '*) baseline_worktree_state=untracked;; *) baseline_worktree_state=modified;; esac
  baseline_digest="$(printf 'path=%s\ncontent=%s\ntype=regular\nmode=%s\nworkingTree=%s\nrepairTarget=%s\nevaluationSurface=%s\n' "$target_path" "$baseline_target_digest" "$baseline_mode" "$baseline_worktree_state" "$target_id" "$protected_digest" | verification_digest_text)"
fi

model=""; case "$provider" in codex) model="${MANA_CODEX_MODEL:-gpt-5.4-mini}";; claude) model="${MANA_CLAUDE_MODEL:-haiku}";; opencode) model="${MANA_OPENCODE_MODEL:-opencode/gpt-5.1-codex}";; stub) model=deterministic-stub;; *) eligibility=blocked; eligibility_reason="unsupported repair runner: $provider";; esac
plan_json="$(jq -n --arg eligibility "$eligibility" --arg reason "$eligibility_reason" --arg check "${check_id:-}" --arg provider "$provider" --arg model "$model" --arg path "$allow_path" --arg protectedDigest "${protected_digest:-unavailable}" --arg targetId "${target_id:-}" --arg baseline "$baseline_digest" --arg baselineMode "$baseline_mode" --arg baselineState "$baseline_worktree_state" --arg exclusions "$MANA_REPAIR_PROJECTION_EXCLUSIONS" --argjson runnerSeconds "$MANA_REPAIR_MAX_RUNNER_SECONDS" --argjson maxLines "$MANA_REPAIR_DEFAULT_MAX_CHANGED_LINES" '{schemaVersion:"1",kind:"repair-once-plan",eligibility:$eligibility,reason:$reason,targetId:(if $targetId=="" then null else $targetId end),checkId:(if $check=="" then null else $check end),containment:{backend:"disposable-workspace",capability:"faulty-contained",adversarialBoundary:false,liveRepositoryProviderAccess:false,hostPatchImport:true,processIsolation:false,hostFilesystemIsolation:false,networkIsolation:false},staging:{materialization:"current-working-tree-copy",exclusions:$exclusions,createsWorkspace:false},baseline:{identity:$baseline,type:"regular",mode:$baselineMode,workingTreeState:$baselineState},runner:{provider:$provider,model:$model,invocations:1,wallTimeSeconds:$runnerSeconds,stdoutLimitBytes:65536,stderrLimitBytes:65536,subagents:false,workingDirectory:"disposable-project-copy"},mutationGrant:{allowedPaths:[$path],maxFiles:1,hardMaxFiles:5,maxChangedLines:$maxLines,hardMaxChangedLines:500},candidateImport:{exactPathOnly:true,regularTextContentOnly:true,creations:false,deletions:false,renames:false,symlinks:false,modeChanges:false,liveDriftStopReason:"live_target_drift"},protectedSurfaceDigest:$protectedDigest,rerun:{count:1,verifierOwned:true,repository:"live",afterImport:true,usesStoredEffectiveArgv:false},stopConditions:["ineligible","runner_failed","runner_timeout","candidate_policy_violation","live_target_drift","evaluation_surface_changed","after_verification_incomparable"],persistentEffects:false}')"
render_plan() { echo 'MANA REPAIR ONCE PLAN'; jq -r '"eligibility: "+.eligibility,"reason: "+.reason,"check: "+(.checkId//"unselected"),"containment: "+.containment.backend+" ("+.containment.capability+"; not an adversarial boundary)","runner: "+.runner.provider+" (exactly one invocation; disposable-project-copy working directory; subagents disabled)","allowed paths: "+(.mutationGrant.allowedPaths|join(", ")),"staging: current working-tree copy; exclusions: "+.staging.exclusions,"baseline: "+.baseline.identity+" ("+.baseline.workingTreeState+", mode "+.baseline.mode+")","candidate import: exact regular-text content change only; no create/delete/rename/symlink/mode change","live drift: stop with "+.candidateImport.liveDriftStopReason,"protected surface: "+.protectedSurfaceDigest,"rerun: verifier-owned against live repository after host import","budgets: 600s; stdout/stderr 65536 bytes; 1 file/"+(.mutationGrant.maxChangedLines|tostring)+" changed lines","stop conditions: "+(.stopConditions|join(", "))' <<<"$plan_json"; }
if [ "$dry_run" = true ]; then if [ "$json" = true ]; then printf '%s\n' "$plan_json"; else render_plan; fi; [ "$eligibility" = eligible ]; exit; fi
if [ "$eligibility" != eligible ]; then
  preflight_id="repair-preflight-$(date -u +%Y%m%dT%H%M%SZ)-$$"; runtime_init "$project_root" repair || true
  runtime_emit repair.started repair "$preflight_id" started "provider=$provider" "" false || true
  runtime_emit repair.eligibility.checked repair "$preflight_id" "$eligibility" "status=$eligibility" "${from_reference:-}" false || true
  runtime_emit repair.escalated repair "$preflight_id" "$eligibility" "stopReason=eligibility_gate" "" false || true
  runtime_emit repair.completed repair "$preflight_id" "$eligibility" "stopReason=eligibility_gate" "" false || true; runtime_finish failed
  if [ "$json" = true ]; then printf '%s\n' "$plan_json"; else render_plan; fi; exit 1
fi

umask 077; started_epoch="$(date +%s)"; attempt_id="repair-attempt-$(date -u +%Y%m%dT%H%M%SZ)-$$"; repair_parent="$workspace/evidence/repair"; evidence_staging="$repair_parent/.${attempt_id}.tmp"; final_dir="$repair_parent/$attempt_id"; lock="$repair_parent/.repair.lock"; disposable_root=""; import_temp=""
mkdir -p "$repair_parent"
if [ -d "$repair_parent/.repair-loop.lock" ]; then [ -n "$loop_context_id" ] && [ "$(sed -n '1p' "$repair_parent/.repair-loop.lock/id" 2>/dev/null)" = "$loop_context_id" ] || fail 'a bounded repair loop owns this workspace'; fi
mkdir "$lock" 2>/dev/null || fail 'another repair attempt is active in this workspace'; mkdir "$evidence_staging" "$evidence_staging/runner" || fail 'repair evidence staging collision'
repair_cleanup() { rmdir "$lock" 2>/dev/null || true; [ -z "$import_temp" ] || rm -f "$import_temp"; [ -z "$disposable_root" ] || repair_cleanup_disposable_root "$disposable_root" || true; rm -rf "$evidence_staging" "$tmp"; }
repair_interrupted() { runtime_emit repair.interrupted repair "$attempt_id" interrupted "stopReason=interrupted" "" false || true; runtime_finish failed; repair_cleanup; trap - EXIT; exit 130; }
trap repair_cleanup EXIT; trap repair_interrupted INT TERM
runtime_init "$project_root" repair || fail 'runtime audit initialization failed'; runtime_emit repair.started repair "$attempt_id" started "provider=$provider" "" false; runtime_emit repair.eligibility.checked repair "$attempt_id" eligible "status=eligible" "$from_reference" false

cp -p "$project_root/$target_path" "$tmp/allowed-before" || fail 'could not snapshot allowed repair target'
[ "$(verification_digest_file "$tmp/allowed-before")" = "$baseline_target_digest" ] || fail 'repair target drifted before disposable staging; provider dispatch refused'
[ "$(repair_file_mode "$project_root/$target_path")" = "$baseline_mode" ] || fail 'repair target mode drifted before disposable staging; provider dispatch refused'
cp "$tmp/target.json" "$evidence_staging/target.json"; target_digest="$(verification_digest_file "$evidence_staging/target.json")"
disposable_temp_base="${TMPDIR:-/tmp}"; disposable_temp_base="${disposable_temp_base%/}"
disposable_root="$(mktemp -d "$disposable_temp_base/mana-repair-workspace.XXXXXX")" || fail 'could not create disposable repair root'
disposable_canonical="$(cd "$disposable_root" && pwd -P)" || fail 'could not resolve disposable repair root'
case "$disposable_canonical" in "$project_root"|"$project_root"/*) fail 'disposable repair root resolved inside the live repository';; esac
candidate_project="$disposable_root/project"; mkdir "$candidate_project" || fail 'could not create disposable project workspace'
repair_materialize_workspace "$project_root" "$candidate_project" || fail 'project cannot be safely materialized for bounded repair (unsafe path, symlink, or special file)'
[ ! -e "$candidate_project/.git" ] && [ ! -L "$candidate_project/.git" ] && [ ! -e "$candidate_project/.mana" ] && [ ! -L "$candidate_project/.mana" ] || fail 'control-plane exclusion failed during repair staging'
[ -f "$candidate_project/$target_path" ] && [ ! -L "$candidate_project/$target_path" ] || fail 'staged target is not the authorized regular file'
[ "$(verification_digest_file "$candidate_project/$target_path")" = "$baseline_target_digest" ] && [ "$(repair_file_mode "$candidate_project/$target_path")" = "$baseline_mode" ] || fail 'staged target does not match the host baseline'
repair_workspace_manifest "$candidate_project" "$tmp/candidate-before.json" "$tmp" || fail 'could not inventory staged repair baseline'
workspace_identity="$(verification_digest_file "$tmp/candidate-before.json")"
candidate_project_mode="$(repair_file_mode "$candidate_project")" || fail 'could not identify disposable project root mode'
runtime_emit repair.staging.created repair "$attempt_id" completed "backend=disposable-workspace capability=faulty-contained" "" false
loop_contract_note=""; if [ -n "$loop_context_id" ]; then loop_contract_note="Bounded loop iteration $loop_iteration of 2. One prior bounded attempt occurred. This is the FINAL allowed attempt."; [ "$loop_iteration" = 1 ] && loop_contract_note="Bounded loop iteration 1 of at most 2. A second invocation is allowed only if Mana mechanically proves strict-subset partial progress."; fi
contract="$tmp/contract.txt"; jq -r --arg ref "$from_reference" --arg digest "$from_digest" --arg protected "$protected_digest" --arg loopNote "$loop_contract_note" '
  ["BOUNDED MANA REPAIR CONTRACT v1","You are operating in a disposable project copy, not the live repository.","Repair target: "+.targetId,"Concern: "+.concernKey,"Before evidence reference (not present in this copy): "+$ref+" ("+$digest+")","Allowed path (exactly one): "+(.mutationGrant.allowedPaths|join(", ")),"Protected evaluation surface digest: "+$protected,"Failure observations: "+(.failure.observations|tojson),(if $loopNote!="" then $loopNote else empty end),"Make one bounded implementation attempt only. Modify only the exact allowed path.","Do not create .git or .mana, or change tests, specs, verifier, governance, ignore rules, or protected surface.","Do not invoke Mana, recurse, use subagents, broaden scope, make unrelated fixes, commit, push, deploy, or claim success.","Stop immediately after the bounded edit. Mana will compute the candidate delta, validate it, import an accepted change, and rerun verification against the live repository."]|join("\n")' "$tmp/target.json" > "$contract"
[ "$(wc -c < "$contract" | tr -d ' ')" -le "$MANA_REPAIR_MAX_CONTRACT_BYTES" ] || fail 'repair contract exceeded 8 KiB'
MANA_PROVIDER_PROGRAM="$provider"; mana_provider_repair_args "$provider" "$candidate_project" "$model" || fail "could not construct repair runner arguments: $provider"; runner_program="${MANA_PROVIDER_PROGRAM:-$provider}"; command -v "$runner_program" >/dev/null 2>&1 || fail "repair runner executable not found: $runner_program"
runner_fingerprint="$( { printf 'program=%s\n' "$runner_program"; printf 'arg=%s\n' "${MANA_PROVIDER_ARGS[@]}"; verification_digest_file "$contract"; } | verification_digest_text)"
runtime_emit repair.runner.started repair "$attempt_id" started "provider=$provider" "" false
status_file="$tmp/runner.status"; prompt="$(cat "$contract")"; invocation_started="$(date +%s)"
(
  cd "$candidate_project" || exit 125
  unset OLDPWD MANA_PROJECT_ROOT MANA_HOME GIT_DIR GIT_WORK_TREE INIT_CWD npm_config_local_prefix
  MANA_REPAIR_RUNNING=1 perl "$root/scripts/lib/verification-exec.pl" --timeout "$MANA_REPAIR_MAX_RUNNER_SECONDS" --output-cap "$MANA_REPAIR_MAX_STREAM_BYTES" --stdout "$evidence_staging/runner/stdout.log" --stderr "$evidence_staging/runner/stderr.log" --status "$status_file" -- "$runner_program" "${MANA_PROVIDER_ARGS[@]}" "$prompt"
) || true
MANA_REPAIR_REDACT_PATH="$disposable_root" MANA_REPAIR_REDACT_CANONICAL="$disposable_canonical" perl -pi -e 's/\Q$ENV{MANA_REPAIR_REDACT_PATH}\E/[DISPOSABLE_WORKSPACE]/g; s/\Q$ENV{MANA_REPAIR_REDACT_CANONICAL}\E/[DISPOSABLE_WORKSPACE]/g' "$evidence_staging/runner/stdout.log" "$evidence_staging/runner/stderr.log" || fail 'could not redact disposable workspace identity from runner logs'
if [ -f "$status_file" ]; then IFS=$'\t' read -r runner_code runner_signal timed_out descendants runner_out_bytes runner_err_bytes runner_duration < "$status_file"; else runner_code=125; runner_signal=0; timed_out=0; descendants=0; runner_out_bytes=0; runner_err_bytes=0; runner_duration=$((($(date +%s)-invocation_started)*1000)); fi
runner_timed_out=false; [ "$timed_out" = 1 ] && runner_timed_out=true; runner_descendants=false; [ "$descendants" = 1 ] && runner_descendants=true
if [ "$runner_timed_out" = true ]; then runtime_emit repair.runner.failed repair "$attempt_id" timed_out "provider=$provider" "" false
elif [ "$runner_code" -ne 0 ]; then runtime_emit repair.runner.failed repair "$attempt_id" failed "provider=$provider exitCode=$runner_code" "" false
else runtime_emit repair.runner.completed repair "$attempt_id" completed "provider=$provider exitCode=0" "" false; fi

policy_file="$tmp/policy-violations"; scope_file="$tmp/scope-violations"; surface_changes_file="$tmp/surface-changes"; : > "$policy_file"; : > "$scope_file"; : > "$surface_changes_file"
candidate_workspace_integrity=true
if [ ! -d "$candidate_project" ] || [ "$(repair_file_mode "$candidate_project" 2>/dev/null || printf unavailable)" != "$candidate_project_mode" ] || find "$disposable_root" -mindepth 1 -maxdepth 1 ! -name project -print -quit 2>/dev/null | grep -q .; then
  candidate_workspace_integrity=false; printf '%s\n' candidate_workspace_root_changed >> "$policy_file"
fi
if ! repair_workspace_manifest "$candidate_project" "$tmp/candidate-after.json" "$tmp"; then
  candidate_workspace_integrity=false; printf '%s\n' candidate_workspace_invalid >> "$policy_file"; printf '[]\n' > "$tmp/candidate-after.json"
fi
repair_candidate_delta "$tmp/candidate-before.json" "$tmp/candidate-after.json" "$tmp/candidate-delta.json" || { candidate_workspace_integrity=false; printf '%s\n' candidate_delta_unavailable >> "$policy_file"; printf '{"changedPaths":[],"changes":[]}\n' > "$tmp/candidate-delta.json"; }
mutations_json="$(jq -c .changedPaths "$tmp/candidate-delta.json")"
while IFS= read -r changed; do
  [ "$changed" = "$allow_path" ] || { printf '%s\n' "$changed" >> "$scope_file"; printf 'out_of_scope_change:%s\n' "$changed" >> "$policy_file"; }
  case "$changed" in .git|.git/*|*/.git|*/.git/*) printf '%s\n' control_plane_git_created_or_changed >> "$policy_file";; esac
  case "$changed" in .mana|.mana/*|*/.mana|*/.mana/*) printf '%s\n' control_plane_mana_created_or_changed >> "$policy_file";; esac
  case "$changed" in .gitignore|.gitattributes|.gitmodules) printf '%s\n' "$changed" >> "$surface_changes_file";; esac
done < <(jq -r '.changedPaths[]' "$tmp/candidate-delta.json")
target_changed=false; jq -e --arg path "$target_path" '.changedPaths|index($path)' "$tmp/candidate-delta.json" >/dev/null && target_changed=true
candidate_digest="$baseline_target_digest"; patch_digest="$(git diff --no-index --binary -- "$tmp/allowed-before" "$candidate_project/$target_path" 2>/dev/null | verification_digest_text)"; changed_lines=0; line_ambiguous=false
if [ "$target_changed" = true ]; then
  candidate_type="$(jq -r --arg path "$target_path" '.changes[]|select(.path==$path)|(.after.type // "missing")' "$tmp/candidate-delta.json")"
  candidate_mode="$(jq -r --arg path "$target_path" '.changes[]|select(.path==$path)|(.after.mode // "unavailable")' "$tmp/candidate-delta.json")"
  if [ "$candidate_type" = missing ]; then printf '%s\n' target_deleted >> "$policy_file"; candidate_digest=unavailable; patch_digest=unavailable
  elif [ "$candidate_type" != file ] || [ ! -f "$candidate_project/$target_path" ] || [ -L "$candidate_project/$target_path" ]; then printf '%s\n' target_type_changed >> "$policy_file"; candidate_digest=unavailable; patch_digest=unavailable
  else
    candidate_digest="$(verification_digest_file "$candidate_project/$target_path")"
    patch_digest="$(git diff --no-index --binary -- "$tmp/allowed-before" "$candidate_project/$target_path" 2>/dev/null | verification_digest_text)"
    [ "$candidate_mode" = "$baseline_mode" ] || printf '%s\n' target_mode_changed >> "$policy_file"
    repair_supported_text_file "$candidate_project/$target_path" || printf '%s\n' target_not_supported_text >> "$policy_file"
    numstat="$(git diff --no-index --numstat -- "$tmp/allowed-before" "$candidate_project/$target_path" 2>/dev/null || true)"
    if [ -n "$numstat" ]; then additions="$(awk 'NR==1{print $1}' <<<"$numstat")"; deletions="$(awk 'NR==1{print $2}' <<<"$numstat")"; if [[ "$additions" =~ ^[0-9]+$ ]] && [[ "$deletions" =~ ^[0-9]+$ ]]; then changed_lines=$((additions+deletions)); else line_ambiguous=true; fi; fi
  fi
fi
[ "$line_ambiguous" != true ] && [ "$changed_lines" -le "$MANA_REPAIR_DEFAULT_MAX_CHANGED_LINES" ] || printf '%s\n' changed_line_measurement_ambiguous_or_exceeded >> "$policy_file"
policy_violations="$(LC_ALL=C sort -u "$policy_file" | verification_json_array_lines)"; scope_violations="$(LC_ALL=C sort -u "$scope_file" | verification_json_array_lines)"; surface_changes="$(LC_ALL=C sort -u "$surface_changes_file" | verification_json_array_lines)"
runtime_emit repair.candidate.inspected repair "$attempt_id" completed "changed=$(jq length <<<"$mutations_json") violations=$(jq length <<<"$policy_violations") integrity=$candidate_workspace_integrity" "" false

comparison=UNKNOWN; progress=null; attempt_status=completed; stop_reason=attempt_complete; rerun_count=0; after_ref=null; after_digest=null; reasons='[]'; resolved='[]'; persistent='[]'; new_required='[]'; new_optional='[]'; limitations='["Disposable-workspace containment protects the live repository from ordinary or faulty provider edits, but is not an OS security boundary against a deliberately malicious same-UID process.","Process, host-filesystem, home-directory, credential, and network isolation are not provided.","Raw runner logs are capped owner-only local evidence and may still contain sensitive model output."]'; live_baseline_matched=null; import_applied=false; imported_digest=null
if [ "$(jq length <<<"$policy_violations")" -gt 0 ]; then attempt_status=policy_violation; stop_reason=candidate_policy_violation; reasons='["candidate_policy_violation"]'
elif [ "$runner_timed_out" = true ] || [ "$runner_descendants" = true ]; then attempt_status=runner_timed_out; stop_reason=runner_timeout; reasons='["runner_timeout_or_descendant_cleanup"]'
elif [ "$runner_code" -ne 0 ]; then attempt_status=runner_failed; stop_reason=runner_nonzero_exit; reasons='["runner_nonzero_exit"]'
else
  if [ "$target_changed" = true ]; then
    if ! repair_prepare_import "$candidate_project/$target_path" "$project_root/$target_path" "$baseline_mode" "$candidate_digest"; then
      attempt_status=integrity_violation; stop_reason=import_preparation_failed; reasons='["host_import_preparation_failed"]'
    else import_temp="$MANA_REPAIR_IMPORT_TEMP"; fi
  fi
  if [ "$attempt_status" = completed ]; then
    while IFS= read -r item; do file="$(jq -r .file <<<"$item")"; old="$(jq -r .digest <<<"$item")"; if [ -L "$file" ]; then now="$(readlink "$file" | verification_digest_text)"; elif [ -f "$file" ]; then now="$(verification_digest_file "$file")"; else now=unavailable; fi; [ "$old" = "$now" ] || jq -r .label <<<"$item" >> "$surface_changes_file"; done < "$protected_manifest"
    surface_changes="$(LC_ALL=C sort -u "$surface_changes_file" | verification_json_array_lines)"
    current_parent="$(cd "$project_root/$target_parent" 2>/dev/null && pwd -P || true)"
    if [ "$current_parent" != "$expected_parent" ] || [ ! -f "$project_root/$target_path" ] || [ -L "$project_root/$target_path" ] || [ "$(repair_file_mode "$project_root/$target_path" 2>/dev/null || printf unavailable)" != "$baseline_mode" ] || [ "$(verification_digest_file "$project_root/$target_path" 2>/dev/null || printf unavailable)" != "$baseline_target_digest" ]; then
      live_baseline_matched=false; attempt_status=integrity_violation; stop_reason=live_target_drift; reasons='["live_target_drift"]'
    elif [ "$(jq length <<<"$surface_changes")" -gt 0 ]; then
      live_baseline_matched=true; attempt_status=integrity_violation; stop_reason=evaluation_surface_changed; reasons='["evaluation_surface_changed"]'
    else
      live_baseline_matched=true
      if [ "$target_changed" = true ]; then
        if repair_publish_import "$import_temp" "$project_root/$target_path" && [ "$(verification_digest_file "$project_root/$target_path")" = "$candidate_digest" ] && [ "$(repair_file_mode "$project_root/$target_path")" = "$baseline_mode" ]; then import_temp=""; import_applied=true; imported_digest="\"$candidate_digest\""; runtime_emit repair.import.applied repair "$attempt_id" completed "applied=true" "" false
        else attempt_status=integrity_violation; stop_reason=import_publication_failed; reasons='["host_import_publication_failed"]'; fi
      else runtime_emit repair.import.applied repair "$attempt_id" completed "applied=false" "" false
      fi
    fi
  fi
fi
if [ "$attempt_status" != completed ]; then runtime_emit repair.import.rejected repair "$attempt_id" "$attempt_status" "stopReason=$stop_reason" "" false; fi
if [ "$attempt_status" = completed ]; then
  runtime_emit repair.verification.started repair "$attempt_id" started "check=$check_id" "$from_reference" false
  after_capture="$tmp/after.json"; "$root/scripts/mana-verify.sh" --project-root "$project_root" --rerun "$from" --check "$check_id" --json > "$after_capture" || true; rerun_count=1
  if verification_result_validate "$after_capture" && [ "$(jq -r .schemaVersion "$after_capture")" = 2 ]; then
    after_run="$(jq -r .runId "$after_capture")"; after_file="$workspace/evidence/verification/$after_run/result.json"; after_ref="${after_file#"$project_root"/}"; after_digest="$(verification_digest_file "$after_file")"
    runtime_emit repair.verification.completed repair "$attempt_id" completed "result=$(jq -r .overallResult "$after_file")" "$after_ref" false
    same=true; for field in concernKey skillId baseCheckId specDigest adapterImplementationDigest targetFingerprint environmentClassification environmentDigest; do [ "$(jq -r --arg id "$check_id" ".checks[]|select(.checkId==\$id)|.$field" "$from")" = "$(jq -r --arg id "$check_id" ".checks[]|select(.checkId==\$id)|.$field" "$after_file")" ] || same=false; done
    [ "$(jq -r --arg id "$check_id" '.checks[]|select(.checkId==$id)|.executable.digest' "$from")" = "$(jq -r --arg id "$check_id" '.checks[]|select(.checkId==$id)|.executable.digest' "$after_file")" ] || same=false
    if [ "$same" != true ] || [ "$(jq -r .observedEffects.unexpectedSourceMutation "$after_file")" != false ]; then reasons='["verification_identity_or_integrity_mismatch"]'; stop_reason=after_verification_incomparable
    else comparison_json="$(repair_comparison_json "$from" "$after_file" "$check_id")"; comparison="$(jq -r .comparison <<<"$comparison_json")"; progress="$(jq -c .progress <<<"$comparison_json")"; reasons="$(jq -c .reasons <<<"$comparison_json")"; resolved="$(jq -c .resolvedFailures <<<"$comparison_json")"; persistent="$(jq -c .persistentFailures <<<"$comparison_json")"; new_required="$(jq -c .newRequiredFailures <<<"$comparison_json")"; new_optional="$(jq -c .newOptionalFailures <<<"$comparison_json")"; [ "$comparison" = UNKNOWN ] && { attempt_status=verification_failed; stop_reason=after_verification_incomparable; }; fi
  else runtime_emit repair.verification.completed repair "$attempt_id" failed "result=invalid" "" false; attempt_status=verification_failed; stop_reason=after_verification_missing; reasons='["after_evidence_missing_or_invalid"]'; fi
fi
runtime_emit repair.comparison.completed repair "$attempt_id" completed "comparison=$comparison" "" false
[ "$attempt_status" = completed ] || runtime_emit repair.escalated repair "$attempt_id" "$attempt_status" "stopReason=$stop_reason" "" false

after_json=null; [ "$after_ref" != null ] && after_json="$(jq -cn --arg ref "$after_ref" --arg digest "$after_digest" '{reference:$ref,digest:$digest}')"
wall_ms=$((($(date +%s)-started_epoch)*1000)); result_tmp="$evidence_staging/.result.json.tmp"
jq -n --arg attempt "$attempt_id" --arg runtime "$MANA_RUNTIME_EXECUTION_ID" --arg targetRef "${workspace_reference}/evidence/repair/${attempt_id}/target.json" --arg targetDigest "$target_digest" --arg targetId "$target_id" --arg concern "$concern_key" --arg provider "$provider" --arg runnerFingerprint "$runner_fingerprint" --arg plan "$plan_identity" --arg protected "$protected_digest" --arg patch "$patch_digest" --arg workspaceIdentity "$workspace_identity" --arg candidateDigest "$candidate_digest" --arg baseline "$baseline_digest" --arg baselineContent "$baseline_target_digest" --arg baselineMode "$baseline_mode" --arg baselineState "$baseline_worktree_state" --arg beforeRef "$from_reference" --arg beforeDigest "$from_digest" --arg comparison "$comparison" --arg stop "$stop_reason" --arg status "$attempt_status" --argjson runnerExit "$runner_code" --argjson runnerSignal "$runner_signal" --argjson runnerTimedOut "$runner_timed_out" --argjson descendants "$runner_descendants" --argjson allowed "$(printf '%s\n' "$allow_path" | verification_json_array_lines)" --argjson mutated "$mutations_json" --argjson violations "$scope_violations" --argjson policyViolations "$policy_violations" --argjson surfaceChanges "$surface_changes" --argjson candidateIntegrity "$candidate_workspace_integrity" --argjson changedLines "$changed_lines" --argjson liveMatched "$live_baseline_matched" --argjson applied "$import_applied" --argjson imported "$imported_digest" --argjson after "$after_json" --argjson reasons "$reasons" --argjson resolved "$resolved" --argjson persistent "$persistent" --argjson newRequired "$new_required" --argjson newOptional "$new_optional" --argjson progress "$progress" --argjson limitations "$limitations" --argjson reruns "$rerun_count" --argjson wall "$wall_ms" '{schemaVersion:"1",kind:"repair-attempt-result",attemptId:$attempt,runtimeExecutionId:$runtime,target:{reference:$targetRef,digest:$targetDigest,targetId:$targetId,concernKey:$concern},provider:$provider,runner:{fingerprint:$runnerFingerprint,exitCode:$runnerExit,signal:$runnerSignal,timedOut:$runnerTimedOut,descendantsTerminated:$descendants,inputTokens:null,outputTokens:null,invocationCount:1},executionPlanIdentity:$plan,isolation:{capability:"faulty-contained",backend:"disposable-workspace",adversarialBoundary:false,liveRepositoryProviderAccess:false,hostPatchImport:true,processIsolation:false,hostFilesystemIsolation:false,networkIsolation:false},candidate:{workspaceIdentity:$workspaceIdentity,workspaceIntegrity:$candidateIntegrity,changedPaths:$mutated,candidateDigest:$candidateDigest,changedLineCount:$changedLines,policyViolations:$policyViolations},import:{baselineDigest:$baseline,baselineContentDigest:$baselineContent,baselineType:"regular",baselineMode:$baselineMode,workingTreeState:$baselineState,repairTargetId:$targetId,evaluationSurfaceDigest:$protected,liveBaselineMatched:$liveMatched,applied:$applied,importedDigest:$imported},allowedPaths:$allowed,protectedSurfaceDigest:$protected,actualMutatedPaths:$mutated,patchDigest:$patch,scopeViolations:$violations,evaluationSurfaceChanges:$surfaceChanges,beforeVerification:{reference:$beforeRef,digest:$beforeDigest},afterVerification:$after,comparison:$comparison,comparabilityReasons:$reasons,resolvedFailures:$resolved,persistentFailures:$persistent,newRequiredFailures:$newRequired,newOptionalFailures:$newOptional,progress:$progress,attemptStatus:$status,stopReason:$stop,limitations:$limitations,wallTimeMs:$wall,verificationRerunCount:$reruns,judgment:null}' > "$result_tmp"
repair_attempt_validate "$result_tmp" || fail 'Repair Attempt Result failed strict canonical validation'; mv "$result_tmp" "$evidence_staging/result.json"
{ echo '# Mana Repair Attempt'; echo; echo "- Attempt: \`$attempt_id\`"; echo "- Target: \`$target_id\`"; echo "- Status: \`$attempt_status\`"; echo "- Comparison: \`$comparison\`"; echo "- Stop reason: \`$stop_reason\`"; echo '- Containment: `faulty-contained` via `disposable-workspace` (not an OS security boundary)'; echo "- Host import applied: \`$import_applied\`"; echo '- Runner invocations: `1`'; echo "- Verification reruns: \`$rerun_count\`"; echo; echo '## Meaning'; echo; echo 'RESOLVED means only that the targeted verification concern disappeared under comparable evidence. It does not mean ready to merge, correct implementation, or production-safe.'; } > "$evidence_staging/summary.md"
chmod 600 "$evidence_staging/runner/stdout.log" "$evidence_staging/runner/stderr.log" "$evidence_staging/target.json" "$evidence_staging/result.json"; [ ! -e "$final_dir" ] || fail 'repair attempt identity collision'; mv "$evidence_staging" "$final_dir"
runtime_emit repair.completed repair "$attempt_id" "$attempt_status" "comparison=$comparison stopReason=$stop_reason" "${workspace_reference}/evidence/repair/$attempt_id/result.json" false; runtime_finish "$([ "$attempt_status" = completed ] && echo completed || echo failed)"; rmdir "$lock" 2>/dev/null || true
"$root/scripts/run-evidence-index.sh" --project-root "$project_root" --workspace "$workspace" >/dev/null 2>&1 || true
if [ "$json" = true ]; then cat "$final_dir/result.json"; else echo 'MANA REPAIR ONCE'; echo "status: $attempt_status"; echo "comparison: $comparison"; echo "evidence: ${workspace_reference}/evidence/repair/$attempt_id/result.json"; fi
[ "$attempt_status" = completed ]
