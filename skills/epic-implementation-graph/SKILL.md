---
name: epic-implementation-graph
version: 1.0.0
description: Produces a reviewable implementation dependency graph for an epic from Jira evidence, existing Mana knowledge, and optionally user-approved read-only service discovery.
compatibility:
  - codex
  - claude
  - opencode
preferred_runner: codex
allowed_tools:
  - jira_read
  - read_files
  - code_search
  - git_read
  - confluence_read
  - architecture_rules_read
inputs:
  - epic_structure_report
  - epic_partitioning_report
  - service_context
  - service_discovery_approved
  - repository_snapshot
outputs:
  - epic_implementation_graph
  - implementation_waves
  - dependency_assumptions
  - service_discovery_report
risk_level: medium
owner_role: Team Leader / Architect
stack:
  - any
tags:
  - epic
  - planning
  - dependencies
  - implementation-graph
model_tier: economy
execution_mode: read
delegation_group: requirements
parallel_safe: true
---

# Epic Implementation Graph

## Purpose
Turn validated epic scope into a proposed directed acyclic graph (DAG) of
implementation prerequisites, parallel work, gates, and unresolved assumptions.
It recommends an order; it does not assign work or approve architecture.

## When To Use It
- Epic structure and sibling-story consistency have already been evaluated.
- A Team Leader needs a proposed delivery order, parallelization opportunities,
  or an explicit dependency register before assigning work.

## Outputs
- `epic_implementation_graph`
- `implementation_waves`
- `dependency_assumptions`
- `service_discovery_report`

## Evidence Order
1. Explicit Jira dependencies, links, acceptance criteria, and statuses.
2. Existing approved Mana knowledge cards and core service context.
3. Read-only repository/service discovery, only when
   `service_discovery_approved` is explicitly `true`.

Never infer a dependency solely because two stories name the same service,
component, person, or release. Mark it as a hypothesis until supported.

## Execution Logic
1. Consume `epic_structure_report` and `epic_partitioning_report`. Do not
   generate a delivery graph if contradictions or critical scope gaps remain
   unresolved; return a partial graph and the blocking questions instead.
2. Read only relevant KB cards through `.mana/global/knowledge/index.md`.
   Record card paths, confidence, verification date, and stale/unknown status.
3. If discovery is not approved, use no repository traversal. State which
   graph edges remain `unverified_without_service_discovery`.
4. If approved, limit discovery to services explicitly named by the epic or
   stories. Inspect ownership, public contracts, deployment/config boundaries,
   and existing integration evidence. Do not scan unrelated repositories,
   write code, call production systems, or change external state.
5. Add graph edges only with evidence and classify each as `hard_dependency`,
   `soft_dependency`, `shared_constraint`, or `unverified_hypothesis`.
6. Emit implementation waves: prerequisites, parallelizable work, integration
   gates, and release/validation gates. A cycle is a blocker, not a suggested
   execution sequence.
7. Escalate architecture, database, security, concurrency, or cross-service
   compatibility judgments to the full specialist when needed. If unavailable,
   return `needs_model_escalation` rather than guessing.

## Decision Rules
- `blocked`: a required edge creates a cycle, a prior contradiction remains, or
  the graph requires unsupported specialist judgment.
- `warning`: an edge is soft, stale, incomplete, or unverified because service
  discovery was not approved.
- `info`: an evidenced dependency or parallelization opportunity.

## Required Output
- A Mermaid DAG plus a tabular edge register: from, to, class, evidence,
  confidence, and owner needed.
- An implementation-wave list that excludes unverified edges from mandatory
  sequencing.
- A service-discovery report showing `not_requested`, `approved_and_checked`,
  or `blocked`, including access gaps.
- Explicit human approvals required before assignment or architectural changes.

## Guardrails
- Read-only only.
- Existing KB is evidence, not authority: respect its confidence and expiry.
- Do not promote or modify KB cards during this skill; use
  `service-knowledge-capture` after a separate approved analysis if durable
  knowledge was found.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md`. Use concise
evidence-first notes, compact caveman mode, and a context budget: retain graph
edges, evidence references, confidence, and next checks rather than raw Jira,
KB, or source transcripts. Do not include private reasoning.
