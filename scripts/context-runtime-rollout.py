#!/usr/bin/env python3
"""CTX-10 local rollout policy and versioned managed-block boundary.

This tool deliberately has no provider, network, environment-policy, or model
surface.  It is the host-owned boundary used by bootstrap, doctor and inspect.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

sys.dont_write_bytecode = True
VERSION = 2
POLICY_VERSION = "mana.context-runtime.rollout-policy/v1"
DECISION_VERSION = "mana.context-runtime.rollout-decision/v1"
POLICY_SNAPSHOT_VERSION = "mana.context-runtime.rollout-policy-snapshot/v1"
DECISION_RECEIPT_VERSION = "mana.context-runtime.rollout-decision-receipt/v1"
DECISION_BUNDLE_VERSION = "mana.context-runtime.rollout-decision-bundle/v1"
DECISION_HEAD_VERSION = "mana.context-runtime.rollout-decision-head/v1"
DECISION_HEAD_COMMIT_VERSION = "mana.context-runtime.rollout-decision-head-commit/v1"
INTENT_VERSION = "mana.context-runtime.execution-intent/v1"
INTENT_COMMIT_VERSION = "mana.context-runtime.execution-intent-commit/v1"
SELECTION_COMMIT_VERSION = "mana.context-runtime.rollout-decision-commitment/v1"
POLICY_RELATIVE = ".mana/context-runtime/runtime-selection-v1.json"
LOCK_RELATIVE = ".mana/context-runtime/.rollout-publication.lock"
MAX_BYTES = 256 * 1024
MODES = {"inherited", "legacy", "shadow", "v2", "compare"}
# This is a deliberately small, line-oriented grammar.  A marker is a whole
# line, has one of these exact prefixes, and has no optional attributes.
BEGIN = re.compile(r"^(?P<prefix># |// |)mana:context-runtime:begin version=(?P<version>[0-9]+) id=(?P<id>[A-Za-z0-9._-]{1,80}) digest=(?P<digest>[0-9a-f]{64})$")
END = re.compile(r"^(?P<prefix># |// |)mana:context-runtime:end id=(?P<id>[A-Za-z0-9._-]{1,80})$")
MARKER_STEM = re.compile(r"^(?:# |// |)mana:context-runtime:(?:begin|end)(?:\s|$)")


class RolloutError(RuntimeError):
    pass


class ConcurrentRolloutUpdate(RolloutError):
    pass


class DecisionAuthorityError(RolloutError):
    """A materialized decision no longer matches its host-owned commitment."""


def _decision_authority_error() -> DecisionAuthorityError:
    return DecisionAuthorityError(
        "CTX10_DECISION_AUTHORITY_REJECTED: materialized rollout decision authority rejected"
    )


_CTX03 = None
_PIPELINE = None
_CTX09_MODE = None
_CTX09_COMPARISON = None
# Import-only fault injection for the permanent crash/recovery matrix.  There
# is deliberately no CLI or environment surface for these points.
_TEST_DECISION_HOOK = None


def _runtime_module():
    global _CTX03
    if _CTX03 is not None:
        return _CTX03
    source = Path(__file__).with_name("lib") / "context-runtime.py"
    spec = importlib.util.spec_from_file_location("mana_ctx03", source)
    if spec is None or spec.loader is None:
        raise RolloutError("CTX-03 boundary is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _CTX03 = module
    return _CTX03


def _pipeline_module():
    """Load the CTX-06/07 authoritative reader without invoking a runner."""
    global _PIPELINE
    if _PIPELINE is not None:
        return _PIPELINE
    source = Path(__file__).with_name("lib") / "context-pipeline.py"
    spec = importlib.util.spec_from_file_location("mana_ctx06_inspect", source)
    if spec is None or spec.loader is None:
        raise RolloutError("CTX-06 validation boundary is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _PIPELINE = module
    return _PIPELINE


def _ctx09_mode_module():
    """The CTX-09 producer reader is the only receipt authority."""
    global _CTX09_MODE
    if _CTX09_MODE is None:
        source = Path(__file__).with_name("context-runtime-mode.py")
        spec = importlib.util.spec_from_file_location("mana_ctx09_mode_inspect", source)
        if spec is None or spec.loader is None:
            raise RolloutError("CTX-09 producer authority is unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _CTX09_MODE = module
    return _CTX09_MODE


def _ctx09_comparison_module():
    """Load CTX-09B's canonical registration/report reader, never a copy."""
    global _CTX09_COMPARISON
    if _CTX09_COMPARISON is None:
        # The comparison module imports the mode reader itself.  Give it the
        # same fixed import name it uses in production rather than accepting a
        # caller supplied implementation or path.
        source = Path(__file__).with_name("lib") / "context-comparison.py"
        spec = importlib.util.spec_from_file_location("mana_ctx09_comparison_inspect", source)
        if spec is None or spec.loader is None:
            raise RolloutError("CTX-09 comparison authority is unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _CTX09_COMPARISON = module
    return _CTX09_COMPARISON


def _components(relative: str) -> list[str]:
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in {"", ".", ".."} for p in path.parts):
        raise RolloutError("path must be project-relative and traversal-free")
    return list(path.parts)


def _identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode))


def _open_dir(name: str | Path, parent: int | None, nofollow: int, directory: int) -> int:
    fd = os.open(name, os.O_RDONLY | directory | nofollow, dir_fd=parent)
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise RolloutError("authorized path component is not a directory")
    return fd


def _walk(root_fd: int, parts: list[str], nofollow: int, directory: int, create: bool) -> tuple[int, list[int]]:
    current = os.dup(root_fd)
    opened = [current]
    try:
        for part in parts:
            try:
                child = _open_dir(part, current, nofollow, directory)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o700, dir_fd=current)
                child = _open_dir(part, current, nofollow, directory)
            opened.append(child)
            current = child
        return current, opened
    except BaseException:
        for fd in reversed(opened):
            os.close(fd)
        raise


def _same_parent(root_fd: int, parts: list[str], expected: int, nofollow: int, directory: int) -> bool:
    try:
        current, opened = _walk(root_fd, parts, nofollow, directory, False)
        try:
            return _identity(os.fstat(current))[:2] == _identity(os.fstat(expected))[:2]
        finally:
            for fd in reversed(opened):
                os.close(fd)
    except OSError:
        return False


def _fault(point: str, requested: str | None) -> None:
    if requested == point:
        raise RolloutError("injected managed-block fault: " + point)


def _safe_read(
    root: Path, relative: str, *, with_identity: bool = False,
) -> bytes | None | tuple[bytes | None, dict[str, int] | None]:
    """Bounded single-link read through the same anchored no-follow boundary."""
    parts = _components(relative)
    ctx = _runtime_module()
    nofollow, directory = ctx._require_secure_dir_fd_support()
    root_fd = parent = fd = -1
    opened: list[int] = []
    try:
        root_fd = _open_dir(root, None, nofollow, directory)
        try:
            parent, opened = _walk(root_fd, parts[:-1], nofollow, directory, False)
        except FileNotFoundError:
            return (None, None) if with_identity else None
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | nofollow, dir_fd=parent)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RolloutError("managed target must be a single-link regular file")
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise RolloutError("managed target exceeds bounded size")
            chunks.append(chunk)
        final = os.fstat(fd)
        expected = _identity(metadata)
        if (_identity(final) != expected or final.st_size != metadata.st_size
                or _identity(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)) != expected
                or not _same_parent(root_fd, parts[:-1], parent, nofollow, directory)):
            raise RolloutError("managed target changed during read")
        payload = b"".join(chunks)
        if with_identity:
            return payload, {
                "device": final.st_dev,
                "inode": final.st_ino,
                "mode": final.st_mode,
                "size": final.st_size,
                "mtime_ns": final.st_mtime_ns,
                "ctime_ns": final.st_ctime_ns,
            }
        return payload
    except FileNotFoundError:
        return (None, None) if with_identity else None
    finally:
        if fd >= 0:
            os.close(fd)
        for item in reversed(opened):
            os.close(item)
        if root_fd >= 0:
            os.close(root_fd)


_UNSET = object()


def _atomic_replace(
    root: Path, relative: str, payload: bytes, fault: str | None = None,
    source: bytes | None | object = _UNSET, *, lock_held: bool = False,
) -> None:
    """Publish through the accepted CTX-03 writer under one stable host lock."""
    _components(relative)
    ctx = _runtime_module()
    previous_hook = ctx._TEST_SYNC_HOOK

    def publication_sync(point: str) -> None:
        if previous_hook is not None:
            previous_hook(point)
        if point == "after-final-prepublish-check":
            _fault("before-publication", fault)
        if point == "after-publication-before-commit":
            if fault == "during-publication":
                _fault("during-publication", fault)
            _fault("after-publication-pre-cleanup", fault)

    def publish() -> None:
        _fault("after-read", fault)
        _fault("during-managed-block-replacement", fault)
        ctx._TEST_SYNC_HOOK = publication_sync
        try:
            options = {
                "preserve_mode": True,
                "require_single_link": True,
            }
            if source is not _UNSET:
                options["expected_current"] = source
            try:
                ctx.atomic_write_bytes(root, relative, payload, **options)
            except ctx.RollbackFailure:
                raise
            except ctx.ContractError as error:
                current = _safe_read(root, relative)
                if current == payload:
                    return
                if source is not _UNSET and current != source:
                    raise ConcurrentRolloutUpdate(
                        "managed target changed concurrently; refusing replacement"
                    ) from error
                raise RolloutError(str(error)) from error
        finally:
            ctx._TEST_SYNC_HOOK = previous_hook

    if lock_held:
        publish()
    else:
        with ctx.stable_file_lock(root, LOCK_RELATIVE):
            publish()


def _newline(data: bytes) -> bytes:
    return b"\r\n" if b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"") else b"\n"


def _block(prefix: str, block_id: str, content: str, eol: bytes) -> bytes:
    body = content.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    if not body.endswith(b"\n"):
        body += b"\n"
    digest = hashlib.sha256(body).hexdigest()
    start = f"{prefix}mana:context-runtime:begin version={VERSION} id={block_id} digest={digest}".encode()
    end = f"{prefix}mana:context-runtime:end id={block_id}".encode()
    return eol.join([start, body.replace(b"\n", eol).rstrip(eol), end]) + eol


def _parse_blocks(data: bytes) -> list[dict[str, object]]:
    # The file may contain arbitrary user bytes, but marker lines and managed
    # payload are UTF-8.  Work from bytes so replacement boundaries are exact.
    blocks, active = [], None
    offset = 0
    for raw in data.splitlines(keepends=True):
        line = raw.rstrip(b"\r\n")
        try:
            marker = line.decode("utf-8")
        except UnicodeDecodeError:
            marker = ""
        begin, end = BEGIN.fullmatch(marker), END.fullmatch(marker)
        if begin:
            if active is not None:
                raise RolloutError("nested managed-block marker")
            active = {"id": begin.group("id"), "prefix": begin.group("prefix"), "version": int(begin.group("version")), "digest": begin.group("digest"), "start": offset, "body": offset + len(raw)}
        elif end:
            if active is None:
                raise RolloutError("managed-block end without begin")
            if active["id"] != end.group("id") or active["prefix"] != end.group("prefix"):
                raise RolloutError("managed-block identity mismatch")
            active["end"] = offset + len(raw)
            active["body_end"] = offset
            body = data[int(active["body"]):offset]
            canonical = body.replace(b"\r\n", b"\n")
            if b"\r" in canonical:
                raise RolloutError("managed-block payload has non-canonical line ending")
            if hashlib.sha256(canonical).hexdigest() != active["digest"]:
                raise RolloutError("managed-block digest mismatch")
            blocks.append(active); active = None
        elif MARKER_STEM.match(marker):
            raise RolloutError("malformed managed-block marker")
        offset += len(raw)
    if active is not None:
        raise RolloutError("incomplete managed-block marker")
    ids = [str(block["id"]) for block in blocks]
    if len(ids) != len(set(ids)):
        raise RolloutError("duplicate managed-block identity")
    return blocks


