#!/usr/bin/env python3
"""CTX-03 contracts, untrusted checkpoint validation, and contained writes."""
from __future__ import annotations

import ctypes
import errno
import hashlib
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
STRUCTURAL_ONLY_KINDS = {
    "execution-envelope": "execution-envelope-v1.schema.json",
    "context-manifest": "context-manifest-v1.schema.json",
    "provider-capabilities": "provider-capabilities-v1.schema.json",
    "run-state": "run-state-v1.schema.json",
    "transition-bundle": "transition-bundle-v1.schema.json",
    "delegation-plan": "delegation-plan-v1.schema.json",
    "delegation-merge": "delegation-merge-v1.schema.json",
}
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
    "provider-capabilities": 64 * 1024,
    "run-state": 16 * 1024,
    "transition-bundle": 32 * 1024,
    "delegation-plan": 64 * 1024,
    "delegation-merge": 256 * 1024,
    "delegation-task": 32 * 1024,
    "delegation-result": 64 * 1024,
    "finding-validation": 16 * 1024,
    "usage-summary": None,
}
DELEGATION_LIMITS = {
    "tasks": 32,
    "skillsPerTask": 16,
    "evidenceRefsPerTask": 64,
    "taskEvidenceGaps": 16,
    "claimsPerCategory": 32,
    "questions": 32,
    "gaps": 32,
    "artifactRefs": 32,
    "proseChars": 512,
    "gapDescriptionChars": 256,
}
PATH_FIELD_NAMES = {"projectroot", "workspace", "localpath", "outputpath"}
PROSE_FIELD_NAMES = {
    "claim", "question", "reason", "objective", "requiredevidence",
    "nextaction", "description", "constraints", "stopconditions",
}
MAX_PROSE_LINES = 4
DIFF_HEADER = re.compile(r"(?m)^diff --git |^--- [^\n]+\n\+\+\+ [^\n]+\n@@ ")
LOG_LINE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+Z?|\[[^\]\n]{1,32}\])(?:\s+|$)")
THREAD_LINE = re.compile(r"^(?:author|reviewer|commenter|user|assistant)\s*:", re.I)
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
SIGNAL_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
LEGACY_ACTIVATION_WARNING = (
    "Legacy activation fallback: profile has no skill_activation block; "
    "all candidate skills are active until migration."
)


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
            if len(value) < schema.get("minProperties", 0) or len(value) > schema.get("maxProperties", 2**31):
                errors.append(f"{location}: property count is outside bounds")
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


USAGE_MAX_INTEGER = 9007199254740991
USAGE_FIELDS = ("input", "cachedInput", "uncachedInput", "output", "reasoning")


def usage_totals_status(totals: Any, parse_errors: Any = 0) -> str:
    """Classify numeric usage without deriving an unreported dimension."""
    if (not isinstance(totals, dict) or set(totals) - set(USAGE_FIELDS)
            or not isinstance(parse_errors, int) or isinstance(parse_errors, bool)
            or parse_errors < 0 or parse_errors > 0):
        return "invalid"
    values = [totals.get(key) for key in USAGE_FIELDS]
    if any(value is not None and (not isinstance(value, int) or isinstance(value, bool)
           or value < 0 or value > USAGE_MAX_INTEGER) for value in values):
        return "invalid"
    total, cached, uncached = values[:3]
    if total is not None:
        if any(value is not None and value > total for value in (cached, uncached)):
            return "invalid"
        if cached is not None and uncached is not None and cached + uncached != total:
            return "invalid"
    if not any(value is not None for value in values):
        return "unavailable"
    return "measured" if all(value is not None for value in values) else "partial"


def semantic_validate(kind: str, value: dict[str, Any]) -> None:
    reject_unsafe_content(value)
    if kind == "context-manifest":
        semantic_validate_context_manifest(value)
    elif kind == "evidence-manifest":
        semantic_validate_evidence_manifest(value)
    elif kind == "usage-summary":
        for record in [value, *value["phases"]]:
            status = usage_totals_status(record["totals"], record["parseErrors"])
            # Invalid traces have unavailable numeric totals and explicit
            # parseErrors. They remain auditable, never measured or partial.
            if status == "invalid":
                if record["usageStatus"] != "unavailable" or any(v is not None for v in record["totals"].values()):
                    raise ContractError("invalid usage must be unavailable with null totals")
            elif record["usageStatus"] != status:
                raise ContractError("usage status differs from numeric availability")
    for facts_key in ("verifiedFacts", "findings"):
        for index, fact in enumerate(value.get(facts_key, [])):
            if not fact.get("evidenceRefs"):
                raise ContractError(f"{facts_key}[{index}]: facts require evidence references")
    if kind != "delegation-result":
        for index, question in enumerate(value.get("openQuestions", [])):
            if not question.get("requiredEvidence"):
                raise ContractError(f"openQuestions[{index}]: required evidence is mandatory")


def derive_workspace_id(project_root: Path, workspace: str) -> str:
    """Derive a non-path workspace identity from one authorized Mana workspace."""
    if not is_safe_relative_path(workspace):
        raise ContractError("workspace must be a safe project-relative path")
    components = workspace.split("/")
    if (
        len(components) != 3
        or components[0] != ".mana"
        or components[1] not in {"features", "sessions"}
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", components[2]) is None
    ):
        raise ContractError("workspace must name one canonical Mana feature or session workspace")
    workspace_kind = "feature" if components[1] == "features" else "session"
    safe_list_directory(project_root, workspace)
    payload = safe_read_bytes(
        Path(f"{workspace}/manifest.yaml"), project_root=project_root, max_bytes=16 * 1024
    )
    try:
        manifest = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError(f"workspace manifest is not UTF-8: {error}") from error
    expected = {"workspace_type": workspace_kind, "workspace_id": components[2]}
    for key, value in expected.items():
        observed = re.findall(rf"(?m)^{key}:[ ]*(.*?)[ ]*$", manifest)
        if observed not in ([value], [f'"{value}"']):
            raise ContractError("workspace manifest does not authorize the requested workspace identity")
    identity = {
        "identityVersion": "mana.context-runtime.workspace-identity/v1",
        "workspaceKind": workspace_kind,
        "workspaceName": components[2],
    }
    return "W-" + hashlib.sha256(canonical_bytes(identity)).hexdigest()


def evidence_record_identity(
    execution_id: str, workspace_id: str, item: dict[str, Any]
) -> bytes:
    """Return the canonical, timestamp-independent CTX-05 record identity."""
    return canonical_bytes({
        "executionId": execution_id,
        "workspaceId": workspace_id,
        "kind": item["kind"],
        "sourceSystem": item["sourceSystem"],
        "sourceLocator": item["sourceLocator"],
        "revisionId": item["revisionId"],
        "rawDigest": item.get("digest"),
        "normalizedDigest": item.get("normalizedRepresentation", {}).get("digest"),
        "normalizationVersion": item["normalizationVersion"],
        "mediaType": item["mediaType"],
        "sensitivity": item["sensitivity"],
        "relationships": item["relationships"],
        "collectionStatus": item["collectionStatus"],
        "collectionError": item.get("collectionError"),
        "gaps": item.get("gaps", []),
    })


