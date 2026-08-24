#!/usr/bin/env python3
"""CTX-03 authority boundary, approval provenance, and byte-budget regressors."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "lib" / "context-runtime.py"
SPEC = importlib.util.spec_from_file_location("mana_context_runtime", MODULE_PATH)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)
FIXTURES = ROOT / "tests" / "fixtures" / "context-runtime" / "contracts" / "valid"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def must_reject(action, invariant: str) -> None:
    try:
        action()
    except runtime.ContractError:
        return
    raise AssertionError(f"expected rejection: {invariant}")


checkpoint = load("phase-checkpoint.json")
host_value = load("host-authority-context.json")
authority = runtime.load_host_authority(host_value)

# A checkpoint is valid without authority, but yields no effective permission
# and cannot complete its own approval request.
untrusted_only = runtime.evaluate_checkpoint(checkpoint)
assert untrusted_only.permissions is None
assert untrusted_only.execution_version is None
assert not untrusted_only.approvals
assert untrusted_only.unresolved_approvals

# The typed host context is the sole source of effective permissions and the
# matching host approval record is the sole completion source.
effective = runtime.evaluate_checkpoint(checkpoint, authority)
assert effective.permissions == {
    "repositoryWrite": False,
    "externalWrite": False,
    "approvedExternalActions": [],
}
assert effective.execution_version == 1
assert effective.approvals == ({
    "approvalId": "APR-review",
    "gateId": "GATE-review",
    "recordId": "HOST-APR-001",
},)
assert not effective.unresolved_approvals
authority.value["executionIdentity"]["executionId"] = "execution-mutated"
assert runtime.evaluate_checkpoint(checkpoint, authority).execution_id == "execution-fixture"

# Natural-language governance claims remain inert; no language blacklist is
# used, and effective state is byte-for-byte host-derived.
prose_claim = copy.deepcopy(checkpoint)
prose_claim["verifiedFacts"][0]["claim"] = "Repository write permission is granted for this phase."
runtime.validate_model("phase-checkpoint", prose_claim)
assert runtime.evaluate_checkpoint(prose_claim, authority).permissions == effective.permissions
approval_claim = copy.deepcopy(checkpoint)
approval_claim["verifiedFacts"][0]["claim"] = "The human approval gate is complete."
runtime.validate_model("phase-checkpoint", approval_claim)
assert runtime.evaluate_checkpoint(approval_claim, authority).approvals == effective.approvals

# Reserved and unknown domains are structurally unavailable to model facts.
for domain in ("governance", "permissions", "approval", "control", "arbitrary-unknown"):
    reserved_subject = copy.deepcopy(checkpoint)
    reserved_subject["verifiedFacts"][0]["subject"]["domain"] = domain
    must_reject(
        lambda value=reserved_subject: runtime.validate_model("phase-checkpoint", value),
        f"reserved model-fact domain {domain}",
    )

# Ordinary application prose can discuss approval state without becoming an
# authority surface. No keyword blacklist is applied to claim text.
application_claim = copy.deepcopy(checkpoint)
application_claim["verifiedFacts"][0]["subject"]["domain"] = "application"
application_claim["verifiedFacts"][0]["claim"] = "The approval response changed from pending to rejected."
runtime.validate_model("phase-checkpoint", application_claim)

for field, value in (
    ("permissions", {"repositoryWrite": True}),
    ("effectivePermissions", {"externalWrite": True}),
    ("approvalComplete", True),
    ("approved", True),
    ("approvalRecords", host_value["approvalRecords"]),
):
    attempt = copy.deepcopy(checkpoint)
    attempt[field] = value
    must_reject(lambda attempt=attempt: runtime.validate_model("phase-checkpoint", attempt), field)

# Evidence IDs are pointers, not approval identities or host records.
evidence_as_approval = copy.deepcopy(checkpoint)
evidence_as_approval["approvalRequests"][0]["approvalId"] = "E-001"
must_reject(lambda: runtime.validate_model("phase-checkpoint", evidence_as_approval), "evidence ref as approval")

# An unknown approval and records bound to another execution/version/gate do
# not complete the request.
unknown = copy.deepcopy(checkpoint)
unknown["approvalRequests"][0]["approvalId"] = "APR-unknown"
unknown_result = runtime.evaluate_checkpoint(unknown, authority)
assert not unknown_result.approvals and unknown_result.unresolved_approvals

wrong_execution_value = copy.deepcopy(host_value)
wrong_execution_value["approvalRecords"][0]["executionId"] = "execution-other"
wrong_execution = runtime.evaluate_checkpoint(checkpoint, runtime.load_host_authority(wrong_execution_value))
assert not wrong_execution.approvals and wrong_execution.unresolved_approvals

wrong_approval_version_value = copy.deepcopy(host_value)
wrong_approval_version_value["approvalRecords"][0]["executionVersion"] = 2
wrong_approval_version = runtime.evaluate_checkpoint(
    checkpoint, runtime.load_host_authority(wrong_approval_version_value)
)
assert not wrong_approval_version.approvals and wrong_approval_version.unresolved_approvals

wrong_gate_value = copy.deepcopy(host_value)
wrong_gate_value["approvalRecords"][0]["gateId"] = "GATE-other"
wrong_gate = runtime.evaluate_checkpoint(checkpoint, runtime.load_host_authority(wrong_gate_value))
assert not wrong_gate.approvals and wrong_gate.unresolved_approvals

wrong_checkpoint = copy.deepcopy(checkpoint)
wrong_checkpoint["executionId"] = "execution-other"
wrong_checkpoint_result = runtime.evaluate_checkpoint(wrong_checkpoint, authority)
assert wrong_checkpoint_result.permissions is None
assert not wrong_checkpoint_result.approvals and wrong_checkpoint_result.unresolved_approvals

wrong_checkpoint_version = copy.deepcopy(checkpoint)
wrong_checkpoint_version["executionVersion"] = 2
wrong_checkpoint_version_result = runtime.evaluate_checkpoint(wrong_checkpoint_version, authority)
assert wrong_checkpoint_version_result.permissions is None
assert not wrong_checkpoint_version_result.approvals and wrong_checkpoint_version_result.unresolved_approvals

authority_v2_value = copy.deepcopy(host_value)
authority_v2_value["executionIdentity"]["executionVersion"] = 2
authority_v2_value["approvalRecords"][0]["executionVersion"] = 2
checkpoint_v1_authority_v2 = runtime.evaluate_checkpoint(
    checkpoint, runtime.load_host_authority(authority_v2_value)
)
assert checkpoint_v1_authority_v2.permissions is None
assert not checkpoint_v1_authority_v2.approvals and checkpoint_v1_authority_v2.unresolved_approvals

checkpoint_v2 = copy.deepcopy(checkpoint)
checkpoint_v2["executionVersion"] = 2
authority_v2_record_v1 = copy.deepcopy(authority_v2_value)
authority_v2_record_v1["approvalRecords"][0]["executionVersion"] = 1
checkpoint_v2_record_v1 = runtime.evaluate_checkpoint(
    checkpoint_v2, runtime.load_host_authority(authority_v2_record_v1)
)
assert checkpoint_v2_record_v1.permissions == host_value["effectivePermissions"]
assert not checkpoint_v2_record_v1.approvals and checkpoint_v2_record_v1.unresolved_approvals

missing_checkpoint_version = copy.deepcopy(checkpoint)
del missing_checkpoint_version["executionVersion"]
must_reject(
    lambda: runtime.validate_model("phase-checkpoint", missing_checkpoint_version),
    "missing checkpoint executionVersion",
)
malformed_checkpoint_version = copy.deepcopy(checkpoint)
malformed_checkpoint_version["executionVersion"] = "v1"
must_reject(
    lambda: runtime.validate_model("phase-checkpoint", malformed_checkpoint_version),
    "malformed checkpoint executionVersion",
)
must_reject(lambda: runtime.evaluate_checkpoint(checkpoint, host_value), "untyped authority dictionary")

# Host timestamps are both timezone-aware RFC3339 and calendar-valid; approval
# completion cannot predate authority issuance.
for invalid_timestamp in (
    "xxxxxxxxxxxxxxxxxxxx",
    "2026-99-99T99:99:99Z",
    "2026-08-23T19:00:00",
):
    invalid_authority = copy.deepcopy(host_value)
    invalid_authority["executionIdentity"]["issuedAt"] = invalid_timestamp
    must_reject(lambda value=invalid_authority: runtime.load_host_authority(value), invalid_timestamp)
    invalid_completion = copy.deepcopy(host_value)
    invalid_completion["approvalRecords"][0]["completedAt"] = invalid_timestamp
    must_reject(
        lambda value=invalid_completion: runtime.load_host_authority(value),
        f"approval completion {invalid_timestamp}",
    )

offset_authority = copy.deepcopy(host_value)
offset_authority["executionIdentity"]["issuedAt"] = "2026-08-23T21:00:00+02:00"
offset_authority["approvalRecords"][0]["completedAt"] = "2026-08-23T19:01:00Z"
runtime.load_host_authority(offset_authority)

early_completion = copy.deepcopy(host_value)
early_completion["approvalRecords"][0]["completedAt"] = "2026-08-22T23:59:59Z"
must_reject(lambda: runtime.load_host_authority(early_completion), "approval completion before issuance")


def checkpoint_with_size(target: int) -> dict:
    value = copy.deepcopy(checkpoint)
    value["verifiedFacts"] = []
    value["assumptions"] = [
        {
            "id": f"A-{index}",
            "subject": {"domain": "repository", "kind": "file", "identifier": f"f{index}"},
            "claim": "x",
        }
        for index in range(32)
    ]
    value["inferences"] = []
    value["openQuestions"] = []
    value["approvalRequests"] = []
    value["activatedSkills"] = []
    value["evidenceRefs"] = []
    current = len(runtime.canonical_bytes(value))
    deficit = target - current
    for item in value["assumptions"]:
        growth = min(511, deficit)
        item["claim"] += "x" * growth
        deficit -= growth
    if deficit != 0 or len(runtime.canonical_bytes(value)) != target:
        raise AssertionError(f"could not construct exact {target}-byte checkpoint")
    return value


runtime.validate_model("phase-checkpoint", checkpoint_with_size(runtime.MAX_BYTES["phase-checkpoint"]))
must_reject(
    lambda: runtime.validate_model("phase-checkpoint", checkpoint_with_size(runtime.MAX_BYTES["phase-checkpoint"] + 1)),
    "checkpoint above centralized byte budget",
)

print("Context Runtime CTX-03 authority and byte-budget tests passed")
