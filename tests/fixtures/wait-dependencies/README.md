# Synthetic wait dependency fixtures

These Java sources are parse-only scenario inputs. They are never run and do not
assert that Spring starts, JDBC joins a transaction or a database acquires a lock.
The direct final JdbcTemplate allocation satisfies the existing bounded rule-2
source screen; its runtime behavior remains hypothetical.

`oracles.json` contains manual A–J expectations from the unchanged D00 CSV.
`scenarios.py` constructs their explicit sidecar hypotheses and resolves original
observation/sequence references; it does not call S02 or derive expectations.
The test runner creates an external temporary ASPECTJ/final variant solely for
F02 ACTIVE/null identity and a null-suspend scenario for C03. It preserves this
fixture and all canonical T01/S01 inputs. J01–J04 are deferred runtime cases;
J05 rejects invented static OBSERVED/runtimeIdentity fields.

Run `python3 tests/wait-dependencies.py -v` from Mana. Complete inspectable
A/B/C artifacts are under `docs/examples/transaction-01-t02-s02/`.
