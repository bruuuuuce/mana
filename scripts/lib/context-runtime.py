#!/usr/bin/env python3
"""CTX-03 contracts, untrusted checkpoint validation, and contained writes."""
from __future__ import annotations

import ctypes
import errno
import json
import os
import re
import secrets
import stat
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts" / "context-runtime"
MODEL_KINDS = {
    "context-manifest": "context-manifest-v1.schema.json",
    "evidence-manifest": "evidence-manifest-v1.schema.json",
    "phase-input": "phase-input-v1.schema.json",
    "phase-checkpoint": "phase-checkpoint-v1.schema.json",
    "delegation-task": "delegation-task-v1.schema.json",
    "delegation-result": "delegation-result-v1.schema.json",
    "finding-validation": "finding-validation-v1.schema.json",
    "usage-summary": "usage-summary-v1.schema.json",
}
STRUCTURAL_ONLY_KINDS = {"execution-envelope": "execution-envelope-v1.schema.json"}
HOST_AUTHORITY_SCHEMA = "host-authority-context-v1.schema.json"

# Version-specific transport limits. CTX-01 usage-summary-v1 intentionally has
# no new host cap because its historical schema did not define one.
MAX_BYTES: dict[str, int | None] = {
    "execution-envelope": 16 * 1024,
    "host-authority-context": 32 * 1024,
    "context-manifest": 64 * 1024,
    "evidence-manifest": 256 * 1024,
    "phase-input": 64 * 1024,
    "phase-checkpoint": 16 * 1024,
    "delegation-task": 32 * 1024,
    "delegation-result": 16 * 1024,
    "finding-validation": 16 * 1024,
    "usage-summary": None,
}
PATH_FIELD_NAMES = {"projectroot", "workspace", "localpath", "outputpath"}
PROSE_FIELD_NAMES = {
    "claim", "question", "reason", "objective", "requiredevidence",
    "nextaction", "description",
}
MAX_PROSE_LINES = 4
DIFF_HEADER = re.compile(r"(?m)^diff --git |^--- [^\n]+\n\+\+\+ [^\n]+\n@@ ")
LOG_LINE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+Z?|\[[^\]\n]{1,32}\])(?:\s+|$)")
THREAD_LINE = re.compile(r"^(?:author|reviewer|commenter|user|assistant)\s*:", re.I)


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class HostAuthorityContext:
    """Validated host control-plane input; never made from checkpoint fields."""
    _canonical: bytes

    @property
    def value(self) -> dict[str, Any]:
        # Return a fresh value so callers cannot mutate the validated execution
        # identity or approval records after the trust transition.
        return json.loads(self._canonical)


