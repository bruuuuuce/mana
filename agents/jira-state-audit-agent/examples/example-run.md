# Jira State Audit Agent Example Run

## Input

```yaml
jira_issue_key: PROJ-1234
target_branch: main
release_branch: release/2.7
fix_version: 2.7.1
policy_file: docs/policies/jira-state-consistency-policy.md
```

## Expected Behavior

The agent reads Jira, Git, GitHub/GHE, branch, tag, and release evidence using
read-only access. It builds a timeline, applies the Jira state consistency
policy, and writes local Mana artifacts only.

## Example Output

```yaml
agent: jira-state-audit-agent
status: ready_with_warnings
verdict: ambiguous
jira_issue_key: PROJ-1234
rationale: "Done is supported by merge evidence, but Released semantics cannot be proven because tag and release metadata are unavailable."
artifacts:
  - validation/jira-state-audit-report.md
  - validation/jira-state-evidence-timeline.md
warnings:
  - "Local clone does not contain release tags."
  - "GitHub release metadata unavailable."
human_approval_required: true
owner: "Team Leader / Release Owner"
external_writes: false
```
