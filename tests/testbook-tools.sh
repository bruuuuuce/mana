#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
mkdir -p "$project/src/test/java/example" "$project/tests/integration" "$project/k6" "$project/.github/workflows"

printf '%s\n' 'plugins { id "java" }' 'tasks.register("integrationTest")' > "$project/build.gradle"
printf '%s\n' 'class ExampleTest {}' > "$project/src/test/java/example/ExampleTest.java"
printf '%s\n' 'class ExampleIT {}' > "$project/src/test/java/example/ExampleIT.java"
printf '%s\n' 'def test_example(): pass' > "$project/tests/integration/test_example.py"
printf '%s\n' 'export default function () {}' > "$project/k6/smoke.js"
printf '%s\n' 'steps:' '- run: ./gradlew integrationTest' > "$project/.github/workflows/test.yml"

catalog="$tmp/discovered.yaml"
"$root/scripts/discover-testbook.sh" --project-root "$project" --output "$catalog" >/dev/null
grep -q 'id: "gradle-unit-test"' "$catalog"
grep -q 'id: "gradle-integration-test"' "$catalog"
grep -q 'kind: "performance"' "$catalog"
grep -q 'command_origin: "ci_definition"' "$catalog"
grep -A11 'id: "gradle-unit-test"' "$catalog" | grep -q 'approved: false'

if "$root/scripts/run-testbook.sh" --catalog "$catalog" --test gradle-unit-test >"$tmp/unapproved.out" 2>&1; then
  echo "FAIL: unapproved entry executed" >&2
  exit 1
fi
grep -q 'not approved' "$tmp/unapproved.out"

approved_catalog="$tmp/approved.yaml"
cat > "$approved_catalog" <<'EOF'
schema_version: 1
tests:
  - id: "fixture-pass"
    kind: "unit"
    command: "printf testbook-pass"
    command_origin: "fixture"
    source:
      - "fixture"
    prerequisites: "none"
    environment: "local"
    execution_status: "runnable"
    safety: "normal"
    timeout_seconds: 30
    approved: true
EOF
artifacts="$tmp/artifacts"
"$root/scripts/run-testbook.sh" --catalog "$approved_catalog" --test fixture-pass --artifacts-dir "$artifacts" >/dev/null
grep -q 'result: "passed"' "$artifacts/run-report.yaml"
grep -q 'timeout_seconds: 30' "$artifacts/run-report.yaml"
grep -q 'testbook-pass' "$artifacts/command.log"

empty_project="$tmp/empty"
mkdir -p "$empty_project"
empty_catalog="$tmp/empty.yaml"
"$root/scripts/discover-testbook.sh" --project-root "$empty_project" --output "$empty_catalog" >/dev/null
grep -A1 '^tests:$' "$empty_catalog" | grep -q '^  \[\]$'

echo "Testbook tools passed"
