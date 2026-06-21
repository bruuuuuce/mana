#!/usr/bin/env bash
set -u

usage() {
  cat <<'USAGE'
Usage:
  scripts/mana-workspace.sh resolve [options]
  scripts/mana-workspace.sh init [options]
  scripts/mana-workspace.sh status [options]

Commands:
  resolve   Print the workspace path that matches the current branch and options. No files are created.
  init      Create the .mana workspace structure and activate it for the current project.
  status    Print the currently activated workspace when available, then print the default resolved path.

Options:
  --root <path>       Target project root. Defaults to current directory.
  --branch <name>    Branch name. Defaults to current Git branch when available.
  --feature <id>     Explicit feature/story id. Overrides ticket extraction.
  --purpose <name>   Session purpose. Defaults to story-delivery for features and repo-audit for canonical branches.
  --activate         Write .mana/active-workspace. Default for init.
  --no-activate      Do not update .mana/active-workspace.
  --force            Refresh generated manifest and index files. Does not overwrite logs or evidence.
  --help             Show this help.

Workspace routing:
  Feature id provided:       .mana/features/<feature-id>/
  Feature branch with ticket: .mana/features/<ticket-id>/
  Canonical branch:          .mana/sessions/<timestamp>-<branch>-<purpose>/
  Other branch:              .mana/features/<slugified-branch>/

This command does not initialize a Git branch. It creates or resolves the project-local
evidence workspace used by Codex, Junie, agents, and skills.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

command="${1:-}"
if [ -z "$command" ]; then
  usage
  exit 2
fi
shift

case "$command" in
  resolve|init|status) ;;
  --help|-h|help) usage; exit 0 ;;
  *) fail "unknown command: $command" ;;
esac

framework_root="$(cd "$(dirname "$0")/.." && pwd)"
root="$(pwd)"
branch=""
feature=""
purpose=""
activate="auto"
force=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root) root="${2:-}"; shift 2 ;;
    --branch) branch="${2:-}"; shift 2 ;;
    --feature) feature="${2:-}"; shift 2 ;;
    --purpose) purpose="${2:-}"; shift 2 ;;
    --activate) activate=true; shift ;;
    --no-activate) activate=false; shift ;;
    --force) force=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done

[ -n "$root" ] || fail "root cannot be empty"

if [ -z "$branch" ]; then
  branch="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
fi

if [ -z "$branch" ] || [ "$branch" = "HEAD" ]; then
  branch="manual"
fi

slugify() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g'
}

extract_ticket() {
  printf '%s' "$1" | grep -Eio '[A-Z][A-Z0-9]+-[0-9]+' | head -n 1 | tr '[:lower:]' '[:upper:]' || true
}

