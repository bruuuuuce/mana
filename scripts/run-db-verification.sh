#!/usr/bin/env bash
set -euo pipefail
catalog=""; test_id=""; environment="dedicated_test"; artifacts_dir=""
while [ "$#" -gt 0 ]; do case "$1" in --catalog) catalog="$2"; shift 2;; --test) test_id="$2"; shift 2;; --environment) environment="$2"; shift 2;; --artifacts-dir) artifacts_dir="$2"; shift 2;; *) echo "ERROR: expected --catalog, --test, --environment, or --artifacts-dir" >&2; exit 2;; esac; done
[ -f "$catalog" ] && [ -n "$test_id" ] || { echo "ERROR: catalog and test are required" >&2; exit 2; }
field() { awk -v target="$test_id" -v key="$1" '/^  - id: / {if(a)exit;v=$0;sub(/^  - id: "/,"",v);sub(/"$/,"",v);a=(v==target);next} a && $0 ~ "^    " key ": " {v=$0;sub("^    " key ": ","",v);gsub(/^"|"$/,"",v);print v;exit}' "$catalog"; }
root() { awk '$0 ~ /^project_root: / {sub(/^project_root: /,"",$0);gsub(/^"|"$/,"",$0);print;exit}' "$catalog"; }; top() { awk -v key="$1" '$0 ~ "^  " key ": " {sub("^  " key ": ","",$0);gsub(/^"|"$/,"",$0);print;exit}' "$catalog"; }
project_root="$(root)"; classification="$(top classification)"; kind="$(field kind)"; adapter="$(field adapter)"; conn_env="$(field connection_env)"; query="$(field query_file)"; approved="$(field approved)"; status="$(field execution_status)"; entry_env="$(field environment)"; safety="$(field safety)"; timeout="$(field timeout_seconds)"
[ "$classification" = isolated_test ] && [ -d "$project_root" ] || { echo "ERROR: isolated existing project_root required" >&2; exit 3; }
[ "$kind" = database_read ] && [ "$adapter" = postgresql ] && [ "$approved" = true ] && [ "$status" = runnable ] && [ "$entry_env" = "$environment" ] && [ "$safety" = requires_explicit_database_read_approval ] || { echo "ERROR: database catalog approval or environment gate failed" >&2; exit 3; }
case "$query" in /*|*".."*|*.sql) ;; *) echo "ERROR: query_file must be a relative .sql path" >&2; exit 3;; esac
[ -f "$project_root/$query" ] || { echo "ERROR: query file not found" >&2; exit 3; }
sql="$(sed -E 's/--[^\n]*//g; s@/\*([^*]|\*[^/])*\*/@@g' "$project_root/$query" | tr '[:upper:]' '[:lower:]')"
printf '%s' "$sql" | grep -Eq '^[[:space:]]*(select|with)[[:space:]]' && ! printf '%s' "$sql" | grep -Eq '\b(insert|update|delete|merge|alter|drop|create|truncate|grant|revoke|copy|call|do|lock|for[[:space:]]+update)\b' || { echo "ERROR: query is not demonstrably read-only" >&2; exit 3; }
[ "$(printf '%s' "$sql" | tr -cd ';' | wc -c | tr -d ' ')" -le 1 ] || { echo "ERROR: multiple SQL statements are not allowed" >&2; exit 3; }
[ -n "${!conn_env:-}" ] || { echo "ERROR: approved connection environment variable is not set" >&2; exit 3; }
[ -n "$artifacts_dir" ] || artifacts_dir="$project_root/test-runs/$test_id-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$artifacts_dir"; export PGOPTIONS="${PGOPTIONS:-} -c default_transaction_read_only=on"
run_with_timeout() { if command -v timeout >/dev/null 2>&1; then timeout "$@"; else seconds="$1"; shift; perl -e '$seconds = shift @ARGV; alarm $seconds; exec @ARGV' "$seconds" "$@"; fi; }
set +e; run_with_timeout "$timeout" psql "${!conn_env}" -X -v ON_ERROR_STOP=1 -f "$project_root/$query" >"$artifacts_dir/command.log" 2>&1; code=$?; set -e
result=passed; [ "$code" -eq 0 ] || result=failed; printf 'test_id: "%s"\nkind: "database_read"\nenvironment: "%s"\nresult: "%s"\nexit_code: %s\ncommand_log: "command.log"\n' "$test_id" "$environment" "$result" "$code" >"$artifacts_dir/run-report.yaml"; echo "Database verification $test_id $result. Report: $artifacts_dir/run-report.yaml"; exit "$code"
