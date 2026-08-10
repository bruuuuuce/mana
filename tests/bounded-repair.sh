#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"; tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-repair-tests.XXXXXX")"; trap 'rm -rf "$tmp"' EXIT
. "$root/scripts/lib/verification.sh"; . "$root/scripts/lib/repair.sh"
fail() { echo "FAIL: $*" >&2; exit 1; }
init_repo() { mkdir -p "$1"; git -C "$1" init -q; git -C "$1" config user.email test@example.invalid; git -C "$1" config user.name Test; git -C "$1" config commit.gpgsign false; printf '#!/usr/bin/env bash\ntrue\n' > "$1/fixture.sh"; printf 'base\n' > "$1/unrelated.txt"; printf '.mana/\n' > "$1/.gitignore"; git -C "$1" add .; git -C "$1" commit -qm base; printf '#!/usr/bin/env bash\nif then\n' > "$1/fixture.sh"; }
make_origin() { "$root/scripts/mana-verify.sh" --project-root "$1" --skill shell-syntax-verification --json > "$2" && fail 'broken syntax passed'; find "$1/.mana" -path '*/evidence/verification/*/result.json' -type f | tail -n1; }
make_stub() { printf '%s\n' '#!/usr/bin/env bash' "$2" > "$1"; chmod +x "$1"; }
repair() { MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$2" "$root/scripts/mana-repair.sh" --project-root "$1" --from "$3" --check "$4" --allow-path fixture.sh --runner stub --once --json; }

# Verification Result v2 and strict Repair Target/Attempt validators.
project="$tmp/resolved"; init_repo "$project"; origin="$(make_origin "$project" "$tmp/origin.json")"; check="$(jq -r '.checks[0].checkId' "$origin")"
jq -e '.schemaVersion=="2" and .checks[0].rerunDescriptor=={"kind":"repository_path","path":"fixture.sh"} and (.checks[0].evaluationSurface|map(.role)|index("mutable_input"))' "$origin" >/dev/null || fail 'v2 repair metadata missing'

# Dry-run is pure, plans exactly one invocation, and never runs provider/verifier.
before="$(find "$project/.mana" -type f -exec cksum {} + | LC_ALL=C sort)"; dry="$(MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND=/does/not/exist "$root/scripts/mana-repair.sh" --project-root "$project" --from "$origin" --check "$check" --allow-path fixture.sh --runner stub --once --dry-run --explain --json)" || fail 'eligible dry run failed'; after="$(find "$project/.mana" -type f -exec cksum {} + | LC_ALL=C sort)"; [ "$before" = "$after" ] || fail 'dry run persisted effects'; jq -e '.eligibility=="eligible" and .runner.invocations==1 and .runner.subagents==false and .runner.workingDirectory=="disposable-project-copy" and .containment.capability=="faulty-contained" and .containment.adversarialBoundary==false and .containment.liveRepositoryProviderAccess==false and .staging.createsWorkspace==false and .candidateImport.liveDriftStopReason=="live_target_drift" and .persistentEffects==false and .rerun.repository=="live" and .rerun.usesStoredEffectiveArgv==false' <<<"$dry" >/dev/null || fail 'dry plan incorrect'

# Historical argv is evidence only: make it malicious, refresh integrity, then
# prove the same dispatch boundary fixes only the descriptor path and resolves.
jq '.checks[0].effectiveArgv=["bash","-c","touch SHOULD_NOT_EXIST"]' "$origin" > "$tmp/malicious.json"; mv "$tmp/malicious.json" "$origin"; verification_digest_file "$origin" > "$(dirname "$origin")/result.sha256"
stub="$tmp/fix-stub"; make_stub "$stub" 'printf '\''#!/usr/bin/env bash\ntrue\n'\'' > fixture.sh; echo "provider says success SECRET_DO_NOT_TELEMETRY"'
resolved="$(repair "$project" "$stub" "$origin" "$check")" || fail 'deterministic repair dogfood failed'
jq -e '.comparison=="RESOLVED" and .attemptStatus=="completed" and .runner.invocationCount==1 and .verificationRerunCount==1 and .actualMutatedPaths==["fixture.sh"] and .scopeViolations==[] and .evaluationSurfaceChanges==[] and .isolation=={"capability":"faulty-contained","backend":"disposable-workspace","adversarialBoundary":false,"liveRepositoryProviderAccess":false,"hostPatchImport":true,"processIsolation":false,"hostFilesystemIsolation":false,"networkIsolation":false} and .candidate.policyViolations==[] and .import.liveBaselineMatched==true and .import.applied==true and .import.importedDigest==.candidate.candidateDigest and .judgment==null' <<<"$resolved" >/dev/null || fail 'resolved result incorrect'; [ ! -e "$project/SHOULD_NOT_EXIST" ] || fail 'stored effectiveArgv executed'
result_file="$project/$(jq -r '.target.reference' <<<"$resolved")"; result_file="$(dirname "$result_file")/result.json"; repair_attempt_validate "$result_file" || fail 'attempt artifact invalid'; repair_target_validate "$(dirname "$result_file")/target.json" || fail 'target artifact invalid'
[ "$(stat -f '%Lp' "$(dirname "$result_file")/runner/stdout.log" 2>/dev/null || stat -c '%a' "$(dirname "$result_file")/runner/stdout.log")" = 600 ] || fail 'raw log permissions not private'; [ "$(wc -c < "$(dirname "$result_file")/runner/stdout.log" | tr -d ' ')" -le 65536 ] || fail 'raw log cap exceeded'; ! grep -R 'SECRET_DO_NOT_TELEMETRY' "$project/.mana/runtime/events" >/dev/null || fail 'provider output leaked to telemetry'

# A pre-existing dirty out-of-scope path is not falsely attributed, but a new
# mutation to that same dirty path is detected relative to immediate pre-state.
dirty_project="$tmp/dirty"; init_repo "$dirty_project"; printf user-dirty >> "$dirty_project/unrelated.txt"; dirty_origin="$(make_origin "$dirty_project" "$tmp/dirty.json")"; dirty_check="$(jq -r '.checks[]|select(.rerunDescriptor.path=="fixture.sh")|.checkId' "$dirty_origin")"
dirty_result="$(repair "$dirty_project" "$stub" "$dirty_origin" "$dirty_check")" || fail 'repair with pre-existing dirty path failed'; jq -e '.comparison=="RESOLVED" and .actualMutatedPaths==["fixture.sh"]' <<<"$dirty_result" >/dev/null || fail 'pre-existing dirty path falsely attributed'

# Multiple failed concerns require selection; an explicit repair compares only
# its bounded cohort and ignores the unrelated historical failure.
multi_project="$tmp/multi"; init_repo "$multi_project"; printf '#!/usr/bin/env bash\ntrue\n' > "$multi_project/second.sh"; git -C "$multi_project" add second.sh; git -C "$multi_project" commit -qm second; printf '#!/usr/bin/env bash\nif then\n' > "$multi_project/second.sh"; multi_origin="$(make_origin "$multi_project" "$tmp/multi.json")"; multi_check="$(jq -r '.checks[]|select(.rerunDescriptor.path=="fixture.sh")|.checkId' "$multi_origin")"
multi_plan="$(MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$stub" "$root/scripts/mana-repair.sh" --project-root "$multi_project" --from "$multi_origin" --allow-path fixture.sh --runner stub --once --dry-run --json 2>/dev/null || true)"; jq -e '.eligibility=="requires_human" and (.reason|contains("explicit --check"))' <<<"$multi_plan" >/dev/null || fail 'multiple failures were selected automatically'
multi_result="$(repair "$multi_project" "$stub" "$multi_origin" "$multi_check")" || fail 'explicit bounded cohort repair failed'; jq -e '.comparison=="RESOLVED" and .newRequiredFailures==[] and .verificationRerunCount==1' <<<"$multi_result" >/dev/null || fail 'unrelated baseline failure contaminated comparison'

