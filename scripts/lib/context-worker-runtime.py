#!/usr/bin/env python3
"""CTX-07B host-owned worker authority and durable task state.

The production trust root is the canonical installation containing this
module.  Alternate framework roots are accepted only by the explicitly
test-only entry points in ``tests/``; this module's production CLI has no such
surface.
"""
from __future__ import annotations

import argparse
import hashlib
import fcntl
import re
from contextlib import contextmanager
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
HOST_FRAMEWORK_ROOT = HERE.parent.parent
HOST_CONTRACT_ROOT = HERE.parent.parent


def _load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load("mana_context_runtime_workers", "context-runtime.py")
delegation = _load("mana_context_delegation_workers", "context-delegation.py")

PREPARED_SCHEMA = "mana.context-runtime.worker-plan-execution/v1"
PACKET_SCHEMA = "mana.context-runtime.worker-context-packet/v1"
POLICY_SCHEMA = "mana.context-runtime.worker-routing-policy/v1"
POLICY_RELATIVE_PATH = Path("config/context-runtime/worker-routing-policy-v1.json")
DEBUG_POLICY_SCHEMA = "mana.context-runtime.worker-debug-policy/v1"
DEBUG_POLICY_RELATIVE_PATH = Path("config/context-runtime/worker-debug-policy-v1.json")
MANAGED_CHILD_RECEIPT_SCHEMA = "mana.context-runtime.managed-child-receipt/v1"
MANAGED_CHILD_BINDING_SCHEMA = "mana.context-runtime.managed-child-result-binding/v1"
MAX_POLICY_BYTES = 64 * 1024
MAX_PACKET_BYTES = 256 * 1024
MAX_SKILL_BODY_BYTES = 64 * 1024
MAX_EVIDENCE_EXTRACT_BYTES = 16 * 1024
# These are deliberately code-owned operational policy, rather than CLI or
# provider settings.  A future policy version may make them data driven, but
# callers must never be able to lengthen an invocation or a stale claim.
WORKER_TIMEOUT_SECONDS = 120
WORKER_KILL_GRACE_SECONDS = 5
WORKER_CLAIM_LEASE_SECONDS = 300
HIGH_RISK_DOMAINS = {"architecture", "contracts", "database", "operations", "security"}
RISK_ORDER = {"unspecified": 0, "low": 1, "medium": 2, "high": 3}
RESULT_DRAFT_FIELDS = {
    "schemaVersion", "taskId", "status", "verifiedFacts", "findings",
    "assumptions", "inferences", "openQuestions", "evidenceGaps",
    "artifactRefs", "uncertainty",
}
COLLECTION_SECTIONS = {
    "verifiedFacts", "findings", "assumptions", "inferences",
    "openQuestions", "evidenceGaps", "artifactRefs",
}


def fail(message: str) -> None:
    raise runtime.ContractError(message)


def digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def task_execution_key(prepared: dict[str, Any], task: dict[str, Any]) -> str:
    """Stable host identity; taskDigest alone is intentionally insufficient."""
    identity = {
        "executionId": prepared["executionId"],
        "executionVersion": task["executionVersion"],
        "workspaceId": prepared["workspaceId"], "profileId": prepared["profileId"],
        "phaseId": prepared["phaseId"], "attempt": prepared["attempt"],
        "planId": prepared["planId"], "taskId": task["taskId"],
        "taskDigest": digest_bytes(runtime.canonical_bytes(task)),
    }
    return "W-" + hashlib.sha256(runtime.canonical_bytes(identity)).hexdigest()


def _project_root(project_root: str) -> Path:
    root = Path(os.path.abspath(project_root))
    runtime.validate_secure_root(root)
    return root


def _execution_relative(key: str, suffix: str | None = None) -> str:
    if re.fullmatch(r"W-[0-9a-f]{64}", key) is None:
        fail("invalid worker execution key")
    base = f".mana/runtime/worker-executions/{key}"
    return base if suffix is None else f"{base}/{suffix}"


def _ensure_execution_dir(project_root: str, key: str) -> Path:
    root = _project_root(project_root)
    runtime.ensure_secure_directory(root, _execution_relative(key))
    return root


def _read_relative(root: Path, relative: str, *, max_bytes: int = MAX_PACKET_BYTES * 8) -> bytes:
    return runtime.safe_read_bytes(Path(relative), project_root=root, max_bytes=max_bytes)


def _read_json_relative(root: Path, relative: str, *, max_bytes: int = MAX_PACKET_BYTES * 8) -> tuple[dict[str, Any], bytes]:
    payload = _read_relative(root, relative, max_bytes=max_bytes)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot decode worker state: {error}")
    if not isinstance(value, dict):
        fail("worker state must be an object")
    return value, payload


def _publish_json(root: Path, relative: str, value: dict[str, Any], *, immutable: bool = False,
                  expected_current: bytes | None | object = runtime._EXPECTED_CURRENT_UNSET) -> Path:
    payload = runtime.canonical_bytes(value) + b"\n"
    # Exact immutable retries are idempotent; a different object is a conflict.
    if immutable:
        try:
            existing = _read_relative(root, relative)
        except runtime.ContractError as error:
            if "No such file" not in str(error):
                raise
        else:
            if existing != payload:
                fail("conflicting immutable worker artifact")
            return root / relative
    return runtime.atomic_write_bytes(root, relative, payload, immutable=immutable,
                                      expected_current=expected_current)


_HELD_LOCKS: set[tuple[str, str]] = set()


@contextmanager
def _task_lock(root: Path, key: str):
    """Only state operations are serialized; provider work never holds this lock."""
    identity = (str(root), key)
    if identity in _HELD_LOCKS:
        yield
        return
    nofollow, directory = runtime._require_secure_dir_fd_support()
    root_fd = runtime._open_directory(root, dir_fd=None, nofollow=nofollow, directory=directory)
    opened: list[int] = []
    components = _execution_relative(key).split("/")
    try:
        parent, opened = runtime._walk_existing_parent(root_fd, components, nofollow, directory)
        # Lock the already-existing task directory inode. No lock-file bootstrap,
        # publication race or bootstrap temporary can exist. Unsupported directory
        # flock fails closed, just like unsupported CTX-03 rename primitives.
        runtime._test_sync("worker-before-state-lock")
        fcntl.flock(parent, fcntl.LOCK_EX)
        if not runtime._same_existing_directory_from_root(root_fd, components, parent, nofollow, directory):
            fail("worker state lock binding changed")
        _HELD_LOCKS.add(identity)
        try:
            yield
        finally:
            _HELD_LOCKS.remove(identity)
    finally:
        for fd in reversed(opened):
            os.close(fd)
        os.close(root_fd)


def _valid_invocation(invocation: str) -> None:
    if not isinstance(invocation, str) or re.fullmatch(r"I-[0-9a-f]{32}", invocation) is None:
        fail("invalid worker invocation identity")


