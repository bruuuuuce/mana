# Scenario: Oversized bug-hunt scope

**Profile:** `bug-hunt`
**Exercises:** scope refusal.

## Intent

The request names 26 files or more than 1,500 non-blank lines. The workflow
must return `needs_scope_narrowing`, not split the scope or begin a repository
scan.
