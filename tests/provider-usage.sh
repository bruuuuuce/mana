#!/usr/bin/env bash
# CTX-01 deterministic provider-stub coverage. No model or network call runs.
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/provider-execution.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-provider-usage.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project with spaces"; temporary="$tmp/temporary files with spaces"; mkdir -p "$project" "$temporary" "$tmp/bin"
fail() { echo "FAIL: $*" >&2; exit 1; }
assert_no_temporary_trace() {
  ! find "$temporary" \( -name 'mana-provider-events.*' -o -name 'mana-provider-final.*' \) -print | grep -q . || fail "$1 left a temporary provider file"
}
cp "$root/tests/fixtures/context-runtime/provider-usage-stub.sh" "$tmp/bin/codex"
cp "$root/tests/fixtures/context-runtime/provider-no-usage-stub.sh" "$tmp/bin/claude"
chmod +x "$tmp/bin/codex"
chmod +x "$tmp/bin/claude"

run_case() {
  local case_id="$1" scenario="$2" retain="${3:-false}" output result
  output="$tmp/$case_id.out"
  MANA_PROVIDER_ARGS=(exec --model fixture)
  if PATH="$tmp/bin:$PATH" TMPDIR="$temporary" MANA_RUNTIME_EXECUTION_ID="execution-$case_id" MANA_PROVIDER_USAGE_SCENARIO="$scenario" MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE="$retain" mana_provider_execute codex "$project" fixture-profile 'fixture prompt must not persist' codex "${MANA_PROVIDER_ARGS[@]}" >"$output" 2>"$tmp/$case_id.err"; then
    return 0
  else
    result=$?
  fi
  cat "$tmp/$case_id.err" >&2
  return "$result"
}

run_case complete complete || fail 'complete fixture failed'
complete="$project/.mana/runtime/metrics/execution-complete/usage-summary-v1.json"
python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/context-runtime/usage-summary-v1.schema.json" "$complete" || fail 'complete summary does not validate'
jq -e '.usageStatus == "measured" and .status == "complete" and .totals == {input:120,cachedInput:30,uncachedInput:90,output:25,reasoning:7} and .turns == 1 and .toolCalls == 1 and .rawTraceRetained == false' "$complete" >/dev/null || fail 'complete usage was not parsed'
grep -Fxq 'human final message' "$tmp/complete.out" || fail 'final message was not relayed'
assert_no_temporary_trace complete
[ "$(stat -f '%Lp' "$project/.mana/runtime/metrics/execution-complete")" = 700 ] || fail 'metrics directory permissions are not restrictive'
[ "$(stat -f '%Lp' "$complete")" = 600 ] || fail 'JSON summary permissions are not restrictive'
[ "$(stat -f '%Lp' "${complete%.json}.md")" = 600 ] || fail 'Markdown summary permissions are not restrictive'
! grep -R -Fq 'PAYLOAD-MUST-NOT-LEAK' "$project/.mana/runtime/metrics" || fail 'tool payload leaked into metrics'
! grep -R -Eqi 'fixture prompt|human final message|partial final message' "$project/.mana/runtime/metrics" || fail 'prompt or response leaked into metrics'

run_case missing missing || fail 'missing usage fixture failed'
missing="$project/.mana/runtime/metrics/execution-missing/usage-summary-v1.json"
jq -e '.usageStatus == "unavailable" and .totals.input == null and .totals.cachedInput == null and .totals.uncachedInput == null and .totals.output == null and .totals.reasoning == null' "$missing" >/dev/null || fail 'missing usage was inferred'

run_case malformed malformed || fail 'malformed JSONL fixture failed'
malformed="$project/.mana/runtime/metrics/execution-malformed/usage-summary-v1.json"
jq -e '.usageStatus == "unavailable" and .parseErrors == 1 and .rawTraceRetained == false' "$malformed" >/dev/null || fail 'malformed JSONL was not represented safely'
assert_no_temporary_trace malformed-jsonl

for invalid_case in float negative numeric-string null large-invalid; do
  run_case "$invalid_case" "$invalid_case" || fail "$invalid_case fixture crashed the wrapper"
  invalid="$project/.mana/runtime/metrics/execution-$invalid_case/usage-summary-v1.json"
  python3 "$root/tests/lib/json_schema_subset.py" "$root/contracts/context-runtime/usage-summary-v1.schema.json" "$invalid" || fail "$invalid_case summary does not validate"
  jq -e '.status == "complete" and .usageStatus == "unavailable" and .totals.input == null and .parseErrors == 1' "$invalid" >/dev/null || fail "$invalid_case usage was not rejected safely"
  assert_no_temporary_trace "$invalid_case usage"