def evidence_record_id(execution_id: str, workspace_id: str, item: dict[str, Any]) -> str:
    return "E-" + hashlib.sha256(
        evidence_record_identity(execution_id, workspace_id, item)
    ).hexdigest()


def semantic_validate_evidence_manifest(value: dict[str, Any]) -> None:
    """Validate CTX-05 identities and payload/status invariants."""
    execution_id = value["executionId"]
    workspace_id = value["workspaceId"]
    identifiers: list[str] = []
    for index, item in enumerate(value["items"]):
        identifier = item["evidenceId"]
        identifiers.append(identifier)
        if identifier != evidence_record_id(execution_id, workspace_id, item):
            raise ContractError(f"items[{index}]: evidenceId does not match canonical record identity")
        status = item["collectionStatus"]
        if status in {"complete", "partial"}:
            source = item["sourcePayload"]
            normalized = item["normalizedRepresentation"]
            if item["digest"] != source["digest"]:
                raise ContractError(f"items[{index}]: digest does not match source payload")
            if item["localPath"] != normalized["localPath"] or item["byteSize"] != normalized["byteSize"]:
                raise ContractError(f"items[{index}]: compatibility payload metadata is inconsistent")
            raw_hex = source["digest"].split(":", 1)[1]
            normalized_hex = normalized["digest"].split(":", 1)[1]
            if source["localPath"] != f".mana/runtime-evidence/payloads/source/{raw_hex}.bin":
                raise ContractError(f"items[{index}]: source blob path does not match its digest")
            if normalized["localPath"] != f".mana/runtime-evidence/payloads/normalized/{normalized_hex}.bin":
                raise ContractError(f"items[{index}]: normalized blob path does not match its digest")
        try:
            _parse_timestamp(item["collectedAt"], f"items[{index}].collectedAt")
        except ContractError:
            raise
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("evidence manifest contains duplicate evidence IDs")


def semantic_validate_context_manifest(value: dict[str, Any]) -> None:
    """Check internal consistency only; this is not authoritative validation."""
    candidate_ids = value["declaredCandidateSkills"]
    active_records = value["activatedSkills"]
    active_ids = [record["id"] for record in active_records]
    inactive_ids = value["inactiveSkills"]
    candidate_set, active_set, inactive_set = set(candidate_ids), set(active_ids), set(inactive_ids)

    if len(active_ids) != len(active_set):
        raise ContractError("context manifest activates a skill more than once")
    if active_set & inactive_set:
        raise ContractError("context manifest marks a skill both active and inactive")
    if active_set | inactive_set != candidate_set:
        raise ContractError("context manifest active/inactive skills must exactly partition declared candidates")

    baseline_set = set(value["baselineSkills"])
    if not baseline_set <= active_set:
        raise ContractError("context manifest baseline skills must be declared and active")

    static_records = value["staticallyActivatedSkills"]
    semantic_records = value["semanticallyRequestedSkills"]
    available_records = value["availableConditionalSkills"]
    for label, records in (
        ("static activation", static_records),
        ("semantic request", semantic_records),
    ):
        requested = [record["skill"] for record in records]
        signals = [record["signal"] for record in records]
        if len(requested) != len(set(requested)):
            raise ContractError(f"context manifest contains duplicate {label} skills")
        if len(signals) != len(set(signals)):
            raise ContractError(f"context manifest contains duplicate {label} signals")
        if not set(requested) <= active_set:
            raise ContractError(f"context manifest {label} contains an undeclared or inactive skill")
    available_skills = [record["skill"] for record in available_records]
    available_signals = [record["signal"] for record in available_records]
    if len(available_signals) != len(set(available_signals)):
        raise ContractError("context manifest contains duplicate available conditional signals")
    if not set(available_skills) <= inactive_set:
        raise ContractError("available conditional skills must be declared and inactive")

    static_pairs = {(record["skill"], record["signal"]) for record in static_records}
    semantic_pairs = {(record["skill"], record["signal"]) for record in semantic_records}
    for record in active_records:
        identity, reason, signal = record["id"], record["reason"], record["activationSignal"]
        valid_reason = (
            (reason == "baseline" and identity in baseline_set and signal is None)
            or (reason == "static-signal" and (identity, signal) in static_pairs)
            or (reason == "semantic-request" and (identity, signal) in semantic_pairs)
            or (reason == "legacy-fallback" and value["activationMode"] == "legacy-fallback" and signal is None)
        )
        if not valid_reason:
            raise ContractError(f"activated skill {identity!r} has inconsistent activation provenance")

    deep_records = value["deepLoadedSkills"]
    deep_ids = [record["id"] for record in deep_records]
    if len(deep_ids) != len(set(deep_ids)) or not set(deep_ids) <= active_set:
        raise ContractError("deep-loaded skills must be unique and active")
    for record in deep_records:
        if record["instructionPath"] != f"skills/{record['id']}/SKILL.md":
            raise ContractError("deep-loaded instruction path does not match its active skill")

    escalation_expected = {
        record["id"] for record in active_records
        if record["modelTier"] == "full" or record["riskLevel"] == "high"
    }
    if set(value["modelEscalationSkills"]) != escalation_expected:
        raise ContractError("model escalation skills do not match active full/high-risk work")
    write_expected = {record["id"] for record in active_records if record["executionMode"] == "write"}
    if set(value["writePermissionRequirements"]) != write_expected:
        raise ContractError("write permission requirements do not match active write work")

    if value["activationMode"] == "legacy-fallback":
        if (
            baseline_set != candidate_set or inactive_set or static_records
            or semantic_records or available_records
            or any(record["reason"] != "legacy-fallback" for record in active_records)
            or not value["warnings"]
        ):
            raise ContractError("legacy fallback must keep every candidate active and emit a warning")


def _host_text(path: Path, label: str) -> str:
    try:
        if not path.is_file():
            raise ContractError(f"authoritative {label} is missing")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ContractError(f"cannot read authoritative {label}: {error}") from error


def _top_level_scalar(text: str, key: str, label: str) -> str:
    matches: list[str] = []
    pattern = re.compile(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$")
    for line in text.splitlines():
        match = pattern.fullmatch(line)
        if match:
            matches.append(match.group(1))
    if len(matches) != 1 or not matches[0]:
        raise ContractError(f"authoritative {label} must declare exactly one non-empty {key}")
    return matches[0]


def _top_level_list(text: str, key: str, label: str) -> list[str]:
    lines = text.splitlines()
    headers = [index for index, line in enumerate(lines) if re.fullmatch(rf"{re.escape(key)}:[ \t]*", line)]
    if len(headers) != 1:
        raise ContractError(f"authoritative {label} must declare exactly one {key} list")
    values: list[str] = []
    for line in lines[headers[0] + 1:]:
        if line and not line[0].isspace() and not line.startswith("- ") and not line.lstrip().startswith("#"):
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"[ ]*-[ ]+([^\s][^\r\n]*?)[ ]*", line)
        if not match:
            raise ContractError(f"authoritative {label} has malformed {key} list entry")
        values.append(match.group(1))
    if not values:
        raise ContractError(f"authoritative {label} declares an empty {key} list")
    if len(values) != len(set(values)):
        raise ContractError(f"authoritative {label} declares duplicate {key} entries")
    return values


