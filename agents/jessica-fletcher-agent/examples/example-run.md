# Example Run

Input:

```yaml
staged_diff: "git diff --cached"
branch_diff: "git diff origin/main...HEAD"
story_context: ".mana/features/PROJ-123/context/story-context.md"
test_evidence: ".mana/features/PROJ-123/tests/test-evidence.md"
```

Output:

```yaml
agent: jessica-fletcher-agent
status: warning
stop_go: "fix_before_push"
top_hypotheses:
  - severity: warning
    hypothesis: "New fallback path can hide downstream timeout."
    evidence:
      - "Timeout exception is converted to default status."
    mitigation: "Add explicit pending state and integration test."
missing_tests:
  - "No integration test for downstream timeout."
missing_signals:
  - "No metric for fallback activation."
```
