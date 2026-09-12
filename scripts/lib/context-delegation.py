#!/usr/bin/env python3
"""CTX-07A host-only delegation binding, validation, and lossless merge."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import unicodedata
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load("mana_context_runtime", "context-runtime.py")
pipeline = _load("mana_context_pipeline", "context-pipeline.py")
phase_runtime = _load("mana_context_phase_runtime", "context-phase-runtime.py")

LIMITS = {
    "planBytes": runtime.MAX_BYTES["delegation-plan"] or 0,
    "taskBytes": runtime.MAX_BYTES["delegation-task"] or 0,
    "resultBytes": runtime.MAX_BYTES["delegation-result"] or 0,
    "mergeBytes": runtime.MAX_BYTES["delegation-merge"] or 0,
    **runtime.DELEGATION_LIMITS,
}

BINDING_FIELDS = (
    "executionId", "executionVersion", "workspaceId", "profileId", "phaseId", "attempt"
)
PLAN_DRAFT_FIELDS = {"schemaVersion", "tasks"}
TASK_DRAFT_FIELDS = {
    "taskId", "owner", "question", "scope", "taskType", "effectClass",
    "delegationAllowed", "maxChildDepth", "skills", "evidenceRefs",
    "evidenceExtracts", "evidenceGaps", "expectedOutput", "stopConditions", "limits",
}
RESULT_DRAFT_FIELDS = {
    "schemaVersion", "taskId", "status", "verifiedFacts", "findings",
    "assumptions", "inferences", "openQuestions", "evidenceGaps",
    "artifactRefs", "uncertainty",
}
CLAIM_DRAFT_FIELDS = {
    "id", "subject", "predicate", "stance", "claim", "severity", "evidenceRefs"
}
QUESTION_DRAFT_FIELDS = {"id", "subject", "question", "evidenceRefs"}
GAP_DRAFT_FIELDS = {"description", "kind", "impact", "evidenceRefs"}
ARTIFACT_DRAFT_FIELDS = {"artifactId", "kind", "evidenceRefs"}
UNCERTAINTY_DRAFT_FIELDS = {"level", "description", "evidenceRefs"}
EVIDENCE_ID = re.compile(r"^E-[a-f0-9]{64}$")


def fail(message: str) -> None:
    raise runtime.ContractError(message)


def canonical_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        fail(f"{label} must be text")
    normalized = " ".join(unicodedata.normalize("NFC", value).split())
    if not normalized:
        fail(f"{label} cannot be empty")
    return normalized


def derived_id(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(runtime.canonical_bytes(value)).hexdigest()


def digest(value: Any) -> str:
    return derived_id("sha256:", value)


def enforce_size(label: str, value: Any, limit: int) -> None:
    if len(runtime.canonical_bytes(value)) > limit:
        fail(f"{label} exceeds its {limit} byte limit")


def read_object(path: str, *, label: str, max_bytes: int) -> dict[str, Any]:
    payload = runtime.safe_read_bytes(Path(path), max_bytes=max_bytes + 1)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot decode {label}: {error}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    enforce_size(label, value, max_bytes)
    return value


def _phase_args(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        execution_id=args.execution_id,
        project_root=args.project_root,
        framework_root=args.framework_root,
        static_signal=args.static_signal,
        request_skill=args.request_skill,
        deep_load_skill=args.deep_load_skill,
    )


def authoritative_context(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any] | None]:
    phase_args = _phase_args(args)
    before = pipeline.prepare_phase(phase_args)
    phase_runtime.validate_packet(before)
    context = pipeline._load_run_context(phase_args)
    after = pipeline.prepare_phase(phase_args)
    phase_runtime.validate_packet(after)
    if runtime.canonical_bytes(before) != runtime.canonical_bytes(after):
        fail("authoritative phase changed while preparing delegation")
    if before["runStatus"] != "active":
        fail("delegation requires an active authoritative phase")
    if (
        context.state["revision"] != before["revision"]
        or context.state["currentAttempt"] != before["currentAttempt"]
        or context.state["currentPhaseId"] != before["phase"]["id"]
    ):
        fail("delegation snapshot does not match authoritative HEAD")
    return before, context.evidence_manifest


def host_bindings(packet: dict[str, Any]) -> dict[str, Any]:
    envelope = packet["executionEnvelope"]
    phase = packet["phase"]
    assert isinstance(envelope, dict) and isinstance(phase, dict)
    return {
        "executionId": packet["executionId"],
        "executionVersion": envelope["executionVersion"],
        "workspaceId": envelope["workspaceId"],
        "profileId": packet["profileId"],
        "phaseId": phase["id"],
        "attempt": packet["currentAttempt"],
    }


def _active_skills(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    manifest = packet["contextManifest"]
    assert isinstance(manifest, dict)
    return {item["id"]: item for item in manifest["activatedSkills"]}


def _require_fields(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        fail(f"{label} has an invalid field set")
    return value


def _sorted_objects(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(values, key=runtime.canonical_bytes)


def question_key(task: dict[str, Any]) -> str:
    return derived_id("Q-", {
        "identityVersion": "mana.context-runtime.delegation-question/v1",
        "question": canonical_text(task["question"], "task question"),
        "scope": task["scope"],
        "taskType": task["taskType"],
        "expectedOutput": task["expectedOutput"],
    })


def ownership_key(task: dict[str, Any]) -> str:
    return derived_id("O-", {
        "identityVersion": "mana.context-runtime.delegation-ownership/v1",
        "questionKey": task["questionKey"],
        "owner": task["owner"],
    })


def plan_projection(plan: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(plan)
    projected.pop("planId", None)
    for task in projected.get("tasks", []):
        task.pop("planId", None)
        task.pop("taskDigest", None)
    return {
        "identityVersion": "mana.context-runtime.delegation-plan-identity/v1",
        "plan": projected,
    }


def plan_id(plan: dict[str, Any]) -> str:
    return derived_id("P-", plan_projection(plan))


def task_digest(task: dict[str, Any]) -> str:
    projected = deepcopy(task)
    projected.pop("taskDigest", None)
    return digest({
        "identityVersion": "mana.context-runtime.delegation-task-identity/v1",
        "task": projected,
    })


def claim_key(item: dict[str, Any]) -> str:
    return derived_id("C-", {
        "identityVersion": "mana.context-runtime.delegation-claim/v1",
        "subject": item["subject"],
        "predicate": item["predicate"],
    })


def result_question_key(item: dict[str, Any]) -> str:
    return derived_id("Q-", {
        "identityVersion": "mana.context-runtime.delegation-result-question/v1",
        "subject": item["subject"],
        "question": canonical_text(item["question"], "result question"),
    })


def gap_key(item: dict[str, Any]) -> str:
    return derived_id("G-", {
        "identityVersion": "mana.context-runtime.delegation-gap/v1",
        "description": canonical_text(item["description"], "evidence gap description"),
        "kind": item["kind"],
        "impact": item["impact"],
    })


def _strip_result_digest(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_result_digest(child)
            for key, child in value.items()
            if key not in {
                "resultDigest", "semanticResultDigest", "executionReceiptDigest",
                "executionProvenance", "sourceResultDigest",
            }
        }
    if isinstance(value, list):
        return [_strip_result_digest(child) for child in value]
    return value


def result_digest(result: dict[str, Any]) -> str:
    return digest({
        "identityVersion": "mana.context-runtime.delegation-result-identity/v1",
        "result": _strip_result_digest(result),
    })


def execution_receipt_digest(semantic_digest: str, provenance: dict[str, Any]) -> str:
    """Bind semantic content to host-owned execution/receipt provenance."""
    return digest({
        "identityVersion": "mana.context-runtime.execution-receipt/v2",
        "semanticResultDigest": semantic_digest,
        "providerReceiptDigest": provenance["receiptDigest"],
        "executionProvenance": provenance,
    })


class ExecutionAuthority:
    """CTX-07B host-worker provenance only; never managed-child proof."""

    __slots__ = ("provenance",)

    def __init__(self, provenance: dict[str, Any]) -> None:
        self.provenance = deepcopy(provenance)


def _execution_provenance(
    provider: str, *, transport: str, root_invocation_id: str,
    child_invocation_id: str | None, attestation_kind: str,
    receipt_id: str | None, receipt_digest: str | None,
) -> dict[str, Any]:
    if transport not in {"host-worker", "provider-managed-child"}:
        fail("execution transport is invalid")
    if provider not in {"codex", "claude", "opencode"}:
        fail("execution provider is invalid")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", root_invocation_id):
        fail("root invocation ID is invalid")
    if child_invocation_id is not None and not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", child_invocation_id):
        fail("child invocation ID is invalid")
    if transport == "host-worker":
        if (
            child_invocation_id is not None
            or attestation_kind != "host-worker-process/v1"
            or receipt_id is not None
            or receipt_digest is not None
        ):
            fail("host-worker transport has invalid child attestation")
    elif (
        child_invocation_id is None or child_invocation_id == root_invocation_id
        or attestation_kind != "provider-native-managed-child-event-receipt/v1"
        or not isinstance(receipt_id, str)
        or re.fullmatch(r"R-[a-f0-9]{64}", receipt_id) is None
        or not isinstance(receipt_digest, str)
        or re.fullmatch(r"sha256:[a-f0-9]{64}", receipt_digest) is None
    ):
        fail("provider-managed child transport has invalid attestation")
    return {
        "executionTransport": transport,
        "provider": provider,
        "rootInvocationId": root_invocation_id,
        "childInvocationId": child_invocation_id,
        "attestationKind": attestation_kind,
        "receiptId": receipt_id,
        "receiptDigest": receipt_digest,
    }


def host_worker_execution_authority(provider: str, invocation_id: str) -> ExecutionAuthority:
    """Create provenance from a host-owned CTX-07B process identity."""
    return ExecutionAuthority(_execution_provenance(
        provider, transport="host-worker", root_invocation_id=invocation_id,
        child_invocation_id=None, attestation_kind="host-worker-process/v1",
        receipt_id=None, receipt_digest=None,
    ))


def _host_worker_authority_provenance(authority: ExecutionAuthority) -> dict[str, Any]:
    if not isinstance(authority, ExecutionAuthority) or not isinstance(authority.provenance, dict):
        fail("delegation result execution authority is not host-owned")
    supplied = authority.provenance
    if supplied.get("executionTransport") != "host-worker":
        fail("caller-supplied managed-child authority is forbidden; committed receipt lookup required")
    return _execution_provenance(
        supplied["provider"], transport="host-worker",
        root_invocation_id=supplied["rootInvocationId"],
        child_invocation_id=supplied["childInvocationId"],
        attestation_kind=supplied["attestationKind"],
        receipt_id=supplied["receiptId"], receipt_digest=supplied["receiptDigest"],
    )


MANAGED_CHILD_RECEIPT_SCHEMA = "mana.context-runtime.managed-child-receipt/v1"
MANAGED_CHILD_COMMIT_SCHEMA = "mana.context-runtime.managed-child-receipt-commit/v1"
MANAGED_CHILD_BINDING_SCHEMA = "mana.context-runtime.managed-child-result-binding/v1"


def managed_child_task_execution_key(packet: dict[str, Any], task: dict[str, Any]) -> str:
    identity = {
        **host_bindings(packet), "planId": task["planId"], "taskId": task["taskId"],
        "taskDigest": "sha256:" + hashlib.sha256(runtime.canonical_bytes(task)).hexdigest(),
    }
    return derived_id("W-", identity)


def managed_child_receipt_relative(key: str, invocation: str) -> str:
    if not isinstance(key, str) or re.fullmatch(r"W-[a-f0-9]{64}", key) is None:
        fail("invalid worker execution key")
    if not isinstance(invocation, str) or re.fullmatch(r"I-[a-f0-9]{32}", invocation) is None:
        fail("invalid worker invocation identity")
    return f".mana/runtime/worker-executions/{key}/attempts/{invocation}/managed-child-receipt.json"


def managed_child_receipt_digest(receipt: dict[str, Any]) -> str:
    return digest({
        "identityVersion": "mana.context-runtime.provider-native-receipt/v1",
        "provider": receipt["provider"], "attestationKind": receipt["attestationKind"],
        "orderedEventCount": receipt["orderedEventCount"],
        "orderedEventDigest": receipt["orderedEventDigest"],
    })


def _managed_child_ordered_events(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    root = {"rootInvocationId": receipt["rootInvocationId"]}
    child = {**root, "childInvocationId": receipt["childInvocationId"]}
    bound = {**child, "taskId": receipt["taskId"], "taskDigest": receipt["taskDigest"]}
    return [
        {"sequence": 1, "eventType": "root.started", **root,
         **{field: receipt[field] for field in (*BINDING_FIELDS, "planId")}},
        {"sequence": 2, "eventType": "child.started", **child},
        {"sequence": 3, "eventType": "child.task.bound", **bound},
        {"sequence": 4, "eventType": "child." + receipt["terminalStatus"],
         **bound, "status": receipt["terminalStatus"]},
    ]


def validate_managed_child_receipt_record(
    receipt: dict[str, Any], key: str, invocation: str,
    packet: dict[str, Any], task: dict[str, Any],
) -> None:
    """Audit/lifecycle record validity, including failed; grants no authority."""
    required = {
        "schemaVersion", "commitState", "receiptId", "receiptDigest", "provider",
        "attestationKind", "hostInvocationId", "rootInvocationId", "childInvocationId",
        *BINDING_FIELDS, "planId", "taskId", "taskDigest", "taskExecutionKey",
        "terminalStatus", "orderedEventCount", "orderedEventDigest",
    }
    managed_child_receipt_relative(key, invocation)
    if not isinstance(receipt, dict) or set(receipt) != required or receipt["schemaVersion"] != MANAGED_CHILD_RECEIPT_SCHEMA:
        fail("managed-child receipt artifact is malformed")
    if receipt["commitState"] != "committed":
        fail("managed-child receipt artifact is not committed")
    if receipt["hostInvocationId"] != invocation or receipt["taskExecutionKey"] != key:
        fail("managed-child receipt belongs to another host invocation")
    expected = {**host_bindings(packet), "provider": packet["provider"],
                **{field: task[field] for field in ("planId", "taskId", "taskDigest")}}
    if (key != managed_child_task_execution_key(packet, task)
            or any(task[field] != expected[field] for field in BINDING_FIELDS)
            or any(receipt[field] != value for field, value in expected.items())
            or task["taskDigest"] != task_digest(task)):
        fail("managed-child receipt is foreign or stale")
    if (receipt["attestationKind"] != "provider-native-managed-child-event-receipt/v1"
            or receipt["terminalStatus"] not in {"completed", "failed"}
            or type(receipt["orderedEventCount"]) is not int or receipt["orderedEventCount"] != 4):
        fail("managed-child receipt terminal or ordered-event identity is invalid")
    for field in ("rootInvocationId", "childInvocationId"):
        if not isinstance(receipt[field], str) or re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", receipt[field]) is None:
            fail("managed-child receipt invocation identity is invalid")
    if receipt["rootInvocationId"] == receipt["childInvocationId"]:
        fail("managed-child receipt does not identify a distinct child")
    ordered_digest = "sha256:" + hashlib.sha256(runtime.canonical_bytes(_managed_child_ordered_events(receipt))).hexdigest()
    if receipt["orderedEventDigest"] != ordered_digest:
        fail("managed-child receipt ordered event digest is inconsistent")
    expected_digest = managed_child_receipt_digest(receipt)
    if receipt["receiptDigest"] != expected_digest or receipt["receiptId"] != "R-" + expected_digest[7:]:
        fail("managed-child receipt ID or digest is inconsistent")


def managed_child_receipt_commit_record(receipt: dict[str, Any], artifact_identity: tuple[int, int]) -> dict[str, Any]:
    return {
        "schemaVersion": MANAGED_CHILD_COMMIT_SCHEMA,
        "taskExecutionKey": receipt["taskExecutionKey"], "hostInvocationId": receipt["hostInvocationId"],
        "receiptId": receipt["receiptId"], "receiptDigest": receipt["receiptDigest"],
        "artifactDigest": "sha256:" + hashlib.sha256(runtime.canonical_bytes(receipt)).hexdigest(),
        "artifactIdentity": {"device": artifact_identity[0], "inode": artifact_identity[1]},
    }


def _read_private_object_and_identity(root: Path, relative: str, label: str) -> tuple[dict[str, Any], tuple[int, int]]:
    payload, identity = runtime.safe_read_private_bytes(
        Path(relative), project_root=root, max_bytes=LIMITS["resultBytes"],
    )
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot decode {label}: {error}")
    if not isinstance(value, dict) or payload != runtime.canonical_bytes(value) + b"\n":
        fail(f"{label} artifact is not canonical")
    return value, identity


def _read_private_committed_object(root: Path, relative: str, label: str) -> dict[str, Any]:
    return _read_private_object_and_identity(root, relative, label)[0]


def read_committed_managed_child_receipt_record(
    project_root: str | Path, invocation: str, packet: dict[str, Any], task: dict[str, Any],
) -> dict[str, Any]:
    """Read a committed terminal audit record at its host-derived location."""
    root = Path(os.path.abspath(project_root))
    runtime.validate_secure_root(root)
    key = managed_child_task_execution_key(packet, task)
    relative = managed_child_receipt_relative(key, invocation)
    try:
        receipt, identity = _read_private_object_and_identity(root, relative, "managed-child receipt")
    except runtime.ContractError as error:
        if "No such file" in str(error):
            fail("provider-managed child result has no committed receipt artifact")
        raise
    validate_managed_child_receipt_record(receipt, key, invocation, packet, task)
    try:
        commit = _read_private_committed_object(root, relative.replace("receipt.json", "receipt-commit.json"), "managed-child receipt commit")
    except runtime.ContractError as error:
        if "No such file" in str(error):
            fail("managed-child receipt artifact is not committed: missing host commitment")
        raise
    if commit != managed_child_receipt_commit_record(receipt, identity):
        fail("managed-child receipt differs from its host commitment")
    return receipt


def load_committed_completed_managed_child_receipt(
    project_root: str | Path, invocation: str, packet: dict[str, Any], task: dict[str, Any],
) -> dict[str, Any]:
    """The success authority boundary: lookup, fresh CTX-03 read, completed only."""
    receipt = read_committed_managed_child_receipt_record(project_root, invocation, packet, task)
    if receipt["terminalStatus"] != "completed":
        fail("provider-managed child receipt is not successful: completed required")
    root = Path(os.path.abspath(project_root))
    key = managed_child_task_execution_key(packet, task)
    execution_id = receipt["executionId"]
    if not isinstance(execution_id, str) or re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", execution_id) is None:
        fail("managed-child receipt execution identity is invalid")
    run = f".mana/runtime/runs/{execution_id}"
    envelope = _read_private_committed_object(root, f"{run}/execution-envelope-v1.json", "execution envelope")
    state = _read_private_committed_object(root, f"{run}/run-state-v1.json", "run HEAD")
    runtime.validate_structure("execution-envelope", envelope)
    runtime.validate_structure("run-state", state)
    if (any(envelope[field] != receipt[field] for field in ("executionId", "executionVersion", "workspaceId", "profileId", "provider"))
            or any(state[field] != receipt[field] for field in ("executionId", "executionVersion", "profileId"))
            or state["currentPhaseId"] != receipt["phaseId"] or state["currentAttempt"] != receipt["attempt"]):
        fail("managed-child receipt is foreign or stale for current run HEAD")
    claim = _read_private_committed_object(root, f".mana/runtime/worker-executions/{key}/claim.json", "worker claim")
    if (claim.get("taskExecutionKey") != key or claim.get("invocationId") != invocation
            or claim.get("taskDigest") != task["taskDigest"]
            or claim.get("status") not in {"active", "terminal"}
            or (claim["status"] == "terminal" and claim.get("terminalStatus") != "complete")):
        fail("managed-child receipt is not bound to the current task execution")
    try:
        head = _read_private_committed_object(
            root, f".mana/runtime/worker-executions/{key}/task-result-head.json", "task-result HEAD"
        )
    except runtime.ContractError as error:
        if "No such file" not in str(error):
            raise
    else:
        if head.get("taskExecutionKey") != key or head.get("invocationId") != invocation:
            fail("managed-child receipt and task-result HEAD belong to different invocations")
    # Re-attest the receipt after the other host records have been read. The
    # materialized provenance below comes from these freshly verified bytes.
    if read_committed_managed_child_receipt_record(root, invocation, packet, task) != receipt:
        fail("managed-child receipt changed during authority lookup")
    return receipt


def _lookup_managed_child_provenance(
    project_root: str | Path, invocation: str, packet: dict[str, Any], task: dict[str, Any],
) -> dict[str, Any]:
    receipt = load_committed_completed_managed_child_receipt(project_root, invocation, packet, task)
    return _execution_provenance(
        receipt["provider"], transport="provider-managed-child",
        root_invocation_id=receipt["rootInvocationId"], child_invocation_id=receipt["childInvocationId"],
        attestation_kind=receipt["attestationKind"], receipt_id=receipt["receiptId"],
        receipt_digest=receipt["receiptDigest"],
    )


def _lookup_managed_child_result_invocation(
    project_root: str | Path, packet: dict[str, Any], task: dict[str, Any], result: dict[str, Any],
) -> str:
    """Merge selects the invocation from committed HEAD, never result provenance."""
    root = Path(os.path.abspath(project_root))
    key = managed_child_task_execution_key(packet, task)
    base = f".mana/runtime/worker-executions/{key}"
    head = _read_private_committed_object(root, f"{base}/task-result-head.json", "task-result HEAD")
    invocation = head.get("invocationId")
    managed_child_receipt_relative(key, invocation)
    expected_head = {
        "schemaVersion": "mana.context-runtime.worker-result-head/v1", "taskExecutionKey": key,
        "invocationId": invocation, "artifact": f"attempts/{invocation}/result.json",
        "resultDigest": result["resultDigest"],
        "artifactDigest": "sha256:" + hashlib.sha256(runtime.canonical_bytes(result)).hexdigest(),
    }
    if head != expected_head:
        fail("provider-managed child result differs from authoritative task-result HEAD")
    committed_result = _read_private_committed_object(root, f"{base}/{expected_head['artifact']}", "task result")
    if committed_result != result:
        fail("provider-managed child result differs from committed artifact")
    receipt = load_committed_completed_managed_child_receipt(root, invocation, packet, task)
    binding = _read_private_committed_object(root, f".mana/runtime/managed-child-result-bindings/{receipt['receiptDigest'][7:]}.json", "managed-child result binding")
    expected_binding = {
        "schemaVersion": MANAGED_CHILD_BINDING_SCHEMA, "receiptId": receipt["receiptId"],
        "receiptDigest": receipt["receiptDigest"], "taskExecutionKey": key, "hostInvocationId": invocation,
        "semanticResultDigest": result["semanticResultDigest"], "executionReceiptDigest": result["executionReceiptDigest"],
        "resultArtifactDigest": head["artifactDigest"], "authoritativeResultHead": head,
    }
    if binding != expected_binding:
        fail("provider-managed child receipt/result binding is foreign or conflicting")
    return invocation


def validate_gap_shape(gap: dict[str, Any], label: str) -> None:
    description = canonical_text(gap["description"], f"{label} description")
    if description != gap["description"]:
        fail(f"{label} description is not canonical")
    if EVIDENCE_ID.fullmatch(description):
        fail(f"{label} cannot use an evidence ID as a gap description")


def validate_evidence_refs(
    refs: Iterable[str], packet: dict[str, Any], evidence_manifest: dict[str, Any] | None, label: str
) -> None:
    selected = set(refs)
    if not selected:
        return
    if evidence_manifest is None:
        fail(f"{label} names evidence but the authoritative run has no CTX-05 manifest")
    runtime.validate_model("evidence-manifest", evidence_manifest)
    bindings = host_bindings(packet)
    if (
        evidence_manifest["executionId"] != bindings["executionId"]
        or evidence_manifest["workspaceId"] != bindings["workspaceId"]
    ):
        fail(f"{label} uses a foreign CTX-05 evidence manifest")
    records = {item["evidenceId"]: item for item in evidence_manifest["items"]}
    available = set(packet["phaseInput"]["evidenceRefs"])
    policy = packet["phase"]["policy"]
    for evidence_id in selected:
        record = records.get(evidence_id)
        if record is None:
            fail(f"{label} names an unknown CTX-05 evidence ID")
        if evidence_id not in available:
            fail(f"{label} names evidence absent from the current phase packet")
        if record["kind"] not in policy["evidenceKinds"]:
            fail(f"{label} names evidence with a disallowed phase kind")
        if record["collectionStatus"] not in policy["evidenceStatuses"]:
            fail(f"{label} names evidence with a disallowed phase status")


def _validate_task_policy(
    task: dict[str, Any], packet: dict[str, Any], evidence_manifest: dict[str, Any] | None
) -> None:
    if len(task["skills"]) > LIMITS["skillsPerTask"]:
        fail(f"delegation task {task['taskId']} exceeds the skill cardinality limit")
    if len(task["evidenceRefs"]) > LIMITS["evidenceRefsPerTask"]:
        fail(f"delegation task {task['taskId']} exceeds the evidence cardinality limit")
    if len(task["evidenceGaps"]) > LIMITS["taskEvidenceGaps"]:
        fail(f"delegation task {task['taskId']} exceeds the gap cardinality limit")
    if canonical_text(task["question"], "task question") != task["question"]:
        fail(f"delegation task {task['taskId']} question is not canonical")
    if task["questionKey"] != question_key(task):
        fail(f"delegation task {task['taskId']} has a non-authoritative question key")
    if task["ownershipKey"] != ownership_key(task):
        fail(f"delegation task {task['taskId']} has a non-authoritative ownership key")
    if task["effectClass"] != "read" or task["delegationAllowed"] is not False:
        fail(f"delegation task {task['taskId']} requests broader authority")
    if task["maxChildDepth"] != 0:
        fail(f"delegation task {task['taskId']} permits recursive delegation")
    for index, gap in enumerate(task["evidenceGaps"]):
        validate_gap_shape(gap, f"delegation task {task['taskId']} evidenceGaps[{index}]")
    validate_evidence_refs(task["evidenceRefs"], packet, evidence_manifest, f"delegation task {task['taskId']}")
    extracts = task.get("evidenceExtracts", [])
    if any(item["evidenceId"] not in set(task["evidenceRefs"]) for item in extracts if isinstance(item, dict) and "evidenceId" in item):
        fail(f"delegation task {task['taskId']} authorizes an extract outside its evidence refs")
    active_skills = _active_skills(packet)
    for skill_id in task["skills"]:
        skill = active_skills.get(skill_id)
        if skill is None:
            fail(f"delegation task {task['taskId']} uses an undeclared skill")
        if skill["executionMode"] != "read" or skill["parallelSafe"] is not True:
            fail(f"delegation task {task['taskId']} is not read-only and parallel-safe")
    manifest = packet["contextManifest"]
    if task["limits"]["retrievalCycles"] > manifest["limits"]["retrievalCyclesPerQuestion"]:
        fail(f"delegation task {task['taskId']} exceeds the host retrieval limit")


def validate_plan(
    plan: dict[str, Any], packet: dict[str, Any], evidence_manifest: dict[str, Any] | None
) -> None:
    runtime.validate_structure("delegation-plan", plan)
    enforce_size("delegation plan", plan, LIMITS["planBytes"])
    bindings = host_bindings(packet)
    if any(plan[field] != bindings[field] for field in BINDING_FIELDS):
        fail("delegation plan is bound to a different authoritative phase packet")
    if len(plan["tasks"]) > packet["contextManifest"]["limits"]["directWorkers"]:
        fail("delegation plan exceeds the host-enforced direct worker limit")
    task_ids: set[str] = set()
    question_keys: set[str] = set()
    ownership_keys: set[str] = set()
    for index, task in enumerate(plan["tasks"]):
        runtime.validate_model("delegation-task", task)
        enforce_size(f"delegation task {task['taskId']}", task, LIMITS["taskBytes"])
        if any(task[field] != bindings[field] for field in BINDING_FIELDS):
            fail(f"delegation task {index} is bound to a different authoritative phase packet")
        if task["planId"] != plan["planId"]:
            fail(f"delegation task {task['taskId']} is bound to a different plan")
        if task["taskId"] in task_ids:
            fail("delegation plan contains a reused task ID")
        if task["questionKey"] in question_keys:
            fail("one canonical question cannot have multiple tasks or owners")
        if task["ownershipKey"] in ownership_keys:
            fail("delegation plan contains a duplicate ownership key")
        task_ids.add(task["taskId"])
        question_keys.add(task["questionKey"])
        ownership_keys.add(task["ownershipKey"])
        _validate_task_policy(task, packet, evidence_manifest)
    expected_plan_id = plan_id(plan)
    if plan["planId"] != expected_plan_id:
        fail("delegation plan ID does not match its canonical validated bytes")
    for task in plan["tasks"]:
        if task["taskDigest"] != task_digest(task):
            fail(f"delegation task {task['taskId']} digest does not match its canonical binding")


def _normalize_scope(scope: Any) -> Any:
    if not isinstance(scope, dict):
        return scope
    normalized = deepcopy(scope)
    boundaries = normalized.get("boundaries")
    if isinstance(boundaries, list) and all(isinstance(item, dict) for item in boundaries):
        normalized["boundaries"] = _sorted_objects(boundaries)
    return normalized


def bind_plan(
    draft: dict[str, Any], packet: dict[str, Any], evidence_manifest: dict[str, Any] | None
) -> dict[str, Any]:
    _require_fields(draft, PLAN_DRAFT_FIELDS, "delegation plan draft")
    if draft["schemaVersion"] != "mana.context-runtime.delegation-plan-draft/v1":
        fail("delegation plan draft has an unsupported version")
    if not isinstance(draft["tasks"], list) or not draft["tasks"]:
        fail("delegation plan draft requires at least one task")
    if len(draft["tasks"]) > LIMITS["tasks"]:
        fail("delegation plan draft exceeds the task cardinality limit")
    bindings = host_bindings(packet)
    tasks: list[dict[str, Any]] = []
    for index, raw_task in enumerate(draft["tasks"]):
        # R1B is backwards compatible with R1A task drafts: absence means no
        # evidence bytes are admitted into the worker capsule.
        if isinstance(raw_task, dict) and set(raw_task) == TASK_DRAFT_FIELDS - {"evidenceExtracts"}:
            raw_task = {**raw_task, "evidenceExtracts": []}
        task_draft = _require_fields(raw_task, TASK_DRAFT_FIELDS, f"delegation task draft {index}")
        task = {
            "schemaVersion": "mana.context-runtime.delegation-task/v1",
            **bindings,
            "taskId": task_draft["taskId"],
            "owner": task_draft["owner"],
            "question": canonical_text(task_draft["question"], f"delegation task draft {index} question"),
            "scope": _normalize_scope(task_draft["scope"]),
            "taskType": task_draft["taskType"],
            "effectClass": task_draft["effectClass"],
            "delegationAllowed": task_draft["delegationAllowed"],
            "maxChildDepth": task_draft["maxChildDepth"],
            "skills": sorted(task_draft["skills"]) if isinstance(task_draft["skills"], list) else task_draft["skills"],
            "evidenceRefs": sorted(task_draft["evidenceRefs"]) if isinstance(task_draft["evidenceRefs"], list) else task_draft["evidenceRefs"],
            "evidenceExtracts": sorted(task_draft.get("evidenceExtracts", []), key=runtime.canonical_bytes),
            "evidenceGaps": _sorted_objects(task_draft["evidenceGaps"]) if isinstance(task_draft["evidenceGaps"], list) and all(isinstance(item, dict) for item in task_draft["evidenceGaps"]) else task_draft["evidenceGaps"],
            "expectedOutput": deepcopy(task_draft["expectedOutput"]),
            "stopConditions": sorted(task_draft["stopConditions"]) if isinstance(task_draft["stopConditions"], list) else task_draft["stopConditions"],
            "limits": deepcopy(task_draft["limits"]),
        }
        if isinstance(task["expectedOutput"], dict) and isinstance(task["expectedOutput"].get("sections"), list):
            task["expectedOutput"]["sections"] = sorted(task["expectedOutput"]["sections"])
        task["questionKey"] = question_key(task)
        task["ownershipKey"] = ownership_key(task)
        tasks.append(task)
    plan = {
        "schemaVersion": "mana.context-runtime.delegation-plan/v1",
        **bindings,
        "tasks": tasks,
    }
    plan["planId"] = plan_id(plan)
    for task in tasks:
        task["planId"] = plan["planId"]
        task["taskDigest"] = task_digest(task)
    validate_plan(plan, packet, evidence_manifest)
    return plan


def _provenance(task: dict[str, Any], evidence_refs: list[str], source_digest: str = "") -> dict[str, Any]:
    return {
        "taskId": task["taskId"],
        "planId": task["planId"],
        "sourceResultDigest": source_digest,
        "evidenceRefs": evidence_refs,
    }


def _prepare_claim(raw: Any, task: dict[str, Any], label: str, *, finding: bool) -> dict[str, Any]:
    item = deepcopy(_require_fields(raw, CLAIM_DRAFT_FIELDS, label))
    item["claim"] = canonical_text(item["claim"], f"{label} claim")
    item["evidenceRefs"] = sorted(item["evidenceRefs"]) if isinstance(item["evidenceRefs"], list) else item["evidenceRefs"]
    if finding and item["severity"] is None:
        fail(f"{label} requires severity")
    if not finding and item["severity"] is not None:
        fail(f"{label} cannot assign severity")
    item["claimKey"] = claim_key(item)
    item["provenance"] = _provenance(task, item["evidenceRefs"])
    return item


def _prepare_question(raw: Any, task: dict[str, Any], label: str) -> dict[str, Any]:
    item = deepcopy(_require_fields(raw, QUESTION_DRAFT_FIELDS, label))
    item["question"] = canonical_text(item["question"], f"{label} question")
    item["evidenceRefs"] = sorted(item["evidenceRefs"]) if isinstance(item["evidenceRefs"], list) else item["evidenceRefs"]
    item["questionKey"] = result_question_key(item)
    item["provenance"] = _provenance(task, item["evidenceRefs"])
    return item


def _prepare_gap(raw: Any, task: dict[str, Any], label: str) -> dict[str, Any]:
    item = deepcopy(_require_fields(raw, GAP_DRAFT_FIELDS, label))
    item["description"] = canonical_text(item["description"], f"{label} description")
    item["evidenceRefs"] = sorted(item["evidenceRefs"]) if isinstance(item["evidenceRefs"], list) else item["evidenceRefs"]
    validate_gap_shape(item, label)
    item["gapKey"] = gap_key(item)
    item["provenance"] = _provenance(task, item["evidenceRefs"])
    return item


def _prepare_artifact(raw: Any, task: dict[str, Any], label: str) -> dict[str, Any]:
    item = deepcopy(_require_fields(raw, ARTIFACT_DRAFT_FIELDS, label))
    item["evidenceRefs"] = sorted(item["evidenceRefs"]) if isinstance(item["evidenceRefs"], list) else item["evidenceRefs"]
    item["provenance"] = _provenance(task, item["evidenceRefs"])
    return item


def _prepare_uncertainty(raw: Any, task: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(_require_fields(raw, UNCERTAINTY_DRAFT_FIELDS, "delegation result uncertainty"))
    if item["description"] is not None:
        item["description"] = canonical_text(item["description"], "delegation result uncertainty description")
    item["evidenceRefs"] = sorted(item["evidenceRefs"]) if isinstance(item["evidenceRefs"], list) else item["evidenceRefs"]
    item["provenance"] = _provenance(task, item["evidenceRefs"])
    return item


def _result_elements(result: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for category in (
        "verifiedFacts", "findings", "assumptions", "inferences",
        "openQuestions", "evidenceGaps", "artifactRefs",
    ):
        for item in result[category]:
            yield category, item
    yield "uncertainty", result["uncertainty"]


def bind_result(
    draft: dict[str, Any], packet: dict[str, Any], plan: dict[str, Any], task: dict[str, Any],
    evidence_manifest: dict[str, Any] | None, *, authority: ExecutionAuthority | None = None,
    managed_child_project_root: str | Path | None = None,
    managed_child_invocation_id: str | None = None,
) -> dict[str, Any]:
    _require_fields(draft, RESULT_DRAFT_FIELDS, "delegation result draft")
    if draft["schemaVersion"] != "mana.context-runtime.delegation-result-draft/v1":
        fail("delegation result draft has an unsupported version")
    if draft["taskId"] != task["taskId"]:
        fail("delegation result draft names a different task")
    for category in ("verifiedFacts", "findings", "assumptions", "inferences"):
        if len(draft[category]) > LIMITS["claimsPerCategory"]:
            fail(f"delegation result draft exceeds the {category} cardinality limit")
    if len(draft["openQuestions"]) > LIMITS["questions"]:
        fail("delegation result draft exceeds the question cardinality limit")
    if len(draft["evidenceGaps"]) > LIMITS["gaps"]:
        fail("delegation result draft exceeds the gap cardinality limit")
    if len(draft["artifactRefs"]) > LIMITS["artifactRefs"]:
        fail("delegation result draft exceeds the artifact cardinality limit")
    result = {
        "schemaVersion": "mana.context-runtime.delegation-result/v1",
        **{field: task[field] for field in BINDING_FIELDS},
        "planId": task["planId"],
        "taskId": task["taskId"],
        "taskDigest": task["taskDigest"],
        "owner": task["owner"],
        "status": draft["status"],
        "verifiedFacts": [_prepare_claim(item, task, f"verifiedFacts[{index}]", finding=False) for index, item in enumerate(draft["verifiedFacts"])],
        "findings": [_prepare_claim(item, task, f"findings[{index}]", finding=True) for index, item in enumerate(draft["findings"])],
        "assumptions": [_prepare_claim(item, task, f"assumptions[{index}]", finding=False) for index, item in enumerate(draft["assumptions"])],
        "inferences": [_prepare_claim(item, task, f"inferences[{index}]", finding=False) for index, item in enumerate(draft["inferences"])],
        "openQuestions": [_prepare_question(item, task, f"openQuestions[{index}]") for index, item in enumerate(draft["openQuestions"])],
        "evidenceGaps": [_prepare_gap(item, task, f"evidenceGaps[{index}]") for index, item in enumerate(draft["evidenceGaps"])],
        "artifactRefs": [_prepare_artifact(item, task, f"artifactRefs[{index}]") for index, item in enumerate(draft["artifactRefs"])],
        "uncertainty": _prepare_uncertainty(draft["uncertainty"], task),
    }
    cited = {ref for _, item in _result_elements(result) for ref in item["evidenceRefs"]}
    result["evidenceRefs"] = sorted(cited)
    # Managed-child callers supply lookup identity only. No DTO, dict, digest,
    # or previously resolved provenance is sufficient proof at this boundary.
    if authority is not None:
        _host_worker_authority_provenance(authority)
    if managed_child_project_root is not None or managed_child_invocation_id is not None:
        if authority is not None or managed_child_project_root is None or managed_child_invocation_id is None:
            fail("managed-child binding requires only complete host lookup identity")
        provenance = _lookup_managed_child_provenance(
            managed_child_project_root, managed_child_invocation_id, packet, task
        )
    else:
        authority = authority or host_worker_execution_authority(
            packet["provider"], f"host-bind-{task['taskId']}"
        )
        provenance = _host_worker_authority_provenance(authority)
    if provenance["provider"] != packet["provider"]:
        fail("delegation result execution authority uses another provider")
    result["executionProvenance"] = provenance
    result["semanticResultDigest"] = result_digest(result)
    # resultDigest is retained as the CTX-07A compatibility alias.  It is
    # deliberately semantic, never an execution receipt identity.
    result["resultDigest"] = result["semanticResultDigest"]
    result["executionReceiptDigest"] = execution_receipt_digest(
        result["semanticResultDigest"], provenance
    )
    for _, item in _result_elements(result):
        item["provenance"]["sourceResultDigest"] = result["resultDigest"]
    validate_result(
        result, packet, plan, task, evidence_manifest, authority=authority,
        managed_child_project_root=managed_child_project_root,
        managed_child_invocation_id=managed_child_invocation_id,
    )
    return result


def validate_result(
    result: dict[str, Any], packet: dict[str, Any], plan: dict[str, Any], task: dict[str, Any],
    evidence_manifest: dict[str, Any] | None, *, authority: ExecutionAuthority | None = None,
    managed_child_project_root: str | Path | None = None,
    managed_child_invocation_id: str | None = None,
) -> None:
    """Validate one result bound to an already validated authoritative plan.

    This is deliberately the single semantic result validator used both after
    host binding and while merging.  Revalidating at merge remains necessary:
    a result artifact may have changed after bind-result emitted it.
    """
    runtime.validate_model("delegation-result", result)
    enforce_size("delegation result", result, LIMITS["resultBytes"])
    plan_tasks = [item for item in plan["tasks"] if item["taskId"] == task["taskId"]]
    if len(plan_tasks) != 1 or runtime.canonical_bytes(plan_tasks[0]) != runtime.canonical_bytes(task):
        fail("delegation result task is not the authoritative task from its plan")
    expected_bindings = {field: task[field] for field in BINDING_FIELDS}
    if any(result[field] != expected_bindings[field] for field in BINDING_FIELDS):
        fail("delegation result is foreign or stale for the authoritative phase packet")
    for field in ("planId", "taskId", "taskDigest", "owner"):
        if result[field] != task[field]:
            fail(f"delegation result has an inconsistent {field}")
    expected_digest = result_digest(result)
    if result["semanticResultDigest"] != expected_digest or result["resultDigest"] != expected_digest:
        fail("delegation result digest does not match its canonical content")
    supplied = result["executionProvenance"]
    if authority is not None:
        _host_worker_authority_provenance(authority)
    if supplied["executionTransport"] == "provider-managed-child":
        if authority is not None:
            fail("caller-supplied authority cannot authorize a managed-child result")
        if managed_child_project_root is None or managed_child_invocation_id is None:
            fail("provider-managed child result has no committed host receipt authority")
        expected_provenance = _lookup_managed_child_provenance(
            managed_child_project_root, managed_child_invocation_id, packet, task
        )
    elif managed_child_project_root is not None or managed_child_invocation_id is not None:
        fail("host-worker result cannot use managed-child lookup identity")
    elif authority is not None:
        expected_provenance = _host_worker_authority_provenance(authority)
    else:
        expected_provenance = _execution_provenance(
            supplied["provider"], transport=supplied["executionTransport"],
            root_invocation_id=supplied["rootInvocationId"],
            child_invocation_id=supplied["childInvocationId"],
            attestation_kind=supplied["attestationKind"],
            receipt_id=supplied["receiptId"], receipt_digest=supplied["receiptDigest"],
        )
    if expected_provenance["provider"] != packet["provider"]:
        fail("delegation result execution provenance uses another provider")
    if result["executionProvenance"] != expected_provenance:
        fail("delegation result execution provenance is not host-valid")
    if result["executionReceiptDigest"] != execution_receipt_digest(expected_digest, expected_provenance):
        fail("delegation result execution receipt digest does not match host provenance")
    seen_ids: set[str] = set()
    cited: set[str] = set()
    for category, item in _result_elements(result):
        identifier = item.get("id") or item.get("gapKey") or item.get("artifactId") or "uncertainty"
        scoped_id = f"{category}:{identifier}"
        if scoped_id in seen_ids:
            fail(f"delegation result contains duplicate item {scoped_id}")
        seen_ids.add(scoped_id)
        if category in {"verifiedFacts", "findings", "assumptions", "inferences"}:
            if canonical_text(item["claim"], f"{category} claim") != item["claim"]:
                fail(f"{category} contains non-canonical prose")
            if item["claimKey"] != claim_key(item):
                fail(f"{category} contains a tampered claim key")
            if category == "findings" and item["severity"] is None:
                fail("finding omits severity")
            if category != "findings" and item["severity"] is not None:
                fail(f"{category} cannot assign severity")
            if category in {"verifiedFacts", "findings", "inferences"} and not item["evidenceRefs"]:
                fail(f"{category} requires real CTX-05 evidence")
        elif category == "openQuestions":
            if canonical_text(item["question"], "open question") != item["question"]:
                fail("open question contains non-canonical prose")
            if item["questionKey"] != result_question_key(item):
                fail("open question contains a tampered question key")
        elif category == "evidenceGaps":
            validate_gap_shape(item, "result evidence gap")
            if item["gapKey"] != gap_key(item):
                fail("result evidence gap contains a tampered gap key")
        provenance = item["provenance"]
        if (
            provenance["taskId"] != task["taskId"]
            or provenance["planId"] != task["planId"]
            or provenance["sourceResultDigest"] != result["resultDigest"]
            or provenance["evidenceRefs"] != item["evidenceRefs"]
        ):
            fail(f"{category} contains inconsistent point provenance")
        cited.update(item["evidenceRefs"])
    if result["evidenceRefs"] != sorted(cited):
        fail("delegation result evidence index is not the exact cited evidence union")
    validate_evidence_refs(
        cited, packet, evidence_manifest, f"delegation result {task['taskId']}"
    )
    if not cited.issubset(set(task["evidenceRefs"])):
        fail(f"delegation result {task['taskId']} cites evidence outside its task packet")
    uncertainty = result["uncertainty"]
    if (uncertainty["level"] == "none") != (uncertainty["description"] is None):
        fail("delegation result uncertainty level and description disagree")


def _aggregate(results: Iterable[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    return _sorted_objects(deepcopy(item) for result in results for item in result[category])


def _conflicts(aggregates: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    comparable: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for category in ("verifiedFacts", "findings", "assumptions", "inferences"):
        for item in aggregates[category]:
            comparable.setdefault(item["claimKey"], []).append((category, item))
    conflicts: list[dict[str, Any]] = []
    for key, entries in comparable.items():
        stances = {item["stance"] for _, item in entries}
        if not {"affirmed", "denied"}.issubset(stances):
            continue
        claims = [
            {
                "category": category,
                "id": item["id"],
                "stance": item["stance"],
                "provenance": deepcopy(item["provenance"]),
            }
            for category, item in entries
            if item["stance"] in {"affirmed", "denied"}
        ]
        conflicts.append({
            "claimKey": key,
            "stances": ["affirmed", "denied"],
            "claims": _sorted_objects(claims),
        })
    return sorted(conflicts, key=lambda item: item["claimKey"])


def merge(
    plan: dict[str, Any], results: list[dict[str, Any]], packet: dict[str, Any],
    evidence_manifest: dict[str, Any] | None,
    *, authorities: dict[str, ExecutionAuthority] | None = None,
    managed_child_project_root: str | Path | None = None,
) -> dict[str, Any]:
    validate_plan(plan, packet, evidence_manifest)
    tasks = {task["taskId"]: task for task in plan["tasks"]}
    by_task: dict[str, dict[str, Any]] = {}
    for result in results:
        task_id = result.get("taskId")
        if not isinstance(task_id, str) or task_id not in tasks:
            fail("delegation merge contains a result for an undeclared task")
        if task_id in by_task:
            fail("delegation merge contains a duplicate task result")
        invocation = None
        if result.get("executionProvenance", {}).get("executionTransport") == "provider-managed-child":
            if authorities is not None and task_id in authorities:
                _host_worker_authority_provenance(authorities[task_id])
                fail("caller-supplied authority cannot authorize a managed-child merge")
            if managed_child_project_root is not None:
                invocation = _lookup_managed_child_result_invocation(
                    managed_child_project_root, packet, tasks[task_id], result
                )
        validate_result(
            result, packet, plan, tasks[task_id], evidence_manifest,
            authority=None if authorities is None else authorities.get(task_id),
            managed_child_project_root=managed_child_project_root if invocation is not None else None,
            managed_child_invocation_id=invocation,
        )
        by_task[task_id] = result
    ordered_results = [deepcopy(by_task[task_id]) for task_id in sorted(by_task)]
    aggregates = {
        category: _aggregate(ordered_results, category)
        for category in (
            "verifiedFacts", "findings", "assumptions", "inferences",
            "openQuestions", "evidenceGaps", "artifactRefs",
        )
    }
    conflicts = _conflicts(aggregates)
    missing = sorted(set(tasks) - set(by_task))
    incomplete = bool(missing) or any(result["status"] != "complete" for result in ordered_results)
    merge_status = "conflicted" if conflicts else "incomplete" if incomplete else "complete"
    value = {
        "schemaVersion": "mana.context-runtime.delegation-merge/v1",
        **{field: plan[field] for field in BINDING_FIELDS},
        "planId": plan["planId"],
        "mergeStatus": merge_status,
        "taskResults": ordered_results,
        **aggregates,
        "evidenceRefs": sorted({ref for result in ordered_results for ref in result["evidenceRefs"]}),
        "uncertainty": _sorted_objects(deepcopy(result["uncertainty"]) for result in ordered_results),
        "missingTaskIds": missing,
        "conflicts": conflicts,
    }
    runtime.validate_structure("delegation-merge", value)
    enforce_size("delegation merge", value, LIMITS["mergeBytes"])
    return value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Bind and validate CTX-07A packets without invoking providers or workers."
    )
    commands = result.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("execution_id")
        command.add_argument("--project-root", required=True)
        command.add_argument("--framework-root", default=str(HERE.parent.parent))
        command.add_argument("--static-signal", action="append", default=[])
        command.add_argument("--request-skill", action="append", default=[])
        command.add_argument("--deep-load-skill", action="append", default=[])

    bind_plan_command = commands.add_parser("bind-plan")
    common(bind_plan_command)
    bind_plan_command.add_argument("--draft", required=True)
    bind_plan_command.set_defaults(handler="bind-plan")

    validate = commands.add_parser("validate-plan")
    common(validate)
    validate.add_argument("--plan", required=True)
    validate.set_defaults(handler="validate-plan")

    bind_result_command = commands.add_parser("bind-result")
    common(bind_result_command)
    bind_result_command.add_argument("--plan", required=True)
    bind_result_command.add_argument("--draft", required=True)
    bind_result_command.set_defaults(handler="bind-result")

    merge_command = commands.add_parser("merge-results")
    common(merge_command)
    merge_command.add_argument("--plan", required=True)
    merge_command.add_argument("--result", action="append", default=[])
    merge_command.set_defaults(handler="merge")
    return result


def main(argv: list[str]) -> int:
    try:
        args = parser().parse_args(argv[1:])
        packet, evidence_manifest = authoritative_context(args)
        if args.handler == "bind-plan":
            draft = read_object(args.draft, label="delegation plan draft", max_bytes=LIMITS["planBytes"])
            value = bind_plan(draft, packet, evidence_manifest)
        else:
            plan = read_object(args.plan, label="delegation plan", max_bytes=LIMITS["planBytes"])
            validate_plan(plan, packet, evidence_manifest)
            if args.handler == "validate-plan":
                return 0
            if args.handler == "bind-result":
                draft = read_object(args.draft, label="delegation result draft", max_bytes=LIMITS["resultBytes"])
                task_id = draft.get("taskId")
                task = next((item for item in plan["tasks"] if item["taskId"] == task_id), None)
                if task is None:
                    fail("delegation result draft names an undeclared task")
                value = bind_result(draft, packet, plan, task, evidence_manifest)
            else:
                results = [
                    read_object(path, label="delegation result", max_bytes=LIMITS["resultBytes"])
                    for path in args.result
                ]
                value = merge(plan, results, packet, evidence_manifest)
        sys.stdout.buffer.write(runtime.canonical_bytes(value) + b"\n")
        return 0
    except (runtime.ContractError, OSError, ValueError, TypeError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