def refresh_block(root: Path, relative: str, block_id: str, content: str, prefix: str, fault: str | None = None) -> dict[str, object]:
    # Read via the same secure code path by entering the writer only once: its
    # post-read identity check prevents a concurrent user edit from being lost.
    source = _safe_read(root, relative)
    raw = source or b""
    _fault("after-parse", fault)
    blocks = _parse_blocks(raw)
    found = next((b for b in blocks if b["id"] == block_id), None)
    if found is not None and int(found["version"]) > VERSION:
        return {"state": "future", "changed": False, "blockId": block_id}
    eol = _newline(raw)
    replacement = _block(prefix, block_id, content, eol)
    if found is None:
        payload = raw + (b"" if not raw or raw.endswith((b"\n", b"\r")) else eol) + replacement
        state = "missing"
    else:
        start, end = int(found["start"]), int(found["end"])
        current = raw[start:end]
        payload = raw[:start] + replacement + raw[end:]
        state = "current" if current == replacement else "stale"
    if payload != raw:
        _atomic_replace(root, relative, payload, fault, source)
        return {"state": state, "changed": True, "blockId": block_id}
    return {"state": state, "changed": False, "blockId": block_id}


def _refresh_block_with_retry(
    root: Path, relative: str, block_id: str, content: str, prefix: str,
    fault: str | None = None,
) -> dict[str, object]:
    for attempt in range(3):
        try:
            return refresh_block(root, relative, block_id, content, prefix, fault)
        except ConcurrentRolloutUpdate:
            if attempt == 2:
                raise
    raise AssertionError("unreachable managed-block retry state")


def _policy_default() -> bytes:
    return (json.dumps({"schemaVersion": POLICY_VERSION, "defaultMode": "legacy", "profiles": {}}, indent=2, sort_keys=True) + "\n").encode()


def _strict_json(raw: bytes, label: str) -> object:
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise RolloutError(label + " contains duplicate JSON member: " + key)
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RolloutError(label + " is invalid JSON") from error


def _validate_policy(policy: object) -> dict[str, object]:
    if not isinstance(policy, dict) or set(policy) != {"schemaVersion", "defaultMode", "profiles"} or policy.get("schemaVersion") != POLICY_VERSION or policy.get("defaultMode") != "legacy" or not isinstance(policy.get("profiles"), dict):
        raise RolloutError("runtime policy violates the host-owned v1 schema")
    for profile, selection in policy["profiles"].items():
        if (not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", profile)
                or not isinstance(selection, dict) or "mode" not in selection
                or set(selection) - {"mode", "failClosed", "exempted", "reason"}
                or selection.get("mode") not in MODES
                or not isinstance(selection.get("failClosed", False), bool)
                or not isinstance(selection.get("exempted", False), bool)
                or ("reason" in selection and (not isinstance(selection["reason"], str) or not selection["reason"] or len(selection["reason"]) > 256))):
            raise RolloutError("runtime profile selection violates the host-owned v1 schema")
        # These cross-field constraints are the host semantic pass after the
        # JSON Schema shape/type pass.  They prevent contradictory selection.
        if selection.get("exempted", False) and selection["mode"] != "legacy":
            raise RolloutError("runtime profile exemption conflicts with selected mode")
        if selection.get("failClosed", False) and selection["mode"] in {"inherited", "legacy"}:
            raise RolloutError("runtime profile failClosed conflicts with selected mode")
    return policy


def load_policy(root: Path) -> tuple[dict[str, object] | None, str]:
    raw = _safe_read(root, POLICY_RELATIVE)
    if raw is None:
        return None, "missing"
    policy = _validate_policy(_strict_json(raw, "runtime policy"))
    return policy, "current"


def _project_root_binding(root: Path) -> str:
    metadata = root.stat(follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise RolloutError("project root is not a host-owned directory")
    return "sha256:" + hashlib.sha256(
        f"{metadata.st_dev}:{metadata.st_ino}:{metadata.st_mode}".encode("ascii")
    ).hexdigest()


def _decision_identity(execution_id: str, execution_version: int, workspace_id: str,
                       profile: str, root: Path) -> dict[str, object]:
    if (not re.fullmatch(r"(?:execution|legacy)-[A-Za-z0-9._-]{1,120}", execution_id)
            or type(execution_version) is not int or execution_version < 1
            or not re.fullmatch(r"W-[a-f0-9]{64}", workspace_id)
            or re.fullmatch(r"[A-Za-z0-9._-]{1,120}", profile) is None):
        raise RolloutError("execution identity is invalid")
    return {"executionId": execution_id, "executionVersion": execution_version,
            "workspaceId": workspace_id, "profileId": profile,
            "projectRootBinding": _project_root_binding(root)}


def _decision_namespace(identity: dict[str, object]) -> str:
    """Return the host-derived execution namespace for rollout authority."""
    key = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f".mana/context-runtime/decisions/{key}"


def _intent_namespace(identity: dict[str, object]) -> str:
    """Host-derived authority namespace, outside the CTX-10 closure."""
    key = hashlib.sha256(_canonical(identity)).hexdigest()
    return f".mana/runtime/execution-intents/{key}"


def _decision_head_path(identity: dict[str, object], name: str) -> str:
    return f"{_decision_namespace(identity)}/HEAD/{name}"


def _decision_bundle_path(identity: dict[str, object], bundle_id: str, name: str) -> str:
    if re.fullmatch(r"B-[a-f0-9]{64}", bundle_id) is None:
        raise _decision_authority_error()
    return f"{_decision_namespace(identity)}/bundles/{bundle_id}/{name}"


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _decision_artifact(value: object, identity: dict[str, object], profile: str) -> dict[str, object]:
    fields = {"schemaVersion", "executionId", "executionVersion", "workspaceId", "projectRootBinding",
              "profileId", "policyId", "policyVersion", "policyDigest", "configuredMode", "effectiveMode",
              "decisionSource", "decisionReason"}
    if (not isinstance(value, dict) or set(value) != fields
            or value.get("schemaVersion") != DECISION_VERSION
            or {key: value.get(key) for key in identity} != identity
            or value.get("profileId") != profile
            or value.get("policyId") != "runtime-selection-v1"
            or value.get("policyVersion") != POLICY_VERSION
            or not isinstance(value.get("policyDigest"), str)
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", value["policyDigest"])
            or value.get("configuredMode") not in MODES
            or value.get("effectiveMode") not in MODES - {"inherited"}
            or value.get("decisionSource") != "host-owned-policy"
            or not isinstance(value.get("decisionReason"), str)
            or not value["decisionReason"]):
        raise _decision_authority_error()
    expected_effective = "legacy" if value["configuredMode"] == "inherited" else value["configuredMode"]
    if value["effectiveMode"] != expected_effective:
        raise _decision_authority_error()
    return value


def _legacy_warning(configured: str, exempted: bool, *, inherited: bool = False,
                    global_default: bool = False) -> dict[str, str] | None:
    if configured == "legacy" and exempted:
        return {"code": "profile-exempted", "reason": "profile-exempted",
                "message": "This profile is explicitly exempted and remains on legacy."}
    if configured == "legacy":
        return {"code": "profile-pinned-legacy", "reason": "profile-pinned-legacy",
                "message": "This profile is explicitly pinned to legacy."}
    if inherited:
        return {"code": "inherited-legacy", "reason": "inherited-legacy",
                "message": "Legacy is selected through an inherited policy selection."}
    if global_default:
        return {"code": "global-default-legacy", "reason": "global-default-legacy",
                "message": "Legacy is selected by the global default."}
    return None


def _migration_metadata(configured: str, exempted: bool, *, declared: bool = False) -> tuple[str, str | None]:
    if configured == "legacy":
        return ("exempted", "profile-exempted") if exempted else ("pinned", "profile-pinned-legacy")
    if configured == "inherited":
        return ("inherited", "inherited-legacy") if declared else ("global-default", "global-default-legacy")
    return "opt-in", None


def _selection_from_policy(
    policy: dict[str, object] | None, status: str, profile: str,
    requested: str | None = None,
) -> dict[str, object]:
    selection = (policy or {"profiles": {}})["profiles"].get(profile, {})
    configured = selection.get("mode", "inherited")
    mode = "legacy" if configured == "inherited" else configured
    if requested is not None and requested not in MODES - {"inherited"}:
        raise RolloutError("unknown requested runtime mode")
    if requested is not None and status == "current" and requested != mode:
        raise RolloutError("requested runtime mode conflicts with the materialized profile selection")
    if requested is not None and status == "missing":
        mode = requested  # Preserves CTX-09 explicit CLI compatibility before bootstrap.
    warning = _legacy_warning(
        configured, bool(selection.get("exempted", False)),
        inherited=bool(selection) and configured == "inherited",
        global_default=not selection,
    ) if mode == "legacy" else None
    disposition, migration_warning = _migration_metadata(
        configured, bool(selection.get("exempted", False)), declared=bool(selection),
    )
    return {
        "schemaVersion": DECISION_VERSION,
        "profileId": profile,
        "mode": mode,
        "runtimeSelection": mode,
        "configuredMode": configured,
        "policyStatus": status,
        "failClosed": bool(selection.get("failClosed", False)),
        "migrationDisposition": disposition,
        "migrationWarning": migration_warning,
        "warning": warning,
    }


def _expected_decision_artifact(
    identity: dict[str, object], profile: str, policy: dict[str, object],
    policy_digest: str,
) -> dict[str, object]:
    decision = _selection_from_policy(policy, "current", profile)
    return {
        "schemaVersion": DECISION_VERSION,
        "policyId": "runtime-selection-v1",
        "policyVersion": POLICY_VERSION,
        "policyDigest": policy_digest,
        **identity,
        "profileId": profile,
        "configuredMode": decision["configuredMode"],
        "effectiveMode": decision["mode"],
        "decisionSource": "host-owned-policy",
        "decisionReason": (decision["warning"] or {"reason": "profile-opt-in"})["reason"],
    }


def _policy_snapshot(
    identity: dict[str, object], policy: dict[str, object], policy_digest: str,
) -> dict[str, object]:
    return {
        "schemaVersion": POLICY_SNAPSHOT_VERSION,
        "policyId": "runtime-selection-v1",
        "policyVersion": POLICY_VERSION,
        "policyDigest": policy_digest,
        "executionIdentity": identity,
        "policy": policy,
    }


def _validate_policy_snapshot(
    value: object, identity: dict[str, object], profile: str,
) -> tuple[dict[str, object], str]:
    fields = {
        "schemaVersion", "policyId", "policyVersion", "policyDigest",
        "executionIdentity", "policy",
    }
    try:
        if (not isinstance(value, dict) or set(value) != fields
                or value.get("schemaVersion") != POLICY_SNAPSHOT_VERSION
                or value.get("policyId") != "runtime-selection-v1"
                or value.get("policyVersion") != POLICY_VERSION
                or value.get("executionIdentity") != identity):
            raise _decision_authority_error()
        policy = _validate_policy(value["policy"])
        policy_digest = _sha256(_canonical(policy))
        if value.get("policyDigest") != policy_digest:
            raise _decision_authority_error()
        # Recompute the selected profile now so a committed but semantically
        # unusable snapshot cannot be admitted by shape alone.
        _selection_from_policy(policy, "current", profile)
        return policy, policy_digest
    except DecisionAuthorityError:
        raise
    except (KeyError, TypeError, RolloutError) as error:
        raise _decision_authority_error() from error


_FILE_INSTANCE_FIELDS = {"device", "inode", "mode", "size", "mtime_ns", "ctime_ns"}
_BUNDLE_FILES = {
    "policySnapshot": "policy-snapshot-v1.json",
    "rolloutDecision": "decision-v1.json",
    "decisionReceipt": "decision-receipt-v1.json",
}


def _decision_sync(point: str) -> None:
    if _TEST_DECISION_HOOK is not None:
        _TEST_DECISION_HOOK(point)


def _validate_file_identity(value: object, actual: dict[str, int] | None) -> bool:
    return (isinstance(value, dict)
            and set(value) == _FILE_INSTANCE_FIELDS
            and all(type(value[field]) is int and value[field] >= 0 for field in value)
            and stat.S_ISREG(value["mode"])
            and value == actual)


def _file_commitment(path: str, payload: bytes, instance: dict[str, int]) -> dict[str, object]:
    return {"path": path, "digest": _sha256(payload), "fileInstance": instance}


def _validate_commitment(
    value: object, path: str, payload: bytes, instance: dict[str, int] | None,
) -> bool:
    return (isinstance(value, dict)
            and set(value) == {"path", "digest", "fileInstance"}
            and value.get("path") == path
            and value.get("digest") == _sha256(payload)
            and _validate_file_identity(value.get("fileInstance"), instance))


def _canonical_object(payload: bytes, label: str) -> dict[str, object]:
    value = _strict_json(payload, label)
    if not isinstance(value, dict) or _canonical(value) != payload:
        raise _decision_authority_error()
    return value


def _staging_file_instance(staging, name: str, expected: bytes) -> dict[str, int]:
    """Attest one staged child through its held directory descriptor."""
    ctx = _runtime_module()
    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | staging._nofollow,
                 dir_fd=staging._staging_fd)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o600):
            raise _decision_authority_error()
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=staging._staging_fd, follow_symlinks=False)
        stable = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if (b"".join(chunks) != expected
                or any(getattr(before, field) != getattr(after, field) for field in stable)
                or any(getattr(named, field) != getattr(after, field) for field in stable)
                or not ctx._verify_identity(staging._staging_fd, name, ctx._entry_identity(after))):
            raise _decision_authority_error()
        return {
            "device": after.st_dev, "inode": after.st_ino, "mode": after.st_mode,
            "size": after.st_size, "mtime_ns": after.st_mtime_ns,
            "ctime_ns": after.st_ctime_ns,
        }
    finally:
        os.close(fd)


