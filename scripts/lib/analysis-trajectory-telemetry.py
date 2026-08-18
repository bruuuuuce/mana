#!/usr/bin/env python3
"""Versioned, privacy-preserving passive Analysis Trajectory telemetry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

EVENT_SCHEMA = "mana.analysis-trajectory.event/v1"
SUMMARY_SCHEMA = "mana.analysis-trajectory.run-summary/v1"
REF = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")
EVENT_TYPES = {
    "analysis_started", "analysis_completed", "analysis_stopped",
    "provider_iteration_started", "provider_iteration_completed",
    "compact_context_synthesis_started", "compact_context_synthesis_completed",
    "evidence_added", "evidence_gap_opened", "evidence_gap_closed",
    "search_scope_entered", "search_scope_exited", "search_scope_changed",
    "scope_expansion_proposed", "open_decision_observed", "hypothesis_rejected",
    "target_revisited", "no_new_evidence_observed", "analysis_failed",
}


def compact_ref(value: str) -> str:
    if not REF.fullmatch(value):
        raise ValueError("telemetry references must be bounded sanitized identifiers")
    return value


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid telemetry JSON at line {number}: {error}") from error
        if not isinstance(event, dict):
            raise ValueError(f"telemetry event at line {number} is not an object")
        events.append(event)
    return events


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)


def init(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    run_seed = f"{args.story_ref}\n{workspace.name}\n{args.scope_version}".encode()
    run_id = "trajectory-" + hashlib.sha256(run_seed).hexdigest()[:20]
    output = workspace / "evidence" / "analysis-trajectory-events-v1.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError(f"telemetry output already exists: {output}")
    output.touch()
    print(run_id)
    return 0


def emit(args: argparse.Namespace) -> int:
    output = Path(args.events)
    events = read_events(output)
    append_event(events, args, output)
    return 0


def append_event(events: list[dict], args: argparse.Namespace, output: Path) -> None:
    event_type = args.event_type
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported telemetry event type: {event_type}")
    for value in (args.run_id, args.boundary, args.action_kind, args.provider, args.model, args.effort, args.target_scope_ref, args.outcome):
        compact_ref(value)
    refs = {
        "acceptanceCriterionRefs": args.acceptance_criterion_refs,
        "evidenceGapRefs": args.evidence_gap_refs,
        "decisionRefs": args.decision_refs,
        "evidenceAddedRefs": args.evidence_added_refs,
        "reasonCodes": args.reason_codes,
    }
    for values in refs.values():
        for value in values:
            compact_ref(value)
    sequence = len(events) + 1
    event = {
        "schemaVersion": EVENT_SCHEMA,
        "eventId": f"{args.run_id}-{sequence:06d}",
        "runId": args.run_id,
        "sequence": sequence,
        "emittedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "eventType": event_type,
        "boundary": args.boundary,
        "actionKind": args.action_kind,
        "provider": args.provider,
        "model": args.model,
        "effort": args.effort,
        "targetScopeRef": args.target_scope_ref,
        "acceptanceCriterionRefs": args.acceptance_criterion_refs,
        "evidenceGapRefs": args.evidence_gap_refs,
        "decisionRefs": args.decision_refs,
        "evidenceAddedRefs": args.evidence_added_refs,
        "counters": {},
        "budgetDelta": {},
        "outcome": args.outcome,
        "reasonCodes": args.reason_codes,
    }
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    events.append(event)


def observe_artifact(args: argparse.Namespace) -> int:
    output = Path(args.events)
    events = read_events(output)
    artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    if not isinstance(artifact, dict):
        raise ValueError("observed artifact is not an object")
    if args.phase == "discovery":
        observations = [("evidence_gap_opened", "evidence-gap", item.get("id")) for item in artifact.get("openQuestions", [])]
        observations += [("open_decision_observed", "decision", item.get("id")) for item in artifact.get("decisions", []) if item.get("status") == "open"]
    elif args.phase == "triage":
        observations = [("open_decision_observed", "decision", item.get("id")) for item in artifact.get("decisions", []) if item.get("status") == "open"]
    else:
        raise ValueError(f"unsupported observed artifact phase: {args.phase}")
    for event_type, reference_kind, reference in observations:
        compact_ref(reference)
        child = argparse.Namespace(**vars(args))
        child.event_type = event_type
        child.boundary = "provider_result"
        child.action_kind = args.phase
        child.target_scope_ref = args.target_scope_ref
        child.outcome = "completed"
        child.acceptance_criterion_refs = []
        child.evidence_gap_refs = [reference] if reference_kind == "evidence-gap" else []
        child.decision_refs = [reference] if reference_kind == "decision" else []
        child.evidence_added_refs = []
        child.reason_codes = []
        append_event(events, child, output)
    return 0


def summarize(args: argparse.Namespace) -> int:
    events = read_events(Path(args.events))
    if not events:
        raise ValueError("cannot summarize an empty telemetry trace")
    sequences = [event.get("sequence") for event in events]
    if sequences != list(range(1, len(events) + 1)):
        raise ValueError("telemetry sequence is not monotonic")
    run_ids = {event.get("runId") for event in events}
    if len(run_ids) != 1:
        raise ValueError("telemetry trace has inconsistent run IDs")
    scopes = [event["targetScopeRef"] for event in events if event.get("targetScopeRef") != "none"]
    repetitions = sorted({scope for scope in scopes if scopes.count(scope) > 1})
    provider_events = [event for event in events if event.get("eventType") == "provider_iteration_started"]
    no_evidence, maximum_no_evidence = 0, 0
    evidence_per_iteration = []
    for event in events:
        if event.get("eventType") == "provider_iteration_completed":
            count = len(event.get("evidenceAddedRefs", []))
            evidence_per_iteration.append({"eventId": event["eventId"], "evidenceRefCount": count})
            no_evidence = no_evidence + 1 if count == 0 else 0
            maximum_no_evidence = max(maximum_no_evidence, no_evidence)
    routes = sorted({
        (event.get("provider"), event.get("model"), event.get("effort"))
        for event in provider_events
    })
    terminal = next((event for event in reversed(events) if event["eventType"] in {"analysis_completed", "analysis_failed", "analysis_stopped"}), None)
    summary = {
        "schemaVersion": SUMMARY_SCHEMA,
        "runId": next(iter(run_ids)),
        "eventCount": len(events),
        "providerIterationCount": len(provider_events),
        "visitedScopeRefs": sorted(set(scopes)),
        "repeatedTargetScopeRefs": repetitions,
        "maxConsecutiveIterationsWithoutEvidence": maximum_no_evidence,
        "evidenceAddedPerIteration": evidence_per_iteration,
        "scopeExpansionCount": sum(event.get("eventType") == "scope_expansion_proposed" for event in events),
        "openDecisionObservationCount": sum(event.get("eventType") == "open_decision_observed" for event in events),
        "routes": [{"provider": provider, "model": model, "effort": effort} for provider, model, effort in routes],
        "totalCheckpoints": 0,
        "tokenUsage": {"available": False},
        "runOutcome": terminal.get("outcome") if terminal else "partial",
        "partial": terminal is None,
    }
    write_json(Path(args.output), summary)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init")
    init_parser.add_argument("workspace")
    init_parser.add_argument("story_ref")
    init_parser.add_argument("scope_version")
    emit_parser = commands.add_parser("emit")
    emit_parser.add_argument("events")
    emit_parser.add_argument("run_id")
    emit_parser.add_argument("event_type")
    for name in ("boundary", "action_kind", "provider", "model", "effort", "target_scope_ref", "outcome"):
        emit_parser.add_argument(name)
    for name in ("acceptance_criterion_refs", "evidence_gap_refs", "decision_refs", "evidence_added_refs", "reason_codes"):
        emit_parser.add_argument(f"--{name.replace('_', '-')}", nargs="*", default=[])
    summary_parser = commands.add_parser("summarize")
    summary_parser.add_argument("events")
    summary_parser.add_argument("output")
    observe_parser = commands.add_parser("observe-artifact")
    observe_parser.add_argument("events")
    observe_parser.add_argument("run_id")
    observe_parser.add_argument("phase", choices=("discovery", "triage"))
    observe_parser.add_argument("provider")
    observe_parser.add_argument("model")
    observe_parser.add_argument("effort")
    observe_parser.add_argument("target_scope_ref")
    observe_parser.add_argument("artifact")
    args = parser.parse_args()
    try:
        return {"init": init, "emit": emit, "observe-artifact": observe_artifact, "summarize": summarize}[args.command](args)
    except (OSError, ValueError) as error:
        print(f"ERROR: Analysis Trajectory telemetry: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