@dataclass(frozen=True)
class EffectiveAuthority:
    execution_id: str | None
    execution_version: int | None
    permissions: dict[str, Any] | None
    approvals: tuple[dict[str, Any], ...]
    unresolved_approvals: tuple[dict[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "executionVersion": self.execution_version,
            "effectivePermissions": self.permissions,
            "completedApprovals": list(self.approvals),
            "unresolvedApprovals": list(self.unresolved_approvals),
        }


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def normalized_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_safe_relative_path(value: str, *, allow_dot: bool = False) -> bool:
    if value == ".":
        return allow_dot
    if not value or value.startswith("/") or "\\" in value or "//" in value:
        return False
    return all(part not in {"", ".", ".."} and not part.startswith("~") for part in value.split("/"))


class RollbackFailure(ContractError):
    """Publication succeeded, rollback did not: host recovery is required."""

    category = "publication-succeeded-rollback-failed"
    operation = "atomic-write"
    manual_recovery_required = True

    def __init__(
        self, *, stage: str, destination: str, destination_state: str,
        recovery_artifact: str | None, original_recovery_artifact: str | None,
        staging_temporary: str | None, new_content_may_remain: bool,
        original_preserved: bool, recovery_permissions_restricted: bool | None,
        cause: Exception,
    ) -> None:
        for label, path in (
            ("destination", destination),
            ("recovery artifact", recovery_artifact),
            ("original recovery artifact", original_recovery_artifact),
            ("staging temporary", staging_temporary),
        ):
            if path is not None and not is_safe_relative_path(path):
                raise ContractError(f"rollback {label} must be a safe relative path")
        super().__init__("publication succeeded but rollback failed; manual recovery required")
        self.stage = stage
        self.destination = destination
        self.destination_state = destination_state
        self.recovery_artifact = recovery_artifact
        self.original_recovery_artifact = original_recovery_artifact
        self.staging_temporary = staging_temporary
        self.new_content_may_remain = new_content_may_remain
        self.original_preserved = original_preserved
        self.recovery_permissions_restricted = recovery_permissions_restricted
        underlying_errno = getattr(cause, "errno", None)
        self.underlying_errno = underlying_errno if isinstance(underlying_errno, int) else None
        self.underlying_cause = type(cause).__name__

    def as_dict(self) -> dict[str, Any]:
        """Return only bounded, non-payload recovery metadata."""
        return {
            "category": self.category,
            "operation": self.operation,
            "stage": self.stage,
            "destination": self.destination,
            "destinationState": self.destination_state,
            "recoveryArtifact": self.recovery_artifact,
            "originalRecoveryArtifact": self.original_recovery_artifact,
            "stagingTemporary": self.staging_temporary,
            "newContentMayRemain": self.new_content_may_remain,
            "originalPreserved": self.original_preserved,
            "recoveryArtifactPermissionsRestricted": self.recovery_permissions_restricted,
            "underlyingErrno": self.underlying_errno,
            "underlyingCause": self.underlying_cause,
            "manualRecoveryRequired": self.manual_recovery_required,
        }


class Evaluator:
    """Minimal JSON Schema evaluator for the subset in these contracts."""
    def __init__(self) -> None:
        self.documents: dict[Path, Any] = {}

    def load(self, path: Path) -> Any:
        path = path.resolve()
        if path not in self.documents:
            with path.open(encoding="utf-8") as handle:
                self.documents[path] = json.load(handle)
        return self.documents[path]

    def resolve_ref(self, reference: str, document: Path) -> tuple[Any, Path]:
        path_part, separator, fragment = reference.partition("#")
        target_path = (document.parent / path_part).resolve() if path_part else document.resolve()
        target = self.load(target_path)
        if separator and fragment:
            if not fragment.startswith("/"):
                raise ContractError(f"unsupported schema reference: {reference}")
            for token in fragment[1:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                target = target[int(token)] if isinstance(target, list) else target[token]
        return target, target_path

    @staticmethod
    def _type(value: Any, expected: str) -> bool:
        return {
            "null": value is None, "boolean": isinstance(value, bool),
            "object": isinstance(value, dict), "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        }.get(expected, False)

    def evaluate(self, value: Any, schema: Any, document: Path, location: str = "$") -> list[str]:
        if schema is True:
            return []
        if schema is False or not isinstance(schema, dict):
            return [f"{location}: invalid schema"]
        errors: list[str] = []
        if "$ref" in schema:
            target, target_document = self.resolve_ref(schema["$ref"], document)
            errors.extend(self.evaluate(value, target, target_document, location))
        if "type" in schema:
            expected = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(self._type(value, item) for item in expected):
                return errors + [f"{location}: expected {schema['type']!r}"]
        if "const" in schema and value != schema["const"]:
            errors.append(f"{location}: does not match required schema version")
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{location}: value is not allowed")
        if isinstance(value, str):
            if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 2**31):
                errors.append(f"{location}: string length is outside bounds")
            if "pattern" in schema and re.search(schema["pattern"], value) is None:
                errors.append(f"{location}: string does not match required pattern")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value < schema.get("minimum", value) or value > schema.get("maximum", value):
                errors.append(f"{location}: number is outside bounds")
        if isinstance(value, list):
            if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 2**31):
                errors.append(f"{location}: item count is outside bounds")
            if schema.get("uniqueItems") and len({canonical_bytes(item) for item in value}) != len(value):
                errors.append(f"{location}: items must be unique")
            if "items" in schema:
                for index, item in enumerate(value):
                    errors.extend(self.evaluate(item, schema["items"], document, f"{location}[{index}]"))
        if isinstance(value, dict):
            for name in schema.get("required", []):
                if name not in value:
                    errors.append(f"{location}: missing required field {name!r}")
            properties = schema.get("properties", {})
            for name, item in value.items():
                if name in properties:
                    errors.extend(self.evaluate(item, properties[name], document, f"{location}.{name}"))
                elif schema.get("additionalProperties") is False:
                    errors.append(f"{location}: unknown field {name!r}")
                elif isinstance(schema.get("additionalProperties"), dict):
                    errors.extend(self.evaluate(item, schema["additionalProperties"], document, f"{location}.{name}"))
        for child in schema.get("allOf", []):
            errors.extend(self.evaluate(value, child, document, location))
        if "anyOf" in schema and not any(not self.evaluate(value, child, document, location) for child in schema["anyOf"]):
            errors.append(f"{location}: no allowed shape matched")
        if "oneOf" in schema:
            matched = sum(not self.evaluate(value, child, document, location) for child in schema["oneOf"])
            if matched != 1:
                errors.append(f"{location}: expected exactly one allowed shape")
        return errors


def _looks_like_bulk_payload(text: str) -> bool:
    stripped = text.strip()
    if stripped[:1] in {"{", "["} and stripped[-1:] in {"}", "]"}:
        try:
            if isinstance(json.loads(stripped), (dict, list)):
                return True
        except json.JSONDecodeError:
            pass
    if DIFF_HEADER.search(stripped):
        return True
    lines = stripped.splitlines()
    return (
        len(lines) > MAX_PROSE_LINES
        or (len(lines) >= 3 and all(LOG_LINE.search(line) for line in lines))
        or (len(lines) >= 3 and all(THREAD_LINE.search(line) for line in lines))
    )


def reject_unsafe_content(value: Any, location: str = "$", field_name: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = normalized_name(key)
            if normalized in PATH_FIELD_NAMES and isinstance(child, str):
                if not is_safe_relative_path(child, allow_dot=normalized == "projectroot"):
                    raise ContractError(f"{location}.{key}: project path must be safe and relative")
            reject_unsafe_content(child, f"{location}.{key}", normalized)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_unsafe_content(child, f"{location}[{index}]", field_name)
    elif isinstance(value, str) and field_name in PROSE_FIELD_NAMES and _looks_like_bulk_payload(value):
        raise ContractError(f"{location}: prose field cannot transport bulk/raw evidence")


def _validate_schema(kind: str, value: dict[str, Any], schema_name: str) -> None:
    cap = MAX_BYTES[kind]
    if cap is not None and len(canonical_bytes(value)) > cap:
        raise ContractError(f"{kind} exceeds its {cap} byte limit")
    evaluator = Evaluator()
    schema_path = CONTRACTS / schema_name
    errors = evaluator.evaluate(value, evaluator.load(schema_path), schema_path)
    if errors:
        raise ContractError("; ".join(errors[:8]))


def semantic_validate(kind: str, value: dict[str, Any]) -> None:
    reject_unsafe_content(value)
    for facts_key in ("verifiedFacts", "findings"):
        for index, fact in enumerate(value.get(facts_key, [])):
            if not fact.get("evidenceRefs"):
                raise ContractError(f"{facts_key}[{index}]: facts require evidence references")
    for index, question in enumerate(value.get("openQuestions", [])):
        if not question.get("requiredEvidence"):
            raise ContractError(f"openQuestions[{index}]: required evidence is mandatory")


def validate_model(kind: str, value: dict[str, Any]) -> None:
    if kind not in MODEL_KINDS:
        raise ContractError(f"unknown model/data contract kind: {kind}")
    _validate_schema(kind, value, MODEL_KINDS[kind])
    semantic_validate(kind, value)


def validate_structure(kind: str, value: dict[str, Any]) -> None:
    """Validate syntax only; this operation never creates authority."""
    if kind not in STRUCTURAL_ONLY_KINDS:
        raise ContractError(f"unknown structural-only contract kind: {kind}")
    _validate_schema(kind, value, STRUCTURAL_ONLY_KINDS[kind])
    reject_unsafe_content(value)


def _parse_timestamp(value: str, field: str) -> datetime:
    """Parse the RFC3339 timezone-aware subset declared by the host schema."""
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except (TypeError, ValueError) as error:
        raise ContractError(f"{field} must be a valid RFC3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone")
    return parsed


def load_host_authority(value: dict[str, Any]) -> HostAuthorityContext:
    _validate_schema("host-authority-context", value, HOST_AUTHORITY_SCHEMA)
    reject_unsafe_content(value)
    gate_ids = [gate["gateId"] for gate in value["humanGates"]]
    if len(gate_ids) != len(set(gate_ids)):
        raise ContractError("host authority contains duplicate gate IDs")
    record_keys = [
        (record["approvalId"], record["gateId"], record["executionId"], record["executionVersion"])
        for record in value["approvalRecords"]
    ]
    if len(record_keys) != len(set(record_keys)):
        raise ContractError("host authority contains duplicate approval records")
    issued_at = _parse_timestamp(value["executionIdentity"]["issuedAt"], "issuedAt")
    for index, record in enumerate(value["approvalRecords"]):
        completed_at = _parse_timestamp(record["completedAt"], f"approvalRecords[{index}].completedAt")
        if completed_at < issued_at:
            raise ContractError(f"approvalRecords[{index}].completedAt precedes issuedAt")
    return HostAuthorityContext(_canonical=canonical_bytes(value))


def evaluate_checkpoint(checkpoint: dict[str, Any], authority: HostAuthorityContext | None = None) -> EffectiveAuthority:
    """Derive permission and approval state solely from trusted host input."""
    validate_model("phase-checkpoint", checkpoint)
    requests = checkpoint.get("approvalRequests", [])
    if authority is None:
        return EffectiveAuthority(None, None, None, (), tuple(requests))
    if not isinstance(authority, HostAuthorityContext):
        raise ContractError("authority must be a validated HostAuthorityContext")
    host = authority.value
    identity = host["executionIdentity"]
    if (
        checkpoint["executionId"] != identity["executionId"]
        or checkpoint["executionVersion"] != identity["executionVersion"]
    ):
        return EffectiveAuthority(None, None, None, (), tuple(requests))
    records = {
        (record["approvalId"], record["gateId"]): record
        for record in host["approvalRecords"]
        if record["executionId"] == identity["executionId"]
        and record["executionVersion"] == identity["executionVersion"]
        and record["decision"] == "approved"
    }
    known_gates = {gate["gateId"] for gate in host["humanGates"]}
    completed, unresolved = [], []
    for request in requests:
        record = records.get((request["approvalId"], request["gateId"]))
        if request["gateId"] not in known_gates or record is None:
            unresolved.append(request)
        else:
            completed.append({
                "approvalId": record["approvalId"], "gateId": record["gateId"],
                "recordId": record["provenance"]["sourceRecordId"],
            })
    return EffectiveAuthority(
        identity["executionId"], identity["executionVersion"], host["effectivePermissions"],
        tuple(completed), tuple(unresolved),
    )


def _require_secure_dir_fd_support() -> tuple[int, int]:
    nofollow, directory = getattr(os, "O_NOFOLLOW", None), getattr(os, "O_DIRECTORY", None)
    required = (os.open, os.mkdir, os.stat, os.unlink)
    if nofollow is None or directory is None or any(fn not in os.supports_dir_fd for fn in required):
        raise ContractError("platform lacks required directory-FD/no-follow primitives")
    return nofollow, directory


def _open_directory(name: str | Path, *, dir_fd: int | None, nofollow: int, directory: int) -> int:
    fd = os.open(name, os.O_RDONLY | directory | nofollow, dir_fd=dir_fd)
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise ContractError(f"output component is not a directory: {name}")
    return fd


def _walk_parent(root_fd: int, components: list[str], nofollow: int, directory: int) -> tuple[int, list[int]]:
    current_fd, opened = os.dup(root_fd), []
    opened.append(current_fd)
    try:
        for component in components:
            try:
                child_fd = _open_directory(component, dir_fd=current_fd, nofollow=nofollow, directory=directory)
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                child_fd = _open_directory(component, dir_fd=current_fd, nofollow=nofollow, directory=directory)
            opened.append(child_fd)
            current_fd = child_fd
        return current_fd, opened
    except BaseException:
        for fd in reversed(opened):
            os.close(fd)
        raise


def _walk_existing_parent(root_fd: int, components: list[str], nofollow: int, directory: int) -> tuple[int, list[int]]:
    current_fd, opened = os.dup(root_fd), []
    opened.append(current_fd)
    try:
        for index, component in enumerate(components):
            child_fd = _open_directory(component, dir_fd=current_fd, nofollow=nofollow, directory=directory)
            opened.append(child_fd)
            current_fd = child_fd
            _test_read_sync(f"after-parent-component:{index}")
        return current_fd, opened
    except BaseException:
        for fd in reversed(opened):
            os.close(fd)
        raise


def _same_directory_from_root(root_fd: int, components: list[str], expected_fd: int, nofollow: int, directory: int) -> bool:
    try:
        check_fd, opened = _walk_parent(root_fd, components, nofollow, directory)
    except OSError:
        return False
    try:
        expected, actual = os.fstat(expected_fd), os.fstat(check_fd)
        return (expected.st_dev, expected.st_ino) == (actual.st_dev, actual.st_ino)
    finally:
        for fd in reversed(opened):
            os.close(fd)


def _same_existing_directory_from_root(root_fd: int, components: list[str], expected_fd: int, nofollow: int, directory: int) -> bool:
    try:
        check_fd, opened = _walk_existing_parent(root_fd, components, nofollow, directory)
    except OSError:
        return False
    try:
        expected, actual = os.fstat(expected_fd), os.fstat(check_fd)
        return (expected.st_dev, expected.st_ino) == (actual.st_dev, actual.st_ino)
    finally:
        for fd in reversed(opened):
            os.close(fd)


def _entry_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode)


def _inspect_destination(parent_fd: int, name: str) -> tuple[int, int, int] | None:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ContractError("output target must be a regular file or absent")
    return _entry_identity(metadata)


# Importing tests may set this callback. No production CLI/env surface exposes it.
_TEST_SYNC_HOOK: Callable[[str], None] | None = None
_TEST_READ_SYNC_HOOK: Callable[[str], None] | None = None


def _test_sync(point: str) -> None:
    if _TEST_SYNC_HOOK is not None:
        _TEST_SYNC_HOOK(point)


def _test_read_sync(point: str) -> None:
    if _TEST_READ_SYNC_HOOK is not None:
        _TEST_READ_SYNC_HOOK(point)


def safe_read_json(path: Path) -> dict[str, Any]:
    """Read JSON through an FD-anchored, component-wise no-follow walk."""
    nofollow, directory = _require_secure_dir_fd_support()
    if path.is_absolute():
        anchor, components = Path(path.anchor), list(path.parts[1:])
    else:
        anchor, components = Path("."), list(path.parts)
    if not components or any(component in {"", ".", ".."} for component in components):
        raise ContractError("input path must not contain empty, dot, or traversal components")
    root_fd, parent_fds, fd = -1, [], -1
    try:
        root_fd = _open_directory(anchor, dir_fd=None, nofollow=nofollow, directory=directory)
        parent_fd, parent_fds = _walk_existing_parent(root_fd, components[:-1], nofollow, directory)
        fd = os.open(components[-1], os.O_RDONLY | os.O_NONBLOCK | nofollow, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ContractError("input must be a regular, non-symlink file")
        _test_read_sync("after-final-open")
        if not _same_existing_directory_from_root(root_fd, components[:-1], parent_fd, nofollow, directory):
            raise ContractError("input parent binding changed during traversal")
        with os.fdopen(fd, encoding="utf-8") as handle:
            fd = -1
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read JSON input: {error}") from error
    finally:
        if fd >= 0:
            os.close(fd)
        for opened_fd in reversed(parent_fds):
            os.close(opened_fd)
        if root_fd >= 0:
            os.close(root_fd)
    if not isinstance(value, dict):
        raise ContractError("contract value must be a JSON object")
    return value


class _RenamePrimitives:
    """Minimal Linux/macOS wrappers for kernel no-replace and exchange rename."""
    RENAME_NOREPLACE = 1
    RENAME_EXCHANGE = 2
    RENAME_SWAP = 0x00000002
    RENAME_EXCL = 0x00000004

    def __init__(self) -> None:
        libc = ctypes.CDLL(None, use_errno=True)
        self._function: Any | None = None
        if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
            function = libc.renameat2
            function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            function.restype = ctypes.c_int
            self._function, self._noreplace, self._exchange = function, self.RENAME_NOREPLACE, self.RENAME_EXCHANGE
        elif sys.platform == "darwin" and hasattr(libc, "renameatx_np"):
            function = libc.renameatx_np
            function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            function.restype = ctypes.c_int
            self._function, self._noreplace, self._exchange = function, self.RENAME_EXCL, self.RENAME_SWAP
        else:
            self._noreplace = self._exchange = 0

    @property
    def available(self) -> bool:
        return self._function is not None

    def _rename(self, source_fd: int, source: str, target_fd: int, target: str, flag: int) -> None:
        if self._function is None:
            raise ContractError("platform lacks kernel no-replace/exchange rename primitives")
        ctypes.set_errno(0)
        result = self._function(source_fd, os.fsencode(source), target_fd, os.fsencode(target), flag)
        if result != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), target)

    def noreplace(self, source_fd: int, source: str, target_fd: int, target: str) -> None:
        self._rename(source_fd, source, target_fd, target, self._noreplace)

    def exchange(self, left_fd: int, left: str, right_fd: int, right: str) -> None:
        self._rename(left_fd, left, right_fd, right, self._exchange)


