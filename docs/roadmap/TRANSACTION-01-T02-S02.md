# T02-S02 proposal — Conditional wait dependency analysis

Status: proposal only. S01 does not authorize implementation or execution of S02.
No definitive deadlock diagnosis is proposed from S01's source syntax alone.

The next increment should consume Resource Timeline Model v1 and T01 without
allocating replacement physical identities or changing historical T01 evidence.
Before implementation, establish an explicit concurrency scenario, resource/API
scope, datasource identity and alias rules, lock-request compatibility and the
quality of evidence needed for acquisition, retention and waits.

Proposed input/output distinctions:

| Evidence | Permitted result |
|---|---|
| Same lexical SQL identifier only | Possible alias; runtime resource identity UNKNOWN |
| Positioned operation within live P, datasource/enlistment unknown | Conditional resource-use candidate, no proven holder/waiter edge |
| UNPLACED observation or unresolved continuation | No causal wait edge; report UNKNOWN with evidence |
| Explicit concurrent paths, resource identity, request/holder evidence and compatible lifetime spans | Evidence-qualified conditional wait dependency, subject to the agreed contract |
| Cycle among conditional edges | Candidate cycle under stated premises; no definitive runtime deadlock |

Proposed deliverables: versioned wait-dependency contract, bounded graph
construction, renderer input and independent positive/negative oracles. Include
same-resource/different-datasource separation, SQL alias ambiguity, unknown
enlistment, suspended outer P retention, independent P2, ended transactions,
savepoints, async boundaries and conflicting/absent concurrency assumptions.

Acceptance should require provenance for each edge and an explicit account of
UNKNOWN facts. READ/WRITE must not silently become database lock modes; FOR UPDATE
must not become acquired ownership. The absence of a proven cycle must not mean
deadlock-free. Runtime/database capture requires a separate explicit mandate;
no query to target databases is authorized by this proposal.
