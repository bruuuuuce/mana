# T02-S01 independent source/path fixture

`oracles.json` is hand-authored from Resources.java and the T01 contract, not
generated from engine output. It specifies literal P/manager/type/resource and
scope counts. `tests/resource-timeline.py` separately specifies the full ordered
REQUIRES_NEW event list and adversarial lifetime/assignment expectations.

The fixture stipulates conditional proxy entry and suspend/savepoint capabilities.
These are not runtime facts. No target build or database exists for this fixture.
The manager declaration intentionally proves no datasource binding.

Required checks cover REQUIRED/P1, REQUIRES_NEW/P2, NESTED/savepoint/P1,
nontransactional syntax, UNKNOWN physical context, ambiguous datasource/manager,
rejection after physical end, and preservation of suspended P1's lifetime.
Manager ambiguity is a separate temporary copy with a second source @Bean; the
original fixture is hash-checked and left untouched. UNKNOWN initial context,
async and unknown interception do not establish a traversed JDBC body.

Dynamic SQL, unsupported APIs/SQL, comments, unresolved children and JDBC suffixes
have explicit controls. A suffix JDBC call may have source syntax in observations,
but UNPLACED syntax has no chronological entry, physical ID or wait-graph meaning.
The tests also verify T01 model equality, source spans/hashes, JSON round-trip,
external publication and overwrite rejection.