def _validate_ids(values: list[str], label: str) -> None:
    for value in values:
        if IDENTIFIER.fullmatch(value) is None:
            raise ContractError(f"authoritative {label} contains malformed identifier")


def _parse_skill_activation(text: str, profile_id: str) -> tuple[str, list[str], dict[str, str]]:
    """Return absent/valid activation; every present malformed shape fails."""
    lines = text.splitlines()
    occurrences = [
        (index, line) for index, line in enumerate(lines)
        if re.match(r"^[ \t]*skill_activation[ \t]*:", line)
    ]
    if not occurrences:
        return "legacy-fallback", [], {}
    if len(occurrences) != 1:
        raise ContractError(f"profile {profile_id!r} declares skill_activation more than once")
    start, header = occurrences[0]
    if header != "skill_activation:":
        raise ContractError(f"profile {profile_id!r} has malformed skill_activation header")

    block: list[str] = []
    for line in lines[start + 1:]:
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        block.append(line)

    baseline: list[str] = []
    conditional: dict[str, str] = {}
    seen_sections: set[str] = set()
    active_section: str | None = None
    for line in block:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line:
            raise ContractError(f"profile {profile_id!r} has tab-indented skill_activation")
        indent = len(line) - len(line.lstrip(" "))
        content = line[indent:]
        section_match = re.fullmatch(r"(baseline|conditional):[ ]*", content)
        if indent == 2 and section_match:
            active_section = section_match.group(1)
            if active_section in seen_sections:
                raise ContractError(f"profile {profile_id!r} duplicates skill_activation.{active_section}")
            seen_sections.add(active_section)
            continue
        if indent == 2 and re.fullmatch(r"[A-Za-z0-9_-]+:.*", content):
            raise ContractError(f"profile {profile_id!r} has unknown key in skill_activation")
        if active_section == "baseline":
            item = re.fullmatch(r"-[ ]+([^\s][A-Za-z0-9_-]*)[ ]*", content)
            if indent not in {2, 4} or item is None:
                raise ContractError(f"profile {profile_id!r} has malformed skill_activation.baseline entry")
            skill = item.group(1)
            if IDENTIFIER.fullmatch(skill) is None:
                raise ContractError(f"profile {profile_id!r} has malformed baseline skill id")
            baseline.append(skill)
            continue
        if active_section == "conditional":
            item = re.fullmatch(r"([A-Za-z0-9_-]+):[ ]+([A-Za-z0-9_-]+)[ ]*", content)
            if indent != 4 or item is None:
                raise ContractError(f"profile {profile_id!r} has malformed skill_activation.conditional entry")
            signal, skill = item.groups()
            if SIGNAL_IDENTIFIER.fullmatch(signal) is None or IDENTIFIER.fullmatch(skill) is None:
                raise ContractError(f"profile {profile_id!r} has malformed conditional signal or skill id")
            if signal in conditional:
                raise ContractError(f"profile {profile_id!r} declares duplicate conditional signal {signal!r}")
            conditional[signal] = skill
            continue
        raise ContractError(f"profile {profile_id!r} has partially valid or malformed skill_activation")

    if seen_sections != {"baseline", "conditional"}:
        raise ContractError(f"profile {profile_id!r} skill_activation requires baseline and conditional mappings")
    if not baseline:
        raise ContractError(f"profile {profile_id!r} skill_activation.baseline must be a non-empty list")
    if len(baseline) != len(set(baseline)):
        raise ContractError(f"profile {profile_id!r} declares duplicate baseline skill")
    conditional_skills = list(conditional.values())
    duplicates = sorted({skill for skill in conditional_skills if conditional_skills.count(skill) > 1})
    if duplicates:
        raise ContractError(f"profile {profile_id!r} maps one conditional skill to multiple signals: {duplicates[0]}")
    conflict = set(baseline) & set(conditional_skills)
    if conflict:
        raise ContractError(f"profile {profile_id!r} marks a skill baseline and conditional: {sorted(conflict)[0]}")
    return "declarative", baseline, conditional


def _parse_skill_index(framework_root: Path) -> dict[str, dict[str, str]]:
    text = _host_text(framework_root / "skills" / "index.yaml", "skill index")
    records: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in text.splitlines():
        match = re.fullmatch(r"  - id: ([A-Za-z0-9_-]+)[ ]*", line)
        if match:
            identity = match.group(1)
            if identity in records:
                raise ContractError("authoritative skill index declares duplicate skill id")
            current = {"id": identity}
            records[identity] = current
            continue
        if current is not None:
            field = re.fullmatch(r"    (path|risk_level|model_tier|execution_mode|delegation_group|capability|verification_spec):[ ]+([^\s]+)[ ]*", line)
            if field:
                current[field.group(1)] = field.group(2)
    required = {"path", "risk_level", "model_tier", "execution_mode", "delegation_group"}
    for identity, record in records.items():
        if not required <= record.keys():
            raise ContractError(f"authoritative skill index metadata is incomplete for {identity!r}")
    return records


def _front_matter(text: str, label: str) -> list[str]:
    lines = text.splitlines()
    boundaries = [index for index, line in enumerate(lines) if line == "---"]
    if len(boundaries) < 2 or boundaries[0] != 0:
        raise ContractError(f"authoritative {label} has malformed front matter")
    return lines[1:boundaries[1]]


def _front_matter_scalar(lines: list[str], key: str) -> str | None:
    values = [match.group(1) for line in lines if (match := re.fullmatch(rf"{re.escape(key)}:[ ]*(.*?)[ ]*", line))]
    if len(values) > 1:
        raise ContractError(f"authoritative front matter duplicates {key}")
    return values[0] if values else None


def _front_matter_list(lines: list[str], key: str) -> list[str]:
    headers = [index for index, line in enumerate(lines) if re.fullmatch(rf"{re.escape(key)}:[ ]*", line)]
    if not headers:
        return []
    if len(headers) != 1:
        raise ContractError(f"authoritative front matter duplicates {key}")
    values: list[str] = []
    for line in lines[headers[0] + 1:]:
        match = re.fullmatch(r"  - (.+?)[ ]*", line)
        if match:
            values.append(match.group(1))
            continue
        if line and not line[0].isspace():
            break
        if line.strip():
            raise ContractError(f"authoritative front matter has malformed {key} entry")
    return values


def _canonical_framework_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    if not root.is_dir():
        raise ContractError("authoritative framework root is not a directory")
    return root