done
run_case large-valid large-valid || fail 'large valid integer fixture failed'
large_valid="$project/.mana/runtime/metrics/execution-large-valid/usage-summary-v1.json"
jq -e '.usageStatus == "measured" and .totals.input == 9007199254740991 and .parseErrors == 0' "$large_valid" >/dev/null || fail 'large supported integer was not retained exactly'

if run_case interrupted interrupted; then fail 'interrupted fixture succeeded'; fi
interrupted="$project/.mana/runtime/metrics/execution-interrupted/usage-summary-v1.json"
jq -e '.status == "interrupted" and .usageStatus == "measured" and .totals.input == 5' "$interrupted" >/dev/null || fail 'interrupted run has no partial usage artifact'

if run_case failure failure; then fail 'provider failure fixture succeeded'; fi
failure="$project/.mana/runtime/metrics/execution-failure/usage-summary-v1.json"
jq -e '.status == "failed" and .usageStatus == "measured" and .totals.input == 8 and .totals.output == 2' "$failure" >/dev/null || fail 'provider failure has no partial usage artifact'
assert_no_temporary_trace provider-failure

run_case retained complete true || fail 'debug retention fixture failed'
retained_dir="$project/.mana/runtime/metrics/execution-retained"
jq -e '.rawTraceRetained == true' "$retained_dir/usage-summary-v1.json" >/dev/null || fail 'debug retention was not recorded'
[ -f "$retained_dir/raw-provider-events.jsonl" ] || fail 'debug raw trace missing'
[ "$(stat -f '%Lp' "$retained_dir/raw-provider-events.jsonl")" = 600 ] || fail 'debug raw trace permissions are not restrictive'
assert_no_temporary_trace debug-retention
[ "$(find "$project/.mana/runtime/metrics" -name raw-provider-events.jsonl -print | wc -l | tr -d ' ')" = 1 ] || fail 'raw trace survived outside explicit debug retention'
grep -Fq 'raw provider event retention is enabled locally' "$tmp/retained.err" || fail 'debug retention warning missing'

MANA_PROVIDER_ARGS=(exec)
if PATH="$tmp/bin:$PATH" TMPDIR="$temporary" MANA_RUNTIME_EXECUTION_ID=execution-invalid-retention MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE=invalid mana_provider_execute codex "$project" fixture-profile prompt codex "${MANA_PROVIDER_ARGS[@]}" >/dev/null 2>&1; then fail 'invalid raw trace opt-in was accepted'; fi
if PATH="$tmp/bin:$PATH" TMPDIR="$temporary" MANA_RUNTIME_EXECUTION_ID='../../outside' mana_provider_execute codex "$project" fixture-profile prompt codex "${MANA_PROVIDER_ARGS[@]}" >/dev/null 2>&1; then fail 'unsafe execution id was accepted'; fi

MANA_PROVIDER_ARGS=(-p)
PATH="$tmp/bin:$PATH" TMPDIR="$temporary" MANA_RUNTIME_EXECUTION_ID=execution-no-usage mana_provider_execute claude "$project" fixture-profile 'fixture prompt must not persist' claude "${MANA_PROVIDER_ARGS[@]}" > "$tmp/no-usage.out" || fail 'unstructured provider fixture failed'
no_usage="$project/.mana/runtime/metrics/execution-no-usage/usage-summary-v1.json"
jq -e '.provider == "claude" and .usageStatus == "unavailable" and .totals.input == null and .turns == null and .rawTraceRetained == false' "$no_usage" >/dev/null || fail 'unstructured provider usage was inferred'
grep -Fxq 'provider final message without structured usage' "$tmp/no-usage.out" || fail 'unstructured provider final output changed'

