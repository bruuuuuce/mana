#!/usr/bin/env python3
"""Explicit M08 derived catalog maintenance; never called implicitly by Inspect."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterator, Mapping


SCHEMA_VERSION = 1
RESTRICTED = {".mana/jira-mcp.env", ".mana/env"}
MAX_FILE_BYTES = 1_048_576


class CatalogError(RuntimeError):
    pass


class BusyError(CatalogError):
    pass


def cache_root(*, platform: str | None = None, environment: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    platform = sys.platform if platform is None else platform
    environment = os.environ if environment is None else environment
    home = Path.home() if home is None else home
    override = environment.get("MANA_CACHE_HOME")
    if override:
        root = Path(override)
        if not root.is_absolute():
            raise CatalogError("MANA_CACHE_HOME must be absolute")
        return root
    if platform == "win32":
        local = environment.get("LOCALAPPDATA")
        if not local:
            raise CatalogError("LOCALAPPDATA is unavailable")
        return Path(local) / "Mana" / "Cache"
    if platform == "darwin":
        return home / "Library" / "Caches" / "mana"
    return Path(environment.get("XDG_CACHE_HOME", home / ".cache")) / "mana"


def project_identity(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    basis = f"remote:{result.stdout.strip()}" if result.returncode == 0 and result.stdout.strip() else f"root:{root}"
    return hashlib.sha256(basis.encode()).hexdigest()


def paths(root: Path) -> tuple[str, Path, Path]:
    identity = project_identity(root)
    directory = cache_root() / "catalogs"
    return identity, directory / f"{identity}.sqlite3", directory / f"{identity}.lock"


@contextlib.contextmanager
def lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise BusyError("catalog builder is busy") from error
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise BusyError("catalog builder is busy") from error
        hold_ms = int(os.environ.get("MANA_CATALOG_TEST_HOLD_LOCK_MS", "0"))
        if hold_ms:
            time.sleep(hold_ms / 1000)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()


def connect(path: Path, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0)
    else:
        connection = sqlite3.connect(path, timeout=0)
    connection.row_factory = sqlite3.Row
    return connection


def initialize(connection: sqlite3.Connection, identity: str) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS entries (
          path TEXT PRIMARY KEY,
          source_scope TEXT NOT NULL,
          file_type TEXT NOT NULL,
          byte_size INTEGER NOT NULL,
          device INTEGER NOT NULL,
          inode INTEGER NOT NULL,
          mtime_ns INTEGER NOT NULL,
          ctime_ns INTEGER NOT NULL,
          mode INTEGER NOT NULL,
          content_digest TEXT NOT NULL,
          revision_identity TEXT NOT NULL,
          classification TEXT NOT NULL,
          schema_version INTEGER NOT NULL
        ) WITHOUT ROWID;
        """
    )
    existing = dict(connection.execute("SELECT key,value FROM metadata"))
    if existing and (existing.get("schema_version") != str(SCHEMA_VERSION) or existing.get("project_identity") != identity):
        raise CatalogError("catalog schema or project identity is unsupported")
    connection.executemany(
        "INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)",
        [("schema_version", str(SCHEMA_VERSION)), ("project_identity", identity)],
    )


def scope(relative: str) -> str:
    if relative.startswith(".mana/user-context/") or relative == ".mana/user-context-state":
        return "user"
    if relative.startswith(".mana/learning/candidates/"):
        return "candidate"
    return "project"


def classification(relative: str) -> str:
    if relative.startswith(".mana/global/"):
        return "service_context"
    if relative.startswith((".mana/features/", ".mana/sessions/")):
        return "workspace"
    if relative.startswith(".mana/runtime/"):
        return "runtime"
    if relative.startswith(".mana/learning/candidates/"):
        return "learning"
    if relative.startswith(".mana/learning/"):
        return "knowledge"
    if relative.startswith(".mana/user-context/"):
        return "user_context"
    return "unknown"


def file_type(relative: str) -> str:
    suffix = Path(relative).suffix.lower()
    return {".md": "text/markdown", ".json": "application/json", ".jsonl": "application/json", ".yaml": "application/yaml", ".yml": "application/yaml", ".txt": "text/plain"}.get(suffix, "application/octet-stream")


