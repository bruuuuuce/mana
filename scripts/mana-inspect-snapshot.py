#!/usr/bin/env python3
"""Produce project and semantic snapshots in one read-only Python process."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

# Loading sibling producers must not create a __pycache__ in the Mana checkout.
sys.dont_write_bytecode = True


def producer(name: str):
    path = Path(__file__).with_name(f"mana-inspect-{name}.py")
    spec = importlib.util.spec_from_file_location(f"mana_inspect_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.stdout.strip() if result.returncode == 0 else ""


def project(root: Path) -> dict:
    remote = git(root, "remote", "get-url", "origin")
    identity = f"remote:{remote}" if remote else f"root:{root.as_posix()}"
    active = root / ".mana" / "active-workspace"
    active_value = None
    if active.is_file() and not active.is_symlink():
        lines = active.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].startswith((".mana/features/", ".mana/sessions/")):
            active_value = lines[0]
    present = (root / ".mana").is_dir()
    names = ["project", "semantic-snapshot", "artifacts", "artifact", "source", "work-items", "work-item", "project-context", "activity"]
    return {
        "schema": "mana.inspect.project/v1",
        "project_id": "project:" + hashlib.sha256(identity.encode()).hexdigest(),
        "framework": {"version": "0.4.1", "compatibility": "mana-inspect/v1"},
        "mana": {"present": present, "active_workspace": active_value},
        "git": {"branch": git(root, "rev-parse", "--abbrev-ref", "HEAD") or "unavailable", "head": git(root, "rev-parse", "HEAD") or "unavailable", "working_tree_dirty": bool(git(root, "status", "--porcelain", "--untracked-files=normal"))},
        "capabilities": ["workspace", "artifact_catalog", "artifact_detail", "source_relations", "semantic_work_items", "semantic_project_context", "semantic_activity", "semantic_snapshot"] if present else [],
        "operations": [{"name": name, "schema": f"mana.inspect.{name}/v1"} for name in names],
        "guarantees": {"model_calls": 0, "writes": False, "paths": "project_relative_only"}, "diagnostics": [],
    }


def snapshot(root: Path, include_supporting: bool) -> dict:
    inventory = producer("catalog").catalog(root)
    semantic = producer("semantic")
    not_requested = {"status": "not_requested", "value": None, "diagnostic": None}
    projections = {"work_items": {"status": "available", "value": semantic.work_items(root, inventory), "diagnostic": None}, "project_context": dict(not_requested), "activity": dict(not_requested), "artifacts": dict(not_requested)}
    if include_supporting:
        for name, projection in (("project_context", lambda: semantic.project_context(root, inventory)), ("activity", lambda: semantic.activity(root, inventory, 10000))):
            try:
                projections[name] = {"status": "available", "value": projection(), "diagnostic": None}
            except OverflowError:
                projections[name] = {"status": "unavailable", "value": None, "diagnostic": {"code": f"{name}_projection_failed"}}
    semantic_inventory = [{key: value for key, value in entry.items() if key != "updated_at"} for entry in inventory]
    canonical = json.dumps(semantic_inventory, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "schema": "mana.inspect.semantic-snapshot/v1", "snapshot_revision": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "inventory": {"catalog_build_count": 1, "file_count": len(inventory), "admitted_bytes": sum(entry["byte_size"] for entry in inventory)},
        "project": project(root), "projections": projections,
        "guarantees": {"model_calls": 0, "network_calls": 0, "writes": False, "paths": "project_relative_only"}, "diagnostics": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("operation", choices=("project", "semantic-snapshot"))
    parser.add_argument("--include-supporting", action="store_true")
    args = parser.parse_args()
    try:
        root = args.project_root.resolve(strict=True)
        if (root / ".mana").is_symlink(): raise ValueError(".mana must not be a symlink")
        response = project(root) if args.operation == "project" else snapshot(root, args.include_supporting)
        print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