def _require_rename_primitives() -> _RenamePrimitives:
    primitives = _RenamePrimitives()
    if not primitives.available:
        raise ContractError("platform lacks kernel no-replace/exchange rename primitives")
    return primitives


def _verify_identity(parent_fd: int, name: str, expected: tuple[int, int, int]) -> bool:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return _entry_identity(metadata) == expected


def _best_effort_verify_identity(
    parent_fd: int, name: str, expected: tuple[int, int, int],
) -> bool:
    """Inspect recovery state without masking the primary rollback error."""
    try:
        return _verify_identity(parent_fd, name, expected)
    except OSError:
        return False


def _relative_artifact(parent_components: list[str], name: str) -> str:
    return "/".join([*parent_components, name])


def _regular_identity(parent_fd: int, name: str) -> tuple[int, int, int] | None:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        return None
    return _entry_identity(metadata)


def _restrict_recovery_artifact(
    parent_fd: int, name: str, expected: tuple[int, int, int], nofollow: int,
) -> bool:
    """Restrict a verified regular recovery entry without following links."""
    fd = -1
    try:
        fd = os.open(name, os.O_RDONLY | nofollow, dir_fd=parent_fd)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or _entry_identity(metadata) != expected:
            return False
        os.fchmod(fd, 0o600)
        return stat.S_IMODE(os.fstat(fd).st_mode) == 0o600
    except OSError:
        return False
    finally:
        if fd >= 0:
            os.close(fd)


