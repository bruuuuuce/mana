#!/usr/bin/env bash
# Test-only CTX-10 reader seam. It returns a canonical already-validated
# identity and delegates every other Python invocation to the real interpreter.
set -euo pipefail

if [ "${1:-}" = "${CTX10_EXECUTION_IDENTITY_TOOL:-}" ] && [ "${2:-}" = execution-identity ]; then
  printf '%s\n' '{"executionId":"execution-ctx10-fixture","executionVersion":1,"workspaceId":"W-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","profileId":"mana-help"}'
  exit 0
fi

exec "${CTX10_REAL_PYTHON:?CTX10_REAL_PYTHON is required}" "$@"
