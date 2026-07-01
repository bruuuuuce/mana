#!/usr/bin/env bash
set -u

usage() {
  cat <<'USAGE'
Usage:
  scripts/run-sonar-scanner.sh [options]

Runs sonar-scanner through Mana guardrails. Project properties live in the
project-local .mana workspace. Environment variables hold only environment
or secret values.

Commands:
  --check          Validate local scanner, env, project config, and Sonar server access.
  --dry-run        Print the scanner command with token redacted.
  --analyze        Run sonar-scanner and store logs/summary under .mana/.
  --init-config    Create .mana/global/sonar-project.properties from template.

Options:
  --project-root <path>  Target project root. Defaults to current directory.
  --config <path>        Sonar properties file. Defaults to .mana/global/sonar-project.properties.
  --output-dir <path>    Evidence output directory for --analyze.
  --help                 Show this help.

Required environment for --analyze:
  SONAR_HOST_URL=http://localhost:9000
  SONAR_TOKEN=...

Project configuration:
  .mana/global/sonar-project.properties
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

warn() {
  echo "WARN: $*" >&2
}

root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"
config=""
output_dir=""
mode=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root)
      project_root="${2:-}"
      [ -n "$project_root" ] || fail "--project-root requires a path"
      shift 2
      ;;
    --config)
      config="${2:-}"
      [ -n "$config" ] || fail "--config requires a path"
      shift 2
      ;;
    --output-dir)
      output_dir="${2:-}"
      [ -n "$output_dir" ] || fail "--output-dir requires a path"
      shift 2
      ;;
    --check|--dry-run|--analyze|--init-config)
      [ -z "$mode" ] || fail "choose only one command"
      mode="${1#--}"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
done

[ -n "$mode" ] || mode="check"
project_root="$(cd "$project_root" && pwd)"

if [ -z "$config" ]; then
  config="$project_root/.mana/global/sonar-project.properties"
elif [ "${config#/}" = "$config" ]; then
  config="$project_root/$config"
fi

property_value() {
  key="$1"
  [ -f "$config" ] || return 0
  awk -F= -v key="$key" '
    $0 ~ /^[[:space:]]*#/ { next }
    $1 == key {
      sub(/^[^=]*=/, "")
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      print
      exit
    }
  ' "$config"
}

init_config() {
  template="$root/templates/mana-workspace/global/sonar-project.properties.template"
  [ -f "$template" ] || fail "missing template: $template"
  mkdir -p "$(dirname "$config")"
  if [ -f "$config" ]; then
    echo "Sonar config already exists: $config"
    return 0
  fi
  cp "$template" "$config"
  echo "Sonar config created: $config"
  echo "Edit project key, name, sources, binaries, and exclusions before running --analyze."
}

check_scanner() {
  if ! command -v sonar-scanner >/dev/null 2>&1; then
    echo "ERROR: sonar-scanner is not installed or not in PATH" >&2
    return 1
  fi
  echo "Sonar scanner: $(command -v sonar-scanner)"
  if sonar-scanner --version >/dev/null 2>&1; then
    sonar-scanner --version | sed -n '1,5p'
  else
    echo "ERROR: sonar-scanner is installed but does not run. Check Java version and scanner installation." >&2
    return 1
  fi
}

