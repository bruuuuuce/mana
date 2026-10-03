# M08 operations, privacy, recovery, and rollback

M08 adds optional read, cache, Knowledge, action, and review-scheduler
capabilities. Existing Inspect v1 operations and ordinary Mana workflows remain
available when every M08 component is disabled or its derived state is absent.

## Compatibility and rollout

- `inspect project` advertises `semantic-snapshot` only with the exact
  `mana.inspect.semantic-snapshot/v1` schema. Consumers that do not recognize it
  continue to use the individual v1 operations.
- `mana catalog`, `mana knowledge`, `mana action`, and `mana review-inbox` are
  separate wrapper commands. None runs during bootstrap or an unrelated Mana
  profile.
- The derived catalog and FTS5 Knowledge index are host-cache projections. A
  missing, incompatible, stale, or corrupt projection is reported explicitly
  and can be rebuilt without rewriting canonical project artifacts.
- Lexical FTS5 remains the production retrieval engine. The M08-F semantic
  experiment is closed because the fixed corpus exposed no qualifying lexical
  recall miss.

## Recovery and rollback

Inspect is read-only. If the aggregate operation is unavailable, remove or
ignore the advertised capability and use the unchanged individual v1 reads.
Rebuild derived state with:

```sh
./mana catalog rebuild --json
./mana knowledge build --json
```

Both rebuilds publish under a single host lock. A failed build leaves the last
committed database intact or reports that no current projection exists.

Knowledge edits and Learning dispositions require the exact current revision.
A conflict creates or returns a governed proposal instead of overwriting newer
content. Action receipts are append-only host-cache evidence; they contain
bounded references and revisions, not credentials.

User Knowledge is editable only when Mana reports a current mirror and an
explicit external-source disclosure. Familiar shows that root before sending
the source-relative target, disclosure, and expected revision back to Mana.
Mana re-resolves the configured source, writes it atomically, and refreshes the
read-only mirror; a refresh failure is reported as `partial_refresh`. Candidate
acceptance and User Learning promotion remain two separate confirmed actions.

The review scheduler is disabled until an explicit user configuration sets
`enabled:true`. One cycle can be invoked by an OS scheduler:

```sh
./mana review-inbox cycle --json
```

or the portable foreground host can run independently of Familiar:

```sh
./mana review-inbox service --json
```

INT or TERM stops the foreground host. Setting `enabled:false` stops future
discovery and causes the service to exit without deleting existing review
evidence. Expired analysis leases recover as `interrupted`; network failure
does not advance durable inbox state. A publication result of `unknown` is
never retried or reported as success automatically.

## Privacy and authority

Project source and `.mana` artifacts remain authoritative. Derived databases
live outside the project under the platform user cache/state root and store
only allowlisted, bounded documents and metadata. Symlinks, traversal,
replacement races, non-regular files, oversized sources, malformed records,
and unsupported schemas fail closed or become explicit diagnostics.

Knowledge responses expose source scope, lifecycle, reference, document and
passage revisions, rank reasons, freshness, bounds, and gaps. They do not
generate answers. Scheduler state excludes credentials, full diffs, provider
prompts/responses, and unrestricted review comments. Familiar supplies no
alternate filesystem parser or credential store.

## Release evidence boundary

The deterministic fixture generator, contract clean-room suites, lexical
evaluation, inspect benchmark, and Familiar performance harness are release
inputs. A debug or headless timing is diagnostic only. macOS and Windows native
startup, frame, lifecycle, notification, and service-registration evidence are
separate platform gates; one platform never proves the other. Failure of a GUI
automation session is recorded as environment evidence unless the application
itself crashes or violates a checked contract.


### Project and semantic snapshot transport

The Inspect shell entry point delegates `project` and `semantic-snapshot` to
`mana-inspect-snapshot.py`. One Python process builds one immutable catalog and
calls the existing semantic projections without serializing the inventory
between child processes. It creates no bytecode cache. Snapshot identity
retains the compact, sorted-key jq encoding used by the original producer;
mtime stays outside that identity. Individual v1 operations remain available.

Validate with `tests/mana-inspect.sh`, `tests/mana-inspect-contract.sh`,
`python3 tests/mana-inspect-snapshot.py`, and `tests/m08-fixture-benchmark.sh`.
The snapshot regression covers individual-projection equivalence, one catalog
build, same-byte atomic replacement, and unchanged source bytes.
