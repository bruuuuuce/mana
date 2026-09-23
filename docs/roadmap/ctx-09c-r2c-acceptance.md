# CTX-09C-R2C acceptance

Date: 2026-09-14. Scope: R2C only, assuming R2A/R2B completed.

CTX-09C-R2C status: READY

## Implemented contract

The [live host](../../scripts/context-runtime-live-shadow.py) re-attests the
complete reachable HEAD/bundle chain before reuse and CAS, including producer
receipts/commits, runtime and execution/profile/target identity, artifact file
instances, private side receipts, exact legacy outcome and comparison records.
It rejects missing/foreign/tampered references, identical-byte replacements
of committed artifact/receipt/outcome files, incomplete predecessors and
incorrect stages. Invalid authority raises explicit manual recovery before
delivery or mutation of that HEAD.

An immutable comparison intent reserves one invocation. The complete attempt
and its separate publication seal bind the input receipt digest, ordered
legacy/v2 pair, producer receipts, report/result digests and attempt inode.
The comparison stage of the single CAS journal commits both attempt and seal.
A valid sealed pre-HEAD attempt is adopted without another comparator call.
An incomplete or invalid orphan attempt is excluded from authority and becomes
terminal indeterminate without re-execution.

The ephemeral packet has a fixed state-referenced private locator, committed
before materialization. It is captured with a file-instance commitment for
consumption and mode 0600 within 0700. Under the comparison lock, reconciliation
and handled exits remove the packet, its publication staging bytes, empty
input directory and abandoned HEAD CAS temporaries. Terminal reuse materializes
no packet. R2B's sensitive exact outcome remains the caller delivery authority.

See the [R2C contract](../standards/context-runtime-contract.md#ctx-09c-r2c-full-re-attestation-exactly-once-comparison-and-crash-reconciliation).

## Verification evidence

All test commands ran sequentially with closed stdin. Model/API calls were
replaced only by installed local fixtures. Required native suites ran outside
the managed sandbox after its first live-shadow attempt reported
`sandbox_apply: Operation not permitted`; production containment was not
weakened. The final canonical run had no live-shadow native skips.

| Gate | Verified result |
| --- | --- |
| `tests/context-runtime-comparison.sh </dev/null` | Exit 0; 56 tests |
| `tests/context-runtime-modes.sh </dev/null` | Exit 0; 29 tests; native outside-write/network canaries passed |
| Final live-shadow block in canonical suite | PASS; shared input 14, live shadow 16, R2A 8, R2B 17, R2C 12 tests; no skips |
| `tests/run-zero-token-acceptance.sh </dev/null` | Exit 0; `Complete zero-token acceptance suite passed` |
| `scripts/validate-repo.sh </dev/null` | Exit 0; `Repository validation passed` |
| ShellCheck `-x` on shadow provider/phase provider, live-shadow wrapper and repository validator | Exit 0 |
| Bash syntax checks on wrapper and validator | Exit 0 |
| Final Python AST checks on live host, R2B/R2C tests and R2C producer fixture | Exit 0; four files |
| `git diff --check` | Exit 0 |

The final R2C block completed 12 tests in 39.347 seconds in the canonical run.
The [R2C tests](../../tests/context-runtime-r2c.py) use real forked hosts and
`os._exit(99)`, real local subprocess producers, the real offline comparator,
real filesystem publications, flock and HEAD CAS. Their import-only producer
admission fixture tests the transaction protocol; native containment is a
separate R2A/live-shadow/modes gate and passed at that layer.

## Real crash and concurrency matrix

The abrupt-death matrix passed after packet publication, input materialization,
legacy artifact/complete receipt before HEAD, legacy HEAD, shadow
artifact/complete receipt before HEAD, shadow HEAD, comparison attempt/seal
before HEAD, during comparison HEAD CAS, and comparison HEAD before cleanup.

For every one of these nine boundaries, reconciliation plus repeat reuse
verified exactly one legacy invocation, one shadow invocation and one
comparator invocation; one committed stage of each kind in the fully validated
authoritative chain; identical legacy stdout/stderr/status for callers;
zero residual packet/input directories or HEAD CAS temporaries; private modes
and state references at the crash; and the unchanged tree outside `.mana`.
No new global `mana-ctx09c-input-*` directory remained.

Two real concurrent harnesses passed both without a prior crash and after
legacy HEAD, shadow artifact/pre-HEAD, comparison artifact/pre-HEAD and
comparison HEAD CAS crashes. Both callers returned the same exact legacy
outcome and result; the invocation counts remained 1/1/1 and the chain
contained one authoritative legacy, shadow and comparison commit.

Separate negative tests passed for producer/comparator deaths without a
complete receipt or attempt, terminal legacy exit 23, missing/tampered/new-inode
committed files, incomplete/foreign chains and HEAD identity, invalid orphan
attempts/seals, a rehashed bundle with an inconsistent shadow stage, packet
rebinding before consumption, failed raw packet staging and packet cleanup
even when the crashed HEAD is invalid. Ambiguous effects never replayed.

The relevant R2B tests now exercise the recoverable session cleanup and require
an invalid completed chain to be preserved while explicit recovery errors are
raised; R2C cannot publish a claimed verified successor to corrupted authority.

No R2D or CTX-09G+ implementation is included.
