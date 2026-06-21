# PR Readiness Flow

PR readiness compiles the description, reviewer focus, test evidence, risk report, and development summary so reviewers spend time on judgement rather than context hunting.

## Operating Principles
- Skills are atomic and reusable.
- Agents orchestrate skills and produce phase artifacts.
- MCP access is governed, audited, redacted, and least-privilege.
- Humans remain accountable for clarity, design, implementation, approval, and correctness.
- AI reduces churn by surfacing gaps early and preserving evidence.

```mermaid
flowchart LR
    Requirements --> Planning --> Development --> Validation --> Review --> Learning
```

## Practical Use
Use the related profiles and templates to create repeatable artifacts. Fill each artifact with project-specific evidence and route blockers to the accountable owner.

## Mana Workspace
PR readiness reads validation and test evidence from the active `.mana` workspace and writes PR artifacts under `pr/`, including `pr-description.md`, `reviewer-focus.md`, `risk-report.md`, `development-summary.md`, `developer-handoff.md`, and `developer-decision-review.md`.
