# Project Link Bootstrap

Use `scripts/bootstrap-project.sh` to link this framework into an application
repository without copying the whole framework.

Run from the target project root:

```bash
/path/to/mana/scripts/bootstrap-project.sh
```

Or initialize a feature workspace immediately:

```bash
/path/to/mana/scripts/bootstrap-project.sh --feature PROJ-1234
```

The bootstrap creates:

```text
mana
.mana/env
.mana/README.md
.mana/links/
.codex/agents/mana-*.toml
.opencode/agents/mana_*.md
.mana/jira-mcp.env
.mana/
```

The framework remains in one shared filesystem location. Project-specific
artifacts remain in the target project under `.mana/`.
Mana-managed Codex custom agents are installed under `.codex/agents/` so
`./mana profile story-start --codex` can discover `mana_explorer`,
`mana_full_specialist`, and `mana_worker` while running with the application
repository as `--cd`.
Mana-managed OpenCode agents are installed under `.opencode/agents/` so
`./mana profile story-start --opencode` can discover `mana_orchestrator`,
`mana_explorer`, `mana_full_specialist`, and `mana_worker` from the target
project.

## Local Wrapper

After bootstrap, use:

```bash
./mana profile mana-help
./mana profile story-start
./mana profile jessica-fletcher
./mana profile jessica-fletcher --jira-key PROJ-1234 --codex
./mana profile jessica-fletcher --jira-key PROJ-1234 --opencode
./mana workspace status
./mana workspace init --feature PROJ-1234
./mana jira-mcp --get-issue PROJ-1234
./mana jira-mcp --fetch-epic-story-pack PROJ-1234
./mana jira-mcp --env-file .mana/jira-mcp.env --check-access --issue PROJ-1234
./mana jira-mcp --env-file .mana/jira-mcp.env --dry-run
./mana sonar --init-config
./mana sonar --check
./mana dependency-evidence --collect
./mana evidence-index
```

For Jira Server/Data Center, you can skip the env file and launch the profile
from a shell with:

```bash
export JIRA_URL=https://jira.your-company.com
export JIRA_PERSONAL_TOKEN=...
./mana profile jessica-fletcher --codex
```

Mana discovers generic Jira issue keys from the current branch name using a
configurable pattern such as `PROJ-1234`. Pass `--jira-key <KEY>` when the
branch name does not contain the issue key.

## Sonar Scanner

Sonar is optional local evidence for branch and PR review. Keep only host and
token in the shell:

```bash
export SONAR_HOST_URL=http://localhost:9000
export SONAR_TOKEN=...
```

Project scanner properties live in:

```text
.mana/global/sonar-project.properties
```

Initialize and validate them with:

```bash
./mana sonar --init-config
./mana sonar --check
```

## Evidence Index And Dependency Evidence

When dependency manifests, lockfiles, or local dependency scanner reports are
part of a branch or PR, collect a local inventory:

```bash
./mana dependency-evidence --collect
```

After collecting Jira, Sonar, dependency, test, validation, or PR artifacts,
refresh the active workspace index:

```bash
./mana evidence-index
```

The index is written under `.mana/<workspace>/evidence/index.md` and lets review
and validation agents read a compact evidence map before loading detailed
artifacts.

## Git Ignore

By default the bootstrap appends:

```text
.mana/jira-mcp.env
.mana/
```

Use `--no-gitignore` when a project wants to version selected `.mana`
artifacts intentionally.

## Notes

- `.mana/links/` contains symlinks to framework folders for discoverability.
- `.codex/agents/mana-*.toml` are Mana-managed. Bootstrap creates
  `.codex/agents` when needed, preserves unrelated custom agents, warns and
  skips same-name non-managed collisions, and with `--force` replaces only
  Mana-managed files or symlinks.
- `.opencode/agents/mana_*.md` are Mana-managed. Bootstrap creates
  `.opencode/agents` when needed, preserves unrelated OpenCode agents, warns and
  skips same-name non-managed collisions, and with `--force` replaces only
  Mana-managed files or symlinks.
- Existing `.codex/config.toml` is never replaced. If no config exists,
  bootstrap writes a minimal Mana-managed config with Codex agent limits.
  `scripts/run-profile.sh` still enforces `agents.max_threads=3`,
  `agents.max_depth=1`, and `agents.interrupt_message=false` through Codex CLI
  runtime overrides.
- Use `MANA_CODEX_SUBAGENTS=false ./mana profile story-start --codex` or
  `./mana profile story-start --codex --no-codex-subagents` to use the legacy
  manual escalation fallback.
- Use `MANA_OPENCODE_SUBAGENTS=false ./mana profile story-start --opencode` or
  `./mana profile story-start --opencode --no-opencode-subagents` to disable
  OpenCode subagent delegation.
- Real Jira credentials should stay in `.mana/jira-mcp.env`, another ignored
  env file, or shell environment variables. They must not be committed.
- Re-run with `--force` to refresh generated wrapper files and managed symlinks.
