#!/usr/bin/env bash
# CTX-07A-R2 deterministic binding, semantic result validation, merge, and isolation gate.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd -P)"
validator="$root/scripts/lib/context-runtime.sh"

python3 -m py_compile "$root/scripts/lib/context-delegation.py" "$root/tests/context-runtime-delegation.py"
python3 "$root/tests/context-runtime-delegation.py"

for kind in delegation-plan delegation-task delegation-result delegation-merge; do
  test -f "$root/contracts/context-runtime/${kind}-v1.schema.json"
done

"$validator" validate-model delegation-task "$root/tests/fixtures/context-runtime/contracts/valid/delegation-task.json"
"$validator" validate-model delegation-result "$root/tests/fixtures/context-runtime/contracts/valid/delegation-result.json"

echo 'Context Runtime CTX-07A-R2 delegation tests passed (host-only, zero-provider)'
