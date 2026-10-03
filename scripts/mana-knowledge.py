#!/usr/bin/env python3
"""M08-C local lexical knowledge index and bounded retrieval contracts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
loader_spec = importlib.util.spec_from_file_location("mana_catalog", ROOT / "scripts" / "mana-catalog.py")
assert loader_spec and loader_spec.loader
catalog = importlib.util.module_from_spec(loader_spec)
sys.modules[loader_spec.name] = catalog
loader_spec.loader.exec_module(catalog)

KNOWLEDGE_SCHEMA_VERSION = 1
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".adoc"}
MAX_DOCUMENT_BYTES = 1_048_576
MAX_PASSAGE_BYTES = 2_048
SCOPES = {"framework", "user", "project", "candidate"}
LIFECYCLES = {"active", "candidate", "reviewed", "rejected", "deferred", "archived", "superseded"}


@dataclass(frozen=True)
class Source:
    document_id: str
    reference: str
    path: Path
    scope: str
    lifecycle: str
    title: str | None
    info: os.stat_result
    candidate: bool = False


def identifier(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:24]}"


def git_blob_digest(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def healthy_user_mirror(project: Path) -> tuple[bool, str]:
    state = project / ".mana" / "user-context-state"
    mirror = project / ".mana" / "user-context"
    if not state.is_file() or state.is_symlink() or not mirror.is_dir() or mirror.is_symlink():
        return False, ""
    values = {}
    for line in state.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    if values.get("schema") != "1" or values.get("status") != "healthy" or not values.get("digest"):
        return False, values.get("digest", "")
    records = []
    for path in sorted(mirror.rglob("*")):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            return False, values["digest"]
        data = path.read_bytes()
        if len(data) > MAX_DOCUMENT_BYTES or path.stat().st_mode & 0o222:
            return False, values["digest"]
        records.append(f"{git_blob_digest(data)}\t{len(data)}\t{path.relative_to(mirror).as_posix()}\n")
    manifest = "".join(records).encode()
    return git_blob_digest(manifest) == values["digest"], values["digest"]


def configured_user_source(project: Path) -> Path | None:
    """Resolve the explicitly configured external User Context source.

    The generated project mirror remains read-only.  This path is disclosed
    only as part of an advertised write capability so a client can show the
    exact external target before asking Mana to mutate it.
    """
    result = subprocess.run(
        [str(ROOT / "scripts" / "mana-context.sh"), "path", "--source", "--project-root", str(project)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        source = Path(result.stdout.strip())
        if not source.is_absolute() or not source.is_dir():
            return None
        return source.resolve(strict=True)
    except (OSError, ValueError):
        return None


def regular_text(path: Path) -> os.stat_result | None:
    if path.is_symlink() or path.suffix.lower() not in TEXT_SUFFIXES:
        return None
    try:
        info = path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DOCUMENT_BYTES:
        return None
    return info


def add_source(values: list[Source], path: Path, reference: str, scope: str, lifecycle: str, title: str | None = None, candidate: bool = False) -> None:
    info = path.stat() if candidate and path.is_file() and not path.is_symlink() else regular_text(path)
    if info is None or not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DOCUMENT_BYTES:
        return
    values.append(Source(identifier("doc", f"{scope}\0{reference}"), reference, path, scope, lifecycle, title, info, candidate))


def discover(project: Path) -> tuple[list[Source], list[dict[str, str]], str]:
    sources: list[Source] = []
    diagnostics: list[dict[str, str]] = []
    manifest = json.loads((ROOT / "config" / "knowledge-sources.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "mana.knowledge.framework-sources/v1":
        raise catalog.CatalogError("framework source manifest is invalid")
    for relative in manifest["sources"]:
        if not isinstance(relative, str) or relative.startswith("/") or ".." in Path(relative).parts:
            raise catalog.CatalogError("framework source manifest contains an unsafe path")
        add_source(sources, ROOT / relative, f"mana://framework/{relative}", "framework", "active")

    global_root = project / ".mana" / "global"
    if global_root.is_dir() and not global_root.is_symlink():
        for path in sorted(global_root.rglob("*")):
            add_source(sources, path, path.relative_to(project).as_posix(), "project", "active")
    journey_root = project / ".mana" / "learning" / "journeys"
    if journey_root.is_dir() and not journey_root.is_symlink():
        for path in sorted(journey_root.rglob("*")):
            add_source(sources, path, path.relative_to(project).as_posix(), "project", "active")

    user_healthy, user_digest = healthy_user_mirror(project)
    user_root = project / ".mana" / "user-context"
    if user_healthy:
        for path in sorted(user_root.rglob("*")):
            add_source(sources, path, path.relative_to(project).as_posix(), "user", "active")
    elif user_root.exists():
        diagnostics.append({"code": "user_context_not_current", "scope": "user"})

    candidate_root = project / ".mana" / "learning" / "candidates"
    if candidate_root.is_dir() and not candidate_root.is_symlink():
        for path in sorted(candidate_root.glob("*.json")):
            if path.is_symlink() or path.stat().st_size > MAX_DOCUMENT_BYTES:
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                diagnostics.append({"code": "malformed_candidate", "scope": "candidate"})
                continue
            lifecycle = value.get("status")
            if lifecycle not in LIFECYCLES - {"active", "superseded"}:
                diagnostics.append({"code": "unsupported_candidate_lifecycle", "scope": "candidate"})
                continue
            title = value.get("candidateId") if isinstance(value.get("candidateId"), str) else path.stem
            add_source(sources, path, path.relative_to(project).as_posix(), "candidate", lifecycle, title, True)
    sources.sort(key=lambda source: (source.scope, source.reference))
    signature_basis = [user_digest]
    for source in sources:
        info = source.info
        signature_basis.append(f"{source.document_id}\0{source.lifecycle}\0{info.st_dev}\0{info.st_ino}\0{info.st_size}\0{info.st_mtime_ns}\0{info.st_ctime_ns}")
    return sources, diagnostics, hashlib.sha256("\n".join(signature_basis).encode()).hexdigest()


def source_content(source: Source) -> str:
    if source.candidate:
        value = json.loads(source.path.read_text(encoding="utf-8"))
        fields = ["observation", "possibleImpact", "counterEvidence", "suggestedDestination"]
        parts = [f"# {source.title}"] + [f"## {name}\n{value[name]}" for name in fields if isinstance(value.get(name), str)]
        return "\n\n".join(parts) + "\n"
    data = source.path.read_bytes()
    if b"\x00" in data:
        raise UnicodeError("binary content")
    return data.decode("utf-8")


def title_and_passages(source: Source, content: str) -> tuple[str, list[tuple[str, str, str]]]:
    title = source.title
    headings: list[str] = []
    paragraphs: list[tuple[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        buffer.clear()
        if text:
            paragraphs.append((" / ".join(headings), text))

    for line in content.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", line)
        if match:
            flush()
            level = len(match.group(1))
            heading = re.sub(r"\s+", " ", match.group(2)).strip()[:256]
            headings[:] = headings[: level - 1]
            headings.append(heading)
            if level == 1 and not title:
                title = heading
        elif line.strip():
            buffer.append(line.rstrip())
        else:
            flush()
    flush()
    title = title or Path(source.reference).stem
    chunks: list[tuple[str, str, str]] = []
    ordinal = 0
    for heading, paragraph in paragraphs:
        remaining = paragraph
        while remaining:
            encoded = remaining.encode("utf-8")
            if len(encoded) <= MAX_PASSAGE_BYTES:
                chunk, remaining = remaining, ""
            else:
                prefix = encoded[:MAX_PASSAGE_BYTES].decode("utf-8", errors="ignore")
                split = max(prefix.rfind("\n"), prefix.rfind(" "))
                if split < MAX_PASSAGE_BYTES // 2:
                    split = len(prefix)
                chunk, remaining = remaining[:split].strip(), remaining[split:].strip()
            if not chunk:
                break
            passage_id = identifier("psg", f"{source.document_id}\0{heading}\0{ordinal}")
            chunks.append((passage_id, heading, chunk))
            ordinal += 1
    return title, chunks


def ensure_schema(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(passage_id UNINDEXED, document_id UNINDEXED, title, heading_path, body, source_scope UNINDEXED, lifecycle_state UNINDEXED, passage_revision UNINDEXED, tokenize='unicode61 remove_diacritics 2')")
    except sqlite3.OperationalError as error:
        raise catalog.CatalogError("sqlite-fts5-unavailable") from error
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
          document_id TEXT PRIMARY KEY,
          source_reference TEXT NOT NULL,
          source_scope TEXT NOT NULL,
          lifecycle_state TEXT NOT NULL,
          title TEXT NOT NULL,
          document_revision TEXT NOT NULL,
          byte_size INTEGER NOT NULL,
          device INTEGER NOT NULL,
          inode INTEGER NOT NULL,
          mtime_ns INTEGER NOT NULL,
          ctime_ns INTEGER NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS knowledge_passages (
          row_id INTEGER PRIMARY KEY AUTOINCREMENT,
          passage_id TEXT NOT NULL UNIQUE,
          document_id TEXT NOT NULL,
          ordinal INTEGER NOT NULL,
          heading_path TEXT NOT NULL,
          body TEXT NOT NULL,
          passage_revision TEXT NOT NULL,
          byte_size INTEGER NOT NULL
        );
        """
    )


