#!/usr/bin/env bash
# CTX-05 provider-neutral, host-owned evidence store.  The implementation is
# dependency-free and intentionally has no provider or network dispatch path.

mana_evidence_store() {
  local root
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || return 1
  python3 "$root/scripts/lib/evidence-store.py" "$@"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  mana_evidence_store "$@"
fi