def _receipt_id(value: dict[str, object]) -> str:
    return "R-" + hashlib.sha256(_canonical(value)).hexdigest()


def _new_bundle_id() -> str:
    """Allocate a host nonce; no public surface accepts a bundle identity."""
    return "B-" + hashlib.sha256(os.urandom(32)).hexdigest()


def _authority_id(value: dict[str, object]) -> str:
    return "A-" + hashlib.sha256(_canonical(value)).hexdigest()


def _directory_entries(root: Path, relative: str) -> list[str] | None:
    parts = _components(relative)
    ctx = _runtime_module()
    nofollow, directory = ctx._require_secure_dir_fd_support()
    root_fd = target = -1
    opened: list[int] = []
    try:
        root_fd = _open_dir(root, None, nofollow, directory)
        try:
            target, opened = _walk(root_fd, parts, nofollow, directory, False)
        except FileNotFoundError:
            return None
        if not _same_parent(root_fd, parts, target, nofollow, directory):
            raise _decision_authority_error()
        return sorted(os.listdir(target))
    finally:
        for fd in reversed(opened):
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)


def _require_private_directory(root: Path, relative: str) -> None:
    parts = _components(relative)
    ctx = _runtime_module()
    nofollow, directory = ctx._require_secure_dir_fd_support()
    root_fd = -1
    opened: list[int] = []
    try:
        root_fd = _open_dir(root, None, nofollow, directory)
        target, opened = _walk(root_fd, parts, nofollow, directory, False)
        metadata = os.fstat(target)
        if (not stat.S_ISDIR(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o700
                or metadata.st_uid != os.getuid()
                or not _same_parent(root_fd, parts, target, nofollow, directory)):
            raise _decision_authority_error()
    finally:
        for fd in reversed(opened):
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)


def _intent_paths(identity: dict[str, object]) -> tuple[str, str]:
    base = _intent_namespace(identity)
    return f"{base}/execution-intent-v1.json", f"{base}/intent-commit-v1.json"


def _load_intent(
    root: Path, identity: dict[str, object], profile: str,
) -> tuple[dict[str, object], bytes, dict[str, int], bytes, dict[str, int]]:
    """Read the external host authority before touching any CTX-10 artifact."""
    try:
        intent_path, commit_path = _intent_paths(identity)
        _require_private_directory(root, _intent_namespace(identity))
        raw, instance = _safe_read(root, intent_path, with_identity=True)
        commit_raw, commit_instance = _safe_read(root, commit_path, with_identity=True)
        if any(value is None for value in (raw, instance, commit_raw, commit_instance)):
            raise _decision_authority_error()
        intent = _canonical_object(raw, "execution intent")
        commit = _canonical_object(commit_raw, "execution intent commit")
        body = {key: value for key, value in intent.items() if key != "intentDigest"}
        fields = {
            "schemaVersion", "intentId", "executionIdentity", "target", "policy",
            "policyDigest", "policySnapshotDigest", "configuredMode", "effectiveMode",
            "lifecycleStatus", "commitState", "intentDigest",
        }
        if (set(intent) != fields or intent.get("schemaVersion") != INTENT_VERSION
                or not isinstance(intent.get("intentId"), str)
                or re.fullmatch(r"I-[a-f0-9]{64}", intent["intentId"]) is None
                or intent.get("executionIdentity") != identity
                or intent.get("lifecycleStatus") != "initialized"
                or intent.get("commitState") != "committed"
                or intent.get("intentDigest") != _sha256(_canonical(body))
                or stat.S_IMODE(instance["mode"]) != 0o600
                or stat.S_IMODE(commit_instance["mode"]) != 0o600):
            raise _decision_authority_error()
        target = intent["target"]
        if target is not None and (not isinstance(target, dict)
                                   or set(target) != {"repository", "base", "prNumber"}):
            raise _decision_authority_error()
        policy = _validate_policy(intent["policy"])
        policy_digest = _sha256(_canonical(policy))
        expected = _expected_decision_artifact(identity, profile, policy, policy_digest)
        snapshot_digest = _sha256(_canonical(_policy_snapshot(identity, policy, policy_digest)))
        if (intent.get("policyDigest") != policy_digest
                or intent.get("policySnapshotDigest") != snapshot_digest
                or intent.get("configuredMode") != expected["configuredMode"]
                or intent.get("effectiveMode") != expected["effectiveMode"]):
            raise _decision_authority_error()
        if (set(commit) != {"schemaVersion", "intentId", "intentPath", "intentDigest",
                            "intentFile", "executionIdentityDigest", "commitState"}
                or commit.get("schemaVersion") != INTENT_COMMIT_VERSION
                or commit.get("intentId") != intent["intentId"]
                or commit.get("intentPath") != intent_path
                or commit.get("intentDigest") != _sha256(raw)
                or not _validate_file_identity(commit.get("intentFile"), instance)
                or commit.get("executionIdentityDigest") != _sha256(_canonical(identity))
                or commit.get("commitState") != "committed"):
            raise _decision_authority_error()
        return intent, raw, instance, commit_raw, commit_instance
    except DecisionAuthorityError:
        raise
    except (OSError, KeyError, TypeError, ValueError, RolloutError) as error:
        raise _decision_authority_error() from error


def _verify_ctx06_intent_link(
    root: Path, identity: dict[str, object], profile: str,
    intent_record: tuple[dict[str, object], bytes, dict[str, int], bytes, dict[str, int]] | None,
) -> None:
    """Reject old or foreign CTX-06 runs; absence is checked by dispatch."""
    try:
        execution_id = identity["executionId"]
        if not str(execution_id).startswith("execution-"):
            return
        run = f".mana/runtime/runs/{execution_id}"
        run_raw = _safe_read(root, f"{run}/run-directory-v1.json")
        if run_raw is None:
            return
        run_record = _canonical_object(run_raw, "CTX-06 run directory")
        if any(run_record.get(key) != identity[key] for key in
               ("executionId", "workspaceId", "profileId")):
            raise _decision_authority_error()
        envelope_raw = _safe_read(root, f"{run}/execution-envelope-v1.json")
        if envelope_raw is None or intent_record is None:
            raise _decision_authority_error()
        envelope = _canonical_object(envelope_raw, "CTX-06 execution envelope")
        if envelope.get("schemaVersion") != "mana.context-runtime.execution-envelope/v2":
            raise _decision_authority_error()
        _runtime_module().validate_execution_envelope(envelope)
        intent, raw, instance, commit_raw, commit_instance = intent_record
        intent_path, commit_path = _intent_paths(identity)
        expected = {
            "intentId": intent["intentId"], "intentPath": intent_path,
            "intentDigest": _sha256(raw), "intentFile": instance,
            "intentCommitPath": commit_path,
            "intentCommitDigest": _sha256(commit_raw),
            "intentCommitFile": commit_instance,
        }
        if ({key: envelope.get(key) for key in ("executionId", "executionVersion",
                                               "workspaceId", "profileId")} !=
                {key: identity[key] for key in ("executionId", "executionVersion",
                                                "workspaceId", "profileId")}
                or envelope.get("executionIntent") != expected
                or envelope.get("target") != intent["target"]):
            raise _decision_authority_error()
    except DecisionAuthorityError:
        raise
    except (OSError, KeyError, TypeError, ValueError, RolloutError) as error:
        raise _decision_authority_error() from error


def _ensure_intent(
    root: Path, identity: dict[str, object], profile: str,
    target: dict[str, object] | None = None,
) -> tuple[dict[str, object], bytes, dict[str, int], bytes, dict[str, int]]:
    """Commit frozen policy and identity in the host namespace before selection."""
    intent_path, _ = _intent_paths(identity)
    if _safe_read(root, intent_path) is not None:
        existing = _load_intent(root, identity, profile)
        if target is not None and existing[0]["target"] != target:
            raise _decision_authority_error()
        return existing
    policy, status = load_policy(root)
    if policy is None or status != "current":
        raise RolloutError("runtime policy must be materialized before an execution intent")
    policy_digest = _sha256(_canonical(policy))
    expected = _expected_decision_artifact(identity, profile, policy, policy_digest)
    body = {
        "schemaVersion": INTENT_VERSION,
        "intentId": "I-" + hashlib.sha256(os.urandom(32)).hexdigest(),
        "executionIdentity": identity,
        "target": target,
        "policy": policy,
        "policyDigest": policy_digest,
        "policySnapshotDigest": _sha256(_canonical(_policy_snapshot(identity, policy, policy_digest))),
        "configuredMode": expected["configuredMode"],
        "effectiveMode": expected["effectiveMode"],
        "lifecycleStatus": "initialized",
        "commitState": "committed",
    }
    intent = {**body, "intentDigest": _sha256(_canonical(body))}
    payload = _canonical(intent)
    ctx = _runtime_module()
    parent = ".mana/runtime/execution-intents"
    key = _intent_namespace(identity).rsplit("/", 1)[1]
    staging = ctx.PrivateStagingDirectory.create(root, parent, "intent-" + key[:16])
    try:
        staging.write_bytes("execution-intent-v1.json", payload)
        instance = _staging_file_instance(staging, "execution-intent-v1.json", payload)
        commit = {
            "schemaVersion": INTENT_COMMIT_VERSION,
            "intentId": intent["intentId"],
            "intentPath": intent_path,
            "intentDigest": _sha256(payload),
            "intentFile": instance,
            "executionIdentityDigest": _sha256(_canonical(identity)),
            "commitState": "committed",
        }
        commit_payload = _canonical(commit)
        staging.write_bytes("intent-commit-v1.json", commit_payload)
        _staging_file_instance(staging, "intent-commit-v1.json", commit_payload)
        os.fsync(staging._staging_fd)
        _decision_sync("after-authority-initialization-staging")
        staging.publish_noreplace(key)
        staging.commit_publication()
        _decision_sync("after-authority-initialization")
    finally:
        try:
            staging.cleanup()
        finally:
            staging.close()
    return _load_intent(root, identity, profile)


