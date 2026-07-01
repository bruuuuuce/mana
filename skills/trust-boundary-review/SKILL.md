---
name: trust-boundary-review
version: 1.0.0
description: Reviews authentication, authorization, validation, sensitive data, and trust boundaries.
compatibility:
  - codex
  - junie
  - claude
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
  - jira_read
  - confluence_read
  - architecture_rules_read
inputs:
  - story
  - code_diff
  - security_rules
  - data_classification
outputs:
  - trust_boundary_report
  - security_questions
  - mitigation_actions
risk_level: high
owner_role: Security / Architect
tags:
  - security
  - trust-boundary
  - privacy
---

# Trust Boundary Review

## Purpose
Detect missing authorization, unsafe data propagation, insufficient validation, PII leakage, and inconsistent trust assumptions between services.

This skill exists to reduce delivery churn by making a narrow, reusable judgement explicit. It produces structured artifacts and recommendations; it does not perform broad autonomous actions.

## When To Use It
- During the lifecycle phase indicated by the tags and preferred runner.
- When the required inputs are available and the team needs a repeatable review.
- Before a human approval gate where missing evidence would slow the team down.
- When a related agent invokes it as one step in a larger workflow.

## When Not To Use It
- Do not use it as a replacement for the accountable human owner.
- Do not use it for unrelated files, binary artifacts, or systems outside the approved MCP policy.
- Do not use it after the decision point if the finding can no longer influence the design without rework.
- Do not use it to justify unsafe shortcuts against project rules.

## Inputs
- story
- code_diff
- security_rules
- data_classification

## Outputs
- trust_boundary_report
- security_questions
- mitigation_actions

## Execution Logic
1. Identify actors, systems, and trust boundaries.
2. Trace sensitive fields across calls and logs.
3. Check authorization decisions near privileged actions.
4. Require human security review for high-risk findings.

## Decision Rules
- `blocker`: unresolved high-risk issue, missing critical input, unsafe database/security/architecture condition, or untestable requirement that prevents responsible delivery.
- `warning`: incomplete evidence, medium-risk design concern, missing non-critical test, or ambiguity that can be accepted by the owner.
- `info`: observation useful for reviewers, implementation, or future learning.

## Failure Modes
- Missing or stale input artifacts can produce false negatives.
- Repository search can miss dynamically configured flows or generated code.
- MCP access restrictions can prevent full validation; report the access gap explicitly.
- AI output can be incomplete; human review remains mandatory.

## Required Human Review
The owner role `Security / Architect` reviews blocker and warning findings. High-risk security, database, concurrency, or architecture findings require explicit approval before implementation or merge.

## Interaction With Codex
Codex should run this skill for repository-level analysis, planning, validation, documentation, and report generation. Codex should prefer proposed patches and written findings over destructive edits.

## Interaction With Junie
Junie may use the output inside the IDE to implement one approved task at a time, generate local tests, or apply local fixes. Junie must not change files outside the approved impact map without asking.

## Interaction With MCP
MCP access must be least-privilege. Read-only access is preferred. Writes, destructive operations, external comments, database execution, or ticket updates require human approval and audit logging.

## Correct Usage Examples
- Run during the intended lifecycle phase with the full story, context, and linked artifacts available.
- Use the output as evidence for refinement, planning, review, or local implementation decisions.
- Escalate blocker findings to the named human owner before continuing.
- Store the generated report with the story or branch artifacts so later agents can reuse it.

## Incorrect Usage Examples
- Do not use this skill as an autonomous code-changing tool.
- Do not run it with only a title or vague one-line request and treat the result as complete.
- Do not ignore high-severity findings because the output is advisory.
- Do not use it to bypass team, architecture, DBA, security, or reviewer approval.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output Standard) for all generated artifacts. Use `templates/standard-agent-skill-report.template.md` when no more specific template exists.

Internal reasoning must use compact caveman mode: terse fragments, evidence-first notes, no long narrative, and no private chain-of-thought in final artifacts. Maintain a context budget: keep a short working summary with objective, base branch or PR, issue keys, workspace path, checked evidence, open hypotheses, discarded hypotheses, and next checks instead of accumulating raw transcripts, full diffs, repeated file dumps, or copied tool output.

## Diagram
```mermaid
flowchart TD
    Inputs[Required inputs] --> Skill[trust-boundary-review]
    Skill --> Findings[Findings by severity]
    Skill --> Artifacts[Structured outputs]
    Findings --> HumanGate[Human review gate]
    Artifacts --> NextAgent[Downstream agent or workflow]
```

## Example Output
```yaml
skill: trust-boundary-review
status: warning
summary: "Analysis completed with one blocker candidate and two warnings."
findings:
  - severity: warning
    area: "example"
    message: "A required detail or verification point is incomplete."
    recommended_action: "Clarify with the owner and update the related artifact."
outputs:
  - trust_boundary_report
  - security_questions
  - mitigation_actions
human_review_required: true
```
