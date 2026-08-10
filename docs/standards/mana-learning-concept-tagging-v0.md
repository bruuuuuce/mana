# Mana Learning concept tagging and teaching v0

Phase 6 connects the closed canonical Concept Registry to existing Journey
nodes without giving a classifier authority over IDs or graph topology.

```bash
./mana concepts prepare-node --journey jrn_… --node jn_… --language java > request.json
./mana concepts validate-classification --request request.json --result result.json
./mana concepts apply-classification --journey jrn_… --request request.json --result result.json
./mana concepts labels --journey jrn_… --node jn_… --json
./mana concepts teach --concept-id cpt_001 --journey jrn_… --node jn_… --json
```

`prepare-node` materializes the selected Journey and constructs classifier
context from at most eight existing source anchors and 8,000 source bytes. It
adds source-range evidence only for those anchors. The request contains the
bounded candidate inventory and the exact evidence IDs that a result may cite.
Known classifications can select only a candidate `cpt_*` ID; unresolved
results remain project-local candidates.

`apply-classification` validates the closed-ID/evidence boundary before
appending `ConceptOccurrence` records. The occurrence retains relevance,
evidence and the classifier request ID, preventing a request from being applied
twice. No nodes, edges or source regions are discovered.

`labels` is the CLI projection that a Flutter client can later render as concept
badges. `teach` loads the canonical KB document only when requested; optional
project examples are bounded to anchors of the selected node and never trigger
a repository-wide occurrence scan.