def index_status(project: Path, database: Path, identity: str) -> tuple[str, str, str, list[dict[str, str]]]:
    if not database.exists():
        return "missing", "catalog-not-built", "", []
    try:
        connection = catalog.connect(database, readonly=True)
        catalog.validate_database(connection, identity)
        values = dict(connection.execute("SELECT key,value FROM metadata"))
        if values.get("knowledge_schema_version") != str(KNOWLEDGE_SCHEMA_VERSION):
            return "missing", "knowledge-index-not-built", "", []
        sources, diagnostics, signature = discover(project)
        if values.get("knowledge_source_signature") != signature:
            return "stale", "admitted-source-set-or-file-identity-changed", values.get("knowledge_revision", ""), diagnostics
        if connection.execute("SELECT count(*) FROM knowledge_documents").fetchone()[0] != len(sources):
            return "invalid", "document-count-mismatch", values.get("knowledge_revision", ""), diagnostics
        return "current", "source-file-identities-match", values.get("knowledge_revision", ""), diagnostics
    except sqlite3.DatabaseError:
        return "invalid", "sqlite-validation-failed", "", []
    except catalog.CatalogError as error:
        return "unsupported", str(error), "", []
    finally:
        if "connection" in locals():
            connection.close()


def build(project: Path, database: Path, identity: str) -> dict[str, object]:
    catalog_freshness, _, _ = catalog.status(project, database, identity)
    if catalog_freshness != "current":
        raise catalog.CatalogError(f"derived-catalog-{catalog_freshness}")
    sources, diagnostics, signature = discover(project)
    connection = catalog.connect(database)
    indexed = reused = removed = passages_count = 0
    try:
        catalog.validate_database(connection, identity)
        ensure_schema(connection)
        existing = {row["document_id"]: row for row in connection.execute("SELECT * FROM knowledge_documents")}
        admitted_ids = {source.document_id for source in sources}
        with connection:
            for document_id in set(existing) - admitted_ids:
                row_ids = [row[0] for row in connection.execute("SELECT row_id FROM knowledge_passages WHERE document_id=?", (document_id,))]
                connection.executemany("DELETE FROM knowledge_fts WHERE rowid=?", ((row_id,) for row_id in row_ids))
                connection.execute("DELETE FROM knowledge_passages WHERE document_id=?", (document_id,))
                connection.execute("DELETE FROM knowledge_documents WHERE document_id=?", (document_id,))
                removed += 1
            manifest_rows = []
            for source in sources:
                content = source_content(source)
                revision = f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"
                old = existing.get(source.document_id)
                if old is not None and old["document_revision"] == revision and old["lifecycle_state"] == source.lifecycle:
                    reused += 1
                    manifest_rows.append((source.document_id, revision, source.lifecycle))
                    continue
                if old is not None:
                    row_ids = [row[0] for row in connection.execute("SELECT row_id FROM knowledge_passages WHERE document_id=?", (source.document_id,))]
                    connection.executemany("DELETE FROM knowledge_fts WHERE rowid=?", ((row_id,) for row_id in row_ids))
                    connection.execute("DELETE FROM knowledge_passages WHERE document_id=?", (source.document_id,))
                title, passages = title_and_passages(source, content)
                info = source.info
                connection.execute("INSERT OR REPLACE INTO knowledge_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)", (source.document_id, source.reference, source.scope, source.lifecycle, title, revision, len(content.encode()), info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns))
                for ordinal, (passage_id, heading, body) in enumerate(passages):
                    passage_revision = f"sha256:{hashlib.sha256(body.encode()).hexdigest()}"
                    cursor = connection.execute("INSERT INTO knowledge_passages(passage_id,document_id,ordinal,heading_path,body,passage_revision,byte_size) VALUES(?,?,?,?,?,?,?)", (passage_id, source.document_id, ordinal, heading, body, passage_revision, len(body.encode())))
                    connection.execute("INSERT INTO knowledge_fts(rowid,passage_id,document_id,title,heading_path,body,source_scope,lifecycle_state,passage_revision) VALUES(?,?,?,?,?,?,?,?,?)", (cursor.lastrowid, passage_id, source.document_id, title, heading, body, source.scope, source.lifecycle, passage_revision))
                    passages_count += 1
                indexed += 1
                manifest_rows.append((source.document_id, revision, source.lifecycle))
            knowledge_revision = "sha256:" + hashlib.sha256("".join(f"{doc}\0{rev}\0{state}\n" for doc, rev, state in sorted(manifest_rows)).encode()).hexdigest()
            connection.executemany("INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)", [("knowledge_schema_version", str(KNOWLEDGE_SCHEMA_VERSION)), ("knowledge_source_signature", signature), ("knowledge_revision", knowledge_revision)])
        return {"freshness": "current", "revision": knowledge_revision, "documents": len(sources), "indexed_documents": indexed, "reused_documents": reused, "removed_documents": removed, "indexed_passages": passages_count, "diagnostics": diagnostics, "fts": "sqlite-fts5-bm25/v1"}
    finally:
        connection.close()


