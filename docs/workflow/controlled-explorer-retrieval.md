# Controlled Explorer Retrieval

`mana_explorer` remains Mana's read-only discovery capability. It now works in
at most three explicit cycles: **dispatch → evaluate → refine → loop or stop**.
The cycle record names the investigated question, available and requested
evidence, request rationale, retrieved provenance, sufficiency decision, and
remaining gaps. It asks for targeted files or symbols, not repository dumps,
and suppresses unchanged evidence.

Use `mana explore "<question>" --json` for a deterministic local preview. Use
`--scope repository`, `--scope service-context`, or `--scope user-context` for
an explicit source; the default `all` keeps the sources distinct. The
runner agent follows the same output contract when it is delegated discovery
work. It returns `sufficient`, `partial`, `insufficient-evidence`, `blocked`,
or `human-input-required`; reaching the limit never manufactures an answer.

The source-impact-map classifications remain authoritative: `probably_modify`
is a likely impact signal, `inspect_before_deciding` is context only, and
`do_not_touch_unless_approved` remains a governance boundary. Explorer agents
cannot spawn child explorers. When the runtime publisher is available, the
controller emits retrieval-cycle, evidence requested/accepted/rejected, gap,
and stop events as best-effort audit data.

This is project-local read-only retrieval. Repository search still excludes
`.mana/**`; Service Context and a healthy generated User Context mirror are
searched only through explicit roots and retain `service-context` or
`user-context` provenance. User Context is inspect-only and cannot become a
modification target. Retrieval does not call network tools, MCP, models, or
external services, and it does not replace specialist review.
