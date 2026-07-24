---
name: gui-test-context-discovery
version: 1.0.0
description: Builds a redacted, read-only inventory of GUI test targets, documentation references, test-data references, and environment gaps before authoring browser tests.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - confluence_read
  - jira_read
inputs:
  - application_url_reference
  - documentation_sources
  - testing_policy
outputs:
  - gui_test_context_inventory
  - gui_test_context_gaps
risk_level: medium
owner_role: Developer / QA
stack:
  - any
tags:
  - testing
  - gui
  - browser
  - confluence
  - test-data
model_tier: economy
execution_mode: read
delegation_group: tests
parallel_safe: true
---

# GUI Test Context Discovery

## Purpose
Collect the minimum evidence needed to plan browser tests without opening the
application, using credentials, or copying sensitive test data into Mana.

## When To Use It
Use before authoring GUI tests for an unfamiliar application, or whenever the
test target, roles, data references, or reset procedure are undocumented.

## Workflow
1. Read the testing policy and the supplied documentation references.
2. Record target URL references, user roles, payment-data references, expected
   flows, and source links. Store only identifiers such as `secret_ref`, never
   credentials, PANs, tokens, or personal data.
3. Identify the declared test environment and whether it is isolated from
   production. Treat an unknown target classification as blocked.
4. Produce a redacted context inventory and explicit gaps for unavailable
   Confluence pages, accounts, data, reset procedures, or acceptance criteria.

## Rules
- Access to Jira and Confluence is read-only.
- Do not navigate a live target, test credentials, or payment flows.
- Do not infer account values or transform documentation into secrets.
- A production or unclassified target is a blocker, not a test candidate.

## Outputs
Write a compact inventory with source references, redacted data references,
environment classification, and owner decisions required before authoring.

## Decision Rules
- `blocked`: target is production, unclassified, or required context is absent.
- `warning`: a source, role, reset procedure, or test-only data reference is incomplete.
- `info`: context is sufficient to propose a testbook but still requires approval.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use compact caveman mode: terse, evidence-first notes only. Maintain
a context budget with references, gaps, and next decisions, never raw document
dumps, credentials, or copied sensitive values.
