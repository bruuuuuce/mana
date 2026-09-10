#!/usr/bin/env bash
# CTX-07B deterministic fresh host-worker and model-routing acceptance gate.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd -P)"
python3 -m py_compile \
  "$root/scripts/lib/context-worker-runtime.py" \
  "$root/tests/context-runtime-workers.py" \
  "$root/tests/context-worker-runtime-retain-test-only.py"
python3 "$root/tests/context-runtime-workers.py"
python3 "$root/tests/context-runtime-worker-recovery.py"
bash "$root/tests/context-runtime-worker-boundaries.sh"
test -f "$root/contracts/context-runtime/delegation-result-draft-v1.schema.json"
test -f "$root/contracts/context-runtime/worker-routing-policy-v1.schema.json"
test -f "$root/contracts/context-runtime/worker-debug-policy-v1.schema.json"
test -f "$root/contracts/context-runtime/worker-context-packet-v1.schema.json"
python3 "$root/tests/lib/json_schema_subset.py" \
  "$root/contracts/context-runtime/delegation-result-draft-v1.schema.json" \
  "$root/tests/fixtures/context-runtime/contracts/valid/delegation-result-draft.json"
python3 "$root/tests/lib/json_schema_subset.py" \
  "$root/contracts/context-runtime/worker-routing-policy-v1.schema.json" \
  "$root/config/context-runtime/worker-routing-policy-v1.json"
python3 "$root/tests/lib/json_schema_subset.py" \
  "$root/contracts/context-runtime/worker-routing-policy-v1.schema.json" \
  "$root/tests/fixtures/context-runtime/ctx06a-framework/config/context-runtime/worker-routing-policy-v1.json"
python3 "$root/tests/lib/json_schema_subset.py" \
  "$root/contracts/context-runtime/worker-debug-policy-v1.schema.json" \
  "$root/config/context-runtime/worker-debug-policy-v1.json"
python3 "$root/tests/lib/json_schema_subset.py" \
  "$root/contracts/context-runtime/worker-debug-policy-v1.schema.json" \
  "$root/tests/fixtures/context-runtime/ctx06a-framework/config/context-runtime/worker-debug-policy-v1.json"
python3 "$root/tests/lib/json_schema_subset.py" \
  "$root/contracts/context-runtime/worker-debug-policy-v1.schema.json" \
  "$root/tests/fixtures/context-runtime/ctx06a-framework/config/context-runtime/worker-debug-policy-retain-v1.json"

echo 'Context Runtime CTX-07B-R2A-E worker suite passed (authority, diagnostics, real recovery boundaries, zero-token)'
