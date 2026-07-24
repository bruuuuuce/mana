---
name: gui-testbook-authoring
version: 1.0.0
description: Converts approved GUI requirements and redacted test context into a reviewable Playwright testbook with preconditions, deterministic assertions, and explicit safety gates.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
inputs:
  - gui_test_context_inventory
  - acceptance_criteria
  - existing_gui_testbook
outputs:
  - gui_testbook_proposal
  - playwright_implementation_plan
risk_level: medium
owner_role: Developer / QA
stack:
  - any
tags:
  - testing
  - gui
  - playwright
  - testbook
model_tier: economy
execution_mode: read
delegation_group: tests
parallel_safe: true
---

# GUI Testbook Authoring

## Purpose
Create a reviewable catalog and implementation plan for deterministic browser
tests. The testbook specifies what may run; Playwright code specifies how.

## When To Use It
Use after GUI context discovery and before an owner approves executable
Playwright scenarios.

## Workflow
1. Use the redacted context inventory and acceptance criteria.
2. Define one scenario per catalog entry: role, preconditions, test-data
   references, ordered actions, deterministic assertions, cleanup, and expected
   artifacts.
3. Map the scenario to a Playwright spec and config with trace, screenshot, and
   video enabled. Use locators and semantic assertions, not LLM visual guesses.
4. Set every proposed entry to `approved: false` and `needs_environment` until
   its environment, data reset, and owner approval are verified.

## Rules
- Do not place URLs, secrets, PANs, tokens, or customer data in the catalog.
- Reference secrets only through an environment variable name or vault key.
- Do not author tests that can use production, create irreversible external
  data, or charge a real payment instrument.
- Testbook learning may propose a diff; it never self-approves an entry.

## Outputs
Use `templates/gui-testbook.template.yaml`. Emit an implementation plan and
the approval questions separately from the executable catalog.

## Decision Rules
- `blocked`: target isolation, test-only data, or required reset evidence is absent.
- `warning`: an assertion is visual-only, unstable, or lacks a deterministic locator.
- `info`: a proposed entry is complete but remains unapproved.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use compact caveman mode and a context budget: retain scenarios,
references, approval gates, and gaps, not documentation transcripts or secrets.