def emit_status(command: str, freshness: str, reason: str, revision: str, diagnostics: list[dict[str, str]]) -> None:
    print(json.dumps({"schema": "mana.knowledge.index-status/v1", "command": command, "freshness": freshness, "reason": reason, "revision": revision or None, "capability": "sqlite-fts5-bm25/v1" if freshness != "unsupported" else "unavailable", "diagnostics": diagnostics, "guarantees": {"model_calls": 0, "network_calls": 0, "canonical_writes": False}}, sort_keys=True))


def query_terms(query: str) -> list[str]:
    return list(dict.fromkeys(term.casefold() for term in re.findall(r"[^\W_]{2,}", query, flags=re.UNICODE)))[:12]


def search(project: Path, database: Path, identity: str, args: argparse.Namespace) -> tuple[dict[str, object], int]:
    freshness, reason, revision, diagnostics = index_status(project, database, identity)
    base = {"schema": "mana.knowledge.search/v1", "query": args.query, "index": {"freshness": freshness, "reason": reason, "revision": revision or None, "ranking": "sqlite-fts5-bm25/v1"}, "filters": {"scopes": args.scope, "lifecycles": args.lifecycle}, "limits": {"results": args.limit, "returned_bytes": args.max_bytes}, "results": [], "gaps": [], "diagnostics": diagnostics, "guarantees": {"generated_answer": False, "model_calls": 0, "network_calls": 0}, "returned_bytes": 0}
    if freshness != "current":
        base["gaps"].append({"code": "index_not_current"})
        return base, 4
    if args.if_revision and args.if_revision != revision:
        base["gaps"].append({"code": "revision_precondition_failed"})
        return base, 4
    terms = query_terms(args.query)
    if not terms:
        base["gaps"].append({"code": "no_searchable_terms"})
        return base, 2
    expression = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
    placeholders_scope = ",".join("?" for _ in args.scope)
    placeholders_lifecycle = ",".join("?" for _ in args.lifecycle)
    snippet_column = "" if args.metadata_only else ",snippet(knowledge_fts,4,'','…',' … ',24) AS snippet"
    sql = f"SELECT rowid,passage_id,document_id,title,heading_path,source_scope,lifecycle_state,passage_revision,bm25(knowledge_fts) AS score{snippet_column} FROM knowledge_fts WHERE knowledge_fts MATCH ? AND source_scope IN ({placeholders_scope}) AND lifecycle_state IN ({placeholders_lifecycle}) ORDER BY score,document_id,passage_id LIMIT ?"
    connection = catalog.connect(database, readonly=True)
    returned = 0
    try:
        rows = connection.execute(sql, [expression, *args.scope, *args.lifecycle, args.limit]).fetchall()
        for row in rows:
            snippet = None if args.metadata_only else row["snippet"]
            size = len((snippet or "").encode())
            if returned + size > args.max_bytes:
                base["gaps"].append({"code": "returned_byte_budget_reached"})
                break
            document = connection.execute("SELECT source_reference,document_revision FROM knowledge_documents WHERE document_id=?", (row["document_id"],)).fetchone()
            result = {"passage_id": row["passage_id"], "document_id": row["document_id"], "title": row["title"], "heading_path": [value for value in row["heading_path"].split(" / ") if value], "source_scope": row["source_scope"], "lifecycle_state": row["lifecycle_state"], "source_reference": document["source_reference"], "document_revision": document["document_revision"], "passage_revision": row["passage_revision"], "rank": {"algorithm": "sqlite-fts5-bm25/v1", "score": row["score"], "reasons": [f"term:{term}" for term in terms]}, "returned_bytes": size}
            if snippet is not None:
                result["snippet"] = snippet
            base["results"].append(result)
            returned += size
        base["returned_bytes"] = returned
        if not base["results"]:
            base["gaps"].append({"code": "no_matching_passage"})
        return base, 0
    finally:
        connection.close()


