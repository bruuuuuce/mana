# Runtime usage observability

CTX-01 adds a provider-neutral usage summary for executions that cross Mana's
provider boundary. It is separate from runtime events because event envelopes
remain deliberately free of token and transcript data.

For each execution Mana writes only the following metric artifacts:

```text
.mana/runtime/metrics/<execution-id>/
  usage-summary-v1.json
  usage-summary-v1.md
```

The JSON document follows
`contracts/context-runtime/usage-summary-v1.schema.json`. It contains numeric
provider usage when supplied by the provider, bounded operational counts, and
explicit `null` values for data the provider did not report. Mana never turns
character counts into a measured usage claim. Providers without structured
usage produce `usageStatus: "unavailable"`.

For Codex, Mana requests a JSONL event stream and a separately written final
message. The event stream is created with restrictive permissions in the local
temporary directory, parsed into numeric fields only, and deleted by default.
The final message is relayed to the existing human output channel, preserving
the prior command behaviour.

To retain a raw Codex stream for local debugging only, set:

```text
MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE=true
```

Mana prints a warning and stores the raw stream as
`raw-provider-events.jsonl` beside the summary with restrictive permissions.
That file can contain sensitive provider data and must not be treated as a
delivery artifact. Retention is opt-in; invalid values fail the invocation.

Summaries contain no prompts, final messages, responses, tool payloads, source
content, environment-variable values, credentials, personal notes, or private
reasoning. A provider failure still produces a safe summary when the metrics
directory is writable; any valid usage events emitted before failure are
included.
