# MR00 independent transition oracles

`cases.json` contains 44 complete supplied IR fixtures, O01–O44, with the literal
ACCEPT/REJECT decisions and transition references from the frozen MR00 CSV.
Eight additional positive payloads exercise T08/T09/T10/T11/T12/T20/T21/T23;
the last inspects the ordinary caller of the nonempty F02 example.

The payloads were hand-authored before the MR01 validator correction, without
calling the production engine, alternative composer, validator or renderer to
generate expectations. Their source strings, source locations, hashes and
context receipts explicitly describe **synthetic supplied IR premises**, not
JDK parser output, actual Java interception or runtime transactions. No synthetic
payload is passed off as evidence that the source resolver produced it.

Negative fixtures retain the full envelope and coherent effective-context
projections. Each specifies its semantic contradiction and accepted diagnostic
pattern. O13 includes both modern and legacy versions. Exact historical R4
payloads are tested separately, unchanged, from its preserved receipt.

Run `python3 tests/transaction-transition-contract.py -v`. Every O identifier is
an individual executable test. The suite also checks literal CSV alignment,
provenance, transition coverage and the approved D2/D3/D4 consumer constraints.
No production function is an oracle for the expected outcome.
