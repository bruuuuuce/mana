# Architecture Overview

This repository defines an AI-assisted software delivery framework for enterprise Java and payment systems. It separates atomic skills, orchestrating agents, governed MCP integrations, and human approval gates.

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

## Project-Local Artifact Workspace
The framework expects adopting projects to use a `.mana/` directory for generated artifacts. Feature work is stored under `.mana/features/<feature-id>/`; canonical branch activity is stored under `.mana/sessions/<timestamp>-<branch>-<purpose>/`; durable shared knowledge is stored under `.mana/global/`.
