# Mana Casting

Mana's delivery lifecycle is:

`attunement → divination → casting → evidence → judgment`

Only casting starts a runner. Attunement and judgment remain human-led stages;
Mana does not add placeholder commands for them.

## Boundary and execution path

`mana divination "<intent>"` is a local, read-only recommendation. Its next
command is advisory. `mana cast <profile>` independently reloads the requested
profile, validates its declared skills, semantic agents, and core Service
Context, then initializes the existing Mana workspace and delegates execution
to `scripts/run-profile.sh`. The latter remains the only profile executor and
the only code that starts Codex, Claude Code, or OpenCode.

```bash
mana divination "Add a Kafka contract field and Liquibase migration"
mana cast architecture-review --dry-run
mana cast mana-help

mana divination "Review a migration" --json > divination.json
mana cast --from divination.json --dry-run
```

`--from` accepts only a recommended, read-only divination JSON object with its
profile fingerprint. Casting compares the saved fingerprint to current profile
metadata and blocks stale results. A divination file is never authorization;
the explicit `mana cast` invocation is still required.

## Dry runs

`mana cast <profile> --dry-run` makes no workspace, runner, hook, tool, build,
test, MCP, or external command invocation. It reports the semantic agents,
profile-owned skills, runtime capability classes, skill tiers, declared tool
allowlists, human gates, expected agent artifacts, blocking conditions,
workspace destinations, and possible external systems. Workspace paths are
shown using the existing `mana-workspace.sh` feature-or-session convention and
are initialized only by a real cast.

## Safety rules

- Casting never substitutes a different profile.
- Core Service Context files are required before a cast; the error names each
  missing `.mana/global` file.
- `human_approval_requirement: true` remains a gate for the governed decision.
  Starting a cast is not evidence of approval. Runtime agents must stop at
  concrete approval or policy blockers and must not mark approval complete
  without explicit input.
- Skill selection continues to come from the profile; cast does not invent a
  skill list. The runner receives the same model-tier and tool constraints it
  already uses.
- Profiles whose native runner has no CLI adapter (currently Junie-only
  profiles) are reported as blocked rather than rerouted to another runner.
- Mana never commits as part of casting.

`--json` writes one stable result object to stdout. During a real execution,
the existing runner transcript is sent to stderr so automation does not receive
mixed output.
