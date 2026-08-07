# Good Usage

User asks:

```text
I have an epic with two stories, Jira MCP is not configured, and I want to know
what to do first.
```

Expected behavior:

- Recommend `templates/epic-story-pack.template.md`.
- Recommend `.mana/features/<EPIC-ID>/context/epic-story-pack.md`.
- Recommend `scripts/mana-workspace.sh init`.
- Recommend `scripts/run-profile.sh story-start` for each story.
- Highlight evidence gaps and approval gates.

User asks:

```text
How do I reuse my coding conventions across projects without putting my
personal path or preferences into each repository?
```

Expected behavior:

- Explain that User Context is optional and distinct from `.mana/global/`.
- Route configuration to the user-level `MANA_USER_CONTEXT_ROOT` setting.
- Recommend `mana context status`, followed by `mana context refresh` when
  needed.
- Explain that `.mana/user-context/` is generated and should not be committed.
- State that repository evidence and project/service constraints override
  conflicting personal guidance.
- Do not request direct access to or modify the external source directory.
