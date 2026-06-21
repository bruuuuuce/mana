# Example Run

Input:

```yaml
user_goal: "Plan an epic with two stories."
current_phase: "epic intake"
mcp_status: "jira unavailable"
```

Output:

```yaml
agent: mana-help-agent
status: ready_with_warnings
next_step: "Create an epic story pack and run story-start per story."
commands:
  - "scripts/mana-workspace.sh init --root . --feature EPIC-123"
  - "cp templates/epic-story-pack.template.md .mana/features/EPIC-123/context/epic-story-pack.md"
  - "scripts/run-profile.sh story-start"
  - "scripts/run-profile.sh team-planning"
  - "scripts/run-profile.sh story-ready-for-dev"
warnings:
  - "Jira MCP unavailable; keep evidence gaps explicit."
```
