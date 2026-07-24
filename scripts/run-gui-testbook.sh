#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/run-gui-testbook.sh --catalog <gui-testbook.yaml> --test <id> [options]

Options:
  --environment <name>       Required isolated environment name. Defaults to dedicated_test.
  --artifacts-dir <path>     Directory for reports and Playwright artifacts.

Runs only approved, runnable GUI entries from an isolated-test Playwright catalog.
USAGE
}

catalog=""; test_id=""; environment="dedicated_test"; artifacts_dir=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --catalog) catalog="${2:?--catalog requires a path}"; shift 2 ;;
    --test) test_id="${2:?--test requires an id}"; shift 2 ;;
    --environment) environment="${2:?--environment requires a value}"; shift 2 ;;
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
catalog_field() {
  awk -v key="$1" '$0 ~ "^  " key ": " { value=$0; sub("^  " key ": ", "", value); gsub(/^"|"$/, "", value); print value; exit }' "$catalog"
}
root_field() {
  awk -v key="$1" '$0 ~ "^" key ": " { value=$0; sub("^" key ": ", "", value); gsub(/^"|"$/, "", value); print value; exit }' "$catalog"
}

target_classification="$(catalog_field classification)"
config="$(catalog_field config)"
project_root="$(root_field project_root)"
kind="$(field kind)"; command="$(field command)"; approved="$(field approved)"; entry_environment="$(field environment)"; status="$(field execution_status)"; safety="$(field safety)"; timeout_seconds="$(field timeout_seconds)"
[ "$target_classification" = "isolated_test" ] || { echo "ERROR: GUI target must be classified isolated_test" >&2; exit 3; }
[ -n "$project_root" ] && [ -d "$project_root" ] || { echo "ERROR: catalog requires an existing absolute project_root" >&2; exit 3; }
case "$project_root" in /*) ;; *) echo "ERROR: project_root must be absolute" >&2; exit 3 ;; esac
[ -n "$config" ] || { echo "ERROR: Playwright config is required" >&2; exit 3; }
case "$config" in /*|*".."*) echo "ERROR: Playwright config must be a relative project path" >&2; exit 3 ;; esac
[ -f "$project_root/$config" ] || { echo "ERROR: Playwright config not found: $config" >&2; exit 3; }
for setting in trace screenshot video; do
  grep -Eq "${setting}[[:space:]]*:" "$project_root/$config" || { echo "ERROR: Playwright config must declare $setting artifacts" >&2; exit 3; }
done
[ "$kind" = "gui" ] || { echo "ERROR: $test_id is not a GUI entry" >&2; exit 3; }
[ "$approved" = "true" ] || { echo "ERROR: $test_id is not approved" >&2; exit 3; }
[ "$status" = "runnable" ] || { echo "ERROR: $test_id is $status; complete prerequisites first" >&2; exit 3; }
[ "$entry_environment" = "$environment" ] || { echo "ERROR: $test_id requires environment $entry_environment, not $environment" >&2; exit 3; }
[ "$safety" = "requires_explicit_gui_approval" ] || { echo "ERROR: $test_id lacks GUI execution approval" >&2; exit 3; }
[ -n "$timeout_seconds" ] || timeout_seconds=900
case "$timeout_seconds" in *[!0-9]*|'') echo "ERROR: invalid timeout_seconds" >&2; exit 3 ;; esac
case "$command" in "npx playwright test "*|"playwright test "*) ;; *) echo "ERROR: GUI command must be an approved playwright test invocation" >&2; exit 3 ;; esac
case "$command" in *';'*|*'&&'*|*'||'*|*'|'*|*'>'*|*'<'*|*'$('*|*'`'*) echo "ERROR: shell composition is not allowed in GUI commands" >&2; exit 3 ;; esac

[ -n "$artifacts_dir" ] || artifacts_dir="$project_root/test-runs/$test_id-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$artifacts_dir/playwright"
log_file="$artifacts_dir/command.log"; report_file="$artifacts_dir/run-report.yaml"; junit_file="$artifacts_dir/junit.xml"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; started_epoch="$(date +%s)"
set +e
(
  cd "$project_root"
  export PLAYWRIGHT_JUNIT_OUTPUT_FILE="$junit_file"
  export PLAYWRIGHT_OUTPUT_DIR="$artifacts_dir/playwright"
  if command -v timeout >/dev/null 2>&1; then
    timeout "$timeout_seconds" bash -lc "$command --config '$config' --output '$artifacts_dir/playwright' --reporter=line,junit"
  else
    perl -e '$seconds = shift @ARGV; alarm $seconds; exec @ARGV' "$timeout_seconds" bash -lc "$command --config '$config' --output '$artifacts_dir/playwright' --reporter=line,junit"
  fi
) >"$log_file" 2>&1
exit_code=$?
set -e
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; duration_seconds=$(( $(date +%s) - started_epoch ))
result="passed"; [ "$exit_code" -eq 0 ] || result="failed"
cat > "$report_file" <<EOF
test_id: "$test_id"
kind: "gui"
environment: "$environment"
target_classification: "isolated_test"
result: "$result"
exit_code: $exit_code
started_at: "$started_at"
finished_at: "$finished_at"
duration_seconds: $duration_seconds
timeout_seconds: $timeout_seconds
command_log: "$(basename "$log_file")"
junit: "$(basename "$junit_file")"
playwright_artifacts: "playwright"
EOF
echo "GUI test $test_id $result. Report: $report_file"
exit "$exit_code"
