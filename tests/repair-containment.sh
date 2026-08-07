#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"; tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-containment-tests.XXXXXX")"; trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
init_repo() {
  mkdir -p "$1"; git -C "$1" init -q; git -C "$1" config user.email test@example.invalid; git -C "$1" config user.name Test; git -C "$1" config commit.gpgsign false
  printf '#!/usr/bin/env bash\ntrue\n' > "$1/fixture.sh"; printf 'base\n' > "$1/unrelated.txt"; printf '.mana/\n' > "$1/.gitignore"; git -C "$1" add .; git -C "$1" commit -qm base
  printf '#!/usr/bin/env bash\nif then\n' > "$1/fixture.sh"
}
make_origin() { "$root/scripts/mana-verify.sh" --project-root "$1" --skill shell-syntax-verification --json > "$tmp/verify.json" && fail 'invalid shell fixture passed'; find "$1/.mana" -path '*/evidence/verification/*/result.json' -type f | tail -n1; }
make_stub() { printf '%s\n' '#!/usr/bin/env bash' "$2" > "$1"; chmod +x "$1"; }
run_case() {
  local name="$1" body="$2" project stub origin check
  local -a repair_args
  project="$tmp/$name"; stub="$tmp/$name.stub"
  init_repo "$project"; origin="$(make_origin "$project")"; check="$(jq -r '.checks[0].checkId' "$origin")"; make_stub "$stub" "$body"
  repair_args=("$root/scripts/mana-repair.sh" --project-root "$project" --from "$origin" --check "$check" --allow-path fixture.sh --runner stub --once --json)
  if [ "$name" = drift ]; then
    MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$stub" LIVE_TARGET="$project/fixture.sh" STUB_PWD_CAPTURE="$tmp/$name.pwd" "${repair_args[@]}" > "$tmp/$name.json" || true
  else
    MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$stub" STUB_PWD_CAPTURE="$tmp/$name.pwd" "${repair_args[@]}" > "$tmp/$name.json" || true
  fi
  CASE_PROJECT="$project"; CASE_RESULT="$tmp/$name.json"
}
assert_rejected_unchanged() {
  jq -e '.comparison=="UNKNOWN" and .attemptStatus=="policy_violation" and .verificationRerunCount==0 and .import.applied==false and (.candidate.policyViolations|length)>0' "$CASE_RESULT" >/dev/null || fail "$1 candidate was not rejected"
  grep -Fq 'if then' "$CASE_PROJECT/fixture.sh" || fail "$1 changed the live target"
  [ "$(cat "$CASE_PROJECT/unrelated.txt")" = base ] || fail "$1 changed an unrelated live file"
}

