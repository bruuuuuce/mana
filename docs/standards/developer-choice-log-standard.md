# Developer Choice Log Standard

Every story or feature workspace that involves developer interaction must keep
one canonical developer choice log:

```text
.mana/features/<FEATURE-ID>/decisions/developer-choice-log.md
```

For canonical-branch sessions, use:

```text
.mana/sessions/<session-id>/decisions/developer-choice-log.md
```

## Purpose

`developer-choice-log.md` records implementation choices discussed with,
answered by, or confirmed by developers. It is the durable Markdown trace for:

- targeted questions asked to developers;
- developer answers;
- confirmed implementation choices;
- rejected or deferred alternatives;
- evidence and tests supporting the answer;
- Team Leader or specialist acceptance.

It is not a private chain-of-thought log.

## Required Updates

Update or reference this file when any of these happen:

- `developer-decision-review` asks implementation-choice questions.
- A developer confirms why code differs from the plan.
- A developer confirms why a risky or non-obvious approach was chosen.
- A developer confirms intentional non-changes.
- A Team Leader accepts or rejects the developer answer.
- A PR package includes developer rationale.

## Required Table

Use this table:

| Date | Story | Area | Question Or Choice | Developer Answer | Evidence | Confirmed By | Status | Follow-Up |
|---|---|---|---|---|---|---|---|---|

Status values:

- `asked`
- `answered`
- `confirmed`
- `rejected`
- `deferred`
- `needs_owner_review`

## Rules

- Do not mark a choice as `confirmed` without an explicit developer answer or owner acceptance in the input.
- Do not hide unanswered blocker questions.
- Do not store secrets, credentials, raw production data, or unredacted customer data.
- Use concrete evidence: file path, method, test, PR comment, Jira comment, artifact path, or owner note.
- Link related entries in `agent-memory/story-trace.md`.
- If a developer answer changes code or tests, link the follow-up artifact.