validate_config() {
  status=0
  if [ ! -f "$config" ]; then
    echo "ERROR: missing Sonar config: $config" >&2
    echo "Run: scripts/run-sonar-scanner.sh --project-root \"$project_root\" --init-config" >&2
    return 1
  fi
  echo "Sonar config: $config"

  project_key="$(property_value sonar.projectKey)"
  project_name="$(property_value sonar.projectName)"
  sources="$(property_value sonar.sources)"
  binaries="$(property_value sonar.java.binaries)"

  if [ -z "$project_key" ]; then echo "ERROR: sonar.projectKey is required" >&2; status=1; fi
  if [ -z "$project_name" ]; then warn "sonar.projectName is not set"; fi
  if [ -z "$sources" ]; then
    echo "ERROR: sonar.sources is required" >&2
    status=1
  else
    old_ifs="$IFS"
    IFS=,
    for source in $sources; do
      IFS="$old_ifs"
      source="$(printf '%s' "$source" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
      if [ -n "$source" ] && [ ! -e "$project_root/$source" ]; then
        warn "sonar.sources path does not exist yet: $source"
      fi
      IFS=,
    done
    IFS="$old_ifs"
  fi
  if [ -n "$binaries" ] && [ ! -e "$project_root/$binaries" ]; then
    warn "sonar.java.binaries path does not exist yet: $binaries; build the project first"
  fi

  if [ -z "${SONAR_HOST_URL:-}" ]; then
    echo "ERROR: SONAR_HOST_URL is required" >&2
    status=1
  else
    echo "Sonar host: $SONAR_HOST_URL"
  fi
  if [ -z "${SONAR_TOKEN:-}" ]; then
    echo "ERROR: SONAR_TOKEN is required for scanner authentication" >&2
    status=1
  else
    echo "Sonar token: configured"
  fi
  return "$status"
}

check_sonar_server() {
  status=0
  if ! command -v curl >/dev/null 2>&1; then
    echo "ERROR: curl is required to check Sonar server reachability" >&2
    return 1
  fi
  if [ -z "${SONAR_HOST_URL:-}" ] || [ -z "${SONAR_TOKEN:-}" ]; then
    return 1
  fi

  sonar_url="${SONAR_HOST_URL%/}"
  curl_config="$(mktemp)"
  curl_body="$(mktemp)"
  trap 'rm -f "$curl_config" "$curl_body"' EXIT
  chmod 600 "$curl_config"
  {
    printf '%s\n' 'silent'
    printf '%s\n' 'show-error'
    printf '%s\n' 'location'
    printf '%s\n' 'connect-timeout = 5'
    printf '%s\n' 'max-time = 15'
    printf '%s\n' 'header = "Accept: application/json"'
    printf 'header = "Authorization: Bearer %s"\n' "$SONAR_TOKEN"
  } > "$curl_config"

  version_status="$(curl --config "$curl_config" --output "$curl_body" --write-out "%{http_code}" "$sonar_url/api/server/version" || true)"
  case "$version_status" in
    200)
      version="$(sed -n '1p' "$curl_body" | tr -d '\r\n')"
      echo "Sonar server reachable: ${version:-unknown version}"
      ;;
    000)
      echo "ERROR: Sonar server is not reachable: $sonar_url" >&2
      status=1
      ;;
    401|403)
      echo "ERROR: Sonar server rejected authentication while checking version (HTTP $version_status)" >&2
      status=1
      ;;
    *)
      echo "ERROR: Sonar server version check failed with HTTP $version_status" >&2
      status=1
      ;;
  esac

  validate_status="$(curl --config "$curl_config" --output "$curl_body" --write-out "%{http_code}" "$sonar_url/api/authentication/validate" || true)"
  case "$validate_status" in
    200)
      if grep -q '"valid"[[:space:]]*:[[:space:]]*true' "$curl_body"; then
        echo "Sonar token authentication validated"
      else
        echo "ERROR: Sonar token authentication check returned invalid" >&2
        status=1
      fi
      ;;
    000)
      echo "ERROR: Sonar authentication endpoint is not reachable: $sonar_url" >&2
      status=1
      ;;
    401|403)
      echo "ERROR: Sonar token authentication failed with HTTP $validate_status" >&2
      status=1
      ;;
    *)
      echo "ERROR: Sonar authentication check failed with HTTP $validate_status" >&2
      status=1
      ;;
  esac
  return "$status"
}

active_workspace() {
  active_file="$project_root/.mana/active-workspace"
  if [ -f "$active_file" ]; then
    active_relative="$(sed -n '1p' "$active_file")"
    if [ -n "$active_relative" ]; then
      echo "$project_root/$active_relative"
      return 0
    fi
  fi
  "$root/scripts/mana-workspace.sh" resolve --root "$project_root" --purpose sonar-analysis
}

