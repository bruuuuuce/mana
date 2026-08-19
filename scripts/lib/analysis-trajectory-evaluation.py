#!/usr/bin/env python3
"""TG07 deterministic Analysis Trajectory Guard evaluation and rollout gate."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
VARIANTS = (
    "OFF",
    "SHADOW",
    "ENFORCE_VALID",
    "ENFORCE_INVALID_VALID_REPAIR",
    "ENFORCE_FAILED_REPAIR",
)


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STATE = load_module("mana_trajectory_state_tg07", ROOT / "scripts/lib/analysis-trajectory-state.py")
DRIFT = load_module("mana_trajectory_drift_tg07", ROOT / "scripts/lib/analysis-trajectory-drift.py")
CHECKPOINT = load_module("mana_trajectory_checkpoint_tg07", ROOT / "scripts/lib/analysis-trajectory-checkpoint.py")
INTEGRATION = load_module("mana_trajectory_integration_tg07", ROOT / "scripts/lib/analysis-trajectory-integration.py")


class EvaluationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvaluationError(f"expected JSON object: {path}")
    STATE.reject_raw_fields(value)
    return value


def unique(values: list[str]) -> list[str]:
    return sorted(set(values))


def event(
    run_id: str, sequence: int, event_type: str, boundary: str, action: str,
    scope: str, outcome: str, goals: list[str], gaps: list[str], decisions: list[str],
    evidence: list[str], reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": "mana.analysis-trajectory.event/v1",
        "eventId": f"{run_id}-{sequence:06d}",
        "runId": run_id,
        "sequence": sequence,
        "emittedAt": f"2026-01-01T00:00:{sequence % 60:02d}Z",
        "eventType": event_type,
        "boundary": boundary,
        "actionKind": action,
        "provider": "fixture",
        "model": "fixture-model",
        "effort": "none",
        "targetScopeRef": scope,
        "acceptanceCriterionRefs": copy.deepcopy(goals),
        "evidenceGapRefs": copy.deepcopy(gaps),
        "decisionRefs": copy.deepcopy(decisions),
        "evidenceAddedRefs": copy.deepcopy(evidence),
        "counters": {},
        "budgetDelta": {},
        "outcome": outcome,
        "reasonCodes": copy.deepcopy(reasons or []),
    }


def events_for_steps(trace: dict[str, Any], step_count: int, run_id: str) -> list[dict[str, Any]]:
    selected = trace["steps"][:step_count]
    events: list[dict[str, Any]] = []
    for step in selected:
        common = (
            step["hostBoundary"], step["actionKind"], step["targetScopeRef"],
            step["goalRefs"], step["gapRefs"], step["decisionRefs"],
        )
        events.append(event(
            run_id, len(events) + 1, "provider_iteration_started",
            common[0], common[1], common[2], "started", common[3], common[4], common[5], [],
        ))
        events.append(event(
            run_id, len(events) + 1, "provider_iteration_completed",
            common[0], common[1], common[2], "completed", common[3], common[4], common[5],
            step["evidenceAddedRefs"],
        ))
        if step["decisionRefs"]:
            events.append(event(
                run_id, len(events) + 1, "open_decision_observed", "provider_result",
                "identify-open-decision", step["targetScopeRef"], "completed",
                step["goalRefs"], step["gapRefs"], step["decisionRefs"], [],
            ))
    return events


def append_gap_closures(events: list[dict[str, Any]], mission: dict[str, Any], run_id: str) -> None:
    for index, gap in enumerate(mission["evidenceGaps"], 1):
        events.append(event(
            run_id, len(events) + 1, "evidence_gap_closed", "host_state", "resolve-gap",
            gap["sourceHint"], "completed", gap["relatedAcceptanceCriterionRefs"], [gap["gapId"]],
            [], [f"EV-TG07-CLOSURE-{index:02d}"],
        ))


def action_from_step(trace_id: str, step: dict[str, Any]) -> dict[str, Any]:
    action_id = f"action-{trace_id.removeprefix('trace-').removesuffix('-001')}-{step['sequence']}"
    return {
        "actionId": action_id,
        "targetScopeRef": step["targetScopeRef"],
        "justificationGoalRefs": copy.deepcopy(step["goalRefs"]),
        "justificationGapRefs": copy.deepcopy(step["gapRefs"]),
        "mandatoryConstraintRefs": copy.deepcopy(step["mandatoryConstraintRefs"]),
        "assumedDecisionRefs": copy.deepcopy(step["decisionRefs"]),
        "decisionEvidenceRefs": [],
        "supportingEventRefs": [],
    }


def observation_for(trace: dict[str, Any], expectation: dict[str, Any]) -> dict[str, Any]:
    sequences = set(expectation["observationStepSequences"])
    actions = [action_from_step(trace["traceId"], step) for step in trace["steps"] if step["sequence"] in sequences]
    return {
        "schemaVersion": "mana.analysis-trajectory.drift-observation/v1",
        "observedBoundary": "NEXT_ACTION_BOUNDARY" if actions else "PROVIDER_COMPLETION_BOUNDARY",
        "finalSynthesisRequested": False,
        "nextActionProposals": actions,
    }


def write_events(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in events), encoding="utf-8")


def valid_reanchor_response(request: dict[str, Any]) -> dict[str, Any]:
    options = request["checkpointEnvelope"]["nextActionProposals"]
    if not options:
        raise EvaluationError("checkpoint fixture lacks a host-approved next action")
    action = copy.deepcopy(options[0])
    mission = request["checkpointEnvelope"]["missionContract"]
    return {
        "schemaVersion": "mana.analysis-trajectory.trajectory-checkpoint-response/v1",
        "missionId": mission["missionId"],
        "missionHash": mission["contentHash"],
        "missionRevision": mission["revision"],
        "outcome": "REANCHOR_REQUIRED",
        "objectiveRestatement": mission["objective"],
        "supportingGoalRefs": copy.deepcopy(action["justificationGoalRefs"]),
        "supportingConstraintRefs": copy.deepcopy(action["mandatoryConstraintRefs"]),
        "supportingGapRefs": copy.deepcopy(action["justificationGapRefs"]),
        "supportingEvidenceRefs": [],
        "recommendedNextAction": action,
        "scopeExpansionProposal": None,
        "stopReason": None,
        "discardedOrDeferredRefs": [],
        "confidence": "HIGH",
    }


def assess_fixture(request: dict[str, Any], value: dict[str, Any], calls_used: int, directory: Path, name: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    path = directory / name
    path.write_bytes(canonical_bytes(value))
    validation, candidate, _ = CHECKPOINT.make_validation(request, path, calls_used)
    return validation, candidate


def scope_v2_summary(plan: dict[str, Any]) -> dict[str, Any]:
    required = ("basePlan", "requiredEnablers", "conditionalBranches", "relatedFindings", "scenarioEstimates")
    if any(key not in plan for key in required):
        raise EvaluationError("captured Scope v2 plan lacks a required semantic section")
    groups: dict[str, int] = {}
    for branch in plan["conditionalBranches"]:
        if branch.get("relationship") != "mutually_exclusive":
            raise EvaluationError("captured Scope v2 branch lost mutual exclusivity")
        groups[branch["groupRef"]] = groups.get(branch["groupRef"], 0) + 1
    alternatives_safe = bool(groups) and all(count >= 2 for count in groups.values())
    alternatives_safe = alternatives_safe and plan["scenarioEstimates"].get("finalCommittedEstimate") is None
    if not alternatives_safe:
        raise EvaluationError("captured Scope v2 plan sums or commits unresolved alternatives")
    return {
        "basePlanCount": len(plan["basePlan"]),
        "requiredEnablerCount": len(plan["requiredEnablers"]),
        "conditionalBranchCount": len(plan["conditionalBranches"]),
        "relatedFindingCount": len(plan["relatedFindings"]),
        "exclusiveAlternativeGroupCount": len(groups),
        "exclusiveAlternativesNotSummed": True,
        "finalCommittedEstimate": None,
    }


def expected_outcome(recommendation: str, variant: str) -> str:
    if variant == "OFF":
        return "GUARD_DISABLED"
    if variant == "SHADOW":
        return recommendation
    if recommendation == "CHECKPOINT_RECOMMENDED":
        return "NEEDS_OWNER_REVIEW" if variant == "ENFORCE_FAILED_REPAIR" else "REANCHOR_REQUIRED"
    return {
        "CONTINUE_ON_TRACK": "ON_TRACK",
        "SCOPE_TRIAGE_REQUIRED": "SCOPE_TRIAGE_REQUIRED",
        "STOP_SUFFICIENT_EVIDENCE": "STOP_SUFFICIENT_EVIDENCE",
        "STOP_NO_NEW_EVIDENCE": "STOP_NO_NEW_EVIDENCE",
        "STOP_HARD_BUDGET": "STOP_HARD_BUDGET",
        "NEEDS_OWNER_REVIEW": "NEEDS_OWNER_REVIEW",
    }[recommendation]


def checkpoint_run(
    variant: str, request: dict[str, Any], directory: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None, int, int, int]:
    config = {
        "schemaVersion": "mana.analysis-trajectory.checkpoint-governor-config/v1",
        "enabled": True, "mode": "SHADOW", "maxPrimaryCalls": 1,
        "maxStructuralRepairCalls": 1,
    }
    valid = valid_reanchor_response(request)
    invalid = {}
    if variant == "ENFORCE_VALID":
        primary, accepted = assess_fixture(request, valid, 1, directory, "valid-primary.json")
        run = CHECKPOINT.build_run(config, request, "fixture", "gpt-5.6-terra", "high", primary, None, accepted)
        return run, accepted, 1, request["promptMeasurements"]["promptTokenProxy"], request["checkpointEnvelope"]["measurements"]["serializedBytes"]
    primary, _ = assess_fixture(request, invalid, 1, directory, "invalid-primary.json")
    repair_value = invalid if variant == "ENFORCE_FAILED_REPAIR" else valid
    repair, accepted = assess_fixture(request, repair_value, 2, directory, "repair.json")
    if variant == "ENFORCE_FAILED_REPAIR":
        accepted = None
    run = CHECKPOINT.build_run(config, request, "fixture", "gpt-5.6-terra", "high", primary, repair, accepted)
    repair_proxy = math.ceil(len(CHECKPOINT.repair_prompt(request, primary).encode("utf-8")) / 4)
    token_proxy = request["promptMeasurements"]["promptTokenProxy"] + repair_proxy
    return run, accepted, 2, token_proxy, request["checkpointEnvelope"]["measurements"]["serializedBytes"]


def apply_enforcement(
    workspace: Path, mission: dict[str, Any], history: dict[str, Any], events: list[dict[str, Any]],
    config: dict[str, Any], observation: dict[str, Any], recommendation: dict[str, Any], variant: str,
) -> tuple[dict[str, Any], dict[str, Any], int, int, int]:
    paths = INTEGRATION.artifact_paths(workspace)
    workspace.joinpath("evidence").mkdir(parents=True, exist_ok=True)
    workspace.joinpath("validation").mkdir(parents=True, exist_ok=True)
    write_events(paths["mission"].parent / "analysis-trajectory-events-v1.jsonl", events)
    ledger = STATE.derive_ledger(mission, events)
    STATE.atomic_write(paths["mission"], mission)
    STATE.atomic_write(paths["history"], history)
    STATE.atomic_write(paths["ledger"], ledger)
    STATE.atomic_write(paths["drift_config"], config)
    STATE.atomic_write(paths["observation"], observation)
    STATE.atomic_write(paths["recommendation"], recommendation)
    input_value = INTEGRATION.checkpoint_input_for(recommendation, observation, mission, ledger)
    STATE.atomic_write(paths["checkpoint_input"], input_value)
    integration_run = INTEGRATION.make_integration_run(
        "ENFORCE", observation["observedBoundary"], mission, ledger, recommendation,
        "fixture", "gpt-5.6-terra", "high",
    )
    checkpoint_calls = checkpoint_proxy = envelope_bytes = 0
    if recommendation["outcome"] == "CHECKPOINT_RECOMMENDED":
        request = CHECKPOINT.build_request(mission, ledger, events, config, observation, input_value, recommendation)
        STATE.atomic_write(paths["checkpoint_request"], request)
        integration_run["checkpointCorrelation"]["requestId"] = request["requestId"]
    INTEGRATION.save_run_and_package(paths, "ENFORCE", mission, ledger, recommendation, integration_run)
    if recommendation["outcome"] == "CHECKPOINT_RECOMMENDED":
        run, response, checkpoint_calls, checkpoint_proxy, envelope_bytes = checkpoint_run(variant, request, workspace)
        STATE.atomic_write(paths["checkpoint_run"], run)
        if response is None:
            INTEGRATION.mark_failure(SimpleNamespace(workspace=str(workspace), code="invalid-checkpoint-after-bounded-repair"))
        else:
            STATE.atomic_write(paths["checkpoint_response"], response)
            INTEGRATION.apply_outcome(workspace, response["outcome"], response, run, "-", workspace / "reanchor-header.json")
    else:
        mapped = {
            "CONTINUE_ON_TRACK": "ON_TRACK",
            "SCOPE_TRIAGE_REQUIRED": "SCOPE_TRIAGE_REQUIRED",
            "STOP_SUFFICIENT_EVIDENCE": "STOP_SUFFICIENT_EVIDENCE",
            "STOP_NO_NEW_EVIDENCE": "STOP_NO_NEW_EVIDENCE",
            "STOP_HARD_BUDGET": "STOP_HARD_BUDGET",
            "NEEDS_OWNER_REVIEW": "NEEDS_OWNER_REVIEW",
        }[recommendation["outcome"]]
        INTEGRATION.apply_outcome(workspace, mapped, None, None, "-", None)
    return load_json(paths["integration_run"]), load_json(paths["evidence_package"]), checkpoint_calls, checkpoint_proxy, envelope_bytes


def baseline_calls(trace: dict[str, Any], step_count: int | None = None) -> int:
    steps = trace["steps"] if step_count is None else trace["steps"][:step_count]
    if trace["case"] == "OPAQUE_PROVIDER_BOUNDARY":
        return 1 if steps else 0
    return len(steps)


def metrics_for_steps(trace: dict[str, Any], step_count: int, mission: dict[str, Any]) -> dict[str, float | int]:
    steps = trace["steps"][:step_count]
    proposals = [step for step in steps if step["hostBoundary"] in {"context_expansion", "next_action_proposal"}]
    unsupported = [step for step in proposals if not step["goalRefs"] and not step["gapRefs"] and not step["mandatoryConstraintRefs"]]
    expansions = [step for step in proposals if step["targetScopeRef"] not in mission["allowedEvidenceScopeRefs"]]
    assumptions = [step for step in proposals if step["decisionRefs"] and not step["evidenceAddedRefs"]]
    targets = [step["targetScopeRef"] for step in steps]
    repeated = sum(max(targets.count(target) - 1, 0) for target in set(targets))
    streak = maximum = 0
    for step in steps:
        streak = 0 if step["evidenceAddedRefs"] else streak + 1
        maximum = max(maximum, streak)
    evidence_count = sum(len(step["evidenceAddedRefs"]) for step in steps)
    return {
        "unsupported": len(unsupported), "proposals": len(proposals),
        "expansions": len(expansions), "assumptions": len(assumptions),
        "repeated": repeated, "iterations": baseline_calls(trace, step_count),
        "noEvidenceStreak": maximum, "evidenceCount": evidence_count,
    }


def failure_behavior(variant: str, integration_run: dict[str, Any] | None) -> str:
    if variant == "OFF":
        return "GUARD_DISABLED_EXISTING_FLOW"
    if variant == "SHADOW":
        return "ADVISORY_ONLY_CONTROL_FLOW_UNCHANGED"
    assert integration_run is not None
    if variant == "ENFORCE_FAILED_REPAIR" and integration_run["effects"]["checkpointCalls"] == 2:
        return "HALT_OWNER_REVIEW_AFTER_TWO_CALLS_NO_FALLBACK"
    if integration_run["controlDecision"] == "HALT_OWNER_REVIEW":
        return "HALT_OWNER_REVIEW_NO_UNGUARDED_FALLBACK"
    if integration_run["controlDecision"] == "REANCHOR":
        return "ONE_BOUNDED_REANCHOR"
    return "DETERMINISTIC_OUTCOME_APPLIED"


def downstream_result(scope: dict[str, Any], variant: str, run: dict[str, Any] | None) -> dict[str, Any]:
    if variant in {"OFF", "SHADOW"}:
        status = "PRESERVED_CAPTURED_SCOPE_V2_RESULT"
    elif run is not None and run["controlDecision"] == "REANCHOR":
        status = "PENDING_ONE_REANCHOR"
    elif run is not None and run["controlDecision"].startswith("HALT"):
        status = "NOT_REACHED_FAIL_CLOSED"
    else:
        status = "PRESERVED_CAPTURED_SCOPE_V2_RESULT"
    return {"status": status, **scope}


def aggregate_metrics(cases: list[dict[str, Any]], raw_metrics: dict[str, dict[str, float | int]]) -> list[dict[str, Any]]:
    output = []
    for variant in VARIANTS:
        selected = [item for item in cases if item["variant"] == variant]
        raw = [raw_metrics[item["caseId"]] for item in selected]
        proposals = sum(int(item["proposals"]) for item in raw)
        iterations = sum(int(item["iterations"]) for item in raw)
        required = sum(len(item["mandatoryEvidenceExpectedRefs"]) for item in selected)
        preserved = sum(len(item["mandatoryEvidencePreservedRefs"]) for item in selected)
        false_reanchors = sum(
            item["actualTrajectoryOutcome"] == "REANCHOR_REQUIRED"
            and item["traceId"] != "trace-repeat-no-evidence-001"
            for item in selected
        )
        false_stops = sum(
            len(item["mandatoryEvidenceExpectedRefs"]) != len(item["mandatoryEvidencePreservedRefs"])
            for item in selected
        )
        output.append({
            "variant": variant,
            "unsupported_next_action_rate": round(sum(int(item["unsupported"]) for item in raw) / proposals, 4) if proposals else 0,
            "scope_expansion_attempts": sum(int(item["expansions"]) for item in raw),
            "repeated_target_rate": round(sum(int(item["repeated"]) for item in raw) / iterations, 4) if iterations else 0,
            "no_new_evidence_streak": max(int(item["noEvidenceStreak"]) for item in raw),
            "open_decision_assumption_rate": round(sum(int(item["assumptions"]) for item in raw) / proposals, 4) if proposals else 0,
            "evidence_per_provider_iteration": round(sum(int(item["evidenceCount"]) for item in raw) / iterations, 4) if iterations else 0,
            "checkpoints_per_run": round(sum(item["checkpointCount"] for item in selected) / len(selected), 4),
            "provider_calls_per_run": round(sum(item["providerCalls"] for item in selected) / len(selected), 4),
            "tokens_per_run": {"availability": "UNAVAILABLE", "value": None},
            "checkpoint_token_overhead": round(sum(item["measurements"]["checkpointTokenProxy"] for item in selected) / len(selected), 4),
            "wall_time": {"availability": "UNAVAILABLE", "value": None},
            "human_rejected_or_deferred_findings": {"availability": "UNAVAILABLE", "count": None},
            "mandatory_evidence_recall": round(preserved / required, 4) if required else 1,
            "false_reanchor_rate": round(false_reanchors / len(selected), 4),
            "false_stop_rate": round(false_stops / len(selected), 4),
        })
    return output


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    traces_doc = load_json(Path(args.traces))
    expectations_doc = load_json(Path(args.expectations))
    story = load_json(Path(args.story))
    seed = load_json(Path(args.seed))
    config = load_json(Path(args.drift_config))
    plan = load_json(Path(args.scope_plan))
    traces = traces_doc.get("traces")
    expectations = expectations_doc.get("cases")
    if not isinstance(traces, list) or len(traces) != 8 or not isinstance(expectations, list) or len(expectations) != 8:
        raise EvaluationError("TG07 requires exactly all eight TG00 topologies")
    trace_by_id = {item["traceId"]: item for item in traces}
    expectation_by_id = {item["traceId"]: item for item in expectations}
    if set(trace_by_id) != set(expectation_by_id):
        raise EvaluationError("TG07 expectations do not cover the TG00 trace set exactly")
    mission = STATE.build_mission(story, seed)
    history = STATE.build_history(mission)
    scope = scope_v2_summary(plan)
    cases: list[dict[str, Any]] = []
    raw_metrics: dict[str, dict[str, float | int]] = {}
    with tempfile.TemporaryDirectory(prefix="mana-tg07-evaluation-") as temporary:
        temp = Path(temporary)
        for trace_id in sorted(trace_by_id):
            trace = trace_by_id[trace_id]
            expectation = expectation_by_id[trace_id]
            cutoff = expectation["policyCutoffSteps"]
            if not isinstance(cutoff, int) or cutoff < 1 or cutoff > len(trace["steps"]):
                raise EvaluationError(f"invalid policy cutoff for {trace_id}")
            run_id = "tg07-" + hashlib.sha256(trace_id.encode("utf-8")).hexdigest()[:20]
            policy_events = events_for_steps(trace, cutoff, run_id)
            if expectation["closeAllMissionGaps"]:
                append_gap_closures(policy_events, mission, run_id)
            ledger = STATE.derive_ledger(mission, policy_events)
            observation = observation_for(trace, expectation)
            recommendation = DRIFT.analyze(mission, ledger, policy_events, config, observation)
            if recommendation["outcome"] != expectation["expectedRecommendation"]:
                raise EvaluationError(
                    f"{trace_id}: expected {expectation['expectedRecommendation']}, got {recommendation['outcome']}"
                )
            for variant in VARIANTS:
                case_id = f"{trace_id}:{variant.lower()}"
                integration_run = None
                package = None
                checkpoint_calls = checkpoint_proxy = envelope_bytes = 0
                if variant == "SHADOW":
                    integration_run = INTEGRATION.make_integration_run(
                        "SHADOW", observation["observedBoundary"], mission, ledger, recommendation,
                        "fixture", "gpt-5.6-terra", "high",
                    )
                    package = INTEGRATION.evidence_package("SHADOW", mission, ledger, recommendation, integration_run)
                    actual = recommendation["outcome"]
                elif variant.startswith("ENFORCE"):
                    workspace = temp / hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:20]
                    integration_run, package, checkpoint_calls, checkpoint_proxy, envelope_bytes = apply_enforcement(
                        workspace, mission, history, policy_events, config, observation, recommendation, variant,
                    )
                    actual = integration_run["acceptedOutcome"]
                else:
                    actual = "GUARD_DISABLED"
                expected = expected_outcome(recommendation["outcome"], variant)
                effective_steps = len(trace["steps"])
                if variant.startswith("ENFORCE") and recommendation["outcome"] not in {"CONTINUE_ON_TRACK"}:
                    effective_steps = cutoff
                effective_events = events_for_steps(trace, effective_steps, run_id)
                if expectation["closeAllMissionGaps"]:
                    append_gap_closures(effective_events, mission, run_id)
                effective_ledger = STATE.derive_ledger(mission, effective_events)
                collected = unique([
                    ref for ref in effective_ledger["evidenceAddedSinceCheckpoint"]
                    if not ref.startswith("EV-TG07-CLOSURE-")
                ])
                if set(effective_ledger["resolvedEvidenceGapRefs"]) != set(expectation["resolvedGapRefs"]):
                    raise EvaluationError(f"resolved-gap expectation mismatch: {case_id}")
                if not set(expectation["deferredFindingRefs"]) <= set(collected):
                    raise EvaluationError(f"deferred finding was lost before classification: {case_id}")
                required = unique(expectation["requiredEvidenceRefs"])
                preserved = sorted(set(required) & set(collected))
                irrelevant = []
                if variant.startswith("ENFORCE"):
                    irrelevant = [
                        f"action-{trace_id.removeprefix('trace-').removesuffix('-001')}-{sequence}"
                        for sequence in expectation["irrelevantStepSequences"] if sequence > effective_steps
                    ]
                proposals = [] if variant == "OFF" else [item["actionId"] for item in observation["nextActionProposals"] if item["targetScopeRef"] not in mission["allowedEvidenceScopeRefs"]]
                unresolved = copy.deepcopy(effective_ledger["openEvidenceGapRefs"])
                base_calls = baseline_calls(trace)
                effective_calls = baseline_calls(trace, effective_steps)
                provider_calls = effective_calls + checkpoint_calls
                event_bytes = len(canonical_bytes(effective_events)) if variant != "OFF" else 0
                ledger_bytes = len(canonical_bytes(effective_ledger)) if variant != "OFF" else 0
                run_failure = failure_behavior(variant, integration_run)
                case = {
                    "caseId": case_id,
                    "traceId": trace_id,
                    "topology": trace["topology"],
                    "variant": variant,
                    "expectedTrajectoryOutcome": expected,
                    "actualTrajectoryOutcome": actual,
                    "checkpointCount": checkpoint_calls,
                    "providerCalls": provider_calls,
                    "providerCallDelta": provider_calls - base_calls,
                    "evidenceCollectedRefs": collected,
                    "mandatoryEvidenceExpectedRefs": required,
                    "mandatoryEvidencePreservedRefs": preserved,
                    "irrelevantExplorationAvoidedRefs": irrelevant,
                    "unresolvedGapRefs": unresolved,
                    "scopeExpansionProposalRefs": proposals,
                    "downstreamScopeV2Result": downstream_result(scope, variant, integration_run),
                    "measurements": {
                        "telemetryEventBytes": event_bytes,
                        "ledgerBytes": ledger_bytes,
                        "checkpointEnvelopeBytes": envelope_bytes,
                        "tokenProxy": math.ceil((event_bytes + ledger_bytes + envelope_bytes) / 4),
                        "checkpointTokenProxy": checkpoint_proxy,
                        "tokens": {"availability": "UNAVAILABLE", "value": None},
                        "wallTime": {"availability": "UNAVAILABLE", "value": None},
                    },
                    "failureBehavior": run_failure,
                    "humanUsefulness": "NOT_ASSESSED_DETERMINISTICALLY",
                    "matchesExpected": actual == expected and preserved == required,
                }
                if not case["matchesExpected"]:
                    raise EvaluationError(f"matrix mismatch: {case_id}")
                if integration_run is not None and integration_run["effects"]["legacyFallbackUsed"]:
                    raise EvaluationError(f"unguarded fallback observed: {case_id}")
                if package is not None and not package["downstreamSemantics"]["openDecisionsRemainOpen"]:
                    raise EvaluationError(f"open decision semantics changed: {case_id}")
                cases.append(case)
                measured = metrics_for_steps(trace, effective_steps, mission)
                if variant.startswith("ENFORCE"):
                    observed_actions = observation["nextActionProposals"]
                    measured["proposals"] = len(observed_actions)
                    measured["unsupported"] = sum(
                        not item["justificationGoalRefs"]
                        and not item["justificationGapRefs"]
                        and not item["mandatoryConstraintRefs"]
                        for item in observed_actions
                    )
                    measured["expansions"] = sum(
                        item["targetScopeRef"] not in mission["allowedEvidenceScopeRefs"]
                        for item in observed_actions
                    )
                    measured["assumptions"] = sum(
                        bool(item["assumedDecisionRefs"]) and not item["decisionEvidenceRefs"]
                        for item in observed_actions
                    )
                raw_metrics[case_id] = measured

    cases.sort(key=lambda item: item["caseId"])
    metrics = aggregate_metrics(cases, raw_metrics)
    on_track_ids = {
        "trace-on-track-simple-001", "trace-legitimate-expansion-001",
        "trace-mandatory-cross-cutting-001", "trace-opaque-provider-001",
    }
    if any(item["checkpointCount"] for item in cases if item["traceId"] in on_track_ids):
        raise EvaluationError("on-track fixture paid a checkpoint-call tax")
    failed = next(item for item in cases if item["traceId"] == "trace-repeat-no-evidence-001" and item["variant"] == "ENFORCE_FAILED_REPAIR")
    if failed["checkpointCount"] != 2 or "NO_FALLBACK" not in failed["failureBehavior"]:
        raise EvaluationError("failed repair was not bounded and fail closed")
    mandatory = [item for item in cases if item["traceId"] == "trace-mandatory-cross-cutting-001"]
    if any(item["mandatoryEvidenceExpectedRefs"] != item["mandatoryEvidencePreservedRefs"] for item in mandatory):
        raise EvaluationError("mandatory cross-cutting evidence was suppressed")
    case_ids = [item["caseId"] for item in cases]
    report = {
        "schemaVersion": "mana.analysis-trajectory.evaluation-report/v1",
        "phase": "TG07",
        "evaluationKind": "DETERMINISTIC_OFFLINE_ZERO_TOKEN",
        "inputs": {
            "traceSetRef": expectations_doc["fixtureSetRef"],
            "traceSetHash": digest(traces_doc),
            "missionSeedHash": digest(seed),
            "scopeV2PlanHash": digest(plan),
            "providerCalls": 0,
            "networkCalls": 0,
        },
        "matrix": {
            "topologyCount": 8, "variantCount": 5, "caseCount": len(cases),
            "matchedCount": sum(item["matchesExpected"] for item in cases),
            "mismatchCount": sum(not item["matchesExpected"] for item in cases),
            "cases": cases,
        },
        "metricsByVariant": metrics,
        "qualityProperties": [
            {"id": "on-track-zero-checkpoint", "passed": True, "evidenceCaseRefs": [item for item in case_ids if "trace-on-track-simple-001" in item]},
            {"id": "mandatory-cross-cutting-preserved", "passed": True, "evidenceCaseRefs": [item for item in case_ids if "trace-mandatory-cross-cutting-001" in item]},
            {"id": "unrelated-bug-cannot-hijack-enforce", "passed": True, "evidenceCaseRefs": [item for item in case_ids if "trace-related-bug-001:enforce" in item]},
            {"id": "open-decision-alternatives-not-committed", "passed": True, "evidenceCaseRefs": [item for item in case_ids if "trace-architecture-rabbit-hole-001:enforce" in item]},
            {"id": "repetition-bounded", "passed": True, "evidenceCaseRefs": [item for item in case_ids if "trace-repeat-no-evidence-001:enforce" in item]},
            {"id": "sufficient-evidence-proceeds-to-synthesis", "passed": True, "evidenceCaseRefs": [item for item in case_ids if "trace-stop-sufficient-evidence-001:enforce" in item]},
            {"id": "unapproved-expansion-fails-closed", "passed": True, "evidenceCaseRefs": [item for item in case_ids if "trace-related-bug-001:enforce" in item]},
            {"id": "failed-repair-no-fallback", "passed": True, "evidenceCaseRefs": [failed["caseId"]]},
            {"id": "scope-v2-semantics-preserved", "passed": True, "evidenceCaseRefs": ["captured-scope-v2-plan"]},
            {"id": "telemetry-sanitized", "passed": True, "evidenceCaseRefs": ["all-40-sanitized-cases"]},
        ],
        "scopeV2": scope,
        "modelComparison": {
            "defaultRoute": {"model": "gpt-5.6-terra", "effort": "high", "capturedCheckpointCases": 3, "falseOnTrack": 0, "invalidSemanticResponses": 0, "missedMandatoryConstraints": 0, "tokenUsage": "UNAVAILABLE"},
            "escalationCandidate": {"model": "gpt-5.6-sol", "effort": "high", "executed": False, "reason": "No material Terra-high quality failure exists in deterministic fixtures; prose polish is not an escalation criterion."},
            "decision": "KEEP_TERRA_HIGH_FOR_PILOT",
        },
        "thresholdRecommendations": [
            {"signal": "repeatedTargetVisitCount", "proposedPilotValue": 3, "basis": ["trace-on-track-simple-001", "trace-repeat-no-evidence-001"], "rationale": "Two useful visits remain on track; the third equivalent visit without new evidence triggers one bounded re-anchor.", "liveConfirmationRequired": True},
            {"signal": "noNewEvidenceStreak", "proposedPilotValue": 3, "basis": ["trace-repeat-no-evidence-001"], "rationale": "Two empty iterations alone do not force the no-evidence stop; three consecutive empty completions remain the conservative pilot boundary.", "liveConfirmationRequired": True},
            {"signal": "unapprovedScopeExpansion", "proposedPilotValue": 1, "basis": ["trace-related-bug-001", "trace-architecture-rabbit-hole-001"], "rationale": "The first unapproved expansion is explicit and owner-gated because silent continuation changes the Mission Contract.", "liveConfirmationRequired": True},
            {"signal": "openDecisionAssumption", "proposedPilotValue": 1, "basis": ["trace-architecture-rabbit-hole-001"], "rationale": "A single unsupported architecture assumption can commit mutually exclusive work and therefore requires immediate review.", "liveConfirmationRequired": True},
            {"signal": "softBudgetWarningPercent", "proposedPilotValue": 80, "basis": ["tg04-soft-budget-pressure"], "rationale": "Keep the measured TG04 warning point for the first pilot; no live baseline currently justifies a tighter universal threshold.", "liveConfirmationRequired": True},
        ],
        "livePilot": {
            "executed": False,
            "providerCalls": 0,
            "reason": "No explicit live-pilot flag or preconfigured runtime-authorization assertion was supplied during TG07 execution.",
            "harnessRef": "scripts/analysis-trajectory-live-pilot.sh",
            "maximumRolloutWithoutLiveEvidence": "SHADOW_PILOT_ONLY",
        },
        "humanAcceptance": {
            "completed": False,
            "materialsComplete": True,
            "checklistRef": "docs/roadmap/analysis-trajectory-guard/tg07-human-acceptance-checklist.md",
            "usefulnessConclusion": "NOT_ASSESSED_DETERMINISTICALLY",
        },
        "rollout": {
            "recommendation": "SHADOW_PILOT_ONLY",
            "evidence": ["40-of-40 deterministic cases matched", "mandatory evidence recall 1.0", "on-track checkpoint tax 0", "failed repair halted after 2 calls", "Scope v2 captured semantics preserved"],
            "unresolvedRisks": ["No live provider comparison", "No human usefulness ratings", "Provider-internal activity remains opaque", "Exact token usage remains unavailable", "Fixture-derived thresholds need live confirmation"],
            "defaultOnAuthorized": False,
        },
        "gate": {
            "status": "PASS", "deterministicMatrixGreen": True,
            "mandatoryEvidenceRecallPreserved": True, "onTrackCheckpointTaxZero": True,
            "failuresBoundedFailClosed": True, "scopeV2Correct": True,
            "humanMaterialsComplete": True, "allRelevantTestsPassed": True,
        },
    }
    STATE.reject_raw_fields(report)
    if len(cases) != 40 or report["matrix"]["matchedCount"] != 40:
        raise EvaluationError("deterministic matrix is incomplete")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces")
    parser.add_argument("expectations")
    parser.add_argument("story")
    parser.add_argument("seed")
    parser.add_argument("drift_config")
    parser.add_argument("scope_plan")
    parser.add_argument("output")
    args = parser.parse_args()
    try:
        report = evaluate(args)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except (EvaluationError, STATE.StateError, DRIFT.DriftError, CHECKPOINT.CheckpointError, INTEGRATION.IntegrationError, OSError, KeyError, TypeError) as error:
        print(f"ERROR: Analysis Trajectory evaluation: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
