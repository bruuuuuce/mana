# ADR: M08 derived catalog storage

## Status

Accepted for M08-B. This decision authorizes only an explicit, derived catalog
projection. It does not authorize hidden writes from `mana inspect`, a daemon,
credentials in the database, or treating cached state as canonical.

## Decision

Mana stores the M08 catalog in the current user's platform cache directory,
outside the inspected project:

- macOS: `$HOME/Library/Caches/mana/catalogs/`;
- Windows: `%LOCALAPPDATA%\\Mana\\Cache\\catalogs\\`;
- XDG: `${XDG_CACHE_HOME:-$HOME/.cache}/mana/catalogs/`;
- tests and controlled hosts: `MANA_CACHE_HOME/catalogs/`.

Each database is named by a SHA-256 project identity. The identity is the
normalized Git origin when present and otherwise the canonical project root.
The database stores the identity digest, never the origin URL or absolute
project path. A project without a stable origin therefore receives a new cache
after relocation; the old entry is left for explicit cache cleanup and is
never guessed or rebound automatically.

SQLite is the initial storage engine. Schema versions are explicit. Builders
publish with one host-owned advisory lock and a SQLite transaction. Readers
open an existing compatible database read-only. `status`, `build`, `verify`,
and `rebuild` are explicit maintenance commands; ordinary read-only Inspect
operations never create, migrate, repair, or delete a database.

## Stored data

The catalog projection may store only bounded derived metadata needed to validate and
reconstruct entries: project identity digest, project-relative path, source
scope, regular-file type, size, file identity metadata, content digest,
semantic revision, classification, schema version, and bounded diagnostics.
It must not store absolute paths, source bodies, credentials, prompts,
responses, unrestricted logs, model output, or provider data. M08-C may add
separate `documents`, `passages`, and FTS tables in the same database for
explicitly admitted textual knowledge sources. Those tables may store bounded
passage text and headings required for local lexical search, but inherit the
same exclusions, source scopes, lifecycle labels, project identity, deletion,
and no-credential rules. They are never a canonical source and can be rebuilt
independently of catalog metadata.

Content digests remain the semantic identity. Size, modification time, change
time, and platform file identity may avoid rehashing only while the same file
instance is unchanged. A replacement, rename, permission change, or ambiguous
metadata transition requires content revalidation before reuse.

## Freshness and failure

Every command reports one of `current`, `stale`, `missing`, `invalid`, or
`unsupported`, with a bounded reason and schema version. A stale or unavailable
database grants no authority. Deleting it and rebuilding must reproduce the
same logical catalog from canonical files.

An interrupted build rolls back. An incompatible database remains untouched
and is reported `unsupported`. `rebuild` creates and validates a replacement
transactionally before publication; it does not expose partial rows.

## Concurrency

The maintenance command takes a per-project lock adjacent to the database.
Lock acquisition is bounded. A second builder exits with an explicit busy
status; it never writes concurrently. SQLite readers may continue to use the
last committed database while a builder prepares a transaction. Multi-window
Familiar clients are readers and do not own the lock.

## Cleanup and deletion

M08 does not run background retention or expose a broad deletion command.
Cleanup is an explicit user or host operation against the documented
`catalogs/` directory beneath the platform cache root; callers may apply their
own maximum age policy there. The directory contains only digest-named catalog
databases, lock files, and SQLite sidecars, but callers must still constrain
deletion to that directory. Removing the cache affects performance only;
canonical project and User Context files remain untouched. A future Mana
cleanup command requires its own bounded-target tests before this ADR can claim
it as supported.

## Watchers and platform behavior

Because the cache is outside `.mana`, publishing it cannot trigger the project
watcher. The path resolver uses native platform APIs and does not require a
Unix home layout on Windows. Tests override the root with `MANA_CACHE_HOME` and
must cover macOS-style, Windows-style, and XDG resolution without writing to a
real user cache.

## Consequences

The cache is disposable and local to one OS user. It improves repeated reads
without changing source authority or the default read-only Inspect contract.
Relocated projects without a stable remote may temporarily lose the speedup,
which is safer than binding unrelated projects by heuristic.