def passage(database: Path, identity: str, project: Path, args: argparse.Namespace) -> tuple[dict[str, object], int]:
    freshness, reason, revision, diagnostics = index_status(project, database, identity)
    response = {"schema": "mana.knowledge.passage/v1", "index": {"freshness": freshness, "reason": reason, "revision": revision or None}, "passage": None, "diagnostics": diagnostics}
    if freshness != "current" or (args.if_revision and args.if_revision != revision):
        return response, 4
    connection = catalog.connect(database, readonly=True)
    try:
        row = connection.execute("SELECT p.*,d.source_reference,d.source_scope,d.lifecycle_state,d.document_revision,d.title FROM knowledge_passages p JOIN knowledge_documents d USING(document_id) WHERE passage_id=?", (args.passage_id,)).fetchone()
        if row is None:
            return response, 2
        body = row["body"].encode()[: args.max_bytes].decode("utf-8", errors="ignore")
        response["passage"] = {"passage_id": row["passage_id"], "document_id": row["document_id"], "title": row["title"], "heading_path": [value for value in row["heading_path"].split(" / ") if value], "body": body, "truncated": len(body.encode()) < row["byte_size"], "source_reference": row["source_reference"], "source_scope": row["source_scope"], "lifecycle_state": row["lifecycle_state"], "document_revision": row["document_revision"], "passage_revision": row["passage_revision"]}
        return response, 0
    finally:
        connection.close()


