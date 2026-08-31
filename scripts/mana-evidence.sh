#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/evidence-store.sh
. "$root/scripts/lib/evidence-store.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/mana-evidence.sh [--project-root <path>] <command> [options]

Commands:
  collect    Store a sanitized complete/partial record, or a failed/unavailable record.
  list       List evidence metadata for an execution.
  show       Show metadata for one evidence reference.
  read       Emit a bounded text range for one evidence reference.
  extract    Emit one explicit, provenance-bearing bounded extract.

Inputs and content stay inside the project boundary and .mana/runtime-evidence
is local-only. No command contacts a provider or network service.
USAGE
}

if [ "$#" -eq 0 ] || [ "${1:-}" = --help ] || [ "${1:-}" = -h ] || [ "${1:-}" = help ]; then
  usage
  exit 0
fi

mana_evidence_store "$@"