def _rollback_absent(
    primitives: _RenamePrimitives, parent_fd: int, target_name: str,
    temporary_name: str, published_identity: tuple[int, int, int], *,
    destination: str, staging_artifact: str, stage: str,
) -> None:
    try:
        primitives.noreplace(parent_fd, target_name, parent_fd, temporary_name)
        if not _verify_identity(parent_fd, temporary_name, published_identity):
            try:
                primitives.noreplace(parent_fd, temporary_name, parent_fd, target_name)
            except OSError:
                pass
            raise ContractError("cannot verify rollback of newly published destination")
        os.unlink(temporary_name, dir_fd=parent_fd)
    except (ContractError, OSError) as error:
        new_at_destination = _best_effort_verify_identity(
            parent_fd, target_name, published_identity
        )
        new_in_staging = _best_effort_verify_identity(
            parent_fd, temporary_name, published_identity
        )
        if new_at_destination:
            destination_state = "new-content-published"
        elif new_in_staging:
            destination_state = "destination-absent-new-content-in-staging"
        else:
            destination_state = "partial-state-unverified"
        raise RollbackFailure(
            stage=stage,
            destination=destination,
            destination_state=destination_state,
            recovery_artifact=None,
            original_recovery_artifact=None,
            staging_temporary=staging_artifact if new_in_staging else None,
            new_content_may_remain=new_at_destination or destination_state == "partial-state-unverified",
            original_preserved=False,
            recovery_permissions_restricted=None,
            cause=error,
        ) from error


