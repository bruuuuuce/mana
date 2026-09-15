#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
python3 "$root/tests/context-runtime-shadow-input.py"
python3 "$root/tests/context-runtime-live-shadow.py"
python3 "$root/tests/context-runtime-r2a.py"
python3 "$root/tests/context-runtime-r2b.py"
python3 "$root/tests/context-runtime-r2c.py"
python3 "$root/tests/context-runtime-r2d.py"
python3 "$root/tests/context-runtime-r3a.py"
python3 "$root/tests/context-runtime-r3b.py"
echo 'Context Runtime CTX-09C live shadow tests passed (local-only, zero-token)'
