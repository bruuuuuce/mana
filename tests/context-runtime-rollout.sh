#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
bootstrap_tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-ctx10-bootstrap.XXXXXX")"
trap 'rm -rf "$bootstrap_tmp"' EXIT
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$bootstrap_tmp/pycache"
python3 "$root/tests/context-runtime-rollout.py"
python3 "$root/tests/context-runtime-rollout-race.py"

mkdir -p "$bootstrap_tmp/linked" "$bootstrap_tmp/no-links"
"$root/scripts/bootstrap-project.sh" --project-root "$bootstrap_tmp/linked" --mana-root "$root" --no-jira-env --no-gitignore >/dev/null
find "$bootstrap_tmp/linked/.mana/links" -type l -print -quit | grep -q .
"$root/scripts/bootstrap-project.sh" --project-root "$bootstrap_tmp/no-links" --mana-root "$root" --no-links --no-jira-env --no-gitignore >/dev/null
test -z "$(find "$bootstrap_tmp/no-links/.mana/links" -type l -print -quit)"
"$bootstrap_tmp/no-links/mana" inspect runtime --json | jq -e '.runtimeMode == "legacy" and .guarantees.writes == false' >/dev/null
# Provider presence is host state, not bootstrap authority: each provider is
# either refreshed when installed or reported unavailable without a config.
python3 "$root/scripts/context-runtime-rollout.py" status --project-root "$bootstrap_tmp/no-links" | jq -e '.noLinks == true and ([.providers[] | ((.installed and .managedBlock == "current") or ((.installed | not) and .managedBlock == "unavailable" and .warning == "provider-not-installed"))] | all)' >/dev/null
rg -q 'legacy will remain supported for at least one compatibility' "$root/docs/architecture/context-runtime-v2.md"
rg -q 'CTX-10 does \*\*not\*\* flip the global default' "$root/docs/architecture/context-runtime-v2.md"
rg -q 'does not initialize `\.mana`' "$root/docs/architecture/context-runtime-v2.md"
rg -q 'PRC-06 remains required before rollout activation' "$root/docs/architecture/context-runtime-v2.md"
rg -q 'PRC-06 remains required before rollout activation' "$root/docs/standards/context-runtime-contract.md"
rg -q 'PRC-06 remains required before rollout activation' "$root/CHANGELOG.md"
python3 -c 'import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); v=json.loads(p.read_text()); v["profiles"]={"mana-help":{"mode":"v2","failClosed":True}}; p.write_text(json.dumps(v)+"\n")' "$bootstrap_tmp/no-links/.mana/context-runtime/runtime-selection-v1.json"
if (cd "$bootstrap_tmp/no-links" && ./mana profile mana-help --context-runtime legacy) >/dev/null 2>&1; then
  echo "expected host policy/CLI conflict to fail closed" >&2; exit 1
fi
run_v2_rejection() {
  local expected="$1"
  shift
  local output
  output="$( (cd "$bootstrap_tmp/no-links" && ./mana profile mana-help "$@") 2>&1 || true)"
  printf '%s\n' "$output" | grep -Fq -- "$expected" || {
    echo "expected CTX-10 v2 rejection $expected, got: $output" >&2
    exit 1
  }
}

# CTX-10-R2.1: a missing CTX-06 identity is the public precedence when both
# prerequisites are absent, including when the runner flag appears before or
# after the runtime selector.
run_v2_rejection 'CTX10_EXECUTION_IDENTITY_REQUIRED' --context-runtime v2
run_v2_rejection 'CTX10_EXECUTION_IDENTITY_REQUIRED' --codex --context-runtime v2

# The remaining cases use a trusted-identity fixture at the CTX-10 reader
# boundary. It isolates dispatch validation; the actual CTX-06 chain is covered
# by its authoritative suite and this fixture never reaches a provider binary.
mkdir -p "$bootstrap_tmp/bin"
real_python="$(command -v python3)"
cat > "$bootstrap_tmp/bin/python3" <<EOF
#!/usr/bin/env bash
if [ "\${1:-}" = "$root/scripts/context-runtime-rollout.py" ] && [ "\${2:-}" = execution-identity ]; then
  printf '%s\\n' '{"executionId":"execution-ctx10-fixture","executionVersion":1,"workspaceId":"W-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","profileId":"mana-help"}'
  exit 0
fi
exec "$real_python" "\$@"
EOF
chmod 700 "$bootstrap_tmp/bin/python3"
run_v2_identity_fixture() {
  local expected="$1"
  shift
  local output
  output="$( (cd "$bootstrap_tmp/no-links" && PATH="$bootstrap_tmp/bin:$PATH" ./mana profile mana-help "$@") 2>&1 || true)"
  printf '%s\n' "$output" | grep -Fq -- "$expected" || {
    echo "expected CTX-10 v2 fixture result $expected, got: $output" >&2
    exit 1
  }
}
# B and C: identity is admitted first; absent/conflicting runners have the
# same stable category and argument order cannot change it.
run_v2_identity_fixture 'CTX10_PROVIDER_RUNNER_SELECTION_REQUIRED' --runtime-execution-id execution-ctx10-fixture --context-runtime v2
run_v2_identity_fixture 'CTX10_PROVIDER_RUNNER_SELECTION_REQUIRED' --claude --runtime-execution-id execution-ctx10-fixture --codex --context-runtime v2
# F: with both dispatch prerequisites present, control reaches the v2 runner;
# it does not silently fall back to legacy or produce a precondition category.
v2_valid_output="$( (cd "$bootstrap_tmp/no-links" && PATH="$bootstrap_tmp/bin:$PATH" ./mana profile mana-help --codex --context-runtime v2 --runtime-execution-id execution-ctx10-fixture) 2>&1 || true)"
printf '%s\n' "$v2_valid_output" | grep -Fq 'authoritative transition reconciliation failed before provider execution'
if printf '%s\n' "$v2_valid_output" | grep -Fq 'CTX10_'; then
  echo "valid CTX-10 v2 dispatch stopped at a precondition: $v2_valid_output" >&2
  exit 1
fi
echo "Context Runtime CTX-10 linked/no-links bootstrap regression passed"
