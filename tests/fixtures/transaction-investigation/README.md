# Transaction investigation fixture

Small synthetic Java/Spring source for the unified investigation command. It has
REQUIRED joining, REQUIRES_NEW, conditional NESTED/savepoint behavior, proxy
self-invocation, two opposite source resource orders, and dynamic SQL. No database
or Spring runtime is included; lock behavior and deadlocks are deliberately not
asserted.

`expected-outcomes.json` was authored from source/model contracts before running
the investigation. Use `context.json` to exercise the unresolved savepoint case,
or `context-savepoints.json` to stipulate savepoint support conditionally; its
manager and proxy inputs remain assumptions, not runtime evidence. The injected
`JdbcTemplate` fields deliberately show the current S01 limit: observations can be
reported, but T01's ordinary JDBC calls remain unresolved call boundaries because
the opt-in resource leaf requires a narrower direct-allocation witness.

```sh
python3 scripts/mana-investigate-transactions.py \
  --project-root tests/fixtures/transaction-investigation \
  --context tests/fixtures/transaction-investigation/context.json \
  --entry 'investigation.OrderService#process()' \
  --output-dir /private/tmp/mana-transaction-investigation
```

Compare the manual workflow with `mana-transaction.py` and
`mana-resource-timeline.py`. The unified command reduces two analysis invocations
to one and adds the report and transaction sequence source. This is a command-count
comparison, not a time or superiority benchmark.
