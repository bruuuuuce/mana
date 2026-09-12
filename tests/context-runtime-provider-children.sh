#!/usr/bin/env bash
# CTX-07C deterministic provider-managed child and capability fallback gate.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
python3 "$root/tests/context-runtime-provider-children.py"
