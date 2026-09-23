#!/usr/bin/env python3
"""CTX-09B deterministic comparison of CTX-09A registered local snapshots.

No provider APIs, runtime execution, free-text interpretation or authority.
Unsupported formats and insufficient evidence never establish equivalence.
"""
import sys
sys.dont_write_bytecode = True

import argparse
import errno
import hashlib
import importlib.util
import json
import os
import secrets
import signal
import stat
from pathlib import Path

REPO = Path(__file__).absolute().parents[2]
SPEC = importlib.util.spec_from_file_location("ctx09b_mode_io", REPO / "scripts/context-runtime-mode.py")
mode = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mode)
runtime = mode.runtime
INPUT_VERSION = "mana.context-runtime.semantic-comparison-input/v1"
REPORT_VERSION = "mana.context-runtime.semantic-comparison/v1"
INPUT_SCHEMA = "semantic-comparison-input-v1.schema.json"
REPORT_SCHEMA = "semantic-comparison-v1.schema.json"
REPORT_FILE = "semantic-comparison-v1.json"
MAX_INPUT = 256 * 1024
MAX_REPORT = 1024 * 1024
DIMENSIONS = tuple(sorted(("status", "blockers", "warnings", "evidenceReferences", "requirementCoverage",
                           "approvalGates", "activatedRiskDomains", "highRiskEscalation", "unresolvedQuestions",
                           "artifactCompleteness", "humanUsefulnessDisposition", "externalWritePolicy")))
_TEST_HOOK = None  # Import-only; never environment/CLI authority.


def sync(point):
    if _TEST_HOOK is not None:
        _TEST_HOOK(point)


