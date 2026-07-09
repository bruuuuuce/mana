# Scenario: Ambiguous Story

**Profile:** `story-start`
**Exercises:** `story-quality`, `acceptance-criteria-testability`,
clarification-question routing, Jira-free fallback flow.

## Setup

1. In a scratch project with a Mana workspace, create
   `.mana/features/PROJ-101/context/epic-story-pack.md` from
   `inputs/epic-story-pack.md`.
2. Run `story-start` without Jira access so the runner must use the story
   pack as the requirement source.

## Intent

The story pack describes a discount feature with detailed UI requirements but
vague error behavior, an unmeasurable acceptance criterion, and a sibling
story that contradicts the discount cap. A correct run reports the asymmetry,
flags the contradiction, and stops with clarification questions instead of
planning implementation on invented requirements.
