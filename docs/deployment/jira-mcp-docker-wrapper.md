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

Use either shell environment variables or an env file outside version control.
For Jira Server/Data Center with a personal access token, the minimal shell
setup is:

```bash
export JIRA_URL=https://jira.your-company.com
export JIRA_PERSONAL_TOKEN=...
export JIRA_SSL_VERIFY=true
```

Then Mana profiles can start the read-only Jira MCP server automatically when
they run through Codex and need `jira_read`.

Alternatively, create an env file:

```bash
cp mcp/env/jira-mcp.env.example mcp/env/jira-mcp.env
chmod 600 mcp/env/jira-mcp.env
```

For Jira Server/Data Center:

```text
JIRA_URL=https://jira.your-company.com
JIRA_PERSONAL_TOKEN=...
JIRA_SSL_VERIFY=true
READ_ONLY_MODE=true
```

For Jira Cloud:

```text
JIRA_URL=https://your-company.atlassian.net
JIRA_USERNAME=your.email@company.com
JIRA_API_TOKEN=...
READ_ONLY_MODE=true
```

For Jira Cloud site REST APIs, use the Atlassian account email plus an
Atlassian API token. Do not use `JIRA_PERSONAL_TOKEN` or `JIRA_ACCESS_TOKEN`
against `*.atlassian.net/rest/api/...`; those Bearer-style tokens commonly
return HTTP 403 on Cloud site URLs.

## Run Manually

```bash
scripts/run-jira-mcp-docker.sh --env-file mcp/env/jira-mcp.env
```

Dry-run the Docker invocation:

```bash
scripts/run-jira-mcp-docker.sh --env-file mcp/env/jira-mcp.env --dry-run
```

Verify credentials without starting Docker or an agent:

```bash
scripts/run-jira-mcp-docker.sh --env-file mcp/env/jira-mcp.env --check-access
```

Verify both authentication and read access to a real issue:

```bash
scripts/run-jira-mcp-docker.sh --env-file mcp/env/jira-mcp.env --check-access --issue PROJ-1234
```

When `--issue` is provided, the issue read is authoritative. Some Jira
installations restrict `/rest/api/2/myself` through SSO or permission policy
even when issue reads work; in that case Mana reports the `/myself` response as
a warning and passes only if the specific issue is readable.

Read a story quickly without starting Docker or an agent:

```bash
scripts/run-jira-mcp-docker.sh --get-issue PROJ-1234
```

In a linked project, use the wrapper:

```bash
./mana jira-mcp --get-issue PROJ-1234
```

The command prints a read-only JSON payload with summary, description,
rendered fields, comments, links, parent/subtasks, and release metadata. It does
not print credentials.

## Codex MCP Configuration

When `scripts/run-profile.sh` finds `.mana/jira-mcp.env`,
`mcp/env/jira-mcp.env`, or the required Jira environment variables, it passes a
read-only Jira MCP server configuration to `codex exec` automatically.

For manual Codex setup, use `mcp/config/codex-jira-mcp.docker.json` as the
starting point and replace the example paths with absolute paths on the machine
running Codex.

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

## Branch Issue Discovery

Mana profiles discover Jira issue keys from the current branch using the
generic default pattern `[A-Z][A-Z0-9]+-[0-9]+`, for example `PROJ-1234`.
Override the pattern per invocation with:

```bash
scripts/run-profile.sh jessica-fletcher --jira-key-regex '(ABC|XYZ)-[0-9]+' --codex
```

Or pass an issue explicitly:

```bash
scripts/run-profile.sh story-start --jira-key PROJ-1234 --codex
```

Issue discovery is a context hint, not a blocker. If no key is found, agents use
local Mana artifacts or ask for story context only when the selected profile
requires it.

## References

- MCP Atlassian: https://github.com/sooperset/mcp-atlassian
- Docker installation: https://mcp-atlassian.soomiles.com/docs/installation
- Configuration: https://mcp-atlassian.soomiles.com/docs/configuration
