#!/usr/bin/env bash
# CTX-09A independent local regression and fault gate: providers are stubs.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
python3 "$root/tests/context-runtime-modes.py"
echo 'Context Runtime CTX-09A mode plumbing tests passed (local-only, zero-token)'