def capabilities(project: Path, database: Path, identity: str) -> tuple[dict[str, object], int]:
    freshness, reason, revision, diagnostics = index_status(project, database, identity)
    user_available = not any(item.get("code") == "user_context_not_current" for item in diagnostics)
    user_source = configured_user_source(project) if freshness == "current" and user_available else None
    user_editable = user_source is not None
    return {
        "schema": "mana.knowledge.capabilities/v1",
        "index": {"freshness": freshness, "reason": reason, "revision": revision or None, "ranking": "sqlite-fts5-bm25/v1"},
        "scopes": [
            {"scope": "framework", "health": "current" if freshness == "current" else freshness, "editable": False},
            {
                "scope": "user",
                "health": "current" if freshness == "current" and user_available else "unavailable",
                "editable": user_editable,
                "reason": "explicit-source-confirmation-required" if user_editable else "configured-external-source-unavailable",
                "source_disclosure": str(user_source) if user_editable else None,
            },
            {"scope": "project", "health": "current" if freshness == "current" else freshness, "editable": True},
            {"scope": "candidate", "health": "current" if freshness == "current" else freshness, "editable": False},
        ],
        "operations": ["capabilities", "documents", "document", "search", "passage", "learning-candidates"],
        "effective_context_trace": {"status": "unavailable", "reason": "no-authoritative-run-receipt-adapter"},
        "diagnostics": diagnostics,
    }, 0 if freshness in {"current", "stale", "missing"} else 4


