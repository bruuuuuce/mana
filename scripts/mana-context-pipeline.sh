#!/usr/bin/env bash
# CTX-06A/B state and CTX-06C preparation commands; no provider dispatch.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
exec "$root/scripts/lib/context-pipeline.sh" "$@"
