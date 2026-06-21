# Story Trace Standard

Every feature or Jira-story workspace must maintain one canonical story trace:

```text
.mana/features/<JIRA-KEY>/agent-memory/story-trace.md
```

For canonical-branch sessions, use the equivalent session workspace:

```text
.mana/sessions/<session-id>/agent-memory/story-trace.md
```

## Purpose

`story-trace.md` is the single story-specific Markdown file that links agent
reasoning summaries, assumptions, decisions, approval gates, and handoffs.

It is not a private chain-of-thought log. Agents must write concise,
evidence-first delivery trace notes only.

## Required Updates

Every agent that runs against a story, branch, release, or PR must update or
reference `agent-memory/story-trace.md` with:

- agent name;
- timestamp when known;
- story or feature id;
- current step;
- evidence used;
- assumptions made;
- decision rationale;
- owner or approval gate;
- next action;
- links to generated artifacts.

## Reasoning Trace Table

Use this table:

| Date | Agent | Step | Evidence | Assumption | Result | Next Action |
|---|---|---|---|---|---|---|

Keep each row short. Prefer artifact paths over long explanations.

## Decision Table

Use this table:

| Date | Decision | Rationale | Owner | Impact | Approval Status | Follow-Up |
|---|---|---|---|---|---|---|

Approval status values:

- `proposed`
- `approved`
- `rejected`
- `deferred`
- `needs_human_decision`

## Rules

- Do not write secrets, credentials, raw production data, or unredacted customer data.
- Do not publish private chain-of-thought.
- Do not mark approvals as complete unless explicit approval exists in the input.
- Do not split the canonical story trace across multiple competing files.
- Agent-specific notes may still exist, but they must link back to `story-trace.md`.