def discover(root: Path) -> tuple[list[tuple[str, Path, os.stat_result]], dict[str, int]]:
    mana = root / ".mana"
    if mana.is_symlink():
        raise CatalogError(".mana must not be a symlink")
    if not mana.exists():
        return [], {"symlinks": 0, "oversize": 0, "restricted": 0, "unreadable": 0}
    if not mana.is_dir():
        raise CatalogError(".mana is not a directory")
    admitted: list[tuple[str, Path, os.stat_result]] = []
    skipped = {"symlinks": 0, "oversize": 0, "restricted": 0, "unreadable": 0}
    for directory, names, filenames in os.walk(mana, topdown=True, followlinks=False):
        base = Path(directory)
        kept: list[str] = []
        for name in sorted(names):
            candidate = base / name
            if candidate.is_symlink():
                skipped["symlinks"] += 1
            else:
                kept.append(name)
        names[:] = kept
        for name in sorted(filenames):
            candidate = base / name
            relative = candidate.relative_to(root).as_posix()
            if candidate.is_symlink():
                skipped["symlinks"] += 1
                continue
            if relative in RESTRICTED or name in {"latest.json", "latest.md"}:
                skipped["restricted"] += 1
                continue
            try:
                info = candidate.stat()
            except OSError:
                skipped["unreadable"] += 1
                continue
            if not stat.S_ISREG(info.st_mode):
                skipped["unreadable"] += 1
                continue
            if info.st_size > MAX_FILE_BYTES:
                skipped["oversize"] += 1
                continue
            admitted.append((relative, candidate, info))
    admitted.sort(key=lambda value: value[0])
    return admitted, skipped


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def sqlite_file_identity(value: int) -> int | str:
    # NTFS file IDs can be wider than SQLite's signed 64-bit INTEGER. A tagged
    # decimal string keeps every bit and avoids INTEGER affinity converting a
    # bare decimal string into an imprecise REAL. Existing small IDs stay ints.
    return value if -(1 << 63) <= value < (1 << 63) else f"integer:{value}"


def metadata_matches(row: sqlite3.Row, info: os.stat_result) -> bool:
    return all(
        row[key] == value
        for key, value in (
            ("byte_size", info.st_size),
            ("device", sqlite_file_identity(info.st_dev)),
            ("inode", sqlite_file_identity(info.st_ino)),
            ("mtime_ns", info.st_mtime_ns),
            ("ctime_ns", info.st_ctime_ns),
            ("mode", stat.S_IMODE(info.st_mode)),
        )
    )


def validate_database(connection: sqlite3.Connection, identity: str) -> None:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise CatalogError("catalog integrity check failed")
    values = dict(connection.execute("SELECT key,value FROM metadata"))
    if values.get("schema_version") != str(SCHEMA_VERSION) or values.get("project_identity") != identity:
        raise CatalogError("catalog schema or project identity is unsupported")


