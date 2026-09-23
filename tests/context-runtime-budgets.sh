#!/usr/bin/env bash
# Dedicated CTX-08-R1 zero-token regression suite. No network/model calls.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
python3 "$root/tests/context-runtime-budgets.py"
echo 'Context Runtime CTX-08-R1 budget suite passed (host authority, monotone decisions, coherent usage, zero-token)'