def documents(project: Path, database: Path, identity: str, args: argparse.Namespace) -> tuple[dict[str, object], int]:
    freshness, reason, revision, diagnostics = index_status(project, database, identity)
    response = {"schema": "mana.knowledge.documents/v1", "index": {"freshness": freshness, "reason": reason, "revision": revision or None}, "filters": {"scopes": args.scope, "lifecycles": args.lifecycle}, "documents": [], "next_offset": None, "diagnostics": diagnostics}
    if freshness != "current":
        return response, 4
    scopes = ",".join("?" for _ in args.scope)
    states = ",".join("?" for _ in args.lifecycle)
    connection = catalog.connect(database, readonly=True)
    try:
        rows = connection.execute(f"SELECT document_id,source_reference,source_scope,lifecycle_state,title,document_revision,byte_size FROM knowledge_documents WHERE source_scope IN ({scopes}) AND lifecycle_state IN ({states}) ORDER BY source_scope,title,document_id LIMIT ? OFFSET ?", [*args.scope, *args.lifecycle, args.limit + 1, args.offset]).fetchall()
        page = rows[: args.limit]
        response["documents"] = [dict(row) for row in page]
        if len(rows) > args.limit:
            response["next_offset"] = args.offset + args.limit
        return response, 0
    finally:
        connection.close()


def document_detail(project: Path, database: Path, identity: str, args: argparse.Namespace) -> tuple[dict[str, object], int]:
    freshness, reason, revision, diagnostics = index_status(project, database, identity)
    response = {"schema": "mana.knowledge.document/v1", "index": {"freshness": freshness, "reason": reason, "revision": revision or None}, "document": None, "diagnostics": diagnostics}
    if freshness != "current" or (args.if_revision and args.if_revision != revision):
        return response, 4
    connection = catalog.connect(database, readonly=True)
    try:
        value = connection.execute("SELECT * FROM knowledge_documents WHERE document_id=?", (args.document_id,)).fetchone()
        if value is None:
            return response, 2
        returned = 0
        passages = []
        truncated = False
        for row in connection.execute("SELECT passage_id,ordinal,heading_path,body,passage_revision,byte_size FROM knowledge_passages WHERE document_id=? ORDER BY ordinal", (args.document_id,)):
            remaining = args.max_bytes - returned
            if remaining <= 0:
                truncated = True
                break
            body = row["body"].encode()[:remaining].decode("utf-8", errors="ignore")
            passages.append({"passage_id": row["passage_id"], "ordinal": row["ordinal"], "heading_path": [part for part in row["heading_path"].split(" / ") if part], "body": body, "passage_revision": row["passage_revision"], "truncated": len(body.encode()) < row["byte_size"]})
            returned += len(body.encode())
            if passages[-1]["truncated"]:
                truncated = True
                break
        editable = False
        editable_content = None
        edit_target = None
        source_disclosure = None
        if value["source_scope"] == "project" and value["source_reference"].startswith(".mana/global/"):
            source = project / value["source_reference"]
            try:
                if source.is_symlink():
                    raise ValueError("editable source is a symlink")
                resolved = source.resolve(strict=True)
                contained = os.path.commonpath([str(project), str(resolved)]) == str(project)
                raw = resolved.read_bytes() if contained and resolved.is_file() else b""
                current_revision = f"sha256:{hashlib.sha256(raw).hexdigest()}"
                if current_revision == value["document_revision"] and len(raw) <= args.max_bytes:
                    editable_content = raw.decode("utf-8")
                    editable = True
                    edit_target = value["source_reference"]
            except (OSError, UnicodeError, ValueError):
                pass
        elif value["source_scope"] == "user" and value["source_reference"].startswith(".mana/user-context/"):
            source_root = configured_user_source(project)
            relative = value["source_reference"][len(".mana/user-context/"):]
            try:
                if source_root is None or not relative or ".." in Path(relative).parts:
                    raise ValueError("external source is unavailable")
                source = source_root / relative
                if source.is_symlink():
                    raise ValueError("editable source is a symlink")
                resolved = source.resolve(strict=True)
                contained = os.path.commonpath([str(source_root), str(resolved)]) == str(source_root)
                raw = resolved.read_bytes() if contained and resolved.is_file() else b""
                current_revision = f"sha256:{hashlib.sha256(raw).hexdigest()}"
                if current_revision == value["document_revision"] and len(raw) <= args.max_bytes:
                    editable_content = raw.decode("utf-8")
                    editable = True
                    edit_target = relative
                    source_disclosure = str(source_root)
            except (OSError, UnicodeError, ValueError):
                pass
        response["document"] = {"document_id": value["document_id"], "source_reference": value["source_reference"], "source_scope": value["source_scope"], "lifecycle_state": value["lifecycle_state"], "title": value["title"], "document_revision": value["document_revision"], "byte_size": value["byte_size"], "returned_bytes": returned, "truncated": truncated, "passages": passages, "edit_capability": {"available": editable, "expected_revision": value["document_revision"] if editable else None, "exact_content": editable_content, "target": edit_target, "source_disclosure": source_disclosure}}
        return response, 0
    finally:
        connection.close()