# Tampering is blocked by the canonical evidence digest.
tamper_project="$tmp/tamper"; init_repo "$tamper_project"; tamper_origin="$(make_origin "$tamper_project" "$tmp/tamper.json")"; tamper_check="$(jq -r '.checks[0].checkId' "$tamper_origin")"; jq '.checks[0].result="passed"' "$tamper_origin" > "$tmp/t"; mv "$tmp/t" "$tamper_origin"
blocked="$(MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$stub" "$root/scripts/mana-repair.sh" --project-root "$tamper_project" --from "$tamper_origin" --check "$tamper_check" --allow-path fixture.sh --runner stub --once --dry-run --json 2>/dev/null || true)"; jq -e '.eligibility=="blocked" and (.reason|contains("digest"))' <<<"$blocked" >/dev/null || fail 'tampered evidence not blocked'

# Malicious descriptors are rejected as data before planning or dispatch.
descriptor_project="$tmp/descriptor"; init_repo "$descriptor_project"; descriptor_origin="$(make_origin "$descriptor_project" "$tmp/descriptor.json")"; descriptor_check="$(jq -r '.checks[0].checkId' "$descriptor_origin")"; jq '.checks[0].rerunDescriptor.path="../escape.sh"' "$descriptor_origin" > "$tmp/descriptor-tampered"; mv "$tmp/descriptor-tampered" "$descriptor_origin"; verification_digest_file "$descriptor_origin" > "$(dirname "$descriptor_origin")/result.sha256"
descriptor_plan="$(MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$stub" "$root/scripts/mana-repair.sh" --project-root "$descriptor_project" --from "$descriptor_origin" --check "$descriptor_check" --allow-path fixture.sh --runner stub --once --dry-run --json 2>/dev/null || true)"; jq -e '.eligibility=="blocked"' <<<"$descriptor_plan" >/dev/null || fail 'malicious rerun descriptor accepted'

