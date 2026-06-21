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
  --help               Show this help.

Required Jira configuration:
  Jira Cloud:
    JIRA_URL=https://your-company.atlassian.net
    JIRA_USERNAME=your.email@company.com
    JIRA_API_TOKEN=...

  Jira Server/Data Center:
    JIRA_URL=https://jira.your-company.com
    JIRA_PERSONAL_TOKEN=...

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

cmd=(docker run --rm -i)

if [ -n "$env_file" ]; then
  cmd+=(--env-file "$env_file")
else
  cmd+=(
    -e JIRA_URL
    -e JIRA_USERNAME
    -e JIRA_API_TOKEN
    -e JIRA_PERSONAL_TOKEN
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
