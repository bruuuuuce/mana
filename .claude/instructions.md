# Claude Code Instructions

## Governance Rules

- Read planning artifacts before analysis.
- Resolve the active `.mana` workspace before running planning, validation, PR readiness, or learning workflows.
- Load `.mana/global/service-mission.md`, `.mana/global/architecture.md`, and `.mana/global/engineering-guards.md` when present before producing recommendations.
- Treat violations of `.mana/global/engineering-guards.md` as blockers unless an accountable owner explicitly approves an exception.
- Write planning artifacts, validation reports, PR packages, developer handoff, and learning outputs into the active `.mana` workspace.
- Do not modify the same branch while Junie or Codex is actively editing it.
- Prefer reports, risk registers, and proposed patches over direct destructive edits.
- Respect MCP least privilege, redaction, approval, and audit policies.
- Stop on high-risk database, architecture, security, or cross-service blockers.
- Do not commit automatically. Every commit requires explicit developer approval.
- `github_read` is optional read-only GitHub CLI access. If `gh` exists and is
  authenticated, use it to read PR metadata, diffs, files, checks, and reviewer
  requests. Do not approve, comment, merge, edit, label, assign, or otherwise
  write through `gh` without explicit human approval.
- `github_pr_comment_write` is allowed only when a profile explicitly receives
  `publish_high_risk_comments=true` and a single PR number or URL. In that case,
  publish at most one `gh pr comment` containing blocker or high-criticality
  findings from the current run.
- Exclude Mana framework/bootstrap noise from production findings and evidence:
  `.mana/**`, `AGENTS.md`, `CLAUDE.md`, `mana`, and Mana-only `.gitignore` or
  env ignore changes. Mention them only as operational setup notes when relevant.
- For any profile using branch or code diff evidence, resolve and report the
  comparison base. Prefer explicit input, then `origin/HEAD`, then a single
  credible primary branch. If ambiguous, ask the user; do not default to `main`.
- For any profile using branch or code diff evidence, start with a filtered diff
  inventory, exclude Mana/bootstrap noise, classify changed files by risk domain,
  and read only files needed to validate plausible blocker or warning
  hypotheses. If the filtered diff is larger than roughly 80 files or 2,000
  changed lines, ask the user to choose a review scope instead of scanning the
  whole repository.
- Do not read every skill listed in a profile up front. Read the agent and
  playbook first, load the primary skill needed to start, then load specialist
  skills only when the filtered inputs show their risk domain is relevant.

## MCP Tool Availability

Claude Code resolves the framework's abstract tool names as follows:

| Abstract tool | Claude Code resolution |
|---|---|
| `read_files` | Native Read tool |
| `code_search` | Native Bash (grep, find) |
| `git_read` | Native Bash (git commands) |
| `github_read` | Native Bash (`gh` CLI), read-only when installed and authenticated |
| `github_pr_comment_write` | Native Bash (`gh pr comment`), only with explicit profile approval |
| `architecture_rules_read` | Native Read + code_search |
| `test_runner_read` | Native Bash |
| `test_runner_execute_local` | Native Bash |
| `jira_read` | MCP server — configure via `mcp/config/claude-jira-mcp.json` |
| `confluence_read` | MCP server — same server as Jira (sooperset/mcp-atlassian) |
| `liquibase_validate` | Bash wrapper — `scripts/run-jira-mcp-docker.sh` |
| `database_snapshot_read` | Not natively available; document the gap in the report |
| `logs_observability_read` | Not natively available; document the gap in the report |

Skills requiring `database_snapshot_read` or `logs_observability_read`
(`database-drift`, `incident-risk-forecast`, `non-functional-requirements-review`)
can still run; document the missing context as a warning and continue with
available inputs.

## MCP Configuration

Copy or symlink `mcp/config/claude-jira-mcp.json` to `~/.claude/mcp.json`,
or pass it explicitly:

```bash
claude --mcp-config /path/to/mana/mcp/config/claude-jira-mcp.json
```

Fill in `/path/to/secure/jira-mcp.env` with the credentials documented in
`mcp/env/jira-mcp.env.example`.

## Running Profiles

```bash
# From the Mana repository root or a linked project
scripts/run-profile.sh <profile-name> --project-root /path/to/project
```

Claude Code reads the printed profile, loads the listed agents, and loads only
the primary or conditionally relevant skills.
Output artifacts go into the active `.mana` workspace.
