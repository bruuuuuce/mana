#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
fixtures="$root/evals/fixtures"
status=0

expect_block() {
  local name="$1" expected="$2"
  shift 2
  local output code
  set +e
  output="$("$@" 2>&1)"
  code=$?
  set -e
  if [ "$code" -eq 0 ] || ! printf '%s' "$output" | grep -Fq "$expected"; then
    echo "ERROR: $name did not block as expected" >&2
    printf '%s\n' "$output" >&2
    status=1
  else
    echo "PASS: $name"
  fi
}

expect_block "GUI unapproved entry" "not approved" \
  "$root/scripts/run-gui-testbook.sh" --catalog "$fixtures/gui-playwright/gui-testbook-negative.yaml" --test unapproved-gui
expect_block "API unapproved entry" "approval or environment gate failed" \
  "$root/scripts/run-api-testbook.sh" --catalog "$fixtures/api-newman/api-testbook.yaml" --test unapproved-api
expect_block "DB mutating query" "not demonstrably read-only" \
  "$root/scripts/run-db-verification.sh" --catalog "$fixtures/db-postgres/database-verification.yaml" --test unsafe-db-query

[ "$status" -eq 0 ] && echo "Validation fixtures passed"
exit "$status"
