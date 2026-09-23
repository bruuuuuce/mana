#!/usr/bin/env bash
# Local structured fixtures only; never invokes a provider or either runtime.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
python3 "$root/tests/context-runtime-comparison.py"
echo 'Context Runtime CTX-09B deterministic semantic comparison tests passed (local-only, zero-token)'
