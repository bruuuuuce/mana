#!/usr/bin/env bash
# Canonical fixture entry point; production exposes no alternate root option.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
. "$root/scripts/run-profile-v2.sh"