scanner_command() {
  cmd=(
    sonar-scanner
    "-Dsonar.host.url=$SONAR_HOST_URL"
    "-Dsonar.token=$SONAR_TOKEN"
    "-Dproject.settings=$config"
  )
}

print_redacted_command() {
  for arg in "${cmd[@]}"; do
    case "$arg" in
      -Dsonar.token=*) printf '%q ' "-Dsonar.token=<redacted>" ;;
      *) printf '%q ' "$arg" ;;
    esac
  done
  printf '\n'
}

redact_log_file() {
  file="$1"
  token="${SONAR_TOKEN:-}"
  [ -n "$token" ] || return 0
  tmp="$file.redacted"
  : > "$tmp"
  while IFS= read -r line || [ -n "$line" ]; do
    printf '%s\n' "${line//$token/<redacted>}" >> "$tmp"
  done < "$file"
  mv "$tmp" "$file"
}

write_summary() {
  summary="$1"
  log="$2"
  status="$3"
  project_key="$(property_value sonar.projectKey)"
  {
    echo "# Sonar Scanner Summary"
    echo
    echo "- Status: \`$status\`"
    echo "- Project root: \`$project_root\`"
    echo "- Config: \`$config\`"
    echo "- Project key: \`${project_key:-unknown}\`"
    echo "- Host: \`${SONAR_HOST_URL:-not configured}\`"
    echo "- Log: \`$log\`"
    echo "- Token printed: \`no\`"
    echo
    echo "## Scanner Result"
    echo
    if grep -q "EXECUTION SUCCESS" "$log" 2>/dev/null; then
      echo "- Scanner reported execution success."
    elif grep -q "EXECUTION FAILURE" "$log" 2>/dev/null; then
      echo "- Scanner reported execution failure."
    else
      echo "- Scanner did not emit a recognized success/failure marker."
    fi
    echo
    echo "## Review Guidance"
    echo
    echo "- Treat this artifact as evidence for branch validation or PR review."
    echo "- Do not approve, merge, or reject solely from Sonar output."
    echo "- Triage only findings that are new, touched by the branch, or high-risk."
  } > "$summary"
}

case "$mode" in
  init-config)
    init_config
    ;;
  check)
    check_scanner
    scanner_status=$?
    validate_config
    config_status=$?
    if [ "$config_status" -eq 0 ]; then
      check_sonar_server
      server_status=$?
    else
      server_status=1
    fi
    if [ "$scanner_status" -eq 0 ] && [ "$config_status" -eq 0 ] && [ "$server_status" -eq 0 ]; then
      echo "Sonar scanner check passed"
      exit 0
    fi
    exit 1
    ;;
  dry-run)
    check_scanner || exit 1
    validate_config || exit 1
    scanner_command
    print_redacted_command
    ;;
  analyze)
    check_scanner || exit 1
    validate_config || exit 1
    if [ -z "$output_dir" ]; then
      workspace="$(active_workspace)"
      output_dir="$workspace/evidence/sonar"
    elif [ "${output_dir#/}" = "$output_dir" ]; then
      output_dir="$project_root/$output_dir"
    fi
    mkdir -p "$output_dir"
    log="$output_dir/sonar-command.log"
    summary="$output_dir/sonar-summary.md"
    scanner_command
    echo "Running sonar-scanner. Log: $log"
    if (cd "$project_root" && "${cmd[@]}") > "$log" 2>&1; then
      status="success"
    else
      scanner_exit=$?
      status="failed_exit_$scanner_exit"
    fi
    redact_log_file "$log"
    write_summary "$summary" "$log" "$status"
    echo "Sonar summary written: $summary"
    [ "$status" = "success" ]
    ;;
  *)
    fail "unknown command: $mode"
    ;;
esac
