#!/usr/bin/env python3
"""CTX-06B-R1B immutable transition publication and concurrency regressions."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "lib" / "context-pipeline.py"
SPEC = importlib.util.spec_from_file_location("mana_context_pipeline_r1b", MODULE)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)

FRAMEWORK = ROOT / "tests" / "fixtures" / "context-runtime" / "ctx06a-framework"
PROFILE = "ctx06a-fixture"
WORKSPACE = ".mana/sessions/ctx06a-fixture"


def canonical_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pipeline.runtime.canonical_bytes(value) + b"\n")


def must_reject(action, invariant: str) -> None:
    try:
        action()
    except (pipeline.runtime.ContractError, pipeline.runtime.RollbackFailure):
        return
    raise AssertionError(f"expected rejection: {invariant}")


def base_args(project: Path, execution: str) -> list[str]:
    return [
        "--project-root", str(project), "--framework-root", str(FRAMEWORK),
        execution,
    ]


def initialize(project: Path, execution: str) -> None:
    project.mkdir(parents=True, exist_ok=True)
    workspace = project / WORKSPACE
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "manifest.yaml").write_text(
        'workspace_type: "session"\nworkspace_id: "ctx06a-fixture"\n', encoding="utf-8"
    )
    args = pipeline.parser().parse_args([
        "initialize", PROFILE,
        "--framework-root", str(FRAMEWORK),
        "--project-root", str(project),
        "--execution-id", execution,
        "--provider", "codex",
        "--workspace", WORKSPACE,
        "--objective", "Exercise durable Context Runtime transitions.",
        "--target-repository", "mana-fixture",
        "--target-base", "main",
        "--target-pr-number", "17",
    ])
    pipeline.initialize(args)


def checkpoint(
    execution: str, checkpoint_id: str, phase: str, status: str,
    action: str, target: str | None, *, approvals: bool = False,
) -> dict:
    return {
        "schemaVersion": "mana.context-runtime.phase-checkpoint/v1",
        "checkpointId": checkpoint_id,
        "executionId": execution,
        "executionVersion": 1,
        "profileId": PROFILE,
        "phaseId": phase,
        "status": status,
        "verifiedFacts": [],
        "assumptions": [],
        "inferences": [],
        "openQuestions": [],
        "closedHypotheses": [],
        "candidateFindings": [],
        "approvalRequests": (
            [{"approvalId": "APR-owner", "gateId": "GATE-owner-approval"}]
            if approvals else []
        ),
        "activatedSkills": ["ctx06a-fixture-skill"],
        "evidenceRefs": [],
        "nextActionRequest": {
            "kind": action,
            "targetId": target,
            "reason": "Exercise one durable transition.",
        },
    }


def authority(execution: str, source_record: str = "HOST-APR-R1B") -> dict:
    return {
        "schemaVersion": "mana.context-runtime.host-authority-context/v1",
        "executionIdentity": {
            "executionId": execution,
            "executionVersion": 1,
            "profileId": PROFILE,
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
        "approvalRecords": [{
            "approvalId": "APR-owner",
            "recordVersion": 1,
            "executionId": execution,
            "executionVersion": 1,
            "gateId": "GATE-owner-approval",
            "decision": "approved",
            "completedAt": "2026-09-02T00:01:00Z",
            "provenance": {
                "source": "human",
                "actorId": "human-owner",
                "recordedBy": "host:mana-runtime",
                "sourceRecordId": source_record,
            },
        }],
    }


def accept(project: Path, execution: str, checkpoint_path: Path) -> dict:
    args = pipeline.parser().parse_args([
        "accept-checkpoint", execution,
        "--project-root", str(project),
        "--framework-root", str(FRAMEWORK),
        "--checkpoint", str(checkpoint_path),
    ])
    return pipeline.accept_checkpoint(args)


def resume(project: Path, execution: str, authority_path: Path) -> dict:
    args = pipeline.parser().parse_args([
        "resume", execution,
        "--project-root", str(project),
        "--framework-root", str(FRAMEWORK),
        "--authority", str(authority_path),
    ])
    return pipeline.resume(args)


def reconcile(project: Path, execution: str) -> dict:
    args = pipeline.parser().parse_args([
        "reconcile", execution,
        "--project-root", str(project),
        "--framework-root", str(FRAMEWORK),
    ])
    return pipeline.reconcile(args)


def head(project: Path, execution: str) -> dict:
    return json.loads((
        project / ".mana/runtime/runs" / execution / "run-state-v1.json"
    ).read_text(encoding="utf-8"))


def public_bundles(project: Path, execution: str) -> list[Path]:
    root = project / ".mana/runtime/runs" / execution / "transitions"
    return sorted(path for path in root.iterdir() if not path.name.startswith("."))


with tempfile.TemporaryDirectory(prefix="mana-r1b-") as temporary:
    sandbox = Path(temporary).resolve()

    # One immutable bundle is published before the sole mutable HEAD is CASed.
    execution = "execution-r1b-normal"
    project = sandbox / "normal"
    initialize(project, execution)
    lock_path = project / ".mana/runtime/runs" / execution / ".transition-head.lock"
    assert lock_path.is_file() and (lock_path.stat().st_mode & 0o777) == 0o600
    advance_path = sandbox / "advance.json"
    canonical_write(advance_path, checkpoint(
        execution, "C-advance", "classify", "complete",
        "next-declared-phase", "synthesize",
    ))
    first = accept(project, execution, advance_path)
    state = head(project, execution)
    assert state["revision"] == 1 and state["transitionId"] == first["transitionId"]
    assert state["previousStateDigest"].startswith("sha256-")
    bundles = public_bundles(project, execution)
    assert len(bundles) == 1 and bundles[0].name == state["transitionId"]
    assert (bundles[0] / "checkpoint-v1.json").is_file()
    assert (bundles[0] / "run-state-v1.json").is_file()
    assert (bundles[0] / "phase-input-v1.json").is_file()
    assert not (project / ".mana/runtime/runs" / execution / "phases/002-synthesize").exists()
    manifest = json.loads((bundles[0] / "transition-v1.json").read_text(encoding="utf-8"))
    assert manifest["nextStateDigest"] == pipeline._digest_value(state)
    assert manifest["previousTransitionId"] is None
    assert first["phaseInput"].endswith("/phase-input-v1.json")

    # Exact retry is idempotent; same checkpoint ID with changed bytes conflicts.
    duplicate = accept(project, execution, advance_path)
    assert duplicate["transitionId"] == first["transitionId"] and duplicate["duplicate"]
    assert len(public_bundles(project, execution)) == 1
    conflicting = copy.deepcopy(json.loads(advance_path.read_text(encoding="utf-8")))
    conflicting["nextActionRequest"]["reason"] = "Different durable operation bytes."
    conflict_path = sandbox / "conflict.json"
    canonical_write(conflict_path, conflicting)
    must_reject(
        lambda: accept(project, execution, conflict_path),
        "conflicting duplicate checkpoint ID",
    )

    # A failure after immutable publication but before HEAD CAS leaves no
    # authoritative checkpoint/input; explicit reconciliation commits it once.
    execution = "execution-r1b-reconcile"
    project = sandbox / "reconcile"
    initialize(project, execution)
    pending_path = sandbox / "pending.json"
    canonical_write(pending_path, checkpoint(
        execution, "C-pending", "classify", "complete",
        "next-declared-phase", "synthesize",
    ))

    class InjectedFailure(RuntimeError):
        pass

    def fail_after_bundle(stage: str) -> None:
        if stage == "after-bundle-publication":
            raise InjectedFailure("stop between bundle publication and HEAD CAS")

    pipeline._TEST_TRANSITION_HOOK = fail_after_bundle
    try:
        try:
            accept(project, execution, pending_path)
        except InjectedFailure:
            pass
        else:
            raise AssertionError("injected post-bundle failure was not observed")
    finally:
        pipeline._TEST_TRANSITION_HOOK = None
    assert head(project, execution)["revision"] == 0
    pending_bundles = public_bundles(project, execution)
    assert len(pending_bundles) == 1
    pending_manifest = json.loads((
        pending_bundles[0] / "transition-v1.json"
    ).read_text(encoding="utf-8"))
    assert head(project, execution)["transitionId"] is None
    recovered = reconcile(project, execution)
    assert recovered["reconciled"] and recovered["duplicate"]
    assert head(project, execution)["transitionId"] == pending_manifest["transitionId"]
    again = reconcile(project, execution)
    assert again["revision"] == 1 and not again["reconciled"]

    # Two unrelated checkpoint publications from one previous HEAD are
    # linearized by the single CAS. The losing bundle never becomes authority.
    execution = "execution-r1b-race"
    project = sandbox / "race"
    initialize(project, execution)
    race_paths = []
    for suffix in ("a", "b"):
        path = sandbox / f"race-{suffix}.json"
        canonical_write(path, checkpoint(
            execution, f"C-race-{suffix}", "classify", "complete",
            "next-declared-phase", "synthesize",
        ))
        race_paths.append(path)
    barrier = threading.Barrier(2)

    def stop_at_cas(stage: str) -> None:
        if stage == "before-head-cas":
            barrier.wait(timeout=10)

    def race_accept(path: Path):
        try:
            return ("ok", accept(project, execution, path))
        except pipeline.runtime.ContractError as error:
            return ("rejected", str(error))

    pipeline._TEST_TRANSITION_HOOK = stop_at_cas
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(race_accept, race_paths))
    finally:
        pipeline._TEST_TRANSITION_HOOK = None
    assert sorted(outcome[0] for outcome in outcomes) == ["ok", "rejected"]
    race_head = head(project, execution)
    assert race_head["revision"] == 1
    assert len(public_bundles(project, execution)) == 2
    assert sum(path.name == race_head["transitionId"] for path in public_bundles(project, execution)) == 1
    current_bundle = next(path for path in public_bundles(project, execution)
                          if path.name == race_head["transitionId"])
    current_input = json.loads((current_bundle / "phase-input-v1.json").read_text(encoding="utf-8"))
    assert current_input["checkpointRef"] == race_head["latestCheckpointRef"]

    # Conflicting concurrent duplicates may both publish immutable candidates,
    # but only the CAS winner is committed. Retrying that exact winner remains
    # idempotent even in the presence of the stale conflicting bundle.
    execution = "execution-r1b-conflicting-race"
    project = sandbox / "conflicting-race"
    initialize(project, execution)
    conflict_paths = []
    for suffix in ("a", "b"):
        value = checkpoint(
            execution, "C-same-id", "classify", "complete",
            "next-declared-phase", "synthesize",
        )
        value["nextActionRequest"]["reason"] = f"Conflicting operation {suffix}."
        path = sandbox / f"same-id-{suffix}.json"
        canonical_write(path, value)
        conflict_paths.append(path)
    barrier = threading.Barrier(2)
    pipeline._TEST_TRANSITION_HOOK = stop_at_cas
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            conflict_outcomes = list(executor.map(race_accept, conflict_paths))
    finally:
        pipeline._TEST_TRANSITION_HOOK = None
    assert sorted(outcome[0] for outcome in conflict_outcomes) == ["ok", "rejected"]
    conflict_head = head(project, execution)
    committed_checkpoint = json.loads((
        project / ".mana/runtime/runs" / execution / "transitions" /
        conflict_head["transitionId"] / "checkpoint-v1.json"
    ).read_text(encoding="utf-8"))
    winner_path = next(
        path for path in conflict_paths
        if json.loads(path.read_text(encoding="utf-8")) == committed_checkpoint
    )
    winner_retry = accept(project, execution, winner_path)
    assert winner_retry["duplicate"] and winner_retry["transitionId"] == conflict_head["transitionId"]
    loser_path = next(path for path in conflict_paths if path != winner_path)
    must_reject(
        lambda: accept(project, execution, loser_path),
        "stale conflicting concurrent duplicate",
    )

    # Terminal checkpoint first commits a blocked state. Identical concurrent
    # resumes converge on one deterministic bundle and one HEAD revision.
    execution = "execution-r1b-resume-race"
    project = sandbox / "resume-race"
    initialize(project, execution)
    advance_path = sandbox / "resume-advance.json"
    canonical_write(advance_path, checkpoint(
        execution, "C-resume-advance", "classify", "complete",
        "next-declared-phase", "synthesize",
    ))
    accept(project, execution, advance_path)
    terminal_path = sandbox / "terminal.json"
    canonical_write(terminal_path, checkpoint(
        execution, "C-terminal", "synthesize", "complete", "stop", None,
        approvals=True,
    ))
    blocked = accept(project, execution, terminal_path)
    assert blocked["status"] == "blocked" and blocked["phaseInput"] is None
    authority_path = sandbox / "authority.json"
    canonical_write(authority_path, authority(execution))
    barrier = threading.Barrier(2)
    pipeline._TEST_TRANSITION_HOOK = stop_at_cas
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            resume_results = list(executor.map(
                lambda _index: resume(project, execution, authority_path), range(2)
            ))
    finally:
        pipeline._TEST_TRANSITION_HOOK = None
    assert len({result["transitionId"] for result in resume_results}) == 1
    assert all(result["status"] == "completed" for result in resume_results)
    assert any(result["reconciled"] for result in resume_results)
    completed = head(project, execution)
    assert completed["status"] == "completed" and completed["revision"] == 3
    assert completed["transitionId"] == resume_results[0]["transitionId"]
    resume_retry = resume(project, execution, authority_path)
    assert resume_retry["duplicate"] and resume_retry["transitionId"] == completed["transitionId"]
    conflicting_authority_path = sandbox / "conflicting-authority.json"
    canonical_write(
        conflicting_authority_path, authority(execution, "HOST-APR-R1B-CONFLICT")
    )
    must_reject(
        lambda: resume(project, execution, conflicting_authority_path),
        "conflicting duplicate resume authority",
    )

print("Context Runtime CTX-06B-R1B transition publication tests passed (zero-token)")
