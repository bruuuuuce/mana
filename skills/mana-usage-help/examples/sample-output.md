# Sample Output

```yaml
skill: mana-usage-help
status: ready_with_warnings
next_step_recommendation: "Use the Jira fallback story pack, then run story-start."
command_sequence:
  - "scripts/mana-workspace.sh init --root . --feature EPIC-123"
  - "cp templates/epic-story-pack.template.md .mana/features/EPIC-123/context/epic-story-pack.md"
  - "scripts/run-profile.sh story-start"
required_artifacts:
  - ".mana/features/EPIC-123/context/epic-story-pack.md"
  - ".mana/global/service-mission.md"
missing_context:
  - "Jira MCP credentials are not configured."
risk_notes:
  - "Treat missing Jira fields as evidence gaps."
human_review_required: false
```
