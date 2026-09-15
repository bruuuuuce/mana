#!/usr/bin/env bash
# CTX-09G-R1 permanent local regression: shadow setup ordering and acceptance
# hygiene. No provider or external service is invoked.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-ctx09g-r1.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

# Provider setup must be conditional on the already-resolved mode. The
# installers remain available for legacy, but cannot run unconditionally in a
# shadow invocation.
guard="if [ \"\$context_runtime_shadow\" = false ]; then"
[ "$(grep -Fc "$guard" "$root/scripts/run-profile.sh")" -ge 3 ] || fail 'provider mode guards incomplete'
# shellcheck disable=SC2016 # matching literal shell source
grep -Fq 'ensure_codex_agents_at "$provider_config_root"' "$root/scripts/run-profile.sh" || fail 'private Codex setup missing'
grep -Fq 'CODEX_HOME' "$root/scripts/lib/context-shadow-backend.py" || fail 'private Codex config is not consumed'
grep -Fq 'CLAUDE_CONFIG_DIR' "$root/scripts/lib/context-shadow-backend.py" || fail 'private Claude config is not consumed'
grep -Fq 'OPENCODE_CONFIG_DIR' "$root/scripts/lib/context-shadow-backend.py" || fail 'private OpenCode config is not consumed'

scenario="$tmp/scenario"; evaluation_project="$tmp/project"
mkdir -p "$scenario" "$evaluation_project/.mana/global"
cat > "$scenario/scenario.md" <<'EOF'
# Scenario: CTX-09G-R1 external evaluation output
**Profile:** `mana-help`
EOF
cat > "$scenario/eval.yaml" <<'EOF'
version: 1
assertions:
  - type: must_not_modify
    value: true
EOF
before="$tmp/before"; after="$tmp/after"
snapshot() {
  local out="$1"
  # Installed fixture dependencies are immutable test inputs and may contain
  # millions of files; the worktree-owned surfaces below remain exhaustive
  # for this gate, including ignored Mana/provider state and bytecode.
  (cd "$root" && find . \
    -path './.git' -prune -o \
    -path './evals/fixtures/*/node_modules' -prune -o \
    -path './.ruff_cache' -prune -o -path './.codegraph' -prune -o \
    -print0) |
    while IFS= read -r -d '' path; do
      if [ -L "$root/$path" ]; then
        printf 'L|%s|%s\n' "$path" "$(readlink "$root/$path")"
      elif [ -f "$root/$path" ]; then
        printf 'F|%s|%s|%s|%s\n' "$path" "$(stat -f '%p:%z:%d:%i' "$root/$path")" "$(shasum -a 256 "$root/$path" | awk '{print $1}')" "$(stat -f '%l' "$root/$path")"
      elif [ -d "$root/$path" ]; then
        printf 'D|%s|%s\n' "$path" "$(stat -f '%p:%d:%i' "$root/$path")"
      fi
    done | LC_ALL=C sort > "$out"
}
snapshot "$before"
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$tmp/pycache" \
  "$root/scripts/mana-eval.sh" --project-root "$evaluation_project" \
  run "$scenario" --json >/dev/null || fail 'external evaluation harness failed'
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$tmp/pycache" \
  python3 -m py_compile "$root/scripts/lib/context-shadow-backend.py" || fail 'external py_compile failed'
snapshot "$after"
cmp -s "$before" "$after" || fail 'complete worktree snapshot changed during acceptance harness'
[ -d "$evaluation_project/.mana/evaluations/results" ] || fail 'test-owned evaluation root was not used'
[ -d "$tmp/pycache" ] || fail 'test-owned Python cache root was not used'
echo 'CTX-09G-R1 shadow setup and zero-mutation hygiene passed'