def build_database(root: Path, database: Path, identity: str) -> dict[str, object]:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(database)
    try:
        initialize(connection, identity)
        previous = {row["path"]: row for row in connection.execute("SELECT * FROM entries")}
        admitted, skipped = discover(root)
        rows = []
        hashed = reused = 0
        for relative, path, info in admitted:
            old = previous.get(relative)
            if old is not None and metadata_matches(old, info):
                content_digest = old["content_digest"]
                reused += 1
            else:
                content_digest = digest(path)
                hashed += 1
            rows.append(
                (
                    relative,
                    scope(relative),
                    file_type(relative),
                    info.st_size,
                    sqlite_file_identity(info.st_dev),
                    sqlite_file_identity(info.st_ino),
                    info.st_mtime_ns,
                    info.st_ctime_ns,
                    stat.S_IMODE(info.st_mode),
                    content_digest,
                    f"sha256:{content_digest}",
                    classification(relative),
                    SCHEMA_VERSION,
                )
            )
        with connection:
            connection.execute("DELETE FROM entries")
            connection.executemany("INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            connection.execute("INSERT OR REPLACE INTO metadata VALUES('verified_at_epoch',?)", (str(int(time.time())),))
        validate_database(connection, identity)
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        logical = hashlib.sha256("".join(f"{row[0]}\0{row[10]}\n" for row in rows).encode()).hexdigest()
        return {"admitted_files": len(rows), "hashed_files": hashed, "reused_files": reused, "deleted_files": len(set(previous) - {row[0] for row in rows}), "skipped": skipped, "logical_revision": f"sha256:{logical}"}
    finally:
        connection.close()


def status(root: Path, database: Path, identity: str) -> tuple[str, str, dict[str, object]]:
    if not database.exists():
        return "missing", "catalog-not-built", {}
    try:
        connection = connect(database, readonly=True)
        validate_database(connection, identity)
        previous = {row["path"]: row for row in connection.execute("SELECT * FROM entries")}
        admitted, skipped = discover(root)
        current = {relative: info for relative, _, info in admitted}
        if set(previous) != set(current):
            return "stale", "path-set-changed", {"admitted_files": len(current), "skipped": skipped}
        if any(not metadata_matches(previous[path], info) for path, info in current.items()):
            return "stale", "file-identity-or-metadata-changed", {"admitted_files": len(current), "skipped": skipped}
        return "current", "metadata-and-file-identity-match", {"admitted_files": len(current), "skipped": skipped}
    except sqlite3.DatabaseError:
        return "invalid", "sqlite-validation-failed", {}
    except CatalogError:
        return "unsupported", "schema-or-project-identity-mismatch", {}
    finally:
        if "connection" in locals():
            connection.close()


def verify(root: Path, database: Path, identity: str) -> tuple[str, str, dict[str, object]]:
    if not database.exists():
        return "missing", "catalog-not-built", {}
    try:
        connection = connect(database, readonly=True)
        validate_database(connection, identity)
        previous = {row["path"]: row for row in connection.execute("SELECT * FROM entries")}
        admitted, skipped = discover(root)
        if set(previous) != {value[0] for value in admitted}:
            return "stale", "path-set-changed", {"verified_files": 0, "skipped": skipped}
        verified = 0
        for relative, path, _ in admitted:
            if digest(path) != previous[relative]["content_digest"]:
                return "stale", "content-digest-changed", {"verified_files": verified, "skipped": skipped}
            verified += 1
        return "current", "all-content-digests-match", {"verified_files": verified, "skipped": skipped}
    except sqlite3.DatabaseError:
        return "invalid", "sqlite-validation-failed", {}
    except CatalogError:
        return "unsupported", "schema-or-project-identity-mismatch", {}
    finally:
        if "connection" in locals():
            connection.close()


def emit(command: str, freshness: str, reason: str, identity: str, metrics: dict[str, object]) -> None:
    print(json.dumps({"schema": "mana.catalog.maintenance/v1", "command": command, "freshness": freshness, "reason": reason, "project_identity": f"sha256:{identity}", "catalog_schema_version": SCHEMA_VERSION, "metrics": metrics, "guarantees": {"canonical_writes": False, "project_writes": False, "source_content_stored": False, "absolute_paths_stored": False, "model_calls": 0, "network_calls": 0}}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("command", choices=("status", "build", "verify", "rebuild"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.json:
        raise SystemExit("--json is required")
    root = args.project_root.resolve(strict=True)
    identity, database, lock_path = paths(root)
    try:
        if args.command == "status":
            freshness, reason, metrics = status(root, database, identity)
        elif args.command == "verify":
            freshness, reason, metrics = verify(root, database, identity)
        elif args.command == "build":
            with lock(lock_path):
                metrics = build_database(root, database, identity)
            freshness, reason = "current", "incremental-build-committed"
        else:
            with lock(lock_path):
                database.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary = tempfile.mkstemp(prefix=f"{identity}.", suffix=".sqlite3", dir=database.parent)
                os.close(descriptor)
                Path(temporary).unlink()
                try:
                    metrics = build_database(root, Path(temporary), identity)
                    os.replace(temporary, database)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            freshness, reason = "current", "rebuild-published"
        emit(args.command, freshness, reason, identity, metrics)
        return 0 if freshness in {"current", "missing", "stale"} else 4
    except BusyError as error:
        emit(args.command, "stale", str(error), identity, {})
        return 6
    except (CatalogError, OSError, sqlite3.DatabaseError) as error:
        emit(args.command, "invalid", str(error), identity, {})
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
