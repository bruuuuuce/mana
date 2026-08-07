#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"; tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-loop-tests.XXXXXX")"; trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
mkdir -p "$tmp/bin"; real_bash="$(command -v bash)"
cat > "$tmp/bin/bash" <<EOF
#!$real_bash
case "\${1:-}" in */mana-verify.sh|*/mana-repair.sh|*/mana-repair-loop.sh) exec "$real_bash" "\$@";; esac
if [ "\${1:-}" = -n ]; then
  target="\${@: -1}"
  if grep -q '^TWO' "\$target"; then printf "\$target: line 1: syntax error near unexpected token 'OBS-A'\n\$target: line 2: syntax error near unexpected token 'OBS-B'\n" >&2; exit 2
  elif grep -q '^ONE' "\$target"; then printf "\$target: line 1: syntax error near unexpected token 'OBS-A'\n" >&2; exit 2
  elif grep -q '^NEW' "\$target"; then printf "\$target: line 1: syntax error near unexpected token 'OBS-C'\n" >&2; exit 2
  elif grep -q '^BLOCK' "\$target"; then printf 'controlled inconclusive\n' >&2; exit 125
  elif grep -q '^OK' "\$target"; then exit 0
  else printf 'OBS-UNKNOWN\n' >&2; exit 2; fi
fi
exec "$real_bash" "\$@"
EOF
chmod +x "$tmp/bin/bash"

cat > "$tmp/provider-stub" <<'EOF'
#!/bin/bash
count=0; [ ! -f "$STUB_COUNTER" ] || count="$(sed -n '1p' "$STUB_COUNTER")"; count=$((count+1)); printf '%s\n' "$count" > "$STUB_COUNTER"
printf '%s\n' "$PWD" >> "${STUB_PWD_LOG:-/dev/null}"
last=""; for arg in "$@"; do last="$arg"; done
[ "$count" -ne 2 ] || printf '%s\n' "$last" > "${STUB_SECOND_CONTRACT:-/dev/null}"
case "$STUB_SCENARIO:$count" in
  resolved:1) printf 'OK\n' > fixture.sh;;
  two_step:1|second_noop:1|second_regress:1|second_scope:1) printf 'ONE\n' > fixture.sh;;
  two_step:2) grep -q '^ONE' fixture.sh || exit 9; printf 'OK\n' > fixture.sh;;
  second_noop:2) :;;
  second_regress:2) printf 'NEW\n' > fixture.sh;;
  second_scope:2) printf changed >> unrelated.txt;;
  noop:1) echo 'provider claims partial progress';;
  regress_first:1) printf 'NEW\n' > fixture.sh;;
  scope_first:1) printf changed >> unrelated.txt;;
  integrity_first:1) printf changed >> .gitignore;;
  crash_first:1) exit 7;;
  timeout_first:1) sleep 20;;
  interrupt_first:1) sleep 3;;
  inconclusive_first:1) printf 'BLOCK\n' > fixture.sh;;
  budget:1) printf 'ONE\n' > fixture.sh;;
  *) :;;
esac
echo 'provider textual success/progress is not authoritative'
EOF
chmod +x "$tmp/provider-stub"

