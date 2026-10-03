# M08-F Semantic Retrieval Decision

## Decision

Closed without admitting embeddings. FTS5 lexical retrieval remains the
production baseline.

## Evidence

The frozen `mana.knowledge.evaluation-corpus/v1` corpus was evaluated after
the M08-C scope, lifecycle, freshness, and byte filters were implemented. The
machine-readable report is `m08-lexical-retrieval-evaluation.json`.

- 30 questions, including bilingual, conflict, stale, trap, and no-answer cases;
- mean recall at k: `1.0`;
- mean precision at k: `0.6211`;
- zero freshness errors, source-scope errors, and irrelevant-trap hits;
- maximum returned payload: `959` bytes;
- median local search latency: `42.578` ms;
- answer quality was not evaluated and no generated answer was produced.

The admission rule requires measured misses attributable to vocabulary,
language, or conceptual mismatch before comparing an embedding candidate.
This corpus produced no recall miss, so an embedding run would add model,
privacy, packaging, and maintenance cost without a qualifying problem to
solve. The experiment is therefore closed rather than marked successful.

## Reopening rule

Reopen M08-F only after a frozen corpus revision contains reviewed hard-query
misses that remain after correcting source data, ground truth, chunking,
filters, and lifecycle selection. Any future comparison must retain the same
top-k, byte budget, provenance, authority filters, and answer-independent
evaluation.
