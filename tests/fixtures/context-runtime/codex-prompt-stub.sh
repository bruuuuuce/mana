#!/usr/bin/env bash
# Deterministic CTX-04 runner stub: capture only the final prompt argument.
set -eu
if [ "${1:-}" = "--version" ]; then
  echo 'codex-cli context-profile-compiler-test-stub'
  exit 0
fi
last=""
for argument in "$@"; do last="$argument"; done
printf '%s\n' "$last" > "${MANA_TEST_CODEX_PROMPT:?capture path is required}"
