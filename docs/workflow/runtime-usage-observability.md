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

CTX-06C retains those canonical aggregate paths and adds bounded per-invocation
records below the same private execution directory:

```text
.mana/runtime/metrics/<execution-id>/phases/
  <ordinal>-<phase>-attempt-<n>-invocation-<n>.json
  <ordinal>-<phase>-attempt-<n>-invocation-<n>-raw-provider-events.jsonl  # debug opt-in only
```

The aggregate JSON `phases` array carries phase ID, ordinal, semantic attempt,
provider invocation number, provider version, status, numeric usage, and
operational counts. Aggregate totals sum only values actually reported; an
entirely unreported field remains `null`. Existing single-invocation summaries
with `phases: []` remain valid.

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

Provider argv is passed to the wrapper as positional Bash arguments, preserving
argument count, order, repeated flags, and values containing spaces. On `HUP`,
`INT`, or `TERM`, Mana terminates the supervised provider, writes a best-effort
interrupted summary when safe, and removes temporary provider files. Usage
values are accepted only as non-negative integers in Mana's supported numeric
domain; floats, strings, `null`, negatives, and out-of-domain values are never
rounded or used in Bash arithmetic.

To retain a raw Codex stream for local debugging only, set:

```text
MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE=true
```

Mana prints a warning and stores the raw stream as
`raw-provider-events.jsonl` beside the summary with restrictive permissions.
That file can contain sensitive provider data and must not be treated as a
delivery artifact. Retention is opt-in; invalid values fail the invocation.
For a phased run, each retained trace is moved to its matching phase metric
record before the next provider starts, so traces cannot overwrite one another.

Summaries contain no prompts, final messages, responses, tool payloads, source
content, environment-variable values, credentials, personal notes, or private
reasoning. A provider failure still produces a safe summary when the metrics
directory is writable; any valid usage events emitted before failure are
included.

Use `mana runtime metrics <execution-id> --json` to inspect the JSON summary;
without `--json` Mana renders its compact Markdown companion.