def compile_context_manifest(
    framework_root: str | Path, profile_id: str, execution_id: str, *,
    static_signals: list[str] | None = None,
    requested_skills: list[str] | None = None,
    deep_load_skills: list[str] | None = None,
) -> dict[str, Any]:
    """Compile exclusively from host-resolved framework sources and inputs."""
    root = _canonical_framework_root(framework_root)
    if IDENTIFIER.fullmatch(profile_id) is None:
        raise ContractError("profile id is malformed")
    if re.fullmatch(r"execution-[A-Za-z0-9._-]{1,120}", execution_id) is None:
        raise ContractError("execution id is malformed")
    profile_path = root / "profiles" / f"{profile_id}.yaml"
    profile_text = _host_text(profile_path, "profile")
    if _top_level_scalar(profile_text, "name", "profile") != profile_id:
        raise ContractError("authoritative profile name does not match profile id")
    candidates = _top_level_list(profile_text, "skills", "profile")
    agents = _top_level_list(profile_text, "agents", "profile")
    _validate_ids(candidates, "profile skills")
    _validate_ids(agents, "profile agents")
    activation_mode, baseline, conditional = _parse_skill_activation(profile_text, profile_id)
    if activation_mode == "legacy-fallback":
        baseline = list(candidates)
    if not set(baseline) <= set(candidates):
        raise ContractError("authoritative baseline skill is not a declared candidate")
    if not set(conditional.values()) <= set(candidates):
        raise ContractError("authoritative conditional skill is not a declared candidate")

    index = _parse_skill_index(root)
    for skill in candidates:
        if skill not in index:
            raise ContractError(f"authoritative profile declares unknown skill {skill!r}")
        path = index[skill]["path"]
        if not is_safe_relative_path(path) or not (root / path).is_file():
            raise ContractError(f"authoritative skill metadata has unsafe or missing path for {skill!r}")

    static_signals = list(static_signals or [])
    requested_skills = list(requested_skills or [])
    deep_load_skills = list(deep_load_skills or [])
    for label, values in (("static signal", static_signals), ("semantic skill request", requested_skills), ("deep-load request", deep_load_skills)):
        if len(values) != len(set(values)):
            raise ContractError(f"duplicate {label}")
    if activation_mode == "legacy-fallback" and (static_signals or requested_skills):
        raise ContractError("legacy profile does not accept declarative activation requests")
    for signal in static_signals:
        if SIGNAL_IDENTIFIER.fullmatch(signal) is None or signal not in conditional:
            raise ContractError(f"undeclared static activation signal {signal!r}")
    inverse = {skill: signal for signal, skill in conditional.items()}
    for skill in requested_skills:
        if IDENTIFIER.fullmatch(skill) is None or skill not in inverse:
            raise ContractError(f"undeclared semantic skill request {skill!r}")
    static_skills = {conditional[signal] for signal in static_signals}
    if static_skills & set(requested_skills):
        raise ContractError("one conditional skill cannot be activated by both static and semantic requests")

    active_reasons: dict[str, tuple[str, str | None]] = {
        skill: ("legacy-fallback" if activation_mode == "legacy-fallback" else "baseline", None)
        for skill in baseline
    }
    for signal in static_signals:
        active_reasons[conditional[signal]] = ("static-signal", signal)
    for skill in requested_skills:
        active_reasons[skill] = ("semantic-request", inverse[skill])
    active_ids = sorted(active_reasons)
    for skill in deep_load_skills:
        if skill not in active_reasons:
            raise ContractError(f"cannot deep-load inactive or undeclared skill {skill!r}")

    activated: list[dict[str, Any]] = []
    escalation: list[str] = []
    write_requirements: list[str] = []
    for skill in active_ids:
        metadata = index[skill]
        tier = metadata["model_tier"] or "unspecified"
        risk = metadata["risk_level"] or "unspecified"
        mode = metadata["execution_mode"] or "unspecified"
        group = metadata["delegation_group"] or "unspecified"
        if tier not in {"economy", "full", "unspecified"}:
            raise ContractError(f"authoritative model tier is invalid for {skill!r}")
        if risk not in {"low", "medium", "high", "unspecified"}:
            raise ContractError(f"authoritative risk level is invalid for {skill!r}")
        if mode not in {"read", "write", "unspecified"}:
            raise ContractError(f"authoritative execution mode is invalid for {skill!r}")
        skill_text = _host_text(root / metadata["path"], f"skill {skill}")
        parallel_value = _front_matter_scalar(_front_matter(skill_text, f"skill {skill}"), "parallel_safe")
        if parallel_value not in {None, "", "true", "false"}:
            raise ContractError(f"authoritative parallel_safe is invalid for {skill!r}")
        parallel = True if parallel_value == "true" else False if parallel_value == "false" else None
        reason, signal = active_reasons[skill]
        activated.append({"id": skill, "reason": reason, "activationSignal": signal, "modelTier": tier, "riskLevel": risk, "executionMode": mode, "delegationGroup": group, "parallelSafe": parallel})
        if tier == "full" or risk == "high":
            escalation.append(skill)
        if mode == "write":
            write_requirements.append(skill)

    artifacts: set[str] = set()
    for agent in agents:
        agent_path = root / "agents" / agent / "AGENT.md"
        front_matter = _front_matter(_host_text(agent_path, f"agent {agent}"), f"agent {agent}")
        for artifact in _front_matter_list(front_matter, "outputs"):
            if not any(character.isspace() for character in artifact) and ("." in artifact or "/" in artifact):
                if not is_safe_relative_path(artifact):
                    raise ContractError(f"authoritative agent output is unsafe for {agent!r}")
                artifacts.add(artifact)

    inactive = sorted(set(candidates) - set(active_ids))
    available = [{"signal": signal, "skill": skill} for signal, skill in sorted(conditional.items()) if skill in inactive]
    manifest = {
        "schemaVersion": "mana.context-runtime.context-manifest/v1", "executionId": execution_id,
        "profileId": profile_id, "activationMode": activation_mode, "semanticAgents": sorted(agents),
        "declaredCandidateSkills": sorted(candidates), "baselineSkills": sorted(baseline),
        "staticallyActivatedSkills": [{"signal": signal, "skill": conditional[signal]} for signal in sorted(static_signals)],
        "semanticallyRequestedSkills": [{"skill": skill, "signal": inverse[skill]} for skill in sorted(requested_skills)],
        "activatedSkills": activated,
        "deepLoadedSkills": [{"id": skill, "instructionPath": index[skill]["path"]} for skill in sorted(deep_load_skills)],
        "inactiveSkills": inactive, "availableConditionalSkills": available,
        "modelEscalationSkills": sorted(escalation), "writePermissionRequirements": sorted(write_requirements),
        "requiredArtifacts": sorted(artifacts),
        "limits": {"directWorkers": 2, "workerDepth": 0, "retrievalCyclesPerQuestion": 3},
        "warnings": [LEGACY_ACTIVATION_WARNING] if activation_mode == "legacy-fallback" else [],
    }
    validate_model("context-manifest", manifest)
    return manifest


