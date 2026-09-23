#!/usr/bin/env bash
# Test-only stand-in for sandbox-exec.  Never selected by the production path.
set -euo pipefail
[ "${1:-}" = -f ] || exit 2
shift 2
[ "${1:-}" = -- ] || exit 2
shift
exec "$@"