def learning_candidates(project: Path, database: Path, identity: str, args: argparse.Namespace) -> tuple[dict[str, object], int]:
    freshness, reason, revision, diagnostics = index_status(project, database, identity)
    response = {"schema": "mana.learning.review-queue/v1", "index": {"freshness": freshness, "reason": reason, "revision": revision or None}, "candidates": [], "diagnostics": diagnostics}
    if freshness != "current":
        return response, 4
    candidate_root = project / ".mana" / "learning" / "candidates"
    for path in sorted(candidate_root.glob("*.json")) if candidate_root.is_dir() else []:
        if path.is_symlink() or path.stat().st_size > MAX_DOCUMENT_BYTES:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        status = value.get("status")
        if status not in args.lifecycle:
            continue
        raw = path.read_bytes()
        response["candidates"].append({"candidate_id": value.get("candidateId"), "source_scope": "project", "revision": f"sha256:{hashlib.sha256(raw).hexdigest()}", "status": status, "proposal": value.get("observation"), "evidence": value.get("evidenceReferences", []), "counter_evidence": value.get("counterEvidence"), "limitations": value.get("possibleImpact"), "target_scope": value.get("suggestedDestination"), "source_reference": path.relative_to(project).as_posix(), "review_id": None, "review_revision": None, "promotion_eligible": status == "reviewed", "promoted": False})
    state_base = Path(os.environ["MANA_USER_STATE_HOME"]) if os.environ.get("MANA_USER_STATE_HOME") else Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "mana"
    result = subprocess.run([str(ROOT / "scripts" / "mana-user-learning.sh"), "--project-root", str(project), "candidates", "--json"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0:
        try:
            user_candidates = json.loads(result.stdout).get("candidates", [])
        except json.JSONDecodeError:
            user_candidates = []
        for value in user_candidates:
            review_state = str(value.get("reviewState", "PENDING"))
            status = {"PENDING": "candidate", "ACCEPT": "reviewed", "EDIT_AND_ACCEPT": "reviewed", "REJECT": "rejected", "DEFER": "deferred"}.get(review_state, "candidate")
            if status not in args.lifecycle:
                continue
            candidate_id = value.get("candidateId")
            path = state_base / "user-learning" / "candidates" / f"{candidate_id}.json"
            if not isinstance(candidate_id, str) or not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_DOCUMENT_BYTES:
                continue
            raw = path.read_bytes()
            review_id = value.get("reviewId")
            review_revision = None
            if isinstance(review_id, str) and re.fullmatch(r"review-[0-9a-f]{64}", review_id):
                review_path = state_base / "user-learning" / "reviews" / f"{review_id}.json"
                if review_path.is_file() and not review_path.is_symlink() and review_path.stat().st_size <= MAX_DOCUMENT_BYTES:
                    review_revision = f"sha256:{hashlib.sha256(review_path.read_bytes()).hexdigest()}"
            eligible = review_state in {"ACCEPT", "EDIT_AND_ACCEPT"} and not bool(value.get("promoted")) and review_revision is not None
            response["candidates"].append({"candidate_id": candidate_id, "source_scope": "user", "revision": f"sha256:{hashlib.sha256(raw).hexdigest()}", "status": status, "proposal": value.get("guidance"), "evidence": value.get("sourceClusterIds", []), "counter_evidence": value.get("counterEvidence"), "limitations": value.get("limitations"), "target_scope": value.get("scope"), "source_reference": f"mana-user-state://user-learning/candidates/{candidate_id}", "review_id": review_id, "review_revision": review_revision, "promotion_eligible": eligible, "promoted": bool(value.get("promoted"))})
    response["candidates"].sort(key=lambda item: (item["source_scope"], item["candidate_id"] or ""))
    return response, 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--project-root", required=True, type=Path)
    commands = value.add_subparsers(dest="command", required=True)
    for name in ("status", "build", "capabilities"):
        child = commands.add_parser(name)
        child.add_argument("--json", action="store_true", required=True)
    search_parser = commands.add_parser("search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--scope", action="append", choices=sorted(SCOPES))
    search_parser.add_argument("--lifecycle", action="append", choices=sorted(LIFECYCLES))
    search_parser.add_argument("--limit", type=int, default=8)
    search_parser.add_argument("--max-bytes", type=int, default=8192)
    search_parser.add_argument("--metadata-only", action="store_true")
    search_parser.add_argument("--if-revision")
    search_parser.add_argument("--json", action="store_true", required=True)
    passage_parser = commands.add_parser("passage")
    passage_parser.add_argument("passage_id")
    passage_parser.add_argument("--max-bytes", type=int, default=8192)
    passage_parser.add_argument("--if-revision")
    passage_parser.add_argument("--json", action="store_true", required=True)
    documents_parser = commands.add_parser("documents")
    documents_parser.add_argument("--scope", action="append", choices=sorted(SCOPES))
    documents_parser.add_argument("--lifecycle", action="append", choices=sorted(LIFECYCLES))
    documents_parser.add_argument("--limit", type=int, default=50)
    documents_parser.add_argument("--offset", type=int, default=0)
    documents_parser.add_argument("--json", action="store_true", required=True)
    document_parser = commands.add_parser("document")
    document_parser.add_argument("document_id")
    document_parser.add_argument("--max-bytes", type=int, default=65_536)
    document_parser.add_argument("--if-revision")
    document_parser.add_argument("--json", action="store_true", required=True)
    learning_parser = commands.add_parser("learning-candidates")
    learning_parser.add_argument("--lifecycle", action="append", choices=sorted(LIFECYCLES))
    learning_parser.add_argument("--json", action="store_true", required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    project = args.project_root.resolve(strict=True)
    identity, database, lock_path = catalog.paths(project)
    if args.command == "status":
        freshness, reason, revision, diagnostics = index_status(project, database, identity)
        emit_status("status", freshness, reason, revision, diagnostics)
        return 0 if freshness in {"current", "missing", "stale"} else 4
    if args.command == "build":
        try:
            with catalog.lock(lock_path):
                result = build(project, database, identity)
            print(json.dumps({"schema": "mana.knowledge.index-build/v1", **result, "guarantees": {"model_calls": 0, "network_calls": 0, "canonical_writes": False}}, sort_keys=True))
            return 0
        except catalog.BusyError:
            emit_status("build", "stale", "catalog-builder-busy", "", [])
            return 6
        except (catalog.CatalogError, sqlite3.DatabaseError, OSError, UnicodeError, json.JSONDecodeError) as error:
            emit_status("build", "unsupported" if "fts5" in str(error) else "invalid", str(error), "", [])
            return 4
    if args.command == "capabilities":
        response, code = capabilities(project, database, identity)
        print(json.dumps(response, sort_keys=True))
        return code
    if args.command == "documents":
        args.scope = args.scope or ["framework", "user", "project", "candidate"]
        args.lifecycle = args.lifecycle or ["active"]
        if not 1 <= args.limit <= 200 or args.offset < 0:
            raise SystemExit("document list bounds are invalid")
        response, code = documents(project, database, identity, args)
        print(json.dumps(response, sort_keys=True))
        return code
    if args.command == "document":
        if not re.fullmatch(r"doc_[0-9a-f]{24}", args.document_id) or not 256 <= args.max_bytes <= 65_536:
            raise SystemExit("document request is invalid")
        response, code = document_detail(project, database, identity, args)
        print(json.dumps(response, sort_keys=True))
        return code
    if args.command == "learning-candidates":
        args.lifecycle = args.lifecycle or ["candidate", "reviewed", "rejected", "deferred"]
        response, code = learning_candidates(project, database, identity, args)
        print(json.dumps(response, sort_keys=True))
        return code
    if args.command == "search":
        args.scope = args.scope or ["framework", "user", "project"]
        args.lifecycle = args.lifecycle or ["active"]
        if not 1 <= args.limit <= 20 or not 256 <= args.max_bytes <= 65_536 or len(args.query.encode()) > 512:
            raise SystemExit("search bounds are invalid")
        response, code = search(project, database, identity, args)
    else:
        if not re.fullmatch(r"psg_[0-9a-f]{24}", args.passage_id) or not 256 <= args.max_bytes <= 65_536:
            raise SystemExit("passage request is invalid")
        response, code = passage(database, identity, project, args)
    print(json.dumps(response, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