init_project() {
  local project="$1" initial="${2:-TWO}"; mkdir -p "$project"; git -C "$project" init -q; git -C "$project" config user.email test@example.invalid; git -C "$project" config user.name Test; git -C "$project" config commit.gpgsign false
  printf 'OK\n' > "$project/fixture.sh"; printf 'base\n' > "$project/unrelated.txt"; printf '.mana/\n' > "$project/.gitignore"; git -C "$project" add .; git -C "$project" commit -qm base
  if [ "$initial" = MANY ]; then i=0; while [ "$i" -lt 99 ]; do printf 'TWO-%s\n' "$i"; i=$((i+1)); done > "$project/fixture.sh"; else printf '%s\n' "$initial" > "$project/fixture.sh"; fi
}
make_origin() { local project="$1" capture="$2"; PATH="$tmp/bin:$PATH" "$root/scripts/mana-verify.sh" --project-root "$project" --skill shell-syntax-verification --json > "$capture" && fail 'controlled negative fixture passed'; find "$project/.mana" -path '*/evidence/verification/*/result.json' -type f | tail -n1; }
counter_for() { printf '%s/%s.count' "$tmp" "$1"; }
run_repair() { # project origin check scenario mode output [extra env already exported]
  local project="$1" origin="$2" check="$3" scenario="$4" mode="$5" output="$6" counter; counter="$(counter_for "$(basename "$project")-$scenario-$mode")"; rm -f "$counter"
  rm -f "$counter.pwds"
  PATH="$tmp/bin:$PATH" MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$tmp/provider-stub" STUB_COUNTER="$counter" STUB_PWD_LOG="$counter.pwds" STUB_SCENARIO="$scenario" STUB_SECOND_CONTRACT="$tmp/second-contract" "$root/scripts/mana-repair.sh" --project-root "$project" --from "$origin" --check "$check" --allow-path fixture.sh --runner stub $mode --json > "$output" || true
  RUN_COUNTER="$counter"
}
new_fixture() { local name="$1" initial="${2:-TWO}"; FIXTURE_PROJECT="$tmp/$name"; init_project "$FIXTURE_PROJECT" "$initial"; FIXTURE_ORIGIN="$(make_origin "$FIXTURE_PROJECT" "$tmp/$name-origin.json")"; FIXTURE_CHECK="$(jq -r '.checks[0].checkId' "$FIXTURE_ORIGIN")"; }

# CLI hard bound and default/single-attempt compatibility.
new_fixture default; run_repair "$FIXTURE_PROJECT" "$FIXTURE_ORIGIN" "$FIXTURE_CHECK" resolved '' "$tmp/default.json"; jq -e '.kind=="repair-attempt-result" and .comparison=="RESOLVED" and .runner.invocationCount==1' "$tmp/default.json" >/dev/null || fail 'default invocation is not repair_once'; [ "$(cat "$RUN_COUNTER")" = 1 ] || fail 'default invoked provider more than once'
for mode in '--once' '--max-iterations 1'; do new_fixture "single-${mode//[^a-z0-9]/}"; run_repair "$FIXTURE_PROJECT" "$FIXTURE_ORIGIN" "$FIXTURE_CHECK" resolved "$mode" "$tmp/single.json"; [ "$(cat "$RUN_COUNTER")" = 1 ] || fail "$mode invoked twice"; done
for invalid in 0 3 -1 nope 1.5; do if PATH="$tmp/bin:$PATH" "$root/scripts/mana-repair.sh" --project-root "$FIXTURE_PROJECT" --from "$FIXTURE_ORIGIN" --check "$FIXTURE_CHECK" --allow-path fixture.sh --runner stub --max-iterations "$invalid" --dry-run >/dev/null 2>&1; then fail "invalid iteration count accepted: $invalid"; fi; done

# Dry-run plans a possible, not guaranteed, second attempt and writes nothing.
new_fixture dry; before="$(find "$FIXTURE_PROJECT/.mana" -type f -exec cksum {} + | sort)"; PATH="$tmp/bin:$PATH" MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$tmp/provider-stub" "$root/scripts/mana-repair.sh" --project-root "$FIXTURE_PROJECT" --from "$FIXTURE_ORIGIN" --check "$FIXTURE_CHECK" --allow-path fixture.sh --runner stub --max-iterations 2 --dry-run --explain --json > "$tmp/dry.json"; after="$(find "$FIXTURE_PROJECT/.mana" -type f -exec cksum {} + | sort)"; [ "$before" = "$after" ] || fail 'loop dry-run wrote persistent state'; jq -e '.hardMaxIterations==2 and .attemptTwo.mayRun==true and (.attemptTwo.condition|contains("strict-subset")) and .persistentEffects==false' "$tmp/dry.json" >/dev/null || fail 'loop dry plan incorrect'

# A: first attempt resolves, therefore one invocation.
new_fixture scenario-a; run_repair "$FIXTURE_PROJECT" "$FIXTURE_ORIGIN" "$FIXTURE_CHECK" resolved '--max-iterations 2' "$tmp/a.json"; jq -e '.kind=="repair-loop-result" and .attemptsExecuted==1 and .finalResult=="RESOLVED" and .stopReason=="target_resolved" and .cost.runnerInvocations==1' "$tmp/a.json" >/dev/null || fail 'scenario A incorrect'; [ "$(cat "$RUN_COUNTER")" = 1 ] || fail 'scenario A invoked twice'

