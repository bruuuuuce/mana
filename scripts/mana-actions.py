#!/usr/bin/env python3
"""M08-D optimistic-concurrency action adapters with structured receipts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location("mana_catalog", ROOT / "scripts" / "mana-catalog.py")
assert module_spec and module_spec.loader
catalog = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(catalog)


def sha(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def safe_relative(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def action_id(payload: dict) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"act_{hashlib.sha256(encoded).hexdigest()[:24]}"


def cache_uri(kind: str, identifier: str) -> str:
    return f"mana-cache://actions/{kind}/{identifier}.json"


def existing_receipt(identifier: str) -> tuple[dict, int] | None:
    path = catalog.cache_root() / "actions" / "receipts" / f"{identifier}.json"
    if not path.is_file() or path.is_symlink():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    codes = {"applied": 0, "noop": 0, "conflict": 7, "validation_failure": 2, "partial_refresh": 3}
    return value, codes.get(value.get("outcome"), 4)


def persist(kind: str, identifier: str, value: dict) -> str:
    directory = catalog.cache_root() / "actions" / kind
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{identifier}.json"
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if target.exists():
        if target.read_text(encoding="utf-8") != encoded:
            raise RuntimeError("action artifact identity collision")
    else:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{identifier}.", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return cache_uri(kind, identifier)


def receipt(identifier: str, action: str, target: dict, expected: str, before: str | None, after: str | None, outcome: str, *, proposal: str | None = None, details: dict | None = None) -> dict:
    value = {"schema": "mana.action.receipt/v1", "action_id": identifier, "action": action, "target": target, "expected_revision": expected, "before_revision": before, "after_revision": after, "outcome": outcome, "proposal_artifact": proposal, "details": details or {}, "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "guarantees": {"model_calls": 0, "network_calls": 0, "automatic_promotion": False}, "receipt_artifact": cache_uri("receipts", identifier)}
    canonical = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    value["receipt_revision"] = sha(canonical)
    persist("receipts", identifier, value)
    return value


def conflict(identifier: str, action: str, target: dict, expected: str, current: str, proposed: dict) -> tuple[dict, int]:
    proposal_value = {"schema": "mana.action.conflict-proposal/v1", "action_id": identifier, "target": target, "expected_revision": expected, "current_revision": current, **proposed}
    artifact = persist("conflicts", identifier, proposal_value)
    return receipt(identifier, action, target, expected, current, current, "conflict", proposal=artifact), 7


def atomic_write(target: Path, content: bytes) -> None:
    mode = target.stat().st_mode & 0o777
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def configured_user_source(project: Path) -> Path:
    result = subprocess.run(catalog.shell_command(ROOT / "scripts" / "mana-context.sh", ["path", "--source", "--project-root", str(project)]), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise ValueError("configured User Context source is unavailable")
    return Path(result.stdout.strip()).resolve(strict=True)


def knowledge_edit(project: Path, args: argparse.Namespace) -> tuple[dict, int]:
    if not safe_relative(args.target) or Path(args.target).suffix.lower() not in {".md", ".markdown", ".txt", ".rst", ".adoc"}:
        raise ValueError("knowledge target is unsafe or unsupported")
    content = args.content_file.read_bytes()
    if not content or len(content) > 65_536 or b"\x00" in content:
        raise ValueError("knowledge payload must be 1-65536 textual bytes")
    content.decode("utf-8")
    proposed_revision = sha(content)
    target_info = {"scope": args.scope, "reference": args.target}
    identity = {"action": "knowledge-edit", "target": target_info, "expected_revision": args.expected_revision, "proposed_revision": proposed_revision}
    identifier = action_id(identity)
    existing = existing_receipt(identifier)
    if existing:
        return existing
    if args.scope == "framework":
        return receipt(identifier, "knowledge-edit", target_info, args.expected_revision, None, None, "validation_failure", details={"code": "framework_scope_read_only"}), 2
    if args.scope == "project":
        if not args.target.startswith(".mana/global/"):
            raise ValueError("project knowledge edits are confined to .mana/global")
        target = project / args.target
    else:
        source = configured_user_source(project)
        if not args.confirm_user_source or Path(args.confirm_user_source).resolve() != source:
            return receipt(identifier, "knowledge-edit", target_info, args.expected_revision, None, None, "validation_failure", details={"code": "user_source_confirmation_required"}), 2
        target = source / args.target
        if os.path.commonpath([str(source), str(target.resolve(strict=False))]) != str(source):
            raise ValueError("user knowledge target escapes the configured source")
    if not target.is_file() or target.is_symlink():
        return receipt(identifier, "knowledge-edit", target_info, args.expected_revision, None, None, "validation_failure", details={"code": "target_unavailable"}), 2
    current = sha(target.read_bytes())
    if current != args.expected_revision:
        return conflict(identifier, "knowledge-edit", target_info, args.expected_revision, current, {"proposed_revision": proposed_revision, "proposed_content": content.decode("utf-8")})
    if current == proposed_revision:
        return receipt(identifier, "knowledge-edit", target_info, args.expected_revision, current, current, "noop"), 0
    atomic_write(target, content)
    after = sha(target.read_bytes())
    if args.scope == "user":
        refresh = subprocess.run(catalog.shell_command(ROOT / "scripts" / "mana-context.sh", ["refresh", "--json", "--project-root", str(project)]), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        outcome = "applied" if refresh.returncode == 0 else "partial_refresh"
        details = {"source_published": True, "mirror_refreshed": refresh.returncode == 0}
        return receipt(identifier, "knowledge-edit", target_info, args.expected_revision, current, after, outcome, details=details), 0 if refresh.returncode == 0 else 3
    return receipt(identifier, "knowledge-edit", target_info, args.expected_revision, current, after, "applied"), 0


def project_learning(project: Path, args: argparse.Namespace) -> tuple[dict, int]:
    if not re.fullmatch(r"learning-[0-9a-f]{8}", args.candidate_id):
        raise ValueError("project candidate ID is malformed")
    target = project / ".mana" / "learning" / "candidates" / f"{args.candidate_id}.json"
    target_info = {"scope": "candidate", "candidate_id": args.candidate_id}
    identifier = action_id({"action": "project-learning", "target": target_info, "expected_revision": args.expected_revision, "disposition": args.disposition})
    existing = existing_receipt(identifier)
    if existing:
        return existing
    if not target.is_file() or target.is_symlink():
        return receipt(identifier, "project-learning", target_info, args.expected_revision, None, None, "validation_failure", details={"code": "candidate_unavailable"}), 2
    current = sha(target.read_bytes())
    if current != args.expected_revision:
        return conflict(identifier, "project-learning", target_info, args.expected_revision, current, {"proposed_disposition": args.disposition})
    command = {"review": "review", "reject": "reject", "archive": "archive"}[args.disposition]
    result = subprocess.run(catalog.shell_command(ROOT / "scripts" / "mana-learning.sh", ["--project-root", str(project), command, args.candidate_id, "--json"]), cwd=project, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        return receipt(identifier, "project-learning", target_info, args.expected_revision, current, current, "validation_failure", details={"code": "producer_rejected_transition"}), 2
    after = sha(target.read_bytes())
    return receipt(identifier, "project-learning", target_info, args.expected_revision, current, after, "applied", details={"disposition": args.disposition, "promotion_performed": False}), 0


def user_state_root() -> Path:
    if os.environ.get("MANA_USER_STATE_HOME"):
        return Path(os.environ["MANA_USER_STATE_HOME"])
    if os.environ.get("XDG_STATE_HOME"):
        return Path(os.environ["XDG_STATE_HOME"]) / "mana"
    return Path.home() / ".local" / "state" / "mana"


def user_learning(project: Path, args: argparse.Namespace) -> tuple[dict, int]:
    if not re.fullmatch(r"user-context-candidate-[0-9a-f]{64}", args.candidate_id):
        raise ValueError("user candidate ID is malformed")
    target = user_state_root() / "user-learning" / "candidates" / f"{args.candidate_id}.json"
    target_info = {"scope": "user", "candidate_id": args.candidate_id}
    identifier = action_id({"action": "user-learning-review", "target": target_info, "expected_revision": args.expected_revision, "disposition": args.disposition, "guidance": args.guidance, "review_scope": args.review_scope})
    existing = existing_receipt(identifier)
    if existing:
        return existing
    if not target.is_file() or target.is_symlink():
        return receipt(identifier, "user-learning-review", target_info, args.expected_revision, None, None, "validation_failure", details={"code": "candidate_unavailable"}), 2
    current = sha(target.read_bytes())
    if current != args.expected_revision:
        return conflict(identifier, "user-learning-review", target_info, args.expected_revision, current, {"proposed_disposition": args.disposition})
    flags = {"accept": ["--accept"], "reject": ["--reject"], "defer": ["--defer"], "edit-and-accept": ["--edit", args.guidance, "--scope", args.review_scope]}[args.disposition]
    result = subprocess.run(catalog.shell_command(ROOT / "scripts" / "mana-user-learning.sh", ["--project-root", str(project), "review", args.candidate_id, *flags, "--json"]), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        return receipt(identifier, "user-learning-review", target_info, args.expected_revision, current, current, "validation_failure", details={"code": "producer_rejected_transition"}), 2
    value = json.loads(result.stdout)
    return receipt(identifier, "user-learning-review", target_info, args.expected_revision, current, current, "applied", details={"review_id": value["review"]["reviewId"], "promotion_required": value["promotionRequired"], "promotion_performed": False}), 0


def user_learning_promote(project: Path, args: argparse.Namespace) -> tuple[dict, int]:
    if not re.fullmatch(r"review-[0-9a-f]{64}", args.review_id):
        raise ValueError("user review ID is malformed")
    target = user_state_root() / "user-learning" / "reviews" / f"{args.review_id}.json"
    target_info = {"scope": "user", "review_id": args.review_id}
    identifier = action_id({"action": "user-learning-promote", "target": target_info, "expected_revision": args.expected_revision})
    existing = existing_receipt(identifier)
    if existing:
        return existing
    if not target.is_file() or target.is_symlink():
        return receipt(identifier, "user-learning-promote", target_info, args.expected_revision, None, None, "validation_failure", details={"code": "review_unavailable"}), 2
    current = sha(target.read_bytes())
    if current != args.expected_revision:
        return conflict(identifier, "user-learning-promote", target_info, args.expected_revision, current, {"proposed_action": "promote"})
    result = subprocess.run(catalog.shell_command(ROOT / "scripts" / "mana-user-learning.sh", ["--project-root", str(project), "promote", args.review_id, "--json"]), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode not in {0, 3}:
        return receipt(identifier, "user-learning-promote", target_info, args.expected_revision, current, current, "validation_failure", details={"code": "producer_rejected_transition"}), 2
    value = json.loads(result.stdout)
    promotion = value.get("promotion", {})
    outcome = "applied" if result.returncode == 0 else "partial_refresh"
    details = {"promotion_status": promotion.get("status"), "entry_id": promotion.get("entryId"), "refresh_succeeded": value.get("refreshSucceeded"), "explicit_promotion": True}
    return receipt(identifier, "user-learning-promote", target_info, args.expected_revision, current, current, outcome, details=details), result.returncode


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--project-root", required=True, type=Path)
    commands = value.add_subparsers(dest="command", required=True)
    edit = commands.add_parser("knowledge-edit")
    edit.add_argument("--scope", required=True, choices=("framework", "user", "project"))
    edit.add_argument("--target", required=True)
    edit.add_argument("--expected-revision", required=True)
    edit.add_argument("--content-file", required=True, type=Path)
    edit.add_argument("--confirm-user-source")
    edit.add_argument("--json", action="store_true", required=True)
    local = commands.add_parser("project-learning")
    local.add_argument("--candidate-id", required=True)
    local.add_argument("--expected-revision", required=True)
    local.add_argument("--disposition", required=True, choices=("review", "reject", "archive"))
    local.add_argument("--json", action="store_true", required=True)
    user = commands.add_parser("user-learning")
    user.add_argument("--candidate-id", required=True)
    user.add_argument("--expected-revision", required=True)
    user.add_argument("--disposition", required=True, choices=("accept", "edit-and-accept", "reject", "defer"))
    user.add_argument("--guidance", default="")
    user.add_argument("--review-scope", default="")
    user.add_argument("--json", action="store_true", required=True)
    promote = commands.add_parser("user-learning-promote")
    promote.add_argument("--review-id", required=True)
    promote.add_argument("--expected-revision", required=True)
    promote.add_argument("--json", action="store_true", required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.expected_revision):
        raise SystemExit("expected revision is malformed")
    project = args.project_root.resolve(strict=True)
    try:
        if args.command == "knowledge-edit":
            response, code = knowledge_edit(project, args)
        elif args.command == "project-learning":
            response, code = project_learning(project, args)
        elif args.command == "user-learning":
            if args.disposition == "edit-and-accept" and (not args.guidance or not args.review_scope):
                raise ValueError("edit-and-accept requires guidance and review scope")
            if args.disposition != "edit-and-accept" and (args.guidance or args.review_scope):
                raise ValueError("guidance and review scope are valid only for edit-and-accept")
            response, code = user_learning(project, args)
        else:
            response, code = user_learning_promote(project, args)
    except (ValueError, UnicodeError, OSError, RuntimeError) as error:
        print(json.dumps({"schema": "mana.action.error/v1", "outcome": "validation_failure", "code": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(response, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
