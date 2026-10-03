#!/usr/bin/env python3
"""Single-process, read-only catalog builder for mana-inspect v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def family(path: str) -> str:
    if path.startswith(".mana/global/"): return "service_context"
    if path.startswith((".mana/features/", ".mana/sessions/")): return "workspace"
    if path.startswith(".mana/runtime/"): return "runtime"
    if path.startswith(".mana/learning/candidates/"): return "learning"
    if path.startswith((".mana/learning/journeys/", ".mana/learning/requests/", ".mana/learning/unresolved-concepts/")): return "knowledge"
    if path.startswith((".mana/evaluations/", ".mana/reports/governance/")): return "governance"
    if path in {".mana/env", ".mana/jira-mcp.env"} or path.startswith(".mana/links/"): return "bootstrap"
    if path == ".mana/user-context-state" or path.startswith(".mana/user-context/"): return "user_context"
    return "unknown"


def classification(path: str) -> str:
    name = Path(path).name
    if "/derived/" in f"/{path}/" or name.endswith(".puml") or name in {"latest.json", "latest.md"}: return "derived"
    if path in {".mana/env"} or path.startswith(".mana/links/") or any(part.startswith(".") for part in Path(path).parts[1:]): return "ephemeral"
    return "canonical"


def kind(path: str) -> str:
    name = Path(path).name
    if name == "manifest.yaml": return "workspace_manifest"
    if name == "journey.yaml": return "journey"
    if "/records/" in path and name.endswith(".yaml") and "-" in name: return "journey_record"
    if "/events/" in path and name.endswith(".jsonl"): return "runtime_events"
    if "/sessions/" in path and name.endswith(".json"): return "runtime_session"
    if path.endswith("/evidence/index.md"): return "evidence_index"
    if path == ".mana/jira-mcp.env": return "restricted_configuration"
    return {".md": "markdown", ".json": "json", ".jsonl": "json_lines", ".yaml": "yaml", ".yml": "yaml"}.get(Path(path).suffix.lower(), "file")


def content_type(path: str) -> str:
    return {".json": "application/json", ".jsonl": "application/json", ".md": "text/markdown", ".yaml": "application/yaml", ".yml": "application/yaml", ".log": "text/plain", ".txt": "text/plain", ".puml": "text/plain"}.get(Path(path).suffix.lower(), "application/octet-stream")


def workspace(path: str) -> str | None:
    parts = path.split("/")
    if len(parts) >= 3 and parts[:2] == [".mana", "features"]: return f"feature:{parts[2]}"
    if len(parts) >= 3 and parts[:2] == [".mana", "sessions"]: return f"session:{parts[2]}"
    return None


def parsed_json(path: Path, relative: str) -> object | None:
    if Path(relative).suffix.lower() not in {".json", ".yaml", ".yml"}: return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def entry(root: Path, path: Path, relative: str) -> dict[str, object]:
    info = path.stat()
    parsed = parsed_json(path, relative)
    fam, cls, typ = family(relative), classification(relative), kind(relative)
    artifact = f"file:{relative}"
    status = "available"
    schema = {".md": "markdown", ".json": "json", ".jsonl": "jsonl", ".yaml": "yaml", ".yml": "yaml"}.get(Path(relative).suffix.lower(), "unknown")
    diagnostic = None
    if isinstance(parsed, dict):
        json_kind = parsed.get("kind", "")
        json_schema = parsed.get("schema", "")
        json_version = parsed.get("schemaVersion", "")
        json_id = parsed.get("runId") if json_kind == "verification-result" else parsed.get("attemptId") if json_kind == "repair-attempt-result" else parsed.get("loopId") if json_kind == "repair-loop-result" else parsed.get("executionId") or parsed.get("candidateId") or ""
        json_status = parsed.get("overallResult") or parsed.get("attemptStatus") or parsed.get("status") or "available"
        if json_kind in {"verification-result", "repair-attempt-result", "repair-loop-result", "user-context-candidate"}: typ = str(json_kind)
        schema = str(json_schema or (f"{json_kind}/v{json_version}" if json_kind or json_version else schema))
        if json_status in {"passed", "failed", "blocked", "partial", "inconclusive", "candidate", "reviewed", "rejected", "archived", "completed", "running", "available"}: status = str(json_status)
        if json_id:
            prefix = {"verification-result": "verification", "repair-attempt-result": "repair-attempt", "repair-loop-result": "repair-loop"}.get(str(json_kind), fam)
            artifact = f"{prefix}:{json_id}"
        if typ == "journey" and isinstance(parsed.get("id"), str) and re.fullmatch(r"jrn_[0-9a-f]{24}", parsed["id"]):
            artifact = f"journey:{parsed['id']}"
        elif typ == "journey_record" and isinstance(parsed.get("id"), str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*_[0-9a-f]{24}", parsed["id"]):
            artifact = f"journey-record:{parsed['id']}"
    else:
        if typ == "journey" or typ == "journey_record":
            pass
        if Path(relative).suffix.lower() in {".json", ".yaml", ".yml"} and not relative.endswith("/manifest.yaml"):
            fam = cls = typ = schema = "unknown"
            status, diagnostic = "malformed", "malformed_json_or_json_yaml"
    return {
        "artifact_id": artifact,
        "revision_id": f"sha256:{digest_file(path)}",
        "family": fam,
        "class": cls,
        "kind": typ,
        "path": relative,
        "schema": schema,
        "workspace": workspace(relative),
        "status": status,
        "updated_at": {"value": str(int(info.st_mtime)), "provenance": "filesystem_mtime_epoch"},
        "content_type": content_type(relative),
        "byte_size": info.st_size,
        "relations": [],
        "diagnostic": diagnostic,
    }


def catalog(root: Path) -> list[dict[str, object]]:
    mana = root / ".mana"
    if mana.is_symlink(): raise ValueError(".mana must not be a symlink")
    if not mana.exists(): return []
    if not mana.is_dir(): raise ValueError(".mana is not a directory")
    values: list[dict[str, object]] = []
    for directory, names, filenames in os.walk(mana, topdown=True, followlinks=False):
        base = Path(directory)
        names[:] = sorted(names)
        for name in sorted(filenames):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if name in {"latest.json", "latest.md"}: continue
            if path.is_symlink():
                target = os.readlink(path)
                values.append({"artifact_id": f"file:{relative}", "revision_id": f"sha256:{digest_bytes(target.encode())}", "family": "unknown", "class": "unknown", "kind": "unknown", "path": relative, "schema": "unknown", "workspace": None, "status": "quarantined", "updated_at": {"value": "unavailable", "provenance": "not_followed_symlink"}, "content_type": "inode/symlink", "byte_size": 0, "relations": [], "diagnostic": "symlink_not_followed"})
                continue
            try:
                info = path.stat()
                if stat.S_ISREG(info.st_mode): values.append(entry(root, path, relative))
            except OSError:
                continue
    values.sort(key=lambda item: (str(item["artifact_id"]), str(item["path"])))
    unique: list[dict[str, object]] = []
    index = 0
    while index < len(values):
        end = index + 1
        while end < len(values) and values[end]["artifact_id"] == values[index]["artifact_id"]: end += 1
        selected = dict(values[index])
        if end - index > 1:
            selected["status"] = "ambiguous"
            selected["diagnostic"] = "duplicate_artifact_id"
        unique.append(selected)
        index = end
    return unique


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        root = args.project_root.resolve(strict=True)
        print(json.dumps(catalog(root), separators=(",", ":"), ensure_ascii=False))
        return 0
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=os.sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
