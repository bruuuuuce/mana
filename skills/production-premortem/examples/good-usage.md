# Good Usage

User asks:

```text
The code introduced in this branch is causing production problems. Find the
most plausible reasons before I commit.
```

Expected behavior:

- Inspect staged and branch diff.
- Read nearby code and relevant service context.
- Rank production failure hypotheses by plausibility and impact.
- Identify missing tests, rollback gaps, and missing observability.
- Return blockers, warnings, and mitigation actions.
