# Good Usage

User asks:

```text
The code introduced in this branch is causing production problems. Find the
most plausible reasons before I commit.
```

Expected behavior:

- Resolve the main branch and inspect the full local branch diff, including
  uncommitted working-tree changes.
- Read nearby code and relevant service context.
- Rank production failure hypotheses by plausibility and impact.
- Identify missing tests, rollback gaps, and missing observability.
- Return blockers, warnings, and mitigation actions.
