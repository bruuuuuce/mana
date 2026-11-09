# MANA-TX-JDBC-01 example

This deterministic source fixture demonstrates injected JDBC operations across a
`REQUIRED` outer transaction and a `REQUIRES_NEW` inner transaction. The explicit
`JDBC_LITERAL_V1` context enables the existing T01 resource-leaf continuation
catalog for the non-callback `update(String)` calls.

Forward path order is `resource_b` on P2, then `resource_a` on resumed P1. The
reverse path orders `resource_a` on P1, then `resource_b` on P2. P identifiers
are symbolic scenario identities. The evidence does not establish runtime
execution, datasource enlistment, locks, waits, or a deadlock.

Reproduce from the repository root:

```sh
python3 scripts/mana-investigate-transactions.py \
  --project-root tests/fixtures/resource-timeline \
  --context docs/examples/mana-tx-jdbc-01/context.json \
  --entry 'fixture.TransactionScenarioA#forward()' \
  --output-dir /private/tmp/mana-tx-jdbc-forward

python3 scripts/mana-investigate-transactions.py \
  --project-root tests/fixtures/resource-timeline \
  --context docs/examples/mana-tx-jdbc-01/context.json \
  --entry 'fixture.TransactionScenarioA#reverse()' \
  --output-dir /private/tmp/mana-tx-jdbc-reverse
```

The checked-in JSON and `.puml` files are the generated resource timelines and
PlantUML sequence sources. SVG output was unavailable in this environment; the
PlantUML renderer still produced the reusable sequence source.