def _load_decision_bundle(
    root: Path, identity: dict[str, object], profile: str, bundle_id: str,
    *, base_relative: str | None = None,
) -> tuple[dict[str, object], dict[str, object], bytes, dict[str, int]]:
    """Re-attest an immutable bundle and derive its expected decision."""
    base = base_relative or f"{_decision_namespace(identity)}/bundles/{bundle_id}"
    manifest_path = f"{base}/bundle-manifest-v1.json"
    manifest_raw, manifest_file = _safe_read(root, manifest_path, with_identity=True)
    if manifest_raw is None or manifest_file is None:
        raise _decision_authority_error()
    manifest = _canonical_object(manifest_raw, "rollout decision bundle manifest")
    fields = {
        "schemaVersion", "bundleId", "bundlePath", "executionId",
        "executionVersion", "workspaceId", "profileId", "projectRootBinding",
        "policyId", "policyVersion", "policySnapshotDigest",
        "rolloutDecisionDigest", "receiptDigest", "configuredMode",
        "effectiveMode", "previousAuthorityReference", "receiptId",
        "childCommitmentsDigest", "artifacts",
    }
    expected_base = f"{_decision_namespace(identity)}/bundles/{bundle_id}"
    if (set(manifest) != fields
            or manifest.get("schemaVersion") != DECISION_BUNDLE_VERSION
            or manifest.get("bundleId") != bundle_id
            or manifest.get("bundlePath") != expected_base
            or {key: manifest.get(key) for key in identity} != identity
            or manifest.get("profileId") != profile
            or manifest.get("policyId") != "runtime-selection-v1"
            or manifest.get("policyVersion") != POLICY_VERSION
            or manifest.get("previousAuthorityReference") is not None
            or not isinstance(manifest.get("artifacts"), dict)
            or set(manifest["artifacts"]) != set(_BUNDLE_FILES)):
        raise _decision_authority_error()
    payloads: dict[str, bytes] = {}
    instances: dict[str, dict[str, int]] = {}
    expected_commitments: dict[str, object] = {}
    for role, name in _BUNDLE_FILES.items():
        final_path = f"{expected_base}/{name}"
        actual_path = f"{base}/{name}"
        raw, instance = _safe_read(root, actual_path, with_identity=True)
        if raw is None or instance is None:
            raise _decision_authority_error()
        commitment = manifest["artifacts"].get(role)
        if not _validate_commitment(commitment, final_path, raw, instance):
            raise _decision_authority_error()
        payloads[role], instances[role] = raw, instance
        expected_commitments[role] = commitment
    if manifest.get("childCommitmentsDigest") != _sha256(_canonical(expected_commitments)):
        raise _decision_authority_error()
    snapshot = _canonical_object(payloads["policySnapshot"], "rollout policy snapshot")
    decision = _canonical_object(payloads["rolloutDecision"], "rollout decision")
    receipt = _canonical_object(payloads["decisionReceipt"], "rollout decision receipt")
    artifact = _decision_artifact(decision, identity, profile)
    policy, policy_digest = _validate_policy_snapshot(snapshot, identity, profile)
    expected = _expected_decision_artifact(identity, profile, policy, policy_digest)
    if artifact != expected:
        raise _decision_authority_error()
    receipt_fields = {
        "schemaVersion", "receiptId", "executionIdentityDigest",
        "policySnapshot", "rolloutDecision",
    }
    receipt_body = {key: receipt[key] for key in receipt if key != "receiptId"}
    snapshot_record = {
        "path": _BUNDLE_FILES["policySnapshot"],
        "digest": _sha256(payloads["policySnapshot"]),
        "fileInstance": instances["policySnapshot"],
    }
    decision_record = {
        "path": _BUNDLE_FILES["rolloutDecision"],
        "digest": _sha256(payloads["rolloutDecision"]),
        "fileInstance": instances["rolloutDecision"],
    }
    if (set(receipt) != receipt_fields
            or receipt.get("schemaVersion") != DECISION_RECEIPT_VERSION
            or receipt.get("receiptId") != _receipt_id(receipt_body)
            or receipt.get("executionIdentityDigest") != _sha256(_canonical(identity))
            or receipt.get("policySnapshot") != snapshot_record
            or receipt.get("rolloutDecision") != decision_record
            or manifest.get("receiptId") != receipt["receiptId"]
            or manifest.get("policySnapshotDigest") != _sha256(payloads["policySnapshot"])
            or manifest.get("rolloutDecisionDigest") != _sha256(payloads["rolloutDecision"])
            or manifest.get("receiptDigest") != _sha256(payloads["decisionReceipt"])
            or manifest.get("configuredMode") != artifact["configuredMode"]
            or manifest.get("effectiveMode") != artifact["effectiveMode"]):
        raise _decision_authority_error()
    return artifact, manifest, manifest_raw, manifest_file


def _load_decision_head(
    root: Path, identity: dict[str, object], profile: str, *, base_relative: str | None = None,
) -> dict[str, object] | None:
    head_path = _decision_head_path(identity, "decision-head-v1.json")
    commit_path = _decision_head_path(identity, "decision-head-commit-v1.json")
    actual_base = base_relative or f"{_decision_namespace(identity)}/HEAD"
    actual_head_path = f"{actual_base}/decision-head-v1.json"
    actual_commit_path = f"{actual_base}/decision-head-commit-v1.json"
    head_raw, head_file = _safe_read(root, actual_head_path, with_identity=True)
    commit_raw, commit_file = _safe_read(root, actual_commit_path, with_identity=True)
    if head_raw is None and commit_raw is None:
        return None
    if head_raw is None or head_file is None or commit_raw is None or commit_file is None:
        raise _decision_authority_error()
    head = _canonical_object(head_raw, "rollout decision HEAD")
    commit = _canonical_object(commit_raw, "rollout decision HEAD commitment")
    head_fields = {
        "schemaVersion", "authorityId", "executionId", "executionVersion",
        "workspaceId", "profileId", "projectRootBinding", "bundleId",
        "bundlePath", "bundleDigest", "bundleManifest", "configuredMode",
        "effectiveMode", "childCommitmentsDigest", "previousAuthorityReference",
    }
    authority_body = {key: head[key] for key in head if key != "authorityId"}
    bundle_id = head.get("bundleId")
    expected_bundle_path = (f"{_decision_namespace(identity)}/bundles/{bundle_id}"
                            if isinstance(bundle_id, str) else "")
    manifest_path = f"{expected_bundle_path}/bundle-manifest-v1.json"
    if (set(head) != head_fields
            or head.get("schemaVersion") != DECISION_HEAD_VERSION
            or head.get("authorityId") != _authority_id(authority_body)
            or {key: head.get(key) for key in identity} != identity
            or head.get("profileId") != profile
            or head.get("bundlePath") != expected_bundle_path
            or head.get("previousAuthorityReference") is not None):
        raise _decision_authority_error()
    artifact, manifest, manifest_raw, manifest_file = _load_decision_bundle(
        root, identity, profile, str(bundle_id)
    )
    if (head.get("bundleDigest") != _sha256(manifest_raw)
            or not _validate_commitment(
                head.get("bundleManifest"), manifest_path, manifest_raw, manifest_file)
            or head.get("configuredMode") != artifact["configuredMode"]
            or head.get("effectiveMode") != artifact["effectiveMode"]
            or head.get("childCommitmentsDigest") != manifest["childCommitmentsDigest"]):
        raise _decision_authority_error()
    commit_fields = {
        "schemaVersion", "authorityId", "executionIdentityDigest", "headPath",
        "headDigest", "headFile", "bundleManifestPath", "bundleManifestDigest",
        "bundleManifestFile",
    }
    if (set(commit) != commit_fields
            or commit.get("schemaVersion") != DECISION_HEAD_COMMIT_VERSION
            or commit.get("authorityId") != head["authorityId"]
            or commit.get("executionIdentityDigest") != _sha256(_canonical(identity))
            or commit.get("headPath") != head_path
            or commit.get("headDigest") != _sha256(head_raw)
            or not _validate_file_identity(commit.get("headFile"), head_file)
            or commit.get("bundleManifestPath") != manifest_path
            or commit.get("bundleManifestDigest") != _sha256(manifest_raw)
            or not _validate_file_identity(commit.get("bundleManifestFile"), manifest_file)
            or stat.S_IMODE(commit_file["mode"]) != 0o600):
        raise _decision_authority_error()
    # Close the read window: neither outer parent record may change while the
    # referenced bundle is being authenticated.
    again_head, again_head_file = _safe_read(root, actual_head_path, with_identity=True)
    again_commit, again_commit_file = _safe_read(root, actual_commit_path, with_identity=True)
    if (again_head != head_raw or again_head_file != head_file
            or again_commit != commit_raw or again_commit_file != commit_file):
        raise _decision_authority_error()
    return artifact


def _selection_path(identity: dict[str, object]) -> str:
    return f"{_intent_namespace(identity)}/SELECTION/rollout-decision-commitment-v1.json"


def _selection_body(
    root: Path, identity: dict[str, object], profile: str,
    intent_record: tuple[dict[str, object], bytes, dict[str, int], bytes, dict[str, int]],
) -> dict[str, object]:
    """Build the external commitment only after the CTX-10 bundle is attested."""
    intent, intent_raw, intent_file, intent_commit_raw, intent_commit_file = intent_record
    artifact = _load_decision_head(root, identity, profile)
    if artifact is None:
        raise _decision_authority_error()
    expected = _expected_decision_artifact(identity, profile, intent["policy"], intent["policyDigest"])
    if artifact != expected:
        raise _decision_authority_error()
    head_path = _decision_head_path(identity, "decision-head-v1.json")
    head_commit_path = _decision_head_path(identity, "decision-head-commit-v1.json")
    head_raw, head_file = _safe_read(root, head_path, with_identity=True)
    head_commit_raw, head_commit_file = _safe_read(root, head_commit_path, with_identity=True)
    if any(value is None for value in (head_raw, head_file, head_commit_raw, head_commit_file)):
        raise _decision_authority_error()
    head = _canonical_object(head_raw, "rollout decision HEAD")
    manifest_path = f"{head['bundlePath']}/bundle-manifest-v1.json"
    manifest_raw, manifest_file = _safe_read(root, manifest_path, with_identity=True)
    if manifest_raw is None or manifest_file is None:
        raise _decision_authority_error()
    intent_path, intent_commit_path = _intent_paths(identity)
    return {
        "schemaVersion": SELECTION_COMMIT_VERSION,
        "commitmentId": "C-" + hashlib.sha256(os.urandom(32)).hexdigest(),
        "authorityType": "execution-intent-selection",
        **identity,
        "target": intent["target"],
        "intentId": intent["intentId"],
        "intent": _file_commitment(intent_path, intent_raw, intent_file),
        "intentCommit": _file_commitment(intent_commit_path, intent_commit_raw, intent_commit_file),
        "policyId": "runtime-selection-v1",
        "policyVersion": POLICY_VERSION,
        "policySnapshotDigest": intent["policySnapshotDigest"],
        "configuredMode": artifact["configuredMode"],
        "effectiveMode": artifact["effectiveMode"],
        "bundleId": head["bundleId"],
        "bundlePath": head["bundlePath"],
        "bundleDigest": head["bundleDigest"],
        "bundleManifest": _file_commitment(manifest_path, manifest_raw, manifest_file),
        "decisionHead": _file_commitment(head_path, head_raw, head_file),
        "decisionHeadCommit": _file_commitment(head_commit_path, head_commit_raw, head_commit_file),
        "creationState": "committed",
        "previousAuthorityReference": None,
    }


