# Claude Code Setup

Use Claude Code for planning, repository analysis, branch validation, PR readiness, documentation, development support, and learning. Claude Code can act as both a repository-level runner (like Codex) and a local implementation runner (like Junie) depending on the active profile.

Claude Code must respect MCP policies and prefer reports or proposed patches over destructive edits.

Claude Code should resolve the active `.mana` workspace before producing artifacts. Feature work belongs under `.mana/features/<feature-id>/`; canonical branch work belongs under `.mana/sessions/<timestamp>-<branch>-<purpose>/`.

For Jira and Confluence access, configure the MCP server using `mcp/config/claude-jira-mcp.json`. See `docs/deployment/jira-mcp-docker-wrapper.md`.
