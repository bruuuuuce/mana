#!/usr/bin/env bash
set -eu

usage() {
  cat <<'USAGE'
Usage:
  scripts/run-jira-mcp-docker.sh [options]

Runs the existing mcp-atlassian Docker MCP server with framework guardrails.
The wrapper is read-only by default and passes Jira credentials through Docker
environment variables or an env file.

Options:
  --env-file <path>    Env file for Docker. Defaults to mcp/env/jira-mcp.env when present.
  --image <image>      Docker image. Defaults to ghcr.io/sooperset/mcp-atlassian:latest.
  --allow-writes       Do not force READ_ONLY_MODE=true. Requires human approval by policy.
  --dry-run            Print the docker command without executing it.
  --check-access       Verify Jira credentials with a read-only REST call, without Docker or agents.
  --issue <KEY>        With --check-access, also verify read access to a specific Jira issue.
  --get-issue <KEY>    Print a read-only Jira issue JSON payload for agent use.
  --help               Show this help.

Required Jira configuration:
  Jira Server/Data Center:
    JIRA_URL=https://jira.your-company.com
    JIRA_PERSONAL_TOKEN=...
    # JIRA_ACCESS_TOKEN is accepted as an alias.

  Jira Cloud:
    JIRA_URL=https://your-company.atlassian.net
    JIRA_USERNAME=your.email@company.com
    JIRA_API_TOKEN=...

Optional restrictions:
  JIRA_PROJECTS_FILTER=PROJ,DEV
  TOOLSETS=default
  ENABLED_TOOLS=jira_get_issue,jira_search,jira_search_fields
USAGE
}

root="$(cd "$(dirname "$0")/.." && pwd)"
image="${MCP_ATLASSIAN_IMAGE:-ghcr.io/sooperset/mcp-atlassian:latest}"
env_file=""
allow_writes=false
dry_run=false
check_access=false
check_issue=""
get_issue=""

if [ -f "$root/mcp/env/jira-mcp.env" ]; then
  env_file="$root/mcp/env/jira-mcp.env"
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --env-file)
      env_file="${2:-}"
      [ -n "$env_file" ] || { echo "ERROR: --env-file requires a path" >&2; exit 2; }
      shift 2
      ;;
    --image)
      image="${2:-}"
      [ -n "$image" ] || { echo "ERROR: --image requires an image" >&2; exit 2; }
      shift 2
      ;;
    --allow-writes)
      allow_writes=true
      shift
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    --check-access)
      check_access=true
      shift
      ;;
    --issue|--jira-key|--jira-issue)
      check_issue="${2:-}"
      [ -n "$check_issue" ] || { echo "ERROR: $1 requires a Jira issue key" >&2; exit 2; }
      shift 2
      ;;
    --get-issue|--read-issue)
      get_issue="${2:-}"
      [ -n "$get_issue" ] || { echo "ERROR: $1 requires a Jira issue key" >&2; exit 2; }
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -n "$env_file" ] && [ ! -f "$env_file" ]; then
  echo "ERROR: env file not found: $env_file" >&2
  exit 2
fi
if [ -n "$check_issue" ] && [ "$check_access" != true ]; then
  echo "ERROR: --issue requires --check-access. Use --get-issue <KEY> to read a Jira story." >&2
  exit 2
fi
if [ "$check_access" = true ] && [ -n "$get_issue" ]; then
  echo "ERROR: choose either --check-access or --get-issue, not both" >&2
  exit 2
fi

load_jira_env() {
  if [ -n "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
  fi
}

prepare_jira_curl_config() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "ERROR: curl is required for Jira REST commands" >&2
    exit 1
  fi

  jira_url="${JIRA_URL:-}"
  jira_url="${jira_url%/}"
  if [ -z "$jira_url" ]; then
    echo "ERROR: JIRA_URL is required for Jira REST commands" >&2
    exit 2
  fi
  personal_token="${JIRA_PERSONAL_TOKEN:-${JIRA_ACCESS_TOKEN:-}}"
  auth_mode=""
  is_atlassian_cloud=false
  case "$jira_url" in
    *".atlassian.net") is_atlassian_cloud=true ;;
  esac

  curl_config="$(mktemp)"
  trap 'rm -f "$curl_config"' EXIT
  chmod 600 "$curl_config"
  {
    printf '%s\n' 'silent'
    printf '%s\n' 'show-error'
    printf '%s\n' 'header = "Accept: application/json"'
    if [ "${JIRA_SSL_VERIFY:-true}" = "false" ]; then
      printf '%s\n' 'insecure'
    fi
    if [ "$is_atlassian_cloud" = true ] && [ -n "${JIRA_USERNAME:-}" ] && [ -n "${JIRA_API_TOKEN:-}" ]; then
      auth_mode="basic"
      basic_auth="$(printf '%s:%s' "$JIRA_USERNAME" "$JIRA_API_TOKEN" | base64 | tr -d '\n')"
      printf 'header = "Authorization: Basic %s"\n' "$basic_auth"
    elif [ -n "$personal_token" ]; then
      auth_mode="bearer"
      printf 'header = "Authorization: Bearer %s"\n' "$personal_token"
    elif [ -n "${JIRA_USERNAME:-}" ] && [ -n "${JIRA_API_TOKEN:-}" ]; then
      auth_mode="basic"
      basic_auth="$(printf '%s:%s' "$JIRA_USERNAME" "$JIRA_API_TOKEN" | base64 | tr -d '\n')"
      printf 'header = "Authorization: Basic %s"\n' "$basic_auth"
    else
      echo "ERROR: JIRA_PERSONAL_TOKEN, JIRA_ACCESS_TOKEN, or JIRA_USERNAME/JIRA_API_TOKEN is required for Jira REST commands" >&2
      exit 2
    fi
  } > "$curl_config"

  echo "Jira access target: $jira_url" >&2
  echo "Jira access auth mode: $auth_mode" >&2
  if [ "$is_atlassian_cloud" = true ] && [ "$auth_mode" = "bearer" ]; then
    echo "WARN: Atlassian Cloud site REST APIs usually require JIRA_USERNAME plus JIRA_API_TOKEN; Bearer tokens against *.atlassian.net commonly return 403." >&2
  fi
}

