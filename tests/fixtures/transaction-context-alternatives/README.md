# F02 context-alternative oracles

`r2-original` reproduces the exact Java source embedded in the immutable R2
receipt: only `required()` is final, and advice application is UNKNOWN there.
`variants` makes the REQUIRES_NEW and NESTED callees final and adds bounded
continuation/nonempty/async/programmatic-hazard negatives. `ambiguous` declares
two managers while explicitly qualifying the caller's P1 with tx.

All targets are parse-only. No Spring context or weaver is executed.

The literal expectations in `oracles.json` were specified from the two alternatives:
REQUIRED joins P1 or inherits P1; without an initial transaction the physical
activity differs; REQUIRES_NEW uses a fresh identity or P1 (both ACTIVE if suspend
is assumed supported); NESTED uses P1 with or without a savepoint. Unproven/false
capabilities and ambiguous managers leave the APPLIED boundary unresolved.
The after-state is conditional on normal synchronous unwind of the empty body;
it does not prove a return, commit or rollback. Branch-only L/P/SP/S effects are
not unconditional entities/events. A logical scope or savepoint marked IF_APPLIED
exists only in that alternative, and its presence remains CONDITIONAL.

Run `python3 tests/transaction-context-alternatives.py -v`. PlantUML checks use
only an existing local jar. Missing rendering is NOT RUN, never a syntax PASS.