def _rollback_exchange(
    primitives: _RenamePrimitives, parent_fd: int, target_name: str,
    temporary_name: str, rollback_identity: tuple[int, int, int],
    published_identity: tuple[int, int, int], *, destination: str,
    original_identity: tuple[int, int, int], temporary_artifact: str,
    stage: str, nofollow: int,
) -> None:
    try:
        primitives.exchange(parent_fd, temporary_name, parent_fd, target_name)
        if (
            not _verify_identity(parent_fd, target_name, rollback_identity)
            or not _verify_identity(parent_fd, temporary_name, published_identity)
        ):
            raise ContractError("cannot verify atomic replacement rollback")
        os.unlink(temporary_name, dir_fd=parent_fd)
    except (ContractError, OSError) as error:
        new_at_destination = _best_effort_verify_identity(
            parent_fd, target_name, published_identity
        )
        original_at_destination = _best_effort_verify_identity(
            parent_fd, target_name, original_identity
        )
        rollback_entry_at_destination = _best_effort_verify_identity(
            parent_fd, target_name, rollback_identity
        )
        new_in_staging = _best_effort_verify_identity(
            parent_fd, temporary_name, published_identity
        )
        original_in_recovery = _best_effort_verify_identity(
            parent_fd, temporary_name, original_identity
        )
        displaced_identity = _regular_identity(parent_fd, temporary_name)
        recovery_artifact = temporary_artifact if displaced_identity is not None and not new_in_staging else None
        permissions_restricted = None
        if recovery_artifact is not None and displaced_identity is not None:
            permissions_restricted = _restrict_recovery_artifact(
                parent_fd, temporary_name, displaced_identity, nofollow
            )
        if new_at_destination and original_in_recovery:
            destination_state = "new-content-published-original-displaced"
        elif new_at_destination and recovery_artifact is not None:
            destination_state = "new-content-published-displaced-entry-preserved"
        elif original_at_destination:
            destination_state = "original-restored"
        elif rollback_entry_at_destination:
            destination_state = "displaced-entry-restored"
        elif new_at_destination:
            destination_state = "new-content-published-displaced-state-unverified"
        else:
            destination_state = "partial-state-unverified"
        raise RollbackFailure(
            stage=stage,
            destination=destination,
            destination_state=destination_state,
            recovery_artifact=recovery_artifact,
            original_recovery_artifact=temporary_artifact if original_in_recovery else None,
            staging_temporary=temporary_artifact if new_in_staging else None,
            new_content_may_remain=(
                new_at_destination
                or not (original_at_destination or rollback_entry_at_destination)
            ),
            original_preserved=original_at_destination or original_in_recovery,
            recovery_permissions_restricted=permissions_restricted,
            cause=error,
        ) from error


