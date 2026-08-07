# Verification Evidence Standard

The canonical result is a schema-version-1 JSON object stored under the active
Mana workspace. It records run/runtime identity, project and diff scope,
selection reasons, skill/spec provenance, checks, fingerprints, fixed argv,
mechanical results, bounded output references, declared and observed effects,
limitations, and zero model/token costs.

The result deliberately contains `judgment: null`. Consumers must not translate
a failed check directly into merge or readiness judgment without review.

Aggregation is mechanical. Unexpected source mutation yields `inconclusive`.
Otherwise, required `blocked`, `inconclusive`, and `failed` checks take
precedence in that order; no checks yields `inconclusive`; a non-passing
optional check yields `partial`; and only all-passing checks yield `passed`.
This ordering prevents a test failure from hiding the absence of required
evidence.

Each check has one stable action fingerprint derived from adapter, normalized
argv, working directory, contract action fields, relevant input digest,
resolved executable identity, trust/effects, and environment digest. A separate
`targetFingerprint` remains stable across an implementation repair, while the
`actionFingerprint` changes when result-relevant input changes. An
`executionFingerprint` governs within-run deduplication, and non-passing checks
include a normalized `failureFingerprint`. V1 does not cache across runs.
All evidence and identity digests use SHA-256; verification refuses execution
when neither `sha256sum` nor `shasum` is available.

Canonical JSON and Markdown are written to same-directory temporary files and
atomically renamed. Raw artifact digests allow consumers to detect later log
changes. A result is not published until it passes Mana's strict envelope
validation.

The sibling `summary.md` is a concise human index, not a replacement for
`result.json`. Full logs are never copied into the summary.
