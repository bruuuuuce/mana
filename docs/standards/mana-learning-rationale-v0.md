# Mana Learning rationale v0

`mana rationale request` bounds rationale work to source evidence already
anchored on one Journey node. `propose` emits at least two competing plausible
interpretations; each says it does not establish historical intent. `apply`
accepts only bounded evidence IDs, plausible/speculative/unknown confidence,
closed categories and non-empty verification suggestions, then appends
independent Hypothesis records.

```bash
./mana rationale request --journey jrn_… --node jn_… --out request.json
./mana rationale propose --request request.json > result.json
./mana rationale apply --journey jrn_… --request request.json --result result.json
```

Historical commits can now be added separately through the bounded Phase 9
contract in `mana-learning-history-v0.md`; they may be assessed against a
hypothesis without rewriting it.