# B: exact strict subset enables the one final invocation, which resolves.
new_fixture scenario-b; run_repair "$FIXTURE_PROJECT" "$FIXTURE_ORIGIN" "$FIXTURE_CHECK" two_step '--max-iterations 2' "$tmp/b.json"; jq -e '.attemptsExecuted==2 and .attempts[0].comparison=="UNCHANGED" and .attempts[0].progress=="partial" and .attempts[1].comparison=="RESOLVED" and .finalResult=="RESOLVED" and .cost.runnerInvocations==2' "$tmp/b.json" >/dev/null || fail 'scenario B incorrect'; [ "$(cat "$RUN_COUNTER")" = 2 ] || fail 'scenario B did not invoke exactly twice'; grep -Fq 'FINAL allowed attempt' "$tmp/second-contract" || fail 'attempt two contract is not marked final'; grep -Fq 'One prior bounded attempt occurred' "$tmp/second-contract" || fail 'attempt two contract omits prior attempt context'
[ "$(wc -l < "$RUN_COUNTER.pwds" | tr -d ' ')" = 2 ] && [ "$(LC_ALL=C sort -u "$RUN_COUNTER.pwds" | wc -l | tr -d ' ')" = 2 ] || fail 'attempt two reused the attempt-one disposable workspace'; while IFS= read -r candidate; do [ ! -e "$candidate" ] || fail 'loop disposable workspace was not cleaned'; done < "$RUN_COUNTER.pwds"

# Attempt references/digests are immutable, valid, and atomically indexed.
loop_file="$FIXTURE_PROJECT/$(find "$FIXTURE_PROJECT/.mana" -path '*/evidence/repair-loop/*/result.json' -type f | tail -n1 | sed "s#^$FIXTURE_PROJECT/##")"; . "$root/scripts/lib/verification.sh"; . "$root/scripts/lib/repair.sh"; repair_loop_result_validate "$loop_file" || fail 'loop artifact invalid'
jq -c '.attempts[]' "$loop_file" | while IFS= read -r item; do ref="$(jq -r .reference <<<"$item")"; digest="$(jq -r .digest <<<"$item")"; [ "$(verification_digest_file "$FIXTURE_PROJECT/$ref")" = "$digest" ] || fail 'loop attempt digest mismatch'; repair_attempt_validate "$FIXTURE_PROJECT/$ref" || fail 'referenced attempt is invalid'; jq -e '.isolation.capability=="faulty-contained" and .import.applied==true' "$FIXTURE_PROJECT/$ref" >/dev/null || fail 'loop attempt did not use a validated host import'; done
! find "$(dirname "$loop_file")" -name '.*.tmp*' -print | grep -q . || fail 'partial loop publication remained'
jq '.unexpected=true' "$loop_file" > "$tmp/loop-unknown.json"; ! repair_loop_result_validate "$tmp/loop-unknown.json" || fail 'loop schema accepted an unknown field'
sed '1s/{/{"kind":"repair-loop-result",/' "$loop_file" > "$tmp/loop-duplicate.json"; ! repair_loop_result_validate "$tmp/loop-duplicate.json" || fail 'loop schema accepted a duplicate key'
loop_workspace="${loop_file%%/evidence/repair-loop/*}"; grep -Fq '## Repair Loops' "$loop_workspace/evidence/index.md" || fail 'repair loop evidence was not indexed'
# A structurally valid aggregate is not sufficient: referenced immutable
# evidence must still resolve and reconcile.  Tampering an attempt is caught
# by the contextual validator without trusting duplicated loop fields.
repair_loop_result_validate_context "$loop_file" "$FIXTURE_PROJECT" || fail 'loop contextual validation failed'
first_attempt_ref="$(jq -r '.attempts[0].reference' "$loop_file")"; cp "$FIXTURE_PROJECT/$first_attempt_ref" "$tmp/attempt-before-tamper"; jq '.stopReason="tampered"' "$FIXTURE_PROJECT/$first_attempt_ref" > "$tmp/tampered-attempt"; mv "$tmp/tampered-attempt" "$FIXTURE_PROJECT/$first_attempt_ref"; ! repair_loop_result_validate_context "$loop_file" "$FIXTURE_PROJECT" || fail 'aggregate accepted tampered referenced attempt'; mv "$tmp/attempt-before-tamper" "$FIXTURE_PROJECT/$first_attempt_ref"

