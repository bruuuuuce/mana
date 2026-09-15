#!/usr/bin/env python3
"""CTX-09C-R1A canonical host input; payloads are never delivery artifacts.

The host builds a packet once. Consumers read its canonical bytes through a
private capsule; they must not reopen the sources named in the snapshot.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
import copy
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = "mana.context-runtime.shared-shadow-input/v1"
MAX_BYTES = 24 * 1024 * 1024
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


budget = load("ctx09c_input_budget", "context-budget.py")
runtime = budget.runtime
Error = runtime.ContractError


def canonical(value):
    return runtime.canonical_bytes(value) + b"\n"


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def policy_execution(comparison_id):
    return comparison_id if comparison_id.startswith("execution-") else "execution-comparison-" + digest(comparison_id.encode())[:32]


def argv_bytes(argv):
    if not argv or any(not isinstance(item, str) or "\x00" in item for item in argv):
        raise Error("invalid host argv")
    # sys.argv is already an array: flags are data, including --project-root.
    return canonical(argv)


def identities(comparison_id):
    if not isinstance(comparison_id, str) or ID.fullmatch(comparison_id) is None:
        raise Error("invalid comparison identity")
    suffix = digest(comparison_id.encode())[:32]
    legacy, shadow = "execution-legacy-" + suffix, "execution-shadow-" + suffix
    base = f".mana/runtime/shadows/{comparison_id}"
    return {
        "comparisonExecutionId": comparison_id,
        "legacyExecutionId": legacy, "shadowExecutionId": shadow,
        "executionVersion": 1,
        "legacyProducerId": legacy, "shadowProducerId": shadow,
        "legacyRunRoot": f".mana/runtime/runs/{legacy}",
        "legacyMetricsRoot": f".mana/runtime/metrics/{legacy}",
        "shadowRunRoot": f"{base}/runs/{shadow}",
        "shadowMetricsRoot": f"{base}/runs/{shadow}/.mana/runtime/metrics/{shadow}",
        "legacyLock": f".mana/runtime/runs/{legacy}/.phase-run.lock",
        "shadowLock": f"{base}/locks/{shadow}.lock",
        "legacyInvocationId": legacy + "-invocation-1",
        "shadowInvocationId": shadow + "-invocation-1",
    }


def _workspace_manifest_identity(payload):
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise Error("workspace manifest is not UTF-8") from error
    observed = {}
    for key in ("workspace_type", "workspace_id"):
        values = re.findall(rf"(?m)^{key}:[ ]*(.*?)[ ]*$", text)
        if len(values) != 1:
            raise Error("workspace manifest identity is incomplete")
        observed[key] = values[0].strip('"')
    if observed["workspace_type"] not in {"feature", "session"} or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", observed["workspace_id"]) is None:
        raise Error("workspace manifest identity is invalid")
    identity = {"identityVersion": "mana.context-runtime.workspace-identity/v1",
                "workspaceKind": observed["workspace_type"],
                "workspaceName": observed["workspace_id"]}
    return "W-" + digest(runtime.canonical_bytes(identity))


def _packet_digest(packet):
    projection = copy.deepcopy(packet)
    projection.pop("inputPacketDigest", None)
    return digest(canonical(projection))


def _evidence_records(execution_id, workspace_id, evidence):
    records, snapshot = [], []
    for ordinal, (_supplied_id, payload) in enumerate(evidence):
        if not isinstance(payload, bytes):
            raise Error("invalid evidence snapshot payload")
        hexadecimal = digest(payload)
        item = {"kind": "snapshot", "sourceSystem": "ctx09c_host",
                "sourceLocator": f"captured/{ordinal}", "collectedAt": "1970-01-01T00:00:00Z",
                "digest": "sha256:" + hexadecimal, "mediaType": "application/octet-stream",
                "byteSize": len(payload), "sensitivity": "internal",
                "localPath": f".mana/runtime-evidence/payloads/normalized/{hexadecimal}.bin",
                "normalizationVersion": "ctx09c-captured-v1", "relationships": [],
                "collectionStatus": "complete", "revisionId": hexadecimal,
                "sourcePayload": {"localPath": f".mana/runtime-evidence/payloads/source/{hexadecimal}.bin",
                                  "digest": "sha256:" + hexadecimal, "byteSize": len(payload)},
                "normalizedRepresentation": {
                    "localPath": f".mana/runtime-evidence/payloads/normalized/{hexadecimal}.bin",
                    "digest": "sha256:" + hexadecimal, "byteSize": len(payload)}}
        item["evidenceId"] = runtime.evidence_record_id(execution_id, workspace_id, item)
        records.append(item)
        snapshot.append({"evidenceId": item["evidenceId"], "payload": blob(payload)})
    manifest = {"schemaVersion": "mana.context-runtime.evidence-manifest/v1",
                "executionId": execution_id, "workspaceId": workspace_id, "items": records}
    runtime.validate_model("evidence-manifest", manifest)
    return manifest, snapshot


def blob(payload):
    if not isinstance(payload, bytes) or len(payload) > 16 * 1024 * 1024:
        raise Error("invalid bounded materialized bytes")
    return {"encoding": "base64", "bytes": base64.b64encode(payload).decode("ascii"),
            "byteLength": len(payload), "sha256": digest(payload)}


def unblob(value):
    if not isinstance(value, dict) or set(value) != {"encoding", "bytes", "byteLength", "sha256"}:
        raise Error("invalid materialized byte record")
    if value["encoding"] != "base64" or not isinstance(value["bytes"], str):
        raise Error("invalid materialized byte encoding")
    try:
        payload = base64.b64decode(value["bytes"], validate=True)
    except (ValueError, TypeError) as error:
        raise Error("invalid materialized bytes") from error
    if (type(value["byteLength"]) is not int or value["byteLength"] != len(payload)
            or len(payload) > 16 * 1024 * 1024 or digest(payload) != value["sha256"]
            or base64.b64encode(payload).decode("ascii") != value["bytes"]):
        raise Error("materialized byte digest mismatch")
    return payload


def decode(payload):
    if not isinstance(payload, bytes) or len(payload) > MAX_BYTES:
        raise Error("shared input exceeds byte limit")
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise Error("duplicate shared input field")
            value[key] = item
        return value
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(Error("nonfinite shared input")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Error("invalid shared input JSON") from error
    if not isinstance(value, dict):
        raise Error("shared input must be an object")
    return value


def validate(payload):
    packet = decode(payload)
    required = {"schemaVersion", "identity", "comparisonExecutionId", "legacyExecutionId",
                "shadowExecutionId", "executionVersion", "workspace", "workspaceId",
                "workspaceManifest", "workspaceBindingDigest", "profileId", "target", "targetKey",
                "input", "inputPacketDigest", "evidenceSnapshot", "evidenceManifest",
                "evidenceSnapshotDigest", "contextManifest", "modeDecision", "modeDecisionDigest",
                "policyDecision", "budgetDecisionDigest", "digests"}
    if set(packet) != required:
        raise Error("incomplete or unknown shared input field")
    if packet["schemaVersion"] != VERSION or not isinstance(packet["identity"], dict):
        raise Error("invalid shared input version or identity")
    if packet["identity"] != identities(packet["identity"].get("comparisonExecutionId")):
        raise Error("shared input namespace mismatch")
    identity = packet["identity"]
    if ((packet["comparisonExecutionId"], packet["legacyExecutionId"], packet["shadowExecutionId"],
         packet["executionVersion"]) != (identity["comparisonExecutionId"], identity["legacyExecutionId"],
                                         identity["shadowExecutionId"], identity["executionVersion"])):
        raise Error("shared input execution binding mismatch")
    if not isinstance(packet["profileId"], str) or not PROFILE.fullmatch(packet["profileId"]):
        raise Error("invalid shared input profile")
    if not isinstance(packet["target"], dict):
        raise Error("invalid shared input target")
    runtime.validate_model("context-manifest", packet["contextManifest"])
    if (packet["contextManifest"]["profileId"] != packet["profileId"]
            or packet["contextManifest"]["executionId"] != packet["comparisonExecutionId"]):
        raise Error("shared input manifest execution/profile mismatch")
    workspace_bytes = unblob(packet["workspaceManifest"])
    if (not runtime.is_safe_relative_path(packet["workspace"])
            or packet["workspaceId"] != _workspace_manifest_identity(workspace_bytes)):
        raise Error("shared input workspace binding mismatch")
    parts = packet["workspace"].split("/")
    expected_kind = "feature" if len(parts) == 3 and parts[1] == "features" else "session"
    workspace_names = re.findall(r'(?m)^workspace_id:[ ]*"?([^"\n]+)"?[ ]*$', workspace_bytes.decode())
    workspace_kinds = re.findall(r'(?m)^workspace_type:[ ]*"?([^"\n]+)"?[ ]*$', workspace_bytes.decode())
    if (len(parts) != 3 or parts[0] != ".mana" or parts[1] not in {"features", "sessions"}
            or len(workspace_names) != 1 or parts[2] != workspace_names[0]
            or len(workspace_kinds) != 1 or expected_kind != workspace_kinds[0]):
        raise Error("shared input workspace path is not host-authorized")
    expected_workspace_binding = digest(canonical({"workspace": packet["workspace"],
        "workspaceId": packet["workspaceId"], "manifestDigest": packet["workspaceManifest"]["sha256"]}))
    if packet["workspaceBindingDigest"] != expected_workspace_binding:
        raise Error("shared input workspace manifest digest mismatch")
    runtime.validate_model("evidence-manifest", packet["evidenceManifest"])
    if (packet["evidenceManifest"]["executionId"] != packet["comparisonExecutionId"]
            or packet["evidenceManifest"]["workspaceId"] != packet["workspaceId"]
            or [item["evidenceId"] for item in packet["evidenceManifest"]["items"]] !=
               [item.get("evidenceId") for item in packet["evidenceSnapshot"]]):
        raise Error("shared input CTX-05 execution/workspace binding mismatch")
    budget.validate_schema(packet["policyDecision"], "provider-budget-decision-v1.schema.json")
    decision = packet["policyDecision"]
    expected = budget.mode_decision(decision["policySnapshot"], {
        "executionId": policy_execution(packet["identity"]["comparisonExecutionId"]),
        "profileId": packet["profileId"], "provider": decision["provider"],
        "executionEnvelope": {"executionVersion": packet["executionVersion"]},
        "contextManifest": packet["contextManifest"],
    }, decision["requestedMode"])
    if decision != expected:
        raise Error("shared input policy decision mismatch")
    materialized = unblob(packet["input"])
    evidence = packet["evidenceSnapshot"]
    if not isinstance(evidence, list) or len(evidence) > 256:
        raise Error("invalid bounded evidence snapshot")
    seen = set()
    for item in evidence:
        if (not isinstance(item, dict) or set(item) != {"evidenceId", "payload"}
                or not isinstance(item["evidenceId"], str)
                or not re.fullmatch(r"E-[a-f0-9]{64}", item["evidenceId"])
                or item["evidenceId"] in seen):
            raise Error("invalid or duplicate evidence snapshot identity")
        seen.add(item["evidenceId"])
        unblob(item["payload"])
    target_key = digest(canonical(packet["target"]))
    expected_mode = {"schemaVersion": "mana.context-runtime.shadow-mode-decision/v1",
                     "comparisonExecutionId": packet["comparisonExecutionId"],
                     "executionVersion": packet["executionVersion"], "mode": "shadow",
                     "authority": "legacy", "permissionGrant": "none", "externalActions": "disabled"}
    expected_digests = {"input": digest(materialized), "evidence": digest(canonical(evidence)),
                        "evidenceManifest": digest(canonical(packet["evidenceManifest"])),
                        "policy": digest(canonical(decision)), "budget": digest(canonical(decision)),
                        "mode": digest(canonical(expected_mode)),
                        "manifest": digest(canonical(packet["contextManifest"])),
                        "workspace": expected_workspace_binding}
    if (packet["targetKey"] != target_key or packet["modeDecision"] != expected_mode
            or packet["digests"] != expected_digests
            or packet["evidenceSnapshotDigest"] != expected_digests["evidence"]
            or packet["modeDecisionDigest"] != expected_digests["mode"]
            or packet["budgetDecisionDigest"] != expected_digests["budget"]
            or packet["inputPacketDigest"] != _packet_digest(packet)
            or canonical(packet) != payload):
        raise Error("shared input canonical bytes or digest mismatch")
    return packet


def validate_host(payload, project_root):
    packet = validate(payload)
    project = Path(project_root).resolve()
    if runtime.derive_workspace_id(project, packet["workspace"]) != packet["workspaceId"]:
        raise Error("active workspace identity changed")
    actual = runtime.safe_read_bytes(Path(packet["workspace"] + "/manifest.yaml"),
                                     project_root=project, max_bytes=16 * 1024)
    if actual != unblob(packet["workspaceManifest"]):
        raise Error("active workspace manifest changed")
    return packet


def materialize(comparison_id, profile, target, input_bytes, manifest, provider,
                evidence=(), requested_mode=None, *, project_root, workspace):
    """Input and evidence are captured host bytes, never deferred source paths."""
    policy = budget.load_policy()
    project = Path(project_root).resolve()
    workspace_id = runtime.derive_workspace_id(project, workspace)
    workspace_bytes = runtime.safe_read_bytes(Path(workspace + "/manifest.yaml"), project_root=project,
                                              max_bytes=16 * 1024)
    if manifest.get("executionId") != comparison_id or manifest.get("profileId") != profile:
        raise Error("CTX-04 manifest is foreign to shared comparison")
    evidence_manifest, snapshot = _evidence_records(comparison_id, workspace_id, evidence)
    decision = budget.mode_decision(policy, {
        "executionId": policy_execution(comparison_id), "profileId": profile, "provider": provider,
        "executionEnvelope": {"executionVersion": 1}, "contextManifest": manifest,
    }, requested_mode)
    identity = identities(comparison_id)
    mode_decision = {"schemaVersion": "mana.context-runtime.shadow-mode-decision/v1",
                     "comparisonExecutionId": comparison_id, "executionVersion": 1, "mode": "shadow",
                     "authority": "legacy", "permissionGrant": "none", "externalActions": "disabled"}
    workspace_manifest = blob(workspace_bytes)
    workspace_binding = digest(canonical({"workspace": workspace, "workspaceId": workspace_id,
                                          "manifestDigest": workspace_manifest["sha256"]}))
    digests = {"input": digest(input_bytes), "evidence": digest(canonical(snapshot)),
               "evidenceManifest": digest(canonical(evidence_manifest)),
               "policy": digest(canonical(decision)), "budget": digest(canonical(decision)),
               "mode": digest(canonical(mode_decision)), "manifest": digest(canonical(manifest)),
               "workspace": workspace_binding}
    packet = {"schemaVersion": VERSION, "identity": identity,
              "comparisonExecutionId": comparison_id, "legacyExecutionId": identity["legacyExecutionId"],
              "shadowExecutionId": identity["shadowExecutionId"], "executionVersion": 1,
              "workspace": workspace, "workspaceId": workspace_id,
              "workspaceManifest": workspace_manifest, "workspaceBindingDigest": workspace_binding,
              "profileId": profile, "target": target, "targetKey": digest(canonical(target)),
              "input": blob(input_bytes), "evidenceSnapshot": snapshot,
              "evidenceManifest": evidence_manifest, "contextManifest": manifest,
              "modeDecision": mode_decision, "policyDecision": decision, "digests": digests,
              "evidenceSnapshotDigest": digests["evidence"], "modeDecisionDigest": digests["mode"],
              "budgetDecisionDigest": digests["budget"]}
    packet["inputPacketDigest"] = _packet_digest(packet)
    payload = canonical(packet)
    validate(payload)
    return payload


def metadata(payload):
    packet = validate(payload)
    # Closed projection: target, manifest, policy snapshot, input and evidence
    # bodies cannot leak into persistent comparison records.
    return {"schemaVersion": VERSION, "identity": packet["identity"],
            "profileId": packet["profileId"], "packetDigest": digest(payload),
            "digests": packet["digests"], "inputBytes": packet["input"]["byteLength"],
            "evidenceCount": len(packet["evidenceSnapshot"]),
            "effectiveMode": packet["policyDecision"]["effectiveMode"]}


class Capsule:
    def __init__(self, path, fd, payload):
        self.path, self.fd = path, fd
        self.sha256 = digest(payload)
        self.identity = os.fstat(fd)

    def consume(self):
        """Attest the capsule and return bytes, with no source reopening."""
        current = os.stat(self.path, follow_symlinks=False)
        held = os.fstat(self.fd)
        if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                or current.st_uid != os.getuid() or stat.S_IMODE(current.st_mode) != 0o600
                or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino)
                or (held.st_dev, held.st_ino, held.st_size, held.st_mtime_ns, held.st_ctime_ns)
                != (self.identity.st_dev, self.identity.st_ino, self.identity.st_size,
                    self.identity.st_mtime_ns, self.identity.st_ctime_ns)):
            raise Error("shared input capsule changed")
        payload = os.pread(self.fd, MAX_BYTES + 1, 0)
        after = os.fstat(self.fd)
        stable_fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if digest(payload) != self.sha256 or any(getattr(after, key) != getattr(held, key) for key in stable_fields):
            raise Error("shared input capsule bytes changed")
        validate(payload)
        return payload


@contextmanager
def capsule(payload):
    validate(payload)
    # No recovery retention in R1A. TemporaryDirectory cleans handled failures
    # as well as normal completion; no packet is published below delivery roots.
    temporary_root = "/private/tmp" if sys.platform == "darwin" else "/tmp"
    with tempfile.TemporaryDirectory(prefix="mana-ctx09c-input-", dir=temporary_root) as temporary:
        os.chmod(temporary, 0o700)
        path = Path(temporary) / "shared-input-v1.json"
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(os.dup(fd), "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            reader = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                yield Capsule(path, reader, payload)
            finally:
                os.close(reader)
        finally:
            os.close(fd)


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == "argv":
            sys.stdout.buffer.write(argv_bytes(sys.argv[2:]))
        elif len(sys.argv) >= 12 and sys.argv[1] == "create":
            _, _, execution, profile, provider, project_root, workspace, target, manifest, requested, economy, full, *argv = sys.argv
            prompt = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
            inputs = canonical({"legacyPrompt": prompt.decode("utf-8"), "legacyArgv": argv,
                                "economyModel": economy, "fullModel": full,
                                "objective": "Run Mana profile " + profile + "; target: " + target})
            consumer = load("ctx09c_host_consumer", "context-shadow-consumer.py")
            input_value = decode(inputs)
            compiled = json.loads(manifest)
            input_value["staticSignals"] = [item["signal"] for item in compiled["staticallyActivatedSkills"]]
            input_value["requestedSkills"] = [item["skill"] for item in compiled["semanticallyRequestedSkills"]]
            input_value["deepLoadSkills"] = compiled["deepLoadedSkills"]
            try:
                input_value["pipelineSnapshot"] = consumer.snapshot(profile)
            except (Error, consumer.pipeline.runtime.ContractError):
                input_value["pipelineSnapshot"] = None
            inputs = canonical(input_value)
            sys.stdout.buffer.write(materialize(execution, profile, json.loads(target), inputs,
                                               json.loads(manifest), provider, requested_mode=requested or None,
                                               project_root=project_root, workspace=workspace))
        else:
            raise Error("unknown shared input helper operation")
    except (Error, OSError, ValueError, TypeError):
        print("ERROR: shared shadow input rejected", file=sys.stderr)
        raise SystemExit(2)
