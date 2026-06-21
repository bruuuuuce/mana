# Jira MCP Docker Wrapper

This framework integrates Jira through the existing `sooperset/mcp-atlassian`
MCP server and a local wrapper script:

```text
Codex
  -> scripts/run-jira-mcp-docker.sh
  -> ghcr.io/sooperset/mcp-atlassian:latest
  -> Jira
```

The wrapper keeps the framework policy in one place:

- `READ_ONLY_MODE=true` is forced by default.
- write-capable Jira tools require the explicit `--allow-writes` flag.
- credentials are supplied through environment variables or an env file.
- project/tool filtering can be applied without changing agent or skill files.

## Configure

Create an env file outside version control:

```bash
cp mcp/env/jira-mcp.env.example mcp/env/jira-mcp.env
chmod 600 mcp/env/jira-mcp.env
```

For Jira Cloud:

```text
JIRA_URL=https://your-company.atlassian.net
JIRA_USERNAME=your.email@company.com
JIRA_API_TOKEN=...
READ_ONLY_MODE=true
```

For Jira Server/Data Center:

```text
JIRA_URL=https://jira.your-company.com
JIRA_PERSONAL_TOKEN=...
JIRA_SSL_VERIFY=true
READ_ONLY_MODE=true
```

## Run Manually

```bash
scripts/run-jira-mcp-docker.sh --env-file mcp/env/jira-mcp.env
```

Dry-run the Docker invocation:

```bash
scripts/run-jira-mcp-docker.sh --env-file mcp/env/jira-mcp.env --dry-run
```

## Codex MCP Configuration

Use `mcp/config/codex-jira-mcp.docker.json` as the starting point and replace
the example paths with absolute paths on the machine running Codex.

```json
{
  "mcpServers": {
    "jira": {
      "command": "/absolute/path/to/mana/scripts/run-jira-mcp-docker.sh",
      "args": [
        "--env-file",
        "/absolute/path/to/secure/jira-mcp.env"
      ]
    }
  }
}
```

Keep write operations disabled for normal story planning, branch validation, and
PR readiness. If a workflow needs comments or transitions, require explicit
human approval and run the wrapper with `--allow-writes` only for that approved
session.

## Default Read-Only Jira Surface

The example env file restricts the exposed surface to Jira read-only tools used
by story planning, branch validation, and PR readiness:

- `jira_get_issue`
- `jira_search`
- `jira_search_fields`
- `jira_get_transitions`
- `jira_get_all_projects`
- `jira_get_project_issues`
- `jira_get_agile_boards`
- `jira_get_board_issues`
- `jira_get_sprints_from_board`
- `jira_get_sprint_issues`
- `jira_get_link_types`
- `jira_get_project_versions`
- `jira_get_project_components`

Use `JIRA_PROJECTS_FILTER`, `TOOLSETS`, or `ENABLED_TOOLS` in the env file to
reduce the exposed surface.

## References

- MCP Atlassian: https://github.com/sooperset/mcp-atlassian
- Docker installation: https://mcp-atlassian.soomiles.com/docs/installation
- Configuration: https://mcp-atlassian.soomiles.com/docs/configuration