def _validate_claim(claim: dict[str, Any], key: str, task_digest: str | None = None) -> None:
    required = {"taskExecutionKey", "invocationId", "taskDigest", "status", "claimedAt",
                "leaseExpiresAt", "terminalAt", "terminalStatus"}
    if set(claim) != required or claim["taskExecutionKey"] != key:
        fail("worker claim is malformed or foreign")
    _valid_invocation(claim["invocationId"])
    if (not isinstance(claim["taskDigest"], str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", claim["taskDigest"]) is None
            or (task_digest is not None and claim["taskDigest"] != task_digest)):
        fail("worker claim task digest differs")
    start, expiry = claim["claimedAt"], claim["leaseExpiresAt"]
    if (type(start) is not int or type(expiry) is not int or start < 0
            or start > int(time.time()) + 5 or expiry != start + WORKER_CLAIM_LEASE_SECONDS):
        fail("worker claim lease differs from host policy")
    if claim["status"] == "active":
        if claim["terminalAt"] is not None or claim["terminalStatus"] is not None:
            fail("active worker claim has terminal state")
    elif claim["status"] == "terminal":
        if (type(claim["terminalAt"]) is not int or claim["terminalAt"] < start
                or claim["terminalStatus"] not in {"complete", "failed", "timed_out", "interrupted", "publication_failed"}):
            fail("invalid worker claim terminal state")
    else:
        fail("invalid worker claim status")


EVENTS = {"worker.claimed", "worker.started", "worker.claim.reconciled", "worker.result.accepted",
          "worker.result.reused", "worker.completed", "worker.failed", "worker.timed_out", "worker.interrupted"}


def _event(project_root: str, event_type: str, key: str, invocation_id: str | None = None,
           at: int | None = None) -> None:
    if event_type not in EVENTS:
        fail("invalid worker event")
    root = _ensure_execution_dir(project_root, key)
    with _task_lock(root, key):
        if invocation_id is not None:
            _valid_invocation(invocation_id)
            claim, _ = _read_json_relative(root, _execution_relative(key, "claim.json"))
            _validate_claim(claim, key)
            if claim["invocationId"] != invocation_id:
                fail("worker event belongs to another invocation")
            at = claim["claimedAt"] if at is None else at
            event_id = f"{invocation_id}-{event_type}.json"
        else:
            event_id = f"{time.time_ns():020d}-{uuid.uuid4().hex}.json"
        record: dict[str, Any] = {"eventType": event_type, "taskExecutionKey": key,
                                  "at": int(time.time()) if at is None else at}
        if invocation_id is not None:
            record["invocationId"] = invocation_id
        runtime.ensure_secure_directory(root, _execution_relative(key, "events"))
        _publish_json(root, _execution_relative(key, f"events/{event_id}"), record,
                      immutable=True, expected_current=None)


def _prepared_task(prepared: dict[str, Any], task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    matches = [item for item in prepared["plan"]["tasks"] if item["taskId"] == task["taskId"]]
    workers = [item for item in prepared["workers"] if item["taskId"] == task["taskId"]]
    if len(matches) != 1 or len(workers) != 1:
        fail("worker task is not uniquely present in the prepared plan")
    if runtime.canonical_bytes(matches[0]) != runtime.canonical_bytes(task):
        fail("worker task differs from the prepared authoritative task")
    return matches[0], workers[0]["contextPacket"]


def _validate_authoritative_result(
    prepared: dict[str, Any], task: dict[str, Any], result: dict[str, Any],
    *, root: Path | None = None, key: str | None = None,
    invocation_id: str | None = None, require_managed_binding: bool = False,
    head: dict[str, Any] | None = None,
) -> None:
    authoritative_task, _worker_packet = _prepared_task(prepared, task)
    provenance = result.get("executionProvenance")
    managed = isinstance(provenance, dict) and provenance.get("executionTransport") == "provider-managed-child"
    if managed:
        if root is None or key is None or invocation_id is None:
            fail("provider-managed child result requires persisted receipt authority")
        receipt = load_committed_completed_managed_child_receipt(root, key, invocation_id, prepared, task)
        if require_managed_binding:
            if head is None:
                fail("provider-managed child result binding requires authoritative HEAD")
            _validate_managed_child_binding(root, key, invocation_id, receipt, result, head)
    delegation.validate_result(
        result, prepared["authorityPacket"], prepared["plan"], authoritative_task,
        prepared.get("evidenceManifest"),
        managed_child_project_root=root if managed else None,
        managed_child_invocation_id=invocation_id if managed else None,
    )


def _read_authoritative_head(root: Path, key: str, prepared: dict[str, Any], task: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    head_relative = _execution_relative(key, "task-result-head.json")
    try:
        head, _ = _read_json_relative(root, head_relative)
    except runtime.ContractError as error:
        if "No such file" in str(error):
            return None
        raise
    required = {"schemaVersion", "taskExecutionKey", "invocationId", "resultDigest", "artifactDigest", "artifact"}
    if set(head) != required or head["schemaVersion"] != "mana.context-runtime.worker-result-head/v1" or head["taskExecutionKey"] != key:
        fail("worker task-result HEAD is malformed or foreign")
    _valid_invocation(head["invocationId"])
    artifact = head["artifact"]
    expected = f"attempts/{head['invocationId']}/result.json"
    if artifact != expected or not runtime.is_safe_relative_path(artifact):
        fail("worker task-result HEAD names an unsafe artifact")
    result_relative = _execution_relative(key, artifact)
    result, payload = _read_json_relative(root, result_relative, max_bytes=delegation.LIMITS["resultBytes"] + 1)
    _validate_authoritative_result(
        prepared, task, result, root=root, key=key,
        invocation_id=head["invocationId"], require_managed_binding=True, head=head,
    )
    canonical = runtime.canonical_bytes(result) + b"\n"
    if (payload != canonical or result["resultDigest"] != head["resultDigest"]
            or digest_bytes(runtime.canonical_bytes(result)) != head["artifactDigest"]):
        fail("worker task-result HEAD digest or canonical bytes do not match")
    return result, result_relative


def _remove_verified_temporary(root: Path, relative: str, expected: bytes) -> None:
    """A name discovers a candidate; validated bytes + held inode authorize removal."""
    nofollow, directory = runtime._require_secure_dir_fd_support()
    root_fd = runtime._open_directory(root, dir_fd=None, nofollow=nofollow, directory=directory)
    opened: list[int] = []
    fd = -1
    parts = relative.split("/")
    try:
        parent, opened = runtime._walk_existing_parent(root_fd, parts[:-1], nofollow, directory)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | nofollow, dir_fd=parent)
        info = os.fstat(fd)
        identity = runtime._entry_identity(info)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != len(expected):
            fail("worker recovery candidate is not a private regular artifact")
        if runtime._verified_regular_bytes(parent, parts[-1], identity, len(expected)) != expected:
            fail("worker recovery candidate bytes changed")
        if (not runtime._same_existing_directory_from_root(root_fd, parts[:-1], parent, nofollow, directory)
                or not runtime._verify_identity(parent, parts[-1], identity)):
            fail("worker recovery candidate binding changed")
        os.unlink(parts[-1], dir_fd=parent)
        os.fsync(parent)
    finally:
        if fd >= 0:
            os.close(fd)
        for handle in reversed(opened):
            os.close(handle)
        os.close(root_fd)


def _optional_json(root: Path, relative: str):
    try:
        return _read_json_relative(root, relative)[0]
    except runtime.ContractError as error:
        if "No such file" in str(error):
            return None
        raise


def _recover_temporaries(root: Path, key: str, prepared, task) -> None:
    """Replay only canonical, semantically bound stages under the task lock.

    Unknown, partial or foreign state is ambiguous and fails closed, never
    deleted by filename. Receipts make every downstream write reconstructible.
    """
    base = _execution_relative(key)
    directories = [base]
    for child in ("attempts", "events", "metrics"):
        relative = f"{base}/{child}"
        try:
            names = runtime.safe_list_directory(root, relative)
        except runtime.ContractError as error:
            if "No such file" in str(error):
                continue
            raise
        directories.append(relative)
        if child == "attempts":
            for name in names:
                _valid_invocation(name)
                directories.append(f"{relative}/{name}")
    candidates = []
    for relative in directories:
        for name in runtime.safe_list_directory(root, relative):
            if ".tmp." not in name:
                continue
            match = re.fullmatch(r"\.(.+\.json)\.tmp\.[0-9a-f]{16}", name)
            if match is None:
                fail("unknown worker recovery candidate")
            value, payload = _read_json_relative(root, f"{relative}/{name}")
            if payload != runtime.canonical_bytes(value) + b"\n":
                fail("noncanonical worker recovery candidate")
            candidates.append((f"{relative}/{name}", f"{relative}/{match[1]}", value, payload))
    # Recover a fully validated receipt before stages derived from it.
    candidates.sort(key=lambda item: (not item[1].endswith("/receipt.json"), item[0]))
    for relative, target, value, payload in candidates:
        current = _optional_json(root, f"{base}/claim.json")
        if current is not None:
            _validate_claim(current, key, task["taskDigest"])
        existing = _optional_json(root, target)
        filename = target.rsplit("/", 1)[-1]
        if filename == "claim.json":
            _validate_claim(value, key, task["taskDigest"])
            if current is None:
                _publish_json(root, target, value, expected_current=None)
            elif value["invocationId"] != current["invocationId"]:
                receipt = _read_receipt(root, key, value["invocationId"], prepared, task)
                if receipt is None or receipt["claim"] != value:
                    fail("ambiguous displaced worker claim")
        elif filename in {"receipt.json", "failure.json"}:
            _validate_receipt(value, key, prepared, task, root=root)
            invocation = value["claim"]["invocationId"]
            expected_path = (_receipt_relative(key, invocation) if filename == "receipt.json"
                             else _execution_relative(key, f"attempts/{invocation}/failure.json"))
            if target != expected_path or current is None or any(
                current[k] != value["claim"][k] for k in ("invocationId", "taskDigest", "claimedAt", "leaseExpiresAt")
            ):
                fail("foreign staged worker receipt")
            _publish_json(root, target, value, immutable=True, expected_current=None)
        elif filename == "result.json" or filename == "task-result-head.json" or "/metrics/" in target:
            invocation = (value.get("invocationId") if filename != "result.json" else target.split("/")[-2])
            _valid_invocation(invocation)
            receipt = _optional_json(root, _receipt_relative(key, invocation))
            if receipt is None:
                fail("worker stage has no durable receipt")
            _validate_receipt(receipt, key, prepared, task, root=root)
            if "/metrics/" in target:
                receipt = _read_receipt(root, key, invocation, prepared, task)
            if filename == "result.json":
                expected = receipt["result"]
            elif filename == "task-result-head.json":
                expected = _head_for(key, receipt)
            else:
                expected = receipt["metric"]
            if value != expected:
                fail("worker stage differs from its receipt")
            # The receipt replay performs publication in the required order.
        elif "/events/" in target:
            if (set(value) != {"eventType", "taskExecutionKey", "invocationId", "at"}
                    or current is None or value["taskExecutionKey"] != key
                    or value["invocationId"] != current["invocationId"]
                    or value["eventType"] not in EVENTS or type(value["at"]) is not int):
                fail("invalid staged worker event")
            if value["eventType"] in {"worker.completed", "worker.result.accepted"}:
                if _read_authoritative_head(root, key, prepared, task) is None:
                    fail("completion event has no authoritative result")
            _publish_json(root, target, value, immutable=True, expected_current=None)
        elif filename == "usage-aggregate.json":
            # Aggregates are derived. Only a validated subset of actual immutable
            # records can be a displaced prior version; arbitrary bytes cannot.
            ids = value.get("invocationIds")
            if not isinstance(ids, list) or ids != sorted(set(ids)):
                fail("invalid staged usage aggregate")
            records = []
            for invocation in ids:
                _valid_invocation(invocation)
                record = _optional_json(root, f"{base}/metrics/{invocation}.json")
                if record is None:
                    fail("staged aggregate references missing usage")
                _validate_metric(record, key, invocation, record["status"])
                records.append(record)
            if value != _aggregate_records(key, records):
                fail("staged usage aggregate differs from immutable usage")
        elif existing != value:
            fail("unknown worker recovery artifact")
        _remove_verified_temporary(root, relative, payload)


def claim_task(project_root: str, prepared_path: str, task_path: str) -> dict[str, Any]:
    prepared = delegation.read_object(prepared_path, label="prepared worker plan", max_bytes=MAX_PACKET_BYTES * 8)
    task = delegation.read_object(task_path, label="delegation task", max_bytes=delegation.LIMITS["taskBytes"])
    key = task_execution_key(prepared, task)
    _prepared_task(prepared, task)
    root = _ensure_execution_dir(project_root, key)
    with _task_lock(root, key):
        _recover_temporaries(root, key, prepared, task)
        claim_relative = _execution_relative(key, "claim.json")
        old_bytes = None
        try:
            old, old_bytes = _read_json_relative(root, claim_relative)
        except runtime.ContractError as error:
            if "No such file" not in str(error):
                raise
            old = None
        if old is not None:
            _validate_claim(old, key, task["taskDigest"])
            receipt = _read_receipt(root, key, old["invocationId"], prepared, task)
            if receipt is not None:
                _finish_receipt(root, key, receipt, prepared, task)
                old, old_bytes = _read_json_relative(root, claim_relative)
        authoritative = _read_authoritative_head(root, key, prepared, task)
        if authoritative is not None:
            if old is None or old["terminalStatus"] != "complete":
                fail("worker result HEAD has no reconciled completion receipt")
            result, _ = authoritative
            _event(project_root, "worker.result.reused", key)
            return {"action": "reused", "taskExecutionKey": key,
                    "resultObject": result, "resultDigest": result["resultDigest"]}
        now = int(time.time())
        if old is not None and old["status"] == "active":
            if old["leaseExpiresAt"] >= now:
                return {"action": "wait", "taskExecutionKey": key}
            # A crashed attempt has no invented usage. Close it durably before
            # issuing a fresh identity, and preserve its immutable summary.
            finalize_task(project_root, key, old["invocationId"], "interrupted")
            old, old_bytes = _read_json_relative(root, claim_relative)
        invocation_id = "I-" + uuid.uuid4().hex
        value = {"taskExecutionKey": key, "invocationId": invocation_id,
                 "taskDigest": task["taskDigest"], "status": "active",
                 "claimedAt": now, "leaseExpiresAt": now + WORKER_CLAIM_LEASE_SECONDS,
                 "terminalAt": None, "terminalStatus": None}
        _publish_json(root, claim_relative, value, expected_current=old_bytes)
        if old is not None:
            _event(project_root, "worker.claim.reconciled", key, invocation_id)
        _event(project_root, "worker.claimed", key, invocation_id)
        return {"action": "claimed", "taskExecutionKey": key, "invocationId": invocation_id,
                "timeoutSeconds": WORKER_TIMEOUT_SECONDS, "killGraceSeconds": WORKER_KILL_GRACE_SECONDS}


def _metric_record(key: str, invocation_id: str, status: str, usage_summary: str | None) -> dict[str, Any]:
    usage_status = "unavailable"
    raw_trace_retained = False
    totals = {"input": None, "cachedInput": None, "uncachedInput": None,
              "output": None, "reasoning": None}
    if usage_summary is not None:
        payload = runtime.safe_read_bytes(Path(usage_summary), max_bytes=MAX_PACKET_BYTES)
        try:
            usage = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            fail(f"cannot decode worker usage summary: {error}")
        if not isinstance(usage, dict):
            fail("worker usage summary must be an object")
        runtime.validate_model("usage-summary", usage)
        usage_status = usage["usageStatus"]
        totals = deepcopy(usage["totals"])
        raw_trace_retained = usage["rawTraceRetained"]
    return {"schemaVersion": "mana.context-runtime.worker-invocation-usage/v1",
            "invocationId": invocation_id, "taskExecutionKey": key, "status": status,
            "usageStatus": usage_status, "totals": totals,
            "rawTraceRetained": raw_trace_retained}


def _raw_trace_relative(key: str, invocation: str) -> str:
    _valid_invocation(invocation)
    return _execution_relative(key, f"attempts/{invocation}/raw-provider-trace")


def _validate_raw_trace_binding(root: Path, key: str, metric: dict[str, Any]) -> None:
    relative = _raw_trace_relative(key, metric["invocationId"])
    path = root / relative
    if metric["rawTraceRetained"] is False:
        if path.exists() or path.is_symlink():
            fail("discarded worker raw trace has a retained artifact")
        return
    payload = _read_relative(root, relative, max_bytes=None)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600):
        fail("retained worker raw trace is not a private mode-0600 artifact")
    if not isinstance(payload, bytes):
        fail("retained worker raw trace is unreadable")


def _materialize_raw_trace(
    root: Path, key: str, metric: dict[str, Any], raw_trace: str | None,
) -> None:
    if metric["rawTraceRetained"] is False:
        if raw_trace is not None:
            fail("worker supplied a raw trace without host retention authority")
        return
    if raw_trace is None:
        fail("worker usage claims raw trace retention without a trace")
    payload = runtime.safe_read_bytes(Path(raw_trace), max_bytes=None)
    relative = _raw_trace_relative(key, metric["invocationId"])
    runtime.ensure_secure_directory(root, relative.rsplit("/", 1)[0])
    runtime.atomic_write_bytes(root, relative, payload, immutable=True, expected_current=None)
    _validate_raw_trace_binding(root, key, metric)


def _managed_child_receipt_relative(key: str, invocation: str) -> str:
    _valid_invocation(invocation)
    return _execution_relative(key, f"attempts/{invocation}/managed-child-receipt.json")


def _managed_child_binding_relative(receipt_digest: str) -> str:
    if not isinstance(receipt_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", receipt_digest) is None:
        fail("invalid managed-child receipt digest")
    return f".mana/runtime/managed-child-result-bindings/{receipt_digest[7:]}.json"


def _managed_child_receipt_digest(receipt: dict[str, Any]) -> str:
    return delegation.managed_child_receipt_digest(receipt)


def _validate_managed_child_receipt_record(receipt, key, invocation, prepared, task) -> None:
    delegation.validate_managed_child_receipt_record(
        receipt, key, invocation, prepared["authorityPacket"], task
    )


def _read_managed_child_receipt_record(root, key, invocation, prepared, task):
    if task_execution_key(prepared, task) != key:
        fail("managed-child receipt task key differs from host derivation")
    try:
        return delegation.read_committed_managed_child_receipt_record(
            root, invocation, prepared["authorityPacket"], task
        )
    except delegation.runtime.ContractError as error:
        fail(str(error))


def load_committed_completed_managed_child_receipt(root, key, invocation, prepared, task):
    if task_execution_key(prepared, task) != key:
        fail("managed-child receipt task key differs from host derivation")
    try:
        return delegation.load_committed_completed_managed_child_receipt(
            root, invocation, prepared["authorityPacket"], task
        )
    except delegation.runtime.ContractError as error:
        fail(str(error))


def _managed_child_binding_record(
    key: str, invocation: str, receipt: dict[str, Any],
    result: dict[str, Any], head: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": MANAGED_CHILD_BINDING_SCHEMA,
        "receiptId": receipt["receiptId"],
        "receiptDigest": receipt["receiptDigest"],
        "taskExecutionKey": key,
        "hostInvocationId": invocation,
        "semanticResultDigest": result["semanticResultDigest"],
        "executionReceiptDigest": result["executionReceiptDigest"],
        "resultArtifactDigest": head["artifactDigest"],
        "authoritativeResultHead": deepcopy(head),
    }


def _commit_managed_child_binding(
    root: Path, key: str, invocation: str, receipt: dict[str, Any],
    result: dict[str, Any], head: dict[str, Any],
) -> None:
    relative = _managed_child_binding_relative(receipt["receiptDigest"])
    runtime.ensure_secure_directory(root, relative.rsplit("/", 1)[0])
    candidate = _managed_child_binding_record(key, invocation, receipt, result, head)
    existing = _optional_json(root, relative)
    if existing is not None and existing != candidate:
        fail("managed-child receipt replay conflicts with its authoritative result binding")
    _publish_json(root, relative, candidate, immutable=True, expected_current=None)


def _validate_managed_child_binding(
    root: Path, key: str, invocation: str, receipt: dict[str, Any],
    result: dict[str, Any], head: dict[str, Any],
) -> None:
    relative = _managed_child_binding_relative(receipt["receiptDigest"])
    binding = _optional_json(root, relative)
    if binding is None:
        fail("provider-managed child result has no committed receipt/result binding")
    expected = _managed_child_binding_record(key, invocation, receipt, result, head)
    if binding != expected:
        fail("provider-managed child receipt/result binding is foreign or conflicting")
    info = (root / relative).lstat()
    parent_info = (root / relative).parent.lstat()
    if (
        not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o600
        or not stat.S_ISDIR(parent_info.st_mode)
        or stat.S_IMODE(parent_info.st_mode) != 0o700
    ):
        fail("managed-child receipt/result binding is not private and immutable")


def _receipt_relative(key: str, invocation: str) -> str:
    _valid_invocation(invocation)
    return _execution_relative(key, f"attempts/{invocation}/receipt.json")


def _validate_metric(metric: dict[str, Any], key: str, invocation: str, status: str) -> None:
    if status not in {"complete", "failed", "timed_out", "interrupted", "publication_failed"}:
        fail("invalid worker metric status")
    expected = _metric_record(key, invocation, status, None)
    if set(metric) != set(expected) or any(metric[k] != expected[k] for k in
            ("schemaVersion", "invocationId", "taskExecutionKey", "status")):
        fail("invalid worker metric identity")
    if type(metric["rawTraceRetained"]) is not bool:
        fail("invalid worker raw trace retention state")
    if metric["usageStatus"] not in {"measured", "unavailable", "partial"} or set(metric["totals"]) != set(expected["totals"]):
        fail("invalid worker metric dimensions")
    if any(v is not None and (type(v) is not int or v < 0 or v > 9007199254740991)
           for v in metric["totals"].values()):
        fail("invalid worker metric value")
    if metric["usageStatus"] == "unavailable" and any(v is not None for v in metric["totals"].values()):
        fail("unavailable worker usage contains measurements")


def _validate_receipt(
    receipt: dict[str, Any], key: str, prepared=None, task=None, *, root: Path | None = None,
) -> None:
    if set(receipt) != {"schemaVersion", "claim", "metric", "result"} or receipt["schemaVersion"] != "mana.context-runtime.worker-receipt/v1":
        fail("invalid worker receipt")
    claim = receipt["claim"]
    _validate_claim(claim, key, None if task is None else task["taskDigest"])
    if claim["status"] != "terminal":
        fail("worker receipt must be terminal")
    status = claim["terminalStatus"]
    _validate_metric(receipt["metric"], key, claim["invocationId"], status)
    if status == "complete":
        if prepared is None or task is None:
            fail("completion recovery requires current authority")
        _validate_authoritative_result(
            prepared, task, receipt["result"], root=root, key=key,
            invocation_id=claim["invocationId"], require_managed_binding=False,
        )
    elif receipt["result"] is not None:
        fail("failed worker receipt contains a result")


def _read_receipt(root: Path, key: str, invocation: str, prepared=None, task=None):
    _valid_invocation(invocation)
    failure = _optional_json(root, _execution_relative(key, f"attempts/{invocation}/failure.json"))
    if failure is not None:
        _validate_receipt(failure, key, prepared, task, root=root)
        if failure["claim"]["invocationId"] != invocation or failure["result"] is not None:
            fail("invalid worker publication failure receipt")
        return failure
    try:
        receipt, _ = _read_json_relative(root, _receipt_relative(key, invocation))
    except runtime.ContractError as error:
        if "No such file" in str(error):
            return None
        raise
    _validate_receipt(receipt, key, prepared, task, root=root)
    if receipt["claim"]["invocationId"] != invocation:
        fail("foreign worker receipt")
    _validate_raw_trace_binding(root, key, receipt["metric"])
    return receipt


def _head_for(key: str, receipt: dict[str, Any]) -> dict[str, Any]:
    result = receipt["result"]
    invocation = receipt["claim"]["invocationId"]
    return {"schemaVersion": "mana.context-runtime.worker-result-head/v1",
            "taskExecutionKey": key, "invocationId": invocation,
            "resultDigest": result["resultDigest"], "artifactDigest": digest_bytes(runtime.canonical_bytes(result)),
            "artifact": f"attempts/{invocation}/result.json"}


def _finish_receipt(root: Path, key: str, receipt: dict[str, Any], prepared=None, task=None) -> None:
    _validate_receipt(receipt, key, prepared, task, root=root)
    _validate_raw_trace_binding(root, key, receipt["metric"])
    terminal = receipt["claim"]
    invocation = terminal["invocationId"]
    claim_relative = _execution_relative(key, "claim.json")
    current, previous = _read_json_relative(root, claim_relative)
    _validate_claim(current, key)
    # A receipt can finish only the exact issued claim, never replace another.
    if any(current[k] != terminal[k] for k in ("taskExecutionKey", "invocationId", "taskDigest", "claimedAt", "leaseExpiresAt")):
        fail("receipt belongs to another worker claim")
    if current["status"] == "terminal" and current != terminal:
        fail("conflicting terminal worker receipt")
    if terminal["terminalStatus"] == "complete":
        result = receipt["result"]
        result_head = _head_for(key, receipt)
        existing_head = _optional_json(
            root, _execution_relative(key, "task-result-head.json")
        )
        _publish_json(root, _execution_relative(key, f"attempts/{invocation}/result.json"),
                      result, immutable=True, expected_current=None)
        if result["executionProvenance"]["executionTransport"] == "provider-managed-child":
            managed_receipt = load_committed_completed_managed_child_receipt(
                root, key, invocation, prepared, task
            )
            if existing_head is None:
                _commit_managed_child_binding(
                    root, key, invocation, managed_receipt, result, result_head
                )
            else:
                if existing_head != result_head:
                    fail("provider-managed child receipt names another result HEAD")
                _validate_managed_child_binding(
                    root, key, invocation, managed_receipt, result, result_head
                )
        _publish_json(root, _execution_relative(key, "task-result-head.json"),
                      result_head, immutable=True, expected_current=None)
        _event(str(root), "worker.result.accepted", key, invocation, terminal["terminalAt"])
    runtime.ensure_secure_directory(root, _execution_relative(key, "metrics"))
    _publish_json(root, _execution_relative(key, f"metrics/{invocation}.json"),
                  receipt["metric"], immutable=True, expected_current=None)
    event = {"complete": "worker.completed", "timed_out": "worker.timed_out",
             "interrupted": "worker.interrupted"}.get(terminal["terminalStatus"], "worker.failed")
    _event(str(root), event, key, invocation, terminal["terminalAt"])
    _rebuild_metric_aggregate(root, key)
    if current != terminal:
        _publish_json(root, claim_relative, terminal, expected_current=previous)


def _make_receipt(claim, key, status, usage_summary, result=None, *, root=None, raw_trace=None):
    terminal = deepcopy(claim)
    terminal.update(status="terminal", terminalAt=int(time.time()), terminalStatus=status)
    metric = _metric_record(key, claim["invocationId"], status, usage_summary)
    if root is not None:
        _materialize_raw_trace(root, key, metric, raw_trace)
    elif metric["rawTraceRetained"] or raw_trace is not None:
        fail("raw trace materialization requires the worker execution root")
    return {"schemaVersion": "mana.context-runtime.worker-receipt/v1", "claim": terminal,
            "metric": metric, "result": result}


def finalize_task(project_root: str, key: str, invocation_id: str, status: str,
                  usage_summary: str | None = None, raw_trace: str | None = None) -> None:
    root = _ensure_execution_dir(project_root, key)
    with _task_lock(root, key):
        claim, _ = _read_json_relative(root, _execution_relative(key, "claim.json"))
        _validate_claim(claim, key)
        if claim["invocationId"] != invocation_id:
            fail("worker claim belongs to another invocation")
        # A committed HEAD is irreversible. Before HEAD, an explicit publication
        # failure can cancel the intent with a separate immutable failure receipt.
        try:
            existing, _ = _read_json_relative(root, _receipt_relative(key, invocation_id))
        except runtime.ContractError as error:
            if "No such file" not in str(error):
                raise
            existing = None
        receipt_path = _receipt_relative(key, invocation_id)
        if existing is not None and existing.get("claim", {}).get("terminalStatus") == "complete":
            head = _optional_json(root, _execution_relative(key, "task-result-head.json"))
            if head is not None:
                if head != _head_for(key, existing):
                    fail("conflicting worker result HEAD during finalization")
                return
            receipt_path = _execution_relative(key, f"attempts/{invocation_id}/failure.json")
            existing = _optional_json(root, receipt_path)
        try:
            receipt = existing or _make_receipt(
                claim, key, status, usage_summary, root=root, raw_trace=raw_trace
            )
        except runtime.ContractError:
            # Invalid usage must not prevent a known failure becoming terminal.
            receipt = existing or _make_receipt(claim, key, status, None, root=root)
        _validate_receipt(receipt, key, root=root)
        runtime.ensure_secure_directory(root, _execution_relative(key, f"attempts/{invocation_id}"))
        _publish_json(root, receipt_path, receipt, immutable=True, expected_current=None)
        _finish_receipt(root, key, receipt)


def _aggregate_records(key: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    totals: dict[str, int | None] = {name: 0 for name in ("input", "cachedInput", "uncachedInput", "output", "reasoning")}
    availability = {name: False for name in totals}
    for record in records:
        status = str(record["status"])
        statuses[status] = statuses.get(status, 0) + 1
        for name in totals:
            value = record["totals"][name]
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                totals[name] = int(totals[name] or 0) + value
                availability[name] = True
    aggregate = {
        "schemaVersion": "mana.context-runtime.worker-usage-aggregate/v1",
        "taskExecutionKey": key,
        "invocationIds": [record["invocationId"] for record in records],
        "invocationCount": len(records), "statuses": statuses,
        "totals": {name: totals[name] if availability[name] else None for name in totals},
    }
    return aggregate


def _rebuild_metric_aggregate(root: Path, key: str) -> None:
    relative = _execution_relative(key, "usage-aggregate.json")
    metrics_relative = _execution_relative(key, "metrics")
    for _ in range(16):
        names = [name for name in runtime.safe_list_directory(root, metrics_relative)
                 if name.startswith("I-") and name.endswith(".json")]
        records: list[dict[str, Any]] = []
        for name in names:
            record, _payload = _read_json_relative(root, f"{metrics_relative}/{name}")
            invocation = record.get("invocationId")
            if not isinstance(invocation, str) or invocation + ".json" != name or record.get("taskExecutionKey") != key:
                fail("worker invocation metric identity is malformed")
            _validate_metric(record, key, invocation, record["status"])
            records.append(record)
        records.sort(key=lambda item: item["invocationId"])
        aggregate = _aggregate_records(key, records)
        try:
            _, previous = _read_json_relative(root, relative)
        except runtime.ContractError as error:
            if "No such file" not in str(error):
                raise
            previous = None
        try:
            _publish_json(root, relative, aggregate, expected_current=previous)
            return
        except runtime.ContractError as error:
            if not any(marker in str(error) for marker in ("appeared", "changed", "disappeared")):
                raise
    fail("worker usage aggregate CAS did not converge")


def publish_task(project_root: str, key: str, invocation_id: str, result_path: str,
                 prepared_path: str, task_path: str, usage_summary: str | None = None,
                 raw_trace: str | None = None) -> dict[str, Any]:
    root = _ensure_execution_dir(project_root, key)
    prepared = delegation.read_object(prepared_path, label="prepared worker plan", max_bytes=MAX_PACKET_BYTES * 8)
    task = delegation.read_object(task_path, label="delegation task", max_bytes=delegation.LIMITS["taskBytes"])
    if task_execution_key(prepared, task) != key:
        fail("worker publication task key differs from host derivation")
    result = delegation.read_object(result_path, label="validated worker result", max_bytes=delegation.LIMITS["resultBytes"])
    _validate_authoritative_result(
        prepared, task, result, root=root, key=key, invocation_id=invocation_id,
        require_managed_binding=False,
    )
    with _task_lock(root, key):
        _recover_temporaries(root, key, prepared, task)
        claim, _ = _read_json_relative(root, _execution_relative(key, "claim.json"))
        _validate_claim(claim, key, task["taskDigest"])
        if claim["invocationId"] != invocation_id:
            fail("worker claim belongs to another invocation")
        existing = _read_receipt(root, key, invocation_id, prepared, task)
        if existing is not None and existing["result"] != result:
            fail("conflicting authoritative worker result")
        if existing is None and claim["status"] != "active":
            fail("worker claim is already terminal")
        receipt = existing or _make_receipt(
            claim, key, "complete", usage_summary, result, root=root, raw_trace=raw_trace
        )
        runtime.ensure_secure_directory(root, _execution_relative(key, f"attempts/{invocation_id}"))
        _publish_json(root, _receipt_relative(key, invocation_id), receipt, immutable=True, expected_current=None)
        _finish_receipt(root, key, receipt, prepared, task)
        authoritative, _ = _read_authoritative_head(root, key, prepared, task) or (None, None)
        if authoritative is None:
            fail("published worker result is not HEAD-reachable")
        return {"action": "published" if existing is None else "reused",
                "resultObject": authoritative, "resultDigest": authoritative["resultDigest"]}


def validate_with_schema(value: dict[str, Any], schema_name: str) -> None:
    schema_path = runtime.CONTRACTS / schema_name
    evaluator = runtime.Evaluator()
    errors = evaluator.evaluate(value, evaluator.load(schema_path), schema_path)
    if errors:
        fail("; ".join(errors[:8]))


def load_policy(framework_root: str | Path | None = None) -> dict[str, Any]:
    if framework_root is None:
        framework_root = HOST_FRAMEWORK_ROOT
    root = runtime._canonical_framework_root(framework_root)
    payload = runtime.safe_read_bytes(
        root / POLICY_RELATIVE_PATH, max_bytes=MAX_POLICY_BYTES + 1
    )
    if len(payload) > MAX_POLICY_BYTES:
        fail("host worker routing policy exceeds its byte limit")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot decode host worker routing policy: {error}")
    if not isinstance(value, dict):
        fail("host worker routing policy must be an object")
    validate_with_schema(value, "worker-routing-policy-v1.schema.json")
    if value.get("schemaVersion") != POLICY_SCHEMA:
        fail("host worker routing policy has an unsupported version")
    seen: set[tuple[str, str]] = set()
    for mapping in value["mappings"]:
        key = (mapping["provider"], mapping["modelTier"])
        if key in seen:
            fail(f"host worker routing policy duplicates mapping {key[0]}/{key[1]}")
        seen.add(key)
    return value


def load_debug_policy(framework_root: str | Path | None = None) -> dict[str, Any]:
    """Load the caller-inaccessible, versioned worker diagnostic decision."""
    if framework_root is None:
        framework_root = HOST_FRAMEWORK_ROOT
    root = runtime._canonical_framework_root(framework_root)
    payload = runtime.safe_read_bytes(
        root / DEBUG_POLICY_RELATIVE_PATH, max_bytes=MAX_POLICY_BYTES + 1
    )
    if len(payload) > MAX_POLICY_BYTES:
        fail("host worker debug policy exceeds its byte limit")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot decode host worker debug policy: {error}")
    if not isinstance(value, dict):
        fail("host worker debug policy must be an object")
    validate_with_schema(value, "worker-debug-policy-v1.schema.json")
    if value.get("schemaVersion") != DEBUG_POLICY_SCHEMA:
        fail("host worker debug policy has an unsupported version")
    return value


def materialize_debug_policy(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": policy["schemaVersion"],
        "policyId": policy["policyId"],
        "policyDigest": digest_bytes(runtime.canonical_bytes(policy)),
        "retainRawTrace": policy["rawTraceRetention"] == "retain",
    }


def task_skill_metadata(
    task: dict[str, Any], manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    active = {item["id"]: item for item in manifest["activatedSkills"]}
    return [deepcopy(active[skill_id]) for skill_id in task["skills"]]


def route_task(
    task: dict[str, Any], skill_metadata: list[dict[str, Any]]
) -> tuple[str, str, list[str]]:
    """Derive tier and effective risk only from validated CTX-07A/CTX-04 data."""
    reasons: list[str] = []
    effective_risk = "high" if task["scope"]["domain"] in HIGH_RISK_DOMAINS else "low"
    if effective_risk == "high":
        reasons.append(f"high-risk-scope:{task['scope']['domain']}")
    for metadata in skill_metadata:
        if RISK_ORDER[metadata["riskLevel"]] > RISK_ORDER[effective_risk]:
            effective_risk = metadata["riskLevel"]
        if metadata["modelTier"] == "full" or metadata["riskLevel"] == "high":
            reasons.append(f"escalated-skill:{metadata['id']}")
    if reasons:
        return "full", effective_risk, sorted(reasons)
    return "economy", effective_risk, ["bounded-read-task"]


def policy_mapping(
    policy: dict[str, Any], provider: str, model_tier: str,
    scope_domain: str, effective_risk: str,
) -> dict[str, Any]:
    matches = [
        item for item in policy["mappings"]
        if item["provider"] == provider and item["modelTier"] == model_tier
    ]
    if len(matches) != 1:
        prefix = "needs_model_escalation: " if model_tier == "full" or effective_risk == "high" else ""
        fail(f"{prefix}host worker routing policy has no unique {provider}/{model_tier} mapping")
    mapping = matches[0]
    if scope_domain not in mapping["allowedScopeDomains"]:
        fail(
            f"needs_model_escalation: host worker route {provider}/{model_tier} "
            f"does not admit scope {scope_domain}"
        )
    if effective_risk not in mapping["allowedRiskLevels"]:
        fail(
            f"needs_model_escalation: host worker route {provider}/{model_tier} "
            f"does not admit risk {effective_risk}"
        )
    return mapping


def project_manifest(
    task: dict[str, Any], packet: dict[str, Any], skill_metadata: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest = packet["contextManifest"]
    return {
        "schemaVersion": "mana.context-runtime.worker-manifest-projection/v1",
        "sourceManifestSchemaVersion": manifest["schemaVersion"],
        "sourceManifestDigest": digest_bytes(runtime.canonical_bytes(manifest)),
        "executionId": manifest["executionId"],
        "profileId": manifest["profileId"],
        "taskSkills": deepcopy(skill_metadata),
        "limits": {
            "workerDepth": manifest["limits"]["workerDepth"],
            "retrievalCyclesPerQuestion": min(
                manifest["limits"]["retrievalCyclesPerQuestion"],
                task["limits"]["retrievalCycles"],
            ),
        },
    }


def load_active_skills(
    framework_root: str, skill_metadata: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    root = runtime._canonical_framework_root(framework_root)
    index = runtime._parse_skill_index(root)
    result: list[dict[str, Any]] = []
    for metadata in skill_metadata:
        skill_id = metadata["id"]
        indexed = index.get(skill_id)
        if indexed is None:
            fail(f"authoritative task skill metadata is missing for {skill_id}")
        expected_index_metadata = {
            "model_tier": metadata["modelTier"],
            "risk_level": metadata["riskLevel"],
            "execution_mode": metadata["executionMode"],
            "delegation_group": metadata["delegationGroup"],
        }
        if any(indexed[key] != value for key, value in expected_index_metadata.items()):
            fail(f"authoritative task skill metadata changed for {skill_id}")
        try:
            payload = runtime.safe_read_bytes(
                root / indexed["path"], max_bytes=MAX_SKILL_BODY_BYTES + 1
            )
        except runtime.ContractError as error:
            if "exceeds its" in str(error):
                fail(
                    f"active task skill body exceeds its {MAX_SKILL_BODY_BYTES} "
                    f"byte limit: {skill_id}"
                )
            raise
        if len(payload) > MAX_SKILL_BODY_BYTES:
            fail(
                f"active task skill body exceeds its {MAX_SKILL_BODY_BYTES} byte limit: "
                f"{skill_id}"
            )
        try:
            body = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            fail(f"active task skill body is not UTF-8 for {skill_id}: {error}")
        front_matter = runtime._front_matter(body, f"skill {skill_id}")
        parallel = runtime._front_matter_scalar(front_matter, "parallel_safe")
        expected_parallel = "true" if metadata["parallelSafe"] is True else "false"
        if parallel != expected_parallel:
            fail(f"authoritative task skill parallel-safety changed for {skill_id}")
        result.append({
            "metadata": deepcopy(metadata),
            "body": body,
            "bodyDigest": digest_bytes(payload),
        })
    return result


def selection_from_mapping(
    policy: dict[str, Any], mapping: dict[str, Any], reasons: list[str]
) -> dict[str, Any]:
    return {
        "provider": mapping["provider"],
        "modelTier": mapping["modelTier"],
        "modelId": mapping["modelId"],
        "reasoningEffort": mapping["reasoningEffort"],
        "policyId": policy["policyId"],
        "policyDigest": digest_bytes(runtime.canonical_bytes(policy)),
        "routingReasons": reasons,
    }


def validate_packet(packet: dict[str, Any], policy: dict[str, Any]) -> None:
    if len(runtime.canonical_bytes(packet)) > MAX_PACKET_BYTES:
        fail(f"worker context packet exceeds its {MAX_PACKET_BYTES} byte limit")
    validate_with_schema(packet, "worker-context-packet-v1.schema.json")
    if packet.get("schemaVersion") != PACKET_SCHEMA:
        fail("worker context packet has an unsupported version")
    envelope = packet["governanceEnvelope"]
    task = packet["delegationTask"]
    runtime.validate_structure("execution-envelope", envelope)
    runtime.validate_model("delegation-task", task)
    permissions = envelope["permissions"]
    if (
        permissions["repositoryWrite"] is not False
        or permissions["externalWrite"] is not False
        or permissions["approvedExternalActions"] != []
    ):
        fail("worker governance envelope is not the read-only CTX-07B authority")
    for field in ("executionId", "executionVersion", "profileId", "workspaceId"):
        if task[field] != envelope[field]:
            fail(f"worker context packet has inconsistent {field}")
    projection = packet["contextManifestProjection"]
    if (
        projection["executionId"] != task["executionId"]
        or projection["profileId"] != task["profileId"]
    ):
        fail("worker context manifest projection is bound elsewhere")
    if packet["evidenceRefs"] != task["evidenceRefs"]:
        fail("worker context packet evidence refs differ from its validated task")
    if packet["outputContract"] != task["expectedOutput"]:
        fail("worker context packet output contract differs from its validated task")
    metadata = projection["taskSkills"]
    if [item["id"] for item in metadata] != task["skills"]:
        fail("worker context manifest projection contains a non-task skill")
    if [item["metadata"] for item in packet["activeSkills"]] != metadata:
        fail("worker context packet skill bodies differ from its manifest projection")
    for active_skill in packet["activeSkills"]:
        if digest_bytes(active_skill["body"].encode("utf-8")) != active_skill["bodyDigest"]:
            fail("worker context packet contains a tampered active skill body")
    tier, risk, reasons = route_task(task, metadata)
    selection = packet["modelSelection"]
    if selection["modelTier"] != tier or selection["routingReasons"] != reasons:
        fail("worker context packet contains a non-authoritative tier derivation")
    if selection["provider"] != envelope["provider"]:
        fail("worker context packet model selection names another provider")
    mapping = policy_mapping(
        policy, selection["provider"], tier, task["scope"]["domain"], risk
    )
    expected = selection_from_mapping(policy, mapping, reasons)
    if selection != expected:
        fail("worker context packet model/effort selection differs from host policy")


def build_packet(
    task: dict[str, Any], host_packet: dict[str, Any], policy: dict[str, Any],
    skill_metadata: list[dict[str, Any]], mapping: dict[str, Any], reasons: list[str],
    active_skills: list[dict[str, Any]],
) -> dict[str, Any]:
    packet = {
        "schemaVersion": PACKET_SCHEMA,
        "governanceEnvelope": deepcopy(host_packet["executionEnvelope"]),
        "delegationTask": deepcopy(task),
        "contextManifestProjection": project_manifest(task, host_packet, skill_metadata),
        "activeSkills": active_skills,
        "evidenceRefs": deepcopy(task["evidenceRefs"]),
        "outputContract": deepcopy(task["expectedOutput"]),
        "modelSelection": selection_from_mapping(policy, mapping, reasons),
    }
    validate_packet(packet, policy)
    return packet


def _safe_capsule_file(path: Path, payload: bytes) -> None:
    """Write a new capsule file without links and make it immutable to worker."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _assert_capsule_tree(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or (path.is_file() and info.st_nlink != 1):
            fail("worker capsule contains a link")
        if path.is_file() and not stat.S_ISREG(info.st_mode):
            fail("worker capsule contains a non-regular file")


def materialize_capsule(packet_path: str, project_root: str, capsule: str, framework_root: str) -> dict[str, Any]:
    """Create the only task data filesystem visible to a worker invocation."""
    packet = delegation.read_object(packet_path, label="worker context packet", max_bytes=MAX_PACKET_BYTES)
    policy = load_policy(framework_root)
    validate_packet(packet, policy)
    root = Path(project_root).resolve(strict=True)
    target = Path(capsule)
    if target.exists() or target.is_symlink() or target.parent.is_symlink():
        fail("worker capsule target must be a new non-symlink directory")
    target.mkdir(mode=0o700, parents=False)
    try:
        # No locator or original-store path is copied into any capsule object.
        assignment = {
            "schemaVersion": "mana.context-runtime.worker-capsule/v1",
            "workerContextPacket": packet,
            "governanceProjection": packet["governanceEnvelope"],
            "manifestProjection": packet["contextManifestProjection"],
            "activeSkills": packet["activeSkills"],
            "outputContract": packet["outputContract"],
            "evidenceExtracts": [],
        }
        task = packet["delegationTask"]
        allowed = set(task["evidenceRefs"])
        evidence_tool = HERE.parent / "mana-evidence.sh"
        for index, request in enumerate(task.get("evidenceExtracts", [])):
            if request["evidenceId"] not in allowed:
                fail("worker evidence extract is not authorized by task evidence refs")
            if request["maxBytes"] > MAX_EVIDENCE_EXTRACT_BYTES:
                fail("worker evidence extract exceeds its byte limit")
            completed = subprocess.run(
                [str(evidence_tool), "--project-root", str(root), "extract", request["evidenceId"],
                 "--execution", task["executionId"], "--selector", request["selector"],
                 "--max-bytes", str(request["maxBytes"])],
                check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            if completed.returncode != 0:
                fail("authorized worker evidence extract could not be materialized")
            try:
                extract = json.loads(completed.stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                fail(f"authorized worker evidence extract is malformed: {error}")
            if not isinstance(extract, dict) or extract.get("byteSize", MAX_EVIDENCE_EXTRACT_BYTES + 1) > request["maxBytes"]:
                fail("authorized worker evidence extract exceeds its contract")
            extract["digest"] = digest_bytes(runtime.canonical_bytes(extract))
            name = f"evidence/extract-{index}.json"
            _safe_capsule_file(target / name, runtime.canonical_bytes(extract) + b"\n")
            assignment["evidenceExtracts"].append({
                "evidenceId": request["evidenceId"], "selector": request["selector"],
                "digest": extract["digest"], "path": name,
            })
        _safe_capsule_file(target / "assignment.json", runtime.canonical_bytes(assignment) + b"\n")
        schema = HOST_CONTRACT_ROOT / "contracts/context-runtime/delegation-result-draft-v1.schema.json"
        schema_bytes = runtime.safe_read_bytes(schema, max_bytes=MAX_PACKET_BYTES)
        _safe_capsule_file(target / "output-schema.json", schema_bytes)
        for directory in [target, *[item for item in target.rglob("*") if item.is_dir()]]:
            directory.chmod(0o500)
        _assert_capsule_tree(target)
        return assignment
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    framework_root = getattr(args, "_framework_root", HOST_FRAMEWORK_ROOT)
    # context-delegation's CTX-06 reader consumes this attribute.  It is set
    # here from code-owned authority, never parsed from production argv/env.
    args.framework_root = str(framework_root)
    host_packet, evidence_manifest = delegation.authoritative_context(args)
    plan = delegation.read_object(
        args.plan, label="delegation plan", max_bytes=delegation.LIMITS["planBytes"]
    )
    # CTX-07A is deliberately the first task-sensitive gate. No worker packet
    # is constructed until the complete plan has survived this validation.
    delegation.validate_plan(plan, host_packet, evidence_manifest)
    policy = load_policy(framework_root)
    debug_policy = materialize_debug_policy(load_debug_policy(framework_root))
    provider = host_packet["provider"]
    resolved: list[
        tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[str]]
    ] = []
    for task in plan["tasks"]:
        metadata = task_skill_metadata(task, host_packet["contextManifest"])
        tier, risk, reasons = route_task(task, metadata)
        mapping = policy_mapping(
            policy, provider, tier, task["scope"]["domain"], risk
        )
        resolved.append((task, metadata, mapping, reasons))
    workers = []
    for task, metadata, mapping, reasons in resolved:
        skills = load_active_skills(str(framework_root), metadata)
        context_packet = build_packet(
            task, host_packet, policy, metadata, mapping, reasons, skills
        )
        workers.append({"taskId": task["taskId"], "contextPacket": context_packet})
    return {
        "schemaVersion": PREPARED_SCHEMA,
        "executionId": host_packet["executionId"],
        "profileId": host_packet["profileId"],
        "workspaceId": host_packet["executionEnvelope"]["workspaceId"],
        "phaseId": host_packet["phase"]["id"],
        "attempt": host_packet["currentAttempt"],
        "provider": provider,
        "planId": plan["planId"],
        "directWorkerLimit": host_packet["contextManifest"]["limits"]["directWorkers"],
        "debugPolicy": debug_policy,
        "authorityPacket": deepcopy(host_packet),
        "evidenceManifest": deepcopy(evidence_manifest),
        "plan": deepcopy(plan),
        "workers": workers,
    }


def render_prompt(packet: dict[str, Any], policy: dict[str, Any]) -> str:
    validate_packet(packet, policy)
    packet_json = runtime.canonical_bytes(packet).decode("utf-8")
    return "\n".join([
        "Mana Context Runtime CTX-07B-R2 fresh host-launched worker.",
        "Treat the host-owned workerContextPacket below as the complete and only work assignment.",
        "The governance envelope is immutable and read-only; do not grant permissions or approvals.",
        "Do not delegate, spawn children, broaden scope, or use evidence outside the authorized references.",
        "The activeSkills list is exhaustive for this task; no inactive or candidate skill is available.",
        "Return one JSON object using schemaVersion mana.context-runtime.delegation-result-draft/v1.",
        "Populate only sections named by outputContract.sections and preserve gaps and uncertainty.",
        f"workerContextPacket={packet_json}",
    ]) + "\n"


def render_child_prompt(packet: dict[str, Any], policy: dict[str, Any]) -> str:
    """Build the bounded CTX-07C root packet for exactly one managed child."""
    validate_packet(packet, policy)
    packet_json = runtime.canonical_bytes(packet).decode("utf-8")
    return "\n".join([
        "Mana Context Runtime CTX-07C provider-managed child adapter.",
        "Invoke exactly one child named mana_ctx07c_child and give it the exact workerContextPacket below.",
        "Do not answer the task in the root, start another child, retry, or add context.",
        "Return the child's JSON object unchanged as the root structured final output.",
        "The child may not delegate, broaden scope, grant authority, or use undeclared evidence.",
        "The host will apply the unchanged CTX-07A schema, task, evidence, digest, and provenance binding.",
        f"workerContextPacket={packet_json}",
    ]) + "\n"


def _decode_provider_output(provider: str, path: str) -> dict[str, Any]:
    if provider not in {"codex", "claude", "opencode"}:
        fail("unknown worker provider output adapter")
    value = delegation.read_object(
        path, label="worker provider output", max_bytes=delegation.LIMITS["resultBytes"]
    )
    candidate: Any = value
    if provider == "claude" and isinstance(value.get("structured_output"), dict):
        candidate = value["structured_output"]
    elif provider == "claude" and isinstance(value.get("result"), str):
        try:
            candidate = json.loads(value["result"])
        except json.JSONDecodeError as error:
            fail(f"cannot decode Claude worker result: {error}")
    if not isinstance(candidate, dict):
        fail("worker final output is not a delegation result draft object")
    delegation.enforce_size(
        "delegation result draft", candidate, delegation.LIMITS["resultBytes"]
    )
    return candidate


def _validate_normalized_draft(draft: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    validate_with_schema(draft, "delegation-result-draft-v1.schema.json")
    runtime.reject_unsafe_content(draft)
    if set(draft) != RESULT_DRAFT_FIELDS:
        fail("delegation result draft has an invalid field set")
    if draft.get("schemaVersion") != "mana.context-runtime.delegation-result-draft/v1":
        fail("delegation result draft has an unsupported version")
    if draft.get("taskId") != task["taskId"]:
        fail("delegation result draft names a different task")
    allowed = set(task["expectedOutput"]["sections"])
    for section in COLLECTION_SECTIONS - allowed:
        if draft.get(section) != []:
            fail(f"delegation result draft populated undeclared section {section}")
    if "uncertainty" not in allowed and draft.get("uncertainty") != {
        "level": "none", "description": None, "evidenceRefs": []
    }:
        fail("delegation result draft populated undeclared section uncertainty")
    return draft


def normalize_output(provider: str, output_path: str, task_path: str) -> dict[str, Any]:
    task = delegation.read_object(
        task_path, label="delegation task", max_bytes=delegation.LIMITS["taskBytes"]
    )
    runtime.validate_model("delegation-task", task)
    return _validate_normalized_draft(_decode_provider_output(provider, output_path), task)


def verify_managed_child_attestation(
    provider: str, output_path: str, prepared: dict[str, Any], task: dict[str, Any],
) -> dict[str, Any]:
    """Pure ordered verifier for the provider-native managed-child event stream."""
    if provider != prepared["provider"] or provider not in {"codex", "claude", "opencode"}:
        fail("provider managed-child receipt names another provider")
    _prepared_task(prepared, task)
    value = delegation.read_object(
        output_path, label="provider managed-child output",
        max_bytes=delegation.LIMITS["resultBytes"],
    )
    receipt = value.get("managedChildExecutionAttestation")
    if not isinstance(receipt, dict) or set(receipt) != {"attestationKind", "events"}:
        fail("provider managed-child output has no structured child receipt")
    if receipt["attestationKind"] != "provider-native-managed-child-event-receipt/v1":
        fail("provider managed-child receipt has an unsupported attestation kind")
    events = receipt["events"]
    if not isinstance(events, list) or len(events) != 4 or not all(isinstance(event, dict) for event in events):
        fail("provider managed-child receipt must contain exactly four structured events")

    state = "initial"
    root_id: str | None = None
    child_id: str | None = None
    terminal_status: str | None = None
    root_fields = {
        "sequence", "eventType", "rootInvocationId", "executionId",
        "executionVersion", "workspaceId", "profileId", "phaseId", "attempt", "planId",
    }
    child_fields = {"sequence", "eventType", "rootInvocationId", "childInvocationId"}
    bound_fields = {
        "sequence", "eventType", "rootInvocationId", "childInvocationId",
        "taskId", "taskDigest",
    }
    terminal_fields = bound_fields | {"status"}
    for index, event in enumerate(events, start=1):
        if type(event.get("sequence")) is not int or event["sequence"] != index:
            fail("provider managed-child receipt sequence is non-canonical")
        event_type = event.get("eventType")
        if state == "terminal":
            fail("provider managed-child receipt has an event after its terminal event")
        if state == "initial":
            if event_type != "root.started" or set(event) != root_fields:
                fail("provider managed-child receipt does not start with the root invocation")
            root_id = event["rootInvocationId"]
            expected_root = {
                "executionId": prepared["executionId"],
                "executionVersion": task["executionVersion"],
                "workspaceId": prepared["workspaceId"],
                "profileId": prepared["profileId"],
                "phaseId": prepared["phaseId"],
                "attempt": prepared["attempt"],
                "planId": prepared["planId"],
            }
            if any(event[field] != expected for field, expected in expected_root.items()):
                fail("provider managed-child receipt is foreign or stale")
            if not isinstance(root_id, str) or re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", root_id) is None:
                fail("provider managed-child receipt has an invalid root invocation ID")
            state = "root"
        elif state == "root":
            if event_type != "child.started" or set(event) != child_fields:
                fail("provider managed-child receipt has no canonical child start")
            child_id = event["childInvocationId"]
            if (
                event["rootInvocationId"] != root_id
                or not isinstance(child_id, str)
                or re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", child_id) is None
                or child_id == root_id
            ):
                fail("provider managed-child receipt does not prove a distinct child invocation")
            state = "child-started"
        elif state == "child-started":
            if event_type != "child.task.bound" or set(event) != bound_fields:
                fail("provider managed-child receipt has no canonical task binding after child start")
            if (
                event["rootInvocationId"] != root_id
                or event["childInvocationId"] != child_id
                or event["taskId"] != task["taskId"]
                or event["taskDigest"] != task["taskDigest"]
            ):
                fail("provider managed-child receipt task binding is foreign or stale")
            state = "task-bound"
        elif state == "task-bound":
            if event_type not in {"child.completed", "child.failed"} or set(event) != terminal_fields:
                fail("provider managed-child receipt has no canonical terminal child event")
            terminal_status = "completed" if event_type == "child.completed" else "failed"
            if (
                event["rootInvocationId"] != root_id
                or event["childInvocationId"] != child_id
                or event["taskId"] != task["taskId"]
                or event["taskDigest"] != task["taskDigest"]
                or event["status"] != terminal_status
            ):
                fail("provider managed-child receipt terminal event is foreign or inconsistent")
            state = "terminal"
    if state != "terminal" or root_id is None or child_id is None or terminal_status is None:
        fail("provider managed-child receipt is incomplete")
    return {
        "provider": provider,
        "attestationKind": receipt["attestationKind"],
        "rootInvocationId": root_id,
        "childInvocationId": child_id,
        "terminalStatus": terminal_status,
        "orderedEventCount": len(events),
        "orderedEventDigest": digest_bytes(runtime.canonical_bytes(events)),
    }


def _load_publication_inputs(
    prepared_path: str, task_path: str, key: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prepared = delegation.read_object(
        prepared_path, label="prepared worker plan", max_bytes=MAX_PACKET_BYTES * 8
    )
    task = delegation.read_object(
        task_path, label="delegation task", max_bytes=delegation.LIMITS["taskBytes"]
    )
    if task_execution_key(prepared, task) != key:
        fail("worker task key differs from host derivation")
    _prepared_task(prepared, task)
    return prepared, task


def publish_managed_child_receipt(
    project_root: str, key: str, invocation_id: str, provider: str,
    output_path: str, prepared_path: str, task_path: str,
) -> dict[str, Any]:
    prepared, task = _load_publication_inputs(prepared_path, task_path, key)
    verified = verify_managed_child_attestation(provider, output_path, prepared, task)
    root = _ensure_execution_dir(project_root, key)
    with _task_lock(root, key):
        _recover_temporaries(root, key, prepared, task)
        claim, _ = _read_json_relative(root, _execution_relative(key, "claim.json"))
        _validate_claim(claim, key, task["taskDigest"])
        if claim["invocationId"] != invocation_id or claim["status"] != "active":
            fail("managed-child receipt does not belong to the active host invocation")
        receipt = {
            "schemaVersion": MANAGED_CHILD_RECEIPT_SCHEMA,
            "commitState": "committed",
            "receiptId": "",
            "receiptDigest": "",
            "provider": provider,
            "attestationKind": verified["attestationKind"],
            "hostInvocationId": invocation_id,
            "rootInvocationId": verified["rootInvocationId"],
            "childInvocationId": verified["childInvocationId"],
            "executionId": prepared["executionId"],
            "executionVersion": task["executionVersion"],
            "workspaceId": prepared["workspaceId"],
            "profileId": prepared["profileId"],
            "phaseId": prepared["phaseId"],
            "attempt": prepared["attempt"],
            "planId": prepared["planId"],
            "taskId": task["taskId"],
            "taskDigest": task["taskDigest"],
            "taskExecutionKey": key,
            "terminalStatus": verified["terminalStatus"],
            "orderedEventCount": verified["orderedEventCount"],
            "orderedEventDigest": verified["orderedEventDigest"],
        }
        receipt["receiptDigest"] = _managed_child_receipt_digest(receipt)
        receipt["receiptId"] = "R-" + receipt["receiptDigest"][7:]
        _validate_managed_child_receipt_record(receipt, key, invocation_id, prepared, task)
        relative = _managed_child_receipt_relative(key, invocation_id)
        runtime.ensure_secure_directory(root, relative.rsplit("/", 1)[0])
        _publish_json(root, relative, receipt, immutable=True, expected_current=None)
        # The separate no-replace commitment binds the entire artifact, including
        # identities and terminal status. A visible receipt alone is not a commit.
        commit_relative = relative.replace("receipt.json", "receipt-commit.json")
        committed_bytes, artifact_identity = runtime.safe_read_private_bytes(
            Path(relative), project_root=root, max_bytes=MAX_PACKET_BYTES
        )
        if committed_bytes != runtime.canonical_bytes(receipt) + b"\n":
            fail("managed-child receipt changed before host commitment")
        _publish_json(root, commit_relative, delegation.managed_child_receipt_commit_record(receipt, artifact_identity),
                      immutable=True, expected_current=None)
        committed = _read_managed_child_receipt_record(root, key, invocation_id, prepared, task)
        return {"receiptObject": committed}


def bind_authoritative_result(
    project_root: str, key: str, invocation_id: str, draft_path: str,
    prepared_path: str, task_path: str, *, managed_child: bool,
) -> dict[str, Any]:
    prepared, task = _load_publication_inputs(prepared_path, task_path, key)
    draft = delegation.read_object(
        draft_path, label="delegation result draft", max_bytes=delegation.LIMITS["resultBytes"]
    )
    root = _ensure_execution_dir(project_root, key)
    with _task_lock(root, key):
        claim, _ = _read_json_relative(root, _execution_relative(key, "claim.json"))
        _validate_claim(claim, key, task["taskDigest"])
        if claim["invocationId"] != invocation_id or claim["status"] != "active":
            fail("result binding does not belong to the active host invocation")
        if managed_child:
            load_committed_completed_managed_child_receipt(root, key, invocation_id, prepared, task)
            authority = None
        else:
            authority = delegation.host_worker_execution_authority(
                prepared["provider"], invocation_id
            )
        return delegation.bind_result(
            draft, prepared["authorityPacket"], prepared["plan"], task,
            prepared.get("evidenceManifest"), authority=authority,
            managed_child_project_root=root if managed_child else None,
            managed_child_invocation_id=invocation_id if managed_child else None,
        )


def merge_authoritative_results(project_root: str, prepared_path: str) -> dict[str, Any]:
    prepared = delegation.read_object(
        prepared_path, label="prepared worker plan", max_bytes=MAX_PACKET_BYTES * 8
    )
    results: list[dict[str, Any]] = []
    for task in prepared["plan"]["tasks"]:
        key = task_execution_key(prepared, task)
        root = _project_root(project_root)
        try:
            with _task_lock(root, key):
                authoritative = _read_authoritative_head(root, key, prepared, task)
        except runtime.ContractError as error:
            if "No such file" in str(error):
                continue
            raise
        if authoritative is None:
            continue
        result, _ = authoritative
        results.append(result)
    return delegation.merge(
        prepared["plan"], results, prepared["authorityPacket"],
        prepared.get("evidenceManifest"), managed_child_project_root=project_root,
    )


def common(command: argparse.ArgumentParser) -> None:
    command.add_argument("execution_id")
    command.add_argument("--project-root", required=True)
    command.add_argument("--static-signal", action="append", default=[])
    command.add_argument("--request-skill", action="append", default=[])
    command.add_argument("--deep-load-skill", action="append", default=[])


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Prepare CTX-07B-R2 host routes/packets and manage worker state."
    )
    commands = result.add_subparsers(dest="command", required=True)
    prepare_command = commands.add_parser("prepare-plan")
    common(prepare_command)
    prepare_command.add_argument("--plan", required=True)
    render_command = commands.add_parser("render-prompt")
    render_command.add_argument("--packet", required=True)
    render_child_command = commands.add_parser("render-child-prompt")
    render_child_command.add_argument("--packet", required=True)
    capsule_command = commands.add_parser("materialize-capsule")
    capsule_command.add_argument("--packet", required=True)
    capsule_command.add_argument("--project-root", required=True)
    capsule_command.add_argument("--capsule", required=True)
    normalize_command = commands.add_parser("normalize-output")
    normalize_command.add_argument("provider")
    normalize_command.add_argument("--output", required=True)
    normalize_command.add_argument("--task", required=True)
    attestation_command = commands.add_parser("verify-managed-child-attestation")
    attestation_command.add_argument("--provider", required=True, choices=["codex", "claude", "opencode"])
    attestation_command.add_argument("--output", required=True)
    attestation_command.add_argument("--prepared", required=True)
    attestation_command.add_argument("--task", required=True)
    receipt_command = commands.add_parser("publish-managed-child-receipt")
    receipt_command.add_argument("--project-root", required=True)
    receipt_command.add_argument("--task-execution-key", required=True)
    receipt_command.add_argument("--invocation-id", required=True)
    receipt_command.add_argument("--provider", required=True, choices=["codex", "claude", "opencode"])
    receipt_command.add_argument("--output", required=True)
    receipt_command.add_argument("--prepared", required=True)
    receipt_command.add_argument("--task", required=True)
    bind_host_command = commands.add_parser("bind-host-worker-result")
    bind_host_command.add_argument("--project-root", required=True)
    bind_host_command.add_argument("--task-execution-key", required=True)
    bind_host_command.add_argument("--invocation-id", required=True)
    bind_host_command.add_argument("--draft", required=True)
    bind_host_command.add_argument("--prepared", required=True)
    bind_host_command.add_argument("--task", required=True)
    bind_child_command = commands.add_parser("bind-managed-child-result")
    bind_child_command.add_argument("--project-root", required=True)
    bind_child_command.add_argument("--task-execution-key", required=True)
    bind_child_command.add_argument("--invocation-id", required=True)
    bind_child_command.add_argument("--draft", required=True)
    bind_child_command.add_argument("--prepared", required=True)
    bind_child_command.add_argument("--task", required=True)
    merge_command = commands.add_parser("merge-authoritative-results")
    merge_command.add_argument("--project-root", required=True)
    merge_command.add_argument("--prepared", required=True)
    claim_command = commands.add_parser("claim-task")
    claim_command.add_argument("--project-root", required=True)
    claim_command.add_argument("--prepared", required=True)
    claim_command.add_argument("--task", required=True)
    publish_command = commands.add_parser("publish-task-result")
    publish_command.add_argument("--project-root", required=True)
    publish_command.add_argument("--task-execution-key", required=True)
    publish_command.add_argument("--invocation-id", required=True)
    publish_command.add_argument("--result", required=True)
    publish_command.add_argument("--prepared", required=True)
    publish_command.add_argument("--task", required=True)
    publish_command.add_argument("--usage-summary")
    publish_command.add_argument("--raw-trace")
    finalize_command = commands.add_parser("finalize-task")
    finalize_command.add_argument("--project-root", required=True)
    finalize_command.add_argument("--task-execution-key", required=True)
    finalize_command.add_argument("--invocation-id", required=True)
    finalize_command.add_argument("--status", required=True, choices=["failed", "timed_out", "interrupted", "publication_failed"])
    finalize_command.add_argument("--usage-summary")
    finalize_command.add_argument("--raw-trace")
    event_command = commands.add_parser("worker-event")
    event_command.add_argument("--project-root", required=True)
    event_command.add_argument("--task-execution-key", required=True)
    event_command.add_argument("--event", required=True, choices=["worker.started", "worker.failed", "worker.timed_out", "worker.interrupted"])
    event_command.add_argument("--invocation-id")
    return result


def main(argv: list[str]) -> int:
    try:
        args = parser().parse_args(argv[1:])
        if args.command == "prepare-plan":
            value = prepare(args)
            sys.stdout.buffer.write(runtime.canonical_bytes(value) + b"\n")
        elif args.command == "render-prompt":
            packet = delegation.read_object(
                args.packet, label="worker context packet", max_bytes=MAX_PACKET_BYTES
            )
            sys.stdout.write(render_prompt(packet, load_policy()))
        elif args.command == "render-child-prompt":
            packet = delegation.read_object(
                args.packet, label="worker context packet", max_bytes=MAX_PACKET_BYTES
            )
            sys.stdout.write(render_child_prompt(packet, load_policy()))
        elif args.command == "materialize-capsule":
            value = materialize_capsule(args.packet, args.project_root, args.capsule, str(HOST_FRAMEWORK_ROOT))
            sys.stdout.buffer.write(runtime.canonical_bytes(value) + b"\n")
        elif args.command == "normalize-output":
            value = normalize_output(args.provider, args.output, args.task)
            sys.stdout.buffer.write(runtime.canonical_bytes(value) + b"\n")
        elif args.command == "verify-managed-child-attestation":
            prepared = delegation.read_object(
                args.prepared, label="prepared worker plan", max_bytes=MAX_PACKET_BYTES * 8
            )
            task = delegation.read_object(
                args.task, label="delegation task", max_bytes=delegation.LIMITS["taskBytes"]
            )
            value = verify_managed_child_attestation(args.provider, args.output, prepared, task)
            sys.stdout.buffer.write(runtime.canonical_bytes(value) + b"\n")
        elif args.command == "publish-managed-child-receipt":
            value = publish_managed_child_receipt(
                args.project_root, args.task_execution_key, args.invocation_id,
                args.provider, args.output, args.prepared, args.task,
            )
            sys.stdout.buffer.write(runtime.canonical_bytes(value) + b"\n")
        elif args.command in {"bind-host-worker-result", "bind-managed-child-result"}:
            value = bind_authoritative_result(
                args.project_root, args.task_execution_key, args.invocation_id,
                args.draft, args.prepared, args.task,
                managed_child=args.command == "bind-managed-child-result",
            )
            sys.stdout.buffer.write(runtime.canonical_bytes(value) + b"\n")
        elif args.command == "merge-authoritative-results":
            value = merge_authoritative_results(args.project_root, args.prepared)
            sys.stdout.buffer.write(runtime.canonical_bytes(value) + b"\n")
        elif args.command == "claim-task":
            value = claim_task(args.project_root, args.prepared, args.task)
            sys.stdout.buffer.write(runtime.canonical_bytes(value) + b"\n")
        elif args.command == "publish-task-result":
            value = publish_task(
                args.project_root, args.task_execution_key, args.invocation_id,
                args.result, args.prepared, args.task, args.usage_summary,
                args.raw_trace,
            )
            sys.stdout.buffer.write(runtime.canonical_bytes(value) + b"\n")
        elif args.command == "finalize-task":
            finalize_task(
                args.project_root, args.task_execution_key, args.invocation_id,
                args.status, args.usage_summary, args.raw_trace,
            )
        else:
            _event(args.project_root, args.event, args.task_execution_key, args.invocation_id)
        return 0
    except (runtime.ContractError, OSError, ValueError, TypeError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
