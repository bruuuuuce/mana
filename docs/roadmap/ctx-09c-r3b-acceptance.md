# CTX-09C-R3B acceptance

Date: 2026-09-15. Scope: workspace/execution binding, complete live-shadow
file-instance re-attestation, exact-outcome and backend-scratch reconciliation,
and deterministic recovery from a completed CTX-06 shadow chain only.

## Implemented evidence

- The canonical packet exposes and validates comparison/legacy/shadow execution
  identities, execution version, host-derived workspace identity and manifest
  binding, profile/target, packet/evidence/mode/budget digests, CTX-04 manifest
  and CTX-05 evidence manifest. Host re-attestation precedes every producer.
- The shadow run materializes the same workspace identity and verifies its
  CTX-04/05 data against the CTX-06 envelope and run record.
- Per-revision HEAD commits bind HEAD and tip-bundle file instances. The chain
  also commits prior bundles, exact outcome, producer receipt/commit pairs,
  candidate bindings, semantic projections, comparison attempt/seal/result and
  comparison ancestry. Same bytes on a new inode are rejected.
- Exact-outcome stage/owner pairs are reconciled by verified FD-relative
  operations. A complete published exact outcome is adopted without replay;
  an incomplete pre-link outcome is aborted without a legacy rerun.
- A completed CTX-06 shadow chain is reprojected after process exit without a
  second provider invocation. Missing receipt/comparison stages are published
  or adopted exactly once under the comparison lock and HEAD CAS.
- Backend scratch is invocation-owned, registered before invocation, removed
  on every handled outcome and reconciled after crash. Foreign or special
  scratch content fails closed as manual recovery.

## Verification evidence

All commands used local fixtures and no real model, network or external side
effect. The zero-token suite and repository validator both completed with exit
0. Native R3A containment remained independently classified by its existing
gate and was not weakened by R3B.

| Gate | Result |
| --- | --- |
| `bash tests/context-runtime-live-shadow.sh` | Exit 0; 14 input, 16 live, 8 R2A, 17 R2B, 12 R2C, 11 R3A, 21 R3B tests |
| `python3 tests/context-runtime-live-shadow.py` | Exit 0; 16 tests |
| `python3 tests/context-runtime-r3b.py` | Exit 0; 21 tests |
| `bash tests/context-runtime-comparison.sh` | Exit 0; 56 tests |
| `bash tests/context-runtime-modes.sh` | Exit 0; 29 tests |
| `bash tests/analysis-trajectory-guard-tg03-state.sh </dev/null` | Exit 0 |
| `bash tests/context-runtime-phase-provider.sh` | Exit 0 |
| `bash tests/context-runtime-workers.sh` | Exit 0 |
| `bash tests/context-runtime-budgets.sh` | Exit 0 |
| `bash tests/run-zero-token-acceptance.sh </dev/null` | Exit 0; complete suite passed |
| `bash scripts/validate-repo.sh` | Exit 0; repository validation passed |
| Python compile, Bash syntax, ShellCheck `-x`, `git diff --check` | Exit 0 |

CTX-09B verdict semantics, CTX-08 `provisional-no-empirical-baseline`, R3A
privacy/admission behavior, and general CTX-06/07 authority are unchanged.
CTX-09G, CTX-10+, PRC-* and MIG-* remain outside scope.

CTX-09C-R3B status: READY FOR INDEPENDENT GATE
