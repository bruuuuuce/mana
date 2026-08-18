#!/usr/bin/env python3
"""TG05 compact, schema-bound, bounded trajectory checkpoint governor.

This host-side helper composes an authoritative checkpoint request, renders the
smallest sufficient model prompt, validates responses, and records bounded
fixture/live-smoke results.  It contains no provider or network dispatch and
does not alter the public Story Start control flow.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any


CONFIG_SCHEMA = "mana.analysis-trajectory.checkpoint-governor-config/v1"
REQUEST_SCHEMA = "mana.analysis-trajectory.trajectory-checkpoint-request/v1"
RESPONSE_SCHEMA = "mana.analysis-trajectory.trajectory-checkpoint-response/v1"
VALIDATION_SCHEMA = "mana.analysis-trajectory.trajectory-checkpoint-validation/v1"
RUN_SCHEMA = "mana.analysis-trajectory.trajectory-checkpoint-run/v1"

OUTCOMES = (
    "ON_TRACK",
    "REANCHOR_REQUIRED",
    "SCOPE_TRIAGE_REQUIRED",
    "STOP_SUFFICIENT_EVIDENCE",
    "STOP_NO_NEW_EVIDENCE",
    "STOP_HARD_BUDGET",
    "NEEDS_OWNER_REVIEW",
)
STOP_REASONS = (
    "EVIDENCE_SUFFICIENT",
    "NO_PRODUCTIVE_NEXT_STEP",
    "HARD_BUDGET_REACHED",
    "OWNER_REVIEW_REQUIRED",
)
SUPPORT_KEYS = (
    "eventRefs", "evidenceRefs", "goalRefs", "gapRefs", "actionRefs",
    "scopeRefs", "decisionRefs", "constraintRefs",
)
IMPLEMENTATION_LEAKAGE = re.compile(
    r"\b(?:implement|implementation|coding[- ]task|write[- ]code|modify[- ]file|"
    r"create[- ]task|pull[- ]request|story[- ]point|person[- ](?:hour|day)|"
    r"engineering[- ]estimate|estimate|estimation)\b",
    re.IGNORECASE,
)
DECISION_LEAKAGE = re.compile(
    r"\b(?:choose|chose|select|selected|commit|committed|adopt|adopted|assume|assumed)\b"
    r".{0,80}\b(?:architecture|product|option|decision|delivery[- ]mode)\b",
    re.IGNORECASE,
)

PRIMARY_INSTRUCTIONS = """MANA TRAJECTORY CHECKPOINT v1
Return exactly one JSON object conforming to the supplied response schema.
The Mission Contract is immutable and host-owned. Do not add fields or rewrite it.

Perform only this bounded checkpoint task:
1. Restate the current objective concisely.
2. Identify the active goal, mandatory constraint, or evidence gap being served.
3. Classify the current trajectory using exactly one permitted outcome.
4. Choose at most one supplied next-action option and justify it only with existing refs.
5. Represent a new scope only as an owner-approved scope-expansion proposal.
6. Keep every open decision open; do not choose a product or architecture option.
7. Stop when evidence is sufficient or no productive referenced next step exists.
8. Do not create implementation scope, implementation tasks, plans, estimates, or code.

Do not infer provider-internal activity. Do not return chain-of-thought, repository
content, conversation history, prompt history, secrets, source text, or prose outside
the response JSON.

BOUNDED_CHECKPOINT_REQUEST_JSON:
"""

REPAIR_INSTRUCTIONS = """MANA TRAJECTORY CHECKPOINT STRUCTURAL REPAIR v1
This is the only permitted repair call. Correct schema/structure only.
Do not perform new semantic exploration and do not add facts or refs.
Return exactly one JSON object conforming to the supplied response schema.
The only inputs are the original bounded request and sanitized validation error codes.

