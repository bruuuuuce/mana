#!/usr/bin/env bash
set -euo pipefail
catalog=""; test_id=""; environment="dedicated_test"; artifacts_dir=""
while [ "$#" -gt 0 ]; do case "$1" in --catalog) catalog="$2"; shift 2;; --test) test_id="$2"; shift 2;; --environment) environment="$2"; shift 2;; --artifacts-dir) artifacts_dir="$2"; shift 2;; *) echo "ERROR: expected --catalog, --test, --environment, or --artifacts-dir" >&2; exit 2;; esac; done
[ -f "$catalog" ] && [ -n "$test_id" ] || { echo "ERROR: catalog and test are required" >&2; exit 2; }
field() { awk -v target="$test_id" -v key="$1" '/^  - id: / {if(a)exit; v=$0;sub(/^  - id: "/,"",v);sub(/"$/,"",v);a=(v==target);next} a && $0 ~ "^    " key ": " {v=$0;sub("^    " key ": ","",v);gsub(/^"|"$/,"",v);print v;exit}' "$catalog"; }
root() { awk '$0 ~ /^project_root: / {sub(/^project_root: /,"",$0);gsub(/^"|"$/,"",$0);print;exit}' "$catalog"; }
top() { awk -v key="$1" '$0 ~ "^  " key ": " {sub("^  " key ": ","",$0);gsub(/^"|"$/,"",$0);print;exit}' "$catalog"; }
project_root="$(root)"; classification="$(top classification)"; runner="$(field runner)"; collection="$(field collection)"; env_file="$(field environment_file)"; approved="$(field approved)"; status="$(field execution_status)"; entry_env="$(field environment)"; safety="$(field safety)"; timeout="$(field timeout_seconds)"
[ "$classification" = isolated_test ] && [ -d "$project_root" ] || { echo "ERROR: isolated existing project_root required" >&2; exit 3; }
[ "$runner" = newman ] && [ "$approved" = true ] && [ "$status" = runnable ] && [ "$entry_env" = "$environment" ] && [ "$safety" = requires_explicit_api_approval ] || { echo "ERROR: API catalog approval or environment gate failed" >&2; exit 3; }
case "$collection:$env_file" in /*|*".."*) echo "ERROR: collection paths must be relative" >&2; exit 3;; esac
[ -f "$project_root/$collection" ] && [ -f "$project_root/$env_file" ] || { echo "ERROR: local Newman collection and environment file required" >&2; exit 3; }
case "$timeout" in ''|*[!0-9]*) echo "ERROR: valid timeout required" >&2; exit 3;; esac
[ -n "$artifacts_dir" ] || artifacts_dir="$project_root/test-runs/$test_id-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$artifacts_dir"
run_with_timeout() { if command -v timeout >/dev/null 2>&1; then timeout "$@"; else seconds="$1"; shift; perl -e '$seconds = shift @ARGV; alarm $seconds; exec @ARGV' "$seconds" "$@"; fi; }
set +e; (cd "$project_root" && run_with_timeout "$timeout" npx newman run "$collection" -e "$env_file" -r cli,json,junit --reporter-json-export "$artifacts_dir/newman.json" --reporter-junit-export "$artifacts_dir/junit.xml") >"$artifacts_dir/command.log" 2>&1; code=$?; set -e
result=passed; [ "$code" -eq 0 ] || result=failed
printf 'test_id: "%s"\nkind: "api"\nenvironment: "%s"\nresult: "%s"\nexit_code: %s\ncommand_log: "command.log"\nnewman_json: "newman.json"\njunit: "junit.xml"\n' "$test_id" "$environment" "$result" "$code" >"$artifacts_dir/run-report.yaml"
echo "API test $test_id $result. Report: $artifacts_dir/run-report.yaml"; exit "$code"