# Old canonical v1 evidence remains readable but is explicitly non-repairable.
old_project="$tmp/old"; init_repo "$old_project"; old_origin="$(make_origin "$old_project" "$tmp/old.json")"; old_check="$(jq -r '.checks[0].checkId' "$old_origin")"
jq 'del(.frameworkIdentity,.rerunOf) | .schemaVersion="1" | .checks |= map(del(.adapterImplementationDigest,.concernKey,.evaluationSurface,.rerunDescriptor))' "$old_origin" > "$tmp/v1"; mv "$tmp/v1" "$old_origin"; verification_result_validate "$old_origin" || fail 'v1 compatibility validation failed'; verification_digest_file "$old_origin" > "$(dirname "$old_origin")/result.sha256"
old_plan="$(MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$stub" "$root/scripts/mana-repair.sh" --project-root "$old_project" --from "$old_origin" --check "$old_check" --allow-path fixture.sh --runner stub --once --dry-run --json 2>/dev/null || true)"; jq -e '.eligibility=="not_repairable" and (.reason|contains("rerun verification first"))' <<<"$old_plan" >/dev/null || fail 'v1 evidence diagnostic incorrect'

# Unsupported Java and governance identities deterministically require humans.
unsupported_project="$tmp/unsupported"; init_repo "$unsupported_project"; unsupported_origin="$(make_origin "$unsupported_project" "$tmp/unsupported.json")"; unsupported_check="$(jq -r '.checks[0].checkId' "$unsupported_origin")"
for tuple in 'java-targeted-build-verification java_approved_test' 'mana-governance-regression-verification mana_eval'; do set -- $tuple; jq --arg skill "$1" --arg adapter "$2" '.checks[0].skillId=$skill | .checks[0].adapter=$adapter' "$unsupported_origin" > "$tmp/unsupported-result"; mv "$tmp/unsupported-result" "$unsupported_origin"; verification_digest_file "$unsupported_origin" > "$(dirname "$unsupported_origin")/result.sha256"; unsupported_plan="$(MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$stub" "$root/scripts/mana-repair.sh" --project-root "$unsupported_project" --from "$unsupported_origin" --check "$unsupported_check" --allow-path fixture.sh --runner stub --once --dry-run --json 2>/dev/null || true)"; jq -e '.eligibility=="requires_human"' <<<"$unsupported_plan" >/dev/null || fail "unsupported $2 target did not require human"; done

# No-op is UNCHANGED and textual success is ignored.
noop_project="$tmp/noop"; init_repo "$noop_project"; noop_origin="$(make_origin "$noop_project" "$tmp/noop.json")"; noop_check="$(jq -r '.checks[0].checkId' "$noop_origin")"; noop="$tmp/noop-stub"; make_stub "$noop" 'echo success'
noop_result="$(repair "$noop_project" "$noop" "$noop_origin" "$noop_check")" || fail 'no-op attempt failed'; jq -e '.comparison=="UNCHANGED" and .actualMutatedPaths==[] and .runner.invocationCount==1' <<<"$noop_result" >/dev/null || fail 'no-op comparison incorrect'

# Out-of-scope candidate mutation stops before import and leaves live files intact.
scope_project="$tmp/scope"; init_repo "$scope_project"; scope_origin="$(make_origin "$scope_project" "$tmp/scope.json")"; scope_check="$(jq -r '.checks[0].checkId' "$scope_origin")"; outside="$tmp/outside-stub"; make_stub "$outside" 'printf '\''#!/usr/bin/env bash\ntrue\n'\'' > fixture.sh; printf changed >> unrelated.txt'
scope_result="$(repair "$scope_project" "$outside" "$scope_origin" "$scope_check" || true)"; jq -e '.comparison=="UNKNOWN" and .attemptStatus=="policy_violation" and .stopReason=="candidate_policy_violation" and .verificationRerunCount==0 and .import.applied==false and (.scopeViolations|index("unrelated.txt"))' <<<"$scope_result" >/dev/null || fail 'scope violation result incorrect'; [ "$(cat "$scope_project/unrelated.txt")" = base ] || fail 'scope violation reached live repository'; grep -Fq 'if then' "$scope_project/fixture.sh" || fail 'authorized candidate was partly imported despite violation'