def atomic_write(project_root: Path, relative: str, value: dict[str, Any]) -> Path:
    if not is_safe_relative_path(relative):
        raise ContractError("output path must be a safe project-relative path")
    nofollow, directory = _require_secure_dir_fd_support()
    primitives = _require_rename_primitives()
    components = relative.split("/")
    parent_components, target_name = components[:-1], components[-1]
    root_fd, parent_fds, temporary_name, temporary_fd = -1, [], None, -1
    temporary_identity: tuple[int, int, int] | None = None
    try:
        root_fd = _open_directory(project_root, dir_fd=None, nofollow=nofollow, directory=directory)
        parent_fd, parent_fds = _walk_parent(root_fd, parent_components, nofollow, directory)
        _test_sync("after-parent-open")
        original_identity = _inspect_destination(parent_fd, target_name)
        _test_sync("after-destination-inspection")
        payload = canonical_bytes(value) + b"\n"
        for _ in range(128):
            candidate = f".{target_name}.tmp.{secrets.token_hex(8)}"
            try:
                temporary_fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600, dir_fd=parent_fd)
                temporary_name = candidate
                break
            except FileExistsError:
                pass
        if temporary_name is None:
            raise ContractError("could not allocate a unique temporary file")
        if not stat.S_ISREG(os.fstat(temporary_fd).st_mode):
            raise ContractError("temporary output is not a regular file")
        temporary_identity = _entry_identity(os.fstat(temporary_fd))
        offset = 0
        while offset < len(payload):
            written = os.write(temporary_fd, payload[offset:])
            if written <= 0:
                raise OSError(errno.EIO, "short write")
            offset += written
        os.fsync(temporary_fd)
        if not _same_directory_from_root(root_fd, parent_components, parent_fd, nofollow, directory):
            raise ContractError("output parent changed before publication")
        published_identity = temporary_identity
        temporary_artifact = _relative_artifact(parent_components, temporary_name)
        # This test-only point is intentionally after the last pre-publication
        # namespace check. The following operation is the kernel CAS boundary.
        _test_sync("after-final-prepublish-check")
        if original_identity is None:
            try:
                primitives.noreplace(parent_fd, temporary_name, parent_fd, target_name)
            except FileExistsError as error:
                raise ContractError("destination appeared before exclusive publication") from error
            if not _same_directory_from_root(root_fd, parent_components, parent_fd, nofollow, directory):
                try:
                    _rollback_absent(
                        primitives, parent_fd, target_name, temporary_name, published_identity,
                        destination=relative, staging_artifact=temporary_artifact,
                        stage="post-publication-parent-attestation",
                    )
                except RollbackFailure:
                    temporary_name = None
                    raise
                temporary_name = None
                raise ContractError("output parent binding changed during publication")
            os.fsync(parent_fd)
            temporary_name = None
        else:
            primitives.exchange(parent_fd, temporary_name, parent_fd, target_name)
            if not _verify_identity(parent_fd, temporary_name, original_identity):
                try:
                    _rollback_exchange(
                        primitives, parent_fd, target_name, temporary_name,
                        _entry_identity(os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False)),
                        published_identity, destination=relative,
                        original_identity=original_identity,
                        temporary_artifact=temporary_artifact,
                        stage="post-publication-destination-attestation", nofollow=nofollow,
                    )
                except RollbackFailure:
                    temporary_name = None
                    raise
                temporary_name = None
                raise ContractError("destination identity changed before atomic replacement")
            if not _same_directory_from_root(root_fd, parent_components, parent_fd, nofollow, directory):
                try:
                    _rollback_exchange(
                        primitives, parent_fd, target_name, temporary_name,
                        original_identity, published_identity, destination=relative,
                        original_identity=original_identity,
                        temporary_artifact=temporary_artifact,
                        stage="post-publication-parent-attestation", nofollow=nofollow,
                    )
                except RollbackFailure:
                    temporary_name = None
                    raise
                temporary_name = None
                raise ContractError("output parent binding changed during publication")
            os.fsync(parent_fd)
            os.unlink(temporary_name, dir_fd=parent_fd)
            temporary_name = None
            os.fsync(parent_fd)
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        if temporary_name is not None and temporary_identity is not None and parent_fds:
            try:
                if _verify_identity(parent_fds[-1], temporary_name, temporary_identity):
                    os.unlink(temporary_name, dir_fd=parent_fds[-1])
            except FileNotFoundError:
                pass
        for fd in reversed(parent_fds):
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)
    return Path(os.path.abspath(project_root)) / relative