SANITIZED_VALIDATION_ERRORS_JSON:
"""


def load_module(filename: str, module_name: str) -> Any:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load host module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STATE = load_module("analysis-trajectory-state.py", "analysis_trajectory_state")
DRIFT = load_module("analysis-trajectory-drift.py", "analysis_trajectory_drift")


class CheckpointError(ValueError):
    """A deterministic TG05 contract, policy, or integrity failure."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def exact_keys(value: Any, expected: set[str], location: str) -> None:
    if not isinstance(value, dict):
        raise CheckpointError(f"{location}: expected an object")
    actual = set(value)
    if actual != expected:
        raise CheckpointError(
            f"{location}: fields differ; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def trusted_json(path: Path) -> dict[str, Any]:
    try:
        return STATE.load_json(path)
    except STATE.StateError as error:
        raise CheckpointError(str(error)) from error


def refs(value: Any, location: str, maximum: int = 256) -> list[str]:
    try:
        return STATE.refs(value, location, maximum)
    except STATE.StateError as error:
        raise CheckpointError(str(error)) from error


def valid_ref(value: Any, location: str) -> str:
    try:
        return STATE.valid_ref(value, location)
    except STATE.StateError as error:
        raise CheckpointError(str(error)) from error


def bounded_text(value: Any, location: str, maximum: int) -> str:
    try:
        return STATE.bounded_text(value, location, maximum)
    except STATE.StateError as error:
        raise CheckpointError(str(error)) from error


def atomic_write_text(path: Path, value: str) -> None:
    if path.is_symlink():
        raise CheckpointError(f"refusing unsafe output symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    exact_keys(
        value,
        {"schemaVersion", "enabled", "mode", "maxPrimaryCalls", "maxStructuralRepairCalls"},
        "config",
    )
    if value["schemaVersion"] != CONFIG_SCHEMA:
        raise CheckpointError("config: unsupported schema version")
    if value["mode"] not in {"OFF", "SHADOW"}:
        raise CheckpointError("config.mode: expected OFF or SHADOW")
    if not isinstance(value["enabled"], bool):
        raise CheckpointError("config.enabled: expected boolean")
    if (value["mode"] == "OFF") != (value["enabled"] is False):
        raise CheckpointError("config enabled/mode markers disagree")
    if value["maxPrimaryCalls"] != 1 or value["maxStructuralRepairCalls"] != 1:
        raise CheckpointError("TG05 call maxima are fixed at one primary and one structural repair")
    return copy.deepcopy(value)


def primary_prompt(request: dict[str, Any]) -> str:
    return PRIMARY_INSTRUCTIONS + canonical_bytes(request).decode("utf-8") + "\n"


def repair_prompt(request: dict[str, Any], validation: dict[str, Any]) -> str:
    sanitized = {"errors": validation["errors"]}
    return (
        REPAIR_INSTRUCTIONS
        + canonical_bytes(sanitized).decode("utf-8")
        + "\n\nORIGINAL_BOUNDED_REQUEST_JSON:\n"
        + canonical_bytes(request).decode("utf-8")
        + "\n"
    )


def remaining_budget(consumed: int, soft: int, hard: int) -> dict[str, int]:
    return {
        "consumed": consumed,
        "softRemaining": max(soft - consumed, 0),
        "hardRemaining": max(hard - consumed, 0),
    }


def request_hash(value: dict[str, Any]) -> str:
    unhashed = copy.deepcopy(value)
    unhashed.pop("requestHash", None)
    return digest(unhashed)


def request_id(
    mission: dict[str, Any], ledger: dict[str, Any], recommendation: dict[str, Any]
) -> str:
    identity = {
        "missionHash": mission["contentHash"],
        "ledgerHash": ledger["ledgerHash"],
        "recommendationHash": recommendation["recommendationHash"],
    }
    return "checkpoint-" + hashlib.sha256(canonical_bytes(identity)).hexdigest()[:24]


def validate_action_options(
    actions: list[dict[str, Any]], mission: dict[str, Any], ledger: dict[str, Any],
    hard_provider_remaining: int,
) -> None:
    allowed = set(mission["allowedEvidenceScopeRefs"])
    candidates = set(mission["scopePolicy"]["proposedExpansionScopeRefs"])
    open_decisions = set(ledger["openDecisionRefs"])
    for index, action in enumerate(actions):
        if IMPLEMENTATION_LEAKAGE.search(action["actionKind"]) or IMPLEMENTATION_LEAKAGE.search(action["expectedEvidence"]):
            raise CheckpointError(f"nextActionProposals[{index}] leaks implementation work")
        if not set(action["decisionDependencies"]) <= open_decisions:
            raise CheckpointError(f"nextActionProposals[{index}] has an unknown decision dependency")
        if action["scopeExpansionRequired"]:
            if action["targetScopeRef"] not in candidates:
                raise CheckpointError(f"nextActionProposals[{index}] is not an available expansion choice")
        elif action["targetScopeRef"] not in allowed:
            raise CheckpointError(f"nextActionProposals[{index}] silently enters an unapproved scope")
        if action["estimatedBudgetDelta"]["providerCalls"] > max(hard_provider_remaining - 1, 0):
            raise CheckpointError(f"nextActionProposals[{index}] exceeds the remaining provider budget")


def build_request(
    mission: dict[str, Any], ledger: dict[str, Any], events: list[dict[str, Any]],
    drift_config: dict[str, Any], observation: dict[str, Any],
    checkpoint_input: dict[str, Any], recommendation: dict[str, Any],
) -> dict[str, Any]:
    try:
        STATE.validate_ledger(ledger, mission, events)
        DRIFT.validate_recommendation(recommendation)
        expected_recommendation = DRIFT.analyze(
            mission, ledger, events, drift_config, observation
        )
    except (STATE.StateError, DRIFT.DriftError) as error:
        raise CheckpointError(str(error)) from error
    if canonical_bytes(recommendation) != canonical_bytes(expected_recommendation):
        raise CheckpointError("trigger recommendation is not derivable from authoritative TG04 inputs")
    if (
        recommendation["outcome"] != "CHECKPOINT_RECOMMENDED"
        or recommendation["modelCheckpointPermittedInTG05"] is not True
        or not recommendation["reasonCodes"]
    ):
        raise CheckpointError("TG04 recommendation does not permit a TG05 checkpoint")
    try:
        envelope = STATE.build_envelope(mission, ledger, events, checkpoint_input)
    except STATE.StateError as error:
        raise CheckpointError(str(error)) from error
    if envelope["triggerReasons"] != recommendation["reasonCodes"]:
        raise CheckpointError("checkpoint trigger reasons do not match the TG04 recommendation")

    provider_consumed = ledger["budgetConsumption"]["providerIterations"]
    hard_provider_remaining = max(
        mission["hardBudgets"]["maxProviderIterations"] - provider_consumed, 0
    )
    if hard_provider_remaining < 1:
        raise CheckpointError("no hard provider-call budget remains for the primary checkpoint")
    validate_action_options(
        envelope["nextActionProposals"], mission, ledger, hard_provider_remaining
    )

    events_by_id = {event["eventId"]: event for event in events}
    active_rejections = []
    for rejection_ref in ledger["rejectedHypothesisRefs"]:
        event = events_by_id.get(rejection_ref)
        if event is None or event["eventType"] != "hypothesis_rejected":
            raise CheckpointError("Ledger contains an unresolvable rejected-hypothesis ref")
        active_rejections.append({
            "rejectionEventRef": rejection_ref,
            "targetScopeRef": event["targetScopeRef"],
        })
    active_rejections.sort(key=lambda item: item["rejectionEventRef"])

    consumption = ledger["budgetConsumption"]
    soft = mission["softBudgets"]
    hard = mission["hardBudgets"]
    placeholder_hash = "sha256:" + "0" * 64
    value: dict[str, Any] = {
        "schemaVersion": REQUEST_SCHEMA,
        "requestId": request_id(mission, ledger, recommendation),
        "requestHash": placeholder_hash,
        "mode": "SHADOW",
        "advisory": True,
        "checkpointEnvelope": envelope,
        "triggerRecommendation": {
            "recommendationId": recommendation["recommendationId"],
            "recommendationHash": recommendation["recommendationHash"],
            "outcome": recommendation["outcome"],
            "reasonCodes": copy.deepcopy(recommendation["reasonCodes"]),
            "supportingRefs": copy.deepcopy(recommendation["supportingRefs"]),
            "observedBoundary": recommendation["observedBoundary"],
        },
        "hostValidationContext": {
            "knownEvidenceRefs": copy.deepcopy(ledger["evidenceAddedSinceCheckpoint"]),
            "openDecisionRefs": copy.deepcopy(ledger["openDecisionRefs"]),
            "activeRejectedHypotheses": active_rejections,
        },
        "remainingBudgets": {
            "eventCount": remaining_budget(
                consumption["eventCount"], soft["maxEvents"], hard["maxEvents"]
            ),
            "providerIterations": remaining_budget(
                provider_consumed, soft["maxProviderIterations"], hard["maxProviderIterations"]
            ),
            "visitedScopeRefs": remaining_budget(
                consumption["visitedScopeCount"], soft["maxVisitedScopeRefs"], hard["maxVisitedScopeRefs"]
            ),
            "evidenceRefs": remaining_budget(
                consumption["evidenceRefCount"], soft["maxEvidenceRefs"], hard["maxEvidenceRefs"]
            ),
            "checkpointBytes": remaining_budget(0, soft["maxEnvelopeBytes"], hard["maxEnvelopeBytes"]),
            "checkpointTokenProxy": remaining_budget(0, soft["maxEnvelopeTokenProxy"], hard["maxEnvelopeTokenProxy"]),
        },
        "permittedOutcomes": list(OUTCOMES),
        "supportedStopReasons": list(STOP_REASONS),
        "scopeExpansionRules": {
            "candidateScopeRefs": copy.deepcopy(mission["scopePolicy"]["proposedExpansionScopeRefs"]),
            "ownerApprovalRequired": True,
            "directMissionMutationPermitted": False,
        },
        "callPolicy": {
            "primaryCallsPerTrigger": 1,
            "structuralRepairCallsPerTrigger": 1 if hard_provider_remaining >= 2 else 0,
            "semanticRetryPermitted": False,
            "periodicCallsPermitted": False,
        },
        "promptMeasurements": {
            "requestBytes": 0,
            "requestTokenProxy": 0,
            "promptBytes": 0,
            "promptTokenProxy": 0,
            "softByteLimit": soft["maxEnvelopeBytes"],
            "hardByteLimit": hard["maxEnvelopeBytes"],
            "softTokenProxyLimit": soft["maxEnvelopeTokenProxy"],
            "hardTokenProxyLimit": hard["maxEnvelopeTokenProxy"],
            "softLimitExceeded": False,
        },
    }
    for _ in range(32):
        request_bytes = len(canonical_bytes(value))
        request_tokens = math.ceil(request_bytes / 4)
        prompt_bytes = len(primary_prompt(value).encode("utf-8"))
        prompt_tokens = math.ceil(prompt_bytes / 4)
        new_measurements = {
            "requestBytes": request_bytes,
            "requestTokenProxy": request_tokens,
            "promptBytes": prompt_bytes,
            "promptTokenProxy": prompt_tokens,
            "softByteLimit": soft["maxEnvelopeBytes"],
            "hardByteLimit": hard["maxEnvelopeBytes"],
            "softTokenProxyLimit": soft["maxEnvelopeTokenProxy"],
            "hardTokenProxyLimit": hard["maxEnvelopeTokenProxy"],
            "softLimitExceeded": any((
                envelope["measurements"]["serializedBytes"] > soft["maxEnvelopeBytes"],
                envelope["measurements"]["tokenProxyEstimate"] > soft["maxEnvelopeTokenProxy"],
                request_bytes > soft["maxEnvelopeBytes"],
                request_tokens > soft["maxEnvelopeTokenProxy"],
                prompt_bytes > soft["maxEnvelopeBytes"],
                prompt_tokens > soft["maxEnvelopeTokenProxy"],
            )),
        }
        new_byte_budget = remaining_budget(
            prompt_bytes, soft["maxEnvelopeBytes"], hard["maxEnvelopeBytes"]
        )
        new_token_budget = remaining_budget(
            prompt_tokens, soft["maxEnvelopeTokenProxy"], hard["maxEnvelopeTokenProxy"]
        )
        if (
            value["promptMeasurements"] == new_measurements
            and value["remainingBudgets"]["checkpointBytes"] == new_byte_budget
            and value["remainingBudgets"]["checkpointTokenProxy"] == new_token_budget
        ):
            break
        value["promptMeasurements"] = new_measurements
        value["remainingBudgets"]["checkpointBytes"] = new_byte_budget
        value["remainingBudgets"]["checkpointTokenProxy"] = new_token_budget
    else:
        raise CheckpointError("checkpoint request/prompt measurements did not converge")
    measurements = value["promptMeasurements"]
    if (
        measurements["requestBytes"] > measurements["hardByteLimit"]
        or measurements["promptBytes"] > measurements["hardByteLimit"]
        or measurements["requestTokenProxy"] > measurements["hardTokenProxyLimit"]
        or measurements["promptTokenProxy"] > measurements["hardTokenProxyLimit"]
    ):
        raise CheckpointError("checkpoint request or prompt exceeds a TG03 hard envelope budget")
    value["requestHash"] = request_hash(value)
    validate_request_shape(value)
    return value


def validate_remaining_budget(value: Any, location: str) -> None:
    exact_keys(value, {"consumed", "softRemaining", "hardRemaining"}, location)
    for key in ("consumed", "softRemaining", "hardRemaining"):
        amount = value[key]
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise CheckpointError(f"{location}.{key}: expected a non-negative integer")


def validate_request_shape(value: dict[str, Any]) -> None:
    try:
        STATE.reject_raw_fields(value)
    except STATE.StateError as error:
        raise CheckpointError(str(error)) from error
    exact_keys(value, {
        "schemaVersion", "requestId", "requestHash", "mode", "advisory",
        "checkpointEnvelope", "triggerRecommendation", "hostValidationContext",
        "remainingBudgets", "permittedOutcomes", "supportedStopReasons",
        "scopeExpansionRules", "callPolicy", "promptMeasurements",
    }, "request")
    if value["schemaVersion"] != REQUEST_SCHEMA or value["mode"] != "SHADOW" or value["advisory"] is not True:
        raise CheckpointError("request schema or shadow/advisory marker is invalid")
    if not isinstance(value["requestId"], str) or not re.fullmatch(r"checkpoint-[0-9a-f]{24}", value["requestId"]):
        raise CheckpointError("request.requestId is invalid")
    if value["requestHash"] != request_hash(value):
        raise CheckpointError("request hash integrity check failed")
    envelope = value["checkpointEnvelope"]
    try:
        STATE.validate_envelope_shape(envelope)
    except STATE.StateError as error:
        raise CheckpointError(str(error)) from error
    mission = envelope["missionContract"]
    ledger = envelope["ledgerSnapshot"]

    trigger = value["triggerRecommendation"]
    exact_keys(trigger, {
        "recommendationId", "recommendationHash", "outcome", "reasonCodes",
        "supportingRefs", "observedBoundary",
    }, "request.triggerRecommendation")
    valid_ref(trigger["recommendationId"], "request.triggerRecommendation.recommendationId")
    if not isinstance(trigger["recommendationHash"], str) or not STATE.HASH_PATTERN.fullmatch(trigger["recommendationHash"]):
        raise CheckpointError("request trigger recommendation hash is invalid")
    if trigger["outcome"] != "CHECKPOINT_RECOMMENDED":
        raise CheckpointError("request trigger is not checkpoint-recommended")
    trigger_reasons = refs(trigger["reasonCodes"], "request.triggerRecommendation.reasonCodes", 11)
    if not trigger_reasons or trigger_reasons != envelope["triggerReasons"]:
        raise CheckpointError("request trigger reasons are empty or disagree with the envelope")
    if not isinstance(trigger["observedBoundary"], str) or not 1 <= len(trigger["observedBoundary"]) <= 128:
        raise CheckpointError("request trigger observed boundary is invalid")
    exact_keys(trigger["supportingRefs"], set(SUPPORT_KEYS), "request.triggerRecommendation.supportingRefs")
    for key in SUPPORT_KEYS:
        refs(trigger["supportingRefs"][key], f"request.triggerRecommendation.supportingRefs.{key}")

    context = value["hostValidationContext"]
    exact_keys(context, {"knownEvidenceRefs", "openDecisionRefs", "activeRejectedHypotheses"}, "request.hostValidationContext")
    known_evidence = refs(context["knownEvidenceRefs"], "request.hostValidationContext.knownEvidenceRefs")
    open_decisions = refs(context["openDecisionRefs"], "request.hostValidationContext.openDecisionRefs")
    if known_evidence != ledger["evidenceAddedSinceCheckpoint"] or open_decisions != ledger["openDecisionRefs"]:
        raise CheckpointError("request host validation refs disagree with the Ledger")
    rejected = context["activeRejectedHypotheses"]
    if not isinstance(rejected, list) or len(rejected) > 256:
        raise CheckpointError("request active rejected hypotheses are invalid")
    rejected_refs = []
    for index, item in enumerate(rejected):
        exact_keys(item, {"rejectionEventRef", "targetScopeRef"}, f"request.activeRejectedHypotheses[{index}]")
        rejected_refs.append(valid_ref(item["rejectionEventRef"], f"request.activeRejectedHypotheses[{index}].rejectionEventRef"))
        valid_ref(item["targetScopeRef"], f"request.activeRejectedHypotheses[{index}].targetScopeRef")
    if rejected_refs != sorted(rejected_refs) or rejected_refs != ledger["rejectedHypothesisRefs"]:
        raise CheckpointError("request rejected hypotheses disagree with the Ledger")

    if value["permittedOutcomes"] != list(OUTCOMES) or value["supportedStopReasons"] != list(STOP_REASONS):
        raise CheckpointError("request closed outcome/stop-reason sets are invalid")
    scope_rules = value["scopeExpansionRules"]
    exact_keys(scope_rules, {"candidateScopeRefs", "ownerApprovalRequired", "directMissionMutationPermitted"}, "request.scopeExpansionRules")
    if (
        refs(scope_rules["candidateScopeRefs"], "request.scopeExpansionRules.candidateScopeRefs")
        != mission["scopePolicy"]["proposedExpansionScopeRefs"]
        or scope_rules["ownerApprovalRequired"] is not True
        or scope_rules["directMissionMutationPermitted"] is not False
    ):
        raise CheckpointError("request scope-expansion rules are invalid")

    budgets = value["remainingBudgets"]
    budget_keys = {
        "eventCount", "providerIterations", "visitedScopeRefs", "evidenceRefs",
        "checkpointBytes", "checkpointTokenProxy",
    }
    exact_keys(budgets, budget_keys, "request.remainingBudgets")
    for key in budget_keys:
        validate_remaining_budget(budgets[key], f"request.remainingBudgets.{key}")
    consumption = ledger["budgetConsumption"]
    soft = mission["softBudgets"]
    hard = mission["hardBudgets"]
    expected_budgets = {
        "eventCount": remaining_budget(consumption["eventCount"], soft["maxEvents"], hard["maxEvents"]),
        "providerIterations": remaining_budget(consumption["providerIterations"], soft["maxProviderIterations"], hard["maxProviderIterations"]),
        "visitedScopeRefs": remaining_budget(consumption["visitedScopeCount"], soft["maxVisitedScopeRefs"], hard["maxVisitedScopeRefs"]),
        "evidenceRefs": remaining_budget(consumption["evidenceRefCount"], soft["maxEvidenceRefs"], hard["maxEvidenceRefs"]),
    }
    for key, expected in expected_budgets.items():
        if budgets[key] != expected:
            raise CheckpointError(f"request remaining budget {key} is not host-derived")

    policy = value["callPolicy"]
    exact_keys(policy, {"primaryCallsPerTrigger", "structuralRepairCallsPerTrigger", "semanticRetryPermitted", "periodicCallsPermitted"}, "request.callPolicy")
    hard_provider_remaining = budgets["providerIterations"]["hardRemaining"]
    expected_repair = 1 if hard_provider_remaining >= 2 else 0
    if policy != {
        "primaryCallsPerTrigger": 1,
        "structuralRepairCallsPerTrigger": expected_repair,
        "semanticRetryPermitted": False,
        "periodicCallsPermitted": False,
    }:
        raise CheckpointError("request bounded call policy is invalid")
    if hard_provider_remaining < 1:
        raise CheckpointError("request has no primary-call budget")
    validate_action_options(
        envelope["nextActionProposals"], mission, ledger, hard_provider_remaining
    )

    measurements = value["promptMeasurements"]
    measurement_keys = {
        "requestBytes", "requestTokenProxy", "promptBytes", "promptTokenProxy",
        "softByteLimit", "hardByteLimit", "softTokenProxyLimit",
        "hardTokenProxyLimit", "softLimitExceeded",
    }
    exact_keys(measurements, measurement_keys, "request.promptMeasurements")
    actual_request_bytes = len(canonical_bytes(value))
    actual_request_tokens = math.ceil(actual_request_bytes / 4)
    actual_prompt_bytes = len(primary_prompt(value).encode("utf-8"))
    actual_prompt_tokens = math.ceil(actual_prompt_bytes / 4)
    expected_measurements = {
        "requestBytes": actual_request_bytes,
        "requestTokenProxy": actual_request_tokens,
        "promptBytes": actual_prompt_bytes,
        "promptTokenProxy": actual_prompt_tokens,
        "softByteLimit": soft["maxEnvelopeBytes"],
        "hardByteLimit": hard["maxEnvelopeBytes"],
        "softTokenProxyLimit": soft["maxEnvelopeTokenProxy"],
        "hardTokenProxyLimit": hard["maxEnvelopeTokenProxy"],
        "softLimitExceeded": any((
            envelope["measurements"]["serializedBytes"] > soft["maxEnvelopeBytes"],
            envelope["measurements"]["tokenProxyEstimate"] > soft["maxEnvelopeTokenProxy"],
            actual_request_bytes > soft["maxEnvelopeBytes"],
            actual_request_tokens > soft["maxEnvelopeTokenProxy"],
            actual_prompt_bytes > soft["maxEnvelopeBytes"],
            actual_prompt_tokens > soft["maxEnvelopeTokenProxy"],
        )),
    }
    if measurements != expected_measurements:
        raise CheckpointError("request prompt measurements are stale or forged")
    if budgets["checkpointBytes"] != remaining_budget(actual_prompt_bytes, soft["maxEnvelopeBytes"], hard["maxEnvelopeBytes"]):
        raise CheckpointError("request checkpoint-byte budget is invalid")
    if budgets["checkpointTokenProxy"] != remaining_budget(actual_prompt_tokens, soft["maxEnvelopeTokenProxy"], hard["maxEnvelopeTokenProxy"]):
        raise CheckpointError("request checkpoint-token-proxy budget is invalid")
    if (
        actual_request_bytes > hard["maxEnvelopeBytes"]
        or actual_prompt_bytes > hard["maxEnvelopeBytes"]
        or actual_request_tokens > hard["maxEnvelopeTokenProxy"]
        or actual_prompt_tokens > hard["maxEnvelopeTokenProxy"]
    ):
        raise CheckpointError("request exceeds a hard prompt/envelope budget")

    expected_id = request_id(mission, ledger, {
        "recommendationHash": trigger["recommendationHash"]
    })
    if value["requestId"] != expected_id:
        raise CheckpointError("request ID is not host-derived")


def validate_request_authority(
    actual: dict[str, Any], mission: dict[str, Any], ledger: dict[str, Any],
    events: list[dict[str, Any]], drift_config: dict[str, Any],
    observation: dict[str, Any], checkpoint_input: dict[str, Any],
    recommendation: dict[str, Any],
) -> None:
    validate_request_shape(actual)
    expected = build_request(
        mission, ledger, events, drift_config, observation,
        checkpoint_input, recommendation,
    )
    if canonical_bytes(actual) != canonical_bytes(expected):
        raise CheckpointError("checkpoint request is not derivable from authoritative host inputs")


def validation_error(code: str, path: str) -> dict[str, str]:
    return {"code": code, "path": path}


def add_structural(errors: list[dict[str, str]], condition: bool, code: str, path: str) -> None:
    if not condition:
        errors.append(validation_error(code, path))


def structural_ref_list(
    value: Any, path: str, errors: list[dict[str, str]], maximum: int = 256
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        errors.append(validation_error("INVALID_REF_ARRAY", path))
        return []
    result = []
    for item in value:
        if not isinstance(item, str) or not STATE.REF_PATTERN.fullmatch(item):
            errors.append(validation_error("INVALID_REF", path))
            continue
        result.append(item)
    if len(result) != len(set(result)):
        errors.append(validation_error("DUPLICATE_REF", path))
    return result


def structural_budget(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    expected = {"providerCalls", "tokenProxy"}
    if not isinstance(value, dict):
        errors.append(validation_error("INVALID_OBJECT", path))
        return
    if set(value) != expected:
        errors.append(validation_error("FIELDS_DIFFER", path))
        return
    for key in sorted(expected):
        amount = value[key]
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            errors.append(validation_error("INVALID_NON_NEGATIVE_INTEGER", f"{path}.{key}"))


def structural_next_action(value: Any, errors: list[dict[str, str]]) -> None:
    path = "recommendedNextAction"
    expected = {
        "actionId", "actionKind", "targetScopeRef", "justificationGoalRefs",
        "justificationGapRefs", "mandatoryConstraintRefs", "expectedEvidence",
        "decisionDependencies", "scopeExpansionRequired", "estimatedBudgetDelta",
    }
    if not isinstance(value, dict):
        errors.append(validation_error("INVALID_OBJECT", path))
        return
    if set(value) != expected:
        errors.append(validation_error("FIELDS_DIFFER", path))
        return
    for key in ("actionId", "actionKind", "targetScopeRef"):
        add_structural(errors, isinstance(value[key], str) and bool(STATE.REF_PATTERN.fullmatch(value[key])), "INVALID_REF", f"{path}.{key}")
    for key in ("justificationGoalRefs", "justificationGapRefs", "mandatoryConstraintRefs", "decisionDependencies"):
        structural_ref_list(value[key], f"{path}.{key}", errors)
    add_structural(errors, isinstance(value["expectedEvidence"], str) and 1 <= len(value["expectedEvidence"]) <= 512, "INVALID_BOUNDED_TEXT", f"{path}.expectedEvidence")
    add_structural(errors, isinstance(value["scopeExpansionRequired"], bool), "INVALID_BOOLEAN", f"{path}.scopeExpansionRequired")
    structural_budget(value["estimatedBudgetDelta"], f"{path}.estimatedBudgetDelta", errors)


def structural_scope_proposal(value: Any, errors: list[dict[str, str]]) -> None:
    path = "scopeExpansionProposal"
    expected = {
        "proposalId", "targetScopeRef", "reason", "relatedGoalRefs",
        "relatedConstraintRefs", "relatedGapRefs", "expectedEvidence",
        "estimatedBudgetDelta", "ownerApprovalRequired",
    }
    if not isinstance(value, dict):
        errors.append(validation_error("INVALID_OBJECT", path))
        return
    if set(value) != expected:
        errors.append(validation_error("FIELDS_DIFFER", path))
        return
    for key in ("proposalId", "targetScopeRef"):
        add_structural(errors, isinstance(value[key], str) and bool(STATE.REF_PATTERN.fullmatch(value[key])), "INVALID_REF", f"{path}.{key}")
    for key in ("relatedGoalRefs", "relatedConstraintRefs", "relatedGapRefs"):
        structural_ref_list(value[key], f"{path}.{key}", errors)
    for key in ("reason", "expectedEvidence"):
        add_structural(errors, isinstance(value[key], str) and 1 <= len(value[key]) <= 512, "INVALID_BOUNDED_TEXT", f"{path}.{key}")
    structural_budget(value["estimatedBudgetDelta"], f"{path}.estimatedBudgetDelta", errors)
    add_structural(errors, value["ownerApprovalRequired"] is True, "OWNER_APPROVAL_REQUIRED", f"{path}.ownerApprovalRequired")


def structural_response_errors(value: Any) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(value, dict):
        return [validation_error("RESPONSE_NOT_OBJECT", "root")]
    try:
        STATE.reject_raw_fields(value)
    except STATE.StateError:
        errors.append(validation_error("PROHIBITED_RAW_FIELD", "root"))
    expected = {
        "schemaVersion", "missionId", "missionHash", "missionRevision", "outcome",
        "objectiveRestatement", "supportingGoalRefs", "supportingConstraintRefs",
        "supportingGapRefs", "supportingEvidenceRefs", "recommendedNextAction",
        "scopeExpansionProposal", "stopReason", "discardedOrDeferredRefs", "confidence",
    }
    if set(value) != expected:
        errors.append(validation_error("FIELDS_DIFFER", "root"))
        return errors[:32]
    add_structural(errors, value["schemaVersion"] == RESPONSE_SCHEMA, "UNSUPPORTED_SCHEMA_VERSION", "schemaVersion")
    add_structural(errors, isinstance(value["missionId"], str) and bool(STATE.MISSION_ID_PATTERN.fullmatch(value["missionId"])), "INVALID_MISSION_ID", "missionId")
    add_structural(errors, isinstance(value["missionHash"], str) and bool(STATE.HASH_PATTERN.fullmatch(value["missionHash"])), "INVALID_HASH", "missionHash")
    add_structural(errors, isinstance(value["missionRevision"], int) and not isinstance(value["missionRevision"], bool) and value["missionRevision"] >= 1, "INVALID_REVISION", "missionRevision")
    add_structural(errors, value["outcome"] in OUTCOMES, "INVALID_OUTCOME", "outcome")
    add_structural(errors, isinstance(value["objectiveRestatement"], str) and 1 <= len(value["objectiveRestatement"]) <= 1024, "INVALID_BOUNDED_TEXT", "objectiveRestatement")
    for key in ("supportingGoalRefs", "supportingConstraintRefs", "supportingGapRefs", "supportingEvidenceRefs", "discardedOrDeferredRefs"):
        structural_ref_list(value[key], key, errors)
    if value["recommendedNextAction"] is not None:
        structural_next_action(value["recommendedNextAction"], errors)
    if value["scopeExpansionProposal"] is not None:
        structural_scope_proposal(value["scopeExpansionProposal"], errors)
    add_structural(errors, value["stopReason"] is None or value["stopReason"] in STOP_REASONS, "INVALID_STOP_REASON", "stopReason")
    add_structural(errors, value["confidence"] in {"LOW", "MEDIUM", "HIGH"}, "INVALID_CONFIDENCE", "confidence")
    return errors[:32]


def semantic_response_errors(
    request: dict[str, Any], response: dict[str, Any], calls_used: int
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    envelope = request["checkpointEnvelope"]
    mission = envelope["missionContract"]
    ledger = envelope["ledgerSnapshot"]
    if response["missionId"] != mission["missionId"]:
        errors.append(validation_error("WRONG_MISSION_ID", "missionId"))
    if response["missionHash"] != mission["contentHash"]:
        errors.append(validation_error("WRONG_MISSION_HASH", "missionHash"))
    if response["missionRevision"] != mission["revision"]:
        errors.append(validation_error("WRONG_MISSION_REVISION", "missionRevision"))

    ref_sets = {
        "supportingGoalRefs": set(mission["acceptanceCriterionRefs"]),
        "supportingConstraintRefs": set(mission["mandatoryConstraintRefs"]),
        "supportingGapRefs": {gap["gapId"] for gap in mission["evidenceGaps"]},
        "supportingEvidenceRefs": set(request["hostValidationContext"]["knownEvidenceRefs"]),
    }
    unknown_codes = {
        "supportingGoalRefs": "UNKNOWN_GOAL_REF",
        "supportingConstraintRefs": "UNKNOWN_CONSTRAINT_REF",
        "supportingGapRefs": "UNKNOWN_GAP_REF",
        "supportingEvidenceRefs": "UNKNOWN_EVIDENCE_REF",
    }
    for key, known in ref_sets.items():
        if not set(response[key]) <= known:
            errors.append(validation_error(unknown_codes[key], key))

    text_values = [response["objectiveRestatement"]]
    action = response["recommendedNextAction"]
    proposal = response["scopeExpansionProposal"]
    if action is not None:
        text_values.extend([action["actionKind"], action["expectedEvidence"]])
    if proposal is not None:
        text_values.extend([proposal["reason"], proposal["expectedEvidence"]])
    if any(IMPLEMENTATION_LEAKAGE.search(text) for text in text_values):
        errors.append(validation_error("IMPLEMENTATION_TASK_LEAKAGE", "objectiveRestatement"))

    options = envelope["nextActionProposals"]
    option_by_id = {item["actionId"]: item for item in options}
    allowed_scopes = set(mission["allowedEvidenceScopeRefs"])
    open_decisions = set(request["hostValidationContext"]["openDecisionRefs"])
    if open_decisions and any(DECISION_LEAKAGE.search(text) for text in text_values):
        errors.append(validation_error("OPEN_DECISION_ASSUMPTION", "objectiveRestatement"))
    rejected_targets = {
        item["targetScopeRef"]
        for item in request["hostValidationContext"]["activeRejectedHypotheses"]
    }
    provider_remaining = request["remainingBudgets"]["providerIterations"]["hardRemaining"]
    token_remaining = request["remainingBudgets"]["checkpointTokenProxy"]["hardRemaining"]
    if action is not None:
        expected_action = option_by_id.get(action["actionId"])
        if expected_action is None or canonical_bytes(expected_action) != canonical_bytes(action):
            errors.append(validation_error("UNKNOWN_OR_MUTATED_ACTION_OPTION", "recommendedNextAction"))
        if not action["justificationGoalRefs"] and not action["justificationGapRefs"] and not action["mandatoryConstraintRefs"]:
            errors.append(validation_error("UNSUPPORTED_NEXT_ACTION", "recommendedNextAction"))
        if action["targetScopeRef"] not in allowed_scopes or action["scopeExpansionRequired"]:
            errors.append(validation_error("UNAPPROVED_SCOPE_EXPANSION", "recommendedNextAction.targetScopeRef"))
        if set(action["decisionDependencies"]) & open_decisions:
            errors.append(validation_error("OPEN_DECISION_ASSUMPTION", "recommendedNextAction.decisionDependencies"))
        if action["targetScopeRef"] in rejected_targets:
            errors.append(validation_error("REJECTED_HYPOTHESIS_REOPENED", "recommendedNextAction.targetScopeRef"))
        if action["estimatedBudgetDelta"]["providerCalls"] > max(provider_remaining - calls_used, 0):
            errors.append(validation_error("HARD_BUDGET_VIOLATION", "recommendedNextAction.estimatedBudgetDelta.providerCalls"))
        if action["estimatedBudgetDelta"]["tokenProxy"] > token_remaining:
            errors.append(validation_error("HARD_BUDGET_VIOLATION", "recommendedNextAction.estimatedBudgetDelta.tokenProxy"))
        if not set(action["justificationGoalRefs"]) <= set(response["supportingGoalRefs"]):
            errors.append(validation_error("ACTION_SUPPORT_MISMATCH", "supportingGoalRefs"))
        if not set(action["mandatoryConstraintRefs"]) <= set(response["supportingConstraintRefs"]):
            errors.append(validation_error("ACTION_SUPPORT_MISMATCH", "supportingConstraintRefs"))
        if not set(action["justificationGapRefs"]) <= set(response["supportingGapRefs"]):
            errors.append(validation_error("ACTION_SUPPORT_MISMATCH", "supportingGapRefs"))

    if proposal is not None:
        candidates = set(request["scopeExpansionRules"]["candidateScopeRefs"])
        if proposal["targetScopeRef"] not in candidates or proposal["targetScopeRef"] in allowed_scopes:
            errors.append(validation_error("INVALID_SCOPE_EXPANSION_CHOICE", "scopeExpansionProposal.targetScopeRef"))
        if not proposal["relatedGoalRefs"] and not proposal["relatedConstraintRefs"] and not proposal["relatedGapRefs"]:
            errors.append(validation_error("UNSUPPORTED_SCOPE_EXPANSION", "scopeExpansionProposal"))
        if not set(proposal["relatedGoalRefs"]) <= ref_sets["supportingGoalRefs"]:
            errors.append(validation_error("UNKNOWN_GOAL_REF", "scopeExpansionProposal.relatedGoalRefs"))
        if not set(proposal["relatedConstraintRefs"]) <= ref_sets["supportingConstraintRefs"]:
            errors.append(validation_error("UNKNOWN_CONSTRAINT_REF", "scopeExpansionProposal.relatedConstraintRefs"))
        if not set(proposal["relatedGapRefs"]) <= set(ledger["openEvidenceGapRefs"]):
            errors.append(validation_error("INACTIVE_GAP_REF", "scopeExpansionProposal.relatedGapRefs"))
        if not set(proposal["relatedGoalRefs"]) <= set(response["supportingGoalRefs"]):
            errors.append(validation_error("PROPOSAL_SUPPORT_MISMATCH", "supportingGoalRefs"))
        if not set(proposal["relatedConstraintRefs"]) <= set(response["supportingConstraintRefs"]):
            errors.append(validation_error("PROPOSAL_SUPPORT_MISMATCH", "supportingConstraintRefs"))
        if not set(proposal["relatedGapRefs"]) <= set(response["supportingGapRefs"]):
            errors.append(validation_error("PROPOSAL_SUPPORT_MISMATCH", "supportingGapRefs"))
        if proposal["estimatedBudgetDelta"]["providerCalls"] > max(provider_remaining - calls_used, 0):
            errors.append(validation_error("HARD_BUDGET_VIOLATION", "scopeExpansionProposal.estimatedBudgetDelta.providerCalls"))
        if proposal["estimatedBudgetDelta"]["tokenProxy"] > token_remaining:
            errors.append(validation_error("HARD_BUDGET_VIOLATION", "scopeExpansionProposal.estimatedBudgetDelta.tokenProxy"))

    known_deferred = set().union(*ref_sets.values())
    known_deferred.update(option_by_id)
    known_deferred.update(mission["allowedEvidenceScopeRefs"])
    known_deferred.update(request["scopeExpansionRules"]["candidateScopeRefs"])
    known_deferred.update(request["hostValidationContext"]["openDecisionRefs"])
    known_deferred.update(item["rejectionEventRef"] for item in request["hostValidationContext"]["activeRejectedHypotheses"])
    for values in request["triggerRecommendation"]["supportingRefs"].values():
        known_deferred.update(values)
    if not set(response["discardedOrDeferredRefs"]) <= known_deferred:
        errors.append(validation_error("UNKNOWN_DEFERRED_REF", "discardedOrDeferredRefs"))

    outcome = response["outcome"]
    stop_reason = response["stopReason"]
    if outcome in {"ON_TRACK", "REANCHOR_REQUIRED"}:
        if action is None or proposal is not None or stop_reason is not None:
            errors.append(validation_error("CONTRADICTORY_OUTCOME_FIELDS", "outcome"))
    elif outcome == "SCOPE_TRIAGE_REQUIRED":
        if action is not None or proposal is None or stop_reason is not None:
            errors.append(validation_error("CONTRADICTORY_OUTCOME_FIELDS", "outcome"))
    else:
        expected_stop = {
            "STOP_SUFFICIENT_EVIDENCE": "EVIDENCE_SUFFICIENT",
            "STOP_NO_NEW_EVIDENCE": "NO_PRODUCTIVE_NEXT_STEP",
            "STOP_HARD_BUDGET": "HARD_BUDGET_REACHED",
            "NEEDS_OWNER_REVIEW": "OWNER_REVIEW_REQUIRED",
        }[outcome]
        if action is not None or proposal is not None or stop_reason != expected_stop:
            errors.append(validation_error("CONTRADICTORY_OUTCOME_FIELDS", "outcome"))

    if outcome == "STOP_SUFFICIENT_EVIDENCE":
        resolved_constraints = {
            constraint
            for gap in ledger["evidenceGaps"] if gap["status"] == "RESOLVED"
            for constraint in gap["relatedMandatoryConstraintRefs"]
        }
        if (
            ledger["openEvidenceGapRefs"]
            or not set(mission["acceptanceCriterionRefs"]) <= set(ledger["coveredGoalRefs"])
            or not set(mission["mandatoryConstraintRefs"]) <= resolved_constraints
            or not set(mission["acceptanceCriterionRefs"]) <= set(response["supportingGoalRefs"])
            or not set(mission["mandatoryConstraintRefs"]) <= set(response["supportingConstraintRefs"])
            or (bool(ledger["evidenceAddedSinceCheckpoint"]) and not response["supportingEvidenceRefs"])
        ):
            errors.append(validation_error("EVIDENCE_NOT_SUFFICIENT", "outcome"))
    if outcome == "STOP_NO_NEW_EVIDENCE" and ledger["noNewEvidenceStreak"] < 1:
        errors.append(validation_error("NO_EVIDENCE_STOP_UNSUPPORTED", "outcome"))
    if outcome == "STOP_HARD_BUDGET" and not any(
        item["hardRemaining"] == 0 for item in request["remainingBudgets"].values()
    ):
        errors.append(validation_error("HARD_BUDGET_STOP_UNSUPPORTED", "outcome"))
    return errors[:32]


def make_validation(
    request: dict[str, Any], response_path: Path, calls_used: int
) -> tuple[dict[str, Any], dict[str, Any] | None, int]:
    validate_request_shape(request)
    try:
        raw = response_path.read_bytes()
    except OSError as error:
        raise CheckpointError(f"cannot read response fixture {response_path}: {error}") from error
    response_hash = digest_bytes(raw)
    try:
        candidate = json.loads(raw)
    except json.JSONDecodeError:
        errors = [validation_error("INVALID_JSON", "root")]
        validation = {
            "schemaVersion": VALIDATION_SCHEMA,
            "requestId": request["requestId"],
            "responseHash": response_hash,
            "status": "STRUCTURAL_INVALID",
            "repairPermitted": calls_used == 1 and request["callPolicy"]["structuralRepairCallsPerTrigger"] == 1,
            "errors": errors,
        }
        return validation, None, 3
    structural = structural_response_errors(candidate)
    if structural:
        validation = {
            "schemaVersion": VALIDATION_SCHEMA,
            "requestId": request["requestId"],
            "responseHash": response_hash,
            "status": "STRUCTURAL_INVALID",
            "repairPermitted": calls_used == 1 and request["callPolicy"]["structuralRepairCallsPerTrigger"] == 1,
            "errors": structural,
        }
        return validation, candidate if isinstance(candidate, dict) else None, 3
    semantic = semantic_response_errors(request, candidate, calls_used)
    status = "SEMANTIC_INVALID" if semantic else "VALID"
    validation = {
        "schemaVersion": VALIDATION_SCHEMA,
        "requestId": request["requestId"],
        "responseHash": response_hash,
        "status": status,
        "repairPermitted": False,
        "errors": semantic,
    }
    return validation, candidate, 4 if semantic else 0


def validate_validation(value: dict[str, Any], request: dict[str, Any]) -> None:
    exact_keys(value, {"schemaVersion", "requestId", "responseHash", "status", "repairPermitted", "errors"}, "validation")
    if value["schemaVersion"] != VALIDATION_SCHEMA or value["requestId"] != request["requestId"]:
        raise CheckpointError("validation correlation failed")
    if value["status"] not in {"VALID", "STRUCTURAL_INVALID", "SEMANTIC_INVALID", "PROVIDER_FAILED"}:
        raise CheckpointError("validation status is invalid")
    if value["responseHash"] is not None and (
        not isinstance(value["responseHash"], str) or not STATE.HASH_PATTERN.fullmatch(value["responseHash"])
    ):
        raise CheckpointError("validation response hash is invalid")
    if not isinstance(value["repairPermitted"], bool):
        raise CheckpointError("validation repair marker is invalid")
    if value["repairPermitted"] and value["status"] != "STRUCTURAL_INVALID":
        raise CheckpointError("non-structural validation cannot permit repair")
    errors = value["errors"]
    if not isinstance(errors, list) or len(errors) > 32:
        raise CheckpointError("validation errors are invalid")
    for index, item in enumerate(errors):
        exact_keys(item, {"code", "path"}, f"validation.errors[{index}]")
        valid_ref(item["code"], f"validation.errors[{index}].code")
        valid_ref(item["path"], f"validation.errors[{index}].path")
    if value["status"] == "VALID" and errors:
        raise CheckpointError("valid assessment contains errors")
    if value["status"] != "VALID" and not errors:
        raise CheckpointError("invalid assessment contains no sanitized error code")


def provider_failure_validation(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": VALIDATION_SCHEMA,
        "requestId": request["requestId"],
        "responseHash": None,
        "status": "PROVIDER_FAILED",
        "repairPermitted": False,
        "errors": [validation_error("PROVIDER_INVOCATION_FAILED", "provider")],
    }


def call_record(kind: str, provider: str, model: str, effort: str, status: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "provider": valid_ref(provider, "run.provider"),
        "model": valid_ref(model, "run.model"),
        "effort": valid_ref(effort, "run.effort"),
        "validationResult": status,
        "usage": {"availability": "UNAVAILABLE", "inputTokens": None, "outputTokens": None},
    }


def build_run(
    config: dict[str, Any], request: dict[str, Any] | None, provider: str,
    model: str, effort: str, primary: dict[str, Any] | None,
    repair: dict[str, Any] | None, accepted_response: dict[str, Any] | None,
) -> dict[str, Any]:
    config = validate_config(config)
    if config["mode"] == "OFF":
        if any(item is not None for item in (request, primary, repair, accepted_response)):
            raise CheckpointError("OFF mode cannot record a request or a provider call")
        calls: list[dict[str, Any]] = []
        status = "DISABLED"
        outcome = None
        correlation = {"requestId": None, "requestHash": None}
    else:
        if request is None or primary is None:
            raise CheckpointError("SHADOW run requires a request and primary assessment")
        validate_request_shape(request)
        validate_validation(primary, request)
        if repair is not None:
            validate_validation(repair, request)
        primary_status = primary["status"]
        if primary_status == "VALID":
            if repair is not None or accepted_response is None:
                raise CheckpointError("valid primary result cannot have a repair")
            status = "ACCEPTED"
        elif primary_status == "STRUCTURAL_INVALID":
            if repair is not None and primary["repairPermitted"] is not True:
                raise CheckpointError("repair call exceeded the request or first-assessment allowance")
            if repair is not None and repair["status"] == "VALID":
                if accepted_response is None:
                    raise CheckpointError("valid repair lacks an accepted response")
                status = "ACCEPTED"
            else:
                if accepted_response is not None:
                    raise CheckpointError("failed repair cannot publish an accepted response")
                status = "NEEDS_OWNER_REVIEW"
        else:
            if repair is not None:
                raise CheckpointError("semantic/provider failure cannot receive a repair call")
            if accepted_response is not None:
                raise CheckpointError("invalid primary cannot publish an accepted response")
            status = "NEEDS_OWNER_REVIEW"
        if accepted_response is not None:
            structural = structural_response_errors(accepted_response)
            if structural:
                raise CheckpointError("accepted response is structurally invalid")
            accepted_calls_used = 2 if repair is not None else 1
            if semantic_response_errors(request, accepted_response, accepted_calls_used):
                raise CheckpointError("accepted response is semantically invalid for the recorded call count")
            outcome = accepted_response["outcome"]
        else:
            outcome = "NEEDS_OWNER_REVIEW"
        calls = [call_record("PRIMARY", provider, model, effort, primary_status)]
        if repair is not None:
            calls.append(call_record("STRUCTURAL_REPAIR", provider, model, effort, repair["status"]))
        if len(calls) > 2:
            raise CheckpointError("checkpoint call count exceeds the TG05 bound")
        if repair is not None and primary_status != "STRUCTURAL_INVALID":
            raise CheckpointError("repair followed a non-structural failure")
        correlation = {"requestId": request["requestId"], "requestHash": request["requestHash"]}
    identity = {"config": config, "correlation": correlation, "calls": calls, "status": status}
    primary_count = sum(item["kind"] == "PRIMARY" for item in calls)
    repair_count = sum(item["kind"] == "STRUCTURAL_REPAIR" for item in calls)
    return {
        "schemaVersion": RUN_SCHEMA,
        "runId": "checkpoint-run-" + hashlib.sha256(canonical_bytes(identity)).hexdigest()[:24],
        "mode": config["mode"],
        "advisory": True,
        "requestCorrelation": correlation,
        "status": status,
        "outcome": outcome,
        "calls": calls,
        "callCounts": {
            "primary": primary_count,
            "structuralRepair": repair_count,
            "total": len(calls),
        },
        "boundedPolicy": {
            "maxPrimaryCalls": 1,
            "maxStructuralRepairCalls": 1,
            "semanticRetryPermitted": False,
        },
        "effects": {
            "controlFlowChanged": False,
            "finalArtifactsChanged": False,
            "enforcementApplied": False,
        },
    }


def load_events(path: Path) -> list[dict[str, Any]]:
    try:
        return STATE.read_events(path)
    except STATE.StateError as error:
        raise CheckpointError(str(error)) from error


def command_build_request(args: argparse.Namespace) -> None:
    request = build_request(
        trusted_json(Path(args.mission)),
        trusted_json(Path(args.ledger)),
        load_events(Path(args.events)),
        trusted_json(Path(args.drift_config)),
        trusted_json(Path(args.observation)),
        trusted_json(Path(args.checkpoint_input)),
        trusted_json(Path(args.recommendation)),
    )
    STATE.atomic_write(Path(args.output), request)


def command_validate_request(args: argparse.Namespace) -> None:
    validate_request_authority(
        trusted_json(Path(args.request)),
        trusted_json(Path(args.mission)),
        trusted_json(Path(args.ledger)),
        load_events(Path(args.events)),
        trusted_json(Path(args.drift_config)),
        trusted_json(Path(args.observation)),
        trusted_json(Path(args.checkpoint_input)),
        trusted_json(Path(args.recommendation)),
    )


def command_render_prompt(args: argparse.Namespace) -> None:
    request = trusted_json(Path(args.request))
    validate_request_shape(request)
    prompt = primary_prompt(request)
    if len(prompt.encode("utf-8")) != request["promptMeasurements"]["promptBytes"]:
        raise CheckpointError("rendered primary prompt does not match measured prompt")
    atomic_write_text(Path(args.output), prompt)


def command_assess(args: argparse.Namespace) -> None:
    if args.calls_used not in {1, 2}:
        raise CheckpointError("calls-used must be 1 or 2")
    request = trusted_json(Path(args.request))
    validation, _, exit_code = make_validation(
        request, Path(args.response), args.calls_used
    )
    STATE.atomic_write(Path(args.output), validation)
    if exit_code:
        raise SystemExit(exit_code)


def command_render_repair(args: argparse.Namespace) -> None:
    request = trusted_json(Path(args.request))
    validation = trusted_json(Path(args.validation))
    validate_request_shape(request)
    validate_validation(validation, request)
    if validation["status"] != "STRUCTURAL_INVALID" or validation["repairPermitted"] is not True:
        raise CheckpointError("repair prompt requires a repairable structural failure")
    prompt = repair_prompt(request, validation)
    prompt_bytes = len(prompt.encode("utf-8"))
    prompt_tokens = math.ceil(prompt_bytes / 4)
    measurements = request["promptMeasurements"]
    if prompt_bytes > measurements["hardByteLimit"] or prompt_tokens > measurements["hardTokenProxyLimit"]:
        raise CheckpointError("repair prompt exceeds a TG03 hard envelope budget")
    atomic_write_text(Path(args.output), prompt)


def command_provider_failed(args: argparse.Namespace) -> None:
    request = trusted_json(Path(args.request))
    validate_request_shape(request)
    STATE.atomic_write(Path(args.output), provider_failure_validation(request))


def command_simulate(args: argparse.Namespace) -> None:
    config = validate_config(trusted_json(Path(args.config)))
    if config["mode"] == "OFF":
        run = build_run(config, None, "fixture", "fixture-model", "none", None, None, None)
        STATE.atomic_write(Path(args.output), run)
        return
    request = trusted_json(Path(args.request))
    validate_request_shape(request)
    primary, primary_response, _ = make_validation(request, Path(args.primary_response), 1)
    repair = None
    accepted = primary_response if primary["status"] == "VALID" else None
    if primary["status"] == "STRUCTURAL_INVALID" and primary["repairPermitted"]:
        if args.repair_response != "-":
            repair, repair_response, _ = make_validation(request, Path(args.repair_response), 2)
            if repair["status"] == "VALID":
                accepted = repair_response
    run = build_run(
        config, request, "fixture", "fixture-model", "none",
        primary, repair, accepted,
    )
    STATE.atomic_write(Path(args.output), run)


def command_record_run(args: argparse.Namespace) -> None:
    config = validate_config(trusted_json(Path(args.config)))
    if config["mode"] == "OFF":
        run = build_run(config, None, args.provider, args.model, args.effort, None, None, None)
    else:
        request = trusted_json(Path(args.request))
        primary = trusted_json(Path(args.primary_validation))
        repair = None if args.repair_validation == "-" else trusted_json(Path(args.repair_validation))
        accepted = None
        if args.accepted_response != "-":
            accepted_path = Path(args.accepted_response)
            calls_used = 2 if repair is not None and repair.get("status") == "VALID" else 1
            accepted_validation, accepted_candidate, accepted_code = make_validation(
                request, accepted_path, calls_used
            )
            expected_validation = repair if calls_used == 2 else primary
            if (
                accepted_code != 0
                or accepted_candidate is None
                or expected_validation is None
                or expected_validation.get("status") != "VALID"
                or accepted_validation["responseHash"] != expected_validation.get("responseHash")
            ):
                raise CheckpointError("accepted response does not match its valid assessment")
            accepted = accepted_candidate
        run = build_run(
            config, request, args.provider, args.model, args.effort,
            primary, repair, accepted,
        )
    STATE.atomic_write(Path(args.output), run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build-request")
    for name in ("mission", "ledger", "events", "drift_config", "observation", "checkpoint_input", "recommendation", "output"):
        build.add_argument(name)
    build.set_defaults(function=command_build_request)

    validate = commands.add_parser("validate-request")
    for name in ("mission", "ledger", "events", "drift_config", "observation", "checkpoint_input", "recommendation", "request"):
        validate.add_argument(name)
    validate.set_defaults(function=command_validate_request)

    render = commands.add_parser("render-prompt")
    render.add_argument("request")
    render.add_argument("output")
    render.set_defaults(function=command_render_prompt)

    assess = commands.add_parser("assess-response")
    assess.add_argument("request")
    assess.add_argument("response")
    assess.add_argument("output")
    assess.add_argument("--calls-used", type=int, default=1)
    assess.set_defaults(function=command_assess)

    repair = commands.add_parser("render-repair-prompt")
    repair.add_argument("request")
    repair.add_argument("validation")
    repair.add_argument("output")
    repair.set_defaults(function=command_render_repair)

    failed = commands.add_parser("provider-failed")
    failed.add_argument("request")
    failed.add_argument("output")
    failed.set_defaults(function=command_provider_failed)

    simulate = commands.add_parser("simulate")
    simulate.add_argument("config")
    simulate.add_argument("request")
    simulate.add_argument("primary_response")
    simulate.add_argument("repair_response")
    simulate.add_argument("output")
    simulate.set_defaults(function=command_simulate)

    record = commands.add_parser("record-run")
    record.add_argument("config")
    record.add_argument("request")
    record.add_argument("provider")
    record.add_argument("model")
    record.add_argument("effort")
    record.add_argument("primary_validation")
    record.add_argument("repair_validation")
    record.add_argument("accepted_response")
    record.add_argument("output")
    record.set_defaults(function=command_record_run)

    args = parser.parse_args()
    try:
        args.function(args)
        return 0
    except SystemExit as error:
        return int(error.code)
    except (CheckpointError, STATE.StateError, DRIFT.DriftError, OSError) as error:
        print(f"ERROR: Analysis Trajectory checkpoint: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
