# MCP Integration Layer

The MCP broker is the governed gateway between AI runners and enterprise tools. Policies enforce least privilege, read/write separation, approval for destructive actions, audit logs, redaction, environment separation, and project-level overrides.

## Jira

Jira is wired through the Docker wrapper at `scripts/run-jira-mcp-docker.sh`,
using the existing `ghcr.io/sooperset/mcp-atlassian:latest` MCP server in
read-only mode by default. See `docs/deployment/jira-mcp-docker-wrapper.md`.

For Jira Server/Data Center, the minimal credential setup is `JIRA_URL` plus
`JIRA_PERSONAL_TOKEN` in the shell that launches the runner, or in an ignored
`.mana/jira-mcp.env` file. Mana profiles pass only discovered issue keys to
agents; credentials stay in the MCP process environment.
