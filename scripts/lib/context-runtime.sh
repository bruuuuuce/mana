#!/usr/bin/env bash
# CTX-03 host-side contract boundary.  The Python implementation is kept
# dependency-free so deterministic validation never needs a provider call.

mana_context_runtime_contract() {
  local root
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || return 1
  python3 "$root/scripts/lib/context-runtime.py" "$@"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  mana_context_runtime_contract "$@"
fi