assert_provider_argv() {
  local provider="$1" program="$2" prompt="prompt with spaces -- and repeated flags" index=1 actual expected expected_file actual_file
  expected_file="$tmp/$provider.expected"
  actual_file="$tmp/$provider.actual"
  shift 2
  { printf '%s\n' "$(( $# + 1 ))"; printf '%s\n' "$@"; printf '%s\n' "$prompt"; } > "$expected_file"
  if [ "$provider" = codex ]; then
    mana_provider_usage_args() { MANA_PROVIDER_USAGE_ARGS=(--json --output-last-message "$tmp/fixed final message"); }
    { printf '%s\n' "$(( $# + 4 ))"; printf '%s\n' "$@"; printf '%s\n' --json --output-last-message "$tmp/fixed final message" "$prompt"; } > "$expected_file"
  fi
  PATH="$tmp/bin:$PATH" TMPDIR="$temporary" MANA_RUNTIME_EXECUTION_ID="execution-argv-$provider" MANA_PROVIDER_USAGE_SCENARIO=argv MANA_PROVIDER_ARG_CAPTURE="$actual_file" mana_provider_execute "$provider" "$project" fixture-profile "$prompt" "$program" "$@" || fail "$provider argv fixture failed"
  while IFS= read -r expected; do
    actual="$(sed -n "${index}p" "$actual_file")"
    [ "$actual" = "$expected" ] || fail "$provider argv element $((index - 1)) changed"
    index=$((index + 1))
  done < "$expected_file"
  [ "$(wc -l < "$actual_file" | tr -d ' ')" = "$(wc -l < "$expected_file" | tr -d ' ')" ] || fail "$provider argc changed"
}

# Positional provider argv must retain each element (including repeats and
# spaces) for every adapter. The fixture compares argc and every argument.
assert_provider_argv codex codex exec --model 'model with spaces' -c 'quoted value = "a b"' --flag repeat --flag repeat
assert_provider_argv claude claude -p --model 'model with spaces' --allowedTools 'Read, Edit' --flag repeat --flag repeat
cp "$tmp/bin/claude" "$tmp/bin/opencode"
assert_provider_argv opencode opencode run --dir 'directory with spaces' --model 'model with spaces' --flag repeat --flag repeat

run_interruption_case() {
  local signal_name="$1" expected_status="$2" case_id ready delivered pid status deadline
  case_id="signal-$(printf '%s' "$signal_name" | tr '[:upper:]' '[:lower:]')"
  ready="$tmp/$signal_name.ready"
  delivered="$tmp/$signal_name.delivered"
  MANA_PROVIDER_ARGS=(exec --model fixture)
  PATH="$tmp/bin:$PATH" TMPDIR="$temporary" MANA_RUNTIME_EXECUTION_ID="execution-$case_id" MANA_PROVIDER_USAGE_SCENARIO=wait-for-signal MANA_PROVIDER_SIGNAL_READY="$ready" MANA_PROVIDER_SIGNAL_DELIVERED="$delivered" mana_provider_execute codex "$project" fixture-profile prompt codex "${MANA_PROVIDER_ARGS[@]}" >"$tmp/$case_id.out" 2>"$tmp/$case_id.err" &
  pid=$!
  deadline=$((SECONDS + 5))
  while [ ! -f "$ready" ] && [ "$SECONDS" -lt "$deadline" ]; do sleep 0.05; done
  [ -f "$ready" ] || fail "$signal_name provider stub did not become ready"
  trace="$(find "$temporary" -name 'mana-provider-events.*' -print)"
  [ -n "$trace" ] && [ "$(stat -f '%Lp' "$trace")" = 600 ] || fail "$signal_name temporary raw trace permissions are not restrictive"
  kill -"$signal_name" "$pid"
  if wait "$pid"; then fail "$signal_name interruption became success"; else status=$?; fi
  [ "$status" = "$expected_status" ] || fail "$signal_name exit status changed: $status"
  deadline=$((SECONDS + 5))
  while [ ! -f "$delivered" ] && [ "$SECONDS" -lt "$deadline" ]; do sleep 0.05; done
  [ -f "$delivered" ] || fail "$signal_name signal-delivery acknowledgement was not written"
  [ "$(cat "$delivered")" = TERM ] || fail "$signal_name was not delivered to the provider stub as SIGTERM"
  summary="$project/.mana/runtime/metrics/execution-$case_id/usage-summary-v1.json"
  if ! jq -e '.status == "interrupted" and .usageStatus == "measured" and .totals.input == 5' "$summary" >/dev/null; then
    cat "$tmp/$case_id.err" >&2
    fail "$signal_name interruption did not write a safe partial summary"
  fi
  assert_no_temporary_trace "$signal_name interruption"
}
run_interruption_case TERM 143
run_interruption_case INT 130
"$root/scripts/mana-runtime.sh" --project-root "$project" metrics execution-complete --json | jq -e '.executionId == "execution-complete" and .usageStatus == "measured"' >/dev/null || fail 'metrics inspection command did not expose the summary'

echo 'Provider usage observability tests passed'
