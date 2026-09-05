#!/usr/bin/env python3
"""CTX-06B-R1C/R1D permanent transition-boundary fault-injection matrix."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "lib" / "context-pipeline.py"
SPEC = importlib.util.spec_from_file_location("mana_context_pipeline_r1c", MODULE)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)

FRAMEWORK = ROOT / "tests" / "fixtures" / "context-runtime" / "ctx06a-framework"
PROFILE = "ctx06a-fixture"
WORKSPACE = ".mana/sessions/ctx06a-fixture"
MISSING_EVIDENCE = "E-" + "f" * 64


class InjectedFailure(RuntimeError):
    pass


def canonical_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pipeline.runtime.canonical_bytes(value) + b"\n")


def initialize(project: Path, execution: str) -> None:
    project.mkdir(parents=True, exist_ok=True)
    workspace = project / WORKSPACE
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "manifest.yaml").write_text(
        'workspace_type: "session"\nworkspace_id: "ctx06a-fixture"\n', encoding="utf-8"
    )
    (project / "outside.txt").write_text("outside-sentinel\n", encoding="utf-8")
    args = pipeline.parser().parse_args([
        "initialize", PROFILE, "--framework-root", str(FRAMEWORK),
        "--project-root", str(project), "--execution-id", execution,
        "--provider", "codex", "--workspace", WORKSPACE,
        "--objective", "Exercise permanent transition fault injection.",
        "--target-repository", "mana-fixture", "--target-base", "main",
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
            "reason": "Exercise one R1C fault boundary.",
        },
    }


def authority(execution: str, *, approved: bool = True) -> dict:
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
        "approvalRecords": ([{
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
                "sourceRecordId": "HOST-APR-R1C",
            },
        }] if approved else []),
    }


def transition_args(project: Path, execution: str, command: str):
    return pipeline.parser().parse_args([
        command, execution, "--project-root", str(project),
        "--framework-root", str(FRAMEWORK),
    ])


def accept(project: Path, execution: str, checkpoint_path: Path) -> dict:
    args = pipeline.parser().parse_args([
        "accept-checkpoint", execution, "--project-root", str(project),
        "--framework-root", str(FRAMEWORK), "--checkpoint", str(checkpoint_path),
    ])
    return pipeline.accept_checkpoint(args)


def resume(project: Path, execution: str, authority_path: Path) -> dict:
    args = pipeline.parser().parse_args([
        "resume", execution, "--project-root", str(project),
        "--framework-root", str(FRAMEWORK), "--authority", str(authority_path),
    ])
    return pipeline.resume(args)


def reconcile(project: Path, execution: str) -> dict:
    return pipeline.reconcile(transition_args(project, execution, "reconcile"))


def run_root(project: Path, execution: str) -> Path:
    return project / ".mana/runtime/runs" / execution


def head(project: Path, execution: str) -> dict:
    return json.loads((run_root(project, execution) / "run-state-v1.json").read_text(
        encoding="utf-8"
    ))


def public_bundles(project: Path, execution: str) -> list[Path]:
    return sorted(
        path for path in (run_root(project, execution) / "transitions").iterdir()
        if not path.name.startswith(".")
    )


def private_residues(project: Path, execution: str) -> list[Path]:
    markers = (".tmp", ".stage", ".abort", "quarantine")
    return [
        path for path in run_root(project, execution).rglob("*")
        if (
            (path.name.startswith(".") and path.name != ".transition-head.lock")
            or any(marker in path.name.lower() for marker in markers)
        )
    ]


def assert_single_authority(
    project: Path, execution: str, *, allow_private_residue: bool = False,
) -> dict:
    """Prove HEAD is canonical and its unique committed chain fully replays."""
    args = transition_args(project, execution, "reconcile")
    context = pipeline._load_run_context(args)
    bundles = pipeline._published_bundles(context)
    committed = pipeline._committed_transition_ids(context, bundles, args)
    state = head(project, execution)
    assert state == context.state
    if state["transitionId"] is None:
        assert state["revision"] == 0 and committed == set()
        initial = json.loads((
            run_root(project, execution) / "phases/001-classify/phase-input-v1.json"
        ).read_text(encoding="utf-8"))
        assert initial["phaseId"] == state["currentPhaseId"]
        assert initial["checkpointRef"] is None
    else:
        assert state["transitionId"] in committed
        assert len(committed) == state["revision"]
        current = bundles[state["transitionId"]]
        assert current.state == state
        if state["status"] == "active":
            assert current.phase_input is not None
            assert current.phase_input["phaseId"] == state["currentPhaseId"]
            assert current.phase_input["checkpointRef"] == state["latestCheckpointRef"]
        else:
            assert current.phase_input is None
    assert state["currentAttempt"] == state["attempts"][state["currentPhaseId"]]
    if not allow_private_residue:
        assert private_residues(project, execution) == []
    assert (project / "outside.txt").read_text(encoding="utf-8") == "outside-sentinel\n"
    return state


def must_fail(action, label: str) -> None:
    try:
        action()
    except (InjectedFailure, pipeline.runtime.ContractError, pipeline.runtime.RollbackFailure):
        return
    raise AssertionError(f"fault was accepted: {label}")


def install_stage_fault(stage: str) -> None:
    def fail_at(observed: str) -> None:
        if observed == stage:
            raise InjectedFailure(stage)
    pipeline._TEST_TRANSITION_HOOK = fail_at


def clear_faults() -> None:
    pipeline._TEST_TRANSITION_HOOK = None
    pipeline.runtime._TEST_SYNC_HOOK = None


def new_advance(sandbox: Path, name: str) -> tuple[Path, str, Path]:
    execution = f"execution-r1c-{name}"
    project = sandbox / name
    initialize(project, execution)
    checkpoint_path = sandbox / f"{name}.json"
    canonical_write(checkpoint_path, checkpoint(
        execution, f"C-{name}", "classify", "complete",
        "next-declared-phase", "synthesize",
    ))
    return project, execution, checkpoint_path


def new_blocked(sandbox: Path, name: str) -> tuple[Path, str, Path]:
    execution = f"execution-r1d-{name}"
    project = sandbox / name
    initialize(project, execution)
    advance_path = sandbox / f"{name}-advance.json"
    canonical_write(advance_path, checkpoint(
        execution, f"C-{name}-advance", "classify", "complete",
        "next-declared-phase", "synthesize",
    ))
    accept(project, execution, advance_path)
    blocked_path = sandbox / f"{name}-blocked.json"
    canonical_write(blocked_path, checkpoint(
        execution, f"C-{name}-blocked", "synthesize", "complete", "stop", None,
        approvals=True,
    ))
    result = accept(project, execution, blocked_path)
    assert result["status"] == "blocked"
    authority_path = sandbox / f"{name}-authority.json"
    canonical_write(authority_path, authority(execution))
    assert assert_single_authority(project, execution)["revision"] == 2
    return project, execution, authority_path


def hard_crash_after_head_exchange(
    project: Path, execution: str, operation,
) -> None:
    child = os.fork()
    if child == 0:
        def terminate(stage: str) -> None:
            if stage == "after-exchange-before-cleanup":
                os._exit(91)

        pipeline.runtime._TEST_SYNC_HOOK = terminate
        try:
            operation()
        except BaseException:
            os._exit(92)
        os._exit(93)
    _pid, status = os.waitpid(child, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 91


with tempfile.TemporaryDirectory(prefix="mana-r1c-") as temporary:
    sandbox = Path(temporary).resolve()

    # Before/after checkpoint acceptance and before/after construction of the
    # next phase input, exceptions cannot create a competing authority.
    reducer_stages = (
        "before-checkpoint-acceptance",
        "after-checkpoint-acceptance",
        "before-next-phase-creation",
        "after-next-phase-creation",
    )
    for stage in reducer_stages:
        project, execution, checkpoint_path = new_advance(sandbox, stage)
        initial = head(project, execution)
        install_stage_fault(stage)
        try:
            must_fail(lambda: accept(project, execution, checkpoint_path), stage)
        finally:
            clear_faults()
        assert assert_single_authority(project, execution) == initial
        recovered = accept(project, execution, checkpoint_path)
        assert recovered["revision"] == 1
        assert_single_authority(project, execution)

    # Faults immediately before and after immutable bundle publication cover
    # both sides of the publication boundary. Exact retries publish or CAS the
    # same deterministic candidate and never create another authoritative HEAD.
    for stage, expected_bundles in (
        ("before-bundle-publication", 0),
        ("after-bundle-publication", 1),
    ):
        project, execution, checkpoint_path = new_advance(sandbox, stage)
        install_stage_fault(stage)
        try:
            must_fail(lambda: accept(project, execution, checkpoint_path), stage)
        finally:
            clear_faults()
        assert assert_single_authority(project, execution)["revision"] == 0
        assert len(public_bundles(project, execution)) == expected_bundles
        recovered = accept(project, execution, checkpoint_path)
        assert recovered["revision"] == 1
        assert len(public_bundles(project, execution)) == 1
        assert_single_authority(project, execution)

    # A crash raised from inside the no-replace primitive, after its kernel
    # rename, leaves one complete pending bundle. Reconciliation is sufficient.
    project, execution, checkpoint_path = new_advance(sandbox, "during-bundle")
    original_rename_factory = pipeline.runtime._require_rename_primitives
    delegate = original_rename_factory()

    class CrashAfterBundleRename:
        def noreplace(self, *args: object) -> None:
            delegate.noreplace(*args)
            raise InjectedFailure("during-bundle-publication")

    pipeline.runtime._require_rename_primitives = lambda: CrashAfterBundleRename()
    try:
        must_fail(
            lambda: accept(project, execution, checkpoint_path),
            "during-bundle-publication",
        )
    finally:
        pipeline.runtime._require_rename_primitives = original_rename_factory
    assert assert_single_authority(project, execution)["revision"] == 0
    assert len(public_bundles(project, execution)) == 1
    recovered = reconcile(project, execution)
    assert recovered["reconciled"] and recovered["revision"] == 1
    assert_single_authority(project, execution)

    # Before/during/after HEAD CAS. During-CAS raises after the kernel exchange;
    # the retry discovers that the immutable bundle already owns HEAD.
    for stage in ("before-head-cas", "after-head-cas"):
        project, execution, checkpoint_path = new_advance(sandbox, stage)
        install_stage_fault(stage)
        try:
            must_fail(lambda: accept(project, execution, checkpoint_path), stage)
        finally:
            clear_faults()
        expected_revision = 0 if stage == "before-head-cas" else 1
        assert assert_single_authority(project, execution)["revision"] == expected_revision
        recovered = accept(project, execution, checkpoint_path)
        assert recovered["revision"] == 1
        assert_single_authority(project, execution)

    project, execution, checkpoint_path = new_advance(sandbox, "during-head-cas")
    def fail_after_head_exchange(stage: str) -> None:
        if stage == "after-exchange-before-cleanup":
            raise InjectedFailure("during-head-cas")

    pipeline.runtime._TEST_SYNC_HOOK = fail_after_head_exchange
    try:
        must_fail(lambda: accept(project, execution, checkpoint_path), "during-head-cas")
    finally:
        clear_faults()
    assert assert_single_authority(project, execution)["revision"] == 1
    recovered = accept(project, execution, checkpoint_path)
    assert recovered["duplicate"] and recovered["revision"] == 1
    assert_single_authority(project, execution)

    # Crash recovery itself is retryable: the first reconciliation faults before
    # CAS, the second commits exactly the already-published bundle.
    project, execution, checkpoint_path = new_advance(sandbox, "reconcile-crash")
    install_stage_fault("after-bundle-publication")
    try:
        must_fail(lambda: accept(project, execution, checkpoint_path), "crash-before-reconcile")
    finally:
        clear_faults()
    install_stage_fault("before-head-cas")
    try:
        must_fail(lambda: reconcile(project, execution), "reconciliation-fault")
    finally:
        clear_faults()
    assert assert_single_authority(project, execution)["revision"] == 0
    assert reconcile(project, execution)["reconciled"]
    assert assert_single_authority(project, execution)["revision"] == 1

    # A real process death after the HEAD exchange bypasses Python finally:
    # the new HEAD is authoritative and the private name contains the old
    # displaced HEAD. Reconciliation verifies the committed bundle chain and
    # exact previous-state bytes before deleting that one FD-relative entry.
    project, execution, checkpoint_path = new_advance(sandbox, "post-exchange-crash")
    hard_crash_after_head_exchange(
        project, execution,
        lambda: accept(project, execution, checkpoint_path),
    )
    crashed = assert_single_authority(
        project, execution, allow_private_residue=True
    )
    assert crashed["revision"] == 1 and crashed["currentPhaseId"] == "synthesize"
    residues = private_residues(project, execution)
    assert len(residues) == 1 and residues[0].name.startswith(
        ".run-state-v1.json.tmp."
    )
    reconciled = reconcile(project, execution)
    assert reconciled["reconciled"] and reconciled["revision"] == 1
    assert assert_single_authority(project, execution) == crashed
    post_crash_retry = accept(project, execution, checkpoint_path)
    assert post_crash_retry["duplicate"] and post_crash_retry["revision"] == 1
    assert assert_single_authority(project, execution) == crashed

    # A matching lexical name is never deletion authority. Tampered and
    # ambiguous candidates fail closed and remain present for manual handling.
    project, execution, checkpoint_path = new_advance(sandbox, "mutated-displaced-head")

    def mutate_displaced_head(stage: str) -> None:
        if stage != "after-exchange-before-cleanup":
            return
        candidates = private_residues(project, execution)
        assert len(candidates) == 1
        candidates[0].write_text("tampered-displaced-head\n", encoding="utf-8")
        raise InjectedFailure(stage)

    pipeline.runtime._TEST_SYNC_HOOK = mutate_displaced_head
    try:
        must_fail(
            lambda: accept(project, execution, checkpoint_path),
            "mutated-displaced-head",
        )
    finally:
        clear_faults()
    mutated = private_residues(project, execution)
    assert len(mutated) == 1
    must_fail(lambda: reconcile(project, execution), "mutated-displaced-head-reconcile")
    assert mutated[0].exists()
    mutated[0].unlink()
    assert assert_single_authority(project, execution)["revision"] == 1

    project, execution, checkpoint_path = new_advance(sandbox, "tampered-residue")
    accepted = accept(project, execution, checkpoint_path)
    fake = run_root(project, execution) / ".run-state-v1.json.tmp.0000000000000000"
    fake.write_text("tampered\n", encoding="utf-8")
    must_fail(lambda: reconcile(project, execution), "tampered-head-residue")
    assert fake.exists()
    fake.unlink()
    assert assert_single_authority(project, execution)["transitionId"] == accepted["transitionId"]

    project, execution, checkpoint_path = new_advance(sandbox, "ambiguous-residue")
    hard_crash_after_head_exchange(
        project, execution,
        lambda: accept(project, execution, checkpoint_path),
    )
    original_residue = private_residues(project, execution)[0]
    second_residue = run_root(project, execution) / ".run-state-v1.json.tmp.1111111111111111"
    shutil.copyfile(original_residue, second_residue)
    must_fail(lambda: reconcile(project, execution), "ambiguous-head-residue")
    assert original_residue.exists() and second_residue.exists()
    original_residue.unlink()
    second_residue.unlink()
    assert_single_authority(project, execution)

    # Distinct permanent resume/retry faults cover reducer work and their HEAD
    # CAS. Every successful recovery advances once, preserves attempts, and a
    # subsequent identical request is idempotent.
    project, execution, retry_path = new_advance(sandbox, "retry-reducer-fault")
    retry_value = checkpoint(
        execution, "C-retry-reducer", "classify", "partial",
        "repeat-current-phase", "classify",
    )
    canonical_write(retry_path, retry_value)
    install_stage_fault("after-next-phase-creation")
    try:
        must_fail(lambda: accept(project, execution, retry_path), "retry-reducer-fault")
    finally:
        clear_faults()
    assert assert_single_authority(project, execution)["revision"] == 0
    retry_result = accept(project, execution, retry_path)
    retry_head = assert_single_authority(project, execution)
    assert retry_result["revision"] == 1 and retry_head["currentAttempt"] == 2
    assert accept(project, execution, retry_path)["duplicate"]
    assert assert_single_authority(project, execution) == retry_head

    project, execution, retry_path = new_advance(sandbox, "retry-cas-fault")
    canonical_write(retry_path, checkpoint(
        execution, "C-retry-cas", "classify", "partial",
        "repeat-current-phase", "classify",
    ))
    pipeline.runtime._TEST_SYNC_HOOK = fail_after_head_exchange
    try:
        must_fail(lambda: accept(project, execution, retry_path), "retry-head-cas-fault")
    finally:
        clear_faults()
    retry_cas_head = assert_single_authority(project, execution)
    assert retry_cas_head["revision"] == 1 and retry_cas_head["currentAttempt"] == 2
    assert accept(project, execution, retry_path)["duplicate"]
    assert assert_single_authority(project, execution) == retry_cas_head

    project, execution, authority_path = new_blocked(sandbox, "resume-reducer-fault")
    install_stage_fault("after-checkpoint-acceptance")
    try:
        must_fail(lambda: resume(project, execution, authority_path), "resume-reducer-fault")
    finally:
        clear_faults()
    assert assert_single_authority(project, execution)["status"] == "blocked"
    resume_result = resume(project, execution, authority_path)
    resume_head = assert_single_authority(project, execution)
    assert resume_result["revision"] == 3 and resume_head["status"] == "completed"
    assert resume(project, execution, authority_path)["duplicate"]
    assert assert_single_authority(project, execution) == resume_head

    project, execution, authority_path = new_blocked(sandbox, "resume-cas-fault")
    pipeline.runtime._TEST_SYNC_HOOK = fail_after_head_exchange
    try:
        must_fail(lambda: resume(project, execution, authority_path), "resume-head-cas-fault")
    finally:
        clear_faults()
    resume_cas_head = assert_single_authority(project, execution)
    assert resume_cas_head["revision"] == 3 and resume_cas_head["status"] == "completed"
    assert resume(project, execution, authority_path)["duplicate"]
    assert assert_single_authority(project, execution) == resume_cas_head

    # Durable checkpoint acceptance creates the next phase only inside the one
    # digest-bound bundle; there is no separately authoritative phase directory.
    project, execution, checkpoint_path = new_advance(sandbox, "next-phase")
    result = accept(project, execution, checkpoint_path)
    assert result["phaseInput"].endswith("/phase-input-v1.json")
    assert not (run_root(project, execution) / "phases/002-synthesize").exists()
    assert assert_single_authority(project, execution)["currentPhaseId"] == "synthesize"

    # Prepare a blocked terminal checkpoint, then exercise resume without and
    # with authority, plus identical concurrent resume at the CAS boundary.
    execution = "execution-r1c-concurrent-resume"
    project = sandbox / "concurrent-resume"
    initialize(project, execution)
    advance_path = sandbox / "resume-advance.json"
    canonical_write(advance_path, checkpoint(
        execution, "C-resume-advance", "classify", "complete",
        "next-declared-phase", "synthesize",
    ))
    accept(project, execution, advance_path)
    terminal_path = sandbox / "resume-terminal.json"
    canonical_write(terminal_path, checkpoint(
        execution, "C-resume-terminal", "synthesize", "complete", "stop", None,
        approvals=True,
    ))
    blocked = accept(project, execution, terminal_path)
    assert blocked["status"] == "blocked"
    blocked_head = assert_single_authority(project, execution)
    blocked_args = transition_args(project, execution, "reconcile")
    blocked_context = pipeline._load_run_context(blocked_args)
    blocked_bundles = pipeline._published_bundles(blocked_context)
    blocked_checkpoint = blocked_bundles[blocked_head["transitionId"]].checkpoint
    must_fail(
        lambda: pipeline._reduce_durable_operation(
            blocked_context, "resume", blocked_checkpoint, None, blocked_args
        ),
        "blocked-resume-without-authority",
    )
    assert assert_single_authority(project, execution) == blocked_head
    unapproved_path = sandbox / "authority-unapproved.json"
    canonical_write(unapproved_path, authority(execution, approved=False))
    must_fail(lambda: resume(project, execution, unapproved_path), "blocked-resume-without-authority")
    assert assert_single_authority(project, execution) == blocked_head
    approved_path = sandbox / "authority-approved.json"
    canonical_write(approved_path, authority(execution))
    barrier = threading.Barrier(2)

    def concurrent_fault(stage: str) -> None:
        if stage == "before-head-cas":
            barrier.wait(timeout=10)

    pipeline._TEST_TRANSITION_HOOK = concurrent_fault
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda _index: resume(project, execution, approved_path), range(2)
            ))
    finally:
        clear_faults()
    assert len({item["transitionId"] for item in results}) == 1
    assert all(item["status"] == "completed" for item in results)
    assert assert_single_authority(project, execution)["status"] == "completed"

    # A real retry sequence consumes the declared one retry, then commits one
    # blocked revision without incrementing the attempt. Even valid unrelated
    # authority cannot enlarge that limit or create a competing revision.
    execution = "execution-r1c-retry-limit"
    project = sandbox / "retry-limit"
    initialize(project, execution)
    retry_one_path = sandbox / "retry-one.json"
    canonical_write(retry_one_path, checkpoint(
        execution, "C-retry-one", "classify", "partial",
        "repeat-current-phase", "classify",
    ))
    retried = accept(project, execution, retry_one_path)
    assert retried["status"] == "active"
    assert assert_single_authority(project, execution)["currentAttempt"] == 2
    retry_over_path = sandbox / "retry-over.json"
    canonical_write(retry_over_path, checkpoint(
        execution, "C-retry-over", "classify", "partial",
        "repeat-current-phase", "classify",
    ))
    over_limit = accept(project, execution, retry_over_path)
    assert over_limit["status"] == "blocked"
    over_limit_head = assert_single_authority(project, execution)
    assert over_limit_head["currentAttempt"] == 2
    retry_authority_path = sandbox / "retry-authority.json"
    canonical_write(retry_authority_path, authority(execution))
    must_fail(
        lambda: resume(project, execution, retry_authority_path),
        "authority-overrides-retry-limit",
    )
    assert assert_single_authority(project, execution) == over_limit_head

    # Forged state/history are untrusted candidates. They are rejected without
    # replacing the durable HEAD; restoring the test-only copied history proves
    # that the original chain remains the sole recoverable authority.
    forged_state = copy.deepcopy(head(project, execution))
    forged_state["attempts"]["synthesize"] = 2
    forged_state["currentAttempt"] = 2
    must_fail(
        lambda: pipeline.validate_state(
            forged_state, execution, PROFILE,
            pipeline.load_declaration(FRAMEWORK, PROFILE),
        ),
        "forged-state",
    )
    authoritative_before_forgery = assert_single_authority(project, execution)
    latest = public_bundles(project, execution)[-1]
    forged_dir = latest.parent / ("T-" + "f" * 64)
    shutil.copytree(latest, forged_dir)
    must_fail(
        lambda: pipeline._published_bundles(
            pipeline._load_run_context(transition_args(project, execution, "reconcile"))
        ),
        "forged-history",
    )
    shutil.rmtree(forged_dir)
    assert assert_single_authority(project, execution) == authoritative_before_forgery

    # Pure reducer boundary attacks cannot mutate durable authority: foreign
    # CTX-04/CTX-05 identity, nested unknown evidence, exhausted retry, and an
    # early non-terminal stop all fail closed against the same initial state.
    project, execution, checkpoint_path = new_advance(sandbox, "untrusted-inputs")
    args = transition_args(project, execution, "reconcile")
    context = pipeline._load_run_context(args)
    initial = assert_single_authority(project, execution)
    good_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    def reduce_with(
        value: dict, *, state: dict | None = None,
        context_manifest: dict | None = None,
        evidence_manifest: dict | None = None,
    ):
        return pipeline.reduce_checkpoint_transition(
            initial if state is None else state,
            value,
            declaration=context.declaration,
            envelope=context.envelope,
            context_manifest=(context.context_manifest if context_manifest is None
                              else context_manifest),
            evidence_manifest=evidence_manifest,
            framework_root=FRAMEWORK,
        )

    foreign_ctx04 = copy.deepcopy(context.context_manifest)
    foreign_ctx04["executionId"] = "execution-foreign"
    must_fail(
        lambda: reduce_with(good_checkpoint, context_manifest=foreign_ctx04),
        "foreign-CTX-04-manifest",
    )
    assert assert_single_authority(project, execution) == initial
    foreign_ctx05 = {
        "schemaVersion": "mana.context-runtime.evidence-manifest/v1",
        "executionId": "execution-foreign",
        "workspaceId": "W-ea5772a40315d5747936f15005972dddabedf4869b64d86592e411d6b76a41a7",
        "items": [],
    }
    must_fail(
        lambda: reduce_with(good_checkpoint, evidence_manifest=foreign_ctx05),
        "foreign-CTX-05-evidence-manifest",
    )
    assert assert_single_authority(project, execution) == initial
    nested_unknown = copy.deepcopy(good_checkpoint)
    nested_unknown["verifiedFacts"] = [{
        "id": "F-r1c",
        "subject": {"domain": "repository", "kind": "file", "identifier": "fixture"},
        "claim": "This forged fact cites unknown evidence.",
        "evidenceRefs": [MISSING_EVIDENCE],
    }]
    must_fail(lambda: reduce_with(nested_unknown), "nested-unknown-evidence-ref")
    assert assert_single_authority(project, execution) == initial
    early_stop = copy.deepcopy(good_checkpoint)
    early_stop["nextActionRequest"] = {
        "kind": "stop", "targetId": None, "reason": "Forged early stop."
    }
    must_fail(lambda: reduce_with(early_stop), "early-stop-non-terminal")
    assert assert_single_authority(project, execution) == initial
    forged_retry_state = copy.deepcopy(initial)
    forged_retry_state["attempts"]["classify"] = 3
    forged_retry_state["currentAttempt"] = 3
    must_fail(
        lambda: reduce_with(good_checkpoint, state=forged_retry_state),
        "retry-beyond-limit",
    )
    assert assert_single_authority(project, execution) == initial

print("Context Runtime CTX-06B-R1D permanent transition fault tests passed (zero-token)")
