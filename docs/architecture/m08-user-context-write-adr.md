# ADR: M08 external User Context write authorization

## Status

Accepted for M08-D/C05. The generated `.mana/user-context/` tree remains a
read-only mirror. An editable User Knowledge capability exists only while the
mirror is current and Mana can resolve a configured external source.

## Decision

Mana, not Familiar, resolves the configured source with `mana-context path
--source`. A document read may advertise an edit only when the corresponding
external regular file has the same content revision as the indexed mirror.
The edit capability returns a source-relative target and the exact external
root as `source_disclosure`.

Familiar must show that disclosure before confirmation and submit it unchanged
with the exact document revision. `mana action knowledge-edit --scope user`
resolves the configured source again, rejects a mismatched disclosure, checks
containment and revision, publishes atomically, and then refreshes the mirror.
The client never writes either tree directly.

## Failure and recovery

Missing configuration, a stale mirror, a symlink, a changed external file, or
a mismatched disclosure removes write authority or returns an explicit
validation/conflict receipt. A successful external write with a failed mirror
refresh returns `partial_refresh`; the canonical external source is retained
and the UI must not claim that the mirror or index is current. Rebuilding the
Knowledge index is a separate derived-state operation.

User Learning review and promotion remain distinct actions. A promotion is
advertised only with the exact review-file revision and requires a second
explicit user action; accepting a candidate never promotes it automatically.

## Privacy

The absolute external root is disclosed only in the local capability/detail
response that authorizes a write. It is not stored in the derived Knowledge
index, action receipt, benchmark report, or project mirror. Receipts retain
bounded logical targets and revisions.
