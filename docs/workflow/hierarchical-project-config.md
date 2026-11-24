# Hierarchical project configuration

Use `mana.toml` to set defaults for a workspace, a group of projects, or
one project. Configuration is optional. TOML requires Python 3.11 or later
on a host with no-follow and directory descriptor support. Existing installations
without TOML files keep their defaults. For a linked project, refresh an older
launcher with `scripts/bootstrap-project.sh --project-root DIR --force`.
Run the following from a linked project, or call
`python3 scripts/mana-config.py --project-root DIR explain --json` from the framework.

```sh
./mana config explain
./mana config explain --json
```

## Machine settings

Create `$XDG_CONFIG_HOME/mana/locations.toml`, or
`$HOME/.config/mana/locations.toml` when XDG is unset. This file contains
canonical absolute paths without symlinks and grants each registered root
access to named locations.

```toml
version = 1

[vaults]
engineering = "/data/Engineering vault"

[knowledge]
common = "/data/knowledge/common"
payments = "/data/knowledge/payments"
personal = "/data/knowledge/personal"

[roots.work]
path = "/work/repos"
vaults = ["engineering"]
knowledge = ["common", "payments", "personal"]
allow_personal = true
allow_runtime = false
```

Use the smallest appropriate registered root. A more specific registered root
starts its own hierarchy and uses its own alias permissions. Grant
`allow_personal = true` only where projects may read the personal KB. Treat
aliases other than `personal` as shared with projects that can enable them.
Keep shared and personal KB directory trees disjoint.
The older User Context configuration in `config.env` applies independently.

## Folder settings

At `/work/repos/mana.toml`:

```toml
version = 1
[export]
vault = "engineering"
[knowledge.sources]
common = true
personal = false
```

At `/work/repos/payments/mana.toml`:

```toml
version = 1
[knowledge.sources]
payments = true
[profiles.requested-pr-review]
runtime = "legacy"
[profiles.requested-pr-review.skills]
architecture-risk = true
```

At `/work/repos/payments/ledger/mana.toml`:

```toml
version = 1
[project]
id = "ledger"
```

MANA reads only the files on this path. A project can omit its own file
when it needs only inherited settings. Keys are validated in every discovered
file. The nearest declaration wins per key, so `payments = false` in the leaf
disables an inherited source. A skill preference of `false` masks its inherited
request. Required skills and explicit CLI activation still apply.

Runtime values are `legacy`, `v2`, and `shadow`. An explicit
`--context-runtime` takes precedence over the folder preference. A root needs
`allow_runtime = true` for an inherited `v2` or `shadow` selection, and the
selected mode must still pass existing runtime admission and committed
execution checks. Render-only and diagnostic commands ignore inherited
runtime selection. Conditional skill requests are checked by the same profile
compiler as explicit requests.

## Knowledge

Build the existing local index before searching. Rebuild it after a source or
its files change. Searches fail as stale when the cached source set differs.
Configured sources are read-only and results identify the alias in references
such as `mana://knowledge/payments/operating-notes.md`. Shared aliases are
returned in the project scope and the personal alias in the user scope. The
derived index stores the admitted excerpts in the local MANA cache.

```sh
./mana catalog build --json
./mana knowledge build --json
./mana knowledge search --query "transaction boundaries" --scope project --json
```

## Obsidian export

Use a completed [Java/Spring investigation](java-spring-transaction-investigation.md)
from the same project checkout.
Pass its output directory and inspect the preview before applying the same
command with `--apply`. The export includes a portable report and its PlantUML
source diagrams. MANA verifies their manifest digests for new bundles, checks
the source project and rejects machine-specific paths. The portable report
drops local reproduction commands and links to the exported diagrams. Report contents may
include code identifiers or SQL literals and should be reviewed before applying
an export to a shared vault.

```sh
./mana export transaction --from /path/to/investigation
./mana export transaction --from /path/to/investigation --apply
```

The vault must already exist. The destination is
`Mana/<project-id>-<namespace>/Transactions/analysis-<content-hash>/`.
The namespace uses the registered root name and the project's relative path.
A repeated export of identical artifacts reuses the directory. If a bundled
file was edited, deleted or replaced, MANA reports a conflict and preserves the
destination. Each new bundle is published as a complete directory.
