#!/usr/bin/env bash
# Explicit CTX-07B fixture harness.  Production callers must use
# scripts/run-context-workers.sh, whose parser has no framework-root option.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
. "$root/scripts/run-context-workers.sh"
