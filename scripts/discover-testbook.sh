#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/discover-testbook.sh [--project-root <path>] [--output <path>]

Inspect a repository without executing tests and write a candidate testbook.
Every discovered entry is unapproved; review it before using run-testbook.sh.
USAGE
}

project_root="$(pwd)"
output=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:?--project-root requires a path}"; shift 2 ;;
    --output) output="${2:?--output requires a path}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
  esac
done

project_root="$(cd "$project_root" && pwd)"
[ -n "$output" ] || output="$project_root/.mana/testbook.discovered.yaml"
mkdir -p "$(dirname "$output")"

yaml_quote() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
has_file() {
  find "$project_root" -path "$project_root/.git" -prune -o -path "$project_root/node_modules" -prune -o -path "$project_root/vendor" -prune -o -path "$project_root/build" -prune -o -path "$project_root/target" -prune -o -type f -name "$1" -print -quit | grep -q .
}
has_path() {
  find "$project_root" -path "$project_root/.git" -prune -o -path "$project_root/node_modules" -prune -o -path "$project_root/vendor" -prune -o -path "$project_root/build" -prune -o -path "$project_root/target" -prune -o -type f -ipath "$1" -print -quit | grep -q .
}

entries=0
emit_entry() {
  local id="$1" kind="$2" command="$3" origin="$4" source="$5" prerequisites="$6" environment="$7" status="$8" safety="$9"
  local timeout_seconds=900
  [ "$kind" = "integration" ] && timeout_seconds=1800
  [ "$kind" = "performance" ] && timeout_seconds=900
  entries=$((entries + 1))
  cat >> "$output" <<EOF
  - id: "$(yaml_quote "$id")"
    kind: "$kind"
    command: "$(yaml_quote "$command")"
    command_origin: "$origin"
    source:
      - "$(yaml_quote "$source")"
    prerequisites: "$prerequisites"
    environment: "$environment"
    execution_status: "$status"
    safety: "$safety"
    timeout_seconds: $timeout_seconds
    approved: false
EOF
}

cat > "$output" <<EOF
schema_version: 1
generated_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
project_root: "$(yaml_quote "$project_root")"
discovery_mode: "read_only"
review_required: true
tests:
EOF

if [ -f "$project_root/build.gradle" ] || [ -f "$project_root/build.gradle.kts" ]; then
  gradle_cmd="./gradlew"; [ -x "$project_root/gradlew" ] || gradle_cmd="gradle"
  if has_path '*/src/test/*' || has_file '*Test.java' || has_file '*Test.kt'; then
    emit_entry "gradle-unit-test" "unit" "$gradle_cmd test" "build_file" "build.gradle" "java_or_gradle" "local" "runnable" "normal"
  fi
  if grep -R -q -E '(^|[^[:alnum:]])integrationTest([^[:alnum:]]|$)' "$project_root"/build.gradle* 2>/dev/null || has_file '*IT.java' || has_file '*IntegrationTest.java'; then
    emit_entry "gradle-integration-test" "integration" "$gradle_cmd integrationTest" "build_file_or_naming" "build.gradle" "docker_or_declared_dependencies" "local" "needs_environment" "normal"
  fi
fi

if [ -f "$project_root/pom.xml" ]; then
  mvn_cmd="mvn"; [ -x "$project_root/mvnw" ] && mvn_cmd="./mvnw"
  if has_path '*/src/test/*' || has_file '*Test.java'; then
    emit_entry "maven-unit-test" "unit" "$mvn_cmd test" "pom_or_test_layout" "pom.xml" "java_and_maven" "local" "runnable" "normal"
  fi
  if grep -q 'maven-failsafe-plugin' "$project_root/pom.xml" || has_file '*IT.java' || has_file '*ITCase.java'; then
    emit_entry "maven-integration-test" "integration" "$mvn_cmd verify" "failsafe_or_naming" "pom.xml" "docker_or_declared_dependencies" "local" "needs_environment" "normal"
  fi
fi