def _load_selection(
    root: Path, identity: dict[str, object], profile: str,
    intent_record: tuple[dict[str, object], bytes, dict[str, int], bytes, dict[str, int]],
) -> dict[str, object] | None:
    """Resolve parent first, then follow exactly its committed CTX-10 graph."""
    try:
        path = _selection_path(identity)
        selection_dir = f"{_intent_namespace(identity)}/SELECTION"
        if _directory_entries(root, selection_dir) is None:
            return None
        _require_private_directory(root, selection_dir)
        raw, instance = _safe_read(root, path, with_identity=True)
        if raw is None:
            return None
        if instance is None or stat.S_IMODE(instance["mode"]) != 0o600:
            raise _decision_authority_error()
        value = _canonical_object(raw, "rollout decision commitment")
        intent, intent_raw, intent_file, intent_commit_raw, intent_commit_file = intent_record
        fields = {
            "schemaVersion", "commitmentId", "authorityType", *identity.keys(),
            "target", "intentId", "intent", "intentCommit", "policyId", "policyVersion",
            "policySnapshotDigest", "configuredMode", "effectiveMode", "bundleId",
            "bundlePath", "bundleDigest", "bundleManifest", "decisionHead",
            "decisionHeadCommit", "creationState", "previousAuthorityReference",
        }
        intent_path, intent_commit_path = _intent_paths(identity)
        if (set(value) != fields
                or value.get("schemaVersion") != SELECTION_COMMIT_VERSION
                or not isinstance(value.get("commitmentId"), str)
                or re.fullmatch(r"C-[a-f0-9]{64}", value["commitmentId"]) is None
                or value.get("authorityType") != "execution-intent-selection"
                or {key: value.get(key) for key in identity} != identity
                or value.get("target") != intent["target"]
                or value.get("intentId") != intent["intentId"]
                or not _validate_commitment(value.get("intent"), intent_path, intent_raw, intent_file)
                or not _validate_commitment(value.get("intentCommit"), intent_commit_path, intent_commit_raw, intent_commit_file)
                or value.get("policyId") != "runtime-selection-v1"
                or value.get("policyVersion") != POLICY_VERSION
                or value.get("policySnapshotDigest") != intent["policySnapshotDigest"]
                or value.get("configuredMode") != intent["configuredMode"]
                or value.get("effectiveMode") != intent["effectiveMode"]
                or value.get("creationState") != "committed"
                or value.get("previousAuthorityReference") is not None):
            raise _decision_authority_error()
        bundle_id = value["bundleId"]
        if (not isinstance(bundle_id, str)
                or re.fullmatch(r"B-[a-f0-9]{64}", bundle_id) is None):
            raise _decision_authority_error()
        bundle_path = f"{_decision_namespace(identity)}/bundles/{bundle_id}"
        head_path = _decision_head_path(identity, "decision-head-v1.json")
        head_commit_path = _decision_head_path(identity, "decision-head-commit-v1.json")
        manifest_path = f"{bundle_path}/bundle-manifest-v1.json"
        if value.get("bundlePath") != bundle_path:
            raise _decision_authority_error()
        # All child paths are host-derived; no commitment path is used as an input.
        for key, child_path in (("bundleManifest", manifest_path),
                                ("decisionHead", head_path),
                                ("decisionHeadCommit", head_commit_path)):
            child_raw, child_file = _safe_read(root, child_path, with_identity=True)
            if child_raw is None or child_file is None or not _validate_commitment(
                    value.get(key), child_path, child_raw, child_file):
                raise _decision_authority_error()
        manifest_raw = _safe_read(root, manifest_path)
        if value.get("bundleDigest") != _sha256(manifest_raw):
            raise _decision_authority_error()
        artifact = _load_decision_head(root, identity, profile)
        expected = _expected_decision_artifact(identity, profile, intent["policy"], intent["policyDigest"])
        if artifact != expected:
            raise _decision_authority_error()
        again, again_instance = _safe_read(root, path, with_identity=True)
        if again != raw or again_instance != instance:
            raise _decision_authority_error()
        again_intent = _load_intent(root, identity, profile)
        if again_intent[1:] != intent_record[1:]:
            raise _decision_authority_error()
        return artifact
    except DecisionAuthorityError:
        raise
    except (OSError, KeyError, TypeError, ValueError, RolloutError) as error:
        raise _decision_authority_error() from error


def _publish_selection(
    root: Path, identity: dict[str, object], profile: str,
    intent_record: tuple[dict[str, object], bytes, dict[str, int], bytes, dict[str, int]],
) -> dict[str, object]:
    body = _selection_body(root, identity, profile, intent_record)
    payload = _canonical(body)
    ctx = _runtime_module()
    staging = ctx.PrivateStagingDirectory.create(root, _intent_namespace(identity), "rollout-selection")
    try:
        staging.write_bytes("rollout-decision-commitment-v1.json", payload)
        _staging_file_instance(staging, "rollout-decision-commitment-v1.json", payload)
        os.fsync(staging._staging_fd)
        _decision_sync("before-parent-commitment")
        staging.publish_noreplace("SELECTION")
        _decision_sync("during-parent-cas")
        staging.commit_publication()
        _decision_sync("after-parent-commit-pre-cleanup")
    finally:
        try:
            staging.cleanup()
        finally:
            staging.close()
    committed = _load_selection(root, identity, profile, intent_record)
    if committed is None:
        raise _decision_authority_error()
    return committed


def _committed_decision(
    root: Path, identity: dict[str, object], profile: str,
) -> dict[str, object]:
    try:
        intent = _load_intent(root, identity, profile)
        _verify_ctx06_intent_link(root, identity, profile, intent)
        artifact = _load_selection(root, identity, profile, intent)
        if artifact is None:
            raise _decision_authority_error()
        return artifact
    except DecisionAuthorityError:
        raise
    except (OSError, KeyError, TypeError, RolloutError) as error:
        raise _decision_authority_error() from error


def resolve(root: Path, profile: str, requested: str | None = None,
            identity: dict[str, object] | None = None) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", profile):
        raise RolloutError("profile identity is invalid")
    # A materialized decision is immutable input for its execution.  In
    # particular, a later edit to the source policy cannot flip an in-flight
    # run.  Resolve remains read-only; execution calls materialize-decision.
    if identity is None:
        raise _decision_authority_error()
    artifact = _committed_decision(root, identity, profile)
    if artifact is not None:
        if requested is not None and requested != artifact["effectiveMode"]:
            raise RolloutError("requested runtime mode conflicts with the materialized profile selection")
        warning = _legacy_warning(str(artifact["configuredMode"]), artifact["decisionReason"] == "profile-exempted",
                                  inherited=artifact["decisionReason"] == "inherited-legacy",
                                  global_default=artifact["decisionReason"] == "global-default-legacy")
        disposition, migration_warning = _migration_metadata(str(artifact["configuredMode"]), artifact["decisionReason"] == "profile-exempted", declared=artifact["decisionReason"] == "inherited-legacy")
        return {"schemaVersion": artifact["schemaVersion"], "profileId": profile, "mode": artifact["effectiveMode"], "runtimeSelection": artifact["effectiveMode"], "configuredMode": artifact["configuredMode"], "policyStatus": "materialized", "failClosed": False, "migrationDisposition": disposition, "migrationWarning": migration_warning, "warning": warning, "decision": artifact}
    raise _decision_authority_error()


def preview_policy(root: Path, profile: str, requested: str | None = None) -> dict[str, object]:
    """Read-only precondition preview; never an authority or dispatch result."""
    policy, status = load_policy(root)
    return _selection_from_policy(policy, status, profile, requested)


def candidate(root: Path, profile: str, requested: str | None = None,
              execution_id: str | None = None) -> dict[str, object]:
    """Precondition mode only; a committed execution wins over policy edits."""
    if execution_id is not None:
        if re.fullmatch(r"(?:execution|legacy)-[A-Za-z0-9._-]{1,120}", execution_id) is None:
            raise _decision_authority_error()
        try:
            if re.fullmatch(r"legacy-[A-Za-z0-9._-]{1,120}", execution_id):
                known = legacy_execution_identity(root, profile, execution_id)
                identity = _decision_identity(execution_id, 1, known["workspaceId"], profile, root)
            else:
                raw = _safe_read(root, f".mana/runtime/runs/{execution_id}/run-directory-v1.json")
                if raw is None:
                    return preview_policy(root, profile, requested)
                record = _canonical_object(raw, "CTX-06 run directory")
                identity = _decision_identity(execution_id, 1, record["workspaceId"], profile, root)
            if _safe_read(root, _intent_paths(identity)[0]) is not None:
                intent = _load_intent(root, identity, profile)
                artifact = _load_selection(root, identity, profile, intent)
                mode = artifact["effectiveMode"] if artifact is not None else intent[0]["effectiveMode"]
                if requested is not None and requested != mode:
                    raise RolloutError("requested runtime mode conflicts with the committed execution intent")
                return {"mode": mode, "profileId": profile,
                        "policyStatus": "materialized" if artifact is not None else "intent-prepared"}
        except DecisionAuthorityError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise _decision_authority_error() from error
    return preview_policy(root, profile, requested)


def _remove_valid_stage(root: Path, parent_relative: str, name: str) -> None:
    """Remove one already validated private staging tree through held FDs."""
    ctx = _runtime_module()
    nofollow, directory = ctx._require_secure_dir_fd_support()
    root_fd = stage_fd = -1
    opened: list[int] = []
    try:
        root_fd = _open_dir(root, None, nofollow, directory)
        parent_fd, opened = _walk(root_fd, _components(parent_relative), nofollow, directory, False)
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        stage_fd = _open_dir(name, parent_fd, nofollow, directory)
        expected = _identity(metadata)
        if (_identity(os.fstat(stage_fd)) != expected
                or stat.S_IMODE(metadata.st_mode) != 0o700
                or metadata.st_uid != os.getuid()
                or not ctx._verify_identity(parent_fd, name, expected)
                or not _same_parent(root_fd, _components(parent_relative), parent_fd, nofollow, directory)):
            raise _decision_authority_error()
        ctx._remove_directory_contents(stage_fd, nofollow, directory)
        if not ctx._verify_identity(parent_fd, name, expected):
            raise _decision_authority_error()
        os.rmdir(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        if stage_fd >= 0:
            os.close(stage_fd)
        for fd in reversed(opened):
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)


def _reconcile_parent_staging(root: Path, identity: dict[str, object]) -> None:
    """Remove private, uncommitted intent/selection staging for this execution."""
    parent = ".mana/runtime/execution-intents"
    key = _intent_namespace(identity).rsplit("/", 1)[1]
    intent_pattern = re.compile(
        r"^\.intent-" + key[:16] + r"\.stage\.[a-f0-9]{16}(?:\.abort\.[a-f0-9]{16})?$")
    intent_stages = [name for name in _directory_entries(root, parent) or []
                     if intent_pattern.fullmatch(name)]
    if len(intent_stages) > 1:
        raise _decision_authority_error()
    for name in intent_stages:
        _remove_valid_stage(root, parent, name)
    namespace = _intent_namespace(identity)
    selection_pattern = re.compile(
        r"^\.rollout-selection\.stage\.[a-f0-9]{16}(?:\.abort\.[a-f0-9]{16})?$")
    selection_stages = [name for name in _directory_entries(root, namespace) or []
                        if selection_pattern.fullmatch(name)]
    if len(selection_stages) > 1:
        raise _decision_authority_error()
    for name in selection_stages:
        _remove_valid_stage(root, namespace, name)


def _reconcile_decision_staging(
    root: Path, identity: dict[str, object], profile: str,
) -> None:
    """Clean only complete, fully re-attested CTX-10 staging trees."""
    namespace = _decision_namespace(identity)
    bundle_parent = f"{namespace}/bundles"
    bundle_stage = re.compile(r"^\.decision-bundle\.stage\.[a-f0-9]{16}(?:\.abort\.[a-f0-9]{16})?$")
    head_stage = re.compile(r"^\.decision-head\.stage\.[a-f0-9]{16}(?:\.abort\.[a-f0-9]{16})?$")
    for parent, pattern, kind in (
        (bundle_parent, bundle_stage, "bundle"),
        (namespace, head_stage, "head"),
    ):
        for name in _directory_entries(root, parent) or []:
            if not pattern.fullmatch(name):
                continue
            relative = f"{parent}/{name}"
            if kind == "bundle":
                raw = _safe_read(root, f"{relative}/bundle-manifest-v1.json")
                if raw is None:
                    raise _decision_authority_error()
                manifest = _canonical_object(raw, "staged rollout decision bundle")
                bundle_id = manifest.get("bundleId")
                if not isinstance(bundle_id, str):
                    raise _decision_authority_error()
                _load_decision_bundle(
                    root, identity, profile, bundle_id, base_relative=relative,
                )
            else:
                if _load_decision_head(
                    root, identity, profile, base_relative=relative,
                ) is None:
                    raise _decision_authority_error()
            _remove_valid_stage(root, parent, name)


