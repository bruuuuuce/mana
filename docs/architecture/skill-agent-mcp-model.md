# Skill Agent MCP Model

Skills are reusable analysis units. Agents compose skills into workflow phases. MCP provides governed access to enterprise systems with least privilege, audit, approval, and redaction. Optional read-only CLI helpers, such as GitHub CLI for `github_read`, may be used when already configured by the developer.

## Operating Principles
- Skills are atomic and reusable.
- Agents orchestrate skills and produce phase artifacts.
- MCP access is governed, audited, redacted, and least-privilege.
- Optional CLI helpers are read-only unless a human explicitly approves an
  external write. PR comment publishing is modeled separately from GitHub read
  access and must be scoped to one selected PR.
- Humans remain accountable for clarity, design, implementation, approval, and correctness.
- AI reduces churn by surfacing gaps early and preserving evidence.

## Practical Use
Use the related profiles and templates to create repeatable artifacts. Fill each artifact with project-specific evidence and route blockers to the accountable owner.
