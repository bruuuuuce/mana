#!/usr/bin/env bash
# Explicit CTX-07B fixture harness whose canonical entry point selects the
# checked-in host-owned retain policy. Production has no equivalent selector.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
. "$root/scripts/run-context-workers.sh"