def strict_json(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise runtime.ContractError("duplicate JSON field")
            result[key] = value
        return result
    def nonfinite(value):
        raise runtime.ContractError("non-finite JSON number")
    return json.loads(payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)


class Contracts(runtime.Evaluator):
    """Only two fixed, host-installed schemas; no input-selected file/ref IO."""

    def __init__(self):
        super().__init__()
        with mode.HostRoot(str(REPO)) as root:
            for name in (INPUT_SCHEMA, REPORT_SCHEMA):
                _, payload = mode.project_file(root, "contracts/context-runtime/" + name,
                                               with_bytes=True, max_bytes=64 * 1024)
                self.documents[REPO / "contracts/context-runtime" / name] = strict_json(payload)
            root.attest()

    def load(self, path):
        # Evaluator resolves only the fixed cached schemas and their fragments.
        if path not in self.documents:
            raise runtime.ContractError("comparison schema reference is not host-installed")
        return self.documents[path]

    def validate(self, value, name):
        document = REPO / "contracts/context-runtime" / name
        if self.evaluate(value, self.load(document), document):
            # Never echo labels, source bodies, values or user field names.
            raise runtime.ContractError("comparison contract validation failed")


def digest(value):
    return hashlib.sha256(runtime.canonical_bytes(value)).hexdigest()


def semantic_value(value):
    # Closed contract marks only these arrays as sets. No prose normalization.
    if isinstance(value, dict):
        return {key: sorted(item) if key in {"requiredEvidence", "approvedActionKeys"}
                else semantic_value(item) for key, item in value.items()}
    return value


def semantic_key(name, record):
    value = record["value"]
    if name in {"blockers", "warnings", "unresolvedQuestions"}:
        identity = {"subject": value["subject"], "predicate": value["predicate"]}
    elif name == "evidenceReferences":
        identity = value["sourceKey"]
    else:
        identity = record["key"]
    return digest({"dimension": name, "identity": identity})


def native_input(payload, contracts):
    try:
        value = strict_json(payload)
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        # Free-text/binary artifacts remain unsupported, even if byte-identical.
        # Malformed declared native JSON is a contract error, not an empty input.
        if INPUT_VERSION.encode() in payload:
            raise runtime.ContractError("invalid declared comparison input") from None
        return None, "unsupported-format"
    if not isinstance(value, dict) or value.get("schemaVersion") != INPUT_VERSION:
        return None, "unsupported-contract"
    contracts.validate(value, INPUT_SCHEMA)
    dimensions = value["dimensions"]
    for name, section in dimensions.items():
        coverage, records = section["coverage"], section["records"]
        if coverage == "not-applicable" and (name != "humanUsefulnessDisposition" or records or section["gaps"]):
            raise runtime.ContractError("invalid not-applicable dimension")
        if coverage == "unavailable" and records:
            raise runtime.ContractError("unavailable dimension cannot carry observations")
        if name in {"status", "externalWritePolicy", "humanUsefulnessDisposition"} and coverage == "complete":
            if len(records) != 1 or records[0]["key"] != name:
                raise runtime.ContractError("complete singleton dimension requires its canonical key")
        keys = [record["key"] for record in records]
        atoms = [semantic_key(name, record) for record in records]
        if len(set(keys)) != len(keys) or len(set(atoms)) != len(atoms):
            raise runtime.ContractError("duplicate comparison observation identity")
    return value, None


def observations(name, value):
    section = value["dimensions"].get(name) if value else None
    return {semantic_key(name, record): (record, index)
            for index, record in enumerate(section["records"])} if section else {}


def global_claim_index(value):
    """Structured assertions only; presentation dimension and labels are inert."""
    claims = {}
    for name in sorted(DIMENSIONS):
        section = value["dimensions"].get(name) if value else None
        for index, record in enumerate(section["records"] if section else []):
            atom = record["value"]
            if not isinstance(atom, dict) or not {"subject", "predicate", "stance"}.issubset(atom):
                continue
            identity = {"subject": atom["subject"], "predicate": atom["predicate"]}
            key = digest(identity)
            claims.setdefault(key, []).append((name, record, index))
    return claims


def internal_conflicts(inputs):
    conflicts = []
    for side in ("legacy", "v2"):
        evidence = evidence_index(inputs[side])
        for key, members in sorted(global_claim_index(inputs[side]).items()):
            stances = {record["value"]["stance"] for _, record, _ in members}
            declared = any("contradictory-evidence" in record["uncertainty"] for _, record, _ in members)
            if not ({"affirmed", "denied"}.issubset(stances) or declared):
                continue
            points = [point(name, record, index, inputs[side], evidence)[0]
                      for name, record, index in members]
            conflicts.append({"side": side, "semanticKey": key, "stances": sorted(stances),
                              "declaredThroughUncertainty": declared,
                              "reason": "unresolved_internal_conflict", "observations": points})
    return conflicts


def evidence_index(value):
    section = value["dimensions"].get("evidenceReferences") if value else None
    return {record["key"]: (record, index) for index, record in enumerate(section["records"])} if section else {}


def evidence_usable(value, record):
    section = value["dimensions"].get("evidenceReferences")
    metadata = record["value"]
    return (section is not None and section["coverage"] == "complete" and not section["gaps"]
            and not record["uncertainty"] and metadata["collectionStatus"] == "complete"
            and metadata["revision"] is not None and metadata["sha256"] is not None)


def contains_unknown(value):
    if isinstance(value, dict):
        # Only typed disposition fields carry uncertainty sentinels. Identity
        # tokens (including a component literally named "unknown") are opaque.
        return any(value.get(key) in {"unknown", "uncertain", "undecided"}
                   for key in ("stance", "validation", "state", "riskLevel", "status", "collectionStatus"))
    return value in {"unknown", "uncertain", "undecided"} if isinstance(value, str) else False


def point(name, record, index, source, evidence):
    refs = sorted(record["evidenceRefs"])
    reasons = set(record["uncertainty"])
    if reasons:
        reasons.add("uncertain-observation")
    value = record["value"]
    if contains_unknown(value):
        reasons.add("unknown-value")
    if name == "status" and value in {"partial", "needs-more-evidence", "needs-model-escalation"}:
        reasons.add("unknown-value")
    if name == "requirementCoverage" and value == "partial":
        reasons.add("unknown-value")
    if name == "unresolvedQuestions" and value["state"] == "open":
        reasons.add("open-question")
    if name == "artifactCompleteness" and value["state"] != "present":
        reasons.add("artifact-incomplete")
    if name == "evidenceReferences" and not evidence_usable(source, record):
        reasons.add("evidence-incomplete")
    if name == "highRiskEscalation" and value["required"]:
        if value["status"] != "performed":
            reasons.add("required-escalation-unavailable")
        if value["modelTier"] == "unspecified":
            reasons.add("required-escalation-unspecified")
    if name == "activatedRiskDomains" and value["modelTier"] == "unspecified":
        reasons.add("required-escalation-unspecified")
    needs_proof = (name in {"blockers", "warnings"}
                   or (name == "approvalGates" and value["state"] == "completed")
                   or (name == "highRiskEscalation" and value["required"])
                   or (name == "activatedRiskDomains" and value["state"] == "active" and value["riskLevel"] == "high")
                   or (name == "unresolvedQuestions" and value["state"] == "resolved"))
    if needs_proof and not refs:
        reasons.add("provenance-unavailable")
    resolved = []
    for ref in refs:
        found = evidence.get(ref)
        if found is None:
            reasons.add("provenance-unavailable")
            continue
        item, position = found
        resolved.append({"recordId": ref, "pointer": f"/dimensions/evidenceReferences/records/{position}",
                         "metadata": item["value"], "uncertainty": sorted(item["uncertainty"])})
        if not evidence_usable(source, item):
            reasons.add("provenance-unavailable")
    if needs_proof and "provenance-unavailable" in reasons:
        reasons.add("high-risk-evidence-unavailable" if name in {"activatedRiskDomains", "highRiskEscalation"}
                    else "provenance-unavailable")
    # requiredEvidence is a declared set of evidence source identities, not prose.
    if name == "unresolvedQuestions" and value["state"] == "resolved":
        if not set(value["requiredEvidence"]).issubset({item["metadata"]["sourceKey"] for item in resolved}):
            reasons.add("provenance-unavailable")
    result = {"recordId": record["key"], "pointer": f"/dimensions/{name}/records/{index}",
              "value": semantic_value(value), "evidenceRefs": refs, "evidence": resolved,
              "uncertainty": sorted(record["uncertainty"])}
    proof = sorted((item["metadata"] for item in resolved), key=runtime.canonical_bytes)
    return result, reasons, proof


def outcome(statuses, incomplete):
    if "different" in statuses:
        return "different"
    return "indeterminate" if incomplete or "indeterminate" in statuses else "equivalent"


def compare_dimension(name, inputs, input_reasons):
    sections = {side: value["dimensions"].get(name) if value else None for side, value in inputs.items()}
    reasons = set(input_reasons)
    coverages = {side: section["coverage"] if section else "missing" for side, section in sections.items()}
    gaps = {side: sorted(section["gaps"]) if section else [] for side, section in sections.items()}
    for side, section in sections.items():
        if section is None:
            reasons.add("dimension-missing")
        elif section["coverage"] not in {"complete", "not-applicable"}:
            reasons.add("coverage-incomplete")
        if name == "artifactCompleteness" and section is not None and not section["records"]:
            reasons.add("artifact-incomplete")
        if gaps[side]:
            reasons.update(gaps[side])
            reasons.add("declared-gap")
    optional_absent = name == "humanUsefulnessDisposition" and set(coverages.values()) == {"not-applicable"}
    if "not-applicable" in coverages.values() and not optional_absent:
        reasons.add("coverage-incomplete")
    observed = {side: observations(name, value) for side, value in inputs.items()}
    evidence = {side: evidence_index(value) for side, value in inputs.items()}
    records, statuses = [], []
    incomplete = bool(reasons)
    for key in sorted(set(observed["legacy"]) | set(observed["v2"])):
        points, proof, item_reasons = {}, {}, set()
        for side in ("legacy", "v2"):
            if key in observed[side]:
                record, index = observed[side][key]
                points[side], local_reasons, proof[side] = point(name, record, index, inputs[side], evidence[side])
                item_reasons.update(local_reasons)
            else:
                points[side] = None
        unknown = bool(item_reasons) or bool(input_reasons)
        incomplete = incomplete or unknown
        if points["legacy"] is None or points["v2"] is None:
            item_reasons.add("one-sided-observation")
            status = "indeterminate" if reasons or unknown else "different"
        else:
            different = points["legacy"]["value"] != points["v2"]["value"]
            provenance_different = proof["legacy"] != proof["v2"]
            if different:
                item_reasons.add("observed-value-difference")
            if provenance_different:
                item_reasons.add("provenance-difference")
            if unknown:
                status = "indeterminate"
            elif different or provenance_different:
                status = "different"  # Known paired changes survive incomplete collection coverage.
            elif reasons:
                status = "indeterminate"
                item_reasons.update(reasons)
            else:
                status = "equivalent"
        records.append({"semanticKey": key, "status": status, "reasons": sorted(item_reasons), **points})
        statuses.append(status)
    return {"name": name, "status": outcome(statuses, incomplete), "complete": not incomplete,
            "coverage": coverages, "gaps": gaps, "reasons": sorted(reasons), "records": records}


def compare(inputs, input_reasons, registration, sources, execution_id):
    reasons = set(reason for reason in input_reasons.values() if reason)
    # Native headers are declarations, bound independently to each reverified
    # host receipt. Agreement between two foreign declarations is insufficient.
    for side, value in inputs.items():
        if value is not None:
            for field, reason in (("profileId", "profile-mismatch"), ("targetKey", "target-mismatch")):
                if value[field] != sources[side][field]:
                    reasons.add(reason)
    conflicts = internal_conflicts(inputs)
    if conflicts:
        reasons.add("unresolved_internal_conflict")
    if all(inputs.values()):
        if inputs["legacy"]["profileId"] != inputs["v2"]["profileId"]:
            reasons.add("profile-mismatch")
        if inputs["legacy"]["targetKey"] != inputs["v2"]["targetKey"]:
            reasons.add("target-mismatch")
    dimensions = [compare_dimension(name, inputs, reasons) for name in DIMENSIONS]
    complete = all(item["complete"] for item in dimensions)
    status = "indeterminate" if conflicts else outcome([item["status"] for item in dimensions], not complete)
    byte_identical = sources["legacy"]["sha256"] == sources["v2"]["sha256"]
    return {"schemaVersion": REPORT_VERSION, "executionId": execution_id, "registration": registration,
            "sources": sources, "authority": "none", "permissionGrant": "none", "externalActions": "disabled",
            "executedRuntimes": [], "equivalenceScope": "declared-structured-semantics-v1",
            "provenanceScope": "registered-artifact-bytes-and-declared-evidence-metadata",
            "humanReviewRequired": True, "nonDegradation": "not-established",
            "status": status, "complete": complete, "byteIdentical": byte_identical,
            "representationOnly": status == "equivalent" and not byte_identical,
            "reasons": sorted(reasons), "conflicts": conflicts, "dimensions": dimensions}


def registration(root, execution_id):
    if not mode.EXECUTION_ID.fullmatch(execution_id):
        raise runtime.ContractError("invalid registration identity")
    path = f"{mode.NAMESPACE}/{execution_id}/mode-plan-v1.json"
    metadata, payload = mode.project_file(root, path, with_bytes=True, private=True, max_bytes=16 * 1024)
    value = strict_json(payload)
    expected = {"schemaVersion": "mana.context-runtime.mode-plan/v1", "executionId": execution_id,
                "mode": "compare", "authority": "none", "externalActions": "disabled", "permissionGrant": "none",
                "comparison": "deferred-ctx-09b"}
    if (not isinstance(value, dict) or set(value) != set(expected) | {"artifacts"}
            or any(value.get(key) != item for key, item in expected.items())
            or not isinstance(value["artifacts"], dict) or set(value["artifacts"]) != {"legacy", "v2"}
            or mode.canonical(value) != payload):
        raise runtime.ContractError("requires canonical CTX-09A compare registration")
    for source in value["artifacts"].values():
        if (not isinstance(source, dict) or set(source) != {"path", "sha256", "fileInstance", "producerRuntime",
                                                         "producerReceiptDigest", "profileId", "targetKey", "executionVersion"}
                or not isinstance(source["path"], str) or len(source["path"]) > 512
                or not isinstance(source["sha256"], str) or not mode.re.fullmatch("[a-f0-9]{64}", source["sha256"])):
            raise runtime.ContractError("invalid registered source identity")
        mode.relative_path(source["path"])
        mode.validate_file_instance(source["fileInstance"])
    return metadata, value


def publish(root, parent, components, payload):
    """Atomic no-replace file publication in the existing private registration.

    Held descriptors and identity checks keep handled failures local. As in
    CTX-09A, SIGKILL/power loss or hostile same-UID theft requires host recovery.
    """
    primitives = runtime._require_rename_primitives()
    root.attest_directory(components, parent)
    mode.absent(parent, REPORT_FILE)
    name = ".semantic-comparison.stage." + secrets.token_hex(16)
    fd, expected, published = None, None, False
    try:
        old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        try:
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | root.nofollow, 0o600, dir_fd=parent)
            expected = mode.identity(fd)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
        os.fchmod(fd, 0o600)
        offset = 0
        while offset < len(payload):
            sync("before-stage-write")
            count = os.write(fd, payload[offset:])
            if count <= 0:
                raise OSError(errno.EIO, "short comparison write")
            offset += count
        os.fsync(fd)

        def attest(name_to_check):
            metadata = os.fstat(fd)
            if (not runtime._verify_identity(parent, name_to_check, expected)
                    or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.getuid()):
                raise runtime.ContractError("comparison publication identity changed")
            os.lseek(fd, 0, os.SEEK_SET)
            actual = bytearray()
            while len(actual) <= len(payload):
                chunk = os.read(fd, min(65536, len(payload) + 1 - len(actual)))
                if not chunk:
                    break
                actual.extend(chunk)
            if bytes(actual) != payload:
                raise runtime.ContractError("comparison publication bytes changed")
            after = os.fstat(fd)
            if (any(getattr(metadata, field) != getattr(after, field) for field in
                    ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"))
                    or not runtime._verify_identity(parent, name_to_check, expected)):
                raise runtime.ContractError("comparison publication changed during attestation")

        sync("before-publication")
        root.attest_directory(components, parent)
        attest(name)
        primitives.noreplace(parent, name, parent, REPORT_FILE)
        published = True
        sync("after-publication")
        root.attest_directory(components, parent)
        attest(REPORT_FILE)
        os.fsync(parent)
        sync("before-commit")
        root.attest_directory(components, parent)
        attest(REPORT_FILE)
    except BaseException:
        if published:
            if not runtime._verify_identity(parent, REPORT_FILE, expected):
                raise runtime.ContractError("comparison rollback identity changed; host recovery required") from None
            primitives.noreplace(parent, REPORT_FILE, parent, name)
            published = False
        raise
    finally:
        try:
            if not published and expected is not None and runtime._verify_identity(parent, name, expected):
                os.unlink(name, dir_fd=parent)
                os.fsync(parent)
        finally:
            if fd is not None:
                os.close(fd)


def run(project_root, execution_id, write_report=False):
    contracts = Contracts()
    with mode.HostRoot(project_root) as root:
        registered, plan = registration(root, execution_id)
        sources, inputs, reasons = {}, {}, {}
        for side in ("legacy", "v2"):
            expected = plan["artifacts"][side]
            sources[side], payload = mode.producer_source(root, execution_id, expected["path"], side,
                                                        profile_id=expected["profileId"], target_key=expected["targetKey"],
                                                        execution_version=expected["executionVersion"],
                                                        with_bytes=True, max_bytes=MAX_INPUT)
            if sources[side] != plan["artifacts"][side]:
                raise runtime.ContractError("registered artifact digest mismatch")
            inputs[side], reasons[side] = native_input(payload, contracts)
        for side, expected in sources.items():
            current = mode.producer_source(root, execution_id, expected["path"], side,
                                           profile_id=expected["profileId"], target_key=expected["targetKey"],
                                           execution_version=expected["executionVersion"], max_bytes=MAX_INPUT)
            if current != expected:
                raise runtime.ContractError("producer binding changed before comparison")
        result = compare(inputs, reasons, registered, sources, execution_id)
        contracts.validate(result, REPORT_SCHEMA)
        payload = mode.canonical(result)
        if len(payload) > MAX_REPORT:
            raise runtime.ContractError("comparison report exceeds byte limit")
        root.attest()
        if write_report:
            components = mode.NAMESPACE.split("/") + [execution_id]
            with root.directory_fd(components) as parent, mode.publication_signals():
                publish(root, parent, components, payload)
        return payload


def main():
    parser = argparse.ArgumentParser(description="CTX-09B offline, non-authoritative semantic diagnostic")
    parser.add_argument("execution_id", help="existing CTX-09A compare registration")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--write-report", action="store_true", help="atomically persist a private local diagnostic")
    args = parser.parse_args()
    sys.stdout.buffer.write(run(args.project_root, args.execution_id, args.write_report))
    return 0  # Different/indeterminate are diagnostics, never release-gate PASS.


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (runtime.ContractError, OSError, UnicodeError, ValueError, RecursionError):
        print("ERROR: local semantic comparison rejected; no authoritative result", file=sys.stderr)
        raise SystemExit(2)