# Positive dogfood: provider cwd is a fresh control-plane-free copy, host
# imports exactly the target content, and the verifier reruns on the live repo.
run_case normal '[ ! -e .git ]; [ ! -e .mana ]; [ -z "${OLDPWD+x}" ]; [ -z "${MANA_PROJECT_ROOT+x}" ]; [ -z "${LIVE_TARGET+x}" ]; printf "%s\n" "$PWD" > "$STUB_PWD_CAPTURE"; printf "%s\n" "$PWD"; printf '\''#!/usr/bin/env bash\ntrue\n'\'' > fixture.sh'
jq -e '.comparison=="RESOLVED" and .attemptStatus=="completed" and .candidate.changedPaths==["fixture.sh"] and .candidate.policyViolations==[] and .import.liveBaselineMatched==true and .import.applied==true and .verificationRerunCount==1' "$CASE_RESULT" >/dev/null || fail 'positive staged repair did not resolve'
candidate_path="$(cat "$tmp/normal.pwd")"; [ "$candidate_path" != "$CASE_PROJECT" ] || fail 'provider ran in live repository'; [ ! -e "$candidate_path" ] || fail 'disposable workspace was not cleaned'; [ "$(cat "$CASE_PROJECT/fixture.sh")" = '#!/usr/bin/env bash
true' ] || fail 'host import did not publish candidate content'
if grep -R -F "$candidate_path" "$CASE_PROJECT/.mana" >/dev/null; then grep -R -n -F "$candidate_path" "$CASE_PROJECT/.mana" >&2; fail 'absolute disposable path leaked into durable evidence or telemetry'; fi
grep -R -F '[DISPOSABLE_WORKSPACE]/project' "$CASE_PROJECT/.mana" >/dev/null || fail 'disposable path in runner output was not redacted'

# Policy-violation dogfood and each unsupported delta shape: nothing imports.
run_case unrelated 'printf '\''#!/usr/bin/env bash\ntrue\n'\'' > fixture.sh; printf changed >> unrelated.txt'; assert_rejected_unchanged unrelated; jq -e '.candidate.changedPaths==["fixture.sh","unrelated.txt"] and (.scopeViolations|index("unrelated.txt"))' "$CASE_RESULT" >/dev/null || fail 'unrelated candidate delta was not recorded'
run_case deleted 'rm fixture.sh'; assert_rejected_unchanged deletion; jq -e '.candidate.policyViolations|index("target_deleted")' "$CASE_RESULT" >/dev/null || fail 'target deletion reason missing'
run_case created 'printf new > extra.txt'; assert_rejected_unchanged creation; [ ! -e "$CASE_PROJECT/extra.txt" ] || fail 'candidate creation reached live repository'
run_case renamed 'mv fixture.sh renamed.sh'; assert_rejected_unchanged rename; [ ! -e "$CASE_PROJECT/renamed.sh" ] || fail 'candidate rename reached live repository'
run_case mode 'chmod +x fixture.sh'; assert_rejected_unchanged mode-change; jq -e '.candidate.policyViolations|index("target_mode_changed")' "$CASE_RESULT" >/dev/null || fail 'mode-only violation missing'
run_case symlink 'rm fixture.sh; ln -s unrelated.txt fixture.sh'; assert_rejected_unchanged symlink; [ ! -L "$CASE_PROJECT/fixture.sh" ] || fail 'candidate symlink reached live repository'
run_case directory 'rm fixture.sh; mkdir fixture.sh'; assert_rejected_unchanged directory
run_case binary 'printf "\\000" > fixture.sh'; assert_rejected_unchanged binary; jq -e '.candidate.policyViolations|index("target_not_supported_text")' "$CASE_RESULT" >/dev/null || fail 'binary candidate was not identified'
run_case patch 'printf '\''#!/usr/bin/env bash\ntrue\n'\'' > fixture.sh; printf '\''claims arbitrary changes\n'\'' > malicious.patch'; assert_rejected_unchanged stored-patch; [ ! -e "$CASE_PROJECT/malicious.patch" ] || fail 'provider-authored patch was trusted'
run_case sibling 'printf '\''#!/usr/bin/env bash\ntrue\n'\'' > fixture.sh; printf escaped > ../outside-project'; assert_rejected_unchanged sibling-write; jq -e '.candidate.workspaceIntegrity==false and (.candidate.policyViolations|index("candidate_workspace_root_changed"))' "$CASE_RESULT" >/dev/null || fail 'write outside disposable project root was not identified'
run_case mana 'mkdir .mana; printf fake > .mana/result.json'; assert_rejected_unchanged staged-mana; jq -e '.candidate.policyViolations|index("control_plane_mana_created_or_changed")' "$CASE_RESULT" >/dev/null || fail 'staged .mana creation not identified'; [ -d "$CASE_PROJECT/.mana" ] || fail 'live Mana control plane was damaged'
run_case git 'mkdir .git; printf fake > .git/claim'; assert_rejected_unchanged staged-git; jq -e '.candidate.policyViolations|index("control_plane_git_created_or_changed")' "$CASE_RESULT" >/dev/null || fail 'staged .git creation not identified'; git -C "$CASE_PROJECT" status --porcelain >/dev/null || fail 'live Git metadata was damaged'
run_case destroyed 'rm -rf "$PWD"'; jq -e '.comparison=="UNKNOWN" and .attemptStatus=="policy_violation" and .candidate.workspaceIntegrity==false and .import.applied==false and .verificationRerunCount==0' "$CASE_RESULT" >/dev/null || fail 'destroyed staging workspace did not fail closed'; grep -Fq 'if then' "$CASE_PROJECT/fixture.sh" || fail 'destroyed staging affected live target'

# Legitimate pre-existing dirty state is the baseline and is importable.
run_case predirty 'printf '\''#!/usr/bin/env bash\ntrue\n'\'' > fixture.sh'
jq -e '.comparison=="RESOLVED" and .import.workingTreeState=="modified" and .import.liveBaselineMatched==true and .import.applied==true' "$CASE_RESULT" >/dev/null || fail 'pre-dirty target baseline was not supported'

# A same-UID process can deliberately reach a supplied host path; the import
# compare detects target drift and never overwrites or merges it.
run_case drift 'printf '\''#!/usr/bin/env bash\ntrue\n'\'' > fixture.sh; printf '\''external concurrent edit\n'\'' > "$LIVE_TARGET"'
jq -e '.comparison=="UNKNOWN" and .attemptStatus=="integrity_violation" and .stopReason=="live_target_drift" and .import.liveBaselineMatched==false and .import.applied==false and .verificationRerunCount==0' "$CASE_RESULT" >/dev/null || fail 'live target drift did not stop import'; [ "$(cat "$CASE_PROJECT/fixture.sh")" = 'external concurrent edit' ] || fail 'drifted live target was overwritten or merged'

# Runtime audit reconstructs the staged/import lifecycle without payloads.
events="$tmp/normal/.mana/runtime/events"; for event in repair.staging.created repair.candidate.inspected repair.import.applied repair.verification.started; do grep -R -F "\"eventType\":\"$event\"" "$events" >/dev/null || fail "runtime audit event missing: $event"; done
grep -R -F '"eventType":"repair.import.rejected"' "$tmp/unrelated/.mana/runtime/events" >/dev/null || fail 'rejected import audit event missing'
! grep -R -E 'claims arbitrary|external concurrent edit|BOUNDED MANA REPAIR CONTRACT|#!/usr/bin/env bash' "$tmp"/*/.mana/runtime/events >/dev/null || fail 'candidate, contract, or provider payload leaked to runtime audit'

echo 'Repair containment tests passed'
