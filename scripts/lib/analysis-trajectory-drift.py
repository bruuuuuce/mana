#!/usr/bin/env python3
"""Deterministic TG04 trajectory detector operating in advisory shadow mode.

The detector consumes only the host-owned Mission Contract, a recomputable
Trajectory Ledger, TG02 events, and a structured observable-boundary record.
It never dispatches a provider, changes control flow, or writes final analysis
artifacts.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


CONFIG_SCHEMA = "mana.analysis-trajectory.drift-config/v1"
OBSERVATION_SCHEMA = "mana.analysis-trajectory.drift-observation/v1"
RECOMMENDATION_SCHEMA = "mana.analysis-trajectory.drift-recommendation/v1"
MATRIX_INPUT_SCHEMA = "mana.analysis-trajectory.drift-evaluation-input/v1"
MATRIX_SCHEMA = "mana.analysis-trajectory.drift-evaluation-matrix/v1"

SIGNALS = (
    "UNSUPPORTED_NEXT_ACTION",
    "UNAPPROVED_SCOPE_EXPANSION",
    "OPEN_DECISION_ASSUMPTION",
    "REPEATED_TARGET_NO_NEW_EVIDENCE",
    "NO_NEW_EVIDENCE_STREAK",
    "REJECTED_HYPOTHESIS_REOPENED",
    "SOFT_BUDGET_PRESSURE",
    "HARD_BUDGET_EXCEEDED",
    "SUFFICIENT_EVIDENCE_REACHED",
    "MANDATORY_CROSS_CUTTING_EXPANSION",
    "FINAL_SYNTHESIS_CHECKPOINT",
)

OUTCOMES = {
    "CONTINUE_ON_TRACK",
    "CHECKPOINT_RECOMMENDED",
    "SCOPE_TRIAGE_REQUIRED",
    "STOP_SUFFICIENT_EVIDENCE",
    "STOP_NO_NEW_EVIDENCE",
    "STOP_HARD_BUDGET",
    "NEEDS_OWNER_REVIEW",
}

BOUNDARIES = {
    "ITERATION_BOUNDARY",
    "NEXT_ACTION_BOUNDARY",
    "FINAL_SYNTHESIS_BOUNDARY",
    "PROVIDER_INVOCATION_BOUNDARY",
    "PROVIDER_COMPLETION_BOUNDARY",
}

SEVERITIES = {
    "UNSUPPORTED_NEXT_ACTION": "WARNING",
    "UNAPPROVED_SCOPE_EXPANSION": "REVIEW",
    "OPEN_DECISION_ASSUMPTION": "REVIEW",
    "REPEATED_TARGET_NO_NEW_EVIDENCE": "WARNING",
    "NO_NEW_EVIDENCE_STREAK": "STOP",
    "REJECTED_HYPOTHESIS_REOPENED": "WARNING",
    "SOFT_BUDGET_PRESSURE": "WARNING",
    "HARD_BUDGET_EXCEEDED": "STOP",
    "SUFFICIENT_EVIDENCE_REACHED": "STOP",
    "MANDATORY_CROSS_CUTTING_EXPANSION": "INFO",
    "FINAL_SYNTHESIS_CHECKPOINT": "INFO",
}

SUPPORT_KEYS = (
    "eventRefs", "evidenceRefs", "goalRefs", "gapRefs", "actionRefs",
    "scopeRefs", "decisionRefs", "constraintRefs",
)


def load_state_module() -> Any:
    path = Path(__file__).with_name("analysis-trajectory-state.py")
    spec = importlib.util.spec_from_file_location("analysis_trajectory_state", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load host state module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STATE = load_state_module()


class DriftError(ValueError):
    """A deterministic detector input or integrity failure."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def exact_keys(value: Any, expected: set[str], location: str) -> None:
    if not isinstance(value, dict):
        raise DriftError(f"{location}: expected an object")
    actual = set(value)
    if actual != expected:
        raise DriftError(
            f"{location}: fields differ; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DriftError(f"cannot read JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise DriftError(f"JSON input must be an object: {path}")
    STATE.reject_raw_fields(value)
    return value


def refs(value: Any, location: str, maximum: int = 256) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise DriftError(f"{location}: expected at most {maximum} refs")
    normalized: list[str] = []
    for index, item in enumerate(value):
        try:
            normalized.append(STATE.valid_ref(item, f"{location}[{index}]"))
        except STATE.StateError as error:
            raise DriftError(str(error)) from error
    if len(set(normalized)) != len(normalized):
        raise DriftError(f"{location}: duplicate refs are not allowed")
    return sorted(normalized)


def bounded_note(value: Any, location: str) -> str:
    if not isinstance(value, str) or len(value) > 512:
        raise DriftError(f"{location}: expected a string no longer than 512 chars")
    return value


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    exact_keys(
        value,
        {"schemaVersion", "enabled", "mode", "thresholds", "evidenceSufficiency", "equivalentTargetGroups"},
        "config",
    )
    if value["schemaVersion"] != CONFIG_SCHEMA:
        raise DriftError("config: unsupported schema version")
    if value["enabled"] is not True or value["mode"] != "SHADOW":
        raise DriftError("TG04 detector may run only when enabled in SHADOW mode")
    thresholds = value["thresholds"]
    exact_keys(
        thresholds,
        {"repeatedTargetVisitCount", "noNewEvidenceStreak", "softBudgetWarningPercent"},
        "config.thresholds",
    )
    limits = {
        "repeatedTargetVisitCount": (2, 32),
        "noNewEvidenceStreak": (2, 32),
        "softBudgetWarningPercent": (50, 100),
    }
    for key, (minimum, maximum) in limits.items():
        amount = thresholds[key]
        if not isinstance(amount, int) or isinstance(amount, bool) or not minimum <= amount <= maximum:
            raise DriftError(f"config.thresholds.{key}: out of range")
    sufficiency = value["evidenceSufficiency"]
    exact_keys(
        sufficiency,
        {
            "minimumEvidenceRefsPerAcceptanceCriterion",
            "minimumResolvedGapsPerMandatoryConstraint",
            "requireNoOpenEvidenceGaps",
        },
        "config.evidenceSufficiency",
    )
    for key in (
        "minimumEvidenceRefsPerAcceptanceCriterion",
        "minimumResolvedGapsPerMandatoryConstraint",
    ):
        amount = sufficiency[key]
        if not isinstance(amount, int) or isinstance(amount, bool) or not 1 <= amount <= 16:
            raise DriftError(f"config.evidenceSufficiency.{key}: out of range")
    if sufficiency["requireNoOpenEvidenceGaps"] is not True:
        raise DriftError("TG04 sufficiency must require no open evidence gaps")
    groups = value["equivalentTargetGroups"]
    if not isinstance(groups, list) or len(groups) > 64:
        raise DriftError("config.equivalentTargetGroups: expected at most 64 groups")
    used: set[str] = set()
    normalized_groups: list[list[str]] = []
    for index, group in enumerate(groups):
        normalized = refs(group, f"config.equivalentTargetGroups[{index}]", 32)
        if len(normalized) < 2:
            raise DriftError("equivalent target groups require at least two targets")
        overlap = used & set(normalized)
        if overlap:
            raise DriftError(f"equivalent target groups overlap: {sorted(overlap)}")
        used.update(normalized)
        normalized_groups.append(normalized)
    normalized_groups.sort()
    return {
        "schemaVersion": CONFIG_SCHEMA,
        "enabled": True,
        "mode": "SHADOW",
        "thresholds": {key: thresholds[key] for key in sorted(thresholds)},
        "evidenceSufficiency": {key: sufficiency[key] for key in sorted(sufficiency)},
        "equivalentTargetGroups": normalized_groups,
    }


def validate_observation(
    value: dict[str, Any], mission: dict[str, Any], ledger: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    exact_keys(
        value,
        {"schemaVersion", "observedBoundary", "finalSynthesisRequested", "nextActionProposals"},
        "observation",
    )
    if value["schemaVersion"] != OBSERVATION_SCHEMA:
        raise DriftError("observation: unsupported schema version")
    boundary = value["observedBoundary"]
    if boundary not in BOUNDARIES:
        raise DriftError("observation.observedBoundary: unsupported boundary")
    final = value["finalSynthesisRequested"]
    if not isinstance(final, bool):
        raise DriftError("observation.finalSynthesisRequested: expected boolean")
    if final != (boundary == "FINAL_SYNTHESIS_BOUNDARY"):
        raise DriftError("final synthesis flag and observed boundary disagree")
    actions = value["nextActionProposals"]
    if not isinstance(actions, list) or len(actions) > 16:
        raise DriftError("observation.nextActionProposals: expected at most 16 actions")
    if actions and boundary != "NEXT_ACTION_BOUNDARY":
        raise DriftError("next actions may only be supplied at NEXT_ACTION_BOUNDARY")
    action_keys = {
        "actionId", "targetScopeRef", "justificationGoalRefs", "justificationGapRefs",
        "mandatoryConstraintRefs", "assumedDecisionRefs", "decisionEvidenceRefs",
        "supportingEventRefs",
    }
    valid_event_refs = {event["eventId"] for event in events}
    valid_evidence_refs = {
        evidence for event in events for evidence in event["evidenceAddedRefs"]
    }
    goals = set(mission["acceptanceCriterionRefs"])
    constraints = set(mission["mandatoryConstraintRefs"])
    open_gaps = set(ledger["openEvidenceGapRefs"])
    open_decisions = set(ledger["openDecisionRefs"])
    normalized_actions: list[dict[str, Any]] = []
    for index, action in enumerate(actions):
        exact_keys(action, action_keys, f"observation.nextActionProposals[{index}]")
        try:
            action_id = STATE.valid_ref(action["actionId"], f"action[{index}].actionId")
            target = STATE.valid_ref(action["targetScopeRef"], f"action[{index}].targetScopeRef")
        except STATE.StateError as error:
            raise DriftError(str(error)) from error
        action_goals = refs(action["justificationGoalRefs"], f"action[{index}].justificationGoalRefs")
        action_gaps = refs(action["justificationGapRefs"], f"action[{index}].justificationGapRefs")
        action_constraints = refs(action["mandatoryConstraintRefs"], f"action[{index}].mandatoryConstraintRefs")
        assumed = refs(action["assumedDecisionRefs"], f"action[{index}].assumedDecisionRefs")
        decision_evidence = refs(action["decisionEvidenceRefs"], f"action[{index}].decisionEvidenceRefs")
        supporting_events = refs(action["supportingEventRefs"], f"action[{index}].supportingEventRefs")
        if not set(action_goals) <= goals:
            raise DriftError(f"action {action_id} references an unknown acceptance criterion")
        if not set(action_gaps) <= open_gaps:
            raise DriftError(f"action {action_id} references a gap that is not open")
        if not set(action_constraints) <= constraints:
            raise DriftError(f"action {action_id} references an unknown mandatory constraint")
        if not set(assumed) <= open_decisions:
            raise DriftError(f"action {action_id} assumes a decision not known to be open")
        if not set(decision_evidence) <= valid_evidence_refs:
            raise DriftError(f"action {action_id} references unknown decision evidence")
        if not set(supporting_events) <= valid_event_refs:
            raise DriftError(f"action {action_id} references an unknown telemetry event")
        normalized_actions.append({
            "actionId": action_id,
            "targetScopeRef": target,
            "justificationGoalRefs": action_goals,
            "justificationGapRefs": action_gaps,
            "mandatoryConstraintRefs": action_constraints,
            "assumedDecisionRefs": assumed,
            "decisionEvidenceRefs": decision_evidence,
            "supportingEventRefs": supporting_events,
        })
    normalized_actions.sort(key=lambda item: item["actionId"])
    if len({action["actionId"] for action in normalized_actions}) != len(normalized_actions):
        raise DriftError("observation contains duplicate action IDs")
    return {
        "schemaVersion": OBSERVATION_SCHEMA,
        "observedBoundary": boundary,
        "finalSynthesisRequested": final,
        "nextActionProposals": normalized_actions,
    }


def target_key(target: str, groups: list[list[str]]) -> str:
    for group in groups:
        if target in group:
            return "equivalent:" + ",".join(group)
    return "target:" + target


def visit_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed = [
        event for event in events
        if event["eventType"] == "provider_iteration_completed"
        and event["boundary"] != "public_pipeline"
        and event["targetScopeRef"] != "none"
    ]
    if completed:
        return completed
    return [
        event for event in events
        if event["eventType"] in {"target_revisited", "search_scope_entered", "search_scope_changed"}
        and event["boundary"] != "public_pipeline"
        and event["targetScopeRef"] != "none"
    ]


def scope_visit_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only boundaries that expose an analysis target as a scope.

    A provider invocation/completion target identifies the host envelope, not
    provider-internal navigation, and must not be reinterpreted as a component
    scope visit.
    """
    return [
        event for event in visit_events(events)
        if event["boundary"] not in {"provider_invocation", "provider_completion"}
    ]


def scope_entry_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every explicit host-visible scope entry/change observation."""
    return [
        event for event in events
        if event["eventType"] in {
            "provider_iteration_completed", "search_scope_entered",
            "search_scope_changed", "target_revisited",
        }
        and event["boundary"] not in {"public_pipeline", "provider_invocation", "provider_completion"}
        and event["targetScopeRef"] != "none"
    ]


def add_support(support: dict[str, set[str]], key: str, values: Any) -> None:
    if isinstance(values, str):
        support[key].add(values)
    else:
        support[key].update(values)


def analyze(
    mission: dict[str, Any], ledger: dict[str, Any], events: list[dict[str, Any]],
    config_value: dict[str, Any], observation_value: dict[str, Any],
) -> dict[str, Any]:
    try:
        STATE.validate_mission(mission)
        STATE.validate_ledger(ledger, mission, events)
    except STATE.StateError as error:
        raise DriftError(str(error)) from error
    config = validate_config(config_value)
    observation = validate_observation(observation_value, mission, ledger, events)
    support = {key: set() for key in SUPPORT_KEYS}
    triggered: dict[str, list[str]] = {}
    not_observable: set[str] = set()
    actions = observation["nextActionProposals"]
    next_action_observed = observation["observedBoundary"] == "NEXT_ACTION_BOUNDARY"

    if not next_action_observed:
        not_observable.update({
            "UNSUPPORTED_NEXT_ACTION", "UNAPPROVED_SCOPE_EXPANSION", "OPEN_DECISION_ASSUMPTION",
        })
    else:
        unsupported = [
            action for action in actions
            if not action["justificationGoalRefs"]
            and not action["justificationGapRefs"]
            and not action["mandatoryConstraintRefs"]
        ]
        if unsupported:
            refs_for_signal = [action["actionId"] for action in unsupported]
            triggered["UNSUPPORTED_NEXT_ACTION"] = refs_for_signal
            add_support(support, "actionRefs", refs_for_signal)
            for action in unsupported:
                add_support(support, "scopeRefs", action["targetScopeRef"])

        unapproved = [
            action for action in actions
            if action["targetScopeRef"] not in mission["allowedEvidenceScopeRefs"]
        ]
        if unapproved:
            refs_for_signal = [action["actionId"] for action in unapproved]
            triggered["UNAPPROVED_SCOPE_EXPANSION"] = refs_for_signal
            add_support(support, "actionRefs", refs_for_signal)
            for action in unapproved:
                add_support(support, "scopeRefs", action["targetScopeRef"])
                add_support(support, "eventRefs", action["supportingEventRefs"])

        assumed = [
            action for action in actions
            if action["assumedDecisionRefs"] and not action["decisionEvidenceRefs"]
        ]
        if assumed:
            signal_refs = sorted({
                ref for action in assumed for ref in [action["actionId"], *action["assumedDecisionRefs"]]
            })
            triggered["OPEN_DECISION_ASSUMPTION"] = signal_refs
            for action in assumed:
                add_support(support, "actionRefs", action["actionId"])
                add_support(support, "decisionRefs", action["assumedDecisionRefs"])
                add_support(support, "eventRefs", action["supportingEventRefs"])

    entered_unapproved = [
        event for event in scope_entry_events(events)
        if event["targetScopeRef"] not in mission["allowedEvidenceScopeRefs"]
    ]
    if entered_unapproved:
        event_refs = [event["eventId"] for event in entered_unapproved]
        triggered["UNAPPROVED_SCOPE_EXPANSION"] = sorted(set([
            *triggered.get("UNAPPROVED_SCOPE_EXPANSION", []), *event_refs,
        ]))
        add_support(support, "eventRefs", event_refs)
        for event in entered_unapproved:
            add_support(support, "scopeRefs", event["targetScopeRef"])

    groups = config["equivalentTargetGroups"]
    visits = scope_visit_events(events)
    repeat_threshold = config["thresholds"]["repeatedTargetVisitCount"]
    by_target: dict[str, list[dict[str, Any]]] = {}
    for event in visits:
        by_target.setdefault(target_key(event["targetScopeRef"], groups), []).append(event)
    repeated_refs: list[str] = []
    for target_visits in by_target.values():
        if len(target_visits) < repeat_threshold:
            continue
        tail = target_visits[-repeat_threshold:]
        if all(not event["evidenceAddedRefs"] for event in tail[1:]):
            repeated_refs.extend(event["eventId"] for event in tail)
            for event in tail:
                add_support(support, "scopeRefs", event["targetScopeRef"])
    if repeated_refs:
        triggered["REPEATED_TARGET_NO_NEW_EVIDENCE"] = sorted(set(repeated_refs))
        add_support(support, "eventRefs", repeated_refs)

    streak_threshold = config["thresholds"]["noNewEvidenceStreak"]
    completed = [
        event for event in events
        if event["eventType"] == "provider_iteration_completed" and event["outcome"] == "completed"
    ]
    streak: list[dict[str, Any]] = []
    for event in reversed(completed):
        if event["evidenceAddedRefs"]:
            break
        streak.append(event)
    streak.reverse()
    if ledger["noNewEvidenceStreak"] >= streak_threshold and len(streak) >= streak_threshold:
        streak_refs = [event["eventId"] for event in streak]
        triggered["NO_NEW_EVIDENCE_STREAK"] = streak_refs
        add_support(support, "eventRefs", streak_refs)
        for event in streak:
            add_support(support, "gapRefs", event["evidenceGapRefs"])
            add_support(support, "scopeRefs", event["targetScopeRef"])

    active_rejections: dict[str, str] = {}
    reopened_refs: list[str] = []
    for event in events:
        target = event["targetScopeRef"]
        if event["eventType"] == "hypothesis_rejected" and target != "none":
            active_rejections[target] = event["eventId"]
            continue
        if target in active_rejections and event["evidenceAddedRefs"]:
            active_rejections.pop(target, None)
            continue
        if (
            target in active_rejections
            and event["eventType"] in {"target_revisited", "provider_iteration_completed", "search_scope_entered", "search_scope_changed"}
            and not event["evidenceAddedRefs"]
        ):
            reopened_refs.extend([active_rejections[target], event["eventId"]])
            add_support(support, "scopeRefs", target)
    if reopened_refs:
        triggered["REJECTED_HYPOTHESIS_REOPENED"] = sorted(set(reopened_refs))
        add_support(support, "eventRefs", reopened_refs)

    budget_map = {
        "eventCount": "maxEvents",
        "providerIterations": "maxProviderIterations",
        "evidenceRefCount": "maxEvidenceRefs",
        "visitedScopeCount": "maxVisitedScopeRefs",
    }
    hard_fields: list[str] = []
    soft_fields: list[str] = []
    warning_percent = config["thresholds"]["softBudgetWarningPercent"]
    for consumption_key, limit_key in budget_map.items():
        consumed = ledger["budgetConsumption"][consumption_key]
        if consumed > mission["hardBudgets"][limit_key]:
            hard_fields.append(limit_key)
        if consumed * 100 >= mission["softBudgets"][limit_key] * warning_percent:
            soft_fields.append(limit_key)
    source_refs = [ref for ref in (
        ledger["sourceEvents"]["firstEventRef"], ledger["sourceEvents"]["lastEventRef"]
    ) if ref is not None]
    if soft_fields:
        triggered["SOFT_BUDGET_PRESSURE"] = sorted([*soft_fields, *source_refs])
        add_support(support, "eventRefs", source_refs)
    if hard_fields:
        triggered["HARD_BUDGET_EXCEEDED"] = sorted([*hard_fields, *source_refs])
        add_support(support, "eventRefs", source_refs)

    evidence_counts = {goal: 0 for goal in mission["acceptanceCriterionRefs"]}
    for event in events:
        if event["evidenceAddedRefs"]:
            for goal in event["acceptanceCriterionRefs"]:
                evidence_counts[goal] += len(event["evidenceAddedRefs"])
    resolved_constraint_counts = {constraint: 0 for constraint in mission["mandatoryConstraintRefs"]}
    for gap in ledger["evidenceGaps"]:
        if gap["status"] == "RESOLVED":
            for constraint in gap["relatedMandatoryConstraintRefs"]:
                resolved_constraint_counts[constraint] += 1
    sufficiency = config["evidenceSufficiency"]
    enough_goals = all(
        count >= sufficiency["minimumEvidenceRefsPerAcceptanceCriterion"]
        for count in evidence_counts.values()
    )
    enough_constraints = all(
        count >= sufficiency["minimumResolvedGapsPerMandatoryConstraint"]
        for count in resolved_constraint_counts.values()
    )
    no_blocking_gaps = not ledger["openEvidenceGapRefs"]
    if enough_goals and enough_constraints and no_blocking_gaps:
        sufficient_refs = sorted({
            *mission["acceptanceCriterionRefs"], *mission["mandatoryConstraintRefs"],
            *ledger["resolvedEvidenceGapRefs"], *ledger["evidenceAddedSinceCheckpoint"],
        })
        triggered["SUFFICIENT_EVIDENCE_REACHED"] = sufficient_refs
        add_support(support, "goalRefs", mission["acceptanceCriterionRefs"])
        add_support(support, "constraintRefs", mission["mandatoryConstraintRefs"])
        add_support(support, "gapRefs", ledger["resolvedEvidenceGapRefs"])
        add_support(support, "evidenceRefs", ledger["evidenceAddedSinceCheckpoint"])
        for gap in ledger["evidenceGaps"]:
            if gap["status"] == "RESOLVED" and gap["closedEventRef"] is not None:
                add_support(support, "eventRefs", gap["closedEventRef"])

    mandatory_scopes = set(mission["scopePolicy"]["globalMandatoryScopeRefs"])
    links: dict[str, set[str]] = {}
    for link in mission["scopePolicy"]["mandatoryConstraintScopeLinks"]:
        links.setdefault(link["scopeRef"], set()).update(link["mandatoryConstraintRefs"])
    mandatory_actions = []
    for action in actions:
        target = action["targetScopeRef"]
        constraints = set(action["mandatoryConstraintRefs"])
        linked = target in mandatory_scopes or bool(constraints & links.get(target, set()))
        if constraints and linked and target in mission["allowedEvidenceScopeRefs"]:
            mandatory_actions.append(action)
    if mandatory_actions:
        mandatory_refs = sorted({
            ref for action in mandatory_actions
            for ref in [action["actionId"], action["targetScopeRef"], *action["mandatoryConstraintRefs"]]
        })
        triggered["MANDATORY_CROSS_CUTTING_EXPANSION"] = mandatory_refs
        for action in mandatory_actions:
            add_support(support, "actionRefs", action["actionId"])
            add_support(support, "scopeRefs", action["targetScopeRef"])
            add_support(support, "constraintRefs", action["mandatoryConstraintRefs"])
            add_support(support, "goalRefs", action["justificationGoalRefs"])
            add_support(support, "gapRefs", action["justificationGapRefs"])
            add_support(support, "eventRefs", action["supportingEventRefs"])

    mandatory_event_refs: list[str] = []
    gap_by_id = {gap["gapId"]: gap for gap in mission["evidenceGaps"]}
    for event in scope_entry_events(events):
        target = event["targetScopeRef"]
        linked_constraints = links.get(target, set())
        gap_constraints = {
            constraint
            for gap_ref in event["evidenceGapRefs"]
            for constraint in gap_by_id[gap_ref]["relatedMandatoryConstraintRefs"]
        }
        if (
            target in mission["allowedEvidenceScopeRefs"]
            and target not in mission["scopePolicy"]["initialStoryScopeRefs"]
            and (target in mandatory_scopes or bool(linked_constraints & gap_constraints))
            and (linked_constraints or gap_constraints)
        ):
            mandatory_event_refs.append(event["eventId"])
            add_support(support, "eventRefs", event["eventId"])
            add_support(support, "scopeRefs", target)
            add_support(support, "gapRefs", event["evidenceGapRefs"])
            add_support(support, "constraintRefs", linked_constraints | gap_constraints)
    if mandatory_event_refs:
        triggered["MANDATORY_CROSS_CUTTING_EXPANSION"] = sorted(set([
            *triggered.get("MANDATORY_CROSS_CUTTING_EXPANSION", []), *mandatory_event_refs,
        ]))

    if observation["finalSynthesisRequested"]:
        final_refs = source_refs or [ledger["ledgerId"]]
        triggered["FINAL_SYNTHESIS_CHECKPOINT"] = final_refs
        add_support(support, "eventRefs", source_refs)

    if "HARD_BUDGET_EXCEEDED" in triggered:
        outcome = "STOP_HARD_BUDGET"
    elif "SUFFICIENT_EVIDENCE_REACHED" in triggered:
        outcome = "STOP_SUFFICIENT_EVIDENCE"
    elif "UNAPPROVED_SCOPE_EXPANSION" in triggered:
        outcome = "SCOPE_TRIAGE_REQUIRED"
    elif "OPEN_DECISION_ASSUMPTION" in triggered:
        outcome = "NEEDS_OWNER_REVIEW"
    elif "NO_NEW_EVIDENCE_STREAK" in triggered:
        outcome = "STOP_NO_NEW_EVIDENCE"
    elif any(code in triggered for code in (
        "UNSUPPORTED_NEXT_ACTION", "REPEATED_TARGET_NO_NEW_EVIDENCE",
        "REJECTED_HYPOTHESIS_REOPENED", "SOFT_BUDGET_PRESSURE",
        "FINAL_SYNTHESIS_CHECKPOINT",
    )):
        outcome = "CHECKPOINT_RECOMMENDED"
    else:
        outcome = "CONTINUE_ON_TRACK"

    signal_evaluations = []
    for code in SIGNALS:
        if code in triggered:
            status = "TRIGGERED"
            signal_refs = sorted(set(triggered[code]))
        elif code in not_observable:
            status = "NOT_OBSERVABLE"
            signal_refs = []
        else:
            status = "CLEAR"
            signal_refs = []
        signal_evaluations.append({
            "reasonCode": code,
            "status": status,
            "severity": SEVERITIES[code],
            "refs": signal_refs,
        })

    unsupported_facts = []
    if ledger["observability"] == "OPAQUE_PROVIDER_BOUNDARY":
        unsupported_facts.extend([
            "provider-internal-context-expansion",
            "provider-internal-delegation",
            "provider-internal-file-read",
            "provider-internal-tool-call",
        ])
    if not next_action_observed:
        unsupported_facts.append("structured-next-action")
    reason_codes = [code for code in SIGNALS if code in triggered]
    config_hash = digest(config)
    identity = {
        "missionHash": mission["contentHash"],
        "ledgerHash": ledger["ledgerHash"],
        "configHash": config_hash,
        "observationHash": digest(observation),
    }
    recommendation: dict[str, Any] = {
        "schemaVersion": RECOMMENDATION_SCHEMA,
        "recommendationId": "recommendation-" + hashlib.sha256(canonical_bytes(identity)).hexdigest()[:24],
        "recommendationHash": "",
        "mode": "SHADOW",
        "advisory": True,
        "outcome": outcome,
        "reasonCodes": reason_codes,
        "missionCorrelation": {
            "missionId": mission["missionId"],
            "missionHash": mission["contentHash"],
            "missionRevision": mission["revision"],
            "ledgerId": ledger["ledgerId"],
            "ledgerHash": ledger["ledgerHash"],
        },
        "observedBoundary": observation["observedBoundary"],
        "modelCheckpointPermittedInTG05": outcome == "CHECKPOINT_RECOMMENDED",
        "continuedExecutionUnsafeInFutureEnforcement": any(code in triggered for code in {
            "UNAPPROVED_SCOPE_EXPANSION", "OPEN_DECISION_ASSUMPTION",
            "NO_NEW_EVIDENCE_STREAK", "HARD_BUDGET_EXCEEDED",
        }),
        "signalEvaluations": signal_evaluations,
        "supportingRefs": {key: sorted(support[key]) for key in SUPPORT_KEYS},
        "observability": {
            "ledgerGranularity": ledger["observability"],
            "nextAction": "OBSERVED" if next_action_observed else "NOT_OBSERVABLE",
            "unsupportedFacts": sorted(set(unsupported_facts)),
        },
        "configCorrelation": {
            "configHash": config_hash,
            "thresholds": copy.deepcopy(config["thresholds"]),
        },
        "metrics": {
            "signalCount": len(SIGNALS),
            "triggeredSignalCount": len(triggered),
            "notObservableSignalCount": len(not_observable - set(triggered)),
            "eventCount": ledger["budgetConsumption"]["eventCount"],
            "providerIterations": ledger["budgetConsumption"]["providerIterations"],
            "evidenceRefCount": ledger["budgetConsumption"]["evidenceRefCount"],
            "visitedScopeCount": ledger["budgetConsumption"]["visitedScopeCount"],
        },
        "effects": {
            "providerCalls": 0,
            "networkCalls": 0,
            "controlFlowChanged": False,
            "finalArtifactsChanged": False,
            "recommendationPublished": True,
        },
    }
    recommendation["recommendationHash"] = recommendation_hash(recommendation)
    validate_recommendation(recommendation)
    return recommendation


def recommendation_hash(value: dict[str, Any]) -> str:
    unhashed = copy.deepcopy(value)
    unhashed.pop("recommendationHash", None)
    return digest(unhashed)


def validate_recommendation(value: dict[str, Any]) -> None:
    expected = {
        "schemaVersion", "recommendationId", "recommendationHash", "mode", "advisory",
        "outcome", "reasonCodes", "missionCorrelation", "observedBoundary",
        "modelCheckpointPermittedInTG05", "continuedExecutionUnsafeInFutureEnforcement",
        "signalEvaluations", "supportingRefs", "observability", "configCorrelation", "metrics", "effects",
    }
    exact_keys(value, expected, "recommendation")
    if value["schemaVersion"] != RECOMMENDATION_SCHEMA or value["mode"] != "SHADOW" or value["advisory"] is not True:
        raise DriftError("recommendation has invalid schema or shadow markers")
    if value["outcome"] not in OUTCOMES:
        raise DriftError("recommendation has invalid outcome")
    if value["reasonCodes"] != [
        code for code in SIGNALS
        if any(item.get("reasonCode") == code and item.get("status") == "TRIGGERED" for item in value["signalEvaluations"])
    ]:
        raise DriftError("recommendation reason codes do not match triggered signals")
    evaluations = value["signalEvaluations"]
    if not isinstance(evaluations, list) or [item.get("reasonCode") for item in evaluations] != list(SIGNALS):
        raise DriftError("recommendation must contain every signal exactly once in canonical order")
    for index, evaluation in enumerate(evaluations):
        exact_keys(evaluation, {"reasonCode", "status", "severity", "refs"}, f"signalEvaluations[{index}]")
        if evaluation["status"] not in {"TRIGGERED", "CLEAR", "NOT_OBSERVABLE"}:
            raise DriftError("signal evaluation has invalid status")
        if evaluation["severity"] != SEVERITIES[evaluation["reasonCode"]]:
            raise DriftError("signal evaluation has invalid severity")
        refs(evaluation["refs"], f"signalEvaluations[{index}].refs")
        if evaluation["status"] == "TRIGGERED" and not evaluation["refs"]:
            raise DriftError("triggered signal must be reference-grounded")
        if evaluation["status"] != "TRIGGERED" and evaluation["refs"]:
            raise DriftError("non-triggered signal cannot claim supporting refs")
    exact_keys(value["supportingRefs"], set(SUPPORT_KEYS), "recommendation.supportingRefs")
    for key in SUPPORT_KEYS:
        refs(value["supportingRefs"][key], f"recommendation.supportingRefs.{key}")
    metrics = value["metrics"]
    metric_keys = {
        "signalCount", "triggeredSignalCount", "notObservableSignalCount",
        "eventCount", "providerIterations", "evidenceRefCount", "visitedScopeCount",
    }
    exact_keys(metrics, metric_keys, "recommendation.metrics")
    for key in metric_keys:
        if not isinstance(metrics[key], int) or isinstance(metrics[key], bool) or metrics[key] < 0:
            raise DriftError(f"recommendation.metrics.{key} must be a non-negative integer")
    if metrics["signalCount"] != len(SIGNALS):
        raise DriftError("recommendation.metrics.signalCount is invalid")
    if metrics["triggeredSignalCount"] != sum(item["status"] == "TRIGGERED" for item in evaluations):
        raise DriftError("recommendation.metrics.triggeredSignalCount is invalid")
    if metrics["notObservableSignalCount"] != sum(item["status"] == "NOT_OBSERVABLE" for item in evaluations):
        raise DriftError("recommendation.metrics.notObservableSignalCount is invalid")
    expected_effects = {
        "providerCalls": 0, "networkCalls": 0, "controlFlowChanged": False,
        "finalArtifactsChanged": False, "recommendationPublished": True,
    }
    if value["effects"] != expected_effects:
        raise DriftError("recommendation effects are not advisory/zero-token")
    if value["recommendationHash"] != recommendation_hash(value):
        raise DriftError("recommendation hash integrity check failed")


def build_matrix(manifest: dict[str, Any], base: Path) -> dict[str, Any]:
    exact_keys(manifest, {"schemaVersion", "cases"}, "matrixInput")
    if manifest["schemaVersion"] != MATRIX_INPUT_SCHEMA:
        raise DriftError("matrixInput: unsupported schema version")
    cases = manifest["cases"]
    if not isinstance(cases, list) or len(cases) < 10 or len(cases) > 64:
        raise DriftError("matrixInput.cases: expected 10 to 64 cases")
    expected_keys = {
        "caseId", "recommendationFile", "expectedOutcome", "expectedReasonCodes",
        "falsePositiveNotes", "falseNegativeNotes", "unsupportedObservabilityNotes",
    }
    output_cases = []
    for index, item in enumerate(cases):
        exact_keys(item, expected_keys, f"matrixInput.cases[{index}]")
        case_id = STATE.valid_ref(item["caseId"], f"matrixInput.cases[{index}].caseId")
        recommendation_path = Path(item["recommendationFile"])
        if recommendation_path.is_absolute() or ".." in recommendation_path.parts:
            raise DriftError("matrix recommendation paths must stay relative to the manifest")
        recommendation = load_json(base / recommendation_path)
        validate_recommendation(recommendation)
        expected_outcome = item["expectedOutcome"]
        if expected_outcome not in OUTCOMES:
            raise DriftError(f"matrix case {case_id} has an invalid expected outcome")
        expected_reasons = refs(item["expectedReasonCodes"], f"matrix case {case_id} expectedReasonCodes", 11)
        expected_reasons = [code for code in SIGNALS if code in expected_reasons]
        if set(expected_reasons) != set(item["expectedReasonCodes"]):
            raise DriftError(f"matrix case {case_id} has an unknown expected reason")
        matches = (
            recommendation["outcome"] == expected_outcome
            and recommendation["reasonCodes"] == expected_reasons
        )
        output_cases.append({
            "caseId": case_id,
            "expectedOutcome": expected_outcome,
            "actualOutcome": recommendation["outcome"],
            "expectedReasonCodes": expected_reasons,
            "actualReasonCodes": recommendation["reasonCodes"],
            "matchesExpected": matches,
            "falsePositiveNotes": bounded_note(item["falsePositiveNotes"], "falsePositiveNotes"),
            "falseNegativeNotes": bounded_note(item["falseNegativeNotes"], "falseNegativeNotes"),
            "unsupportedObservabilityNotes": bounded_note(item["unsupportedObservabilityNotes"], "unsupportedObservabilityNotes"),
        })
    output_cases.sort(key=lambda item: item["caseId"])
    if len({item["caseId"] for item in output_cases}) != len(output_cases):
        raise DriftError("matrixInput contains duplicate case IDs")
    matched = sum(item["matchesExpected"] for item in output_cases)
    return {
        "schemaVersion": MATRIX_SCHEMA,
        "phase": "TG04",
        "mode": "SHADOW",
        "cases": output_cases,
        "summary": {
            "caseCount": len(output_cases),
            "matchedCount": matched,
            "mismatchCount": len(output_cases) - matched,
            "providerCalls": 0,
            "networkCalls": 0,
        },
    }


def command_analyze(args: argparse.Namespace) -> None:
    mission = load_json(Path(args.mission))
    ledger = load_json(Path(args.ledger))
    try:
        events = STATE.read_events(Path(args.events))
    except STATE.StateError as error:
        raise DriftError(str(error)) from error
    recommendation = analyze(
        mission, ledger, events, load_json(Path(args.config)), load_json(Path(args.observation))
    )
    STATE.atomic_write(Path(args.output), recommendation)


def command_validate(args: argparse.Namespace) -> None:
    mission = load_json(Path(args.mission))
    ledger = load_json(Path(args.ledger))
    try:
        events = STATE.read_events(Path(args.events))
    except STATE.StateError as error:
        raise DriftError(str(error)) from error
    actual = load_json(Path(args.recommendation))
    validate_recommendation(actual)
    expected = analyze(
        mission, ledger, events, load_json(Path(args.config)), load_json(Path(args.observation))
    )
    if canonical_bytes(actual) != canonical_bytes(expected):
        raise DriftError("recommendation is not deterministically derivable from supplied host state")


def command_matrix(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest)
    matrix = build_matrix(load_json(manifest_path), manifest_path.parent)
    STATE.atomic_write(Path(args.output), matrix)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    analyze_parser = commands.add_parser("analyze")
    analyze_parser.add_argument("mission")
    analyze_parser.add_argument("ledger")
    analyze_parser.add_argument("events")
    analyze_parser.add_argument("config")
    analyze_parser.add_argument("observation")
    analyze_parser.add_argument("output")
    analyze_parser.set_defaults(function=command_analyze)
    validate_parser = commands.add_parser("validate-recommendation")
    validate_parser.add_argument("mission")
    validate_parser.add_argument("ledger")
    validate_parser.add_argument("events")
    validate_parser.add_argument("config")
    validate_parser.add_argument("observation")
    validate_parser.add_argument("recommendation")
    validate_parser.set_defaults(function=command_validate)
    matrix_parser = commands.add_parser("build-matrix")
    matrix_parser.add_argument("manifest")
    matrix_parser.add_argument("output")
    matrix_parser.set_defaults(function=command_matrix)
    args = parser.parse_args()
    try:
        args.function(args)
    except (DriftError, STATE.StateError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
