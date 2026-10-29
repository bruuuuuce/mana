# Resource timeline examples — S01

These are generated artifacts, not test oracles. Each JSON embeds the complete T01
model and same-snapshot AST facts; paths refer to `tests/fixtures/resource-timeline`.
The source fixture's literal oracles and the tests define the expected behavior
independently. Regenerate with the CLI documented in the model standard, using a
fresh external output directory; copy reviewed artifacts here only afterward.

| Example | Enclosing method | Positioned operation | Physical context |
|---|---|---|---|
| [requires_new](requires_new/resource-timeline.json) | `fixture.Entry#independent()` | WRITE, lexical `ledger` | P2, contextual manager `tx` |
| [nested](nested/resource-timeline.json) | `fixture.Entry#nested()` | EXPLICIT_LOCK_REQUEST, lexical `accounts` | P1 with savepoint SP1 |
| [outside](outside/resource-timeline.json) | `fixture.Entry#outside()` | READ, lexical `accounts` | NO_TRANSACTION |

The first example's essential conditional order is:

```text
PHYSICAL_BEGIN P1
  SUSPEND P1                 P1 stays physically live
  PHYSICAL_BEGIN P2
    RESOURCE_OPERATION O1    WRITE ledger, context P2
    UNRESOLVED_CALL          continuation remains UNKNOWN
  PHYSICAL_END_OUTCOME_UNKNOWN P2
  RESUME_CONDITIONAL P1
PHYSICAL_END_OUTCOME_UNKNOWN P1
```

The actual JSON also preserves frame and logical-scope events. Resource syntax
does not establish datasource identity, enlistment, acquired lock, lock granularity,
transaction outcome or deadlock. No example changes a target or executes SQL.
