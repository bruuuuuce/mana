#!/usr/bin/env python3
"""Host-owned Mission Contract, Trajectory Ledger, and checkpoint envelope.

TG03 deliberately provides deterministic state construction only.  This file
does not import provider dispatch code, send prompts, classify drift, or alter
the Story Start control flow.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any


MISSION_SCHEMA = "mana.analysis-trajectory.mission-contract/v1"
MISSION_HISTORY_SCHEMA = "mana.analysis-trajectory.mission-history/v1"
MISSION_SEED_SCHEMA = "mana.analysis-trajectory.mission-seed/v1"
MISSION_REVISION_SCHEMA = "mana.analysis-trajectory.mission-revision-request/v1"
GAP_SCHEMA = "mana.analysis-trajectory.evidence-gap/v1"
LEDGER_SCHEMA = "mana.analysis-trajectory.trajectory-ledger/v1"
ENVELOPE_SCHEMA = "mana.analysis-trajectory.checkpoint-envelope/v1"
CHECKPOINT_INPUT_SCHEMA = "mana.analysis-trajectory.checkpoint-input/v1"
EVENT_SCHEMA = "mana.analysis-trajectory.event/v1"
GENERATOR = "analysis-trajectory-state/v1"

REF_PATTERN = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
MISSION_ID_PATTERN = re.compile(r"^mission-[0-9a-f]{24}$")
DATE_TIME_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)

PROHIBITED_RAW_FIELDS = {
    "prompt", "prompts", "rawprompt", "response", "rawresponse",
    "chainofthought", "conversation", "conversationhistory", "fullhistory",
    "messages", "sourcecontent", "sourcecode", "secret", "secrets",
    "credential", "credentials", "jirabody", "customerdata", "providerbody",
}

BUDGET_KEYS = {
    "maxEvents", "maxProviderIterations", "maxVisitedScopeRefs",
    "maxEvidenceRefs", "maxLedgerRefs", "maxEnvelopeEvidenceEvents",
    "maxEnvelopeBytes", "maxEnvelopeTokenProxy",
}

EVENT_KEYS = {
    "schemaVersion", "eventId", "runId", "sequence", "emittedAt",
    "eventType", "boundary", "actionKind", "provider", "model", "effort",
    "targetScopeRef", "acceptanceCriterionRefs", "evidenceGapRefs",
    "decisionRefs", "evidenceAddedRefs", "counters", "budgetDelta",
    "outcome", "reasonCodes",
}

EVENT_TYPES = {
    "analysis_started", "analysis_completed", "analysis_stopped",
    "provider_iteration_started", "provider_iteration_completed",
    "compact_context_synthesis_started", "compact_context_synthesis_completed",
    "evidence_added", "evidence_gap_opened", "evidence_gap_closed",
    "search_scope_entered", "search_scope_exited", "search_scope_changed",
    "scope_expansion_proposed", "open_decision_observed",
    "hypothesis_rejected", "target_revisited", "no_new_evidence_observed",
    "analysis_failed",
}

MISSION_KEYS = {
    "schemaVersion", "missionId", "revision", "objective", "storyRef",
    "acceptanceCriteria", "acceptanceCriterionRefs", "mandatoryConstraints",
    "mandatoryConstraintRefs", "authoritativeInputRefs", "scopePolicy",
    "allowedEvidenceScopeRefs", "evidenceGaps", "prohibitedActions",
    "stopConditions", "softBudgets", "hardBudgets", "createdAt",
    "revisionTransition", "provenance", "contentHash",
}


class StateError(ValueError):
    """A deterministic state or contract validation failure."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StateError(f"cannot read JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise StateError(f"JSON input must be an object: {path}")
    reject_raw_fields(value)
    return value


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    if path.is_symlink():
        raise StateError(f"refusing unsafe output symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_bytes(canonical_bytes(value) + b"\n")
    temporary.replace(path)


def normalized_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def reject_raw_fields(value: Any, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise StateError(f"{location}: object key is not a string")
            if normalized_field_name(key) in PROHIBITED_RAW_FIELDS:
                raise StateError(f"{location}: prohibited raw field {key!r}")
            reject_raw_fields(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_raw_fields(child, f"{location}[{index}]")


def exact_keys(value: dict[str, Any], required: set[str], location: str) -> None:
    missing = required - set(value)
    unknown = set(value) - required
    if missing:
        raise StateError(f"{location}: missing fields {sorted(missing)}")
    if unknown:
        raise StateError(f"{location}: unknown fields {sorted(unknown)}")


def bounded_text(value: Any, location: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise StateError(f"{location}: expected a string")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise StateError(f"{location}: text must contain 1..{maximum} characters")
    return normalized


def valid_ref(value: Any, location: str) -> str:
    if not isinstance(value, str) or not REF_PATTERN.fullmatch(value):
        raise StateError(f"{location}: expected a bounded sanitized reference")
    return value


def refs(value: Any, location: str, maximum: int = 256) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise StateError(f"{location}: expected an array of at most {maximum} refs")
    normalized = sorted({valid_ref(item, f"{location}[]") for item in value})
    if len(normalized) != len(value):
        raise StateError(f"{location}: references must be unique")
    return normalized


def ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def validate_budgets(value: Any, location: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise StateError(f"{location}: budgets must be an object")
    exact_keys(value, BUDGET_KEYS, location)
    result: dict[str, int] = {}
    for key in sorted(BUDGET_KEYS):
        amount = value[key]
        if not isinstance(amount, int) or isinstance(amount, bool) or not 1 <= amount <= 100_000_000:
            raise StateError(f"{location}.{key}: expected an integer in 1..100000000")
        result[key] = amount
    return result


def validate_budget_pair(soft: dict[str, int], hard: dict[str, int]) -> None:
    for key in BUDGET_KEYS:
        if soft[key] > hard[key]:
            raise StateError(f"softBudgets.{key} exceeds hardBudgets.{key}")


def normalize_acceptance_criteria(value: Any, location: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value or len(value) > 128:
        raise StateError(f"{location}: expected 1..128 acceptance criteria")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise StateError(f"{location}[{index}]: expected an object")
        ref = item.get("ref", item.get("sourceKey", item.get("id")))
        text = item.get("text")
        approval = item.get("approvalStatus", item.get("status", "unspecified"))
        result.append({
            "ref": valid_ref(ref, f"{location}[{index}].ref"),
            "text": bounded_text(text, f"{location}[{index}].text", 2048),
            "approvalStatus": bounded_text(approval, f"{location}[{index}].approvalStatus", 64),
        })
    result.sort(key=lambda item: item["ref"])
    if len({item["ref"] for item in result}) != len(result):
        raise StateError(f"{location}: duplicate acceptance-criterion ref")
    return result


def normalize_constraints(value: Any, location: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 128:
        raise StateError(f"{location}: expected at most 128 mandatory constraints")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise StateError(f"{location}[{index}]: expected an object")
        exact_keys(item, {"ref", "kind", "statement"}, f"{location}[{index}]")
        result.append({
            "ref": valid_ref(item["ref"], f"{location}[{index}].ref"),
            "kind": valid_ref(item["kind"], f"{location}[{index}].kind"),
            "statement": bounded_text(item["statement"], f"{location}[{index}].statement", 1024),
        })
    result.sort(key=lambda item: item["ref"])
    if len({item["ref"] for item in result}) != len(result):
        raise StateError(f"{location}: duplicate mandatory-constraint ref")
    return result


def normalize_scope_policy(value: Any, constraint_refs: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError(f"{location}: expected an object")
    required = {
        "initialStoryScopeRefs", "requirementDependencyScopeRefs",
        "mandatoryConstraintScopeLinks", "proposedExpansionScopeRefs",
        "globalMandatoryScopeRefs",
    }
    exact_keys(value, required, location)
    links = value["mandatoryConstraintScopeLinks"]
    if not isinstance(links, list) or len(links) > 128:
        raise StateError(f"{location}.mandatoryConstraintScopeLinks: expected at most 128 links")
    normalized_links = []
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            raise StateError(f"{location}.mandatoryConstraintScopeLinks[{index}]: expected an object")
        exact_keys(link, {"scopeRef", "mandatoryConstraintRefs"}, f"{location}.mandatoryConstraintScopeLinks[{index}]")
        linked_constraints = refs(link["mandatoryConstraintRefs"], f"{location}.mandatoryConstraintScopeLinks[{index}].mandatoryConstraintRefs")
        if not linked_constraints or not set(linked_constraints) <= constraint_refs:
            raise StateError(f"{location}.mandatoryConstraintScopeLinks[{index}]: invalid mandatory-constraint refs")
        normalized_links.append({
            "scopeRef": valid_ref(link["scopeRef"], f"{location}.mandatoryConstraintScopeLinks[{index}].scopeRef"),
            "mandatoryConstraintRefs": linked_constraints,
        })
    normalized_links.sort(key=lambda item: (item["scopeRef"], item["mandatoryConstraintRefs"]))
    if len({item["scopeRef"] for item in normalized_links}) != len(normalized_links):
        raise StateError(f"{location}: duplicate mandatory-constraint scope")
    result = {
        "initialStoryScopeRefs": refs(value["initialStoryScopeRefs"], f"{location}.initialStoryScopeRefs"),
        "requirementDependencyScopeRefs": refs(value["requirementDependencyScopeRefs"], f"{location}.requirementDependencyScopeRefs"),
        "mandatoryConstraintScopeLinks": normalized_links,
        "proposedExpansionScopeRefs": refs(value["proposedExpansionScopeRefs"], f"{location}.proposedExpansionScopeRefs"),
        "globalMandatoryScopeRefs": refs(value["globalMandatoryScopeRefs"], f"{location}.globalMandatoryScopeRefs"),
    }
    accepted = set(allowed_scope_refs(result))
    proposed = set(result["proposedExpansionScopeRefs"])
    if accepted & proposed:
        raise StateError(f"{location}: proposed expansions cannot already be accepted")
    return result


def allowed_scope_refs(policy: dict[str, Any]) -> list[str]:
    values = (
        policy["initialStoryScopeRefs"]
        + policy["requirementDependencyScopeRefs"]
        + [item["scopeRef"] for item in policy["mandatoryConstraintScopeLinks"]]
        + policy["globalMandatoryScopeRefs"]
    )
    return sorted(set(values))


def normalize_gap_seed(
    value: Any,
    acceptance_refs: set[str],
    constraint_refs: set[str],
    opened_event_ref: str,
    location: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError(f"{location}: expected an object")
    allowed = {
        "gapId", "description", "relatedAcceptanceCriterionRefs",
        "relatedMandatoryConstraintRefs", "expectedEvidenceType", "sourceHint",
    }
    if "sourceHint" not in value:
        value = {**value, "sourceHint": None}
    exact_keys(value, allowed, location)
    goal_refs = refs(value["relatedAcceptanceCriterionRefs"], f"{location}.relatedAcceptanceCriterionRefs")
    mandatory_refs = refs(value["relatedMandatoryConstraintRefs"], f"{location}.relatedMandatoryConstraintRefs")
    if not set(goal_refs) <= acceptance_refs:
        raise StateError(f"{location}: unknown acceptance-criterion ref")
    if not set(mandatory_refs) <= constraint_refs:
        raise StateError(f"{location}: unknown mandatory-constraint ref")
    if not goal_refs and not mandatory_refs:
        raise StateError(f"{location}: gap must relate to a goal or mandatory constraint")
    source_hint = value["sourceHint"]
    if source_hint is not None:
        source_hint = bounded_text(source_hint, f"{location}.sourceHint", 256)
    return {
        "schemaVersion": GAP_SCHEMA,
        "gapId": valid_ref(value["gapId"], f"{location}.gapId"),
        "description": bounded_text(value["description"], f"{location}.description", 512),
        "relatedAcceptanceCriterionRefs": goal_refs,
        "relatedMandatoryConstraintRefs": mandatory_refs,
        "expectedEvidenceType": valid_ref(value["expectedEvidenceType"], f"{location}.expectedEvidenceType"),
        "sourceHint": source_hint,
        "status": "OPEN",
        "openedEventRef": valid_ref(opened_event_ref, f"{location}.openedEventRef"),
        "closedEventRef": None,
    }


def validate_gap(
    gap: Any,
    acceptance_refs: set[str],
    constraint_refs: set[str],
    location: str,
) -> None:
    if not isinstance(gap, dict):
        raise StateError(f"{location}: expected an evidence-gap object")
    exact_keys(gap, {
        "schemaVersion", "gapId", "description", "relatedAcceptanceCriterionRefs",
        "relatedMandatoryConstraintRefs", "expectedEvidenceType", "sourceHint",
        "status", "openedEventRef", "closedEventRef",
    }, location)
    if gap["schemaVersion"] != GAP_SCHEMA:
        raise StateError(f"{location}: unsupported evidence-gap schema")
    valid_ref(gap["gapId"], f"{location}.gapId")
    bounded_text(gap["description"], f"{location}.description", 512)
    goal_refs = refs(gap["relatedAcceptanceCriterionRefs"], f"{location}.relatedAcceptanceCriterionRefs")
    mandatory_refs = refs(gap["relatedMandatoryConstraintRefs"], f"{location}.relatedMandatoryConstraintRefs")
    if not set(goal_refs) <= acceptance_refs or not set(mandatory_refs) <= constraint_refs:
        raise StateError(f"{location}: gap contains invalid relation refs")
    if not goal_refs and not mandatory_refs:
        raise StateError(f"{location}: gap has no mission relation")
    valid_ref(gap["expectedEvidenceType"], f"{location}.expectedEvidenceType")
    if gap["sourceHint"] is not None:
        bounded_text(gap["sourceHint"], f"{location}.sourceHint", 256)
    if gap["status"] not in {"OPEN", "RESOLVED"}:
        raise StateError(f"{location}: unsupported gap status")
    valid_ref(gap["openedEventRef"], f"{location}.openedEventRef")
    if gap["status"] == "OPEN" and gap["closedEventRef"] is not None:
        raise StateError(f"{location}: open gap cannot have a closed event")
    if gap["status"] == "RESOLVED":
        valid_ref(gap["closedEventRef"], f"{location}.closedEventRef")


def normalize_gaps(
    values: Any,
    acceptance_refs: set[str],
    constraint_refs: set[str],
    opened_event_ref: str,
    location: str,
) -> list[dict[str, Any]]:
    if not isinstance(values, list) or len(values) > 256:
        raise StateError(f"{location}: expected at most 256 evidence gaps")
    result = [
        normalize_gap_seed(item, acceptance_refs, constraint_refs, opened_event_ref, f"{location}[{index}]")
        for index, item in enumerate(values)
    ]
    result.sort(key=lambda item: item["gapId"])
    if len({item["gapId"] for item in result}) != len(result):
        raise StateError(f"{location}: duplicate evidence-gap ID")
    return result


def mission_hash(contract: dict[str, Any]) -> str:
    semantic = copy.deepcopy(contract)
    semantic.pop("contentHash", None)
    return digest(semantic)


def validate_mission(contract: dict[str, Any]) -> None:
    reject_raw_fields(contract)
    exact_keys(contract, MISSION_KEYS, "mission")
    if contract["schemaVersion"] != MISSION_SCHEMA:
        raise StateError("mission: unsupported schema version")
    if not isinstance(contract["missionId"], str) or not MISSION_ID_PATTERN.fullmatch(contract["missionId"]):
        raise StateError("mission.missionId: invalid host-generated mission ID")
    revision = contract["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise StateError("mission.revision: expected a positive integer")
    bounded_text(contract["objective"], "mission.objective", 4096)
    valid_ref(contract["storyRef"], "mission.storyRef")
    acceptance = normalize_acceptance_criteria(contract["acceptanceCriteria"], "mission.acceptanceCriteria")
    constraints = normalize_constraints(contract["mandatoryConstraints"], "mission.mandatoryConstraints")
    if canonical_bytes(acceptance) != canonical_bytes(contract["acceptanceCriteria"]):
        raise StateError("mission.acceptanceCriteria: values are not canonical")
    if canonical_bytes(constraints) != canonical_bytes(contract["mandatoryConstraints"]):
        raise StateError("mission.mandatoryConstraints: values are not canonical")
    acceptance_refs = {item["ref"] for item in acceptance}
    constraint_refs = {item["ref"] for item in constraints}
    if refs(contract["acceptanceCriterionRefs"], "mission.acceptanceCriterionRefs") != sorted(acceptance_refs):
        raise StateError("mission.acceptanceCriterionRefs does not match acceptanceCriteria")
    if refs(contract["mandatoryConstraintRefs"], "mission.mandatoryConstraintRefs") != sorted(constraint_refs):
        raise StateError("mission.mandatoryConstraintRefs does not match mandatoryConstraints")
    refs(contract["authoritativeInputRefs"], "mission.authoritativeInputRefs")
    policy = normalize_scope_policy(contract["scopePolicy"], constraint_refs, "mission.scopePolicy")
    if canonical_bytes(policy) != canonical_bytes(contract["scopePolicy"]):
        raise StateError("mission.scopePolicy: values are not canonical")
    if refs(contract["allowedEvidenceScopeRefs"], "mission.allowedEvidenceScopeRefs") != allowed_scope_refs(policy):
        raise StateError("mission.allowedEvidenceScopeRefs does not match scopePolicy")
    if not isinstance(contract["evidenceGaps"], list):
        raise StateError("mission.evidenceGaps: expected an array")
    for index, gap in enumerate(contract["evidenceGaps"]):
        validate_gap(gap, acceptance_refs, constraint_refs, f"mission.evidenceGaps[{index}]")
        if gap["status"] != "OPEN" or gap["closedEventRef"] is not None:
            raise StateError("mission evidence gaps are immutable initial definitions")
    if [item["gapId"] for item in contract["evidenceGaps"]] != sorted(item["gapId"] for item in contract["evidenceGaps"]):
        raise StateError("mission.evidenceGaps: gaps must be sorted")
    if len({item["gapId"] for item in contract["evidenceGaps"]}) != len(contract["evidenceGaps"]):
        raise StateError("mission.evidenceGaps: duplicate ID")
    refs(contract["prohibitedActions"], "mission.prohibitedActions")
    refs(contract["stopConditions"], "mission.stopConditions")
    soft = validate_budgets(contract["softBudgets"], "mission.softBudgets")
    hard = validate_budgets(contract["hardBudgets"], "mission.hardBudgets")
    validate_budget_pair(soft, hard)
    if len(contract["evidenceGaps"]) > hard["maxLedgerRefs"]:
        raise StateError("mission evidence gaps exceed maxLedgerRefs")
    if not isinstance(contract["createdAt"], str) or not DATE_TIME_PATTERN.fullmatch(contract["createdAt"]):
        raise StateError("mission.createdAt: expected deterministic UTC date-time without fractions")
    transition = contract["revisionTransition"]
    if not isinstance(transition, dict):
        raise StateError("mission.revisionTransition: expected an object")
    exact_keys(transition, {"kind", "previousContentHash", "proposalApprovalRef"}, "mission.revisionTransition")
    if revision == 1:
        if transition != {"kind": "INITIAL", "previousContentHash": None, "proposalApprovalRef": None}:
            raise StateError("initial mission has an invalid revision transition")
    else:
        if transition["kind"] != "APPROVED_CHANGE":
            raise StateError("revised mission must use APPROVED_CHANGE")
        if not isinstance(transition["previousContentHash"], str) or not HASH_PATTERN.fullmatch(transition["previousContentHash"]):
            raise StateError("revised mission has an invalid previous hash")
        valid_ref(transition["proposalApprovalRef"], "mission.revisionTransition.proposalApprovalRef")
    provenance = contract["provenance"]
    if provenance != {"ownership": "host", "generator": GENERATOR, "modelAuthored": False}:
        raise StateError("mission provenance is not host-owned")
    if not isinstance(contract["contentHash"], str) or not HASH_PATTERN.fullmatch(contract["contentHash"]):
        raise StateError("mission.contentHash: invalid hash")
    if contract["contentHash"] != mission_hash(contract):
        raise StateError("mission.contentHash: integrity check failed")


def build_mission(story: dict[str, Any], seed: dict[str, Any]) -> dict[str, Any]:
    if story.get("packageVersion") != "mana.story-start.discovery-package/v1":
        raise StateError("story input is not mana.story-start.discovery-package/v1")
    story_ref = valid_ref(story.get("storyId"), "story.storyId")
    normalized_story = story.get("normalizedStory")
    if not isinstance(normalized_story, dict):
        raise StateError("story.normalizedStory: expected an object")
    objective = bounded_text(normalized_story.get("summary"), "story.normalizedStory.summary", 4096)
    acceptance = normalize_acceptance_criteria(
        normalized_story.get("acceptanceCriteria"),
        "story.normalizedStory.acceptanceCriteria",
    )
    exact_keys(seed, {
        "schemaVersion", "createdAt", "authoritativeInputRefs", "scopePolicy",
        "mandatoryConstraints", "evidenceGaps", "prohibitedActions",
        "stopConditions", "softBudgets", "hardBudgets",
    }, "missionSeed")
    if seed["schemaVersion"] != MISSION_SEED_SCHEMA:
        raise StateError("missionSeed: unsupported schema version")
    created_at = seed["createdAt"]
    if not isinstance(created_at, str) or not DATE_TIME_PATTERN.fullmatch(created_at):
        raise StateError("missionSeed.createdAt: expected deterministic UTC date-time")
    authoritative_refs = refs(seed["authoritativeInputRefs"], "missionSeed.authoritativeInputRefs")
    constraints = normalize_constraints(seed["mandatoryConstraints"], "missionSeed.mandatoryConstraints")
    constraint_refs = {item["ref"] for item in constraints}
    acceptance_refs = {item["ref"] for item in acceptance}
    policy = normalize_scope_policy(seed["scopePolicy"], constraint_refs, "missionSeed.scopePolicy")
    soft = validate_budgets(seed["softBudgets"], "missionSeed.softBudgets")
    hard = validate_budgets(seed["hardBudgets"], "missionSeed.hardBudgets")
    validate_budget_pair(soft, hard)
    mission_identity = {
        "storyRef": story_ref,
        "createdAt": created_at,
        "authoritativeInputRefs": authoritative_refs,
    }
    mission_id = "mission-" + hashlib.sha256(canonical_bytes(mission_identity)).hexdigest()[:24]
    opened_ref = f"{mission_id}:r1"
    gaps = normalize_gaps(seed["evidenceGaps"], acceptance_refs, constraint_refs, opened_ref, "missionSeed.evidenceGaps")
    contract: dict[str, Any] = {
        "schemaVersion": MISSION_SCHEMA,
        "missionId": mission_id,
        "revision": 1,
        "objective": objective,
        "storyRef": story_ref,
        "acceptanceCriteria": acceptance,
        "acceptanceCriterionRefs": sorted(acceptance_refs),
        "mandatoryConstraints": constraints,
        "mandatoryConstraintRefs": sorted(constraint_refs),
        "authoritativeInputRefs": authoritative_refs,
        "scopePolicy": policy,
        "allowedEvidenceScopeRefs": allowed_scope_refs(policy),
        "evidenceGaps": gaps,
        "prohibitedActions": refs(seed["prohibitedActions"], "missionSeed.prohibitedActions"),
        "stopConditions": refs(seed["stopConditions"], "missionSeed.stopConditions"),
        "softBudgets": soft,
        "hardBudgets": hard,
        "createdAt": created_at,
        "revisionTransition": {
            "kind": "INITIAL", "previousContentHash": None,
            "proposalApprovalRef": None,
        },
        "provenance": {
            "ownership": "host", "generator": GENERATOR, "modelAuthored": False,
        },
        "contentHash": "",
    }
    contract["contentHash"] = mission_hash(contract)
    validate_mission(contract)
    return contract


def build_history(mission: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": MISSION_HISTORY_SCHEMA,
        "missionId": mission["missionId"],
        "revisionCount": 1,
        "revisions": [copy.deepcopy(mission)],
    }


def validate_history(history: dict[str, Any]) -> None:
    reject_raw_fields(history)
    exact_keys(history, {"schemaVersion", "missionId", "revisionCount", "revisions"}, "missionHistory")
    if history["schemaVersion"] != MISSION_HISTORY_SCHEMA:
        raise StateError("missionHistory: unsupported schema version")
    if not isinstance(history["revisions"], list) or not 1 <= len(history["revisions"]) <= 64:
        raise StateError("missionHistory.revisions: expected 1..64 revisions")
    if history["revisionCount"] != len(history["revisions"]):
        raise StateError("missionHistory.revisionCount does not match revisions")
    for index, mission in enumerate(history["revisions"]):
        if not isinstance(mission, dict):
            raise StateError(f"missionHistory.revisions[{index}]: expected an object")
        validate_mission(mission)
        if mission["missionId"] != history["missionId"] or mission["revision"] != index + 1:
            raise StateError("missionHistory revision identity is not monotonic")
        if index and mission["revisionTransition"]["previousContentHash"] != history["revisions"][index - 1]["contentHash"]:
            raise StateError("missionHistory hash chain is broken")


def revision_acceptance(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise StateError("revision acceptanceCriteria must be an array")
    prepared = []
    for item in value:
        if not isinstance(item, dict):
            raise StateError("revision acceptance criterion must be an object")
        exact_keys(item, {"ref", "text", "approvalStatus"}, "revision acceptance criterion")
        prepared.append(item)
    return normalize_acceptance_criteria(prepared, "revision.semanticChanges.acceptanceCriteria")


def revision_gap_seeds(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise StateError("revision evidenceGaps must be an array")
    seeds = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise StateError(f"revision evidenceGaps[{index}] must be an object")
        allowed = {
            "gapId", "description", "relatedAcceptanceCriterionRefs",
            "relatedMandatoryConstraintRefs", "expectedEvidenceType", "sourceHint",
        }
        if set(item) == {
            "schemaVersion", "gapId", "description", "relatedAcceptanceCriterionRefs",
            "relatedMandatoryConstraintRefs", "expectedEvidenceType", "sourceHint",
            "status", "openedEventRef", "closedEventRef",
        }:
            item = {key: item[key] for key in allowed}
        seeds.append(item)
    return seeds


def revise_mission(history: dict[str, Any], request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_history(history)
    exact_keys(request, {
        "schemaVersion", "missionId", "expectedRevision", "changeKind",
        "proposalApprovalRef", "approvalAuthority", "acceptedScopeRefs",
        "semanticChanges",
    }, "revisionRequest")
    if request["schemaVersion"] != MISSION_REVISION_SCHEMA:
        raise StateError("revisionRequest: unsupported schema version")
    current = history["revisions"][-1]
    if request["missionId"] != current["missionId"] or request["expectedRevision"] != current["revision"]:
        raise StateError("revisionRequest does not target the active mission revision")
    if request["changeKind"] not in {"APPROVED_MISSION_CHANGE", "APPROVED_SCOPE_EXPANSION"}:
        raise StateError("revisionRequest.changeKind is unsupported")
    approval_ref = valid_ref(request["proposalApprovalRef"], "revisionRequest.proposalApprovalRef")
    valid_ref(request["approvalAuthority"], "revisionRequest.approvalAuthority")
    accepted_scope_refs = refs(request["acceptedScopeRefs"], "revisionRequest.acceptedScopeRefs")
    changes = request["semanticChanges"]
    if not isinstance(changes, dict) or not changes:
        raise StateError("revisionRequest.semanticChanges must be a non-empty object")
    allowed_changes = {
        "objective", "acceptanceCriteria", "mandatoryConstraints",
        "authoritativeInputRefs", "scopePolicy", "evidenceGaps",
        "prohibitedActions", "stopConditions", "softBudgets", "hardBudgets",
    }
    if set(changes) - allowed_changes:
        raise StateError(f"revisionRequest attempts to overwrite host fields: {sorted(set(changes) - allowed_changes)}")
    revised = copy.deepcopy(current)
    if "objective" in changes:
        revised["objective"] = bounded_text(changes["objective"], "revision.semanticChanges.objective", 4096)
    if "acceptanceCriteria" in changes:
        revised["acceptanceCriteria"] = revision_acceptance(changes["acceptanceCriteria"])
    if "mandatoryConstraints" in changes:
        revised["mandatoryConstraints"] = normalize_constraints(changes["mandatoryConstraints"], "revision.semanticChanges.mandatoryConstraints")
    acceptance_refs = {item["ref"] for item in revised["acceptanceCriteria"]}
    constraint_refs = {item["ref"] for item in revised["mandatoryConstraints"]}
    revised["acceptanceCriterionRefs"] = sorted(acceptance_refs)
    revised["mandatoryConstraintRefs"] = sorted(constraint_refs)
    if "authoritativeInputRefs" in changes:
        revised["authoritativeInputRefs"] = refs(changes["authoritativeInputRefs"], "revision.semanticChanges.authoritativeInputRefs")
    if "scopePolicy" in changes:
        revised["scopePolicy"] = normalize_scope_policy(changes["scopePolicy"], constraint_refs, "revision.semanticChanges.scopePolicy")
    revised["allowedEvidenceScopeRefs"] = allowed_scope_refs(revised["scopePolicy"])
    if not set(current["scopePolicy"]["globalMandatoryScopeRefs"]) <= set(revised["scopePolicy"]["globalMandatoryScopeRefs"]):
        raise StateError("revision cannot remove a globally mandatory evidence scope")
    if "evidenceGaps" in changes:
        revised["evidenceGaps"] = normalize_gaps(
            revision_gap_seeds(changes["evidenceGaps"]), acceptance_refs, constraint_refs,
            f"{current['missionId']}:r{current['revision'] + 1}",
            "revision.semanticChanges.evidenceGaps",
        )
    else:
        for gap in revised["evidenceGaps"]:
            validate_gap(gap, acceptance_refs, constraint_refs, "revision.evidenceGap")
    for key in ("prohibitedActions", "stopConditions"):
        if key in changes:
            revised[key] = refs(changes[key], f"revision.semanticChanges.{key}")
    for key in ("softBudgets", "hardBudgets"):
        if key in changes:
            revised[key] = validate_budgets(changes[key], f"revision.semanticChanges.{key}")
    validate_budget_pair(revised["softBudgets"], revised["hardBudgets"])
    if request["changeKind"] == "APPROVED_SCOPE_EXPANSION":
        if not accepted_scope_refs:
            raise StateError("approved scope expansion requires acceptedScopeRefs")
        old_allowed = set(current["allowedEvidenceScopeRefs"])
        new_allowed = set(revised["allowedEvidenceScopeRefs"])
        newly_allowed = new_allowed - old_allowed
        if newly_allowed != set(accepted_scope_refs):
            raise StateError("acceptedScopeRefs must exactly match newly allowed scopes")
        if not newly_allowed <= set(current["scopePolicy"]["proposedExpansionScopeRefs"]):
            raise StateError("scope expansion accepts a scope that was not proposed")
        if newly_allowed & set(revised["scopePolicy"]["proposedExpansionScopeRefs"]):
            raise StateError("accepted scope remains marked as proposed")
    elif accepted_scope_refs:
        raise StateError("acceptedScopeRefs is only valid for a scope expansion")
    revised["revision"] = current["revision"] + 1
    revised["revisionTransition"] = {
        "kind": "APPROVED_CHANGE",
        "previousContentHash": current["contentHash"],
        "proposalApprovalRef": approval_ref,
    }
    revised["contentHash"] = mission_hash(revised)
    validate_mission(revised)
    updated_history = copy.deepcopy(history)
    updated_history["revisions"].append(revised)
    updated_history["revisionCount"] += 1
    validate_history(updated_history)
    return revised, updated_history


def read_events(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise StateError(f"cannot read telemetry events {path}: {error}") from error
    events = []
    for line_number, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise StateError(f"invalid telemetry JSON at line {line_number}: {error}") from error
        if not isinstance(event, dict):
            raise StateError(f"telemetry event at line {line_number} is not an object")
        reject_raw_fields(event, f"events[{line_number - 1}]")
        validate_event(event, line_number)
        events.append(event)
    validate_event_stream(events)
    return events


def validate_event(event: dict[str, Any], line_number: int) -> None:
    location = f"events[{line_number - 1}]"
    exact_keys(event, EVENT_KEYS, location)
    if event["schemaVersion"] != EVENT_SCHEMA or event["eventType"] not in EVENT_TYPES:
        raise StateError(f"{location}: unsupported telemetry schema or event type")
    for key in (
        "eventId", "runId", "boundary", "actionKind", "provider", "model",
        "effort", "targetScopeRef", "outcome",
    ):
        valid_ref(event[key], f"{location}.{key}")
    if not isinstance(event["sequence"], int) or isinstance(event["sequence"], bool) or event["sequence"] < 1:
        raise StateError(f"{location}.sequence: expected a positive integer")
    if not isinstance(event["emittedAt"], str) or len(event["emittedAt"]) > 64:
        raise StateError(f"{location}.emittedAt: expected a bounded date-time")
    for key in (
        "acceptanceCriterionRefs", "evidenceGapRefs", "decisionRefs",
        "evidenceAddedRefs", "reasonCodes",
    ):
        refs(event[key], f"{location}.{key}")
    for key in ("counters", "budgetDelta"):
        if not isinstance(event[key], dict) or len(event[key]) > 64:
            raise StateError(f"{location}.{key}: expected a bounded object")
        for name, amount in event[key].items():
            valid_ref(name, f"{location}.{key} key")
            if not isinstance(amount, (int, float)) or isinstance(amount, bool) or not math.isfinite(amount) or amount < 0:
                raise StateError(f"{location}.{key}.{name}: expected a non-negative number")


def validate_event_stream(events: list[dict[str, Any]]) -> None:
    if not events:
        return
    run_id = events[0]["runId"]
    for index, event in enumerate(events, 1):
        if event["runId"] != run_id or event["sequence"] != index:
            raise StateError("telemetry run IDs or sequence numbers are not monotonic")
        if event["eventId"] != f"{run_id}-{index:06d}":
            raise StateError("telemetry event IDs are not host-derived from run ID and sequence")


def validate_event_refs(mission: dict[str, Any], events: list[dict[str, Any]]) -> None:
    goals = set(mission["acceptanceCriterionRefs"])
    gaps = {item["gapId"] for item in mission["evidenceGaps"]}
    for event in events:
        if not set(event["acceptanceCriterionRefs"]) <= goals:
            raise StateError(f"event {event['eventId']} references an unknown acceptance criterion")
        if not set(event["evidenceGapRefs"]) <= gaps:
            raise StateError(f"event {event['eventId']} references an unknown evidence gap")


def bounded(values: list[str], maximum: int, name: str, truncations: list[dict[str, Any]]) -> list[str]:
    unique = ordered_unique(values)
    if len(unique) > maximum:
        truncations.append({"field": name, "droppedCount": len(unique) - maximum})
    return unique[:maximum]


def ledger_hash(ledger: dict[str, Any]) -> str:
    value = copy.deepcopy(ledger)
    value.pop("ledgerHash", None)
    return digest(value)


def derive_ledger(mission: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    validate_mission(mission)
    validate_event_stream(events)
    validate_event_refs(mission, events)
    maximum = mission["hardBudgets"]["maxLedgerRefs"]
    truncations: list[dict[str, Any]] = []
    gaps = {item["gapId"]: copy.deepcopy(item) for item in mission["evidenceGaps"]}
    covered: list[str] = []
    evidence: list[str] = []
    decisions: list[str] = []
    expansions: list[str] = []
    active_rejections: dict[str, str] = {}
    no_evidence_streak = 0
    started = completed = failed = 0
    terminal_status = "ACTIVE"
    visit_events = [
        event for event in events
        if event["eventType"] == "provider_iteration_completed"
        and event["boundary"] != "public_pipeline"
        and event["targetScopeRef"] != "none"
    ]
    if not visit_events:
        visit_events = [
            event for event in events
            if event["eventType"] in {"provider_iteration_started", "search_scope_entered", "search_scope_changed"}
            and event["boundary"] != "public_pipeline"
            and event["targetScopeRef"] != "none"
        ]
    visited_values = [event["targetScopeRef"] for event in visit_events]
    current_scope = visited_values[-1] if visited_values else None
    for event in events:
        event_type = event["eventType"]
        added = event["evidenceAddedRefs"]
        evidence.extend(added)
        if added:
            covered.extend(event["acceptanceCriterionRefs"])
            active_rejections.pop(event["targetScopeRef"], None)
        if event_type == "evidence_gap_opened":
            if not event["evidenceGapRefs"]:
                raise StateError(f"event {event['eventId']} opens no evidence gap")
            for gap_ref in event["evidenceGapRefs"]:
                if gaps[gap_ref]["status"] == "RESOLVED":
                    raise StateError(f"event {event['eventId']} illegally reopens resolved gap {gap_ref}")
        elif event_type == "evidence_gap_closed":
            if not event["evidenceGapRefs"]:
                raise StateError(f"event {event['eventId']} closes no evidence gap")
            for gap_ref in event["evidenceGapRefs"]:
                if gaps[gap_ref]["status"] != "OPEN":
                    raise StateError(f"event {event['eventId']} repeats an invalid close for {gap_ref}")
                gaps[gap_ref]["status"] = "RESOLVED"
                gaps[gap_ref]["closedEventRef"] = event["eventId"]
        if event_type == "open_decision_observed":
            decisions.extend(event["decisionRefs"])
        elif event_type == "scope_expansion_proposed":
            expansions.append(event["eventId"])
        elif event_type == "hypothesis_rejected":
            if event["targetScopeRef"] == "none":
                raise StateError(f"event {event['eventId']} rejects no identifiable target")
            active_rejections[event["targetScopeRef"]] = event["eventId"]
        if event_type == "provider_iteration_started":
            started += 1
        elif event_type == "provider_iteration_completed":
            if event["outcome"] == "completed":
                completed += 1
                no_evidence_streak = 0 if added else no_evidence_streak + 1
            else:
                failed += 1
        if event_type == "analysis_completed":
            terminal_status = "COMPLETED"
        elif event_type == "analysis_stopped":
            terminal_status = "STOPPED"
        elif event_type == "analysis_failed":
            terminal_status = "FAILED"
    visit_counts: dict[str, int] = {}
    for target in visited_values:
        visit_counts[target] = visit_counts.get(target, 0) + 1
    repeated = [
        {"targetScopeRef": target, "count": count}
        for target, count in sorted(visit_counts.items()) if count > 1
    ]
    if len(repeated) > maximum:
        truncations.append({"field": "repeatedTargetCounters", "droppedCount": len(repeated) - maximum})
        repeated = repeated[:maximum]
    gap_values = [gaps[key] for key in sorted(gaps)]
    open_gaps = [gap["gapId"] for gap in gap_values if gap["status"] == "OPEN"]
    resolved_gaps = [gap["gapId"] for gap in gap_values if gap["status"] == "RESOLVED"]
    event_digest = digest(events)
    serialized_event_bytes = len(canonical_bytes(events))
    ledger: dict[str, Any] = {
        "schemaVersion": LEDGER_SCHEMA,
        "ledgerId": "ledger-" + hashlib.sha256(canonical_bytes({
            "missionHash": mission["contentHash"], "eventHash": event_digest,
        })).hexdigest()[:24],
        "missionId": mission["missionId"],
        "missionHash": mission["contentHash"],
        "missionRevision": mission["revision"],
        "sourceEvents": {
            "runId": events[0]["runId"] if events else None,
            "eventCount": len(events),
            "firstEventRef": events[0]["eventId"] if events else None,
            "lastEventRef": events[-1]["eventId"] if events else None,
            "contentHash": event_digest,
        },
        "coveredGoalRefs": bounded(covered, maximum, "coveredGoalRefs", truncations),
        "openEvidenceGapRefs": bounded(open_gaps, maximum, "openEvidenceGapRefs", truncations),
        "resolvedEvidenceGapRefs": bounded(resolved_gaps, maximum, "resolvedEvidenceGapRefs", truncations),
        "evidenceGaps": gap_values,
        "currentSearchScopeRef": current_scope,
        "visitedScopeRefs": bounded(visited_values, mission["hardBudgets"]["maxVisitedScopeRefs"], "visitedScopeRefs", truncations),
        "evidenceAddedSinceCheckpoint": bounded(evidence, mission["hardBudgets"]["maxEvidenceRefs"], "evidenceAddedSinceCheckpoint", truncations),
        "rejectedHypothesisRefs": bounded(list(active_rejections.values()), maximum, "rejectedHypothesisRefs", truncations),
        "openDecisionRefs": bounded(decisions, maximum, "openDecisionRefs", truncations),
        "scopeExpansionProposalRefs": bounded(expansions, maximum, "scopeExpansionProposalRefs", truncations),
        "repeatedTargetCounters": repeated,
        "noNewEvidenceStreak": no_evidence_streak,
        "providerCounters": {
            "iterationsStarted": started,
            "iterationsCompleted": completed,
            "iterationsFailed": failed,
        },
        "budgetConsumption": {
            "eventCount": len(events),
            "providerIterations": max(started, completed + failed),
            "evidenceRefCount": len(set(evidence)),
            "visitedScopeCount": len(set(visited_values)),
            "serializedEventBytes": serialized_event_bytes,
            "tokenProxyEstimate": math.ceil(serialized_event_bytes / 4),
        },
        "lastCheckpoint": {
            "triggerEventRefs": [], "outcome": "NONE", "eventRef": None,
        },
        "currentStatus": terminal_status,
        "observability": "OPAQUE_PROVIDER_BOUNDARY" if completed and not started else "HOST_BOUNDARIES",
        "truncations": sorted(truncations, key=lambda item: item["field"]),
        "ledgerHash": "",
    }
    ledger["ledgerHash"] = ledger_hash(ledger)
    validate_ledger_shape(ledger, mission)
    return ledger


def validate_ledger_shape(ledger: dict[str, Any], mission: dict[str, Any]) -> None:
    reject_raw_fields(ledger)
    required = {
        "schemaVersion", "ledgerId", "missionId", "missionHash",
        "missionRevision", "sourceEvents", "coveredGoalRefs",
        "openEvidenceGapRefs", "resolvedEvidenceGapRefs", "evidenceGaps",
        "currentSearchScopeRef", "visitedScopeRefs", "evidenceAddedSinceCheckpoint",
        "rejectedHypothesisRefs", "openDecisionRefs",
        "scopeExpansionProposalRefs", "repeatedTargetCounters",
        "noNewEvidenceStreak", "providerCounters", "budgetConsumption",
        "lastCheckpoint", "currentStatus", "observability", "truncations",
        "ledgerHash",
    }
    exact_keys(ledger, required, "ledger")
    if ledger["schemaVersion"] != LEDGER_SCHEMA:
        raise StateError("ledger: unsupported schema version")
    if ledger["missionId"] != mission["missionId"] or ledger["missionHash"] != mission["contentHash"] or ledger["missionRevision"] != mission["revision"]:
        raise StateError("ledger: mission correlation failed")
    if not isinstance(ledger["ledgerId"], str) or not re.fullmatch(r"ledger-[0-9a-f]{24}", ledger["ledgerId"]):
        raise StateError("ledger.ledgerId: invalid")
    ref_limits = {
        "coveredGoalRefs": mission["hardBudgets"]["maxLedgerRefs"],
        "openEvidenceGapRefs": mission["hardBudgets"]["maxLedgerRefs"],
        "resolvedEvidenceGapRefs": mission["hardBudgets"]["maxLedgerRefs"],
        "visitedScopeRefs": mission["hardBudgets"]["maxVisitedScopeRefs"],
        "evidenceAddedSinceCheckpoint": mission["hardBudgets"]["maxEvidenceRefs"],
        "rejectedHypothesisRefs": mission["hardBudgets"]["maxLedgerRefs"],
        "openDecisionRefs": mission["hardBudgets"]["maxLedgerRefs"],
        "scopeExpansionProposalRefs": mission["hardBudgets"]["maxLedgerRefs"],
    }
    for key, maximum in ref_limits.items():
        refs(ledger[key], f"ledger.{key}", maximum)
    if not set(ledger["coveredGoalRefs"]) <= set(mission["acceptanceCriterionRefs"]):
        raise StateError("ledger.coveredGoalRefs contains an unknown goal")
    gap_ids = {gap["gapId"] for gap in ledger["evidenceGaps"]}
    if set(ledger["openEvidenceGapRefs"]) | set(ledger["resolvedEvidenceGapRefs"]) != gap_ids:
        raise StateError("ledger evidence-gap indexes do not cover the current gap state")
    for gap in ledger["evidenceGaps"]:
        validate_gap(gap, set(mission["acceptanceCriterionRefs"]), set(mission["mandatoryConstraintRefs"]), "ledger.evidenceGap")
    if ledger["currentSearchScopeRef"] is not None:
        valid_ref(ledger["currentSearchScopeRef"], "ledger.currentSearchScopeRef")
    for counter_group in (ledger["providerCounters"], ledger["budgetConsumption"]):
        if not isinstance(counter_group, dict):
            raise StateError("ledger counters must be objects")
        for value in counter_group.values():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise StateError("ledger counters must be monotonic non-negative integers")
    if not isinstance(ledger["noNewEvidenceStreak"], int) or ledger["noNewEvidenceStreak"] < 0:
        raise StateError("ledger.noNewEvidenceStreak must be non-negative")
    if ledger["lastCheckpoint"] != {"triggerEventRefs": [], "outcome": "NONE", "eventRef": None}:
        raise StateError("TG03 ledger cannot claim a checkpoint outcome")
    if ledger["currentStatus"] not in {"ACTIVE", "COMPLETED", "STOPPED", "FAILED"}:
        raise StateError("ledger.currentStatus is invalid")
    if ledger["observability"] not in {"HOST_BOUNDARIES", "OPAQUE_PROVIDER_BOUNDARY"}:
        raise StateError("ledger.observability is invalid")
    if not isinstance(ledger["ledgerHash"], str) or not HASH_PATTERN.fullmatch(ledger["ledgerHash"]):
        raise StateError("ledger.ledgerHash is invalid")
    if ledger["ledgerHash"] != ledger_hash(ledger):
        raise StateError("ledger.ledgerHash integrity check failed")


def validate_ledger(ledger: dict[str, Any], mission: dict[str, Any], events: list[dict[str, Any]]) -> None:
    validate_ledger_shape(ledger, mission)
    expected = derive_ledger(mission, events)
    if canonical_bytes(ledger) != canonical_bytes(expected):
        raise StateError("ledger is not deterministically derivable from the mission and events")


def normalize_checkpoint_input(
    value: dict[str, Any], mission: dict[str, Any], ledger: dict[str, Any]
) -> dict[str, Any]:
    exact_keys(value, {"schemaVersion", "triggerReasons", "nextActionProposals"}, "checkpointInput")
    if value["schemaVersion"] != CHECKPOINT_INPUT_SCHEMA:
        raise StateError("checkpointInput: unsupported schema version")
    reasons = refs(value["triggerReasons"], "checkpointInput.triggerReasons", 32)
    actions = value["nextActionProposals"]
    if not isinstance(actions, list) or len(actions) > 16:
        raise StateError("checkpointInput.nextActionProposals must contain at most 16 actions")
    normalized_actions = []
    action_keys = {
        "actionId", "actionKind", "targetScopeRef", "justificationGoalRefs",
        "justificationGapRefs", "mandatoryConstraintRefs", "expectedEvidence",
        "decisionDependencies", "scopeExpansionRequired", "estimatedBudgetDelta",
    }
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise StateError(f"checkpointInput.nextActionProposals[{index}] must be an object")
        exact_keys(action, action_keys, f"checkpointInput.nextActionProposals[{index}]")
        goals = refs(action["justificationGoalRefs"], f"action[{index}].justificationGoalRefs")
        gaps = refs(action["justificationGapRefs"], f"action[{index}].justificationGapRefs")
        constraints = refs(action["mandatoryConstraintRefs"], f"action[{index}].mandatoryConstraintRefs")
        if not goals and not gaps and not constraints:
            raise StateError(f"action[{index}] has no active mission justification")
        if not set(goals) <= set(mission["acceptanceCriterionRefs"]):
            raise StateError(f"action[{index}] references an unknown goal")
        if not set(gaps) <= set(ledger["openEvidenceGapRefs"]):
            raise StateError(f"action[{index}] references a gap that is not currently open")
        if not set(constraints) <= set(mission["mandatoryConstraintRefs"]):
            raise StateError(f"action[{index}] references an unknown constraint")
        target = valid_ref(action["targetScopeRef"], f"action[{index}].targetScopeRef")
        expansion = action["scopeExpansionRequired"]
        if not isinstance(expansion, bool):
            raise StateError(f"action[{index}].scopeExpansionRequired must be boolean")
        if target not in mission["allowedEvidenceScopeRefs"] and not expansion:
            raise StateError(f"action[{index}] enters an unapproved scope without an expansion proposal")
        delta = action["estimatedBudgetDelta"]
        if not isinstance(delta, dict) or set(delta) != {"providerCalls", "tokenProxy"}:
            raise StateError(f"action[{index}].estimatedBudgetDelta has invalid fields")
        for amount in delta.values():
            if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
                raise StateError(f"action[{index}].estimatedBudgetDelta must be non-negative")
        normalized_actions.append({
            "actionId": valid_ref(action["actionId"], f"action[{index}].actionId"),
            "actionKind": valid_ref(action["actionKind"], f"action[{index}].actionKind"),
            "targetScopeRef": target,
            "justificationGoalRefs": goals,
            "justificationGapRefs": gaps,
            "mandatoryConstraintRefs": constraints,
            "expectedEvidence": bounded_text(action["expectedEvidence"], f"action[{index}].expectedEvidence", 512),
            "decisionDependencies": refs(action["decisionDependencies"], f"action[{index}].decisionDependencies"),
            "scopeExpansionRequired": expansion,
            "estimatedBudgetDelta": {
                "providerCalls": delta["providerCalls"], "tokenProxy": delta["tokenProxy"],
            },
        })
    normalized_actions.sort(key=lambda item: item["actionId"])
    if len({item["actionId"] for item in normalized_actions}) != len(normalized_actions):
        raise StateError("checkpointInput contains duplicate action IDs")
    return {
        "schemaVersion": CHECKPOINT_INPUT_SCHEMA,
        "triggerReasons": reasons,
        "nextActionProposals": normalized_actions,
    }


def envelope_with_measurements(envelope: dict[str, Any]) -> dict[str, Any]:
    for _ in range(16):
        size = len(canonical_bytes(envelope))
        token_proxy = math.ceil(size / 4)
        current = envelope["measurements"]
        if current["serializedBytes"] == size and current["tokenProxyEstimate"] == token_proxy:
            return envelope
        current["serializedBytes"] = size
        current["tokenProxyEstimate"] = token_proxy
        current["softLimitExceeded"] = (
            size > current["softByteLimit"]
            or token_proxy > current["softTokenProxyLimit"]
        )
    raise StateError("checkpoint envelope measurements did not converge")


def build_envelope(
    mission: dict[str, Any],
    ledger: dict[str, Any],
    events: list[dict[str, Any]],
    checkpoint_input: dict[str, Any],
) -> dict[str, Any]:
    validate_ledger(ledger, mission, events)
    normalized_input = normalize_checkpoint_input(checkpoint_input, mission, ledger)
    evidence_events = [event for event in events if event["evidenceAddedRefs"]]
    maximum = mission["hardBudgets"]["maxEnvelopeEvidenceEvents"]
    selected = evidence_events[-maximum:]
    delta = [{
        "eventRef": event["eventId"],
        "sequence": event["sequence"],
        "targetScopeRef": event["targetScopeRef"],
        "acceptanceCriterionRefs": event["acceptanceCriterionRefs"],
        "evidenceGapRefs": event["evidenceGapRefs"],
        "evidenceAddedRefs": event["evidenceAddedRefs"],
    } for event in selected]
    soft = mission["softBudgets"]
    hard = mission["hardBudgets"]
    envelope: dict[str, Any] = {
        "schemaVersion": ENVELOPE_SCHEMA,
        "missionContract": copy.deepcopy(mission),
        "ledgerSnapshot": copy.deepcopy(ledger),
        "evidenceDelta": delta,
        "evidenceDeltaTruncatedCount": len(evidence_events) - len(selected),
        "triggerReasons": normalized_input["triggerReasons"],
        "nextActionProposals": normalized_input["nextActionProposals"],
        "measurements": {
            "serializedBytes": 0,
            "tokenProxyEstimate": 0,
            "softByteLimit": soft["maxEnvelopeBytes"],
            "hardByteLimit": hard["maxEnvelopeBytes"],
            "softTokenProxyLimit": soft["maxEnvelopeTokenProxy"],
            "hardTokenProxyLimit": hard["maxEnvelopeTokenProxy"],
            "softLimitExceeded": False,
        },
    }
    envelope_with_measurements(envelope)
    measurements = envelope["measurements"]
    if measurements["serializedBytes"] > measurements["hardByteLimit"]:
        raise StateError("checkpoint envelope exceeds hard byte limit")
    if measurements["tokenProxyEstimate"] > measurements["hardTokenProxyLimit"]:
        raise StateError("checkpoint envelope exceeds hard token-proxy limit")
    validate_envelope_shape(envelope)
    return envelope


def validate_envelope_shape(envelope: dict[str, Any]) -> None:
    reject_raw_fields(envelope)
    exact_keys(envelope, {
        "schemaVersion", "missionContract", "ledgerSnapshot", "evidenceDelta",
        "evidenceDeltaTruncatedCount", "triggerReasons", "nextActionProposals",
        "measurements",
    }, "envelope")
    if envelope["schemaVersion"] != ENVELOPE_SCHEMA:
        raise StateError("envelope: unsupported schema version")
    validate_mission(envelope["missionContract"])
    validate_ledger_shape(envelope["ledgerSnapshot"], envelope["missionContract"])
    if not isinstance(envelope["evidenceDelta"], list):
        raise StateError("envelope.evidenceDelta must be an array")
    if not isinstance(envelope["evidenceDeltaTruncatedCount"], int) or envelope["evidenceDeltaTruncatedCount"] < 0:
        raise StateError("envelope.evidenceDeltaTruncatedCount must be non-negative")
    measurements = envelope["measurements"]
    measurement_keys = {
        "serializedBytes", "tokenProxyEstimate", "softByteLimit", "hardByteLimit",
        "softTokenProxyLimit", "hardTokenProxyLimit", "softLimitExceeded",
    }
    if not isinstance(measurements, dict):
        raise StateError("envelope.measurements must be an object")
    exact_keys(measurements, measurement_keys, "envelope.measurements")
    actual = len(canonical_bytes(envelope))
    if measurements["serializedBytes"] != actual or measurements["tokenProxyEstimate"] != math.ceil(actual / 4):
        raise StateError("envelope measurements do not match serialized content")
    if actual > measurements["hardByteLimit"] or measurements["tokenProxyEstimate"] > measurements["hardTokenProxyLimit"]:
        raise StateError("envelope exceeds a hard budget")


def validate_envelope(
    envelope: dict[str, Any],
    mission: dict[str, Any],
    ledger: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    validate_envelope_shape(envelope)
    checkpoint_input = {
        "schemaVersion": CHECKPOINT_INPUT_SCHEMA,
        "triggerReasons": envelope["triggerReasons"],
        "nextActionProposals": envelope["nextActionProposals"],
    }
    expected = build_envelope(mission, ledger, events, checkpoint_input)
    if canonical_bytes(envelope) != canonical_bytes(expected):
        raise StateError("envelope is not deterministically derivable from supplied state")


def command_create_mission(args: argparse.Namespace) -> None:
    mission = build_mission(load_json(Path(args.story)), load_json(Path(args.seed)))
    history = build_history(mission)
    validate_history(history)
    atomic_write(Path(args.mission), mission)
    atomic_write(Path(args.history), history)


def command_revise_mission(args: argparse.Namespace) -> None:
    history = load_json(Path(args.history))
    request = load_json(Path(args.request))
    mission, updated = revise_mission(history, request)
    atomic_write(Path(args.history), updated)
    atomic_write(Path(args.mission), mission)


def command_derive_ledger(args: argparse.Namespace) -> None:
    mission = load_json(Path(args.mission))
    events = read_events(Path(args.events))
    atomic_write(Path(args.ledger), derive_ledger(mission, events))


def command_build_envelope(args: argparse.Namespace) -> None:
    mission = load_json(Path(args.mission))
    ledger = load_json(Path(args.ledger))
    events = read_events(Path(args.events))
    checkpoint_input = load_json(Path(args.checkpoint_input))
    atomic_write(Path(args.envelope), build_envelope(mission, ledger, events, checkpoint_input))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-mission")
    create.add_argument("story")
    create.add_argument("seed")
    create.add_argument("mission")
    create.add_argument("history")
    create.set_defaults(function=command_create_mission)

    validate_mission_parser = commands.add_parser("validate-mission")
    validate_mission_parser.add_argument("mission")
    validate_mission_parser.set_defaults(function=lambda args: validate_mission(load_json(Path(args.mission))))

    validate_history_parser = commands.add_parser("validate-history")
    validate_history_parser.add_argument("history")
    validate_history_parser.set_defaults(function=lambda args: validate_history(load_json(Path(args.history))))

    revise = commands.add_parser("revise-mission")
    revise.add_argument("history")
    revise.add_argument("request")
    revise.add_argument("mission")
    revise.set_defaults(function=command_revise_mission)

    derive = commands.add_parser("derive-ledger")
    derive.add_argument("mission")
    derive.add_argument("events")
    derive.add_argument("ledger")
    derive.set_defaults(function=command_derive_ledger)

    validate_ledger_parser = commands.add_parser("validate-ledger")
    validate_ledger_parser.add_argument("mission")
    validate_ledger_parser.add_argument("events")
    validate_ledger_parser.add_argument("ledger")
    validate_ledger_parser.set_defaults(function=lambda args: validate_ledger(
        load_json(Path(args.ledger)), load_json(Path(args.mission)), read_events(Path(args.events))))

    build = commands.add_parser("build-envelope")
    build.add_argument("mission")
    build.add_argument("ledger")
    build.add_argument("events")
    build.add_argument("checkpoint_input")
    build.add_argument("envelope")
    build.set_defaults(function=command_build_envelope)

    validate_envelope_parser = commands.add_parser("validate-envelope")
    validate_envelope_parser.add_argument("mission")
    validate_envelope_parser.add_argument("ledger")
    validate_envelope_parser.add_argument("events")
    validate_envelope_parser.add_argument("envelope")
    validate_envelope_parser.set_defaults(function=lambda args: validate_envelope(
        load_json(Path(args.envelope)), load_json(Path(args.mission)),
        load_json(Path(args.ledger)), read_events(Path(args.events))))

    args = parser.parse_args()
    try:
        args.function(args)
        return 0
    except (OSError, StateError) as error:
        print(f"ERROR: Analysis Trajectory state: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
