# Security Policy

Mana is a framework for delivery governance and evidence management. It can be
connected to Jira, Confluence, CI, logs, databases, and other sensitive systems
through MCP or local wrappers, so security issues should be handled carefully.

## Reporting A Vulnerability

If this repository is hosted on GitHub, report vulnerabilities through GitHub
Security Advisories when available. If advisories are not enabled, open a
private report through the repository owner's documented security contact.

Do not include secrets, production customer data, credentials, tokens, payment
data, or unredacted logs in public issues, discussions, pull requests, prompts,
or generated artifacts.

## Supported Versions

Until the project publishes versioned releases, the `main` branch is the only
supported line.

## Security Expectations

- MCP access should be least-privilege and read-only by default.
- External writes, destructive operations, deployments, Jira transitions, and
  database execution require explicit human approval.
- Credentials should live in ignored env files or secret managers, never in the
  repository.
- Generated `.mana/` artifacts should be reviewed before sharing or committing.
- Production data must be redacted before it is used in prompts, reports, or
  examples.