def _published_orphan_bundle(
    root: Path, identity: dict[str, object], profile: str,
) -> tuple[dict[str, object], dict[str, object], bytes, dict[str, int]] | None:
    parent = f"{_decision_namespace(identity)}/bundles"
    bundles = []
    for name in _directory_entries(root, parent) or []:
        if name.startswith("."):
            continue
        if re.fullmatch(r"B-[a-f0-9]{64}", name) is None:
            raise _decision_authority_error()
        bundles.append(_load_decision_bundle(root, identity, profile, name))
    if len(bundles) > 1:
        raise _decision_authority_error()
    return bundles[0] if bundles else None


def _publish_decision_bundle(
    root: Path, identity: dict[str, object], profile: str,
    policy: dict[str, object], policy_digest: str,
) -> tuple[dict[str, object], dict[str, object], bytes, dict[str, int]]:
    ctx = _runtime_module()
    parent = f"{_decision_namespace(identity)}/bundles"
    staging = ctx.PrivateStagingDirectory.create(root, parent, "decision-bundle")
    published = False
    try:
        snapshot_payload = _canonical(_policy_snapshot(identity, policy, policy_digest))
        artifact = _expected_decision_artifact(identity, profile, policy, policy_digest)
        decision_payload = _canonical(artifact)
        staging.write_bytes(_BUNDLE_FILES["policySnapshot"], snapshot_payload)
        snapshot_file = _staging_file_instance(
            staging, _BUNDLE_FILES["policySnapshot"], snapshot_payload,
        )
        staging.write_bytes(_BUNDLE_FILES["rolloutDecision"], decision_payload)
        decision_file = _staging_file_instance(
            staging, _BUNDLE_FILES["rolloutDecision"], decision_payload,
        )
        receipt_body = {
            "schemaVersion": DECISION_RECEIPT_VERSION,
            "executionIdentityDigest": _sha256(_canonical(identity)),
            "policySnapshot": {
                "path": _BUNDLE_FILES["policySnapshot"],
                "digest": _sha256(snapshot_payload),
                "fileInstance": snapshot_file,
            },
            "rolloutDecision": {
                "path": _BUNDLE_FILES["rolloutDecision"],
                "digest": _sha256(decision_payload),
                "fileInstance": decision_file,
            },
        }
        receipt = {**receipt_body, "receiptId": _receipt_id(receipt_body)}
        receipt_payload = _canonical(receipt)
        staging.write_bytes(_BUNDLE_FILES["decisionReceipt"], receipt_payload)
        receipt_file = _staging_file_instance(
            staging, _BUNDLE_FILES["decisionReceipt"], receipt_payload,
        )
        provisional = {
            "policySnapshot": {"path": _BUNDLE_FILES["policySnapshot"], "digest": _sha256(snapshot_payload), "fileInstance": snapshot_file},
            "rolloutDecision": {"path": _BUNDLE_FILES["rolloutDecision"], "digest": _sha256(decision_payload), "fileInstance": decision_file},
            "decisionReceipt": {"path": _BUNDLE_FILES["decisionReceipt"], "digest": _sha256(receipt_payload), "fileInstance": receipt_file},
        }
        bundle_id = _new_bundle_id()
        bundle_path = f"{parent}/{bundle_id}"
        artifacts = {
            role: {**record, "path": f"{bundle_path}/{_BUNDLE_FILES[role]}"}
            for role, record in provisional.items()
        }
        manifest = {
            "schemaVersion": DECISION_BUNDLE_VERSION,
            "bundleId": bundle_id,
            "bundlePath": bundle_path,
            **identity,
            "profileId": profile,
            "policyId": "runtime-selection-v1",
            "policyVersion": POLICY_VERSION,
            "policySnapshotDigest": _sha256(snapshot_payload),
            "rolloutDecisionDigest": _sha256(decision_payload),
            "receiptDigest": _sha256(receipt_payload),
            "configuredMode": artifact["configuredMode"],
            "effectiveMode": artifact["effectiveMode"],
            "previousAuthorityReference": None,
            "receiptId": receipt["receiptId"],
            "childCommitmentsDigest": _sha256(_canonical(artifacts)),
            "artifacts": artifacts,
        }
        manifest_payload = _canonical(manifest)
        staging.write_bytes("bundle-manifest-v1.json", manifest_payload)
        _staging_file_instance(staging, "bundle-manifest-v1.json", manifest_payload)
        os.fsync(staging._staging_fd)
        staged_relative = f"{parent}/{staging._name}"
        _load_decision_bundle(
            root, identity, profile, bundle_id, base_relative=staged_relative,
        )
        _decision_sync("after-bundle-staging")
        staging.publish_noreplace(bundle_id)
        staging.commit_publication()
        published = True
        _decision_sync("after-bundle-publication-pre-head")
    finally:
        try:
            staging.cleanup()
        finally:
            staging.close()
    if not published:
        raise _decision_authority_error()
    return _load_decision_bundle(root, identity, profile, bundle_id)


def _publish_decision_head(
    root: Path, identity: dict[str, object], profile: str,
    bundle: tuple[dict[str, object], dict[str, object], bytes, dict[str, int]],
) -> dict[str, object]:
    ctx = _runtime_module()
    artifact, manifest, manifest_raw, manifest_file = bundle
    namespace = _decision_namespace(identity)
    manifest_path = f"{manifest['bundlePath']}/bundle-manifest-v1.json"
    head_body = {
        "schemaVersion": DECISION_HEAD_VERSION,
        **identity,
        "profileId": profile,
        "bundleId": manifest["bundleId"],
        "bundlePath": manifest["bundlePath"],
        "bundleDigest": _sha256(manifest_raw),
        "bundleManifest": _file_commitment(manifest_path, manifest_raw, manifest_file),
        "configuredMode": artifact["configuredMode"],
        "effectiveMode": artifact["effectiveMode"],
        "childCommitmentsDigest": manifest["childCommitmentsDigest"],
        "previousAuthorityReference": None,
    }
    head = {**head_body, "authorityId": _authority_id(head_body)}
    head_payload = _canonical(head)
    staging = ctx.PrivateStagingDirectory.create(root, namespace, "decision-head")
    published = False
    try:
        staging.write_bytes("decision-head-v1.json", head_payload)
        head_file = _staging_file_instance(staging, "decision-head-v1.json", head_payload)
        commit = {
            "schemaVersion": DECISION_HEAD_COMMIT_VERSION,
            "authorityId": head["authorityId"],
            "executionIdentityDigest": _sha256(_canonical(identity)),
            "headPath": _decision_head_path(identity, "decision-head-v1.json"),
            "headDigest": _sha256(head_payload),
            "headFile": head_file,
            "bundleManifestPath": manifest_path,
            "bundleManifestDigest": _sha256(manifest_raw),
            "bundleManifestFile": manifest_file,
        }
        commit_payload = _canonical(commit)
        staging.write_bytes("decision-head-commit-v1.json", commit_payload)
        _staging_file_instance(staging, "decision-head-commit-v1.json", commit_payload)
        os.fsync(staging._staging_fd)
        staged_relative = f"{namespace}/{staging._name}"
        if _load_decision_head(
            root, identity, profile, base_relative=staged_relative,
        ) is None:
            raise _decision_authority_error()
        _decision_sync("after-head-staging")
        _decision_sync("before-head-cas")
        staging.publish_noreplace("HEAD")
        _decision_sync("during-head-cas")
        staging.commit_publication()
        published = True
        _decision_sync("after-head-cas-pre-cleanup")
    finally:
        try:
            staging.cleanup()
        finally:
            staging.close()
    if not published:
        raise _decision_authority_error()
    committed = _load_decision_head(root, identity, profile)
    if committed is None:
        raise _decision_authority_error()
    return committed


def materialize_decision(root: Path, profile: str, execution_id: str, execution_version: int,
                         workspace_id: str) -> dict[str, object]:
    identity = _decision_identity(execution_id, execution_version, workspace_id, profile, root)
    ctx = _runtime_module()
    with ctx.stable_file_lock(root, LOCK_RELATIVE):
        try:
            _reconcile_parent_staging(root, identity)
            _decision_sync("during-reconciliation")
            intent_path, _ = _intent_paths(identity)
            intent_absent = _safe_read(root, intent_path) is None
            if str(identity["executionId"]).startswith("execution-"):
                run_raw = _safe_read(
                    root, f".mana/runtime/runs/{identity['executionId']}/run-directory-v1.json")
                if run_raw is not None and intent_absent:
                    raise _decision_authority_error()
            if intent_absent and _directory_entries(root, _intent_namespace(identity)) is not None:
                raise _decision_authority_error()
            if intent_absent and _directory_entries(root, _decision_namespace(identity)):
                # Old CTX-10-only executions cannot be promoted retroactively.
                raise _decision_authority_error()
            intent = _ensure_intent(root, identity, profile)
            _verify_ctx06_intent_link(root, identity, profile, intent)
            existing = _load_selection(root, identity, profile, intent)
        except DecisionAuthorityError:
            raise
        except (OSError, KeyError, TypeError, RolloutError) as error:
            raise _decision_authority_error() from error
        if existing is not None:
            return existing
        previous_head = _load_decision_head(root, identity, profile)
        if previous_head is not None:
            expected = _expected_decision_artifact(
                identity, profile, intent[0]["policy"], intent[0]["policyDigest"])
            if previous_head != expected:
                raise _decision_authority_error()
            return _publish_selection(root, identity, profile, intent)
        try:
            _reconcile_decision_staging(root, identity, profile)
            orphan = _published_orphan_bundle(root, identity, profile)
        except DecisionAuthorityError:
            raise
        except (OSError, KeyError, TypeError, RolloutError) as error:
            raise _decision_authority_error() from error
        if orphan is None:
            orphan = _publish_decision_bundle(
                root, identity, profile, intent[0]["policy"], intent[0]["policyDigest"],
            )
        expected = _expected_decision_artifact(
            identity, profile, intent[0]["policy"], intent[0]["policyDigest"])
        if orphan[0] != expected:
            raise _decision_authority_error()
        # Re-attest the complete published bundle immediately before the one
        # no-replace parent HEAD CAS.  Publication alone never grants authority.
        bundle_id = orphan[1]["bundleId"]
        orphan = _load_decision_bundle(root, identity, profile, bundle_id)
        _publish_decision_head(root, identity, profile, orphan)
        return _publish_selection(root, identity, profile, intent)