if [ "$check_access" = true ]; then
  load_jira_env
  prepare_jira_curl_config

  myself_endpoint="$jira_url/rest/api/2/myself"
  status="$(curl --config "$curl_config" --output /dev/null --write-out "%{http_code}" "$myself_endpoint" || true)"
  auth_check_passed=false
  case "$status" in
    200)
      echo "Jira auth check passed: authenticated read access to $jira_url"
      auth_check_passed=true
      ;;
    401|403)
      if [ -n "$check_issue" ]; then
        echo "WARN: Jira /myself check returned HTTP $status; checking issue $check_issue directly." >&2
      else
        echo "ERROR: Jira access check failed with HTTP $status: credentials rejected or insufficient permission" >&2
        exit 1
      fi
      ;;
    000)
      echo "ERROR: Jira access check failed: could not reach $jira_url" >&2
      exit 1
      ;;
    *)
      echo "ERROR: Jira access check failed with HTTP $status" >&2
      exit 1
      ;;
  esac

  if [ -n "$check_issue" ]; then
    issue_endpoint="$jira_url/rest/api/2/issue/$check_issue"
    echo "Jira issue check endpoint: $issue_endpoint"
    issue_status="$(curl --config "$curl_config" --output /dev/null --write-out "%{http_code}" "$issue_endpoint" || true)"
    case "$issue_status" in
      200)
        echo "Jira issue check passed: read access to $check_issue"
        echo "Jira access check passed"
        exit 0
        ;;
      401|403)
        echo "ERROR: Jira issue check failed for $check_issue with HTTP $issue_status: insufficient permission" >&2
        exit 1
        ;;
      404)
        echo "ERROR: Jira issue check failed for $check_issue with HTTP 404: issue not found or not visible" >&2
        exit 1
        ;;
      000)
        echo "ERROR: Jira issue check failed: could not reach $jira_url" >&2
        exit 1
        ;;
      *)
        echo "ERROR: Jira issue check failed for $check_issue with HTTP $issue_status" >&2
        exit 1
        ;;
    esac
  fi

  if [ "$auth_check_passed" != true ]; then
    echo "ERROR: Jira access check failed" >&2
    exit 1
  fi
  echo "Jira access check passed"
  exit 0
fi

if [ -n "$get_issue" ]; then
  load_jira_env
  prepare_jira_curl_config
  fields="summary,description,issuetype,status,priority,assignee,reporter,labels,components,fixVersions,versions,comment,issuelinks,parent,subtasks,created,updated,resolution"
  issue_endpoint="$jira_url/rest/api/2/issue/$get_issue?fields=$fields&expand=renderedFields"
  response_body="$(mktemp)"
  trap 'rm -f "$curl_config" "$response_body"' EXIT
  echo "Jira issue read target: $jira_url" >&2
  echo "Jira issue read auth mode: $auth_mode" >&2
  echo "Jira issue read key: $get_issue" >&2
  issue_status="$(curl --config "$curl_config" --output "$response_body" --write-out "%{http_code}" "$issue_endpoint" || true)"
  case "$issue_status" in
    200)
      cat "$response_body"
      ;;
    401|403)
      echo "ERROR: Jira issue read failed for $get_issue with HTTP $issue_status: insufficient permission" >&2
      exit 1
      ;;
    404)
      echo "ERROR: Jira issue read failed for $get_issue with HTTP 404: issue not found or not visible" >&2
      exit 1
      ;;
    000)
      echo "ERROR: Jira issue read failed: could not reach $jira_url" >&2
      exit 1
      ;;
    *)
      echo "ERROR: Jira issue read failed for $get_issue with HTTP $issue_status" >&2
      exit 1
      ;;
  esac
  printf '\n'
  exit 0
fi

cmd=(docker run --rm -i)

if [ -n "$env_file" ]; then
  cmd+=(--env-file "$env_file")
else
  cmd+=(
    -e JIRA_URL
    -e JIRA_USERNAME
    -e JIRA_API_TOKEN
    -e JIRA_PERSONAL_TOKEN
    -e JIRA_ACCESS_TOKEN
    -e JIRA_SSL_VERIFY
    -e JIRA_PROJECTS_FILTER
    -e TOOLSETS
    -e ENABLED_TOOLS
    -e MCP_VERBOSE
  )
fi

if [ "$allow_writes" = true ]; then
  cmd+=(-e READ_ONLY_MODE=false)
else
  cmd+=(-e READ_ONLY_MODE=true)
fi

cmd+=("$image")

if [ "$dry_run" = true ]; then
  printf '%q ' "${cmd[@]}"
  printf '\n'
  exit 0
fi

exec "${cmd[@]}"
