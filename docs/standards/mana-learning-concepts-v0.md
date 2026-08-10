# Mana Learning Concept Registry v0

The canonical registry lives in `learning-kb/concepts/cpt_*.yaml`; the compact
derived classifier inventory is `learning-kb/concept-index.tsv`. Concept IDs
are Mana-owned (`cpt_001` etc.) and never come from a model.

Each canonical document follows [the v0 concept schema](mana-learning-concept-v0.schema.json)
and has `mana.learning.concept/v1`, a stable ID, key, category, aliases, a
short hint, and optional language/framework applicability.
Run `scripts/build-concept-index.sh > learning-kb/concept-index.tsv` after a
curated edit. `mana concepts validate` rejects drift and duplicate IDs/keys.

`mana concepts prepare` bounds a supplied snippet to 8,000 bytes and emits a
host-generated candidate list. Its result contract permits only:

- `resolution: known` with a `concept_id` present in that exact candidate list;
- `resolution: unresolved` with a label but no concept ID.

Both forms may include a Journey node, evidence references, and relevance
(`primary`, `supporting`, or `incidental`). `validate-classification` verifies
the closed-ID boundary. `record-unresolved` writes each unresolved result as a
project-local `ucp_<host-generated-id>.yaml` candidate under
`.mana/learning/unresolved-concepts/`; it does not promote it into the shared
KB. Promotion is explicitly deferred.

The seed set is intentionally small: general programming, OO, functional,
concurrency, design and architecture patterns, plus Java, Spring, and Rust.

`scripts/evaluate-concept-index.sh` compares keyword-only, keyword + category,
keyword + category + aliases, and that same form with hints. On the committed
fixture, aliases are the smallest representation meeting the v0 thresholds
(precision and recall at least 0.95; ambiguity at most 0.10); hints add cost
without improving that fixture's result. Its token figure is a transparent
bytes/4 estimate for comparison, not a claimed provider token count.