def execution_identity(
    root: Path, execution_id: str, framework_root: Path,
    expected_profile: str | None = None,
) -> dict[str, object]:
    """Read the CTX-06 initialized run; CLI text alone is never authority."""
    if not re.fullmatch(r"execution-[A-Za-z0-9._-]{1,120}", execution_id):
        raise RolloutError(
            "CTX10_EXECUTION_AUTHORITY_REJECTED: supplied CTX-06 execution identity is invalid"
        )
    # This is deliberately a read-only existence gate before the CTX-06 reader
    # is imported.  In particular it cannot create the run directory or the
    # provider-phase lock for a caller-supplied but nonexistent identity.
    run_record = _safe_read(
        root, f".mana/runtime/runs/{execution_id}/run-directory-v1.json"
    )
    if run_record is None:
        raise RolloutError(
            "CTX10_EXECUTION_NOT_INITIALIZED: context runtime v2 requires an initialized CTX-06 execution identity"
        )
    pipeline = _pipeline_module()
    args = argparse.Namespace(project_root=str(root), framework_root=str(framework_root),
                              execution_id=execution_id, static_signal=[], request_skill=[], deep_load_skill=[])
    try:
        context = pipeline._load_run_context(args)
    except Exception as error:
        # CTX-06 has its own dynamically loaded ContractError type.  Normalize
        # its known authority failures here rather than leaking its traceback,
        # absolute paths, or Python stack through the public wrapper.
        contract_error = getattr(getattr(pipeline, "runtime", None), "ContractError", ())
        if contract_error and isinstance(error, contract_error):
            raise RolloutError(
                "CTX10_EXECUTION_AUTHORITY_REJECTED: supplied CTX-06 execution authority was rejected"
            ) from error
        if isinstance(error, (OSError, ValueError, RuntimeError, KeyError, TypeError)):
            raise RolloutError(
                "CTX10_EXECUTION_AUTHORITY_REJECTED: supplied CTX-06 execution authority was rejected"
            ) from error
        raise
    envelope = context.envelope
    if expected_profile is not None and envelope["profileId"] != expected_profile:
        raise RolloutError(
            "CTX10_EXECUTION_AUTHORITY_REJECTED: supplied CTX-06 execution authority was rejected"
        )
    if (_safe_read(root, POLICY_RELATIVE) is not None
            and envelope.get("schemaVersion") != "mana.context-runtime.execution-envelope/v2"):
        # A pre-R2.5 run remains a valid CTX-06 record, but cannot prove a
        # retrospectively invented rollout decision.
        raise RolloutError(
            "CTX10_EXECUTION_AUTHORITY_REJECTED: supplied CTX-06 execution authority was rejected"
        )
    return {"executionId": envelope["executionId"], "executionVersion": envelope["executionVersion"],
            "workspaceId": envelope["workspaceId"], "profileId": envelope["profileId"]}


def legacy_execution_identity(root: Path, profile: str,
                              existing_id: str | None = None) -> dict[str, object]:
    """Bounded host-generated identity for one legacy invocation only.

    It is intentionally random host state, not a profile/timestamp/environment
    derivation.  The workspace binding is the host-owned root object's local
    identity, which prevents a copied decision from being selected elsewhere.
    """
    token = os.urandom(16).hex()
    if existing_id is not None and re.fullmatch(r"legacy-[A-Za-z0-9._-]{1,120}", existing_id) is None:
        raise _decision_authority_error()
    binding = _project_root_binding(root)
    workspace = "W-" + hashlib.sha256(("legacy-invocation:" + binding).encode()).hexdigest()
    return {"executionId": existing_id or "legacy-" + token, "executionVersion": 1,
            "workspaceId": workspace, "profileId": profile}


PROVIDERS = {
    "codex": (".codex/config.toml", "# ", "codex-runtime-v2", "Mana runtime-v2 rollout metadata. Runtime mode is selected only by the host-owned profile policy."),
    "claude": ("CLAUDE.md", "# ", "claude-runtime-v2", "Mana runtime-v2 rollout metadata. Runtime mode is selected only by the host-owned profile policy."),
    "opencode": ("opencode.jsonc", "// ", "opencode-runtime-v2", "Mana runtime-v2 rollout metadata. Runtime mode is selected only by the host-owned profile policy."),
}


def _warning(code: str, severity: str, profile: str, runtime: str, reason: str, action: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "profileId": profile, "currentRuntime": runtime,
            "reason": reason, "recommendedNextAction": action}


def _capability_report(root: Path) -> tuple[dict[str, object] | None, str]:
    raw = _safe_read(root, ".mana/runtime/provider-capabilities-v1.json")
    if raw is None:
        return None, "unavailable"
    try:
        value = json.loads(raw)
        _runtime_module().validate_structure("provider-capabilities", value)
        return value, "current"
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None, "invalid"


def _profile_diagnostics(root: Path, policy: dict[str, object] | None, policy_state: str,
                         providers: dict[str, object]) -> list[dict[str, object]]:
    selections = (policy or {"profiles": {}})["profiles"]
    capabilities, capability_state = _capability_report(root)
    values: list[dict[str, object]] = []
    for profile in sorted({"default", *selections.keys()}):
        declared = profile in selections
        selection = selections.get(profile, {})
        configured = selection.get("mode", "inherited")
        effective = "legacy" if configured == "inherited" or policy_state == "invalid" else configured
        warnings, gaps = [], []
        if policy_state == "invalid":
            warnings.append(_warning("CTX10_INVALID_POLICY", "warning", profile, effective, "the host-owned runtime policy does not validate", "restore a valid legacy-default policy before opting in"))
        elif policy_state == "missing":
            warnings.append(_warning("CTX10_BOOTSTRAP_STALE", "info", profile, effective, "runtime policy is not materialized", "materialize policy only through explicit bootstrap"))
        if not Path(__file__).with_name("run-profile-v2.sh").is_file():
            warnings.append(_warning("CTX10_PIPELINE_V2_ABSENT", "info", profile, effective, "the v2 pipeline entry point is unavailable", "install a compatible pipeline before explicit v2 selection"))
        if configured == "legacy" and selection.get("exempted", False):
            warnings.append(_warning("profile-exempted", "info", profile, effective, "profile is explicitly exempted from v2 rollout", "retain legacy or remove the exemption through explicit policy change"))
        elif configured == "legacy":
            warnings.append(_warning("profile-pinned-legacy", "info", profile, effective, "profile is explicitly pinned to legacy", "make a deliberate per-profile opt-in only after readiness is established"))
        elif configured == "inherited" and declared:
            warnings.append(_warning("inherited-legacy", "info", profile, effective, "profile inherits the global legacy default", "make a deliberate per-profile opt-in only after readiness is established"))
        elif effective == "legacy":
            warnings.append(_warning("global-default-legacy", "info", profile, effective, "legacy remains the global default", "make a deliberate per-profile opt-in only after readiness is established"))
        if effective in {"v2", "shadow", "compare"}:
            try:
                # Compilation is a dry validation of host-owned sources.  It
                # has no publication path and cannot select or enable v2.
                _runtime_module().compile_context_manifest(root, profile, "execution-doctor-validation")
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                warnings.append(_warning("CTX10_MANIFEST_NOT_COMPILABLE", "warning", profile, effective, "profile manifest cannot be compiled from authoritative local sources", "repair the profile declaration before using this runtime"))
            if capability_state != "current":
                gaps.append("provider-capability-report-" + capability_state)
                warnings.append(_warning("CTX10_PROVIDER_CAPABILITY_GAP", "warning", profile, effective, "no valid provider capability report is materialized", "run the explicit capability probe and review its bounded report"))
            elif capabilities is not None and any(item["status"] != "supported" for item in capabilities["capabilities"].values()):
                gaps.append("provider-capability-gap")
                warnings.append(_warning("CTX10_PROVIDER_CAPABILITY_GAP", "warning", profile, effective, "required provider capabilities are unsupported or unknown", "use legacy for this profile or establish the missing capabilities"))
        for provider, state in sorted(providers.items()):
            if not state["installed"]:
                warnings.append(_warning("CTX10_PROVIDER_UNAVAILABLE", "info", profile, effective, "provider executable is unavailable", "install or select an available provider without changing runtime policy"))
            elif state["managedBlock"] == "missing":
                warnings.append(_warning("CTX10_MANAGED_BLOCK_MISSING", "info", profile, effective, "provider rollout metadata is not materialized", "use explicit bootstrap if this provider is intentionally prepared"))
            elif state["managedBlock"] == "stale":
                warnings.append(_warning("CTX10_BOOTSTRAP_STALE", "warning", profile, effective, "provider rollout metadata is stale", "refresh only the bounded managed block through explicit bootstrap"))
            elif state["managedBlock"] == "future":
                warnings.append(_warning("CTX10_MANAGED_BLOCK_FUTURE", "warning", profile, effective, "provider rollout metadata is newer than this runtime", "upgrade Mana or recover the block manually; do not overwrite it"))
        readiness = "ready" if effective == "legacy" and policy_state != "invalid" else ("blocked" if gaps else "unavailable" if policy_state != "current" else "ready")
        disposition, migration_warning = _migration_metadata(configured, bool(selection.get("exempted", False)), declared=declared)
        values.append({"profileId": profile, "configuredSelection": configured, "inheritedDefault": configured == "inherited", "effectiveRuntime": effective, "migrationDisposition": disposition, "migrationWarning": migration_warning, "readiness": readiness, "blockingCapabilityGaps": gaps, "bootstrapState": policy_state, "migrationWarnings": warnings})
    return values


def status(root: Path) -> dict[str, object]:
    try:
        policy, policy_state = load_policy(root)
    except RolloutError:
        policy, policy_state = None, "invalid"
    providers = {}
    for name, (relative, _prefix, block_id, _content) in PROVIDERS.items():
        installed = shutil.which(name) is not None
        if not installed:
            providers[name] = {"installed": False, "managedBlock": "unavailable", "warning": "provider-not-installed"}
            continue
        try:
            raw = _safe_read(root, relative) or b""
            block = next((item for item in _parse_blocks(raw) if item["id"] == block_id), None)
            state = "missing" if block is None else "future" if int(block["version"]) > VERSION else "stale" if int(block["version"]) < VERSION else "current"
        except RolloutError:
            state = "invalid"
        providers[name] = {"installed": True, "managedBlock": state, "warning": None}
    links = root / ".mana/links"
    try:
        link_meta = links.lstat()
        linked = stat.S_ISDIR(link_meta.st_mode) and not stat.S_ISLNK(link_meta.st_mode) and any(entry.is_symlink() for entry in links.iterdir())
    except FileNotFoundError:
        linked = False
    diagnostics = _profile_diagnostics(root, policy, policy_state, providers)
    return {"schemaVersion": "mana.context-runtime.rollout-status/v1", "legacyAvailable": True, "v2Available": (Path(__file__).with_name("run-profile-v2.sh").is_file()), "policy": policy_state, "profiles": sorted((policy or {"profiles": {}})["profiles"].keys()), "profileDiagnostics": diagnostics, "providers": providers, "noLinks": not linked, "budget": "provisional-no-empirical-baseline", "capabilityReport": _capability_report(root)[1] == "current", "usageMetrics": (root / ".mana/runtime/metrics").is_dir()}


def _json_artifact(root: Path, relative: str) -> tuple[dict[str, object] | None, str]:
    raw = _safe_read(root, relative)
    if raw is None:
        return None, "missing"
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid"
    return (value, "available") if isinstance(value, dict) else (None, "invalid")


def _surface(root: Path, paths: list[str], validator, identity, summary) -> dict[str, object]:
    for relative in paths:
        value, state = _json_artifact(root, relative)
        if state == "missing":
            continue
        if state != "available":
            return {"status": "invalid", "reason": "malformed-artifact"}
        try:
            validator(value)
            if not identity(value):
                return {"status": "foreign", "reason": "identity-mismatch"}
            return {"status": "current", **summary(value)}
        except (ValueError, KeyError, TypeError):
            return {"status": "invalid", "reason": "schema-or-validator-rejected"}
    return {"status": "unavailable", "reason": "not-materialized"}


