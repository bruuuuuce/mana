# Bad Usage

Do not answer:

```text
All good, the branch has tests.
```

Why this is bad:

- Passing tests do not prove production safety.
- The skill must reason about failure modes, not only test status.
- Missing observability and rollback gaps can still be production risks.
