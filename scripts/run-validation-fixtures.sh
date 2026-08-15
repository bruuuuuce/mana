#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
fixtures="$root/evals/fixtures"
status=0
rendered="$(mktemp -d)"
trap 'rm -rf "$rendered"' EXIT

render_catalog() {
  local source="$1" project_root="$2" destination="$3"
  awk -v project_root="$project_root" '
    /^project_root: / {
      print "project_root: \"" project_root "\""
      next
    }
    { print }
  ' "$source" > "$destination"
}

render_catalog "$fixtures/gui-playwright/gui-testbook-negative.yaml" \
  "$fixtures/gui-playwright" "$rendered/gui-testbook-negative.yaml"
render_catalog "$fixtures/api-newman/api-testbook.yaml" \
  "$fixtures/api-newman" "$rendered/api-testbook.yaml"
render_catalog "$fixtures/db-postgres/database-verification.yaml" \
  "$fixtures/db-postgres" "$rendered/database-verification.yaml"

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
  "$root/scripts/run-gui-testbook.sh" --catalog "$rendered/gui-testbook-negative.yaml" --test unapproved-gui
expect_block "API unapproved entry" "approval or environment gate failed" \
  "$root/scripts/run-api-testbook.sh" --catalog "$rendered/api-testbook.yaml" --test unapproved-api
expect_block "DB mutating query" "not demonstrably read-only" \
  "$root/scripts/run-db-verification.sh" --catalog "$rendered/database-verification.yaml" --test unsafe-db-query

[ "$status" -eq 0 ] && echo "Validation fixtures passed"
exit "$status"
