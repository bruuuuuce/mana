#!/usr/bin/env bash
# CTX-06A/06B state contract plus CTX-06C preparation. No provider dispatch.

mana_context_pipeline() {
  local root
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || return 1
  python3 "$root/scripts/lib/context-pipeline.py" "$@"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  mana_context_pipeline "$@"
fi
