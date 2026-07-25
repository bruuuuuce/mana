#!/usr/bin/env bash
set -eu

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
# shellcheck source=lib/profile-metadata.sh
. "$root/scripts/lib/profile-metadata.sh"
# shellcheck source=lib/divination.sh
. "$root/scripts/lib/divination.sh"

if ! divination_validate_metadata "$root"; then
  echo "ERROR: $DIVINATION_ERROR" >&2
  exit 1
fi
echo 'Divination metadata validation passed'