# Protected governance mutation is both out of scope and never rerun.
guard_project="$tmp/guard"; init_repo "$guard_project"; guard_origin="$(make_origin "$guard_project" "$tmp/guard.json")"; guard_check="$(jq -r '.checks[0].checkId' "$guard_origin")"; guard="$tmp/guard-stub"; make_stub "$guard" 'printf extra >> .gitignore'
guard_result="$(repair "$guard_project" "$guard" "$guard_origin" "$guard_check" || true)"; jq -e '.comparison=="UNKNOWN" and .verificationRerunCount==0 and (.scopeViolations|index(".gitignore")) and (.evaluationSurfaceChanges|index(".gitignore"))' <<<"$guard_result" >/dev/null || fail 'protected surface mutation not detected'; [ "$(cat "$guard_project/.gitignore")" = '.mana/' ] || fail 'candidate governance mutation reached live repository'

# Non-zero and timeout after partial mutation never trigger verification retry.
exit_project="$tmp/exit"; init_repo "$exit_project"; exit_origin="$(make_origin "$exit_project" "$tmp/exit.json")"; exit_check="$(jq -r '.checks[0].checkId' "$exit_origin")"; exits="$tmp/exit-stub"; make_stub "$exits" 'printf '\''#!/usr/bin/env bash\ntrue\n'\'' > fixture.sh; exit 7'
exit_result="$(repair "$exit_project" "$exits" "$exit_origin" "$exit_check" || true)"; jq -e '.comparison=="UNKNOWN" and .attemptStatus=="runner_failed" and .verificationRerunCount==0 and .runner.exitCode==7' <<<"$exit_result" >/dev/null || fail 'non-zero runner handling incorrect'
timeout_project="$tmp/timeout"; init_repo "$timeout_project"; timeout_origin="$(make_origin "$timeout_project" "$tmp/timeout.json")"; timeout_check="$(jq -r '.checks[0].checkId' "$timeout_origin")"; timeout_stub="$tmp/timeout-stub"; make_stub "$timeout_stub" 'printf changed >> fixture.sh; sleep 20'
timeout_result="$(MANA_REPAIR_RUNNER_SECONDS=1 repair "$timeout_project" "$timeout_stub" "$timeout_origin" "$timeout_check" || true)"; jq -e '.comparison=="UNKNOWN" and .attemptStatus=="runner_timed_out" and .verificationRerunCount==0 and .runner.timedOut==true' <<<"$timeout_result" >/dev/null || fail 'runner timeout handling incorrect'

# A provider leader that returns while a child survives is infrastructure
# uncertainty, not a successful repair eligible for a verification rerun.
descendant_project="$tmp/descendant"; init_repo "$descendant_project"; descendant_origin="$(make_origin "$descendant_project" "$tmp/descendant.json")"; descendant_check="$(jq -r '.checks[0].checkId' "$descendant_origin")"; descendant_stub="$tmp/descendant-stub"; make_stub "$descendant_stub" '(sleep 5) & exit 0'
descendant_result="$(repair "$descendant_project" "$descendant_stub" "$descendant_origin" "$descendant_check" || true)"; jq -e '.comparison=="UNKNOWN" and .attemptStatus=="runner_timed_out" and .runner.descendantsTerminated==true and .verificationRerunCount==0' <<<"$descendant_result" >/dev/null || fail 'descendant cleanup qualified for verification'

# Unsafe grants and unsupported Java/governance adapters never reach provider.
if "$root/scripts/mana-repair.sh" --project-root "$timeout_project" --from "$timeout_origin" --check "$timeout_check" --allow-path ../fixture.sh --runner stub --once --dry-run >/dev/null 2>&1; then fail 'path traversal accepted'; fi
if "$root/scripts/mana-repair.sh" --project-root "$timeout_project" --from "$timeout_origin" --check "$timeout_check" --allow-path "$timeout_project/fixture.sh" --runner stub --once --dry-run >/dev/null 2>&1; then fail 'absolute allow path accepted'; fi

echo 'Bounded repair tests passed'