def _ctx09_surfaces(root: Path, profile: str, execution: str) -> tuple[dict[str, object], dict[str, object]]:
    """Read CTX-09 records only through its own canonical readers.

    The registration names both producer paths.  Consequently inspect neither
    guesses receipt locations nor accepts a receipt merely because it parses.
    """
    mode, comparison = _ctx09_mode_module(), _ctx09_comparison_module()
    try:
        with mode.HostRoot(str(root)) as host:
            _registration_meta, plan = comparison.registration(host, execution)
            expected = plan["artifacts"]
            if any(expected[side]["profileId"] != profile for side in ("legacy", "v2")):
                return ({"status": "foreign", "reason": "profile-or-target-identity-mismatch"},
                        {"status": "foreign", "reason": "profile-or-target-identity-mismatch"})
            sources = {}
            for side in ("legacy", "v2"):
                entry = expected[side]
                sources[side] = mode.producer_source(
                    host, execution, entry["path"], side, profile_id=profile,
                    target_key=entry["targetKey"], execution_version=entry["executionVersion"],
                )
                if sources[side] != entry:
                    raise mode.runtime.ContractError("comparison registration binding changed")
            # Recompute with CTX-09B and compare the exact canonical bytes to
            # the already published report.  This validates artifact, receipt,
            # commit, path and local file-instance commitments again.
            expected_report = comparison.run(str(root), execution, write_report=False)
            report_path = f"{mode.NAMESPACE}/{execution}/{comparison.REPORT_FILE}"
            _metadata, report_bytes = mode.project_file(host, report_path, with_bytes=True,
                                                         private=True, max_bytes=comparison.MAX_REPORT)
            report = comparison.strict_json(report_bytes)
            comparison.Contracts().validate(report, comparison.REPORT_SCHEMA)
            if mode.canonical(report) != report_bytes or report_bytes != expected_report:
                raise mode.runtime.ContractError("comparison report is stale or altered")
            receipt = {"status": "current", "receiptSchema": mode.RECEIPT_VERSION,
                       "roles": ["legacy", "v2"], "artifactCount": 2}
            bounded_reasons = [value for value in report["reasons"] if isinstance(value, str) and len(value) <= 96]
            comparison_surface = {"status": "current", "comparisonStatus": report["status"],
                                  "complete": report["complete"], "dimensionCount": len(report["dimensions"]),
                                  "reasons": bounded_reasons}
            return receipt, comparison_surface
    except FileNotFoundError:
        # A comparison registration without every committed producer/report is
        # incomplete, not an authority.  With no canonical registration it is
        # simply unavailable.
        plan_path = root / mode.NAMESPACE / execution / "mode-plan-v1.json"
        producer_path = root / mode.PRODUCERS / execution
        status = "partial" if plan_path.exists() or producer_path.exists() else "unavailable"
        reason = "canonical-artifact-not-materialized" if status == "partial" else "not-materialized"
        return ({"status": status, "reason": reason}, {"status": status, "reason": reason})
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, mode.runtime.ContractError):
        # A valid plan whose producer chain/recomputed report no longer binds
        # the current execution is stale; malformed/unsafe material is invalid.
        plan_path = root / mode.NAMESPACE / execution / "mode-plan-v1.json"
        status = "stale" if plan_path.exists() else "invalid"
        return ({"status": status, "reason": "ctx09-authority-rejected"},
                {"status": status, "reason": "ctx09-authority-rejected"})


def _run_state_status(root: Path, profile: str, execution: str, framework_root: Path | None = None) -> tuple[dict[str, object] | None, str, str]:
    candidate, state = _json_artifact(root, f".mana/runtime/runs/{execution}/run-state-v1.json")
    if state == "missing":
        return None, "missing", "not-materialized"
    if state != "available":
        return None, "invalid", "malformed-json"
    required = {"schemaVersion", "executionId", "executionVersion", "profileId", "revision", "status", "currentPhaseId", "currentPhaseOrdinal", "currentAttempt", "latestCheckpointRef", "transitionId", "previousStateDigest", "attempts"}
    if not required <= set(candidate):
        return None, "partial", "required-run-state-fields-missing"
    try:
        _runtime_module().validate_structure("run-state", candidate)
    except ValueError:
        return None, "invalid", "run-state-schema-rejected"
    if candidate["executionId"] != execution or candidate["profileId"] != profile:
        return None, "foreign", "execution-or-profile-mismatch"
    try:
        pipeline = _pipeline_module()
        args = argparse.Namespace(project_root=str(root), framework_root=str(framework_root or root), execution_id=execution, static_signal=[], request_skill=[], deep_load_skill=[])
        context = pipeline._load_run_context(args)
        selected = preview_policy(root, profile)["mode"]
        compatible_envelope_modes = {selected}
        if selected == "v2":
            compatible_envelope_modes.add("context-v2")
        if context.envelope["runtimeMode"] not in compatible_envelope_modes:
            return None, "stale", "current-policy-runtime-mismatch"
        pipeline._committed_transition_ids(context, pipeline._published_bundles(context), args)
        return context.state, "current", "validated-schema-identity-head-and-bundle-chain"
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return None, "stale", "authoritative-chain-or-parent-re-attestation-failed"


def inspect(root: Path, profile: str, execution: str | None, framework_root: Path | None = None) -> dict[str, object]:
    decision = preview_policy(root, profile)
    run_state: dict[str, object] | None = None
    artifact_status, artifact_reason = "missing", "not-requested"
    unavailable = {"status": "unavailable", "reason": "execution-not-requested"}
    usage, delegation, receipt = unavailable, unavailable, unavailable
    comparison = {"status": "not-requested" if decision["mode"] in {"legacy", "v2"} else "unavailable", "reason": "execution-not-requested"}
    if execution is not None:
        if not re.fullmatch(r"execution-[A-Za-z0-9._-]{1,120}", execution):
            raise RolloutError("execution identity is invalid")
        run_state, artifact_status, artifact_reason = _run_state_status(root, profile, execution, framework_root)
        ctx = _runtime_module()
        usage = _surface(root, [f".mana/runtime/metrics/{execution}/usage-summary-v1.json"], lambda v: ctx.validate_model("usage-summary", v), lambda v: v["executionId"] == execution and v["profileId"] == profile, lambda v: {"usageStatus": v["usageStatus"], "totals": v["totals"], "turns": v["turns"], "toolCalls": v["toolCalls"], "workers": v["workers"], "compactions": v["compactions"]})
        delegation = _surface(root, [f".mana/runtime/runs/{execution}/delegation-merge-v1.json", f".mana/runtime/runs/{execution}/delegation/delegation-merge-v1.json"], lambda v: ctx.validate_structure("delegation-merge", v), lambda v: v["executionId"] == execution and v["profileId"] == profile, lambda v: {"mergeStatus": v["mergeStatus"], "taskCount": len(v["taskResults"]), "missingTaskCount": len(v["missingTaskIds"])})
        receipt, comparison = _ctx09_surfaces(root, profile, execution)
    return {"schemaVersion": "mana.context-runtime.inspect-rollout/v1", "runtimeMode": decision["mode"], "profileRuntimeSelection": {"profileId": profile, "configuredMode": decision["configuredMode"], "policyStatus": decision["policyStatus"]}, "executionIdentity": None if run_state is None else {"executionId": run_state["executionId"], "executionVersion": run_state["executionVersion"], "profileId": run_state["profileId"]}, "phase": {"current": None if run_state is None else run_state["currentPhaseId"], "ordinal": None if run_state is None else run_state["currentPhaseOrdinal"], "attempt": None if run_state is None else run_state["currentAttempt"]}, "checkpoint": {"latestRef": None if run_state is None else run_state["latestCheckpointRef"]}, "runState": {"status": artifact_status if run_state is None else run_state["status"], "artifactStatus": artifact_status, "reason": artifact_reason}, "usage": usage, "budget": {"status": "provisional-no-empirical-baseline", "decision": "advisory-only"}, "delegation": delegation, "shadowComparison": comparison, "producerReceipt": receipt, "artifacts": {"status": artifact_status, "reason": artifact_reason}, "guarantees": {"modelCalls": 0, "writes": False, "rawEvidence": False, "rawTrace": False, "rawProviderConfig": False}}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="CTX-10 local rollout boundary")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("bootstrap", "status"):
        item = sub.add_parser(command); item.add_argument("--project-root", required=True)
    item = sub.add_parser("candidate"); item.add_argument("--project-root", required=True); item.add_argument("--profile", required=True); item.add_argument("--requested-mode"); item.add_argument("--execution-id")
    item = sub.add_parser("resolve"); item.add_argument("--project-root", required=True); item.add_argument("--profile", required=True); item.add_argument("--requested-mode"); item.add_argument("--execution-id"); item.add_argument("--execution-version", type=int); item.add_argument("--workspace-id")
    item = sub.add_parser("materialize-decision"); item.add_argument("--project-root", required=True); item.add_argument("--profile", required=True); item.add_argument("--execution-id", required=True); item.add_argument("--execution-version", required=True, type=int); item.add_argument("--workspace-id", required=True)
    item = sub.add_parser("execution-identity"); item.add_argument("--project-root", required=True); item.add_argument("--execution-id", required=True); item.add_argument("--framework-root", required=True); item.add_argument("--profile")
    item = sub.add_parser("legacy-execution-identity"); item.add_argument("--project-root", required=True); item.add_argument("--profile", required=True); item.add_argument("--execution-id")
    item = sub.add_parser("inspect"); item.add_argument("--project-root", required=True); item.add_argument("--profile", required=True); item.add_argument("--execution"); item.add_argument("--framework-root")
    item = sub.add_parser("refresh-block"); item.add_argument("--project-root", required=True); item.add_argument("--target", required=True); item.add_argument("--block-id", required=True); item.add_argument("--content", required=True); item.add_argument("--comment-prefix", default="# "); item.add_argument("--fault", choices=["after-read", "after-parse", "during-managed-block-replacement", "before-publication", "during-publication", "after-publication-pre-cleanup"])
    args = parser.parse_args(argv)
    try:
        root = Path(args.project_root).resolve(strict=True)
        if not root.is_dir() or root.is_symlink():
            raise RolloutError("project root is unsafe")
        if args.command == "resolve":
            identity = None
            supplied = (args.execution_id, args.execution_version, args.workspace_id)
            if any(value is not None for value in supplied):
                if any(value is None for value in supplied):
                    raise RolloutError("complete execution identity is required")
                identity = _decision_identity(args.execution_id, args.execution_version, args.workspace_id, args.profile, root)
            result = resolve(root, args.profile, args.requested_mode, identity)
        elif args.command == "candidate":
            result = candidate(root, args.profile, args.requested_mode, args.execution_id)
        elif args.command == "materialize-decision":
            result = materialize_decision(root, args.profile, args.execution_id, args.execution_version, args.workspace_id)
        elif args.command == "execution-identity":
            framework_root = Path(args.framework_root).resolve(strict=True)
            result = execution_identity(root, args.execution_id, framework_root, args.profile)
        elif args.command == "legacy-execution-identity":
            result = legacy_execution_identity(root, args.profile, args.execution_id)
        elif args.command == "inspect":
            framework_root = None if args.framework_root is None else Path(args.framework_root).resolve(strict=True)
            result = inspect(root, args.profile, args.execution, framework_root)
        elif args.command == "status":
            result = status(root)
        elif args.command == "refresh-block":
            result = _refresh_block_with_retry(
                root, args.target, args.block_id, args.content,
                args.comment_prefix, args.fault,
            )
            if result["state"] == "future":
                print(json.dumps(result, sort_keys=True)); return 2
        else:
            if _safe_read(root, POLICY_RELATIVE) is None:
                _atomic_replace(root, POLICY_RELATIVE, _policy_default(), source=None)
            load_policy(root)
            provider_results = {}
            for name, (relative, prefix, block_id, content) in PROVIDERS.items():
                if shutil.which(name) is None:
                    provider_results[name] = {"state": "unavailable", "changed": False, "warning": "provider-not-installed"}
                else:
                    provider_results[name] = _refresh_block_with_retry(root, relative, block_id, content, prefix)
            if any(value["state"] == "future" for value in provider_results.values()):
                raise RolloutError("future managed provider block requires manual upgrade")
            result = {"policy": "current", "providers": provider_results}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, RolloutError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 2
    except Exception as error:
        ctx = _runtime_module()
        if isinstance(error, ctx.RollbackFailure):
            print("ERROR: " + json.dumps(error.as_dict(), sort_keys=True), file=sys.stderr)
            return 2
        if isinstance(error, ctx.ContractError):
            print("ERROR: " + str(error), file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
