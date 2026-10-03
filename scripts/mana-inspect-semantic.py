#!/usr/bin/env python3
"""Single-process semantic projections over one immutable Inspect inventory."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


PROVENANCE_MANIFEST = "explicit_workspace_manifest"


def scalar(path: Path, key: str) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
            if match:
                return match.group(1).strip().strip('"')
    except (OSError, UnicodeError):
        pass
    return ""


def label(path: Path, relative: str) -> str | None:
    if not relative.endswith(".md") or path.is_symlink() or not path.is_file(): return None
    try:
        raw = path.read_bytes()[:8192]
        if b"\0" in raw: return None
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        return None
    fence = ""
    for index, line in enumerate(text.splitlines()):
        if index >= 64: break
        if line.startswith("```"):
            fence = "" if fence == "backtick" else "backtick" if not fence else fence
            continue
        if line.startswith("~~~"):
            fence = "" if fence == "tilde" else "tilde" if not fence else fence
            continue
        if not fence and re.match(r"^#\s+", line):
            value = re.sub(r"\s+#+\s*$", "", re.sub(r"^#\s+", "", line)).strip()
            value = re.sub(r"\s+", " ", value)
            return value if 0 < len(value) <= 256 else None
    return None


def section(relative: str, kind: str, identifier: str) -> str:
    base = f".mana/{kind}s/{identifier}"
    if relative == f"{base}/index.md": return "overview"
    if relative in {f"{base}/context/story-context.md", f"{base}/context/epic-goal-contract.md", f"{base}/context/open-questions.md"}: return "requirements"
    if relative.startswith(f"{base}/planning/"): return "plan"
    if relative.startswith(f"{base}/decisions/"): return "decisions"
    if relative.startswith((f"{base}/evidence/", f"{base}/tests/", f"{base}/validation/")): return "evidence"
    if relative.startswith(f"{base}/pr/"): return "review"
    if relative == f"{base}/agent-memory/story-trace.md": return "timeline"
    return "artifacts"


def active_id(root: Path) -> str | None:
    path = root / ".mana" / "active-workspace"
    if not path.is_file() or path.is_symlink(): return None
    try: value = path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, UnicodeError, IndexError): return None
    match = re.fullmatch(r"\.mana/(features|sessions)/([A-Za-z0-9][A-Za-z0-9._-]*)", value)
    if not match: return None
    return f"{'feature' if match.group(1) == 'features' else 'session'}:{match.group(2)}"


def work_items(root: Path, entries: list[dict[str, object]]) -> dict[str, object]:
    by_workspace: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        workspace = entry.get("workspace")
        if isinstance(workspace, str): by_workspace.setdefault(workspace, []).append(entry)
    active = active_id(root)
    values: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    for kind, plural in (("feature", "features"), ("session", "sessions")):
        directory = root / ".mana" / plural
        if not directory.is_dir() or directory.is_symlink(): continue
        for workspace_dir in sorted((path for path in directory.iterdir() if path.is_dir() and not path.is_symlink()), key=lambda path: path.name):
            identifier = workspace_dir.name
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier): continue
            wid = f"{kind}:{identifier}"
            manifest = workspace_dir / "manifest.yaml"
            item_diagnostics: list[dict[str, object]] = []
            branch = purpose = feature = ""
            canonical: bool | None = None
            if manifest.is_file() and not manifest.is_symlink():
                if scalar(manifest, "workspace_type") != kind or scalar(manifest, "workspace_id") != identifier:
                    item_diagnostics.append({"id": "manifest-identity", "kind": "malformed_canonical_source", "severity": "warning", "provenance": "canonical_path", "related_artifact_ids": []})
                branch, purpose, feature = scalar(manifest, "branch"), scalar(manifest, "purpose"), scalar(manifest, "feature_id")
                canonical_value = scalar(manifest, "canonical_branch")
                canonical = True if canonical_value == "true" else False if canonical_value == "false" else None
            else:
                item_diagnostics.append({"id": "manifest-unavailable", "kind": "unavailable_source", "severity": "warning", "provenance": "canonical_path", "related_artifact_ids": []})
            artifacts = []
            for entry in by_workspace.get(wid, []):
                if entry.get("class") == "ephemeral" or entry.get("status") == "quarantined": continue
                relative = str(entry["path"])
                artifacts.append({"artifact_id": entry["artifact_id"], "path": relative, "kind": entry["kind"], "status": entry["status"], "work_item_id": wid, "section_id": section(relative, kind, identifier), "label": label(root / relative, relative)})
            artifacts.sort(key=lambda item: (str(item["artifact_id"]), str(item["path"])))
            lifecycle = {"state": "unknown", "provenance": "unavailable", "coverage": "unknown"}
            if active == wid: lifecycle = {"state": "in_progress", "provenance": "canonical_path", "coverage": "explicit_structured_only"}
            if any(item["status"] == "failed" for item in artifacts): lifecycle = {"state": "failed", "provenance": PROVENANCE_MANIFEST, "coverage": "explicit_structured_only"}
            if any(item["status"] == "blocked" for item in artifacts): lifecycle = {"state": "blocked", "provenance": PROVENANCE_MANIFEST, "coverage": "explicit_structured_only"}
            attention = [{"id": f"failed-verification:{item['artifact_id']}", "category": "failed_verification", "severity": "error", "work_item_id": wid, "label": None, "next_action": None, "related_artifact_ids": [item["artifact_id"]], "provenance": PROVENANCE_MANIFEST} for item in artifacts if item["status"] == "failed"]
            for item in artifacts:
                if not str(item["path"]).endswith(".json"): continue
                try: stale = json.loads((root / str(item["path"])).read_text(encoding="utf-8")).get("staleness") == "stale"
                except (OSError, UnicodeError, json.JSONDecodeError, AttributeError): stale = False
                if stale: attention.append({"id": f"stale-evidence:{item['artifact_id']}", "category": "stale_evidence", "severity": "warning", "work_item_id": wid, "label": None, "next_action": None, "related_artifact_ids": [item["artifact_id"]], "provenance": PROVENANCE_MANIFEST})
            choice_log = workspace_dir / "decisions" / "developer-choice-log.md"
            try: pending = not choice_log.is_symlink() and "| needs_owner_review |" in choice_log.read_text(encoding="utf-8")
            except (OSError, UnicodeError): pending = False
            if pending: attention.append({"id": "pending-decision:developer-choice-log", "category": "pending_decision", "severity": "warning", "work_item_id": wid, "label": None, "next_action": None, "related_artifact_ids": [f"file:.mana/{plural}/{identifier}/decisions/developer-choice-log.md"], "provenance": "conservative_fallback"})
            unavailable = {"value": None, "provenance": "unavailable"}
            values.append({"work_item_id": wid, "work_item_type": kind, "external_ticket_id": {"value": feature or None, "provenance": PROVENANCE_MANIFEST if feature else "unavailable"}, "title": unavailable, "purpose": {"value": purpose or None, "provenance": PROVENANCE_MANIFEST if purpose else "unavailable"}, "branch": {"value": branch or None, "provenance": PROVENANCE_MANIFEST if branch else "unavailable"}, "canonical_branch": canonical, "lifecycle": lifecycle, "review": {"state": "unknown", "provenance": "unavailable", "coverage": "unknown"}, "attention_items": attention, "artifacts": artifacts})
            diagnostics.extend(item_diagnostics)
    values.sort(key=lambda item: str(item["work_item_id"]))
    return {"schema": "mana.inspect.work-items/v1", "work_items": values, "coverage": "canonical_workspace_manifests" if values else "none", "diagnostics": diagnostics, "guarantees": {"model_calls": 0, "writes": False, "semantic_inference": "canonical_structured_sources_only"}}


CONTEXT = {
    "architecture": (".mana/global/architecture.md", False),
    "project_decisions": (".mana/global/team-decisions/", True),
    "integrations": (".mana/global/integration-map.md", False),
    "engineering_guards": (".mana/global/engineering-guards.md", False),
    "glossary": (".mana/global/domain-glossary.md", False),
    "learning_journeys": (".mana/learning/journeys/", True),
    "testing_policy": (".mana/global/testing-policy.md", False),
    "database_policy": (".mana/global/database-policy.md", False),
}


def reference(root: Path, entry: dict[str, object], *, workspace_id: str | None = None, section_id: str | None = None) -> dict[str, object]:
    relative = str(entry["path"])
    return {"artifact_id": entry["artifact_id"], "path": relative, "kind": entry["kind"], "status": entry["status"], "work_item_id": workspace_id, "section_id": section_id, "label": label(root / relative, relative)}


def context_categories(root: Path, entries: list[dict[str, object]]) -> list[dict[str, object]]:
    categories = []
    for category, (selector, prefix) in CONTEXT.items():
        artifacts = [reference(root, entry) for entry in entries if entry.get("status") != "quarantined" and entry.get("class") != "ephemeral" and (str(entry["path"]).startswith(selector) if prefix else entry["path"] == selector)]
        artifacts.sort(key=lambda item: (str(item["artifact_id"]), str(item["path"])))
        categories.append({"category": category, "artifacts": artifacts, "coverage": "canonical_path_category" if artifacts else "missing"})
    return categories


def project_context(root: Path, entries: list[dict[str, object]]) -> dict[str, object]:
    categories = context_categories(root, entries)
    return {"schema": "mana.inspect.project-context/v1", "categories": categories, "coverage": "canonical_global_context" if any(item["artifacts"] for item in categories) else "none", "diagnostics": [], "guarantees": {"model_calls": 0, "writes": False, "semantic_inference": "canonical_structured_sources_only"}}


def iso_epoch(value: object) -> float | None:
    if not isinstance(value, str) or not value.endswith("Z"): return None
    try: return datetime.fromisoformat(value[:-1] + "+00:00").timestamp()
    except ValueError: return None


def activity(root: Path, entries: list[dict[str, object]], maximum_events: int | None) -> dict[str, object]:
    targets: dict[str, dict[str, object]] = {}
    for entry in entries:
        wid = entry.get("workspace")
        if isinstance(wid, str) and entry.get("class") != "ephemeral" and entry.get("status") != "quarantined":
            kind, identifier = wid.split(":", 1)
            ref = reference(root, entry, workspace_id=wid, section_id=section(str(entry["path"]), kind, identifier))
            targets[str(entry["artifact_id"])] = {"artifact_id": ref["artifact_id"], "work_item_id": ref["work_item_id"], "section_id": ref["section_id"], "project_context_category": None, "label": ref["label"]}
    for category in context_categories(root, entries):
        for item in category["artifacts"]:
            targets[str(item["artifact_id"])] = {"artifact_id": item["artifact_id"], "work_item_id": None, "section_id": None, "project_context_category": category["category"], "label": item["label"]}
    for entry in entries:
        targets.setdefault(str(entry["artifact_id"]), {"artifact_id": entry["artifact_id"], "work_item_id": entry.get("workspace"), "section_id": None, "project_context_category": None, "label": None})
    events: list[dict[str, object]] = []
    by_path = {str(entry["path"]): entry for entry in entries}
    runtime = root / ".mana" / "runtime" / "events"
    for path in sorted(runtime.glob("*.jsonl")) if runtime.is_dir() else []:
        relative = path.relative_to(root).as_posix()
        entry = by_path.get(relative)
        if entry is None: continue
        try: lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError): continue
        for line in lines:
            try: value = json.loads(line)
            except json.JSONDecodeError: continue
            if not isinstance(value, dict) or not isinstance(value.get("eventId"), str) or iso_epoch(value.get("timestamp")) is None: continue
            events.append({"event_id": value["eventId"], "timestamp": {"value": value["timestamp"], "provenance": "explicit_domain_timestamp"}, "event_kind": "unknown", "work_item_id": entry.get("workspace"), "related_artifact_ids": [entry["artifact_id"]], "target": targets[str(entry["artifact_id"])], "summary": None, "provenance": "explicit_workspace_manifest"})
            if maximum_events is not None and len(events) > maximum_events: raise OverflowError("activity_projection_exceeds_snapshot_budget")
    for entry in entries:
        if not str(entry["path"]).endswith(".json"): continue
        try: value = json.loads((root / str(entry["path"])).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError): continue
        if not isinstance(value, dict) or value.get("kind") != "verification-result": continue
        timestamp = value.get("generatedAt") or value.get("finishedAt")
        if iso_epoch(timestamp) is None: continue
        events.append({"event_id": f"verification:{entry['artifact_id']}", "timestamp": {"value": timestamp, "provenance": "explicit_domain_timestamp"}, "event_kind": "verification_completed", "work_item_id": entry.get("workspace"), "related_artifact_ids": [entry["artifact_id"]], "target": targets[str(entry["artifact_id"])], "summary": None, "provenance": "explicit_workspace_manifest"})
    for entry in entries:
        updated = entry.get("updated_at", {})
        value = updated.get("value") if isinstance(updated, dict) else None
        if not isinstance(value, str) or not value.isdigit(): continue
        events.append({"event_id": f"artifact-update:{entry['artifact_id']}", "timestamp": {"value": value, "provenance": "filesystem_mtime_epoch"}, "event_kind": "artifact_updated", "work_item_id": entry.get("workspace"), "related_artifact_ids": [entry["artifact_id"]], "target": targets[str(entry["artifact_id"])], "summary": None, "provenance": "conservative_fallback"})
        if maximum_events is not None and len(events) > maximum_events: raise OverflowError("activity_projection_exceeds_snapshot_budget")
    unique = {str(event["event_id"]): event for event in events}
    ordered = sorted(unique.values(), key=lambda event: (iso_epoch(event["timestamp"]["value"]) if event["timestamp"]["provenance"] == "explicit_domain_timestamp" else int(event["timestamp"]["value"]), str(event["event_id"])))
    coverage = "none" if not ordered else "explicit_and_filesystem_fallback" if any(event["timestamp"]["provenance"] == "filesystem_mtime_epoch" for event in ordered) else "explicit_structured_events"
    return {"schema": "mana.inspect.activity/v1", "events": ordered, "coverage": coverage, "diagnostics": [], "guarantees": {"model_calls": 0, "writes": False, "semantic_inference": "canonical_structured_sources_only"}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("operation", choices=("work-items", "project-context", "activity"))
    parser.add_argument("--max-events", type=int)
    args = parser.parse_args()
    root = args.project_root.resolve(strict=True)
    entries = json.load(sys.stdin)
    if not isinstance(entries, list): raise SystemExit("inventory must be an array")
    try:
        response = work_items(root, entries) if args.operation == "work-items" else project_context(root, entries) if args.operation == "project-context" else activity(root, entries, args.max_events)
        print(json.dumps(response, separators=(",", ":"), ensure_ascii=False))
        return 0
    except OverflowError as error:
        print(str(error), file=sys.stderr)
        return 8


if __name__ == "__main__":
    raise SystemExit(main())
