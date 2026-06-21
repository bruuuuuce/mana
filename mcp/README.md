# MCP Integration Layer

The MCP broker is the governed gateway between AI runners and enterprise tools. Policies enforce least privilege, read/write separation, approval for destructive actions, audit logs, redaction, environment separation, and project-level overrides.

## Jira

Jira is wired through the Docker wrapper at `scripts/run-jira-mcp-docker.sh`,
using the existing `ghcr.io/sooperset/mcp-atlassian:latest` MCP server in
read-only mode by default. See `docs/deployment/jira-mcp-docker-wrapper.md`.
