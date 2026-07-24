# API Test Execution Policy

API validation runs only approved `newman` catalog entries against targets
classified as `isolated_test`. The agent supplies an ID only. It cannot supply
a URL, request, collection command, token, body, or CI action.

Catalog collections and environment files must be relative paths below the
declared absolute `project_root`. Secrets are injected outside Mana and raw
request/response artifacts are access-controlled. Do not publish them or load
them into prompts without review.

Every entry needs explicit approval, matching environment, timeout, and
`requires_explicit_api_approval`. Production, unknown targets, real payment
data, customer data, and irreversible external writes are prohibited. A failure
is a runner result, not automatically an API regression.