if [ -f "$project_root/package.json" ]; then
  node_cmd="npm run"; [ -f "$project_root/pnpm-lock.yaml" ] && node_cmd="pnpm run"; [ -f "$project_root/yarn.lock" ] && node_cmd="yarn"
  while IFS= read -r script_name; do
    [ -n "$script_name" ] || continue
    lower="$(printf '%s' "$script_name" | tr '[:upper:]' '[:lower:]')"
    kind="unit"; status="runnable"; environment="local"; safety="normal"
    case "$lower" in
      *perf*|*load*|*benchmark*) kind="performance"; status="needs_environment"; environment="dedicated_test"; safety="requires_explicit_performance_approval" ;;
      *integration*|*e2e*|*contract*) kind="integration"; status="needs_environment" ;;
    esac
    emit_entry "node-${lower//[^a-z0-9]/-}" "$kind" "$node_cmd $script_name" "package_json_script" "package.json" "node_dependencies" "$environment" "$status" "$safety"
  done < <(sed -nE 's/^[[:space:]]*"([^"]*(test|spec|integration|e2e|contract|perf|load|benchmark)[^"]*)"[[:space:]]*:.*/\1/pI' "$project_root/package.json" | sort -u)
fi

if [ -f "$project_root/pytest.ini" ] || [ -f "$project_root/tox.ini" ] || [ -f "$project_root/pyproject.toml" ]; then
  if has_path '*/tests/*' || has_file 'test_*.py' || has_file '*_test.py'; then
    emit_entry "python-unit-test" "unit" "python -m pytest" "python_test_configuration" "pytest.ini_or_pyproject.toml" "python_dependencies" "local" "runnable" "normal"
  fi
  if has_path '*integration*/*.py' || has_file '*integration_test.py'; then
    emit_entry "python-integration-test" "integration" "python -m pytest -m integration" "test_layout" "tests/integration" "declared_integration_environment" "local" "needs_environment" "normal"
  fi
fi

if [ -f "$project_root/go.mod" ] && has_file '*_test.go'; then
  emit_entry "go-test-suite" "unit" "go test ./..." "go_module_and_test_files" "go.mod" "go_toolchain" "local" "runnable" "normal"
fi
if [ -f "$project_root/Cargo.toml" ] && has_path '*/tests/*'; then
  emit_entry "cargo-test-suite" "unit" "cargo test" "cargo_manifest_and_test_layout" "Cargo.toml" "rust_toolchain" "local" "runnable" "normal"
fi

# CI commands are evidence, not executable local commands. Keep them visible for
# human review without copying pipeline shell fragments into the allowlist.
ci_index=0
while IFS= read -r path; do
  if grep -q -E -i '(test|integration|e2e|contract|performance|benchmark|load)' "$path"; then
    relative="${path#"$project_root"/}"
    ci_index=$((ci_index + 1))
    emit_entry "ci-test-evidence-$ci_index" "unknown" "" "ci_definition" "$relative" "ci_runner_or_documented_local_equivalent" "ci" "discovered_not_runnable" "normal"
  fi
done < <(find "$project_root" -path "$project_root/.git" -prune -o -path "$project_root/node_modules" -prune -o -type f \( -name 'Jenkinsfile' -o -name '.gitlab-ci.yml' -o -name 'azure-pipelines.yml' -o -name 'azure-pipelines.yaml' -o -path '*/.github/workflows/*.yml' -o -path '*/.github/workflows/*.yaml' \) -print 2>/dev/null | sort)

while IFS= read -r path; do
  relative="${path#"$project_root"/}"
  emit_entry "k6-$(basename "${path%.*}" | tr '[:upper:]_' '[:lower:]-')" "performance" "k6 run $relative" "k6_scenario" "$relative" "k6_and_dedicated_target" "dedicated_test" "needs_environment" "requires_explicit_performance_approval"
done < <(find "$project_root" -path "$project_root/.git" -prune -o -path "$project_root/node_modules" -prune -o -type f \( -iname '*.js' -o -iname '*.ts' \) -ipath '*k6*' -print 2>/dev/null | sort)
while IFS= read -r path; do
  relative="${path#"$project_root"/}"
  emit_entry "jmeter-$(basename "${path%.*}" | tr '[:upper:]_' '[:lower:]-')" "performance" "jmeter -n -t $relative" "jmeter_plan" "$relative" "jmeter_and_dedicated_target" "dedicated_test" "needs_environment" "requires_explicit_performance_approval"
done < <(find "$project_root" -path "$project_root/.git" -prune -o -path "$project_root/node_modules" -prune -o -type f -iname '*.jmx' -print 2>/dev/null | sort)

[ "$entries" -gt 0 ] || printf '  []\n' >> "$output"
echo "Discovered $entries candidate test entries: $output"
