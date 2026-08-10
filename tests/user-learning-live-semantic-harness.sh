#!/usr/bin/env bash
# Zero-token regression coverage for live semantic harness initialization.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
live="$root/tests/user-learning-live-semantic.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-learning-live-harness.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

bash -n "$live" || fail 'live semantic harness has invalid Bash syntax'
grep -Fq "(.sourceClusterIds|length)>=1 and (.supportingSignalIds|length)>=2" "$live" || fail 'candidate provenance assertion lost jq grouping'
printf '%s\n' '{"sourceClusterIds":["cluster-a"],"supportingSignalIds":["signal-a","signal-b"]}' | jq -e '(.sourceClusterIds|length)>=1 and (.supportingSignalIds|length)>=2' >/dev/null || fail 'valid candidate provenance assertion failed'
if env -u MANA_RUN_LIVE_MODEL_TESTS -u MANA_USER_LEARNING_T1_PROVIDER -u MANA_USER_LEARNING_T1_MODEL bash "$live" >"$tmp/refusal.out" 2>&1; then
  fail 'live semantic harness accepted execution without opt-in'
fi
grep -Fq 'LIVE TEST OPT-IN REQUIRED' "$tmp/refusal.out" || fail 'live semantic harness opt-in refusal changed'

smoke_output="$(MANA_RUN_LIVE_MODEL_TESTS=1 MANA_USER_LEARNING_T1_PROVIDER=codex MANA_USER_LEARNING_T1_MODEL=harness-smoke MANA_USER_LEARNING_LIVE_HARNESS_SMOKE=1 bash "$live")"
printf '%s' "$smoke_output" | grep -Fq 'scenario=external_constraint reached pre-provider stage' || fail 'live semantic harness did not initialize scenario-local paths before provider execution'

echo 'User Learning live semantic harness tests passed (zero provider calls)'
