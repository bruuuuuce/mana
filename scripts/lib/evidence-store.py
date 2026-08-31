#!/usr/bin/env python3
"""CTX-05 local evidence collection, metadata, and bounded retrieval."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import mimetypes
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MODULE_PATH = Path(__file__).with_name("context-runtime.py")
SPEC = importlib.util.spec_from_file_location("mana_context_runtime_evidence", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - installation failure
    raise RuntimeError("cannot load CTX-03 filesystem boundary")
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)

SCHEMA = "mana.context-runtime.evidence-manifest/v1"
MAX_OUTPUT_BYTES = 16 * 1024
MAX_PAYLOAD_BYTES = 1024 * 1024 * 1024
MAX_LINE_SPAN = 2000
EXECUTION_RE = re.compile(r"^execution-[A-Za-z0-9._-]{1,120}$")
EVIDENCE_RE = re.compile(r"^E-[a-f0-9]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
SENSITIVITIES = {"public", "internal", "restricted", "secret"}
STATUSES = {"complete", "partial", "failed", "unavailable"}
STORE_BASE = ".mana/runtime-evidence"
SOURCE_DIR = f"{STORE_BASE}/payloads/source"
NORMALIZED_DIR = f"{STORE_BASE}/payloads/normalized"
EXECUTIONS_DIR = f"{STORE_BASE}/executions"
REDACTED = "[REDACTED]"

SENSITIVE_NAMES = {
    "authorization", "proxyauthorization", "cookie", "setcookie", "password",
    "passwd", "secret", "token", "accesstoken", "refreshtoken", "idtoken",
    "apikey", "xapikey", "xauthtoken", "clientsecret", "credential", "credentials",
    "sessionid", "sessiontoken",
}
HEADER_RE = re.compile(
    r"(?im)^((?:authorization|proxy-authorization|cookie|set-cookie|x-api-key|api-key|x-auth-token)\s*:\s*).*$"
)
ASSIGNMENT_RE = re.compile(
    r"(?i)([\"']?\b(?:authorization|proxy-authorization|cookie|set-cookie|password|passwd|secret|"
    r"(?:access|refresh|id|session)?[_-]?token|api[_-]?key|x-api-key|x-auth-token|"
    r"client[_-]?secret|credentials?)\b[\"']?)(\s*[:=]\s*)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;&}\]]+)"
)
URL_RE = re.compile(r"(?i)\b(?:https?|wss?)://[^\s<>\"']+")
BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


class EvidenceError(ValueError):
    pass


def fail(message: str) -> None:
    raise EvidenceError(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def emit(value: Any) -> None:
    sys.stdout.buffer.write(canonical(value) + b"\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_execution(value: str) -> str:
    if not EXECUTION_RE.fullmatch(value):
        fail("execution must match execution-<safe-id>")
    return value


def require_evidence(value: str) -> str:
    if not EVIDENCE_RE.fullmatch(value):
        fail("evidence ID must be a canonical E-<sha256> record ID")
    return value


def require_identifier(name: str, value: str) -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        fail(f"{name} must contain 1..80 letters, digits, _ or -")
    return value


def bounded_text(name: str, value: str | None, maximum: int, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            fail(f"{name} is required")
        return None
    if (required and not value) or len(value) > maximum or any(ord(char) < 0x20 and char not in "\t\n\r" for char in value):
        fail(f"{name} is outside its bounded text contract")
    return value


def project_root(value: str) -> Path:
    path = Path(os.path.abspath(os.path.expanduser(value)))
    try:
        runtime.validate_secure_root(path)
    except (runtime.ContractError, OSError):
        fail("project root is not an accessible race-safe directory")
    return path


def initialize_store(root: Path) -> None:
    for relative in (STORE_BASE, SOURCE_DIR, NORMALIZED_DIR, EXECUTIONS_DIR):
        runtime.ensure_secure_directory(root, relative)


def manifest_relative(execution: str) -> str:
    return f"{EXECUTIONS_DIR}/{execution}/manifest.json"


def _missing_contract_error(error: runtime.ContractError) -> bool:
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, FileNotFoundError):
            return True
        cause = cause.__cause__
    return False


def validate_manifest(value: dict[str, Any], execution: str | None = None) -> None:
    try:
        runtime.validate_model("evidence-manifest", value)
    except runtime.ContractError as error:
        fail(f"invalid local evidence manifest: {error}")
    if execution is not None and value["executionId"] != execution:
        fail("local evidence manifest execution mismatch")
    for item in value["items"]:
        if sanitize_locator(item["sourceLocator"]) != item["sourceLocator"]:
            fail("local evidence manifest contains an unsanitized source locator")
        for field in ("collectionError",):
            if field in item and sanitize_text(item[field]["message"]) != item[field]["message"]:
                fail("local evidence manifest contains unsafe error metadata")
        for gap in item.get("gaps", []):
            if sanitize_text(gap) != gap:
                fail("local evidence manifest contains unsafe gap metadata")


def load_manifest(root: Path, execution: str, *, create: bool) -> tuple[dict[str, Any], bytes | None]:
    relative = manifest_relative(execution)
    try:
        payload = runtime.safe_read_bytes(Path(relative), project_root=root, max_bytes=256 * 1024)
    except runtime.ContractError as error:
        if create and _missing_contract_error(error):
            value = {"schemaVersion": SCHEMA, "executionId": execution, "items": []}
            validate_manifest(value, execution)
            return value, None
        if _missing_contract_error(error):
            fail(f"no evidence manifest for {execution}")
        fail(f"cannot read local evidence manifest: {error}")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"invalid local evidence manifest: {error}")
    if not isinstance(value, dict):
        fail("invalid local evidence manifest: expected an object")
    validate_manifest(value, execution)
    return value, payload


def read_manifest(root: Path, execution: str, *, create: bool) -> dict[str, Any]:
    return load_manifest(root, execution, create=create)[0]


def write_manifest(
    root: Path, execution: str, value: dict[str, Any], *, expected_current: bytes | None,
) -> None:
    value["items"] = sorted(value["items"], key=lambda item: item["evidenceId"])
    validate_manifest(value, execution)
    runtime.atomic_write_bytes(
        root, manifest_relative(execution), canonical(value) + b"\n",
        expected_current=expected_current,
    )


def normalize_sensitive_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def is_sensitive_name(value: str) -> bool:
    normalized = normalize_sensitive_name(value)
    return normalized in SENSITIVE_NAMES or normalized.endswith("token") or normalized.endswith("password") or normalized.endswith("secret")


def redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): (REDACTED if is_sensitive_name(str(key)) else redact_json(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    return value


def _sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.netloc or BAD_PERCENT_RE.search(parsed.query):
            raise ValueError("malformed URI")
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        query = urlencode([
            (key, REDACTED if is_sensitive_name(key) else item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=False)
        ])
        return urlunsplit((parsed.scheme, host + port, parsed.path, query, ""))
    except (UnicodeError, ValueError):
        fail("source URI is malformed")
    raise AssertionError


def sanitize_text(value: str) -> str:
    result = HEADER_RE.sub(lambda match: match.group(1) + REDACTED, value)
    result = ASSIGNMENT_RE.sub(lambda match: match.group(1) + match.group(2) + REDACTED, result)

    def sanitize_embedded_url(match: re.Match[str]) -> str:
        candidate = match.group(0)
        suffix = ""
        while candidate and candidate[-1] in ".),]}":
            suffix = candidate[-1] + suffix
            candidate = candidate[:-1]
        return _sanitize_url(candidate) + suffix

    return URL_RE.sub(sanitize_embedded_url, result)


def sanitize_locator(value: str) -> str:
    bounded_text("source locator", value, 2048, required=True)
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value):
        return _sanitize_url(value)
    return sanitize_text(value)


def media_type(value: str | None, source: str) -> str:
    guessed = (value or mimetypes.guess_type(source)[0] or "application/octet-stream").lower()
    if not re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", guessed):
        fail("media type must be a bounded type/subtype")
    return guessed


def _is_json_media(kind: str) -> bool:
    return kind == "application/json" or kind.endswith("+json")


def _is_unsupported_structured(kind: str) -> bool:
    return kind in {"application/xml", "text/xml", "application/yaml", "text/yaml", "application/x-yaml"} or kind.endswith(("+xml", "+yaml"))


def sanitize_payload(payload: bytes, kind: str) -> bytes:
    if len(payload) > MAX_PAYLOAD_BYTES:
        fail("evidence payload exceeds the 1 GiB contract limit")
    if _is_json_media(kind):
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            fail("declared JSON evidence is not syntactically valid UTF-8 JSON")
        return canonical(redact_json(value))
    if kind == "application/x-www-form-urlencoded":
        try:
            text = payload.decode("utf-8")
            if BAD_PERCENT_RE.search(text):
                raise ValueError("invalid percent escape")
            pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=True)
        except (UnicodeDecodeError, ValueError):
            fail("declared form evidence is malformed")
        return urlencode([(key, REDACTED if is_sensitive_name(key) else value) for key, value in pairs]).encode("utf-8")
    if _is_unsupported_structured(kind):
        fail("structured media type cannot be sanitized safely")
    if kind.startswith("text/") or kind in {"application/http", "message/http"}:
        try:
            return sanitize_text(payload.decode("utf-8")).encode("utf-8")
        except UnicodeDecodeError:
            fail("text evidence must be valid UTF-8")
    # Binary evidence is opaque, but ASCII credential carriers are still
    # removed before hashing or persistence.
    return sanitize_text(payload.decode("latin-1")).encode("latin-1")


def read_input(root: Path, path_text: str) -> bytes:
    bounded_text("input path", path_text, 4096, required=True)
    try:
        return runtime.safe_read_bytes(Path(path_text), project_root=root, max_bytes=MAX_PAYLOAD_BYTES)
    except runtime.ContractError:
        fail("cannot read evidence input through the authorized workspace")
    raise AssertionError


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def blob_relative(representation: str, content_digest: str) -> str:
    return f"{STORE_BASE}/payloads/{representation}/{content_digest.split(':', 1)[1]}.bin"


def parse_range(value: str, *, length: int) -> tuple[int, int]:
    match = re.fullmatch(r"([1-9][0-9]*):([1-9][0-9]*)", value)
    if not match:
        fail("range must be non-empty A:B with positive one-based bounds")
    start, end = int(match.group(1)), int(match.group(2))
    if start > end:
        fail("range start must not exceed end")
    if end - start + 1 > MAX_LINE_SPAN:
        fail("requested range exceeds bounded span")
    if end > length:
        fail("requested range is outside available evidence")
    if start == 1 and end == length:
        fail("range selectors must be a strict subset of the payload")
    return start, end


def bounded_max(value: str | None) -> int:
    if value is None:
        return MAX_OUTPUT_BYTES
    if not value.isdigit() or int(value) < 1 or int(value) > MAX_OUTPUT_BYTES:
        fail(f"max bytes must be 1..{MAX_OUTPUT_BYTES}")
    return int(value)


def is_textual(item: dict[str, Any], payload: bytes) -> bool:
    kind = item["mediaType"]
    if kind.startswith("text/") or _is_json_media(kind) or kind in {"application/x-www-form-urlencoded", "application/http", "message/http"}:
        try:
            payload.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return False


def read_blob(root: Path, representation: dict[str, Any]) -> bytes:
    try:
        payload = runtime.safe_read_bytes(
            Path(representation["localPath"]), project_root=root, max_bytes=MAX_PAYLOAD_BYTES,
        )
    except runtime.ContractError as error:
        fail(f"cannot read evidence blob: {error}")
    if len(payload) != representation["byteSize"] or digest(payload) != representation["digest"]:
        fail("evidence blob collision or tamper detected")
    return payload


def verify_item_blobs(root: Path, item: dict[str, Any]) -> None:
    if item["collectionStatus"] in {"complete", "partial"}:
        read_blob(root, item["sourcePayload"])
        read_blob(root, item["normalizedRepresentation"])


def list_executions(root: Path) -> list[str]:
    try:
        names = runtime.safe_list_directory(root, EXECUTIONS_DIR)
    except runtime.ContractError as error:
        fail(f"cannot enumerate evidence manifests: {error}")
    executions = []
    for name in names:
        if not EXECUTION_RE.fullmatch(name):
            fail("evidence execution directory contains an invalid entry")
        executions.append(name)
    return executions


def find_item(root: Path, evidence_id: str, execution: str | None = None) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    executions = [require_execution(execution)] if execution else list_executions(root)
    for candidate_execution in executions:
        manifest = read_manifest(root, candidate_execution, create=False)
        candidates.extend(item for item in manifest["items"] if item["evidenceId"] == evidence_id)
    if not candidates:
        fail(f"unknown evidence ID: {evidence_id}")
    baseline = canonical(candidates[0])
    if any(canonical(candidate) != baseline for candidate in candidates[1:]):
        fail("evidence ID has conflicting local metadata")
    return candidates[0]


def provenance(item: dict[str, Any]) -> dict[str, Any]:
    fields = ("evidenceId", "kind", "sourceSystem", "sourceLocator", "digest", "revisionId", "collectionStatus")
    return {key: item.get(key) for key in fields}


def error_metadata(args: argparse.Namespace, status: str) -> tuple[dict[str, str] | None, list[str]]:
    code = args.error_code
    message = args.error_message
    gaps = args.gap
    if args.unavailable and code is None and message is None:
        code, message = "source_unavailable", "Source unavailable"
    if status == "complete":
        if code is not None or message is not None or gaps:
            fail("complete collection cannot include error or gap metadata")
        return None, []
    if code is None or message is None:
        fail(f"{status} collection requires --error-code and --error-message")
    require_identifier("error code", code)
    safe_message = sanitize_text(bounded_text("error message", message, 256, required=True) or "")
    safe_gaps = [sanitize_text(bounded_text("gap", gap, 256, required=True) or "") for gap in gaps]
    if len(safe_gaps) != len(set(safe_gaps)) or len(safe_gaps) > 16:
        fail("gaps must be unique and at most 16")
    if status == "partial" and not safe_gaps:
        fail("partial collection requires at least one explicit --gap")
    if status in {"failed", "unavailable"} and safe_gaps:
        fail(f"{status} collection cannot include payload gap metadata")
    return {"code": code, "message": safe_message}, safe_gaps


def _record_without_timestamp(item: dict[str, Any]) -> bytes:
    copy = dict(item)
    copy.pop("collectedAt", None)
    return canonical(copy)


def collect(args: argparse.Namespace) -> None:
    root = project_root(args.project_root)
    execution = require_execution(args.execution)
    kind_name = require_identifier("kind", args.kind)
    source_system = require_identifier("source system", args.source_system)
    if args.sensitivity not in SENSITIVITIES:
        fail("unsupported sensitivity")
    if not VERSION_RE.fullmatch(args.normalization_version):
        fail("normalization version is invalid")
    revision_id = bounded_text("revisionId", args.revision_id, 256)
    relationships = [require_evidence(value) for value in args.relationship]
    if len(set(relationships)) != len(relationships) or len(relationships) > 128:
        fail("relationships must be unique and at most 128")
    status = "unavailable" if args.unavailable else args.status
    if status not in STATUSES:
        fail("unsupported collection status")
    locator = sanitize_locator(args.source_locator)
    declared_media = media_type(args.media_type, args.input or locator)
    collection_error, gaps = error_metadata(args, status)

    has_payload = status in {"complete", "partial"}
    if has_payload and not args.input:
        fail(f"{status} collection requires --input")
    if not has_payload and (args.input or args.normalized_input):
        fail(f"{status} collection cannot include payload input")

    source: bytes | None = None
    normalized: bytes | None = None
    item: dict[str, Any] = {
        "kind": kind_name,
        "sourceSystem": source_system,
        "sourceLocator": locator,
        "collectedAt": utc_now(),
        "mediaType": declared_media,
        "sensitivity": args.sensitivity,
        "normalizationVersion": args.normalization_version,
        "relationships": relationships,
        "collectionStatus": status,
        "revisionId": revision_id,
    }
    if has_payload:
        source = sanitize_payload(read_input(root, args.input), declared_media)
        normalized_input = read_input(root, args.normalized_input) if args.normalized_input else source.replace(b"\r\n", b"\n")
        normalized = sanitize_payload(normalized_input, declared_media)
        raw_digest, normalized_digest = digest(source), digest(normalized)
        source_representation = {
            "localPath": blob_relative("source", raw_digest), "digest": raw_digest, "byteSize": len(source),
        }
        normalized_representation = {
            "localPath": blob_relative("normalized", normalized_digest), "digest": normalized_digest, "byteSize": len(normalized),
        }
        item.update({
            "digest": raw_digest,
            "byteSize": len(normalized),
            "localPath": normalized_representation["localPath"],
            "sourcePayload": source_representation,
            "normalizedRepresentation": normalized_representation,
        })
    if collection_error is not None:
        item["collectionError"] = collection_error
    if gaps:
        item["gaps"] = gaps
    item["evidenceId"] = runtime.evidence_record_id(execution, item)

    # All caller input and the prospective complete manifest are validated
    # before any evidence byte is written.
    initialize_store(root)
    runtime.ensure_secure_directory(root, f"{EXECUTIONS_DIR}/{execution}")
    manifest, manifest_payload = load_manifest(root, execution, create=True)
    existing = next((value for value in manifest["items"] if value["evidenceId"] == item["evidenceId"]), None)
    if existing is None:
        prospective = {**manifest, "items": [*manifest["items"], item]}
        validate_manifest(prospective, execution)
    else:
        if _record_without_timestamp(existing) != _record_without_timestamp(item):
            fail("evidence record identity collision or manifest tamper detected")
        verify_item_blobs(root, existing)
        emit({"evidenceId": item["evidenceId"], "collectionStatus": existing["collectionStatus"], "deduplicated": True})
        return

    if source is not None and normalized is not None:
        runtime.atomic_write_bytes(root, item["sourcePayload"]["localPath"], source, immutable=True)
        runtime.atomic_write_bytes(root, item["normalizedRepresentation"]["localPath"], normalized, immutable=True)
    manifest["items"].append(item)
    write_manifest(root, execution, manifest, expected_current=manifest_payload)
    emit({"evidenceId": item["evidenceId"], "collectionStatus": status, "deduplicated": False})


def list_items(args: argparse.Namespace) -> None:
    root = project_root(args.project_root)
    execution = require_execution(args.execution)
    emit(read_manifest(root, execution, create=False))


def show(args: argparse.Namespace) -> None:
    root = project_root(args.project_root)
    item = find_item(root, require_evidence(args.evidence_id), args.execution)
    verify_item_blobs(root, item)
    emit(item)


def _load_retrievable(root: Path, evidence_id: str, execution: str | None) -> tuple[dict[str, Any], bytes]:
    item = find_item(root, evidence_id, execution)
    if item["collectionStatus"] != "complete":
        fail(f"{item['collectionStatus']} evidence has no retrievable complete payload")
    return item, read_blob(root, item["normalizedRepresentation"])


def render_extract(item: dict[str, Any], selector: str, encoding: str, content: bytes, limit: int) -> None:
    if len(content) > limit:
        fail("requested extract exceeds max bytes")
    rendered: Any = base64.b64encode(content).decode("ascii") if encoding == "base64" else content.decode("utf-8")
    emit({"provenance": provenance(item), "selector": selector, "encoding": encoding, "byteSize": len(content), "content": rendered})


def read(args: argparse.Namespace) -> None:
    root = project_root(args.project_root)
    item, payload = _load_retrievable(root, require_evidence(args.evidence_id), args.execution)
    limit = bounded_max(args.max_bytes)
    if not is_textual(item, payload):
        fail("binary evidence requires an explicit byte extract")
    if args.lines:
        lines = payload.decode("utf-8").splitlines(keepends=True)
        start, end = parse_range(args.lines, length=len(lines))
        content = "".join(lines[start - 1:end]).encode("utf-8")
        render_extract(item, f"lines:{args.lines}", "utf-8", content, limit)
        return
    if len(payload) > MAX_OUTPUT_BYTES or len(payload) > limit:
        fail("full read exceeds the bounded maximum; use an explicit strict-subset extract")
    sys.stdout.buffer.write(payload)


def decode_pointer_token(raw: str) -> str:
    output, index = [], 0
    while index < len(raw):
        if raw[index] != "~":
            output.append(raw[index])
            index += 1
            continue
        if index + 1 >= len(raw) or raw[index + 1] not in {"0", "1"}:
            fail("JSON pointer contains an invalid escape")
        output.append("~" if raw[index + 1] == "0" else "/")
        index += 2
    return "".join(output)


def extract(args: argparse.Namespace) -> None:
    root = project_root(args.project_root)
    item, payload = _load_retrievable(root, require_evidence(args.evidence_id), args.execution)
    limit = bounded_max(args.max_bytes)
    selector = args.selector
    if selector.startswith("lines:"):
        if not is_textual(item, payload):
            fail("line extraction requires UTF-8 text evidence")
        lines = payload.decode("utf-8").splitlines(keepends=True)
        start, end = parse_range(selector[6:], length=len(lines))
        content = "".join(lines[start - 1:end]).encode("utf-8")
        encoding = "utf-8"
    elif selector.startswith("json:"):
        if not _is_json_media(item["mediaType"]):
            fail("JSON extraction requires JSON evidence")
        pointer = selector[5:]
        if not pointer.startswith("/"):
            fail("JSON selector must be a non-root RFC 6901 pointer")
        try:
            value: Any = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            fail("invalid JSON evidence")
        for raw_token in pointer[1:].split("/"):
            token = decode_pointer_token(raw_token)
            if isinstance(value, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", token):
                    fail("JSON array index must be canonical without leading zero")
                index = int(token)
                if index >= len(value):
                    fail("JSON selector did not resolve")
                value = value[index]
            elif isinstance(value, dict) and token in value:
                value = value[token]
            else:
                fail("JSON selector did not resolve")
        content = canonical(value)
        encoding = "json"
    elif selector.startswith("bytes:"):
        start, end = parse_range(selector[6:], length=len(payload))
        content = payload[start - 1:end]
        encoding = "base64"
    else:
        fail("unsupported selector; use lines:A:B, json:/pointer, or bytes:A:B")
    render_extract(item, selector, encoding, content, limit)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(add_help=False)
    result.add_argument("--project-root", default=os.getcwd())
    sub = result.add_subparsers(dest="command", required=True)
    collect_parser = sub.add_parser("collect")
    collect_parser.add_argument("--execution", required=True)
    collect_parser.add_argument("--kind", required=True)
    collect_parser.add_argument("--source-system", required=True)
    collect_parser.add_argument("--source-locator", required=True)
    collect_parser.add_argument("--input")
    collect_parser.add_argument("--normalized-input")
    collect_parser.add_argument("--media-type")
    collect_parser.add_argument("--sensitivity", default="internal")
    collect_parser.add_argument("--normalization-version", default="v1")
    collect_parser.add_argument("--revision-id")
    collect_parser.add_argument("--relationship", action="append", default=[])
    collect_parser.add_argument("--status", choices=sorted(STATUSES), default="complete")
    collect_parser.add_argument("--error-code")
    collect_parser.add_argument("--error-message")
    collect_parser.add_argument("--gap", action="append", default=[])
    collect_parser.add_argument("--unavailable", action="store_true")
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--execution", required=True)
    for name in ("show", "read", "extract"):
        command = sub.add_parser(name)
        command.add_argument("evidence_id")
        command.add_argument("--execution")
    sub.choices["show"].add_argument("--metadata", action="store_true", required=True)
    sub.choices["read"].add_argument("--lines")
    sub.choices["read"].add_argument("--max-bytes")
    sub.choices["extract"].add_argument("--selector", required=True)
    sub.choices["extract"].add_argument("--max-bytes")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        {"collect": collect, "list": list_items, "show": show, "read": read, "extract": extract}[args.command](args)
    except runtime.RollbackFailure as error:
        print(json.dumps(error.as_dict(), sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2
    except (EvidenceError, runtime.ContractError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
