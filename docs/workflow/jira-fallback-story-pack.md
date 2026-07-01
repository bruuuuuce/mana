# Jira Fallback Story Pack

When Jira MCP is unavailable, incomplete, or intentionally disabled, use a
manual Markdown story pack as the source of requirement evidence.

When Jira MCP is available, prefer the read-only Markdown cache command instead
of hand-copying issue JSON:

```bash
./mana jira-mcp --fetch-epic-story-pack PROJ-1234
```

The command resolves the parent epic when possible, fetches sibling stories, and
writes:

```text
.mana/features/<EPIC-ID>/evidence/jira/epic-story-pack.md
```

That generated pack is the default requirement evidence for epic/story slicing
reviews. It avoids repeated Jira downloads and keeps agents out of raw Jira JSON.

Template:

```text
templates/epic-story-pack.template.md
```

Recommended workspace path:

```text
.mana/features/<EPIC-ID>/context/epic-story-pack.md
```

For story-specific planning, copy or reference the same pack from:

```text
.mana/features/<STORY-ID>/context/epic-story-pack.md
```

## Rules

- Prefer the generated Jira Markdown cache when Jira read access works.
- Mark `Source mode` as `manual-md-fallback`.
- Record why Jira was unavailable or intentionally skipped.
- Include the epic and every story expected in the delivery slice.
- Keep Jira keys when known, even if the data was copied manually.
- Preserve acceptance criteria exactly when they came from Jira or BA/PO.
- Add evidence gaps instead of inventing missing facts.

## How Agents Should Use It

The story implementation planner may use the story pack in place of `jira_read`
inputs when Jira MCP access is unavailable. Any missing or uncertain field should
be reported as a warning or blocker depending on delivery risk.

The fallback does not reduce approval requirements. Requirement blockers still
belong to BA/PO or Team Leader; architecture, database, security, and contract
blockers still require their normal owners.

## Codex Prompt Pattern

```text
Use docs/workflow/jira-fallback-story-pack.md.
Jira MCP is unavailable for this run.
Read .mana/features/<EPIC-ID>/context/epic-story-pack.md as the requirement source.
Run the story-start workflow for <STORY-ID>.
Treat missing fields as evidence gaps; do not invent Jira data.
```
