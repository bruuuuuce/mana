#!/usr/bin/env bash
set -eu

root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

activation_for() {
  profile="$1"
  signal="$2"
  awk -v signal="$signal" '
    /^skill_activation:/ { in_activation = 1; next }
    in_activation && /^[^[:space:]]/ { exit }
    in_activation && $1 == signal ":" { print $2; exit }
  ' "$root/profiles/$profile.yaml"
}

baseline_contains() {
  profile="$1"
  skill="$2"
  awk -v skill="$skill" '
    /^skill_activation:/ { in_activation = 1; next }
    in_activation && /^[^[:space:]]/ { exit }
    in_activation && /^  baseline:/ { in_baseline = 1; next }
    in_activation && /^  conditional:/ { in_baseline = 0 }
    in_baseline && $1 == "-" && $2 == skill { found = 1 }
    END { exit(found ? 0 : 1) }
  ' "$root/profiles/$profile.yaml"
}

index_value() {
  skill="$1"
  field="$2"
  awk -v skill="$skill" -v field="$field" '
    $1 == "-" && $2 == "id:" { active = ($3 == skill); next }
    active && $1 == field ":" { print $2; exit }
  ' "$root/skills/index.yaml"
}

assert_activation() {
  profile="$1"
  signal="$2"
  expected_skill="$3"
  actual_skill="$(activation_for "$profile" "$signal")"
  [ "$actual_skill" = "$expected_skill" ] || fail "$profile signal $signal activates $actual_skill, expected $expected_skill"
  [ "$(index_value "$expected_skill" model_tier)" = "full" ] || fail "$expected_skill must be full-tier in skills/index.yaml"
}

assert_mapping() {
  profile="$1"
  signal="$2"
  expected_skill="$3"
  actual_skill="$(activation_for "$profile" "$signal")"
  [ "$actual_skill" = "$expected_skill" ] || fail "$profile signal $signal activates $actual_skill, expected $expected_skill"
}

assert_baseline() {
  profile="$1"
  skill="$2"
  baseline_contains "$profile" "$skill" || fail "$profile baseline does not include $skill"
}

assert_activation pr-ready migration_or_schema_change liquibase-production-risk
assert_activation pr-ready api_event_or_client_contract_change cross-service-contract
assert_activation pr-ready dependency_manifest_or_lockfile_change dependency-security-evidence

assert_baseline story-start story-quality
assert_baseline story-start acceptance-criteria-testability
assert_baseline story-start jira-acceptance-criteria-normalizer
assert_baseline story-start source-impact-map
assert_mapping story-start epic_or_parent_objective_present epic-goal-extraction
assert_mapping story-start implementation_scope_confirmed technical-task-breakdown
assert_mapping story-start implementation_scope_and_test_requirements_confirmed green-border-plan
assert_mapping story-start estimation_explicitly_requested_and_scope_confirmed story-effort-estimation
assert_mapping story-start architecture_boundary_change architecture-risk
assert_mapping story-start api_event_or_client_contract_change cross-service-contract
assert_mapping story-start migration_or_schema_change liquibase-production-risk

echo "Profile skill activation tests passed"
