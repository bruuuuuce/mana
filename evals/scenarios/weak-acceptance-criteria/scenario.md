# Scenario: Weak Acceptance Criteria

**Profile:** `story-ready-for-dev`
**Exercises:** `acceptance-criteria-testability`, `developer-readiness-check`,
start/no-start recommendation.

## Setup

1. Create `.mana/features/PROJ-201/context/epic-story-pack.md` from
   `inputs/story.md`.
2. Run `story-ready-for-dev` without Jira access.

## Intent

The story has plausible-sounding acceptance criteria, but none of them define
observable inputs, outputs, preconditions, or failure behavior, and the story
names no owner for the open pricing question. A correct run recommends
no-start with concrete questions, instead of passing the story because the
prose looks complete.
