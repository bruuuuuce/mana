#!/usr/bin/env python3
"""M08-B acceptance tests for the explicit derived catalog."""

from __future__ import annotations

import json
import importlib.util
import os
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mana-catalog.py"
SPEC = importlib.util.spec_from_file_location("mana_catalog_under_test", SCRIPT)
assert SPEC and SPEC.loader
CATALOG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CATALOG)


def run(project: Path, cache: Path, command: str, *, expected: int = 0, extra_env: dict[str, str] | None = None) -> dict:
    env = {**os.environ, "MANA_CACHE_HOME": str(cache), **(extra_env or {})}
    result = subprocess.run([str(SCRIPT), "--project-root", str(project), command, "--json"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert str(project) not in result.stdout
    return payload


def rows(database: Path) -> list[tuple]:
    connection = sqlite3.connect(database)
    try:
        return connection.execute("SELECT path,source_scope,file_type,byte_size,content_digest,revision_identity,classification,schema_version FROM entries ORDER BY path").fetchall()
    finally:
        connection.close()


def main() -> None:
    assert CATALOG.cache_root(platform="darwin", environment={}, home=Path("/Users/test")) == Path("/Users/test/Library/Caches/mana")
    assert CATALOG.cache_root(platform="win32", environment={"LOCALAPPDATA": "/windows/local"}, home=Path("/unused")) == Path("/windows/local/Mana/Cache")
    assert CATALOG.cache_root(platform="linux", environment={"XDG_CACHE_HOME": "/xdg/cache"}, home=Path("/unused")) == Path("/xdg/cache/mana")
    assert CATALOG.cache_root(platform="linux", environment={}, home=Path("/home/test")) == Path("/home/test/.cache/mana")
    try:
        CATALOG.cache_root(platform="linux", environment={"MANA_CACHE_HOME": "relative/cache"}, home=Path("/home/test"))
    except CATALOG.CatalogError:
        pass
    else:
        raise AssertionError("relative MANA_CACHE_HOME was accepted")

    with tempfile.TemporaryDirectory(prefix="mana-catalog-test-") as temporary:
        base = Path(temporary)
        project = base / "project"
        cache = base / "cache"
        (project / ".mana" / "global").mkdir(parents=True)
        (project / ".mana" / "global" / "architecture.md").write_text("# Secret-free architecture\n", encoding="utf-8")
        (project / ".mana" / "learning" / "candidates").mkdir(parents=True)
        candidate = project / ".mana" / "learning" / "candidates" / "candidate.json"
        candidate.write_text('{"candidateId":"candidate-1","status":"candidate"}\n', encoding="utf-8")
        (project / ".mana" / "env").write_text("TOKEN=must-not-enter-cache\n", encoding="utf-8")
        os.symlink("/outside", project / ".mana" / "unsafe-link")

        missing = run(project, cache, "status")
        assert missing["freshness"] == "missing"
        assert not cache.exists(), "read-only status created the cache root"

        first = run(project, cache, "build")
        assert first["freshness"] == "current"
        assert first["metrics"]["admitted_files"] == 2
        assert first["metrics"]["hashed_files"] == 2
        assert first["metrics"]["skipped"]["restricted"] == 1
        assert first["metrics"]["skipped"]["symlinks"] == 1
        databases = list((cache / "catalogs").glob("*.sqlite3"))
        assert len(databases) == 1
        database = databases[0]
        raw = database.read_bytes()
        assert str(project).encode() not in raw
        assert b"must-not-enter-cache" not in raw
        initial_rows = rows(database)
        assert [value[0] for value in initial_rows] == [".mana/global/architecture.md", ".mana/learning/candidates/candidate.json"]
        assert initial_rows[1][1] == "candidate"

        second = run(project, cache, "build")
        assert second["metrics"]["hashed_files"] == 0
        assert second["metrics"]["reused_files"] == 2
        assert run(project, cache, "status")["freshness"] == "current"

        architecture = project / ".mana" / "global" / "architecture.md"
        original_content = architecture.read_bytes()
        original_revision = dict((value[0], value[5]) for value in rows(database))[".mana/global/architecture.md"]
        architecture.write_bytes(b"# Changed architecture\n")
        assert run(project, cache, "status")["freshness"] == "stale"
        modified = run(project, cache, "build")
        assert modified["metrics"]["hashed_files"] == 1
        assert dict((value[0], value[5]) for value in rows(database))[".mana/global/architecture.md"] != original_revision
        architecture.write_bytes(original_content)
        run(project, cache, "build")

        mode = architecture.stat().st_mode
        architecture.chmod(0o600)
        assert run(project, cache, "status")["freshness"] == "stale"
        permission_build = run(project, cache, "build")
        assert permission_build["metrics"]["hashed_files"] == 1
        architecture.chmod(mode & 0o777)
        run(project, cache, "build")

        original_revision = dict((value[0], value[5]) for value in rows(database))[".mana/global/architecture.md"]
        replacement = project / ".mana" / "global" / "replacement.tmp"
        replacement.write_bytes(architecture.read_bytes())
        os.replace(replacement, architecture)
        assert run(project, cache, "status")["freshness"] == "stale"
        replacement_build = run(project, cache, "build")
        assert replacement_build["metrics"]["hashed_files"] == 1
        assert dict((value[0], value[5]) for value in rows(database))[".mana/global/architecture.md"] == original_revision

        architecture.unlink()
        os.symlink("/outside", architecture)
        assert run(project, cache, "status")["freshness"] == "stale"
        symlink_build = run(project, cache, "build")
        assert symlink_build["metrics"]["skipped"]["symlinks"] == 2
        assert ".mana/global/architecture.md" not in {value[0] for value in rows(database)}
        architecture.unlink()
        architecture.write_bytes(original_content)
        restored = run(project, cache, "build")
        assert restored["metrics"]["hashed_files"] == 1

        renamed = candidate.with_name("renamed.json")
        candidate.rename(renamed)
        added = project / ".mana" / "global" / "new.md"
        added.write_text("# New\n", encoding="utf-8")
        changed = run(project, cache, "build")
        assert changed["metrics"]["hashed_files"] == 2
        assert changed["metrics"]["deleted_files"] == 1
        added.unlink()
        renamed.unlink()
        deleted = run(project, cache, "build")
        assert deleted["metrics"]["deleted_files"] == 2
        assert run(project, cache, "verify")["freshness"] == "current"

        before_rebuild = rows(database)
        rebuilt = run(project, cache, "rebuild")
        assert rebuilt["reason"] == "rebuild-published"
        assert rows(database) == before_rebuild
        database.unlink()
        rebuilt_from_missing = run(project, cache, "build")
        assert rebuilt_from_missing["metrics"]["reused_files"] == 0
        assert rows(database) == before_rebuild

        holder_env = {**os.environ, "MANA_CACHE_HOME": str(cache), "MANA_CATALOG_TEST_HOLD_LOCK_MS": "750"}
        holder = subprocess.Popen([str(SCRIPT), "--project-root", str(project), "build", "--json"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=holder_env)
        time.sleep(0.15)
        busy = run(project, cache, "build", expected=6)
        assert busy["freshness"] == "stale" and "busy" in busy["reason"]
        stdout, stderr = holder.communicate(timeout=5)
        assert holder.returncode == 0, (stdout, stderr)

        database.write_bytes(b"not-a-sqlite-database")
        invalid = run(project, cache, "status", expected=4)
        assert invalid["freshness"] == "invalid"

    print("Mana M08 derived catalog tests passed")


if __name__ == "__main__":
    main()
