# Mana Learning diagram enrichment v0

`mana diagram generate` derives exactly one PlantUML asset from an explicitly
selected existing Journey region. It supports `sequence` and `component`.
It requires at least two unique selected nodes and an internal Journey edge, so
Mana does not emit decorative or automatic diagram sets.

```bash
./mana diagram generate --journey jrn_… --kind sequence \
  --node jn_… --node jn_… --title "Authorization path"
```

The generated `.puml` is stored under the Journey `assets/` directory and is
derived, non-authoritative output; its loss never invalidates the Journey. An immutable Diagram record only supplies
the asset path, kind and selected node IDs needed to discover and correlate
the output. Each PlantUML element includes the Journey node ID and a
`mana-node` comment; a renderer can therefore map an element back to the
node's source anchors. Diagram generation never changes nodes, edges or source
code.
