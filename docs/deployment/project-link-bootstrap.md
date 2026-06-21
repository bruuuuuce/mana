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
.mana/jira-mcp.env
.mana/
```

The framework remains in one shared filesystem location. Project-specific
artifacts remain in the target project under `.mana/`.

## Local Wrapper

After bootstrap, use:

```bash
./mana profile mana-help
./mana profile story-start
./mana profile jessica-fletcher
./mana workspace status
./mana workspace init --feature PROJ-1234
./mana jira-mcp --env-file .mana/jira-mcp.env --dry-run
```

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
- Real Jira credentials should stay in `.mana/jira-mcp.env` or another ignored
  env file.
- Re-run with `--force` to refresh generated wrapper files and managed symlinks.
