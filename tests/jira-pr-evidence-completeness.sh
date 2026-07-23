#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
status=0

require() {
  pattern="$1"
  file="$2"
  if ! rg -q --fixed-strings "$pattern" "$file"; then
    echo "ERROR: missing '$pattern' in $file" >&2
    status=1
  fi
}

jira_wrapper="$root/scripts/run-jira-mcp-docker.sh"
jira_skill="$root/skills/jira-release-state-evidence/SKILL.md"
pr_agent="$root/agents/requested-pr-review-agent/AGENT.md"

require 'fields=*all&expand=renderedFields,names,schema' "$jira_wrapper"
require '/comment?startAt=$start_at&maxResults=100' "$jira_wrapper"
require '/properties' "$jira_wrapper"
require '"all_comments"' "$jira_wrapper"
require '"issue_properties"' "$jira_wrapper"
require 'all visible custom' "$jira_skill"
require 'review-thread resolution state' "$jira_skill"
require 'paginated `gh api` calls' "$pr_agent"
require 'GraphQL `reviewThreads`' "$pr_agent"
require 'do not infer `resolved`' "$pr_agent"
require 'general comments cannot be proven' "$pr_agent"

if [ "$status" -eq 0 ]; then
  echo "Jira and PR evidence completeness checks passed"
fi
exit "$status"
