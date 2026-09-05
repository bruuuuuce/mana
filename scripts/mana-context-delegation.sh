#!/usr/bin/env bash
# CTX-07A host-only delegation ownership and merge boundary. No provider call.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$root/scripts/lib/context-delegation.py" "$@"
