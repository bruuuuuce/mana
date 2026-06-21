# Story Trace

Story-specific delivery trace for Jira story or feature `{{feature_id}}`.

This file stores concise reasoning traces, evidence, assumptions, decisions,
approval gates, and agent handoff notes for the active story workspace.

Do not store secrets, credentials, raw production data, unredacted customer
data, or private chain-of-thought. Use concise evidence-first notes.

## Story

- Story id: `{{feature_id}}`
- Workspace id: `{{workspace_id}}`
- Branch: `{{branch}}`
- Purpose: `{{purpose}}`
- Created at: `{{created_at}}`

## Current Status

- Status: `initialized`
- Last agent: `none`
- Last update: `{{created_at}}`

## Reasoning Trace

| Date | Agent | Step | Evidence | Assumption | Result | Next Action |
|---|---|---|---|---|---|---|
| `{{created_at}}` | `mana-workspace` | `init` | `manifest.yaml` | Story id maps to workspace id | Workspace initialized | Run the next profile |

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
|---|---|---|---|---|
