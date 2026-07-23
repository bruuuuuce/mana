#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/run-testbook.sh --catalog <testbook.yaml> --test <id> [options]

Options:
  --environment <name>       Required environment name. Defaults to local.
  --allow-performance         Allow an approved performance entry.
  --artifacts-dir <path>     Directory for logs and run report.

Only entries with approved: true are executable. The command is read from the
selected catalog entry; this script does not accept arbitrary shell commands.
USAGE
}

catalog=""; test_id=""; environment="local"; allow_performance=false; artifacts_dir=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --catalog) catalog="${2:?--catalog requires a path}"; shift 2 ;;
    --test) test_id="${2:?--test requires an id}"; shift 2 ;;
    --environment) environment="${2:?--environment requires a value}"; shift 2 ;;
    --allow-performance) allow_performance=true; shift ;;
    --artifacts-dir) artifacts_dir="${2:?--artifacts-dir requires a path}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
  esac
done
[ -n "$catalog" ] && [ -f "$catalog" ] || { echo "ERROR: readable --catalog is required" >&2; exit 2; }
[ -n "$test_id" ] || { echo "ERROR: --test is required" >&2; exit 2; }

field() {
  local key="$1"
  awk -v target="$test_id" -v key="$key" '
    /^  - id: / { if (active) exit; value=$0; sub(/^  - id: "/, "", value); sub(/"$/, "", value); active=(value == target); next }
    active && $0 ~ "^    " key ": " { value=$0; sub("^    " key ": ", "", value); gsub(/^"|"$/, "", value); print value; exit }
  ' "$catalog"
}
kind="$(field kind)"; command="$(field command)"; approved="$(field approved)"; entry_environment="$(field environment)"; status="$(field execution_status)"; safety="$(field safety)"; timeout_seconds="$(field timeout_seconds)"
[ -n "$kind" ] || { echo "ERROR: test id not found: $test_id" >&2; exit 2; }
[ "$approved" = "true" ] || { echo "ERROR: $test_id is not approved in $catalog" >&2; exit 3; }
[ "$status" = "runnable" ] || { echo "ERROR: $test_id is $status; complete its prerequisites before execution" >&2; exit 3; }
[ "$entry_environment" = "$environment" ] || { echo "ERROR: $test_id requires environment $entry_environment, not $environment" >&2; exit 3; }
if [ "$kind" = "performance" ] && [ "$allow_performance" != true ]; then echo "ERROR: performance tests require --allow-performance" >&2; exit 3; fi
if [ "$safety" = "requires_explicit_performance_approval" ] && [ "$allow_performance" != true ]; then echo "ERROR: this entry requires explicit performance approval" >&2; exit 3; fi
[ -n "$timeout_seconds" ] || timeout_seconds=900
case "$timeout_seconds" in *[!0-9]*|'') echo "ERROR: invalid timeout_seconds for $test_id" >&2; exit 3 ;; esac

[ -n "$artifacts_dir" ] || artifacts_dir="$(dirname "$catalog")/test-runs/$test_id-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$artifacts_dir"
log_file="$artifacts_dir/command.log"; report_file="$artifacts_dir/run-report.yaml"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; started_epoch="$(date +%s)"
set +e
if command -v timeout >/dev/null 2>&1; then
  timeout "$timeout_seconds" bash -lc "$command" >"$log_file" 2>&1
  exit_code=$?
elif command -v perl >/dev/null 2>&1; then
  perl -e '$seconds = shift @ARGV; alarm $seconds; exec @ARGV' "$timeout_seconds" bash -lc "$command" >"$log_file" 2>&1
  exit_code=$?
else
  echo "ERROR: neither timeout nor perl is available to enforce timeout_seconds" >"$log_file"
  exit_code=3
fi
set -e
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; duration_seconds=$(( $(date +%s) - started_epoch ))
result="passed"; [ "$exit_code" -eq 0 ] || result="failed"
cat > "$report_file" <<EOF
test_id: "$test_id"
kind: "$kind"
environment: "$environment"
result: "$result"
exit_code: $exit_code
started_at: "$started_at"
finished_at: "$finished_at"
duration_seconds: $duration_seconds
timeout_seconds: $timeout_seconds
command_log: "$(basename "$log_file")"
EOF
echo "Test $test_id $result. Report: $report_file"
exit "$exit_code"
