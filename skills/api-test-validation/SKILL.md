---
name: api-test-validation
version: 1.0.0
description: Authors and executes explicitly approved Newman API testbook entries against isolated test targets, preserving access-controlled request evidence and redacted reports.
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
  - test_runner_read
  - test_runner_execute_local
inputs:
  - api_requirements
  - api_testbook
  - requested_test_ids
  - environment_name
outputs:
  - api_testbook_proposal
  - api_test_run_report
  - api_test_learning_proposal
risk_level: high
owner_role: Developer / QA
stack:
  - any
tags:
  - testing
  - api
  - newman
  - contract
model_tier: economy
execution_mode: write
delegation_group: tests
parallel_safe: false
---

# API Test Validation

## Purpose
Build and execute a bounded API testbook for isolated test targets. The agent
selects approved IDs; the runner resolves a local Newman collection and never
accepts a URL, request body, credentials, or shell command from the agent.

## When To Use It
Use when API requirements, OpenAPI/collection evidence, or existing automated
requests must become repeatable regression or integration validation.

## Workflow
1. Read API requirements and source references; record only secret references.
2. Propose one catalog entry per collection scenario with deterministic status,
   schema, and negative-path assertions. Keep it unapproved.
3. Require owner approval of target, data reset, and entries.
4. Execute selected entries through `scripts/run-api-testbook.sh`.
5. Produce a redacted report and an approval-required learning proposal.

## Rules
- Target classification must be `isolated_test`; production and unknown targets
  are blocked.
- Newman collection and environment files are local repository artifacts.
- Credentials and sensitive request/response data remain outside the catalog and
  must not appear in reports. Raw artifacts are access-controlled.
- A failing request is not proof of an API regression without cause evidence.

## Outputs
Write an API testbook proposal, run report, artifact references, and learning
proposal. Use `templates/api-testbook.template.yaml`.

## Decision Rules
- `passed`: Newman exits successfully and expected report files exist.
- `failed`: the approved collection command exits non-zero.
- `blocked`: target, approval, collection, environment, or policy gate fails.
- `inconclusive`: evidence cannot isolate product, contract, data, or environment cause.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use compact caveman mode and a context budget: keep source references,
IDs, artifacts, gaps, and cause hypotheses, never raw payloads, tokens, or logs.
