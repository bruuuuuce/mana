# Exact source repair, first increment

`mana repair --exact-request <absolute.json> --host-grant <private.json> --provider none --json`
uses a separate deterministic effect contract, before loading provider libraries.
The supported repository entry is `scripts/mana-repair.sh`; bootstrapped `mana`
forwards the same arguments and its project root must equal the bound destination.
`mana verify` / `scripts/mana-verify.sh` accepts the same options for an operation
of `verify`; that operation runs only the fixed compilation/test pair and never
calls the application function. Existing generative repair and verification
skills retain their existing admission, effects and limitations.

This increment admits **explicit public disposable fixture test authority only**.
It does not accept human identities, remote inference consent or ordinary live
project execution grants. No provider is selected, initialized or invoked. There
is no generation, correction, implicit continuation, shell command or retry.

## Request and host authority

The strict `mana.exact-request/v1` JSON object contains exactly:

| Field | Meaning |
|---|---|
| `id`, `operation` | Run/request identity; `repair-verify` or `verify`, matching the public entry |
| `provider` | Must be `none`, also explicitly required on the CLI |
| `proposal` | Entire original `mom.operator.offline-proposal/v1` package, unchanged, including fingerprint, source request/mission, handoff, base snapshot and `edit.replacement` |
| `destination`, `destination_identity` | Canonical existing private fixture directory, device/inode; under `/private/tmp`, owned by current uid, mode 0700 |
| `outputs` | Separate, canonical, empty, private existing directory under `/private/tmp` |
| `result_sha256` | SHA-256 of UTF-8 `edit.replacement`; this is the only replacement representation |
| `verification` | Exactly `catalog`, `test_path`, `main_class`; catalog must be `java-jdk-pair/v1`, the test path must equal the frozen handoff test |
| `baseline` | Exactly `test_exit`, `stdout_sha256`; for repair, the baseline must match before application |
| `runtime` | Exact output of `scripts/lib/exact_repair.py:runtime()`: current MANA HEAD, pertinent implementation file hashes and aggregate identity, canonical JDK home and executable fingerprints |
| `budget` | Exactly `attempts=1`, `verification_commands=4` (repair) or 2 (verify), positive `timeout_seconds<=30`, `total_seconds<=180` and at least six command timeouts, `output_bytes` 1024..65536 per stream/command, `file_bytes` 1024..1048576 per child-created file |
| `authorization_reference` | Exact host grant ID |
| `protected_files` | 1..32 explicitly selected existing external regular files to probe for denied writes; fixture protected files, MANA implementation and receipt control are added automatically |

Canonical JSON is UTF-8 `json.dumps(sort_keys=True, separators=(',', ':'),
allow_nan=False)`, with default ASCII escaping. The package fingerprint hashes
all package fields except its top-level `fingerprint`; snapshot hashes include
both text and hash records. JSON inputs reject duplicate keys. Inputs are bounded
at 1 MiB, each snapshot/replacement file at 256 KiB. The destination must contain
exactly the snapshot files; source is one existing `src/main/java/*.java` path,
excluding test/configuration directory names. No target creation, deletion or
rename is supported. All paths reject traversal, symlinks and noncanonical aliases;
regular data files must have one hard link. No path embedded in the historical
handoff is automatically opened. The caller explicitly supplies the relocated copy
and protected originals. State and outputs never live inside that copy.

The private host grant JSON has exactly `schema=mana.exact-host-grant/v1`, `id`,
`authority=explicit-public-fixture-test`, `approved=true`, `request_sha256`,
`expires_at` (integer Unix seconds, future and within one hour), `uses=1`.
It must be a regular single-link file owned by the invoking uid, mode 0600, in a
private owned directory outside destination/output. Its request hash binds the
whole request, including the full historical package, runtime, destinations,
commands derived by that runtime, budgets and test-only authority reference.
The host issues this file explicitly; there is no CLI test-bypass switch and no
assumed human approval. A proposal fingerprint alone grants no effects.

Before probes, MANA exclusively creates `<grant-file>.used`, flushes/fsyncs its
request reservation, and never refunds it. Single use is enforced for that private
canonical grant file, including concurrent invocations. The host authority store
is trusted: its issuer must retain reservations and must not duplicate/reissue a
grant under another filename. This is not a distributed or tamper-proof issuer
registry. Do not delete reservations to resume failed attempts.

## Fixed verification catalog and effects

The dispatcher constructs, rather than executes supplied command text:

```text
/usr/bin/javac -d <outputs>/classes <destination>/<edit.path> <destination>/<frozen-test>
/usr/bin/java -cp <outputs>/classes <main_class>
```

