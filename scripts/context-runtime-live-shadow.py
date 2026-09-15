#!/usr/bin/env python3
"""CTX-09C host-owned live shadow harness.

This is intentionally a host helper, not a new public runtime mode.  It runs
the authoritative legacy command and a non-authoritative v2 command from one
captured host input, retains a sensitive local exact legacy outcome separately
from private CTX-09B producer artifacts, and
then asks the existing offline comparator for a diagnostic.  It never retries
either command and never forwards the shadow output to the caller.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import secrets
import subprocess
import stat
import sys
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mode = load("ctx09c_mode", HERE / "context-runtime-mode.py")
comparison = load("ctx09c_comparison", HERE / "lib/context-comparison.py")
shared = load("ctx09c_shared", HERE / "lib/context-shadow-input.py")
backend = load("ctx09c_backend", HERE / "lib/context-shadow-backend.py")
consumer = load("ctx09c_consumer", HERE / "lib/context-shadow-consumer.py")
privacy = consumer.privacy
_TEST_EVENT_HOOK = None
_TEST_FRAMEWORK_ROOT = None


def authority_event(name):
    if _TEST_EVENT_HOOK is not None:
        _TEST_EVENT_HOOK(name)

SHADOW_NAMESPACE = ".mana/runtime/shadows"
USAGE_FIELDS = ("input", "cachedInput", "uncachedInput", "output", "reasoning")
STATE_VERSION = "mana.context-runtime.live-shadow-state/v1"
HEAD_NAME = "live-shadow-head-v1.json"
ARTIFACT_MAX_BYTES = 256 * 1024
TERMINAL = {"completed", "manual_recovery_required"}
TRANSITIONS = {
    "initialized": {"legacy_committed", "manual_recovery_required"},
    "legacy_committed": {"shadow_completed", "shadow_failed", "shadow_unavailable", "completed", "manual_recovery_required"},
    "shadow_completed": {"comparison_completed", "comparison_indeterminate", "manual_recovery_required"},
    "shadow_failed": {"completed"}, "shadow_unavailable": {"completed"},
    "comparison_completed": {"completed"}, "comparison_indeterminate": {"completed"},
    "completed": set(), "manual_recovery_required": set(),
}



class FaultInjected(RuntimeError):
    pass


class ManualRecoveryRequired(mode.runtime.ContractError):
    """No attested delivery exists; never manufacture or reexecute a result."""
    manualRecoveryRequired = True


def fault(point):
    """Permanent, opt-in crash boundary used by the local recovery matrix."""
    requested = set(filter(None, (os.environ.get("MANA_CTX09C_FAULT", "") + "," +
                                  os.environ.get("MANA_CTX09C_FAULT_POINTS", "")).split(",")))
    if point in requested:
        if os.environ.get("MANA_CTX09C_FAULT_EXIT") == "1":
            os._exit(99)
        raise FaultInjected("CTX-09C fault point: " + point)


def canonical(value: object) -> bytes:
    return mode.canonical(value)


def command(value: str, name: str) -> list[str]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise mode.runtime.ContractError(f"invalid {name} command") from error
    if (not isinstance(decoded, list) or not decoded or not decoded[0]
            or any(not isinstance(item, str) or "\x00" in item for item in decoded)):
        raise mode.runtime.ContractError(f"invalid {name} command")
    return decoded


def private_write(root, relative: str, payload: bytes) -> None:
    """FD-relative no-replace publication below the private shadow tree.

    CTX-09A's producer primitive treats all ancestors as private, whereas
    `.mana/runtime` deliberately remains legacy-owned and may be 0755.  This
    equivalent primitive attests the private suffix only and never chmods the
    shared ancestors.
    """
    components = mode.relative_path(relative)
    with private_directory(root, components[:-1]) as parent:
        mode.absent(parent, components[-1])
        temporary = ".live-shadow.stage." + secrets.token_hex(16)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(fd, remaining)
                if written == 0:
                    raise OSError("short live-shadow artifact write")
                remaining = remaining[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(temporary, components[-1], src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            os.unlink(temporary, dir_fd=parent)
            os.fsync(parent)
        except BaseException:
            try: os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError: pass
            raise


def _owned_private_write(root, base, relative, payload, packet_digest, fault_point=None):
    """Crash-reconcilable publication with an identity-bound staging owner."""
    components = mode.relative_path(relative)
    token = secrets.token_hex(16)
    stage_name = ".live-shadow.stage." + token
    owner_name = ".live-shadow.owner." + token
    owner = {"schemaVersion": "mana.context-runtime.live-shadow-staging-owner/v1",
             "comparisonExecutionId": base.rsplit("/", 1)[-1], "base": base,
             "parent": "/".join(components[:-1]), "target": relative,
             "packetDigest": packet_digest, "payloadDigest": shared.digest(payload)}
    with private_directory(root, components[:-1]) as parent:
        mode.absent(parent, components[-1])
        owner_fd = os.open(owner_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600, dir_fd=parent)
        try:
            os.write(owner_fd, canonical(owner)); os.fsync(owner_fd)
        finally:
            os.close(owner_fd)
        fd = os.open(stage_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(fd, remaining)
                if written == 0:
                    raise OSError("short owned live-shadow artifact write")
                remaining = remaining[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            if fault_point:
                fault(fault_point)
            os.link(stage_name, components[-1], src_dir_fd=parent, dst_dir_fd=parent,
                    follow_symlinks=False)
            os.unlink(stage_name, dir_fd=parent)
            os.unlink(owner_name, dir_fd=parent)
            os.fsync(parent)
        except BaseException:
            if os.environ.get("MANA_CTX09C_FAULT_EXIT") != "1":
                for name in (stage_name, owner_name):
                    try: os.unlink(name, dir_fd=parent)
                    except FileNotFoundError: pass
            raise


def _invalid_artifact(category: str, payload: bytes) -> dict[str, object]:
    """A durable-safe validation observation, never an output surrogate."""
    return {"status": "invalid", "errorCategory": category,
            "byteCount": min(len(payload), ARTIFACT_MAX_BYTES + 1)}


def validate_artifact(payload: bytes, packet: dict, role: str) -> tuple[dict[str, object], bytes | None]:
    """Validate a producer candidate before it receives any producer receipt.

    CTX-09B's parser/schema/semantic checks are deliberately reused here so
    that a live side cannot publish an artifact which the offline comparator
    would later reject.  The returned bytes are canonical structured data, not
    the provider's raw response stream.
    """
    if not isinstance(payload, bytes) or len(payload) > ARTIFACT_MAX_BYTES:
        return _invalid_artifact("malformed", payload if isinstance(payload, bytes) else b""), None
    if privacy.PRIVATE_MARKER.search(payload.decode("utf-8", errors="replace")):
        return _invalid_artifact("privacy-invalid", payload), None
    try:
        contracts = comparison.Contracts()
        value, reason = comparison.native_input(payload, contracts)
    except (comparison.mode.runtime.ContractError, UnicodeError, ValueError, RecursionError):
        return _invalid_artifact("semantic-invalid", payload), None
    if value is None:
        # A syntactically valid but foreign object is schema-invalid for this
        # producer contract.  Do not make "unsupported" an artifact state.
        return _invalid_artifact("schema-invalid", payload), None
    identity = packet["identity"]
    target_key = shared.digest(shared.canonical(packet["target"]))
    if value.get("profileId") != packet["profileId"] or value.get("targetKey") != target_key:
        return _invalid_artifact("semantic-invalid", payload), None
    canonical_payload = canonical(value)
    try:
        privacy.validate(value)
    except privacy.PrivacyError:
        return _invalid_artifact("privacy-invalid", payload), None
    return ({"status": "valid", "byteCount": len(canonical_payload),
             "sha256": shared.digest(canonical_payload), "role": role,
             "producerId": identity["legacyProducerId" if role == "legacy" else "shadowProducerId"]},
            canonical_payload)


def _missing_usage(invocation_id: str, reason: str = "missing") -> dict[str, object]:
    return {"availability": "unavailable", "reportedStatus": "unavailable", "status": "unavailable",
            "invocationId": invocation_id, "parseErrors": 0, "totals": dict.fromkeys(USAGE_FIELDS),
            "missing": list(USAGE_FIELDS), "reason": reason}


def read_usage(root, relative: str | None, execution_id: str, profile_id: str,
               invocation_id: str) -> dict[str, object]:
    if relative is None:
        return _missing_usage(invocation_id)
    try:
        _, payload = mode.project_file(root, relative, with_bytes=True, private=True, max_bytes=256 * 1024)
    except FileNotFoundError:
        return _missing_usage(invocation_id)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return {**_missing_usage(invocation_id, "invalid-summary"), "availability": "invalid",
                "parseErrors": 1, "status": "invalid"}
    if not isinstance(value, dict):
        return {**_missing_usage(invocation_id, "invalid-summary"), "availability": "invalid",
                "parseErrors": 1, "status": "invalid"}
    try:
        mode.runtime.validate_model("usage-summary", value)
    except mode.runtime.ContractError:
        return {**_missing_usage(invocation_id, "invalid-summary"), "availability": "invalid",
                "parseErrors": 1, "status": "invalid"}
    if value["executionId"] != execution_id or value["profileId"] != profile_id:
        return {**_missing_usage(invocation_id, "identity-mismatch"), "availability": "invalid",
                "parseErrors": 1, "status": "invalid"}
    totals = value["totals"]
    missing = [field for field in USAGE_FIELDS if totals[field] is None]
    classification = mode.runtime.usage_totals_status(totals, value["parseErrors"])
    availability = "invalid" if classification == "invalid" else classification
    return {"availability": availability, "reportedStatus": value["usageStatus"], "status": value["status"],
            "invocationId": invocation_id, "parseErrors": value["parseErrors"],
            "totals": {field: totals[field] for field in USAGE_FIELDS}, "missing": missing,
            "reason": None if availability == value["usageStatus"] else "incoherent-summary"}


def capture_usage(root, supplied: str | None, execution_id: str, profile_id: str,
                  invocation_id: str) -> dict[str, object]:
    # A normal provider invocation writes this existing CTX-01 location. The
    # side is captured before the next runtime can replace that aggregate.
    path = supplied or f".mana/runtime/metrics/{execution_id}/usage-summary-v1.json"
    try:
        return read_usage(root, path, execution_id, profile_id, invocation_id)
    except FileNotFoundError:
        return read_usage(root, None, execution_id, profile_id, invocation_id)


def usage_comparison(legacy: dict[str, object], v2: dict[str, object]) -> dict[str, object]:
    differences: dict[str, int | None] = {}
    reasons: dict[str, str | None] = {}
    missing: list[str] = []
    both_measured = legacy["availability"] == "measured" and v2["availability"] == "measured"
    for field in USAGE_FIELDS:
        left, right = legacy["totals"][field], v2["totals"][field]
        differences[field] = right - left if both_measured and isinstance(left, int) and isinstance(right, int) else None
        reasons[field] = None if differences[field] is not None else (
            "legacy-" + str(legacy["availability"]) if legacy["availability"] != "measured" else
            "shadow-" + str(v2["availability"]) if v2["availability"] != "measured" else
            "missing-dimension")
        if left is None:
            missing.append("legacy." + field)
        if right is None:
            missing.append("v2." + field)
    if "invalid" in {legacy["availability"], v2["availability"]}:
        availability = "invalid"
    elif "unavailable" in {legacy["availability"], v2["availability"]}:
        availability = "unavailable"
    elif "partial" in {legacy["availability"], v2["availability"]}:
        availability = "partial"
    else:
        availability = "measured"
    return {"schemaVersion": "mana.context-runtime.shadow-usage-comparison/v1",
            "calibrationState": "provisional-no-empirical-baseline",
            "legacy": legacy, "v2": v2, "v2MinusLegacy": differences,
            "deltaReasons": reasons, "availability": availability, "missingOrIncomplete": sorted(missing),
            "authority": "none", "permissionGrant": "none", "externalActions": "disabled"}


def main():
    parser = argparse.ArgumentParser(description="CTX-09C canonical live shadow harness")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--packet-stdin", action="store_true", required=True)
    args = parser.parse_args()
    status, _, output, diagnostics = run_shared(args.project_root, sys.stdin.buffer.read(shared.MAX_BYTES + 1))
    sys.stdout.buffer.write(output)
    sys.stderr.buffer.write(diagnostics)
    return status


@contextmanager
def private_directory(root, parts):
    with root.directory_fd(parts, create=True) as final:
        start = 3 if parts[:3] in ([".mana", "runtime", "runs"], [".mana", "runtime", "metrics"]) else 2
        for length in range(start + 1, len(parts) + 1):
            with root.directory_fd(parts[:length]) as directory:
                if stat.S_IMODE(os.fstat(directory).st_mode) != 0o700:
                    raise mode.runtime.ContractError("producer namespace is not private")
        root.attest_directory(parts, final)
        yield final


@contextmanager
def producer_lock(root, relative):
    parts = mode.relative_path(relative)
    with private_directory(root, parts[:-1]) as parent:
        # Concurrent O_CREAT on a just-created APFS name may report ENOENT.
        # Elect the file creator explicitly; every retry re-attests the pinned
        # parent, and the locked inode is re-attested below before any effect.
        for attempt in range(8):
            root.attest_directory(parts[:-1], parent)
            try:
                try:
                    fd = os.open(parts[-1], os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                except FileExistsError:
                    fd = os.open(parts[-1], os.O_RDWR | os.O_NOFOLLOW, dir_fd=parent)
                break
            except FileNotFoundError:
                if attempt == 7:
                    raise
        try:
            metadata = os.fstat(fd)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600):
                raise mode.runtime.ContractError("producer lock is not private")
            fcntl.flock(fd, fcntl.LOCK_EX)
            root.attest_directory(parts[:-1], parent)
            if not mode.runtime._verify_identity(parent, parts[-1], mode.runtime._entry_identity(metadata)):
                raise mode.runtime.ContractError("producer lock binding changed")
            yield
        finally:
            os.close(fd)


def _read_private(root, relative):
    return mode.project_file(root, relative, with_bytes=True, private=True, max_bytes=16 * 1024 * 1024)[1]


def _immutable(root, relative, payload):
    """Publish once, or converge only on exactly the already committed bytes."""
    try:
        current = _read_private(root, relative)
    except FileNotFoundError:
        private_write(root, relative, payload)
        return
    if current != payload:
        raise mode.runtime.ContractError("conflicting immutable live-shadow artifact")


class Journal:
    """A small CTX-06B-style immutable-bundle journal for one comparison."""
    def __init__(self, root, base, packet):
        self.root, self.base, self.packet = root, base, packet
        self.packet_digest = shared.digest(packet)
        self.head_path = base + "/" + HEAD_NAME
        with private_directory(root, base.split("/")):
            pass
        self.current = self._load()

    def _load(self):
        try:
            commitment, encoded = _outcome_bytes(self.root, self.head_path)
        except FileNotFoundError:
            return None
        value = shared.decode(encoded)
        anchor_path = self.base + "/heads/" + str(value.get("bundleId")) + "/head-commit-v1.json"
        _, anchor_bytes = _outcome_bytes(self.root, anchor_path)
        anchor = shared.decode(anchor_bytes)
        if (not isinstance(anchor, dict) or canonical(anchor) != anchor_bytes
                or set(anchor) != {"schemaVersion", "head", "currentBundle"}
                or anchor["schemaVersion"] != "mana.context-runtime.live-shadow-head-commit/v1"
                or anchor["head"] != commitment):
            raise mode.runtime.ContractError("live-shadow HEAD instance is not committed")
        _outcome_bytes(self.root, self.head_path, anchor["head"])
        self._validate_state(value, encoded, anchor["currentBundle"])
        return value

    def _validate_state(self, value, encoded, current_bundle_binding=None):
        if (not isinstance(value, dict) or value.get("schemaVersion") != STATE_VERSION
                or value.get("packetDigest") != self.packet_digest
                or value.get("comparisonExecutionId") != self.base.rsplit("/", 1)[-1]
                or type(value.get("revision")) is not int or not 1 <= value["revision"] <= 8
                or value.get("stage") not in TRANSITIONS):
            raise mode.runtime.ContractError("invalid or foreign live-shadow HEAD")
        base_fields = {"schemaVersion", "comparisonExecutionId", "packetDigest", "revision", "stage",
                       "previousHeadDigest", "bundleId", "producerRecords", "packetReference"}
        optional_fields = {"input", "legacy", "legacyReceipt", "artifacts", "candidateBindings", "usage", "validation", "shadow",
                           "shadowReceipt", "comparison", "comparisonAttempt", "comparisonSeal", "comparisonRecord", "reason"}
        if not base_fields <= set(value) or set(value) - base_fields - optional_fields:
            raise mode.runtime.ContractError("invalid live-shadow state fields")
        if value["stage"] == "initialized" and set(value) != base_fields | {"input"}:
            raise mode.runtime.ContractError("invalid initialized stage fields")
        if canonical(value) != encoded:
            raise mode.runtime.ContractError("noncanonical live-shadow HEAD")
        identity_state = {k: v for k, v in value.items() if k != "bundleId"}
        bundle_id = "B-" + shared.digest(canonical({"previous": value.get("previousHeadDigest"), "state": identity_state}))
        if value.get("bundleId") != bundle_id:
            raise mode.runtime.ContractError("foreign live-shadow bundle identity")
        bundle_path = self.base + "/bundles/" + bundle_id + "/bundle-v1.json"
        if current_bundle_binding is None:
            bundle_bytes = _read_private(self.root, bundle_path)
        else:
            _, bundle_bytes = _outcome_bytes(self.root, bundle_path, current_bundle_binding)
        bundle = shared.decode(bundle_bytes)
        if (canonical(bundle) != bundle_bytes or set(bundle) != {
                "schemaVersion", "state", "stateDigest", "bundleId", "previousHeadDigest", "previousBundle"}
                or bundle.get("schemaVersion") != "mana.context-runtime.live-shadow-bundle/v1"
                or bundle.get("state") != value or bundle.get("stateDigest") != shared.digest(encoded)
                or bundle.get("previousHeadDigest") != value.get("previousHeadDigest")
                or bundle.get("bundleId") != bundle_id):
            raise mode.runtime.ContractError("live-shadow HEAD bundle mismatch")
        # Walk the complete reachable chain. No directory scan or caller-selected
        # predecessor can confer authority; every edge binds bytes and inode.
        previous = bundle["previousBundle"]
        if value["revision"] == 1:
            if previous is not None or value.get("previousHeadDigest") is not None or value["stage"] != "initialized":
                raise mode.runtime.ContractError("incomplete live-shadow genesis")
        else:
            if not isinstance(previous, dict) or not previous.get("path", "").startswith(self.base + "/bundles/"):
                raise mode.runtime.ContractError("missing live-shadow previous bundle")
            _, prior_bytes = _outcome_bytes(self.root, previous["path"], previous)
            prior = shared.decode(prior_bytes)["state"]
            if (previous["path"] != self.base + "/bundles/" + prior["bundleId"] + "/bundle-v1.json"
                    or prior["revision"] != value["revision"] - 1
                    or shared.digest(canonical(prior)) != value["previousHeadDigest"]
                    or value["stage"] not in TRANSITIONS.get(prior["stage"], set())):
                raise mode.runtime.ContractError("invalid live-shadow chain transition")
            for name in ("legacyReceipt", "shadowReceipt", "comparisonAttempt", "comparisonSeal", "comparisonRecord", "packetReference"):
                if name in prior and value.get(name) != prior[name]:
                    raise mode.runtime.ContractError("live-shadow chain changed a commitment")
            if any(value.get("candidateBindings", {}).get(role) != commitment
                   for role, commitment in prior.get("candidateBindings", {}).items()):
                raise mode.runtime.ContractError("live-shadow chain changed a candidate binding")
            if (prior["stage"] == "legacy_committed" and value["stage"] == "completed"
                    and prior["legacy"]["exitStatus"] == 0):
                raise mode.runtime.ContractError("completed before shadow/comparison")
            self._validate_state(prior, canonical(prior))
        _attest_state(self, value)

    def _cas_head(self, expected, next_value, bundle_binding):
        parts = mode.relative_path(self.head_path)
        encoded = canonical(next_value)
        # CAS authority is a fully attested HEAD, not merely matching JSON.
        verified = self._load()
        if (None if verified is None else canonical(verified)) != expected:
            raise mode.runtime.ContractError("live-shadow HEAD CAS conflict")
        with self.root.directory_fd(parts[:-1], create=True) as directory:
            try:
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            except FileNotFoundError:
                current = None
            else:
                try:
                    current = os.read(fd, 1024 * 1024)
                finally:
                    os.close(fd)
            if current != expected:
                raise mode.runtime.ContractError("live-shadow HEAD CAS conflict")
            temporary = ".live-shadow-head.stage." + hashlib.sha256(encoded).hexdigest()[:24]
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            try:
                os.write(fd, encoded); os.fsync(fd)
            finally:
                os.close(fd)
            try:
                if os.environ.get("MANA_CTX09C_FAULT_STAGE", next_value["stage"]) == next_value["stage"]:
                    fault("during-head-cas")
                os.replace(temporary, parts[-1], src_dir_fd=directory, dst_dir_fd=directory)
                # Remember successful HEAD publication even if the subsequent
                # host fsync/return raises. The legacy barrier can deliver the
                # fully attested outcome without another fallible read.
                head_binding, current = _outcome_bytes(self.root, self.head_path)
                if current != encoded:
                    raise mode.runtime.ContractError("live-shadow HEAD publication changed")
                anchor = {"schemaVersion": "mana.context-runtime.live-shadow-head-commit/v1",
                          "head": head_binding, "currentBundle": bundle_binding}
                _immutable(self.root, self.base + "/heads/" + next_value["bundleId"] +
                           "/head-commit-v1.json", canonical(anchor))
                self.current = next_value
                os.fsync(directory)
            except BaseException:
                try: os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError: pass
                raise

    def commit(self, stage, **fields):
        previous = self.current
        if stage not in ({"initialized"} if previous is None else TRANSITIONS[previous["stage"]]):
            raise mode.runtime.ContractError("invalid live-shadow stage transition")
        state = {"schemaVersion": STATE_VERSION, "comparisonExecutionId": self.base.rsplit("/", 1)[-1],
                 "packetDigest": self.packet_digest, "revision": 1 if previous is None else previous["revision"] + 1,
                 "stage": stage, "previousHeadDigest": None if previous is None else shared.digest(canonical(previous))}
        state.update(fields)
        for name in ("legacyReceipt", "shadowReceipt", "comparisonAttempt", "comparisonSeal", "comparisonRecord", "packetReference"):
            if previous and name in previous:
                state.setdefault(name, previous[name])
        records = dict(previous.get("producerRecords", {})) if previous else {}
        candidate_bindings = dict(previous.get("candidateBindings", {})) if previous else {}
        for role, source in state.get("artifacts", {}).items():
            if role not in records:
                namespace, key = mode.receipt_location(state["comparisonExecutionId"], source["path"])
                records[role] = [_outcome_bytes(self.root, path)[0] for path in (
                    f"{namespace}/{key}/producer-receipt-v1.json",
                    f"{namespace}/{key}.commit/producer-commit-v1.json")]
            if role not in candidate_bindings:
                candidate_bindings[role] = _outcome_bytes(
                    self.root, self.base + f"/records/{role}-candidate-binding-v1.json")[0]
        state["producerRecords"] = records
        if candidate_bindings:
            state["candidateBindings"] = candidate_bindings
        bundle_id = "B-" + shared.digest(canonical({"previous": state["previousHeadDigest"], "state": state}))
        state["bundleId"] = bundle_id
        bundle = {"schemaVersion": "mana.context-runtime.live-shadow-bundle/v1", "bundleId": bundle_id,
                  "stateDigest": shared.digest(canonical(state)), "previousHeadDigest": state["previousHeadDigest"],
                  "previousBundle": None if previous is None else _outcome_bytes(
                      self.root, self.base + "/bundles/" + previous["bundleId"] + "/bundle-v1.json")[0],
                  "state": state}
        _attest_state(self, state)
        bundle_path = self.base + "/bundles/" + bundle_id + "/bundle-v1.json"
        _immutable(self.root, bundle_path, canonical(bundle))
        bundle_binding = _outcome_bytes(self.root, bundle_path)[0]
        expected = None if previous is None else canonical(previous)
        self._cas_head(expected, state, bundle_binding)
        self.current = state
        return state

    def receipt(self, name):
        try:
            return json.loads(_read_private(self.root, self.base + "/records/" + name).decode("utf-8"))
        except FileNotFoundError:
            return None


def _attest_sources(journal, sources):
    packet = shared.validate(journal.packet)
    for role, source in sources.items():
        if role not in {"legacy", "v2"} or source.get("path") != journal.base + f"/{role}-artifact-v1.json":
            raise mode.runtime.ContractError("foreign live-shadow artifact")
        current = _source(journal.root, str(journal.root.path), packet["identity"]["comparisonExecutionId"],
                          packet["profileId"], shared.digest(canonical(packet["target"])), role, source["path"])
        if current != source:
            raise mode.runtime.ContractError("live-shadow producer commitment changed")


def _shadow_receipt(journal, binding=None):
    path = journal.base + "/records/shadow-receipt-v1.json"
    commitment, encoded = _outcome_bytes(journal.root, path, binding)
    receipt = shared.decode(encoded)
    if (canonical(receipt) != encoded or not isinstance(receipt, dict)
            or set(receipt) != {"schemaVersion", "shadow", "artifacts", "usage", "validation"}
            or receipt["schemaVersion"] != "mana.context-runtime.live-shadow-shadow-receipt/v1"
            or receipt["shadow"].get("status") not in {"completed", "failed"}):
        raise mode.runtime.ContractError("invalid shadow receipt")
    _attest_sources(journal, receipt["artifacts"])
    return receipt, commitment


def _attempt_identity(journal, state):
    packet = shared.validate(journal.packet)
    return {"schemaVersion": "mana.context-runtime.comparison-attempt/v1",
            "executionId": packet["identity"]["comparisonExecutionId"],
            "inputReceiptDigest": journal.packet_digest,
            "producerReceiptDigests": {side: state["artifacts"][side]["producerReceiptDigest"] for side in ("legacy", "v2")},
            "pairIdentity": state["artifacts"], "legacyReceipt": state["legacyReceipt"],
            "shadowReceipt": state["shadowReceipt"]}


def _comparison_attempt(journal, state, binding=None, seal_binding=None):
    path = journal.base + "/records/comparison-attempt-v1.json"
    expected = _attempt_identity(journal, state)
    seal_path = journal.base + "/records/comparison-attempt-commit-v1.json"
    seal_commitment, seal_bytes = _outcome_bytes(journal.root, seal_path, seal_binding)
    seal = shared.decode(seal_bytes)
    if (not isinstance(seal, dict) or set(seal) != {"schemaVersion", "attempt", "inputReceiptDigest",
            "producerReceiptDigests", "pairIdentityDigest", "reportDigest", "resultDigest"}
            or canonical(seal) != seal_bytes or seal["schemaVersion"] != "mana.context-runtime.comparison-attempt-commit/v1"
            or seal["inputReceiptDigest"] != expected["inputReceiptDigest"]
            or seal["producerReceiptDigests"] != expected["producerReceiptDigests"]
            or seal["pairIdentityDigest"] != shared.digest(canonical(expected["pairIdentity"]))
            or (binding is not None and seal["attempt"] != binding)):
        raise mode.runtime.ContractError("invalid comparison attempt seal")
    commitment, encoded = _outcome_bytes(journal.root, path, seal["attempt"])
    attempt = shared.decode(encoded)
    if journal.receipt("comparison-intent-v1.json") != expected:
        raise mode.runtime.ContractError("comparison intent identity mismatch")
    if (not isinstance(attempt, dict) or canonical(attempt) != encoded
            or set(attempt) != set(expected) | {"report", "result"}
            or any(attempt[key] != value for key, value in expected.items())):
        raise mode.runtime.ContractError("foreign comparison attempt")
    _attest_sources(journal, state["artifacts"])
    report = attempt["report"]
    comparison.Contracts().validate(report, comparison.REPORT_SCHEMA)
    registered, plan = comparison.registration(journal.root, expected["executionId"])
    if (plan["artifacts"] != expected["pairIdentity"] or report["registration"] != registered
            or report["sources"] != expected["pairIdentity"] or report["executionId"] != expected["executionId"]):
        raise mode.runtime.ContractError("comparison report commitment mismatch")
    result = {"status": "completed", "diagnosticStatus": report["status"], "complete": report["complete"]}
    if attempt["result"] != result:
        raise mode.runtime.ContractError("comparison outcome mismatch")
    if (seal["reportDigest"] != shared.digest(canonical(report))
            or seal["resultDigest"] != shared.digest(canonical(result))):
        raise mode.runtime.ContractError("comparison output/outcome commitment mismatch")
    return result, commitment, seal_commitment


def _attest_state(journal, state):
    packet = shared.validate(journal.packet)
    stage = state["stage"]
    if stage not in {"initialized", "manual_recovery_required"} and not {
            "legacy", "legacyReceipt", "artifacts", "usage", "validation"} <= set(state):
        raise mode.runtime.ContractError("incomplete committed stage")
    shadow_status = state.get("shadow", {}).get("status")
    expected_shadow = {"shadow_completed": {"completed"}, "shadow_failed": {"failed", "timed_out", "interrupted"},
                       "shadow_unavailable": {"unavailable"}}
    if stage in expected_shadow and shadow_status not in expected_shadow[stage]:
        raise mode.runtime.ContractError("shadow expected stage mismatch")
    if stage == "legacy_committed" and any(k in state for k in ("shadow", "shadowReceipt", "comparison", "comparisonAttempt")):
        raise mode.runtime.ContractError("unexpected post-legacy stage fields")
    if stage == "completed" and not {"shadow", "comparison"} <= set(state):
        raise mode.runtime.ContractError("incomplete completed stage")
    if stage in {"comparison_completed", "comparison_indeterminate"} and shadow_status != "completed":
        raise mode.runtime.ContractError("comparison without completed shadow")
    if stage == "comparison_indeterminate" and state.get("comparison", {}).get("status") not in {"completed", "indeterminate", "unavailable"}:
        raise mode.runtime.ContractError("indeterminate expected stage mismatch")
    reference = {"path": journal.base + "/input/shared-input-v1.json", "sha256": journal.packet_digest}
    if state.get("packetReference") != reference:
        raise mode.runtime.ContractError("invalid ephemeral packet reference")
    if state["stage"] == "initialized" and state.get("input") != shared.metadata(journal.packet):
        raise mode.runtime.ContractError("invalid initialized input identity")
    sources = state.get("artifacts", {})
    _attest_sources(journal, sources)
    records = state.get("producerRecords", {})
    if set(records) != set(sources):
        raise mode.runtime.ContractError("incomplete producer record commitments")
    for role, commitments in records.items():
        namespace, key = mode.receipt_location(state["comparisonExecutionId"], sources[role]["path"])
        paths = [f"{namespace}/{key}/producer-receipt-v1.json", f"{namespace}/{key}.commit/producer-commit-v1.json"]
        if not isinstance(commitments, list) or len(commitments) != 2:
            raise mode.runtime.ContractError("incomplete producer receipt/commit")
        for path, commitment in zip(paths, commitments):
            _outcome_bytes(journal.root, path, commitment)
    candidate_bindings = state.get("candidateBindings", {})
    if set(candidate_bindings) != set(sources):
        raise mode.runtime.ContractError("incomplete candidate binding commitments")
    for role, commitment in candidate_bindings.items():
        _, encoded = _outcome_bytes(journal.root, journal.base + f"/records/{role}-candidate-binding-v1.json",
                                    commitment)
        binding = shared.decode(encoded)
        if (canonical(binding) != encoded or binding.get("producerRuntime") != role
                or binding.get("workspaceId") != packet["workspaceId"]
                or binding.get("workspaceBindingDigest") != packet["workspaceBindingDigest"]
                or binding.get("sharedInputPacketDigest") != journal.packet_digest
                or binding.get("producerReceiptDigest") != sources[role]["producerReceiptDigest"]):
            raise mode.runtime.ContractError("candidate binding commitment changed")
    if "legacyReceipt" in state:
        receipt = journal.receipt("legacy-receipt-v1.json")
        _load_legacy_outcome(journal.root, str(journal.root.path), packet, journal.base, receipt,
                             state["legacyReceipt"], validate_projection=True)
        if state.get("legacy") != receipt["legacy"] or any(sources.get(k) != v for k, v in receipt["artifacts"].items()):
            raise mode.runtime.ContractError("legacy state/receipt mismatch")
        if state["stage"] == "legacy_committed" and (state.get("artifacts") != receipt["artifacts"]
                or state.get("usage") != receipt["usage"] or state.get("validation") != receipt["validation"]):
            raise mode.runtime.ContractError("legacy committed fields mismatch")
    elif state["stage"] not in {"initialized", "manual_recovery_required"}:
        raise mode.runtime.ContractError("missing legacy receipt binding")
    if "shadowReceipt" in state:
        receipt, _ = _shadow_receipt(journal, state["shadowReceipt"])
        if (state.get("shadow") != receipt["shadow"] or sources != receipt["artifacts"]
                or state.get("usage") != receipt["usage"] or state.get("validation") != receipt["validation"]):
            raise mode.runtime.ContractError("shadow state/receipt mismatch")
    elif state.get("shadow", {}).get("status") == "completed" or state["stage"] == "shadow_completed":
        raise mode.runtime.ContractError("missing shadow receipt binding")
    if "comparisonAttempt" in state:
        if "comparisonSeal" not in state:
            raise mode.runtime.ContractError("missing comparison seal binding")
        result, _, _ = _comparison_attempt(journal, state, state["comparisonAttempt"], state["comparisonSeal"])
        if state.get("comparison") != result:
            raise mode.runtime.ContractError("comparison state/attempt mismatch")
        path = journal.base + "/records/comparison-report-v1.json"
        if "comparisonRecord" not in state:
            raise mode.runtime.ContractError("missing comparison record binding")
        _, encoded = _outcome_bytes(journal.root, path, state["comparisonRecord"])
        if encoded != canonical(result):
            raise mode.runtime.ContractError("comparison record changed")
        expected_stage = "comparison_indeterminate" if result["diagnosticStatus"] == "indeterminate" else "comparison_completed"
        if state["stage"] not in {expected_stage, "completed"}:
            raise mode.runtime.ContractError("comparison expected stage mismatch")
    elif state.get("comparison", {}).get("status") == "completed" or state["stage"] == "comparison_completed":
        raise mode.runtime.ContractError("missing comparison attempt binding")


class RecoverablePacket:
    def __init__(self, root, path, payload, commitment):
        self.root, self.path, self.payload, self.commitment = root, path, payload, commitment

    def consume(self):
        if self.commitment is None:
            raise mode.runtime.ContractError("packet was not materialized")
        _, encoded = _outcome_bytes(self.root, self.path, self.commitment)
        if encoded != self.payload:
            raise mode.runtime.ContractError("ephemeral packet changed")
        return encoded


def _cleanup_owned_staging(root, base, packet_digest):
    relative = base + "/recovery"
    parts = relative.split("/")
    try:
        context = root.directory_fd(parts)
        directory = context.__enter__()
    except FileNotFoundError:
        return
    try:
        names = os.listdir(directory)
        prefixed = [name for name in names if name.startswith(".live-shadow.stage.")
                    or name.startswith(".live-shadow.owner.")]
        tokens = set()
        for name in prefixed:
            match = re.fullmatch(r"\.live-shadow\.(stage|owner)\.([a-f0-9]{32})", name)
            if match is None:
                raise mode.runtime.ContractError("ambiguous live-shadow staging entry")
            tokens.add(match.group(2))
        for token in sorted(tokens):
            owner_name, stage_name = ".live-shadow.owner." + token, ".live-shadow.stage." + token
            if owner_name not in names:
                raise mode.runtime.ContractError("unowned live-shadow staging artifact")
            owner_path = relative + "/" + owner_name
            _, owner_bytes = _outcome_bytes(root, owner_path)
            owner = shared.decode(owner_bytes)
            allowed_targets = {base + "/recovery/" + name for name in
                               ("stdout.bin", "stderr.bin", "legacy-outcome-v1.json")}
            if (not isinstance(owner, dict) or canonical(owner) != owner_bytes
                    or set(owner) != {"schemaVersion", "comparisonExecutionId", "base", "parent",
                                         "target", "packetDigest", "payloadDigest"}
                    or owner["schemaVersion"] != "mana.context-runtime.live-shadow-staging-owner/v1"
                    or owner["comparisonExecutionId"] != base.rsplit("/", 1)[-1]
                    or owner["base"] != base or owner["parent"] != relative
                    or owner["target"] not in allowed_targets or owner["packetDigest"] != packet_digest):
                raise mode.runtime.ContractError("foreign live-shadow staging owner")
            if stage_name in names:
                stage_path = relative + "/" + stage_name
                _, payload = _outcome_bytes(root, stage_path)
                if shared.digest(payload) != owner["payloadDigest"]:
                    raise mode.runtime.ContractError("tampered live-shadow staging payload")
                target_name = owner["target"].rsplit("/", 1)[-1]
                try:
                    _, target = _outcome_bytes(root, owner["target"])
                except FileNotFoundError:
                    target = None
                if target is not None and target != payload:
                    raise mode.runtime.ContractError("ambiguous staged/final live-shadow artifact")
                # Target present means the publication was adopted before the
                # crash; target absent means this isolated stage was aborted.
                os.unlink(stage_name, dir_fd=directory)
            else:
                try:
                    _, target = _outcome_bytes(root, owner["target"])
                except FileNotFoundError:
                    target = None
                if target is not None and shared.digest(target) != owner["payloadDigest"]:
                    raise mode.runtime.ContractError("ambiguous published live-shadow artifact")
            os.unlink(owner_name, dir_fd=directory)
        os.fsync(directory)
    finally:
        context.__exit__(None, None, None)


def _remove_private_tree(root, relative):
    parts = mode.relative_path(relative)
    with root.directory_fd(parts[:-1]) as parent:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            metadata = os.fstat(fd)
            if (metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700):
                raise mode.runtime.ContractError("backend scratch directory is not private")
            def remove_contents(directory):
                for name in os.listdir(directory):
                    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                        try:
                            if info.st_uid != os.getuid():
                                raise mode.runtime.ContractError("foreign backend scratch directory")
                            remove_contents(child)
                        finally:
                            os.close(child)
                        os.rmdir(name, dir_fd=directory)
                    elif (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                          and info.st_nlink == 1):
                        os.unlink(name, dir_fd=directory)
                    else:
                        raise mode.runtime.ContractError("ambiguous backend scratch entry")
                os.fsync(directory)
            remove_contents(fd)
            root.attest_directory(parts[:-1], parent)
        finally:
            os.close(fd)
        os.rmdir(parts[-1], dir_fd=parent)
        os.fsync(parent)


def _scratch_identity(base, packet):
    return {"schemaVersion": "mana.context-runtime.backend-scratch/v1",
            "comparisonExecutionId": packet["comparisonExecutionId"],
            "shadowExecutionId": packet["shadowExecutionId"],
            "shadowInvocationId": packet["identity"]["shadowInvocationId"],
            "workspaceId": packet["workspaceId"], "packetDigest": shared.digest(canonical(packet)),
            "path": base + "/backend-scratch/" + packet["identity"]["shadowInvocationId"]}


def _reconcile_backend_scratch(root, base, packet):
    expected = _scratch_identity(base, packet)
    registration_path = base + "/records/backend-scratch-v1.json"
    cleanup_path = base + "/records/backend-scratch-cleanup-v1.json"
    try:
        registration_bytes = _read_private(root, registration_path)
        registration = shared.decode(registration_bytes)
        if canonical(registration) != registration_bytes:
            raise mode.runtime.ContractError("noncanonical backend scratch registration")
    except FileNotFoundError:
        registration = None
    if registration is not None and registration != expected:
        raise mode.runtime.ContractError("foreign backend scratch registration")
    scratch = expected["path"]
    try:
        with root.directory_fd(scratch.split("/")) as scratch_fd:
            root.attest_directory(scratch.split("/"), scratch_fd)
        scratch_exists = True
    except FileNotFoundError:
        scratch_exists = False
    try:
        owner_bytes = _read_private(root, scratch + "/owner-v1.json")
        owner = shared.decode(owner_bytes)
        if canonical(owner) != owner_bytes:
            raise mode.runtime.ContractError("noncanonical backend scratch owner")
    except FileNotFoundError:
        owner = None
    try:
        cleaned_bytes = _read_private(root, cleanup_path)
        cleaned = shared.decode(cleaned_bytes)
        if canonical(cleaned) != cleaned_bytes:
            raise mode.runtime.ContractError("noncanonical backend scratch cleanup receipt")
    except FileNotFoundError:
        cleaned = None
    cleanup_record = {"schemaVersion": "mana.context-runtime.backend-scratch-cleanup/v1",
                      "scratch": expected, "status": "removed"}
    if cleaned is not None and cleaned != cleanup_record:
        raise mode.runtime.ContractError("foreign backend scratch cleanup receipt")
    if owner is None:
        if scratch_exists:
            raise mode.runtime.ContractError("backend scratch has no verifiable owner")
        if registration is not None and cleaned is None:
            _immutable(root, cleanup_path, canonical(cleanup_record))
        return
    if owner != expected:
        raise mode.runtime.ContractError("foreign backend scratch owner")
    if cleaned is None and registration is not None:
        _immutable(root, cleanup_path, canonical(cleanup_record))
    _remove_private_tree(root, scratch)


def _prepare_backend_scratch(root, base, packet):
    expected = _scratch_identity(base, packet)
    with private_directory(root, expected["path"].split("/")):
        pass
    _immutable(root, expected["path"] + "/owner-v1.json", canonical(expected))
    fault("backend-scratch-created-pre-registration")
    _immutable(root, base + "/records/backend-scratch-v1.json", canonical(expected))
    return expected["path"]


def _cleanup_packet(root, base, packet_digest):
    # Exact host-owned names only, under the held comparison lock. Also retire
    # the abandoned CAS temporary, which never carries state authority.
    parts = base.split("/")
    _cleanup_owned_staging(root, base, packet_digest)
    with private_directory(root, parts) as directory:
        for name in os.listdir(directory):
            if re.fullmatch(r"\.live-shadow-head\.stage\.[a-f0-9]{24}", name):
                os.unlink(name, dir_fd=directory)
        try:
            with private_directory(root, parts + ["input"]) as inputs:
                root.attest_directory(parts + ["input"], inputs)
                for name in os.listdir(inputs):
                    if name == "shared-input-v1.json" or re.fullmatch(r"\.live-shadow\.stage\.[a-f0-9]{32}", name):
                        os.unlink(name, dir_fd=inputs)
                os.fsync(inputs)
            os.rmdir("input", dir_fd=directory)
        except FileNotFoundError:
            pass
        os.fsync(directory)


@contextmanager
def session(root, base, payload):
    with producer_lock(root, base + "/live-shadow.lock"):
        # The locator is committed before materialization. A killed host leaves
        # only a referenced packet; the next lock holder removes it first.
        packet_digest = shared.digest(payload)
        try:
            _cleanup_packet(root, base, packet_digest)
            _reconcile_backend_scratch(root, base, shared.validate(payload))
        except Exception as error:
            raise ManualRecoveryRequired("manualRecoveryRequired: ambiguous private recovery residue") from error
        try:
            journal = Journal(root, base, payload)
        except Exception as error:
            raise ManualRecoveryRequired("manualRecoveryRequired: invalid legacy journal") from error
        if journal.current is None:
            journal.commit("initialized", input=shared.metadata(payload),
                           packetReference={"path": base + "/input/shared-input-v1.json", "sha256": shared.digest(payload)})
        path = base + "/input/shared-input-v1.json"
        try:
            commitment = None
            if journal.current["stage"] not in TERMINAL:
                private_write(root, path, payload)
                commitment = _outcome_bytes(root, path)[0]
                fault("after-packet-publication")
            yield journal, RecoverablePacket(root, path, payload, commitment)
        finally:
            _cleanup_packet(root, base, packet_digest)
            _reconcile_backend_scratch(root, base, shared.validate(payload))


def _source(root, project_root, execution, profile, target_key, role, relative):
    return mode.producer_source(root, execution, relative, role, profile_id=profile,
                                target_key=target_key,
                                **({"execution_version": 1} if role == "v2" else {}))


def _shadow_candidate_context(root, packet, structured, *, framework_root=None):
    """Derive the binding from the current committed CTX-06 chain, not stdout."""
    project = root.path / packet["identity"]["shadowRunRoot"]
    framework = framework_root or _TEST_FRAMEWORK_ROOT or HERE.parent
    inputs = shared.decode(shared.unblob(packet["input"]))
    actual = consumer.project_completed(project, framework, packet, inputs)
    if canonical(actual) != structured:
        raise mode.runtime.ContractError("shadow candidate differs from current committed chain")
    args = consumer.run_args(project, framework, packet["identity"]["shadowProducerId"], inputs)
    context = consumer.pipeline._load_run_context(args)
    commitments = []
    for artifact in actual["provenance"]["artifacts"]:
        ref = artifact["ref"]
        local = ref if ref.startswith(".mana/") else context.run_relative + "/" + ref
        relative = packet["identity"]["shadowRunRoot"] + "/" + local
        commitment, data = _outcome_bytes(root, relative)
        if commitment["sha256"] != artifact["sha256"] or shared.digest(data) != artifact["sha256"]:
            raise mode.runtime.ContractError("shadow chain artifact commitment changed")
        commitments.append(commitment)
    return {"workspaceId": context.envelope["workspaceId"],
            "committedChainDigest": shared.digest(canonical(commitments))}


def _candidate_binding(root, packet, role, structured, shadow_context=None):
    identity = packet["identity"]
    base = f"{SHADOW_NAMESPACE}/{identity['comparisonExecutionId']}"
    binding = {"comparisonExecutionId": identity["comparisonExecutionId"], "producerRuntime": role,
               "executionId": identity["legacyProducerId" if role == "legacy" else "shadowProducerId"],
               "executionVersion": packet["executionVersion"], "workspaceId": packet["workspaceId"],
               "workspaceBindingDigest": packet["workspaceBindingDigest"],
               "profileId": packet["profileId"], "targetKey": packet["targetKey"],
               "sharedInputPacketDigest": shared.digest(canonical(packet)),
               "evidenceSnapshotDigest": packet["evidenceSnapshotDigest"],
               "modeDecisionDigest": packet["modeDecisionDigest"],
               "budgetDecisionDigest": packet["budgetDecisionDigest"],
               "semanticProjectionDigest": shared.digest(structured),
               "exactLegacyOutcomeDigest": None, "committedChainDigest": None}
    if role == "legacy":
        outcome, encoded = _outcome_bytes(root, base + "/recovery/legacy-outcome-v1.json")
        manifest = shared.decode(encoded)
        if manifest["producerInvocationIdentity"] != {key: identity[key] for key in
                ("comparisonExecutionId", "legacyProducerId", "legacyInvocationId")}:
            raise mode.runtime.ContractError("foreign current exact legacy outcome")
        for name in ("stdout", "stderr"):
            _, stream = _outcome_bytes(root, base + "/recovery/" + name + ".bin", manifest[name])
            if name == "stdout":
                _, actual = validate_artifact(stream, packet, "legacy")
                if actual != structured or manifest["exitStatus"] != 0:
                    raise mode.runtime.ContractError("legacy candidate differs from exact current outcome")
        binding["exactLegacyOutcomeDigest"] = outcome["sha256"]
    else:
        context = shadow_context or _shadow_candidate_context(root, packet, structured)
        if context.get("workspaceId") != packet["workspaceId"]:
            raise mode.runtime.ContractError("shadow candidate workspace differs from shared packet")
        binding["committedChainDigest"] = context["committedChainDigest"]
    return binding


def _publish_validated_artifact(root, project_root, packet, role, status, output, *, shadow_context=None):
    """Publish only a validated semantic projection and its committed receipt."""
    validation, structured = validate_artifact(output, packet, role)
    if status != 0:
        return {**validation, "status": "invalid", "errorCategory": "process-failed"}, None
    if structured is None:
        return validation, None
    identity, execution, profile = packet["identity"], packet["identity"]["comparisonExecutionId"], packet["profileId"]
    target_key = shared.digest(shared.canonical(packet["target"]))
    base = f"{SHADOW_NAMESPACE}/{execution}"
    relative = base + f"/{role}-artifact-v1.json"
    binding_path = base + f"/records/{role}-candidate-binding-v1.json"
    try:
        candidate = _candidate_binding(root, packet, role, structured, shadow_context)
    except (mode.runtime.ContractError, shared.Error, OSError, ValueError, KeyError):
        return _invalid_artifact("candidate-binding-invalid", structured), None
    authority_event(role + ".projection.validated")
    try:
        source = _source(root, project_root, execution, profile, target_key, role, relative)
    except FileNotFoundError:
        source = None
    except mode.runtime.ContractError:
        return _invalid_artifact("candidate-conflict", structured), None
    if source is not None:
        try:
            previous = shared.decode(_read_private(root, binding_path))
            expected = {**candidate, "producerReceiptDigest": source["producerReceiptDigest"]}
            if (previous != expected or source["sha256"] != candidate["semanticProjectionDigest"]):
                raise mode.runtime.ContractError("existing artifact differs from current candidate")
        except (FileNotFoundError, mode.runtime.ContractError, shared.Error):
            return _invalid_artifact("candidate-conflict", structured), None
        return validation, source
    try:
        if role == "legacy":
            mode.publish_legacy_artifact(project_root, execution, profile, target_key, relative, structured)
        else:
            mode.publish_v2_artifact(project_root, execution, profile, target_key, relative, structured, execution_version=1)
        source = _source(root, project_root, execution, profile, target_key, role, relative)
        _immutable(root, binding_path, canonical({**candidate, "producerReceiptDigest": source["producerReceiptDigest"]}))
        authority_event(role + ".producer.published")
        return validation, source
    except (mode.runtime.ContractError, OSError):
        # A failed publication has no producer receipt authority.  Keep the
        # process outcome, but never relabel this candidate as completed.
        return {"status": "invalid", "errorCategory": "publication-failed",
                "byteCount": validation["byteCount"]}, None


def _recover_completed_shadow(journal, project_root, packet):
    """Reproject one completed CTX-06 chain; never invoke the provider."""
    root, state = journal.root, journal.current
    inputs = shared.decode(shared.unblob(packet["input"]))
    shadow_project = root.path / packet["identity"]["shadowRunRoot"]
    framework = _TEST_FRAMEWORK_ROOT or HERE.parent
    projection = consumer.project_completed(shadow_project, framework, packet, inputs)
    structured = canonical(projection)
    context = _shadow_candidate_context(root, packet, structured, framework_root=framework)
    validation, artifact = _publish_validated_artifact(
        root, project_root, packet, "v2", 0, structured, shadow_context=context)
    if artifact is None:
        raise mode.runtime.ContractError("completed shadow chain cannot be admitted")
    fault("shadow-projection-published-pre-receipt")
    identity = packet["identity"]
    usage_path = identity["shadowRunRoot"] + f"/.mana/runtime/metrics/{identity['shadowProducerId']}/usage-summary-v1.json"
    v2_usage = read_usage(root, usage_path, identity["shadowProducerId"], packet["profileId"],
                          identity["shadowInvocationId"])
    artifacts = {**state.get("artifacts", {}), "v2": artifact}
    receipt = {"schemaVersion": "mana.context-runtime.live-shadow-shadow-receipt/v1",
               "shadow": {"status": "completed", "exitStatus": 0, "reason": None},
               "artifacts": artifacts, "usage": usage_comparison(state["usage"], v2_usage),
               "validation": {**state.get("validation", {}), "shadow": validation}}
    _immutable(root, journal.base + "/records/shadow-receipt-v1.json", canonical(receipt))
    fault("shadow-receipt-published-pre-live-shadow-head")
    verified, binding = _shadow_receipt(journal)
    return verified, binding


def _result(packet, state, legacy_output):
    legacy = state.get("legacy", {})
    shadow = state.get("shadow", {})
    usage = state.get("usage", usage_comparison(
        _missing_usage(packet["identity"]["legacyInvocationId"]),
        _missing_usage(packet["identity"]["shadowInvocationId"])))
    validation = state.get("validation", {})
    return {"schemaVersion": "mana.context-runtime.live-shadow-result/v1",
            "executionId": packet["identity"]["comparisonExecutionId"], "authority": "legacy",
            "permissionGrant": "none", "externalActions": "disabled", "input": shared.metadata(canonical(packet)),
            "environmentProvenance": backend.environment_provenance(),
            "legacy": {"status": "completed" if legacy.get("exitStatus") == 0 else "failed", "exitStatus": legacy.get("exitStatus")},
            "v2": {"status": shadow.get("status", "unavailable"), "exitStatus": shadow.get("exitStatus")},
            "shadowStatus": shadow.get("status", "unavailable"), "shadowUnavailableReason": shadow.get("reason"),
            "usage": usage, "artifacts": state.get("artifacts", {}),
            "validation": validation,
            "comparison": state.get("comparison", {"status": "unavailable", "reason": "missing-valid-artifact"}),
            "lifecycle": lifecycle(state), "transactionStage": state["stage"]}


def _outcome_bytes(root, relative, expected=None):
    """Sensitive streams have no comparison byte cap and are never parsed."""
    if expected is not None and (not isinstance(expected, dict)
            or set(expected) != {"path", "sha256", "fileInstance"}
            or expected["path"] != relative or not isinstance(expected["fileInstance"], dict)):
        raise mode.runtime.ContractError("invalid sensitive outcome commitment")
    parts = mode.relative_path(relative)
    with private_directory(root, parts[:-1]) as parent:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600
                    or (expected is not None and mode.file_instance(before) != expected["fileInstance"])):
                raise mode.runtime.ContractError("invalid sensitive outcome file instance")
            chunks, digest = [], hashlib.sha256()
            while True:
                chunk = os.read(fd, 64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                digest.update(chunk)
            after = os.fstat(fd)
            named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            payload = b"".join(chunks)
            commitment = {"path": relative, "sha256": digest.hexdigest(),
                          "fileInstance": mode.file_instance(after)}
            if (mode.file_instance(before) != mode.file_instance(after)
                    or mode.file_instance(named) != mode.file_instance(after) or named.st_nlink != 1
                    or len(payload) != before.st_size or (expected is not None and commitment != expected)):
                raise mode.runtime.ContractError("sensitive outcome commitment changed")
            root.attest_directory(parts[:-1], parent)
            return commitment, payload
        finally:
            os.close(fd)


def _publish_outcome(root, base, identity, done, packet_digest="unbound-test-only"):
    # Sensitive local recovery/delivery artifact, NOT privacy-safe. Only the
    # recovery host reads these files; no stream/digest is exported to shadow.
    streams = {}
    for name, payload in (("stdout", done.stdout), ("stderr", done.stderr)):
        relative = base + "/recovery/" + name + ".bin"
        _owned_private_write(root, base, relative, payload, packet_digest,
                             "exact-outcome-stage-pre-link" if name == "stdout" else None)
        streams[name], captured = _outcome_bytes(root, relative)
        if captured != payload:
            raise mode.runtime.ContractError("outcome publication changed")
    outcome = {**streams, "exitStatus": done.returncode,
               "terminationKind": getattr(done, "termination_kind", "exited"),
               "producerInvocationIdentity": {key: identity[key] for key in
                   ("comparisonExecutionId", "legacyProducerId", "legacyInvocationId")}}
    relative = base + "/recovery/legacy-outcome-v1.json"
    _owned_private_write(root, base, relative, canonical(outcome), packet_digest)
    return _outcome_bytes(root, relative)[0]


def _load_legacy_outcome(root, project_root, packet, base, receipt, receipt_binding=None, *, validate_projection=False):
    if not isinstance(receipt, dict):
        raise mode.runtime.ContractError("missing legacy producer receipt")
    if (set(receipt) != {"schemaVersion", "outcome", "legacy", "artifacts", "usage", "validation"}
            or receipt["schemaVersion"] != "mana.context-runtime.live-shadow-legacy-receipt/v1"
            or not isinstance(receipt["outcome"], dict) or set(receipt["legacy"]) != {"exitStatus"}):
        raise mode.runtime.ContractError("invalid legacy producer receipt shape")
    receipt_path = base + "/records/legacy-receipt-v1.json"
    binding, encoded = _outcome_bytes(root, receipt_path, receipt_binding)
    if shared.decode(encoded) != receipt or canonical(receipt) != encoded:
        raise mode.runtime.ContractError("invalid legacy producer receipt")
    _, encoded = _outcome_bytes(root, base + "/recovery/legacy-outcome-v1.json", receipt["outcome"])
    outcome = shared.decode(encoded)
    identity = packet["identity"]
    if (set(outcome) != {"stdout", "stderr", "exitStatus", "terminationKind", "producerInvocationIdentity"}
            or canonical(outcome) != encoded
            or outcome["producerInvocationIdentity"] != {key: identity[key] for key in
                ("comparisonExecutionId", "legacyProducerId", "legacyInvocationId")}
            or type(outcome["exitStatus"]) is not int or not 0 <= outcome["exitStatus"] <= 255
            or outcome["exitStatus"] != receipt["legacy"]["exitStatus"]
            or outcome["terminationKind"] not in {"exited", "signaled", "timed_out", "interrupted"}):
        raise mode.runtime.ContractError("invalid legacy outcome identity/status")
    streams = {}
    for name in ("stdout", "stderr"):
        expected = outcome[name]
        if not isinstance(expected, dict) or expected.get("path") != base + "/recovery/" + name + ".bin":
            raise mode.runtime.ContractError("foreign legacy outcome stream")
        _, streams[name] = _outcome_bytes(root, expected["path"], expected)
    if validate_projection and receipt.get("validation", {}).get("legacy", {}).get("status") == "valid":
        source = receipt["artifacts"]["legacy"]
        if _source(root, project_root, identity["comparisonExecutionId"], packet["profileId"],
                   shared.digest(canonical(packet["target"])), "legacy", source["path"]) != source:
            raise mode.runtime.ContractError("legacy comparison projection changed")
    return outcome["exitStatus"], streams["stdout"], streams["stderr"], binding


def _recover_published_legacy(journal, project_root, packet):
    """Seal a fully published exact outcome after a pre-receipt host crash."""
    root, base = journal.root, journal.base
    outcome_binding, encoded = _outcome_bytes(root, base + "/recovery/legacy-outcome-v1.json")
    outcome = shared.decode(encoded)
    identity = packet["identity"]
    if (canonical(outcome) != encoded
            or set(outcome) != {"stdout", "stderr", "exitStatus", "terminationKind", "producerInvocationIdentity"}
            or outcome["producerInvocationIdentity"] != {key: identity[key] for key in
                ("comparisonExecutionId", "legacyProducerId", "legacyInvocationId")}
            or type(outcome["exitStatus"]) is not int or not 0 <= outcome["exitStatus"] <= 255
            or outcome["terminationKind"] not in {"exited", "signaled", "timed_out", "interrupted"}):
        raise mode.runtime.ContractError("published legacy outcome is not adoptable")
    streams = {}
    for name in ("stdout", "stderr"):
        expected = outcome[name]
        if expected.get("path") != base + "/recovery/" + name + ".bin":
            raise mode.runtime.ContractError("published legacy stream is foreign")
        _, streams[name] = _outcome_bytes(root, expected["path"], expected)
    try:
        usage = capture_usage(root, None, identity["legacyProducerId"], packet["profileId"],
                              identity["legacyInvocationId"])
    except (mode.runtime.ContractError, OSError):
        usage = read_usage(root, None, identity["legacyProducerId"], packet["profileId"],
                           identity["legacyInvocationId"])
    validation, artifact = _publish_validated_artifact(
        root, project_root, packet, "legacy", outcome["exitStatus"], streams["stdout"])
    artifacts = {"legacy": artifact} if artifact is not None else {}
    receipt = {"schemaVersion": "mana.context-runtime.live-shadow-legacy-receipt/v1",
               "outcome": outcome_binding, "legacy": {"exitStatus": outcome["exitStatus"]},
               "artifacts": artifacts, "usage": usage, "validation": {"legacy": validation}}
    _immutable(root, base + "/records/legacy-receipt-v1.json", canonical(receipt))
    return receipt


def lifecycle(state):
    """Host-generated observations; journals/receipts remain the authority."""
    legacy = state.get("legacy", {})
    shadow = state.get("shadow", {})
    comparison_value = state.get("comparison", {})
    events = [{"event": "legacy.started"}]
    events.append({"event": "legacy.completed" if legacy.get("exitStatus") == 0 else "legacy.failed"})
    if shadow:
        events.append({"event": "shadow.started"})
        status = shadow.get("status")
        if status == "completed": events.append({"event": "shadow.completed"})
        elif status == "unavailable": events.append({"event": "shadow.unavailable"})
        elif status == "timed_out" or shadow.get("reason") == "timeout": events.append({"event": "shadow.timed_out"})
        elif status == "interrupted" or shadow.get("reason") == "interrupted": events.append({"event": "shadow.interrupted"})
        else: events.append({"event": "shadow.failed"})
    if comparison_value:
        events.append({"event": "comparison.completed" if comparison_value.get("status") == "completed"
                       else "comparison.indeterminate" if comparison_value.get("status") == "indeterminate"
                       else "comparison.failed"})
    events.append({"event": "session.manual_recovery_required" if state.get("stage") == "manual_recovery_required"
                   else "session.completed" if state.get("stage") == "completed" else "session.active"})
    return events


def _commit_legacy(journal, delivery, exact, binding, receipt):
    """Arm delivery even if the host raises just after publishing HEAD."""
    try:
        journal.commit("legacy_committed", legacy=receipt["legacy"], legacyReceipt=binding,
                       artifacts=receipt.get("artifacts", {}), usage=receipt["usage"],
                       validation=receipt.get("validation", {}))
    except BaseException:
        # A failed CAS before replacement is not a commit. If replacement
        # completed, its matching state/bundle/receipt is already authority.
        state = journal.current
        if state is None or state.get("stage") != "legacy_committed" or state.get("legacyReceipt") != binding:
            state = journal._load()
        if (state is not None and state.get("stage") == "legacy_committed"
                and state.get("legacyReceipt") == binding and state.get("legacy") == receipt["legacy"]):
            journal.current = state
            delivery.update(exact=exact, result={"authority": "legacy", "transactionStage": "legacy_committed"})
        raise
    delivery.update(exact=exact, result={"authority": "legacy", "transactionStage": "legacy_committed"})
    authority_event("legacy.head.committed")


def run_shared(project_root, payload):
    # The outer barrier also covers context-manager exits (capsule/lock/root
    # cleanup). A cached result is armed only after the authoritative HEAD.
    delivery = {}
    try:
        return _run_shared(project_root, payload, delivery)
    except BaseException:
        if not delivery:
            raise
        status, output, diagnostics = delivery["exact"]
        result = delivery["result"]
        result["handOff"] = "interrupted"
        return status, result, output, diagnostics


def _run_shared(project_root, payload, delivery):
    # This is the host trust transition. It re-derives CTX-05/06's workspace
    # identity from the currently named workspace manifest before any producer
    # intent or process invocation is possible.
    packet = shared.validate_host(payload, project_root)
    identity, execution, profile = packet["identity"], packet["identity"]["comparisonExecutionId"], packet["profileId"]
    inputs, base = shared.decode(shared.unblob(packet["input"])), f"{SHADOW_NAMESPACE}/{execution}"
    # Both legacy and shadow receive a reconstructed allowlist.  Do not pass
    # os.environ onward: the legacy provider is authoritative for output, not
    # for caller shell authority or secret inheritance.
    environment = backend.host_environment(os.environ)
    with mode.HostRoot(project_root) as root, session(root, base, payload) as (journal, captured):
        # Recover only from a complete immutable receipt. An intent without a
        # receipt is an ambiguous external legacy/shadow effect and fails closed.
        try:
            legacy_receipt = journal.receipt("legacy-receipt-v1.json")
            if legacy_receipt:
                legacy_status, legacy_output, legacy_stderr, binding = _load_legacy_outcome(
                    root, project_root, packet, base, legacy_receipt, journal.current.get("legacyReceipt"),
                    validate_projection=True)
                if journal.current["stage"] == "initialized":
                    _commit_legacy(journal, delivery, (legacy_status, legacy_output, legacy_stderr), binding, legacy_receipt)
                elif journal.current.get("legacyReceipt") != binding or journal.current.get("legacy") != legacy_receipt["legacy"]:
                    raise mode.runtime.ContractError("missing legacy commit binding")
                delivery["exact"] = (legacy_status, legacy_output, legacy_stderr)
                delivery["result"] = {"authority": "legacy", "transactionStage": journal.current["stage"]}
            elif journal.current["stage"] != "initialized":
                if journal.current["stage"] == "manual_recovery_required" and "legacy" not in journal.current:
                    return 2, _result(packet, journal.current, b""), b"", b""
                raise mode.runtime.ContractError("missing committed legacy receipt")
            elif journal.receipt("legacy-intent-v1.json"):
                try:
                    legacy_receipt = _recover_published_legacy(journal, project_root, packet)
                    legacy_status, legacy_output, legacy_stderr, binding = _load_legacy_outcome(
                        root, project_root, packet, base, legacy_receipt, validate_projection=True)
                    _commit_legacy(journal, delivery, (legacy_status, legacy_output, legacy_stderr),
                                   binding, legacy_receipt)
                    delivery["exact"] = (legacy_status, legacy_output, legacy_stderr)
                    delivery["result"] = {"authority": "legacy", "transactionStage": journal.current["stage"]}
                except FileNotFoundError:
                    journal.commit("manual_recovery_required", reason="ambiguous-legacy-effect")
                    return 2, _result(packet, journal.current, b""), b"", b""
        except Exception as error:
            raise ManualRecoveryRequired("manualRecoveryRequired: unattested legacy outcome") from error
        if legacy_receipt is None:
            fault("after-input-materialization")
            _immutable(root, base + "/records/legacy-intent-v1.json", canonical({"packetDigest": shared.digest(payload), "kind": "legacy"}))
            argv = [sys.executable, str(HERE / "lib/context-shadow-consumer.py"), "legacy", "--project-root", str(root.path)]
            completed = backend.execute_supervised(argv, input_bytes=captured.consume(), environment=environment,
                                                   cwd=root.path, timeout_name="MANA_CTX09C_LEGACY_TIMEOUT_SECONDS")
            authority_event("legacy.process.exited")
            authority_event("legacy.streams.captured")
            fault("after-legacy-process-exit")
            outcome = _publish_outcome(root, base, identity, completed, journal.packet_digest)
            authority_event("legacy.outcome.attested")
            fault("exact-outcome-published-pre-head")
            try:
                legacy_usage = capture_usage(root, None, identity["legacyProducerId"], profile,
                                             identity["legacyInvocationId"])
            except (mode.runtime.ContractError, OSError):
                legacy_usage = read_usage(root, None, identity["legacyProducerId"], profile,
                                          identity["legacyInvocationId"])
            artifacts = {}
            validation, artifact = _publish_validated_artifact(root, project_root, packet, "legacy",
                                                                 completed.returncode, completed.stdout)
            if artifact is not None:
                artifacts["legacy"] = artifact
            # This private producer receipt binds the sensitive outcome. It is
            # host-only, never a public receipt or a CTX-09B input.
            receipt = {"schemaVersion": "mana.context-runtime.live-shadow-legacy-receipt/v1",
                       "outcome": outcome, "legacy": {"exitStatus": completed.returncode},
                       "artifacts": artifacts, "usage": legacy_usage,
                       "validation": {"legacy": validation}}
            fault("before-legacy-receipt-commit")
            _immutable(root, base + "/records/legacy-receipt-v1.json", canonical(receipt))
            authority_event("legacy.receipt.published")
            fault("after-legacy-receipt-commit")
            fault("after-legacy-artifact-pre-head")
            legacy_status, legacy_output, legacy_stderr, binding = _load_legacy_outcome(
                root, project_root, packet, base, receipt, validate_projection=True)
            _commit_legacy(journal, delivery, (legacy_status, legacy_output, legacy_stderr), binding, receipt)
            legacy_receipt = receipt
        # From this point every exception is advisory: the immutable receipt is
        # re-read and returned unchanged, never replaced by shadow metadata.
        interrupted = False
        try:
            fault("after-legacy-commit")
            fault("after-legacy-head")
            shadow_receipt = journal.receipt("shadow-receipt-v1.json")
            if journal.current["stage"] == "legacy_committed" and shadow_receipt:
                shadow_receipt, shadow_binding = _shadow_receipt(journal)
                journal.commit("shadow_completed" if shadow_receipt["shadow"].get("status") == "completed" else "shadow_failed",
                               legacy=journal.current["legacy"], artifacts=shadow_receipt["artifacts"], usage=shadow_receipt["usage"],
                               shadow=shadow_receipt["shadow"], shadowReceipt=shadow_binding,
                               validation=shadow_receipt["validation"])
            elif (journal.current["stage"] == "legacy_committed" and journal.receipt("shadow-intent-v1.json")):
                # A completed CTX-06 chain is the shadow outcome authority.
                # Reproject it after process exit; only incomplete or
                # unauthenticatable state remains ambiguous.
                try:
                    recovered, shadow_binding = _recover_completed_shadow(journal, project_root, packet)
                    journal.commit("shadow_completed", legacy=journal.current["legacy"],
                                   artifacts=recovered["artifacts"], usage=recovered["usage"],
                                   shadow=recovered["shadow"], shadowReceipt=shadow_binding,
                                   validation=recovered["validation"])
                except (mode.runtime.ContractError, consumer.pipeline.runtime.ContractError,
                        shared.Error, OSError, ValueError, KeyError):
                    journal.commit("manual_recovery_required", legacy=journal.current["legacy"],
                                   artifacts=journal.current.get("artifacts", {}), usage=journal.current["usage"],
                                   validation=journal.current.get("validation", {}), reason="ambiguous-shadow-effect")
            state = journal.current
            if legacy_status != 0:
                if state["stage"] == "legacy_committed":
                    journal.commit("completed", legacy=state["legacy"], artifacts=state.get("artifacts", {}), usage=state["usage"],
                                   shadow={"status": "unavailable", "reason": "legacy-failed-policy"},
                                   comparison={"status": "unavailable", "reason": "legacy-failed-policy"},
                                   validation=state.get("validation", {}))
            elif state["stage"] == "legacy_committed":
                fault("before-shadow")
                shadow = {"status": "unavailable", "exitStatus": None, "reason": "pipeline-capability-gap"}
                v2_usage = read_usage(root, None, identity["shadowProducerId"], profile,
                                      identity["shadowInvocationId"])
                if inputs.get("pipelineSnapshot") is not None:
                    consumer.declaration_from_snapshot(profile, inputs["pipelineSnapshot"])
                    consumer.capabilities(packet["policyDecision"]["provider"])
                    for relative in (identity["shadowRunRoot"], identity["shadowMetricsRoot"]):
                        with private_directory(root, relative.split("/")): pass
                    scratch_relative = _prepare_backend_scratch(root, base, packet)
                    with producer_lock(root, identity["shadowLock"]), backend.admit(
                            root.path / identity["shadowRunRoot"], root.path / identity["shadowMetricsRoot"],
                            scratch_path=root.path / scratch_relative) as admission:
                        shadow["reason"] = admission.reason
                        if admission.status == "available":
                            if journal._load()["stage"] != "legacy_committed":
                                raise mode.runtime.ContractError("shadow requires the legacy HEAD barrier")
                            _immutable(root, base + "/records/shadow-intent-v1.json", canonical(
                                {"packetDigest": shared.digest(payload), "kind": "shadow"}))
                            authority_event("shadow.invocation.started")
                            shadow_project = root.path / identity["shadowRunRoot"]
                            done = admission.invoke([sys.executable, str(HERE / "lib/context-shadow-consumer.py"), "v2", "--project-root", str(shadow_project)],
                                                    input_bytes=captured.consume(), environment=environment, cwd=shadow_project)
                            fault("after-shadow-process-exit")
                            shadow = {"status": backend.shadow_status(done), "exitStatus": done.returncode,
                                      "reason": "timeout" if getattr(done, "timed_out", False) else
                                      "interrupted" if getattr(done, "interrupted_signal", None) else None}
                            usage_path = identity["shadowRunRoot"] + f"/.mana/runtime/metrics/{identity['shadowProducerId']}/usage-summary-v1.json"
                            v2_usage = read_usage(root, usage_path, identity["shadowProducerId"], profile,
                                                  identity["shadowInvocationId"])
                            if done.returncode == 0:
                                fault("before-shadow-artifact-commit")
                                validation, artifact = _publish_validated_artifact(root, project_root, packet, "v2",
                                                                                     done.returncode, done.stdout)
                                fault("after-shadow-artifact-commit")
                                fault("shadow-projection-published-pre-receipt")
                                artifacts = {**state.get("artifacts", {})}
                                if artifact is not None:
                                    artifacts["v2"] = artifact
                                usage = usage_comparison(state["usage"], v2_usage)
                                if artifact is None:
                                    shadow = {"status": "failed", "exitStatus": done.returncode,
                                              "reason": validation["errorCategory"]}
                                receipt = {"schemaVersion": "mana.context-runtime.live-shadow-shadow-receipt/v1", "shadow": shadow,
                                           "artifacts": artifacts, "usage": usage,
                                           "validation": {**state.get("validation", {}), "shadow": validation}}
                                _immutable(root, base + "/records/shadow-receipt-v1.json", canonical(receipt))
                                fault("after-shadow-receipt-commit")
                                fault("shadow-receipt-published-pre-live-shadow-head")
                                fault("after-shadow-artifact-pre-head")
                                _, shadow_binding = _shadow_receipt(journal)
                                journal.commit("shadow_completed" if artifact is not None else "shadow_failed",
                                               legacy=state["legacy"], artifacts=artifacts, usage=usage, shadow=shadow,
                                               shadowReceipt=shadow_binding,
                                               validation={**state.get("validation", {}), "shadow": validation})
                                fault("after-shadow-head")
                            else:
                                journal.commit("shadow_failed", legacy=state["legacy"], artifacts=state.get("artifacts", {}),
                                               usage=usage_comparison(state["usage"], v2_usage), shadow=shadow,
                                               validation={**state.get("validation", {}), "shadow":
                                                           _invalid_artifact("process-failed", done.stdout)})
                        else:
                            journal.commit("shadow_unavailable", legacy=state["legacy"], artifacts=state.get("artifacts", {}),
                                           usage=usage_comparison(state["usage"], v2_usage), shadow=shadow,
                                           validation={**state.get("validation", {}), "shadow":
                                                       _invalid_artifact("backend-unavailable", b"")})
                    fault("backend-scratch-registered-pre-cleanup")
                    _reconcile_backend_scratch(root, base, packet)
                else:
                    journal.commit("shadow_unavailable", legacy=state["legacy"], artifacts=state.get("artifacts", {}),
                                   usage=usage_comparison(state["usage"], v2_usage), shadow=shadow,
                                   validation={**state.get("validation", {}), "shadow":
                                               _invalid_artifact("pipeline-unavailable", b"")})
            if journal.current["stage"] == "shadow_completed":
                fault("before-comparison")
                artifacts = journal.current["artifacts"]
                validations = journal.current.get("validation", {})
                eligible = (set(artifacts) == {"legacy", "v2"}
                            and validations.get("legacy", {}).get("status") == "valid"
                            and validations.get("shadow", {}).get("status") == "valid")
                if not eligible:
                    comparison_result, stage = ({"status": "unavailable", "reason": "missing-or-invalid-validated-artifact"},
                                                "comparison_indeterminate")
                else:
                    plan = {"schemaVersion": "mana.context-runtime.mode-plan/v1", "executionId": execution, "mode": "compare", "authority": "none",
                            "externalActions": "disabled", "permissionGrant": "none", "comparison": "deferred-ctx-09b", "artifacts": artifacts}
                    try:
                        with root.directory_fd(mode.NAMESPACE.split("/"), create=True) as parent:
                            try:
                                existing = _read_private(root, f"{mode.NAMESPACE}/{execution}/mode-plan-v1.json")
                            except FileNotFoundError:
                                mode.absent(parent, execution); mode.publish(root, parent, execution, plan)
                            else:
                                if existing != canonical(plan): raise mode.runtime.ContractError("conflicting comparison registration")
                        try:
                            comparison_result, attempt_binding, seal_binding = _comparison_attempt(journal, journal.current)
                        except FileNotFoundError:
                            # A recorded intent reserves the sole invocation.
                            # A crash inside the comparator without a complete
                            # attempt cannot be retried under this identity.
                            if journal.receipt("comparison-intent-v1.json") is not None:
                                raise mode.runtime.ContractError("ambiguous comparison invocation")
                            _immutable(root, base + "/records/comparison-intent-v1.json", canonical(_attempt_identity(journal, journal.current)))
                            report = json.loads(comparison.run(project_root, execution, False))
                            comparison_result = {"status": "completed", "diagnosticStatus": report["status"], "complete": report["complete"]}
                            attempt = {**_attempt_identity(journal, journal.current), "report": report, "result": comparison_result}
                            _immutable(root, base + "/records/comparison-attempt-v1.json", canonical(attempt))
                            attempt_binding = _outcome_bytes(root, base + "/records/comparison-attempt-v1.json")[0]
                            seal = {"schemaVersion": "mana.context-runtime.comparison-attempt-commit/v1",
                                    "attempt": attempt_binding, "inputReceiptDigest": shared.digest(payload),
                                    "producerReceiptDigests": attempt["producerReceiptDigests"],
                                    "pairIdentityDigest": shared.digest(canonical(artifacts)),
                                    "reportDigest": shared.digest(canonical(report)),
                                    "resultDigest": shared.digest(canonical(comparison_result))}
                            _immutable(root, base + "/records/comparison-attempt-commit-v1.json", canonical(seal))
                            comparison_result, attempt_binding, seal_binding = _comparison_attempt(journal, journal.current)
                        fault("after-comparison-pre-head")
                        fault("after-comparison-artifact-pre-head")
                        _immutable(root, base + "/records/comparison-report-v1.json", canonical(comparison_result))
                        stage = "comparison_completed" if comparison_result["diagnosticStatus"] != "indeterminate" else "comparison_indeterminate"
                    except (mode.runtime.ContractError, comparison.mode.runtime.ContractError, OSError, ValueError, TypeError):
                        comparison_result, stage = {"status": "indeterminate", "reason": "offline-comparison-rejected"}, "comparison_indeterminate"
                journal.commit(stage, legacy=journal.current["legacy"], artifacts=artifacts, usage=journal.current["usage"],
                               shadow=journal.current["shadow"], comparison=comparison_result,
                               **({"comparisonAttempt": attempt_binding,
                                   "comparisonSeal": seal_binding,
                                   "comparisonRecord": _outcome_bytes(root, base + "/records/comparison-report-v1.json")[0]}
                                  if comparison_result["status"] == "completed" else {}),
                               validation=journal.current.get("validation", {}))
                fault("after-comparison-head-pre-cleanup")
            if journal.current["stage"] in {"shadow_failed", "shadow_unavailable", "comparison_completed", "comparison_indeterminate"}:
                state = journal.current
                journal.commit("completed", legacy=state["legacy"], artifacts=state.get("artifacts", {}), usage=state["usage"],
                               shadow=state.get("shadow", {}), comparison=state.get("comparison", {"status": "unavailable"}),
                               validation=state.get("validation", {}))
        except Exception:
            # Do not publish a guessed shadow result. Recovery can use a full
            # receipt; otherwise the intent is deliberately manual recovery.
            try:
                if (journal.current["stage"] == "legacy_committed"
                        and journal.receipt("shadow-intent-v1.json")
                        and journal.receipt("shadow-receipt-v1.json") is None):
                    journal.commit("manual_recovery_required", legacy=journal.current["legacy"], artifacts=journal.current.get("artifacts", {}),
                                   usage=journal.current["usage"], reason="interrupted-shadow-or-comparison",
                                   validation=journal.current.get("validation", {}))
            except Exception:
                pass
            interrupted = True
        result = _result(packet, journal.current, legacy_output)
        delivery["result"] = result
        if interrupted:
            result["handOff"] = "interrupted"
        else:
            try:
                _immutable(root, base + "/usage-comparison-v1.json", canonical(result["usage"]))
                _immutable(root, base + "/live-shadow-result-v1.json", canonical(result))
                fault("final-cleanup")
            except Exception:
                result["handOff"] = "failed"
        return legacy_status, result, legacy_output, legacy_stderr


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManualRecoveryRequired:
        print("ERROR: manualRecoveryRequired: legacy outcome cannot be attested", file=sys.stderr)
        raise SystemExit(2)
    except (mode.runtime.ContractError, shared.Error, consumer.pipeline.runtime.ContractError,
            consumer.phase.runtime.ContractError, OSError, ValueError, TypeError) as error:
        print("ERROR: live shadow host hand-off failed (" + type(error).__name__ + ")", file=sys.stderr)
        raise SystemExit(2)
