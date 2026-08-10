# Mana Learning Git archaeology v0

`mana history enrich` inspects a bounded historical region: exactly one
existing Journey node and one of its source anchors. It runs `git log --follow`
for that anchor path with a caller-controlled commit budget (default 12), so it
does not scan repository-wide history.

For each scoped commit it appends a historical Anchor, a `git_commit` Evidence
record and a TimelineEvent. Rename entries update the path used for older
anchors. When the original anchor carries a symbol, its historical line is
located in that revision where possible; otherwise the original bounded range
is retained as a transparent fallback.

```bash
./mana history enrich --journey jrn_… --node jn_… --anchor anc_… --max-commits 10
./mana history enrich --journey jrn_… --node jn_… --anchor anc_… \
  --hypothesis hyp_… --effect strengthens --reason "The introduction commit documents the compatibility constraint."
```

Git is optional enrichment. If the project is not a Git worktree, the path has
no history, or Git inspection fails, Mana appends `git_enrichment` with status
`failed` and a reason; existing Journey graph records remain valid and usable.
The optional hypothesis effect is an explicit assessment, not an automatic
claim about author intent.