is_canonical_branch() {
  case "$1" in
    main|master|develop|dev|release/*|hotfix/*) return 0 ;;
    *) return 1 ;;
  esac
}

timestamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
canonical=false
workspace_type="feature"
workspace_id=""
feature_id=""

if [ -n "$feature" ]; then
  feature_id="$feature"
  workspace_id="$feature_id"
  workspace_type="feature"
  [ -z "$purpose" ] && purpose="story-delivery"
elif is_canonical_branch "$branch"; then
  canonical=true
  workspace_type="session"
  [ -z "$purpose" ] && purpose="repo-audit"
  branch_slug="$(slugify "$branch")"
  purpose_slug="$(slugify "$purpose")"
  workspace_id="${timestamp}-${branch_slug}-${purpose_slug}"
else
  ticket="$(extract_ticket "$branch")"
  if [ -n "$ticket" ]; then
    feature_id="$ticket"
    workspace_id="$ticket"
  else
    branch_slug="$(slugify "$branch")"
    [ -n "$branch_slug" ] || branch_slug="manual-${timestamp}"
    feature_id="$branch_slug"
    workspace_id="$branch_slug"
  fi
  workspace_type="feature"
  [ -z "$purpose" ] && purpose="story-delivery"
fi

if [ "$workspace_type" = "feature" ]; then
  workspace_path="$root/.mana/features/$workspace_id"
  workspace_relative=".mana/features/$workspace_id"
else
  workspace_path="$root/.mana/sessions/$workspace_id"
  workspace_relative=".mana/sessions/$workspace_id"
fi

if [ "$command" = "resolve" ]; then
  echo "$workspace_path"
  exit 0
fi

if [ "$command" = "status" ]; then
  active_file="$root/.mana/active-workspace"
  if [ -f "$active_file" ]; then
    active_path="$(sed -n '1p' "$active_file")"
    echo "Active workspace: $root/$active_path"
  else
    echo "Active workspace: none"
  fi
  echo "Default resolved workspace: $workspace_path"
  echo "Resolution source: branch=${branch}; feature=${feature:-auto}; purpose=${purpose}"
  exit 0
fi

if [ "$activate" = "auto" ]; then
  activate=true
fi

mkdir -p \
  "$workspace_path/context" \
  "$workspace_path/planning" \
  "$workspace_path/agent-memory" \
  "$workspace_path/skill-outputs" \
  "$workspace_path/decisions" \
  "$workspace_path/tests" \
  "$workspace_path/validation" \
  "$workspace_path/pr" \
  "$workspace_path/learning" \
  "$root/.mana/global/rules" \
  "$root/.mana/global/known-pitfalls" \
  "$root/.mana/global/team-decisions"

write_if_missing() {
  file="$1"
  content="$2"
  if [ ! -f "$file" ]; then
    printf '%s\n' "$content" > "$file"
  fi
}

write_generated_file() {
  file="$1"
  content="$2"
  if [ "$force" = true ] || [ ! -f "$file" ]; then
    printf '%s\n' "$content" > "$file"
  fi
}

write_global_file_if_missing() {
  file="$1"
  title="$2"
  body="$3"
  write_if_missing "$root/.mana/global/$file" "# $title

$body"
}

hooks_config_template="$framework_root/templates/mana-workspace/global/hooks-config.template.yaml"
if [ -f "$hooks_config_template" ]; then
  write_if_missing "$root/.mana/global/hooks-config.yaml" "$(cat "$hooks_config_template")"
fi

write_global_file_if_missing "service-mission.md" "Service Mission" "Describe what this service does, why it exists, where it sits in the wider architecture, what it owns, what it must not do, and which business capability it supports."
write_global_file_if_missing "architecture.md" "Service Architecture" "Describe components, runtime flows, data ownership, boundaries, dependencies, approved patterns, and known constraints."
write_global_file_if_missing "engineering-guards.md" "Engineering Guards" "List non-negotiable rules, forbidden actions, protected areas, required approval gates, and patterns that agents and developers must respect."
write_global_file_if_missing "domain-glossary.md" "Domain Glossary" "Define domain terms, statuses, enums, business meanings, and ownership."
write_global_file_if_missing "integration-map.md" "Integration Map" "Document inbound and outbound APIs, events, topics, payload ownership, timeout, retry, idempotency, and error mapping."
write_global_file_if_missing "testing-policy.md" "Testing Policy" "Document critical behaviors, green-border expectations, regression requirements, test data rules, and flaky test handling."
write_global_file_if_missing "database-policy.md" "Database Policy" "Document critical tables, forbidden operations, rollback rules, Liquibase rules, DBA approval gates, and drift handling."

if [ -n "$feature_id" ]; then
  feature_yaml="\"$feature_id\""
  feature_label="$feature_id"
else
  feature_yaml="null"
  feature_label="none"
fi

manifest_content="workspace_type: \"$workspace_type\"
workspace_id: \"$workspace_id\"
branch: \"$branch\"
feature_id: $feature_yaml
purpose: \"$purpose\"
created_at: \"$timestamp\"
canonical_branch: $canonical
artifact_root: \"$workspace_relative\"
story_trace: \"$workspace_relative/agent-memory/story-trace.md\"
developer_choice_log: \"$workspace_relative/decisions/developer-choice-log.md\"
framework_version: \"1.0.0\"
policy:
  ai_may_modify_code: false
  require_human_approval_for_scope_expansion: true
  require_human_approval_for_external_writes: true"

index_content="# Mana Workspace Index

## Workspace
- Type: \`$workspace_type\`
- Id: \`$workspace_id\`
- Branch: \`$branch\`
- Feature: \`$feature_label\`
- Purpose: \`$purpose\`
- Created at: \`$timestamp\`

## Artifact Map
- \`.mana/global/\`: service mission, architecture, engineering guards and stable service context.
- \`.mana/global/hooks-config.yaml\`: project-level skill toggles for pre-commit and pre-push hooks.
- \`.mana/active-profile\`: currently active Mana profile, written by profile-selector skill.
- \`context/\`: story, epic, clarifications and open questions.
- \`planning/\`: source impact, implementation plan, technical breakdown and risks.
- \`agent-memory/\`: partial findings and agent notes.
- \`agent-memory/story-trace.md\`: canonical story-specific reasoning summary, decisions, approvals and handoffs.
- \`skill-outputs/\`: individual skill reports.
- \`decisions/\`: decisions, clarifications and approvals.
- \`decisions/developer-choice-log.md\`: developer-confirmed implementation choices and rationale.
- \`tests/\`: green-border, regression and test evidence.
- \`validation/\`: branch validation, drift, missing tests and risk status.
- \`pr/\`: PR package, reviewer focus, development summary and developer handoff.
- \`pr/pre-commit-development-summary.md\`: what changed before commit and why.
- \`pr/knowledge-transfer-brief.md\`: call-ready knowledge-transfer walkthrough.
- \`learning/\`: known pitfalls, incident learning and rule suggestions.

## Current Status
Initialized. Replace this section with the latest validated state when agents start producing evidence."

write_generated_file "$workspace_path/manifest.yaml" "$manifest_content"
write_generated_file "$workspace_path/index.md" "$index_content"

write_if_missing "$workspace_path/decisions/decision-log.md" "# Decision Log

| Date | Decision | Context | Owner | Impact | Follow-Up |
|---|---|---|---|---|---|"

developer_choice_log_content="# Developer Choice Log

Story-specific log of implementation choices discussed with and confirmed by developers for \`$feature_label\`.

Do not store secrets, credentials, raw production data, unredacted customer data,
or private chain-of-thought.

## Story

- Story id: \`$feature_label\`
- Workspace id: \`$workspace_id\`
- Branch: \`$branch\`
- Created at: \`$timestamp\`

## Choices

| Date | Story | Area | Question Or Choice | Developer Answer | Evidence | Confirmed By | Status | Follow-Up |
|---|---|---|---|---|---|---|---|---|

## Open Developer Questions

| Date | Question | Evidence | Required Before | Owner |
|---|---|---|---|---|

## Confirmation Notes

- Record only explicit developer answers or owner decisions.
- Use \`asked\`, \`answered\`, \`confirmed\`, \`rejected\`, \`deferred\`, or \`needs_owner_review\`."

write_if_missing "$workspace_path/decisions/developer-choice-log.md" "$developer_choice_log_content"

write_if_missing "$workspace_path/agent-memory/partial-findings.md" "# Partial Findings

Use this file for resumable agent notes. Do not store secrets, credentials, raw production data, or unredacted customer data."

story_trace_content="# Story Trace

Story-specific delivery trace for Jira story or feature \`$feature_label\`.

This file stores concise reasoning traces, evidence, assumptions, decisions,
approval gates, and agent handoff notes for the active story workspace.

Do not store secrets, credentials, raw production data, unredacted customer data,
or private chain-of-thought. Use concise evidence-first notes.

## Story

- Story id: \`$feature_label\`
- Workspace id: \`$workspace_id\`
- Branch: \`$branch\`
- Purpose: \`$purpose\`
- Created at: \`$timestamp\`

## Current Status

- Status: \`initialized\`
- Last agent: \`none\`
- Last update: \`$timestamp\`

## Reasoning Trace

| Date | Agent | Step | Evidence | Assumption | Result | Next Action |
|---|---|---|---|---|---|---|
| \`$timestamp\` | \`mana-workspace\` | \`init\` | \`manifest.yaml\` | Story id maps to workspace id | Workspace initialized | Run the next profile |

## Decisions

| Date | Decision | Rationale | Owner | Impact | Approval Status | Follow-Up |
|---|---|---|---|---|---|---|

## Open Questions

| Question | Owner | Required By | Blocks |
|---|---|---|---|

## Approval Gates

| Gate | Status | Owner | Evidence | Action |
|---|---|---|---|---|

## Agent Handoff

| Date | From Agent | To Agent | Context | Required Next Step |
|---|---|---|---|---|"

write_if_missing "$workspace_path/agent-memory/story-trace.md" "$story_trace_content"

if [ "$activate" = true ]; then
  printf '%s\n' "$workspace_relative" > "$root/.mana/active-workspace"
fi

echo "Mana workspace initialized: $workspace_path"
if [ "$activate" = true ]; then
  echo "Active workspace set to: $workspace_relative"
fi