def authoritative_validate_context_manifest(
    candidate: dict[str, Any], framework_root: str | Path, profile_id: str,
    execution_id: str, *, static_signals: list[str] | None = None,
    requested_skills: list[str] | None = None, deep_load_skills: list[str] | None = None,
) -> None:
    """Compare candidate data with a fresh derivation from trusted host sources."""
    validate_model("context-manifest", candidate)
    expected = compile_context_manifest(framework_root, profile_id, execution_id, static_signals=static_signals, requested_skills=requested_skills, deep_load_skills=deep_load_skills)
    if canonical_bytes(candidate) != canonical_bytes(expected):
        differing = next((key for key in sorted(set(candidate) | set(expected)) if candidate.get(key) != expected.get(key)), "unknown")
        raise ContractError(f"authoritative context manifest mismatch at $.{differing}")


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
        or checkpoint["profileId"] != identity["profileId"]
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


def _anchored_components(path: Path, project_root: Path | None) -> tuple[Path, list[str]]:
    if project_root is None:
        if path.is_absolute():
            return Path(path.anchor), list(path.parts[1:])
        return Path("."), list(path.parts)
    root = Path(os.path.abspath(project_root))
    if path.is_absolute():
        candidate = Path(os.path.abspath(path))
        try:
            relative = candidate.relative_to(root)
        except ValueError as error:
            raise ContractError("input path escapes the authorized root") from error
        return root, list(relative.parts)
    return root, list(path.parts)


def _safe_read_file(
    path: Path, *, project_root: Path | None = None, max_bytes: int | None = None,
    required_mode: int | None = None, required_parent_mode: int | None = None,
    require_single_link: bool = False,
) -> tuple[bytes, tuple[int, int]]:
    """Read a regular file through an FD-anchored no-follow boundary."""
    nofollow, directory = _require_secure_dir_fd_support()
    anchor, components = _anchored_components(path, project_root)
    if not components or any(component in {"", ".", ".."} for component in components):
        raise ContractError("input path must not contain empty, dot, or traversal components")
    root_fd, parent_fds, fd = -1, [], -1
    try:
        root_fd = _open_directory(anchor, dir_fd=None, nofollow=nofollow, directory=directory)
        parent_fd, parent_fds = _walk_existing_parent(root_fd, components[:-1], nofollow, directory)
        fd = os.open(components[-1], os.O_RDONLY | os.O_NONBLOCK | nofollow, dir_fd=parent_fd)
        initial = os.fstat(fd)
        if not stat.S_ISREG(initial.st_mode):
            raise ContractError("input must be a regular, non-symlink file")
        if ((required_mode is not None and stat.S_IMODE(initial.st_mode) != required_mode)
                or (require_single_link and initial.st_nlink != 1)
                or (required_parent_mode is not None
                    and stat.S_IMODE(os.fstat(parent_fd).st_mode) != required_parent_mode)):
            raise ContractError("input permissions or link count differ from required private artifact mode")
        _test_read_sync("after-final-open")
        if not _same_existing_directory_from_root(root_fd, components[:-1], parent_fd, nofollow, directory):
            raise ContractError("input parent binding changed during traversal")
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise ContractError(f"input exceeds its {max_bytes} byte limit")
            chunks.append(chunk)
        if required_mode is not None or required_parent_mode is not None or require_single_link:
            final = os.fstat(fd)
            named = os.stat(components[-1], dir_fd=parent_fd, follow_symlinks=False)
            stable_fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            if (any(getattr(initial, field) != getattr(final, field) for field in stable_fields)
                    or _entry_identity(named) != _entry_identity(final)
                    or not _same_existing_directory_from_root(
                        root_fd, components[:-1], parent_fd, nofollow, directory)
                    or (required_parent_mode is not None
                        and stat.S_IMODE(os.fstat(parent_fd).st_mode) != required_parent_mode)):
                raise ContractError("private input identity changed during read")
        return b"".join(chunks), (initial.st_dev, initial.st_ino)
    except OSError as error:
        raise ContractError(f"cannot read input: {error}") from error
    finally:
        if fd >= 0:
            os.close(fd)
        for opened_fd in reversed(parent_fds):
            os.close(opened_fd)
        if root_fd >= 0:
            os.close(root_fd)


def safe_read_bytes(
    path: Path, *, project_root: Path | None = None, max_bytes: int | None = None,
) -> bytes:
    """Read bytes through the CTX-03 FD-anchored no-follow boundary."""
    return _safe_read_file(
        path, project_root=project_root, max_bytes=max_bytes,
    )[0]


def safe_read_private_bytes(
    path: Path, *, project_root: Path, max_bytes: int,
) -> tuple[bytes, tuple[int, int]]:
    """Read private immutable bytes and their identity from the same held FD."""
    return _safe_read_file(
        path, project_root=project_root, max_bytes=max_bytes,
        required_mode=0o600, required_parent_mode=0o700, require_single_link=True,
    )


def safe_read_json(path: Path) -> dict[str, Any]:
    """Read JSON through an FD-anchored, component-wise no-follow walk."""
    try:
        value = json.loads(safe_read_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read JSON input: {error}") from error
    if not isinstance(value, dict):
        raise ContractError("contract value must be a JSON object")
    return value


def ensure_secure_directory(project_root: Path, relative: str) -> None:
    """Create/reopen one directory tree below an anchored trusted root."""
    if not is_safe_relative_path(relative):
        raise ContractError("directory path must be a safe project-relative path")
    nofollow, directory = _require_secure_dir_fd_support()
    root_fd, opened = -1, []
    try:
        root_fd = _open_directory(project_root, dir_fd=None, nofollow=nofollow, directory=directory)
        target_fd, opened = _walk_parent(root_fd, relative.split("/"), nofollow, directory)
        if not _same_directory_from_root(root_fd, relative.split("/"), target_fd, nofollow, directory):
            raise ContractError("directory binding changed during creation")
    finally:
        for fd in reversed(opened):
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)


def validate_secure_root(project_root: Path) -> None:
    """Open and classify a trusted root without creating any entry."""
    nofollow, directory = _require_secure_dir_fd_support()
    fd = _open_directory(project_root, dir_fd=None, nofollow=nofollow, directory=directory)
    os.close(fd)


def safe_list_directory(project_root: Path, relative: str) -> list[str]:
    """List a directory only while its root-relative binding remains valid."""
    if not is_safe_relative_path(relative):
        raise ContractError("directory path must be a safe project-relative path")
    nofollow, directory = _require_secure_dir_fd_support()
    root_fd, opened = -1, []
    try:
        root_fd = _open_directory(project_root, dir_fd=None, nofollow=nofollow, directory=directory)
        target_fd, opened = _walk_existing_parent(root_fd, relative.split("/"), nofollow, directory)
        names = os.listdir(target_fd)
        if not _same_existing_directory_from_root(root_fd, relative.split("/"), target_fd, nofollow, directory):
            raise ContractError("directory binding changed during listing")
        return sorted(names)
    except OSError as error:
        raise ContractError(f"cannot list directory: {error}") from error
    finally:
        for fd in reversed(opened):
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)


