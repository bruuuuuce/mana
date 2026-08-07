# User Context Layer

The optional User Context Layer makes reusable personal engineering guidance
available across Mana-linked projects without granting runners arbitrary access
outside each repository. It is distinct from Mana framework knowledge,
project-owned Service Context in `.mana/global/`, feature/session artifacts, and
repository evidence.

## Authority And Purpose

User Context may contain preferences, conventions, review guidance, patterns,
and personal knowledge notes. It is advisory and may be stale or inapplicable.
For claims about a project, use this order:

```text
repository evidence > project/service context > user context
```

Current human instructions and Mana governance remain authoritative. Content in
User Context cannot grant tools, writes, approvals, or exceptions to project
constraints.

## Configuration

Mana resolves the source in this order:

1. An explicitly present `MANA_USER_CONTEXT_ROOT` environment variable. An
   empty value disables User Context for that invocation.
2. `$XDG_CONFIG_HOME/mana/config.env` when `XDG_CONFIG_HOME` is set.
3. `$HOME/.config/mana/config.env`.
4. Not configured.

The config file supports one non-executable assignment:

```text
MANA_USER_CONTEXT_ROOT="/absolute/path/to/mana-context"
```

Mana parses this value without sourcing or evaluating the file. The path must
be absolute and outside the project repository. It is never copied into
project-tracked configuration. `XDG_CONFIG_HOME` and `HOME` must themselves be
absolute when used for config discovery; Mana never resolves a user config
location relative to the current project.

Example source:

```text
mana-context/
├── index.md
├── preferences.md
├── guidelines/
├── knowledge/
├── patterns/
└── .manaignore
```

The internal directory structure is not prescribed.

## Materialization

`mana context refresh` builds a filtered staging tree and replaces the generated
`.mana/user-context/` mirror only after the complete copy succeeds. A digest
makes unchanged refreshes idempotent. Full replacement removes files deleted
from the source. The external source is never modified, and symlinks are not
followed or copied.

Refreshes are serialized per project. Abandoned staging data is removed and a
single previous complete tree is recovered after an interrupted replacement.
Before a mirror is reported current, reused by an unchanged refresh, or made
available to retrieval, Mana verifies its complete file manifest and read-only
permissions against the saved digest. Locally modified or manually added files
therefore make the mirror stale and are replaced from the external source.

Mirrored files are marked read-only and the directory is generated/ephemeral.
The normal bootstrap adds both `.mana/user-context/` and `.mana/` to the project
`.gitignore` without replacing existing content.

## Progressive Loading

When present, `.mana/user-context/index.md` and `preferences.md` are navigation
entry points. Runners receive only their paths, never the directory contents.
Agents retrieve deeper files only for a concrete question. User Context is not
added to Service Context, evidence indexes, divination, or learning promotion.

Retrieval preserves `repository`, `service-context`, and `user-context`
provenance. The repository scope continues to exclude all `.mana/**`; only the
two explicit context roots are searched separately.

## Filtering And Security

Supported files are regular textual `.md`, `.markdown`, `.txt`, `.rst`, and
`.adoc` files up to 1 MiB. Binary files, symlinks, and special filesystem nodes
are excluded. A refresh also stops before publishing a mirror larger than 2,000
files or 25 MiB. Built-in exclusions include credentials, keys, VCS metadata,
dependency/build output, and common personal credential directories:

```text
.git/  .env  .env.*  *.key  *.pem  *.p12  *.jks
node_modules/  build/  target/  dist/  coverage/
.ssh/  .aws/  .gnupg/  .DS_Store
```

An optional `.manaignore` uses Git ignore syntax for additional exclusions.
Built-in exclusions are applied separately and cannot be negated. The ignore
file itself is not materialized. Filenames containing newlines, tabs, or the
retrieval record delimiter (`|`) are skipped.

User Context Markdown is reference data, not an instruction source. Do not put
credentials, private keys, customer data, or production data in the source even
though filters are present.

## CLI And Diagnostics

```bash
./mana context status          # redacted health and file counts
./mana context status --json
./mana context refresh
./mana context path            # generated project-local path
./mana context path --source   # explicit external source disclosure
./mana doctor
```

An unconfigured refresh succeeds as a no-op and removes any previous generated
mirror. A configured missing, invalid, or unreadable source returns exit code 2,
keeps the last complete mirror for recovery, and marks it unavailable so it is
not retrieved. `status` itself is diagnostic and returns successfully.

To disable the feature, remove the user config assignment or explicitly run
with `MANA_USER_CONTEXT_ROOT=`; then run `mana context refresh` to remove the
generated mirror.
