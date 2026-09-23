#!/usr/bin/env bash
# CTX-06B authoritative reducer, durable publication, and fault acceptance entry point.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd -P)"

python3 "$root/tests/context-runtime-phase-transitions.py"
python3 "$root/tests/context-runtime-transition-publication.py"
python3 "$root/tests/context-runtime-transition-faults.py"

echo 'Context Runtime CTX-06B-R1D phase resume suite passed (zero-token)'
