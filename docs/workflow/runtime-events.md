# Mana Runtime Events

Mana records a small, repository-local audit trail below `.mana/runtime/` when
`mana cast` crosses into execution. It uses append-oriented JSON Lines at
`events/<execution-id>.jsonl` and session snapshots at `sessions/`. `.mana/`
is already ignored by bootstrap and repository conventions, so runtime records
are never delivery artifacts or committed telemetry.

The versioned envelope contains IDs, an ISO timestamp, profile/component IDs,
status, controlled attributes, and evidence references. Event ordering is the
append order and event IDs carry an execution-local sequence. A short
directory lock protects concurrent writers.

## Taxonomy and guarantees

`profile.started`, `profile.completed`, `profile.failed`, `skill.selected`,
`model.selected`, `approval.required`, `guard.triggered`, `evidence.read`, and
`evidence.missing` are emitted at the cast boundary when that fact is known.
Profile lifecycle, selected skills, model routing, and Service Context checks
are reliable. Runner-internal `tool.invoked`, `tool.blocked`, subagent,
artifact, and approval-recorded events are intentionally deferred: current
runners do not expose a safe structured callback for them, and Mana will not
infer them from model transcripts.

Deterministic `mana verify` executions use the same envelope with
`verification.started`, `check.started`, `check.passed`, `check.failed`,
`check.blocked`, `check.inconclusive`, `evidence.created`, and
`verification.completed`. These events contain operational metadata and links
only. The canonical verification result under the active workspace remains
delivery evidence and is not duplicated into runtime telemetry.

No event stores prompts, model responses, reasoning, environment variables,
credentials, tokens, source contents, arbitrary tool payloads, or unnecessary
personal data. Attributes accept only compact operational `key=value` facts;
secret-like names and values are redacted defensively.

Use `mana runtime sessions`, `mana runtime events <execution-id>`, and
`mana runtime show <execution-id>` for inspection. `mana runtime prune
--dry-run --retain-days 30` only reports files in this release; deletion is
deliberately deferred. Runtime evidence answers *how Mana operated*; delivery
evidence in the active workspace answers *what was learned or delivered*.