The cwd is the bound fixture directory. No Maven, Gradle, wrapper, repository hook,
class-path from the environment, free-form flags or shell expansion is accepted.
The environment is replaced with fixed PATH/locale, private HOME/TMPDIR,
no user Python site/bytecode, and the fingerprinted JDK home. The approved source
and build directory are the only writable filesystem locations in the execution
policy (plus `/dev/null`); receipts are written by the host supervisor outside the
child boundary. The source remains write-authorized by this exact effect contract
even for verification-only requests; that operation itself never applies an edit
and final source hashes must remain unchanged. This is not a no-write profile.

The specific macOS Seatbelt policy denies by default, denies network, Mach service
lookup and both fork/spawn; it permits only the Python/JDK executables and required
runtime/source reads. It allows source **data** writes only (no rename/unlink/mode
change), and build writes under `outputs/classes`. Original fixture, test,
configuration, MANA/MOM checkout and host authority remain unwritable. Broad
system runtime reads and file metadata reads are permitted; this contract does
not claim a VM or full host confidentiality boundary.

Each admitted run executes native probes before any verification/application:
write-open denials on protected files, symlink write escapes, network socket
connect, fork and posix_spawn denial, allowed source write-open/build write, plus
a one-second timeout sentinel. Probe failures block without fallback. The existing
`verification-exec.pl` supervisor supplies process-group timeout/termination,
bounded stdout/stderr and exit/signal/duration collection; inherited CPU and
per-file size limits are added. Fork/spawn denial is essential: the supervisor
alone does not promise cleanup of adversarial detached sessions. The contract
requires macOS Seatbelt and the fingerprinted local Python framework/JDK; missing
native support blocks. There is no weaker temporary-directory fallback.

Repair sequence: validate → reserve → native probes → baseline compile/test →
check exact baseline → recheck source base in the sandboxed application → overwrite
with precisely `edit.replacement` → compile/test again → compare full target file
inventory/hashes. The controller checks cumulative elapsed time before phases;
there is one application and four verification commands at most. Limits are per
file/stream as described, not a total filesystem quota or JVM memory limit.

A failed step stops. A started application is reported PARTIAL on failure;
the copy is left inspectable. No atomic import, rollback or automatic recovery is
promised. `result.json` and its SHA-256 sidecar record request/package/runtime,
actual argv/cwd/output/exit/timeout, authority, before/final hashes, application
state and stop reason. Raw logs/status and control receipt are retained privately.
Hashes identify content; they do not authenticate a human or upgrade historical
MOM evidence. A host crash can leave only the durable reservation/partial files;
there is no crash-atomic transaction protocol.

Receipt persistence is distinct from application and verification. If opening,
writing or closing `result.json` or `result.sha256` raises an I/O error, stdout
still returns the observed result with `receipt_error` containing `artifact` and
`error`; stderr reports `RECEIPT_PERSISTENCE_FAILED` and the same application
state. Exit is 2. An existing BLOCKED/PARTIAL status is retained; COMPLETE becomes
PARTIAL if application started, otherwise BLOCKED (including verification-only). Confirmed `applied=true`, actual `steps`, and
before/final hashes are preserved. Missing steps mean NOT RUN; a started but
unconfirmed application remains potentially partial, never proof of no changes.
An existing `stop_reason` is retained; only an absent reason becomes
`RECEIPT_PERSISTENCE_FAILED`. Successful receipts and schema are unchanged; the
optional error field describes only a persistence failure in the CLI response.

A failed persistence attempt is not retried or repaired. Disk artifacts may be
absent, truncated, or contain the earlier execution result without a valid
sidecar (even a close error may leave complete bytes). They are not a successful
receipt pair and may differ from the final stdout response. Preserve the copy,
logs and reservation for inspection; do not infer no effects from missing
receipts, replay the action, refund budgets or promise durability/rollback.

## Tests and scope of qualification

`python3 -I -B tests/exact-repair.py` tests admission and deterministic component
behavior with explicit executor doubles, plus one native supervisor timeout/child
cleanup test. Doubles never qualify Seatbelt, JDK execution, host issuance or human
approval. Native evidence and the single E2E-002 application are recorded separately
in [MANA-EXACT-001](../reports/MANA-EXACT-001.md).

MOM must later adopt a reviewed MANA revision containing this capability and create
an operation-specific request/private host grant path and admission adapter. Its
architecture-review/provider grant and old producer pin are incompatible. This
increment changes no MOM file, pin, historical package or evidence and qualifies
neither MOM integration nor autonomous/human approval.
