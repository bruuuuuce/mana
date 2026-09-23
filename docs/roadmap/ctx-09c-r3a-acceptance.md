# CTX-09C-R3A acceptance

Date: 2026-09-15. Scope: candidate/artifact binding, shadow pre-commit
privacy, production backend authority, legacy barrier ordering and failure
usage preservation only.

## Implemented evidence

- Existing producer artifacts are reused only when their private binding is
  identical to the newly derived candidate. Legacy binds the exact current
  outcome; shadow binds the current completed CTX-06 chain.
- The exact legacy outcome precedes semantic validation/receipt/HEAD, and the
  committed legacy HEAD precedes every shadow invocation. A permanent event
  assertion verifies the observed sequence.
- The shared privacy validator runs before CTX-06 checkpoint acceptance. The
  real consumer canary leaves an initialized, non-completed HEAD with zero
  transitions and zero semantic producer artifacts/receipts.
- Production CTX-09A exposes no permissive backend flag or environment
  selector. Its offline substitute and native fixture admission live only
  under `tests/`.
- Failure, timeout, SIGINT and SIGTERM retain emitted measured usage; partial,
  missing and incoherent data remain distinct. Deltas require two measured
  sides.

The exact stale gate case is covered: current legacy `blocked`, current shadow
`fail`, stale legacy projection `fail`. The stale artifact is preserved as
forensic data but rejected from the live pair, so the result is never
`equivalent`.

## Verification evidence

Every command used closed stdin and local fixed fixtures. No model/provider
service or external network call was made. The production native hostile
process was also run outside the managed nested sandbox: its real publish,
external-write, legacy-HEAD-read, socket-connect and service-discovery attempts
were denied, its sentinels remained unchanged, and all 11 R3A tests passed.

| Gate | Result |
| --- | --- |
| `python3 tests/context-runtime-r3a.py` | Exit 0; 11 tests |
| `bash tests/context-runtime-live-shadow.sh` | Exit 0; R1/R2/R3A suites |
| `python3 tests/context-runtime-live-shadow.py` | Exit 0; 16 tests |
| `bash tests/context-runtime-comparison.sh` | Exit 0; 56 tests |
| `bash tests/context-runtime-modes.sh` | Exit 0; 29 tests |
| `bash tests/context-runtime-phase-provider.sh` | Exit 0 |
| `bash tests/context-runtime-budgets.sh` | Exit 0 |
| `bash tests/run-zero-token-acceptance.sh </dev/null` | Exit 0; complete suite passed |
| `bash scripts/validate-repo.sh` | Exit 0; repository validation passed |
| Python compile, 15 R3A/runtime files | Exit 0 |
| Bash syntax, five affected/required shell files | Exit 0 |
| ShellCheck `-x`, five affected/required shell files | Exit 0 |
| `git diff --check` | Exit 0 |

Workspace binding, HEAD/bundle re-attestation and crash recovery R3B remain
unimplemented. CTX-09B, CTX-08 and the general CTX-06/07 runtimes are unchanged
by R3A.

CTX-09C-R3A status: READY
