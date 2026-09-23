#!/usr/bin/env bash
# CTX-09B: offline diagnostic only; no provider, runtime or authority selection.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$root/scripts/lib/context-comparison.py" "$@"