def usage() -> int:
    print(
        "Usage:\n"
        "  context-runtime.py validate-model <kind> <input.json>\n"
        "  context-runtime.py validate-structure execution-envelope <input.json>\n"
        "  context-runtime.py write-model <kind> <input.json> <project-root> <relative-output>\n"
        "  context-runtime.py host-validate-authority <authority.json>\n"
        "  context-runtime.py host-write-authority <authority.json> <project-root> <relative-output>\n"
        "  context-runtime.py evaluate-checkpoint <checkpoint.json> [authority.json]",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return usage()
    command = argv[1]
    try:
        if command == "validate-model" and len(argv) == 4:
            validate_model(argv[2], safe_read_json(Path(argv[3])))
            return 0
        if command == "validate-structure" and len(argv) == 4:
            validate_structure(argv[2], safe_read_json(Path(argv[3])))
            return 0
        if command == "write-model" and len(argv) == 6:
            kind, input_name, project_root, relative = argv[2:6]
            value = safe_read_json(Path(input_name))
            validate_model(kind, value)
            print(atomic_write(Path(project_root), relative, value))
            return 0
        if command == "host-validate-authority" and len(argv) == 3:
            load_host_authority(safe_read_json(Path(argv[2])))
            return 0
        if command == "host-write-authority" and len(argv) == 5:
            value = safe_read_json(Path(argv[2]))
            load_host_authority(value)
            print(atomic_write(Path(argv[3]), argv[4], value))
            return 0
        if command == "evaluate-checkpoint" and len(argv) in {3, 4}:
            checkpoint = safe_read_json(Path(argv[2]))
            authority = load_host_authority(safe_read_json(Path(argv[3]))) if len(argv) == 4 else None
            print(json.dumps(evaluate_checkpoint(checkpoint, authority).as_dict(), sort_keys=True))
            return 0
        return usage()
    except RollbackFailure as error:
        print(json.dumps({"error": error.as_dict()}, sort_keys=True), file=sys.stderr)
        return 1
    except (ContractError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
