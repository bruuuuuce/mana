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
- `mana inspect` is deterministic and read-only, uses project-relative paths,
  and quarantines rather than follows workspace/source symlinks. It bounds
  exposed detail payloads to 64 KiB and JSON depth 32; consumers must treat
  returned Markdown/text as untrusted content and never execute it.
- Inspect and pilot-feedback data are local workspace artifacts, not uploads or
  background telemetry. Review their contents before sharing; pilot aggregates
  intentionally omit raw references and notes.
- Path containment, redaction, and payload limits reduce accidental exposure;
  Mana does not claim to be an OS sandbox against hostile files, processes, or
  a compromised local checkout.
