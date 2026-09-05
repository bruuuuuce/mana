#!/usr/bin/env python3
"""CTX-06B-R1A authoritative state-machine regressions (zero provider calls)."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "lib" / "context-pipeline.py"
SPEC = importlib.util.spec_from_file_location("mana_context_pipeline", MODULE)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)

FRAMEWORK = ROOT / "tests" / "fixtures" / "context-runtime" / "ctx06a-framework"
PROFILE = "ctx06a-fixture"
EXECUTION = "execution-ctx06b-r1a"
MISSING_ID = "E-" + "f" * 64
WORKSPACE_ID = "W-ea5772a40315d5747936f15005972dddabedf4869b64d86592e411d6b76a41a7"


def must_reject(action, invariant: str) -> None:
    try:
        action()
    except pipeline.runtime.ContractError:
        return
    raise AssertionError(f"expected rejection: {invariant}")


def evidence_item(kind: str) -> dict:
    item = json.loads((
        ROOT / "tests" / "fixtures" / "context-runtime" / "contracts" / "valid" /
        "evidence-manifest.json"
    ).read_text(encoding="utf-8"))["items"][0]
    item["kind"] = kind
    item["evidenceId"] = pipeline.runtime.evidence_record_id(
        EXECUTION, WORKSPACE_ID, item
    )
    return item


def checkpoint(
    checkpoint_id: str, phase_id: str, status: str, action_kind: str,
    target_id: str | None, *, nested_refs: list[str] | None = None,
    handoff_refs: list[str] | None = None, approvals: list[dict] | None = None,
) -> dict:
    nested_refs = list(nested_refs or [])
    facts = []
    if nested_refs:
        facts = [{
            "id": "F-r1a",
            "subject": {"domain": "repository", "kind": "file", "identifier": "fixture"},
            "claim": "Bounded transition evidence is present.",
            "evidenceRefs": nested_refs,
        }]
    return {
        "schemaVersion": "mana.context-runtime.phase-checkpoint/v1",
        "checkpointId": checkpoint_id,
        "executionId": EXECUTION,
        "executionVersion": 1,
        "profileId": PROFILE,
        "phaseId": phase_id,
        "status": status,
        "verifiedFacts": facts,
        "assumptions": [],
        "inferences": [],
        "openQuestions": [],
        "closedHypotheses": [],
        "candidateFindings": [],
        "approvalRequests": list(approvals or []),
        "activatedSkills": ["ctx06a-fixture-skill"],
        "evidenceRefs": list(handoff_refs or []),
        "nextActionRequest": {
            "kind": action_kind,
            "targetId": target_id,
            "reason": "Exercise one bounded authoritative transition.",
        },
    }


def authority(*, profile_id: str = PROFILE, approved: bool = True):
    approval_records = []
    if approved:
        approval_records = [{
            "approvalId": "APR-owner",
            "recordVersion": 1,
            "executionId": EXECUTION,
            "executionVersion": 1,
            "gateId": "GATE-owner-approval",
            "decision": "approved",
            "completedAt": "2026-09-02T00:01:00Z",
            "provenance": {
                "source": "human",
                "actorId": "human-owner",
                "recordedBy": "host:mana-runtime",
                "sourceRecordId": "HOST-APR-R1A",
            },
        }]
    return pipeline.runtime.load_host_authority({
        "schemaVersion": "mana.context-runtime.host-authority-context/v1",
        "executionIdentity": {
            "executionId": EXECUTION,
            "executionVersion": 1,
            "profileId": profile_id,
            "issuedAt": "2026-09-02T00:00:00Z",
            "issuer": "host:mana-runtime",
        },
        "effectivePermissions": {
            "repositoryWrite": False,
            "externalWrite": False,
            "approvedExternalActions": [],
        },
        "humanGates": [{
            "gateId": "GATE-owner-approval",
            "description": "Owner approval remains human-only.",
        }],
        "approvalRecords": approval_records,
    })


declaration = pipeline.load_declaration(FRAMEWORK, PROFILE)
assert [phase.retry_limit for phase in declaration.phases] == [1, 0]
profile_text = (FRAMEWORK / "profiles" / f"{PROFILE}.yaml").read_text(encoding="utf-8")
must_reject(
    lambda: pipeline.parse_pipeline_declaration(
        profile_text.replace("      retry_limit: 1\n", "", 1), PROFILE
    ),
    "missing host-owned phase retry limit",
)
manifest = pipeline.runtime.compile_context_manifest(FRAMEWORK, PROFILE, EXECUTION)
source_item = evidence_item("source")
summary_item = evidence_item("summary")
SOURCE_ID = source_item["evidenceId"]
SUMMARY_ID = summary_item["evidenceId"]
evidence = {
    "schemaVersion": "mana.context-runtime.evidence-manifest/v1",
    "executionId": EXECUTION,
    "workspaceId": WORKSPACE_ID,
    "items": [source_item, summary_item],
}
envelope = {
    "schemaVersion": "mana.context-runtime.execution-envelope/v1",
    "executionId": EXECUTION,
    "executionVersion": 1,
    "profileId": PROFILE,
    "projectRoot": ".",
    "workspace": ".mana/sessions/ctx06a-fixture",
    "workspaceId": WORKSPACE_ID,
    "target": {"repository": "mana-fixture", "base": "main", "prNumber": 17},
    "permissions": {
        "repositoryWrite": False,
        "externalWrite": False,
        "approvedExternalActions": [],
    },
    "humanGates": ["GATE-owner-approval"],
    "provider": "codex",
    "runtimeMode": "context-v2",
}
initial = pipeline._state_value(EXECUTION, PROFILE, declaration, current_phase="classify")
pipeline.validate_state(initial, EXECUTION, PROFILE, declaration)
assert initial["revision"] == 0
assert initial["attempts"] == {"classify": 1, "synthesize": 0}


def reduce(state: dict, value: dict, **kwargs):
    return pipeline.reduce_checkpoint_transition(
        state, value, declaration=declaration, envelope=envelope,
        context_manifest=manifest, evidence_manifest=evidence,
        framework_root=FRAMEWORK, **kwargs,
    )


# The next state comes only from the previous state and the accepted action.
advance_checkpoint = checkpoint(
    "C-advance", "classify", "complete", "next-declared-phase", "synthesize",
    nested_refs=[SOURCE_ID], handoff_refs=[SUMMARY_ID],
)
advanced = reduce(initial, advance_checkpoint)
assert advanced.kind == "next-declared-phase"
assert initial["attempts"] == {"classify": 1, "synthesize": 0}
assert advanced.state["revision"] == 1
assert advanced.state["transitionId"].startswith("T-")
assert advanced.state["previousStateDigest"] == pipeline._digest_value(initial)
assert advanced.state["currentPhaseId"] == "synthesize"
assert advanced.state["currentAttempt"] == 1
assert advanced.state["attempts"] == {"classify": 1, "synthesize": 1}

# Every nested factual evidenceRefs surface is resolved under current-phase
# policy; the top-level handoff list is resolved under target-phase policy.
fact_template = advance_checkpoint["verifiedFacts"][0]
for surface in ("verifiedFacts", "inferences", "closedHypotheses", "candidateFindings"):
    invalid = copy.deepcopy(advance_checkpoint)
    invalid["verifiedFacts"] = []
    invalid[surface] = [copy.deepcopy(fact_template)]
    invalid[surface][0]["evidenceRefs"] = [MISSING_ID]
    must_reject(lambda value=invalid: reduce(initial, value), f"nested refs in {surface}")
wrong_handoff = copy.deepcopy(advance_checkpoint)
wrong_handoff["evidenceRefs"] = [SOURCE_ID]
must_reject(lambda: reduce(initial, wrong_handoff), "handoff ref outside target phase policy")

# CTX-04, CTX-05, checkpoint, envelope, and authority identities are not
# independently self-asserted: execution/profile mismatches fail closed.
wrong_profile_checkpoint = copy.deepcopy(advance_checkpoint)
wrong_profile_checkpoint["profileId"] = "other-profile"
must_reject(lambda: reduce(initial, wrong_profile_checkpoint), "checkpoint profile binding")
wrong_manifest = copy.deepcopy(manifest)
wrong_manifest["executionId"] = "execution-other"
must_reject(
    lambda: pipeline.reduce_checkpoint_transition(
        initial, advance_checkpoint, declaration=declaration, envelope=envelope,
        context_manifest=wrong_manifest, evidence_manifest=evidence,
        framework_root=FRAMEWORK,
    ),
    "CTX-04 execution binding",
)
wrong_evidence = copy.deepcopy(evidence)
wrong_evidence["executionId"] = "execution-other"
must_reject(
    lambda: pipeline.reduce_checkpoint_transition(
        initial, advance_checkpoint, declaration=declaration, envelope=envelope,
        context_manifest=manifest, evidence_manifest=wrong_evidence,
        framework_root=FRAMEWORK,
    ),
    "CTX-05 execution binding",
)
wrong_workspace_evidence = copy.deepcopy(evidence)
wrong_workspace_evidence["workspaceId"] = (
    "W-f817f78dfbb69e6678f3f93eefb2302eec13624f7d8e4f3030f5afc0b82b1c95"
)
wrong_workspace_evidence["items"] = []
must_reject(
    lambda: pipeline.reduce_checkpoint_transition(
        initial, advance_checkpoint, declaration=declaration, envelope=envelope,
        context_manifest=manifest, evidence_manifest=wrong_workspace_evidence,
        framework_root=FRAMEWORK,
    ),
    "CTX-05 same-execution different-workspace binding",
)
missing_workspace_evidence = copy.deepcopy(evidence)
del missing_workspace_evidence["workspaceId"]
must_reject(
    lambda: pipeline.reduce_checkpoint_transition(
        initial, advance_checkpoint, declaration=declaration, envelope=envelope,
        context_manifest=manifest, evidence_manifest=missing_workspace_evidence,
        framework_root=FRAMEWORK,
    ),
    "CTX-05 missing workspace binding",
)
must_reject(
    lambda: reduce(initial, advance_checkpoint, authority=authority(profile_id="other-profile")),
    "host authority profile binding",
)
wrong_version_envelope = copy.deepcopy(envelope)
wrong_version_envelope["executionVersion"] = 2
must_reject(
    lambda: pipeline.reduce_checkpoint_transition(
        initial, advance_checkpoint, declaration=declaration,
        envelope=wrong_version_envelope, context_manifest=manifest,
        evidence_manifest=evidence, framework_root=FRAMEWORK,
    ),
    "execution envelope/state version binding",
)
wrong_gate_envelope = copy.deepcopy(envelope)
wrong_gate_envelope["humanGates"] = []
must_reject(
    lambda: pipeline.reduce_checkpoint_transition(
        initial, advance_checkpoint, declaration=declaration,
        envelope=wrong_gate_envelope, context_manifest=manifest,
        evidence_manifest=evidence, framework_root=FRAMEWORK,
    ),
    "execution envelope/profile gate binding",
)

# retryLimit is per-phase host policy. The initial materialization is attempt
# one, one repeat is permitted, and the next request blocks without increment.
repeat_one = checkpoint(
    "C-repeat-1", "classify", "partial", "repeat-current-phase", "classify",
    nested_refs=[SOURCE_ID], handoff_refs=[SOURCE_ID],
)
repeated = reduce(initial, repeat_one)
assert repeated.state["attempts"]["classify"] == 2
assert repeated.state["revision"] == 1
repeat_two = checkpoint(
    "C-repeat-2", "classify", "partial", "repeat-current-phase", "classify",
    nested_refs=[SOURCE_ID], handoff_refs=[SOURCE_ID],
)
exhausted = reduce(repeated.state, repeat_two)
assert exhausted.kind == "blocked"
assert exhausted.state["attempts"]["classify"] == 2
assert exhausted.state["revision"] == 2

# A self-certified future attempt or a revision below materialized history is
# not accepted as an authoritative previous state.
future_attempt = copy.deepcopy(initial)
future_attempt["attempts"]["synthesize"] = 1
must_reject(
    lambda: pipeline.validate_state(future_attempt, EXECUTION, PROFILE, declaration),
    "future attempt self-certification",
)
low_revision = copy.deepcopy(repeated.state)
low_revision["revision"] = 0
must_reject(
    lambda: pipeline.validate_state(low_revision, EXECUTION, PROFILE, declaration),
    "revision below host-derived attempts",
)

# stop/completed belongs only to the terminal declared phase. At that phase,
# all declared human gates are real: without evaluated authority the reducer
# blocks, and the same checkpoint cannot resume without host authority.
early_stop = checkpoint("C-early-stop", "classify", "complete", "stop", None)
must_reject(lambda: reduce(initial, early_stop), "non-terminal stop")
terminal_checkpoint = checkpoint(
    "C-terminal", "synthesize", "complete", "stop", None,
    nested_refs=[SUMMARY_ID], handoff_refs=[SUMMARY_ID],
    approvals=[{"approvalId": "APR-owner", "gateId": "GATE-owner-approval"}],
)
waiting = reduce(advanced.state, terminal_checkpoint)
assert waiting.kind == "blocked" and waiting.state["status"] == "blocked"
assert waiting.effective_authority.permissions is None
must_reject(
    lambda: reduce(waiting.state, terminal_checkpoint),
    "blocked resume without host authority",
)
completed = reduce(waiting.state, terminal_checkpoint, authority=authority())
assert completed.kind == "completed"
assert completed.state["status"] == "completed"
assert completed.state["revision"] == waiting.state["revision"] + 1
assert completed.effective_authority.permissions == envelope["permissions"]
assert completed.effective_authority.approvals[0]["gateId"] == "GATE-owner-approval"
must_reject(
    lambda: reduce(completed.state, terminal_checkpoint, authority=authority()),
    "completed state is terminal",
)
missing_gate = copy.deepcopy(terminal_checkpoint)
missing_gate["approvalRequests"] = []
must_reject(lambda: reduce(advanced.state, missing_gate), "omitted terminal human gate")

print("Context Runtime CTX-06B-R1A authoritative transition tests passed (zero-token)")
