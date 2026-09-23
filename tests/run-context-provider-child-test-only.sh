#!/usr/bin/env bash
# Canonical CTX-07C-R2 test-only entry point. Production cannot select its
# capability snapshot, provider adapter, or attestation fixture.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
. "$root/scripts/run-context-workers.sh"
