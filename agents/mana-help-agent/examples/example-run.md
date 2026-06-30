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

## Requested PR Review Example

Input:

```yaml
user_goal: "Review PR 123 quickly."
current_phase: "pull request review"
mcp_status: "gh available"
```

Output:

```yaml
agent: mana-help-agent
status: ready
next_step: "Run requested-pr-review for the selected PR."
commands:
  - "scripts/run-profile.sh requested-pr-review --pr 123 --codex"
warnings:
  - "Add --publish-high-risk-comments only if you want one blocker/high-criticality PR comment to be posted automatically."
```

## Example 3: Read One Jira Story

Input:

```yaml
user_question: "Can Mana read Jira story PROJ-1234?"
mcp_status: "jira env configured"
```

Output:

```yaml
agent: mana-help-agent
status: ready
next_step: "Read the Jira story through the Mana wrapper."
commands:
  - "./mana jira-mcp --get-issue PROJ-1234"
  - "./mana jira-mcp --check-access --issue PROJ-1234"
warnings:
  - "Use --check-access only for credential or permission diagnostics."
```
