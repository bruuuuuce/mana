#!/usr/bin/env python3
"""TG06 host-owned integration at Story Start v2 provider boundaries."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STATE = load_module("mana_trajectory_state_tg06", ROOT / "scripts/lib/analysis-trajectory-state.py")
DRIFT = load_module("mana_trajectory_drift_tg06", ROOT / "scripts/lib/analysis-trajectory-drift.py")
CHECKPOINT = load_module("mana_trajectory_checkpoint_tg06", ROOT / "scripts/lib/analysis-trajectory-checkpoint.py")

EVIDENCE_SCHEMA = "mana.analysis-trajectory.evidence-package/v1"
RUN_SCHEMA = "mana.analysis-trajectory.integration-run/v1"
EXPANSION_SCHEMA = "mana.analysis-trajectory.scope-expansion-proposal/v1"
MODES = {"SHADOW", "ENFORCE"}
BOUNDARIES = {
    "PROVIDER_INVOCATION_BOUNDARY", "PROVIDER_COMPLETION_BOUNDARY",
    "FINAL_SYNTHESIS_BOUNDARY", "NEXT_ACTION_BOUNDARY",
}
UNSUPPORTED_FACTS = [
    "provider-internal-context-expansion",
    "provider-internal-delegation",
    "provider-internal-file-reads",
    "provider-internal-reasoning",
    "provider-internal-tool-calls",
]


class IntegrationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise IntegrationError(f"cannot read JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise IntegrationError(f"JSON input must be an object: {path}")
    STATE.reject_raw_fields(value)
    return value


def artifact_paths(workspace: Path) -> dict[str, Path]:
    return {
        "mission": workspace / "evidence/analysis-trajectory-mission-v1.json",
        "history": workspace / "validation/analysis-trajectory-mission-history-v1.json",
        "ledger": workspace / "validation/analysis-trajectory-ledger-v1.json",
        "drift_config": workspace / "validation/analysis-trajectory-drift-config-v1.json",
        "governor_config": workspace / "validation/analysis-trajectory-checkpoint-governor-config-v1.json",
        "observation": workspace / "validation/analysis-trajectory-observation-v1.json",
        "recommendation": workspace / "validation/analysis-trajectory-recommendation-v1.json",
        "checkpoint_input": workspace / "validation/analysis-trajectory-checkpoint-input-v1.json",
        "checkpoint_request": workspace / "validation/analysis-trajectory-checkpoint-request-v1.json",
        "checkpoint_run": workspace / "validation/analysis-trajectory-checkpoint-run-v1.json",
        "checkpoint_response": workspace / "validation/analysis-trajectory-checkpoint-response-v1.json",
        "integration_run": workspace / "validation/analysis-trajectory-integration-run-v1.json",
        "evidence_package": workspace / "evidence/analysis-trajectory-evidence-package-v1.json",
        "expansion": workspace / "validation/analysis-trajectory-scope-expansion-v1.json",
    }


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def mission_seed(package: dict[str, Any]) -> dict[str, Any]:
    if package.get("packageVersion") != "mana.story-start.discovery-package/v1":
        raise IntegrationError("unsupported Story Start discovery package")
    story_id = STATE.valid_ref(package.get("storyId"), "package.storyId")
    normalized = package.get("normalizedStory")
    if not isinstance(normalized, dict):
        raise IntegrationError("package.normalizedStory must be an object")
    criteria = normalized.get("acceptanceCriteria")
    if not isinstance(criteria, list) or not criteria:
        raise IntegrationError("package must contain acceptance criteria")
    gaps = []
    for index, item in enumerate(criteria):
        if not isinstance(item, dict):
            raise IntegrationError(f"acceptanceCriteria[{index}] must be an object")
        criterion_ref = STATE.valid_ref(
            item.get("sourceKey", item.get("ref", item.get("id"))),
            f"acceptanceCriteria[{index}].sourceKey",
        )
        gap_id = "gap-" + hashlib.sha256(criterion_ref.encode("utf-8")).hexdigest()[:20]
        gaps.append({
            "gapId": gap_id,
            "description": f"Collect host-visible evidence for acceptance criterion {criterion_ref}.",
            "relatedAcceptanceCriterionRefs": [criterion_ref],
            "relatedMandatoryConstraintRefs": [],
            "expectedEvidenceType": "host-visible-evidence",
            "sourceHint": "scope-v2/discovery",
        })
    source_topology = package.get("sourceTopology", "story-start-context")
    source_topology = STATE.valid_ref(source_topology, "package.sourceTopology")
    budgets = {
        "maxEvents": 256,
        "maxProviderIterations": 32,
        "maxVisitedScopeRefs": 32,
        "maxEvidenceRefs": 128,
        "maxLedgerRefs": 128,
        "maxEnvelopeEvidenceEvents": 48,
        "maxEnvelopeBytes": 131072,
        "maxEnvelopeTokenProxy": 32768,
    }
    soft = {key: max(1, value // 2) for key, value in budgets.items()}
    return {
        "schemaVersion": STATE.MISSION_SEED_SCHEMA,
        "createdAt": now_utc(),
        "authoritativeInputRefs": [f"story:{story_id}", f"topology:{source_topology}"],
        "scopePolicy": {
            "initialStoryScopeRefs": ["scope-v2/discovery"],
            "requirementDependencyScopeRefs": ["scope-v2/planning-context", "scope-v2/triage"],
            "mandatoryConstraintScopeLinks": [],
            "proposedExpansionScopeRefs": [],
            "globalMandatoryScopeRefs": [],
        },
        "mandatoryConstraints": [],
        "evidenceGaps": gaps,
        "prohibitedActions": [
            "no-direct-mission-mutation", "no-provider-internal-tool-claims",
            "no-unapproved-scope-expansion",
        ],
        "stopConditions": [
            "all-active-gaps-resolved", "hard-budget-reached", "owner-review-required",
        ],
        "softBudgets": soft,
        "hardBudgets": budgets,
    }


def drift_config() -> dict[str, Any]:
    return {
        "schemaVersion": "mana.analysis-trajectory.drift-config/v1",
        "enabled": True,
        "mode": "SHADOW",
        "thresholds": {
            "repeatedTargetVisitCount": 3,
            "noNewEvidenceStreak": 3,
            "softBudgetWarningPercent": 80,
        },
        "evidenceSufficiency": {
            "minimumEvidenceRefsPerAcceptanceCriterion": 1,
            "minimumResolvedGapsPerMandatoryConstraint": 1,
            "requireNoOpenEvidenceGaps": True,
        },
        "equivalentTargetGroups": [],
    }


def default_observation(boundary: str) -> dict[str, Any]:
    if boundary not in BOUNDARIES:
        raise IntegrationError(f"unsupported observable boundary: {boundary}")
    return {
        "schemaVersion": "mana.analysis-trajectory.drift-observation/v1",
        "observedBoundary": boundary,
        "finalSynthesisRequested": boundary == "FINAL_SYNTHESIS_BOUNDARY",
        "nextActionProposals": [],
    }


def checkpoint_input_for(
    recommendation: dict[str, Any], observation: dict[str, Any],
    mission: dict[str, Any], ledger: dict[str, Any],
) -> dict[str, Any]:
    options = []
    allowed = set(mission["allowedEvidenceScopeRefs"])
    for item in observation.get("nextActionProposals", []):
        options.append({
            "actionId": item["actionId"],
            "actionKind": "inspect-evidence",
            "targetScopeRef": item["targetScopeRef"],
            "justificationGoalRefs": item["justificationGoalRefs"],
            "justificationGapRefs": item["justificationGapRefs"],
            "mandatoryConstraintRefs": item["mandatoryConstraintRefs"],
            "expectedEvidence": "Collect bounded host-visible evidence for the cited mission refs.",
            "decisionDependencies": item["assumedDecisionRefs"],
            "scopeExpansionRequired": item["targetScopeRef"] not in allowed,
            "estimatedBudgetDelta": {"providerCalls": 1, "tokenProxy": 1024},
        })
    if not options and ledger["openEvidenceGapRefs"]:
        gap_id = ledger["openEvidenceGapRefs"][0]
        gap = next(item for item in ledger["evidenceGaps"] if item["gapId"] == gap_id)
        target = mission["allowedEvidenceScopeRefs"][0]
        options.append({
            "actionId": "action-return-to-active-gap",
            "actionKind": "inspect-evidence",
            "targetScopeRef": target,
            "justificationGoalRefs": gap["relatedAcceptanceCriterionRefs"],
            "justificationGapRefs": [gap_id],
            "mandatoryConstraintRefs": gap["relatedMandatoryConstraintRefs"],
            "expectedEvidence": "Close the active evidence gap with one bounded host-visible result.",
            "decisionDependencies": [],
            "scopeExpansionRequired": False,
            "estimatedBudgetDelta": {"providerCalls": 1, "tokenProxy": 1024},
        })
    return {
        "schemaVersion": STATE.CHECKPOINT_INPUT_SCHEMA,
        "triggerReasons": recommendation["reasonCodes"],
        "nextActionProposals": options,
    }


def correlation(mission: dict[str, Any]) -> dict[str, Any]:
    return {
        "missionId": mission["missionId"],
        "missionHash": mission["contentHash"],
        "missionRevision": mission["revision"],
    }


def make_integration_run(
    mode: str, boundary: str, mission: dict[str, Any],
    ledger: dict[str, Any], recommendation: dict[str, Any], provider: str, model: str, effort: str,
) -> dict[str, Any]:
    identity = {
        "missionHash": mission["contentHash"],
        "recommendationHash": recommendation["recommendationHash"],
        "mode": mode,
    }
    return {
        "schemaVersion": RUN_SCHEMA,
        "runId": "trajectory-integration-" + hashlib.sha256(canonical_bytes(identity)).hexdigest()[:24],
        "mode": mode,
        "observedBoundary": boundary,
        "missionCorrelation": correlation(mission),
        "recommendationCorrelation": {
            "recommendationId": recommendation["recommendationId"],
            "recommendationHash": recommendation["recommendationHash"],
            "outcome": recommendation["outcome"],
            "reasonCodes": recommendation["reasonCodes"],
        },
        "checkpointCorrelation": {"requestId": None, "runId": None, "callCount": 0},
        "routing": {"provider": provider, "model": model, "effort": effort or "none"},
        "controlDecision": "CONTINUE",
        "acceptedOutcome": None,
        "failureCode": None,
        "scopeExpanded": False,
        "downstreamEvidencePackageRef": "artifact:analysis-trajectory-evidence-package-v1",
        "effects": {"controlFlowChanged": False, "checkpointCalls": 0, "legacyFallbackUsed": False},
        "measurements": {
            "deterministic": {
                "eventCount": ledger["sourceEvents"]["eventCount"],
                "serializedEventBytes": ledger["budgetConsumption"]["serializedEventBytes"],
                "serializedLedgerBytes": len(canonical_bytes(ledger)),
            },
            "model": {"checkpointCalls": 0, "usageAvailability": "UNAVAILABLE"},
        },
        "observability": {
            "granularity": "PROVIDER_INVOCATION_LEVEL",
            "unsupportedFacts": UNSUPPORTED_FACTS,
        },
    }


def evidence_package(
    mode: str, mission: dict[str, Any], ledger: dict[str, Any],
    recommendation: dict[str, Any], run: dict[str, Any],
) -> dict[str, Any]:
    value = {
        "schemaVersion": EVIDENCE_SCHEMA,
        "packageId": "",
        "packageHash": "",
        "mode": mode,
        "missionCorrelation": {**correlation(mission), "storyRef": mission["storyRef"]},
        "ledgerCorrelation": {
            "ledgerId": ledger["ledgerId"], "ledgerHash": ledger["ledgerHash"],
            "eventCount": ledger["sourceEvents"]["eventCount"],
        },
        "evidenceRefs": ledger["evidenceAddedSinceCheckpoint"],
        "coveredGoalRefs": ledger["coveredGoalRefs"],
        "openEvidenceGapRefs": ledger["openEvidenceGapRefs"],
        "resolvedEvidenceGapRefs": ledger["resolvedEvidenceGapRefs"],
        "openDecisionRefs": ledger["openDecisionRefs"],
        "unapprovedExpansionRefs": sorted(set(
            (
                mission["scopePolicy"]["proposedExpansionScopeRefs"]
                + recommendation["supportingRefs"]["scopeRefs"]
                if recommendation["outcome"] == "SCOPE_TRIAGE_REQUIRED"
                else mission["scopePolicy"]["proposedExpansionScopeRefs"]
            )
        ) - set(mission["allowedEvidenceScopeRefs"])),
        "checkpoint": {
            "triggered": run["checkpointCorrelation"]["requestId"] is not None,
            "reasonCodes": recommendation["reasonCodes"],
            "acceptedOutcome": run["acceptedOutcome"],
            "callCount": run["checkpointCorrelation"]["callCount"],
        },
        "routing": run["routing"],
        "limitations": UNSUPPORTED_FACTS,
        "downstreamSemantics": {
            "implementationScopeClassified": False,
            "openDecisionsRemainOpen": True,
            "unapprovedExpansionsExcluded": True,
            "trajectorySidecarsAreTasks": False,
        },
    }
    semantic = copy.deepcopy(value)
    semantic.pop("packageId")
    semantic.pop("packageHash")
    hash_value = digest(semantic)
    value["packageId"] = "trajectory-package-" + hash_value.split(":", 1)[1][:24]
    value["packageHash"] = digest({key: item for key, item in value.items() if key != "packageHash"})
    return value


def save_run_and_package(
    paths: dict[str, Path], mode: str, mission: dict[str, Any], ledger: dict[str, Any],
    recommendation: dict[str, Any], run: dict[str, Any],
) -> None:
    run["measurements"]["deterministic"] = {
        "eventCount": ledger["sourceEvents"]["eventCount"],
        "serializedEventBytes": ledger["budgetConsumption"]["serializedEventBytes"],
        "serializedLedgerBytes": len(canonical_bytes(ledger)),
    }
    STATE.atomic_write(paths["integration_run"], run)
    STATE.atomic_write(paths["evidence_package"], evidence_package(mode, mission, ledger, recommendation, run))


def initialize(args: argparse.Namespace) -> None:
    mode = args.mode.upper()
    if mode not in MODES:
        raise IntegrationError("mode must be SHADOW or ENFORCE")
    workspace = Path(args.workspace)
    if not workspace.is_dir() or workspace.is_symlink():
        raise IntegrationError("workspace is missing or unsafe")
    paths = artifact_paths(workspace)
    package = load_json(Path(args.package))
    mission = STATE.build_mission(package, mission_seed(package))
    history = STATE.build_history(mission)
    STATE.atomic_write(paths["mission"], mission)
    STATE.atomic_write(paths["history"], history)
    STATE.atomic_write(paths["governor_config"], {
        "schemaVersion": "mana.analysis-trajectory.checkpoint-governor-config/v1",
        "enabled": True,
        "mode": "SHADOW",
        "maxPrimaryCalls": 1,
        "maxStructuralRepairCalls": 1,
    })


def evaluate(args: argparse.Namespace) -> None:
    mode = args.mode.upper()
    if mode not in MODES:
        raise IntegrationError("mode must be SHADOW or ENFORCE")
    boundary = args.boundary.upper()
    workspace = Path(args.workspace)
    paths = artifact_paths(workspace)
    mission = load_json(paths["mission"])
    events = STATE.read_events(Path(args.events))
    ledger = STATE.derive_ledger(mission, events)
    config = drift_config()
    observation = (
        default_observation(boundary) if args.observation == "-"
        else load_json(Path(args.observation))
    )
    if observation.get("observedBoundary") != boundary:
        raise IntegrationError("observation does not match configured real boundary")
    recommendation = DRIFT.analyze(mission, ledger, events, config, observation)
    input_value = (
        checkpoint_input_for(recommendation, observation, mission, ledger)
        if args.checkpoint_input == "-" else load_json(Path(args.checkpoint_input))
    )
    run = make_integration_run(
        mode, boundary, mission, ledger, recommendation, args.provider,
        args.model, args.effort or "none",
    )
    STATE.atomic_write(paths["ledger"], ledger)
    STATE.atomic_write(paths["drift_config"], config)
    STATE.atomic_write(paths["observation"], observation)
    STATE.atomic_write(paths["recommendation"], recommendation)
    STATE.atomic_write(paths["checkpoint_input"], input_value)
    if recommendation["outcome"] == "CHECKPOINT_RECOMMENDED":
        request = CHECKPOINT.build_request(
            mission, ledger, events, config, observation, input_value, recommendation,
        )
        STATE.atomic_write(paths["checkpoint_request"], request)
        run["checkpointCorrelation"]["requestId"] = request["requestId"]
    save_run_and_package(paths, mode, mission, ledger, recommendation, run)


def proposal_from_action(
    mission: dict[str, Any], action: dict[str, Any], approved: bool,
) -> dict[str, Any]:
    proposal_id = action.get("proposalId", action.get("actionId", "scope-expansion-proposal"))
    return {
        "schemaVersion": EXPANSION_SCHEMA,
        "proposalId": proposal_id,
        "missionId": mission["missionId"],
        "missionHash": mission["contentHash"],
        "missionRevision": mission["revision"],
        "targetScopeRef": action["targetScopeRef"],
        "reason": action.get("reason", "The observed action requires evidence outside the active mission scope."),
        "relatedGoalRefs": action.get("relatedGoalRefs", action.get("justificationGoalRefs", [])),
        "relatedConstraintRefs": action.get("relatedConstraintRefs", action.get("mandatoryConstraintRefs", [])),
        "relatedGapRefs": action.get("relatedGapRefs", action.get("justificationGapRefs", [])),
        "expectedEvidenceValue": action.get("expectedEvidence", "Bounded evidence linked to the cited mission refs."),
        "estimatedBudgetDelta": action.get("estimatedBudgetDelta", {"providerCalls": 1, "tokenProxy": 1024}),
        "approvalRequired": True,
        "approvalStatus": "APPROVED" if approved else "PENDING",
    }


def apply_approval(
    paths: dict[str, Path], mission: dict[str, Any], target_scope: str,
    approval_path: str,
) -> tuple[dict[str, Any], bool]:
    if approval_path == "-":
        return mission, False
    request = load_json(Path(approval_path))
    if target_scope not in request.get("acceptedScopeRefs", []):
        raise IntegrationError("approval does not accept the proposed target scope")
    history = load_json(paths["history"])
    revised, revised_history = STATE.revise_mission(
        history, request, approved_external_proposal_scope_refs={target_scope},
    )
    STATE.atomic_write(paths["mission"], revised)
    STATE.atomic_write(paths["history"], revised_history)
    return revised, True


def apply_outcome(
    workspace: Path, outcome: str, payload: dict[str, Any] | None,
    checkpoint_run: dict[str, Any] | None, approval_path: str, header_path: Path | None,
) -> None:
    paths = artifact_paths(workspace)
    mission = load_json(paths["mission"])
    ledger = STATE.derive_ledger(mission, STATE.read_events(Path(args_events(workspace))))
    STATE.atomic_write(paths["ledger"], ledger)
    recommendation = load_json(paths["recommendation"])
    run = load_json(paths["integration_run"])
    if run["mode"] != "ENFORCE":
        raise IntegrationError("control outcomes can be applied only in ENFORCE mode")
    call_count = 0
    if checkpoint_run is not None:
        call_count = checkpoint_run["callCounts"]["total"]
        run["checkpointCorrelation"] = {
            "requestId": checkpoint_run["requestCorrelation"]["requestId"],
            "runId": checkpoint_run["runId"],
            "callCount": call_count,
        }
        if checkpoint_run["status"] != "ACCEPTED" or checkpoint_run["outcome"] != outcome:
            raise IntegrationError("checkpoint run does not accept the supplied outcome")
    run["acceptedOutcome"] = outcome
    run["effects"]["checkpointCalls"] = call_count
    run["measurements"]["model"]["checkpointCalls"] = call_count
    if outcome == "ON_TRACK":
        run["controlDecision"] = "CONTINUE"
    elif outcome == "REANCHOR_REQUIRED":
        if payload is None or payload.get("recommendedNextAction") is None or header_path is None:
            raise IntegrationError("re-anchor requires one validated next action and a transient header")
        action = payload["recommendedNextAction"]
        header = {
            "missionId": mission["missionId"],
            "missionHash": mission["contentHash"],
            "missionRevision": mission["revision"],
            "objective": mission["objective"],
            "activeGoalRefs": payload["supportingGoalRefs"],
            "activeConstraintRefs": payload["supportingConstraintRefs"],
            "activeGapRefs": payload["supportingGapRefs"],
            "rejectedOrDeferredRefs": payload["discardedOrDeferredRefs"],
            "singleRecommendedNextAction": action,
        }
        STATE.atomic_write(header_path, header)
        run["controlDecision"] = "REANCHOR"
        run["effects"]["controlFlowChanged"] = True
    elif outcome == "SCOPE_TRIAGE_REQUIRED":
        action = None if payload is None else payload.get("scopeExpansionProposal")
        if action is None:
            observation = load_json(paths["observation"])
            proposals = observation.get("nextActionProposals", [])
            action = proposals[0] if proposals else None
        if action is None:
            run["controlDecision"] = "HALT_OWNER_REVIEW"
            run["failureCode"] = "scope-proposal-missing"
        else:
            target_scope = action["targetScopeRef"]
            revised, approved = apply_approval(paths, mission, target_scope, approval_path)
            STATE.atomic_write(paths["expansion"], proposal_from_action(mission, action, approved))
            if approved:
                mission = revised
                ledger = STATE.derive_ledger(mission, STATE.read_events(Path(args_events(workspace))))
                STATE.atomic_write(paths["ledger"], ledger)
                run["missionCorrelation"] = correlation(mission)
                run["scopeExpanded"] = True
                run["controlDecision"] = "CONTINUE"
                run["effects"]["controlFlowChanged"] = True
            else:
                run["controlDecision"] = "HALT_OWNER_REVIEW"
                run["failureCode"] = "scope-approval-required"
                run["effects"]["controlFlowChanged"] = True
    elif outcome == "STOP_SUFFICIENT_EVIDENCE":
        run["controlDecision"] = "PROCEED_DOWNSTREAM"
        run["effects"]["controlFlowChanged"] = True
    elif outcome == "STOP_NO_NEW_EVIDENCE":
        if not ledger["openEvidenceGapRefs"]:
            run["controlDecision"] = "HALT_OWNER_REVIEW"
            run["failureCode"] = "unresolved-gaps-not-explicit"
        else:
            run["controlDecision"] = "PROCEED_DOWNSTREAM"
        run["effects"]["controlFlowChanged"] = True
    elif outcome == "STOP_HARD_BUDGET":
        run["controlDecision"] = "HALT_PARTIAL"
        run["failureCode"] = "hard-budget-reached"
        run["effects"]["controlFlowChanged"] = True
    elif outcome == "NEEDS_OWNER_REVIEW":
        run["controlDecision"] = "HALT_OWNER_REVIEW"
        run["failureCode"] = "checkpoint-owner-review"
        run["effects"]["controlFlowChanged"] = True
    else:
        raise IntegrationError(f"unsupported accepted outcome: {outcome}")
    save_run_and_package(paths, "ENFORCE", mission, ledger, recommendation, run)


def args_events(workspace: Path) -> str:
    return str(workspace / "evidence/analysis-trajectory-events-v1.jsonl")


def apply_direct(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace)
    recommendation = load_json(artifact_paths(workspace)["recommendation"])
    outcome = recommendation["outcome"]
    mapping = {
        "CONTINUE_ON_TRACK": "ON_TRACK",
        "SCOPE_TRIAGE_REQUIRED": "SCOPE_TRIAGE_REQUIRED",
        "STOP_SUFFICIENT_EVIDENCE": "STOP_SUFFICIENT_EVIDENCE",
        "STOP_NO_NEW_EVIDENCE": "STOP_NO_NEW_EVIDENCE",
        "STOP_HARD_BUDGET": "STOP_HARD_BUDGET",
        "NEEDS_OWNER_REVIEW": "NEEDS_OWNER_REVIEW",
    }
    if outcome == "CHECKPOINT_RECOMMENDED":
        raise IntegrationError("checkpoint recommendation requires a validated checkpoint response")
    apply_outcome(workspace, mapping[outcome], None, None, args.approval, None)


def apply_response(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace)
    payload = load_json(Path(args.response))
    checkpoint_run = load_json(Path(args.checkpoint_run))
    apply_outcome(
        workspace, payload["outcome"], payload, checkpoint_run,
        args.approval, Path(args.header),
    )


def mark_failure(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace)
    paths = artifact_paths(workspace)
    mission = load_json(paths["mission"])
    ledger = STATE.derive_ledger(mission, STATE.read_events(Path(args_events(workspace))))
    STATE.atomic_write(paths["ledger"], ledger)
    recommendation = load_json(paths["recommendation"])
    run = load_json(paths["integration_run"])
    if paths["checkpoint_run"].is_file():
        checkpoint_run = load_json(paths["checkpoint_run"])
        call_count = checkpoint_run["callCounts"]["total"]
        run["checkpointCorrelation"] = {
            "requestId": checkpoint_run["requestCorrelation"]["requestId"],
            "runId": checkpoint_run["runId"],
            "callCount": call_count,
        }
        run["effects"]["checkpointCalls"] = call_count
        run["measurements"]["model"]["checkpointCalls"] = call_count
    run["acceptedOutcome"] = "NEEDS_OWNER_REVIEW"
    run["controlDecision"] = "HALT_OWNER_REVIEW"
    run["failureCode"] = STATE.valid_ref(args.code, "failureCode")
    run["effects"]["controlFlowChanged"] = run["mode"] == "ENFORCE"
    save_run_and_package(paths, run["mode"], mission, ledger, recommendation, run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("initialize")
    init.add_argument("package"); init.add_argument("workspace"); init.add_argument("mode")
    init.set_defaults(function=initialize)
    evaluate_parser = commands.add_parser("evaluate")
    for name in ("workspace", "events", "mode", "boundary", "provider", "model", "effort", "observation", "checkpoint_input"):
        evaluate_parser.add_argument(name)
    evaluate_parser.set_defaults(function=evaluate)
    direct = commands.add_parser("apply-direct")
    direct.add_argument("workspace"); direct.add_argument("approval")
    direct.set_defaults(function=apply_direct)
    response = commands.add_parser("apply-response")
    for name in ("workspace", "response", "checkpoint_run", "approval", "header"):
        response.add_argument(name)
    response.set_defaults(function=apply_response)
    failure = commands.add_parser("mark-failure")
    failure.add_argument("workspace"); failure.add_argument("code")
    failure.set_defaults(function=mark_failure)
    args = parser.parse_args()
    try:
        args.function(args)
        return 0
    except (IntegrationError, STATE.StateError, DRIFT.DriftError, CHECKPOINT.CheckpointError, OSError, KeyError) as error:
        print(f"ERROR: Analysis Trajectory integration: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