def _remove_directory_contents(directory_fd: int, nofollow: int, directory: int) -> None:
    """Remove an open directory tree without following or reopening pathnames."""
    for name in os.listdir(directory_fd):
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = _open_directory(name, dir_fd=directory_fd, nofollow=nofollow, directory=directory)
            try:
                if _entry_identity(os.fstat(child_fd)) != _entry_identity(metadata):
                    raise ContractError("cleanup entry identity changed")
                _remove_directory_contents(child_fd, nofollow, directory)
            finally:
                os.close(child_fd)
            if _entry_identity(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) != _entry_identity(metadata):
                raise ContractError("cleanup directory identity changed")
            os.rmdir(name, dir_fd=directory_fd)
        else:
            os.unlink(name, dir_fd=directory_fd)


class PrivateStagingDirectory:
    """One inode-stable private tree from staging through publication or abort."""

    def __init__(
        self, project_root: Path, parent_relative: str, name: str,
        root_fd: int, parent_fds: list[int], staging_fd: int,
        nofollow: int, directory: int,
    ) -> None:
        self._project_root = Path(os.path.abspath(project_root))
        self._parent_relative = parent_relative
        self._parent_components = parent_relative.split("/")
        self._name = name
        self._root_fd = root_fd
        self._parent_fds = parent_fds
        self._parent_fd = parent_fds[-1]
        self._staging_fd = staging_fd
        self._nofollow = nofollow
        self._directory = directory
        self._identity = _entry_identity(os.fstat(staging_fd))
        self._publication_name: str | None = None
        self._published = False
        self._closed = False

    @classmethod
    def create(
        cls, project_root: Path, parent_relative: str, prefix: str,
    ) -> "PrivateStagingDirectory":
        if not is_safe_relative_path(parent_relative):
            raise ContractError("staging parent must be a safe project-relative path")
        if re.fullmatch(r"[A-Za-z0-9._-]{1,160}", prefix) is None:
            raise ContractError("staging prefix is malformed")
        ensure_secure_directory(project_root, parent_relative)
        nofollow, directory = _require_secure_dir_fd_support()
        root_fd, parent_fds, staging_fd = -1, [], -1
        name: str | None = None
        created_identity: tuple[int, int, int] | None = None
        try:
            root_fd = _open_directory(
                project_root, dir_fd=None, nofollow=nofollow, directory=directory
            )
            parent_fd, parent_fds = _walk_existing_parent(
                root_fd, parent_relative.split("/"), nofollow, directory
            )
            for _ in range(128):
                candidate = f".{prefix}.stage.{secrets.token_hex(8)}"
                try:
                    os.mkdir(candidate, mode=0o700, dir_fd=parent_fd)
                    name = candidate
                    created_identity = _entry_identity(
                        os.stat(candidate, dir_fd=parent_fd, follow_symlinks=False)
                    )
                    break
                except FileExistsError:
                    continue
            if name is None:
                raise ContractError("could not allocate a private staging directory")
            staging_fd = _open_directory(
                name, dir_fd=parent_fd, nofollow=nofollow, directory=directory
            )
            os.fchmod(staging_fd, 0o700)
            metadata = os.fstat(staging_fd)
            if stat.S_IMODE(metadata.st_mode) != 0o700:
                raise ContractError("staging directory is not mode 0700")
            if (
                created_identity != _entry_identity(metadata)
                or not _verify_identity(parent_fd, name, created_identity)
            ):
                raise ContractError("staging directory binding changed during creation")
            if not _same_existing_directory_from_root(
                root_fd, parent_relative.split("/"), parent_fd, nofollow, directory
            ):
                raise ContractError("staging parent binding changed during creation")
            result = cls(
                project_root, parent_relative, name, root_fd, parent_fds,
                staging_fd, nofollow, directory,
            )
            root_fd, parent_fds, staging_fd = -1, [], -1
            return result
        except BaseException:
            if name is not None and parent_fds:
                try:
                    if (
                        staging_fd >= 0 and created_identity is not None
                        and _entry_identity(os.fstat(staging_fd)) == created_identity
                    ):
                        _remove_directory_contents(staging_fd, nofollow, directory)
                    if (
                        created_identity is not None
                        and _verify_identity(parent_fds[-1], name, created_identity)
                    ):
                        os.rmdir(name, dir_fd=parent_fds[-1])
                except (ContractError, OSError):
                    pass
            raise
        finally:
            if staging_fd >= 0:
                os.close(staging_fd)
            for fd in reversed(parent_fds):
                os.close(fd)
            if root_fd >= 0:
                os.close(root_fd)

    def _require_open(self) -> None:
        if self._closed:
            raise ContractError("staging directory handle is closed")

    def _attest_parent(self) -> bool:
        return _same_existing_directory_from_root(
            self._root_fd, self._parent_components, self._parent_fd,
            self._nofollow, self._directory,
        )

    def _attest_staging_name(self) -> bool:
        return self._attest_parent() and _verify_identity(
            self._parent_fd, self._name, self._identity
        )

    def _attest_publication_name(self) -> bool:
        return (
            self._publication_name is not None
            and self._attest_parent()
            and _verify_identity(
                self._parent_fd, self._publication_name, self._identity
            )
        )

    def ensure_directory(self, relative: str) -> None:
        self._require_open()
        if not is_safe_relative_path(relative):
            raise ContractError("staged directory path must be safe and relative")
        target_fd, opened = _walk_parent(
            self._staging_fd, relative.split("/"), self._nofollow, self._directory
        )
        try:
            if not _same_directory_from_root(
                self._staging_fd, relative.split("/"), target_fd,
                self._nofollow, self._directory,
            ):
                raise ContractError("staged directory binding changed during creation")
        finally:
            for fd in reversed(opened):
                os.close(fd)

    def write_bytes(self, relative: str, payload: bytes) -> None:
        """Create one mode-0600 staged file relative to the held staging FD."""
        self._require_open()
        if not is_safe_relative_path(relative):
            raise ContractError("staged file path must be safe and relative")
        if not isinstance(payload, bytes):
            raise ContractError("staged payload must be bytes")
        components = relative.split("/")
        parent_fd, opened = _walk_existing_parent(
            self._staging_fd, components[:-1], self._nofollow, self._directory
        )
        fd = -1
        identity: tuple[int, int, int] | None = None
        try:
            fd = os.open(
                components[-1],
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | self._nofollow,
                0o600,
                dir_fd=parent_fd,
            )
            os.fchmod(fd, 0o600)
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise ContractError("staged output is not a mode-0600 regular file")
            identity = _entry_identity(metadata)
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise OSError(errno.EIO, "short staged write")
                offset += written
            os.fsync(fd)
            if not _same_existing_directory_from_root(
                self._staging_fd, components[:-1], parent_fd,
                self._nofollow, self._directory,
            ) or not _verify_identity(parent_fd, components[-1], identity):
                raise ContractError("staged output binding changed during write")
        except BaseException:
            if identity is not None:
                try:
                    if _verify_identity(parent_fd, components[-1], identity):
                        os.unlink(components[-1], dir_fd=parent_fd)
                except OSError:
                    pass
            raise
        finally:
            if fd >= 0:
                os.close(fd)
            for opened_fd in reversed(opened):
                os.close(opened_fd)

    def read_bytes(self, relative: str, *, max_bytes: int) -> bytes:
        """Re-validate one staged regular file through the held staging FD."""
        self._require_open()
        if not is_safe_relative_path(relative):
            raise ContractError("staged input path must be safe and relative")
        components = relative.split("/")
        parent_fd, opened = _walk_existing_parent(
            self._staging_fd, components[:-1], self._nofollow, self._directory
        )
        fd = -1
        try:
            fd = os.open(
                components[-1], os.O_RDONLY | os.O_NONBLOCK | self._nofollow,
                dir_fd=parent_fd,
            )
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise ContractError("staged input is not a regular file")
            identity = _entry_identity(metadata)
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(fd, 64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ContractError(f"staged input exceeds its {max_bytes} byte limit")
                chunks.append(chunk)
            if not _same_existing_directory_from_root(
                self._staging_fd, components[:-1], parent_fd,
                self._nofollow, self._directory,
            ) or not _verify_identity(parent_fd, components[-1], identity):
                raise ContractError("staged input binding changed during validation")
            return b"".join(chunks)
        finally:
            if fd >= 0:
                os.close(fd)
            for opened_fd in reversed(opened):
                os.close(opened_fd)

    def publish_noreplace(self, final_name: str) -> Path:
        """Publish the complete tree without crossing the caller's commit barrier."""
        self._require_open()
        if re.fullmatch(r"[A-Za-z0-9._-]{1,160}", final_name) is None:
            raise ContractError("final run directory name is malformed")
        if not self._attest_staging_name():
            raise ContractError("staging directory binding changed before commit")
        primitives = _require_rename_primitives()
        try:
            primitives.noreplace(self._parent_fd, self._name, self._parent_fd, final_name)
        except FileExistsError as error:
            raise ContractError(
                f"phase run directory collision: {self._parent_relative}/{final_name}"
            ) from error
        self._publication_name = final_name
        if (
            not _verify_identity(self._parent_fd, final_name, self._identity)
            or not self._attest_parent()
        ):
            try:
                primitives.noreplace(
                    self._parent_fd, final_name, self._parent_fd, self._name
                )
                if not self._attest_staging_name():
                    raise OSError(errno.EIO, "rolled-back staging identity mismatch")
                self._publication_name = None
            except OSError as rollback_error:
                raise ContractError(
                    "published run directory could not be re-attested or rolled back"
                ) from rollback_error
            raise ContractError("publication parent binding changed during commit")
        return self._project_root / self._parent_relative / final_name

    def commit_publication(self) -> None:
        """Mark an already attested publication committed after the host barrier."""
        self._require_open()
        if self._published or self._publication_name is None:
            raise ContractError("run publication is not awaiting commit")
        # The caller crosses its signal barrier immediately before this assignment.
        # No filesystem operation or other fallible work belongs between the two.
        self._published = True

    def _depublish_to_abort(self) -> None:
        """Atomically hide an uncommitted final entry behind a private abort name."""
        if self._publication_name is None:
            return
        if self._published:
            raise ContractError("committed run publication cannot be aborted")
        if not self._attest_publication_name():
            raise ContractError("published run directory binding changed before abort")
        primitives = _require_rename_primitives()
        abort_name: str | None = None
        for _ in range(128):
            candidate = f".{self._name}.abort.{secrets.token_hex(8)}"
            try:
                primitives.noreplace(
                    self._parent_fd, self._publication_name,
                    self._parent_fd, candidate,
                )
                abort_name = candidate
                break
            except FileExistsError:
                continue
        if abort_name is None:
            raise ContractError("could not allocate a private abort directory")
        self._name = abort_name
        self._publication_name = None
        if not self._attest_staging_name():
            raise ContractError("aborted run directory binding changed after de-publication")
        os.fsync(self._parent_fd)

    def cleanup(self) -> None:
        """Remove staging or an aborted publication through held descriptors only."""
        self._require_open()
        if self._published:
            return
        self._depublish_to_abort()
        if not self._attest_staging_name():
            raise ContractError("staging directory binding changed before cleanup")
        _remove_directory_contents(self._staging_fd, self._nofollow, self._directory)
        if not self._attest_staging_name():
            raise ContractError("staging directory binding changed during cleanup")
        os.rmdir(self._name, dir_fd=self._parent_fd)
        os.fsync(self._parent_fd)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        os.close(self._staging_fd)
        for fd in reversed(self._parent_fds):
            os.close(fd)
        os.close(self._root_fd)


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


def _verified_regular_bytes(
    parent_fd: int, name: str, expected: tuple[int, int, int], max_bytes: int,
) -> bytes | None:
    """Read one identity-pinned regular entry without following its name."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | nofollow, dir_fd=parent_fd)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or _entry_identity(metadata) != expected:
            return None
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                return None
            chunks.append(chunk)
        if not _verify_identity(parent_fd, name, expected):
            return None
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        if fd >= 0:
            os.close(fd)


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


_EXPECTED_CURRENT_UNSET = object()


def atomic_write_bytes(
    project_root: Path, relative: str, payload: bytes, *, immutable: bool = False,
    expected_current: bytes | None | object = _EXPECTED_CURRENT_UNSET,
) -> Path:
    """Publish bytes with CTX-03 no-replace/exchange and anchored cleanup."""
    if not is_safe_relative_path(relative):
        raise ContractError("output path must be a safe project-relative path")
    if not isinstance(payload, bytes):
        raise ContractError("atomic byte payload must be bytes")
    nofollow, directory = _require_secure_dir_fd_support()
    primitives = _require_rename_primitives()
    components = relative.split("/")
    parent_components, target_name = components[:-1], components[-1]
    root_fd, parent_fds, temporary_name, temporary_fd = -1, [], None, -1
    temporary_identity: tuple[int, int, int] | None = None
    temporary_expected_payload: bytes | None = None
    try:
        root_fd = _open_directory(project_root, dir_fd=None, nofollow=nofollow, directory=directory)
        parent_fd, parent_fds = _walk_parent(root_fd, parent_components, nofollow, directory)
        _test_sync("after-parent-open")
        original_identity = _inspect_destination(parent_fd, target_name)
        _test_sync("after-destination-inspection")
        must_read_existing = original_identity is not None and (
            immutable or expected_current is not _EXPECTED_CURRENT_UNSET
        )
        if expected_current is None and original_identity is not None:
            raise ContractError("destination appeared after the caller observed it absent")
        if isinstance(expected_current, bytes) and original_identity is None:
            raise ContractError("destination disappeared after the caller validated it")
        if must_read_existing:
            existing_fd = -1
            try:
                existing_fd = os.open(target_name, os.O_RDONLY | os.O_NONBLOCK | nofollow, dir_fd=parent_fd)
                if (
                    not stat.S_ISREG(os.fstat(existing_fd).st_mode)
                    or _entry_identity(os.fstat(existing_fd)) != original_identity
                ):
                    raise ContractError("immutable destination identity changed during verification")
                existing_chunks = []
                while True:
                    chunk = os.read(existing_fd, 64 * 1024)
                    if not chunk:
                        break
                    existing_chunks.append(chunk)
                _test_sync("after-immutable-read")
                if (
                    not _verify_identity(parent_fd, target_name, original_identity)
                    or not _same_directory_from_root(root_fd, parent_components, parent_fd, nofollow, directory)
                ):
                    raise ContractError("immutable destination binding changed during verification")
                existing_payload = b"".join(existing_chunks)
                if isinstance(expected_current, bytes) and existing_payload != expected_current:
                    raise ContractError("destination changed after caller validation")
                if immutable and existing_payload == payload:
                    return Path(os.path.abspath(project_root)) / relative
                if immutable:
                    raise ContractError("immutable evidence payload collision")
            finally:
                if existing_fd >= 0:
                    os.close(existing_fd)
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
            # The exchange changes which inode the private name denotes. From
            # this point onward it is the displaced original, not the staged
            # payload. Track and verify that identity before any cleanup. This
            # also makes exception cleanup safe at the permanent post-exchange
            # fault point below.
            temporary_identity = original_identity
            temporary_expected_payload = (
                expected_current if isinstance(expected_current, bytes) else None
            )
            displaced_expected = (
                not isinstance(expected_current, bytes)
                or _verified_regular_bytes(
                    parent_fd, temporary_name, original_identity,
                    len(expected_current),
                ) == expected_current
            )
            if (
                not _verify_identity(parent_fd, temporary_name, original_identity)
                or not displaced_expected
            ):
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
            _test_sync("after-exchange-before-cleanup")
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
            if (
                not _verify_identity(parent_fd, temporary_name, original_identity)
                or (
                    isinstance(expected_current, bytes)
                    and _verified_regular_bytes(
                        parent_fd, temporary_name, original_identity,
                        len(expected_current),
                    ) != expected_current
                )
            ):
                raise ContractError("displaced destination changed before cleanup")
            os.unlink(temporary_name, dir_fd=parent_fd)
            temporary_name = None
            os.fsync(parent_fd)
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        if temporary_name is not None and temporary_identity is not None and parent_fds:
            try:
                verified_payload = (
                    temporary_expected_payload is None
                    or _verified_regular_bytes(
                        parent_fds[-1], temporary_name, temporary_identity,
                        len(temporary_expected_payload),
                    ) == temporary_expected_payload
                )
                if (
                    verified_payload
                    and _verify_identity(parent_fds[-1], temporary_name, temporary_identity)
                ):
                    os.unlink(temporary_name, dir_fd=parent_fds[-1])
            except FileNotFoundError:
                pass
        for fd in reversed(parent_fds):
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)
    return Path(os.path.abspath(project_root)) / relative


def atomic_write(project_root: Path, relative: str, value: dict[str, Any]) -> Path:
    """Preserve the public CTX-03 canonical-JSON writer contract."""
    return atomic_write_bytes(project_root, relative, canonical_bytes(value) + b"\n")


def usage() -> int:
    print(
        "Usage:\n"
        "  context-runtime.py validate-model <kind> <input.json>\n"
        "  context-runtime.py validate-structure <execution-envelope|context-manifest|provider-capabilities|run-state|transition-bundle> <input.json>\n"
        "  context-runtime.py write-model <kind> <input.json> <project-root> <relative-output>\n"
        "  context-runtime.py host-validate-authority <authority.json>\n"
        "  context-runtime.py host-write-authority <authority.json> <project-root> <relative-output>\n"
        "  context-runtime.py evaluate-checkpoint <checkpoint.json> [authority.json]\n"
        "  context-runtime.py compile-context-manifest <framework-root> <profile-id> <execution-id> [activation options]\n"
        "  context-runtime.py authoritative-validate-context-manifest <manifest.json> <framework-root> <profile-id> <execution-id> [activation options]\n"
        "  context-runtime.py authoritative-materialize-context-manifest <manifest.json> <framework-root> <profile-id> <execution-id> [activation options]",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return usage()
    command = argv[1]
    try:
        if command in {
            "compile-context-manifest",
            "authoritative-validate-context-manifest",
            "authoritative-materialize-context-manifest",
        }:
            offset = 2
            candidate_path: Path | None = None
            if command in {
                "authoritative-validate-context-manifest",
                "authoritative-materialize-context-manifest",
            }:
                if len(argv) < 6:
                    return usage()
                candidate_path = Path(argv[offset])
                offset += 1
            if len(argv) < offset + 3:
                return usage()
            framework_root, profile_id, execution_id = argv[offset:offset + 3]
            offset += 3
            static_signals: list[str] = []
            requested_skills: list[str] = []
            deep_load_skills: list[str] = []
            while offset < len(argv):
                option = argv[offset]
                if offset + 1 >= len(argv):
                    raise ContractError(f"{option} requires a value")
                value = argv[offset + 1]
                if option == "--static-signal":
                    static_signals.append(value)
                elif option == "--request-skill":
                    requested_skills.append(value)
                elif option == "--deep-load-skill":
                    deep_load_skills.append(value)
                else:
                    raise ContractError(f"unknown context manifest option: {option}")
                offset += 2
            if candidate_path is not None:
                candidate = safe_read_json(candidate_path)
                authoritative_validate_context_manifest(
                    candidate, framework_root, profile_id, execution_id,
                    static_signals=static_signals, requested_skills=requested_skills,
                    deep_load_skills=deep_load_skills,
                )
                if command == "authoritative-materialize-context-manifest":
                    # Emit the exact in-memory value that passed authoritative
                    # comparison. Consumers can capture these bytes once and
                    # never reopen the caller-controlled candidate pathname.
                    sys.stdout.buffer.write(canonical_bytes(candidate) + b"\n")
                return 0
            manifest = compile_context_manifest(
                framework_root, profile_id, execution_id,
                static_signals=static_signals, requested_skills=requested_skills,
                deep_load_skills=deep_load_skills,
            )
            if manifest["activationMode"] == "legacy-fallback":
                print(f"WARNING: {LEGACY_ACTIVATION_WARNING}", file=sys.stderr)
            sys.stdout.buffer.write(canonical_bytes(manifest) + b"\n")
            return 0
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
