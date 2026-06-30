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
- Exclude Mana framework/bootstrap noise from production findings and evidence:
  `.mana/**`, `AGENTS.md`, `CLAUDE.md`, `mana`, and Mana-only `.gitignore` or
  env ignore changes. Mention them only as operational setup notes when relevant.
- For any profile using branch or code diff evidence, resolve and report the
  comparison base. Prefer explicit input, then `origin/HEAD`, then a single
  credible primary branch. If ambiguous, ask the user; do not default to `main`.

## MCP Tool Availability

Claude Code resolves the framework's abstract tool names as follows:

| Abstract tool | Claude Code resolution |
|---|---|
| `read_files` | Native Read tool |
| `code_search` | Native Bash (grep, find) |
| `git_read` | Native Bash (git commands) |
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

Claude Code reads the printed profile and invokes the listed agents and skills.
Output artifacts go into the active `.mana` workspace.
