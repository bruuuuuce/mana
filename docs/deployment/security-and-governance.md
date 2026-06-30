# Security and Governance

Human accountability remains mandatory. AI recommendations require review for high-risk database, security, cross-service, or architecture findings.

## Operating Principles
- Skills are atomic and reusable.
- Agents orchestrate skills and produce phase artifacts.
- MCP access is governed, audited, redacted, and least-privilege.
- GitHub CLI access, when available, is read-only by default. Agents may use
  `gh` to read PR metadata, changed files, diffs, checks, and reviewer requests,
  but must not comment, approve, request changes, merge, edit, label, or assign
  without explicit human approval.
- `github_pr_comment_write` is a separate, narrow exception: a profile may
  publish at most one `gh pr comment` only when a specific PR and an explicit
  publish flag are provided, and only for blocker or high-criticality findings.
- Humans remain accountable for clarity, design, implementation, approval, and correctness.
- AI reduces churn by surfacing gaps early and preserving evidence.

## Practical Use
Use the related profiles and templates to create repeatable artifacts. Fill each artifact with project-specific evidence and route blockers to the accountable owner.