# C: exact unchanged and textual claims never enable a second call.
new_fixture scenario-c; run_repair "$FIXTURE_PROJECT" "$FIXTURE_ORIGIN" "$FIXTURE_CHECK" noop '--max-iterations 2' "$tmp/c.json"; jq -e '.attemptsExecuted==1 and .finalResult=="UNCHANGED" and .stopReason=="no_progress" and .cost.runnerInvocations==1' "$tmp/c.json" >/dev/null || fail 'scenario C incorrect'; [ "$(cat "$RUN_COUNTER")" = 1 ] || fail 'no-progress attempt retried'

# D/E/F: second attempt always stops at the hard boundary.
new_fixture scenario-d; run_repair "$FIXTURE_PROJECT" "$FIXTURE_ORIGIN" "$FIXTURE_CHECK" second_noop '--max-iterations 2' "$tmp/d.json"; jq -e '.attemptsExecuted==2 and .finalResult=="UNCHANGED" and .stopReason=="hard_iteration_limit" and .cost.runnerInvocations==2' "$tmp/d.json" >/dev/null || fail 'scenario D incorrect'
new_fixture scenario-e; run_repair "$FIXTURE_PROJECT" "$FIXTURE_ORIGIN" "$FIXTURE_CHECK" second_regress '--max-iterations 2' "$tmp/e.json"; jq -e '.attemptsExecuted==2 and .finalResult=="REGRESSED" and .stopReason=="regressed" and .cost.runnerInvocations==2' "$tmp/e.json" >/dev/null || fail 'scenario E incorrect'
new_fixture scenario-f; run_repair "$FIXTURE_PROJECT" "$FIXTURE_ORIGIN" "$FIXTURE_CHECK" second_scope '--max-iterations 2' "$tmp/f.json"; jq -e '.attemptsExecuted==2 and .finalResult=="UNKNOWN" and .stopReason=="policy_violation" and .cost.runnerInvocations==2' "$tmp/f.json" >/dev/null || fail 'scenario F incorrect'

# REGRESSED, UNKNOWN, crash, timeout, scope/integrity, and inconclusive first
# attempts all stop after one invocation.
for scenario in regress_first scope_first integrity_first crash_first inconclusive_first; do new_fixture "stop-$scenario"; run_repair "$FIXTURE_PROJECT" "$FIXTURE_ORIGIN" "$FIXTURE_CHECK" "$scenario" '--max-iterations 2' "$tmp/stop.json"; jq -e '.attemptsExecuted==1 and .cost.runnerInvocations==1' "$tmp/stop.json" >/dev/null || fail "$scenario retried"; [ "$(cat "$RUN_COUNTER")" = 1 ] || fail "$scenario provider count exceeded one"; done
new_fixture stop-timeout; counter="$(counter_for timeout)"; rm -f "$counter"; PATH="$tmp/bin:$PATH" MANA_REPAIR_RUNNER_SECONDS=1 MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$tmp/provider-stub" STUB_COUNTER="$counter" STUB_SCENARIO=timeout_first "$root/scripts/mana-repair.sh" --project-root "$FIXTURE_PROJECT" --from "$FIXTURE_ORIGIN" --check "$FIXTURE_CHECK" --allow-path fixture.sh --runner stub --max-iterations 2 --json > "$tmp/timeout.json" || true; jq -e '.attemptsExecuted==1 and .finalResult=="UNKNOWN" and .stopReason=="runner_timeout" and .cost.runnerInvocations==1' "$tmp/timeout.json" >/dev/null || fail 'timeout retried'

# Total loop and cumulative line budgets prevent the second invocation.
new_fixture time-budget; counter="$(counter_for time-budget)"; rm -f "$counter"; PATH="$tmp/bin:$PATH" MANA_REPAIR_LOOP_SECONDS=1 MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$tmp/provider-stub" STUB_COUNTER="$counter" STUB_SCENARIO=two_step "$root/scripts/mana-repair.sh" --project-root "$FIXTURE_PROJECT" --from "$FIXTURE_ORIGIN" --check "$FIXTURE_CHECK" --allow-path fixture.sh --runner stub --max-iterations 2 --json > "$tmp/time-budget.json" || true; jq -e '.attemptsExecuted==1 and .stopReason=="repair_loop_budget_exhausted" and .cost.runnerInvocations==1' "$tmp/time-budget.json" >/dev/null || fail 'total loop budget not enforced'
new_fixture mutation-budget MANY; run_repair "$FIXTURE_PROJECT" "$FIXTURE_ORIGIN" "$FIXTURE_CHECK" budget '--max-iterations 2' "$tmp/mutation-budget.json"; jq -e '.attemptsExecuted==1 and .stopReason=="repair_loop_budget_exhausted" and .cumulativeMutation.changedLines==100' "$tmp/mutation-budget.json" >/dev/null || fail 'cumulative mutation budget not enforced'

# An interrupted governor never publishes or claims completion.
new_fixture concurrent; counter="$(counter_for concurrent)"; rm -f "$counter"; PATH="$tmp/bin:$PATH" MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$tmp/provider-stub" STUB_COUNTER="$counter" STUB_SCENARIO=interrupt_first "$root/scripts/mana-repair.sh" --project-root "$FIXTURE_PROJECT" --from "$FIXTURE_ORIGIN" --check "$FIXTURE_CHECK" --allow-path fixture.sh --runner stub --max-iterations 2 --json > "$tmp/concurrent-first.json" & first_loop_pid=$!
poll=0; while [ ! -f "$counter" ] && [ "$poll" -lt 50 ]; do sleep 0.1; poll=$((poll+1)); done; [ -f "$counter" ] || fail 'concurrency fixture never invoked provider'
if PATH="$tmp/bin:$PATH" MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$tmp/provider-stub" STUB_COUNTER="$tmp/concurrent-second" STUB_SCENARIO=resolved "$root/scripts/mana-repair.sh" --project-root "$FIXTURE_PROJECT" --from "$FIXTURE_ORIGIN" --check "$FIXTURE_CHECK" --allow-path fixture.sh --runner stub --max-iterations 2 --json >/dev/null 2>&1; then fail 'concurrent repair loop was accepted'; fi
[ "$(cat "$counter")" = 1 ] || fail 'concurrent loop reached a provider'; kill -TERM "$first_loop_pid"; wait "$first_loop_pid" 2>/dev/null || true

new_fixture interrupted; counter="$(counter_for interrupted)"; rm -f "$counter"; PATH="$tmp/bin:$PATH" MANA_REPAIR_ALLOW_STUB=true MANA_REPAIR_STUB_COMMAND="$tmp/provider-stub" STUB_COUNTER="$counter" STUB_SCENARIO=interrupt_first "$root/scripts/mana-repair.sh" --project-root "$FIXTURE_PROJECT" --from "$FIXTURE_ORIGIN" --check "$FIXTURE_CHECK" --allow-path fixture.sh --runner stub --max-iterations 2 --json > "$tmp/interrupted.json" & loop_pid=$!
poll=0; while [ ! -f "$counter" ] && [ "$poll" -lt 50 ]; do sleep 0.1; poll=$((poll+1)); done; [ -f "$counter" ] || fail 'interruption fixture never invoked provider'; kill -TERM "$loop_pid"; wait "$loop_pid" 2>/dev/null && fail 'interrupted loop returned success'
! find "$FIXTURE_PROJECT/.mana" -path '*/evidence/repair-loop/*/result.json' -type f | grep -q . || fail 'interrupted loop published completion evidence'
grep -R -q '"eventType":"repair_loop.interrupted"' "$FIXTURE_PROJECT/.mana/runtime/events" || fail 'interrupted loop omitted audit event'
! grep -R -q '"eventType":"repair_loop.completed"' "$FIXTURE_PROJECT/.mana/runtime/events" || fail 'interrupted loop claimed completion'

# Loop telemetry is metadata-only.
! grep -R -E 'OBS-A|OBS-B|provider textual|BOUNDED MANA REPAIR CONTRACT|FINAL allowed|TWO-' "$tmp/scenario-b/.mana/runtime/events" >/dev/null || fail 'sensitive loop content leaked into runtime telemetry'

echo 'Bounded repair loop tests passed'
