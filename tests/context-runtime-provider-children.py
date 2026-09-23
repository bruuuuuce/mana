#!/usr/bin/env python3
"""CTX-07C-R3 completed receipt lookup, fabrication, and anti-replay gate."""
from __future__ import annotations

import importlib.util
import json
import shutil
import signal
import stat
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/context-runtime-workers.py"
PROVIDER_FIXTURE = ROOT / "tests/fixtures/context-runtime/ctx07c-managed-child-attestation-fixture.sh"
ATTESTED_RUNNER = ROOT / "tests/run-context-provider-child-test-only.sh"
WORKER_HELPER = ROOT / "tests/context-worker-runtime-test-only.py"
DELEGATION = ROOT / "scripts/mana-context-delegation.sh"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


worker_suite = load("ctx07c_worker_suite", SOURCE)
worker_runtime = load("ctx07c_worker_runtime", ROOT / "scripts/lib/context-worker-runtime.py")
worker_runtime.HOST_FRAMEWORK_ROOT = worker_suite.FRAMEWORK


REQUIRED_CHILD_CAPABILITIES = {
    "freshInvocation", "ephemeralSession", "explicitModelSelection",
    "explicitReasoningEffort", "providerManagedSubagents",
    "managedChildExecutionAttestation", "childContextInheritanceControl",
    "childModelRouting", "childReasoningEffortRouting",
    "recursiveDelegationPrevention", "maximumChildConcurrency",
    "maximumChildDepth", "structuredOutputSchema", "userConfigurationIsolation",
}


def install_attested_fixture(suite) -> None:
    shutil.copy2(PROVIDER_FIXTURE, suite.bin / "claude")
    (suite.bin / "claude").chmod(0o755)


def one_task_plan(suite, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    safe = label.replace("_", "-")
    task = suite.task(
        f"T-{safe}", f"{safe}-owner",
        f"Exercise the bounded CTX-07C-R2 {safe} path.", [],
    )
    plan = suite.bind_plan({
        "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
        "tasks": [task],
    }, label)
    return plan, plan["tasks"][0]


def child_args(suite, plan_name: str, mode: str = "prefer") -> list[str]:
    return [
        *suite.runner_args(plan_name, runner=ATTESTED_RUNNER),
        "--provider-children", mode,
    ]


def lines(path: Path) -> int:
    if not path.exists():
        return 0
    return len(path.read_text(encoding="utf-8").splitlines())


def expect_contract(action: Callable[[], Any], fragment: str) -> None:
    try:
        action()
    except (worker_runtime.runtime.ContractError, worker_runtime.delegation.runtime.ContractError) as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f"expected rejection containing {fragment!r}")


def prepared_for(suite, plan_name: str) -> tuple[dict[str, Any], Path]:
    output = suite.command([
        str(WORKER_HELPER), "prepare-plan", worker_suite.EXECUTION,
        "--project-root", str(suite.project),
        "--plan", str(suite.tmp / f"{plan_name}.json"),
    ])
    value = json.loads(output.stdout)
    return value, suite.write_json(f"{plan_name}-prepared.json", value)


def positive_end_to_end_and_authority() -> None:
    suite = worker_suite.Suite()
    try:
        suite.setup()
        install_attested_fixture(suite)
        plan, task = one_task_plan(suite, "child-positive")
        env, state = suite.scenario_env("ctx07c-positive", CTX07C_SCENARIO="valid")
        first = suite.command(child_args(suite, "child-positive"), env=env)
        merge = json.loads(first.stdout)
        assert merge["mergeStatus"] == "complete"
        assert merge["missingTaskIds"] == []
        result = merge["taskResults"][0]
        provenance = result["executionProvenance"]
        assert provenance["executionTransport"] == "provider-managed-child"
        assert provenance["provider"] == "claude"
        assert provenance["rootInvocationId"] != provenance["childInvocationId"]
        assert provenance["receiptId"].startswith("R-")
        assert provenance["receiptDigest"].startswith("sha256:")
        assert result["resultDigest"] == result["semanticResultDigest"]

        snapshot = json.loads((state / "capability-snapshot.json").read_text())
        assert all(
            snapshot["capabilities"][name]["status"] == "supported"
            for name in REQUIRED_CHILD_CAPABILITIES
        )
        assert lines(state / "provider-root-reached.log") == 1
        assert lines(state / "child-reached.log") == 1
        assert lines(state / "host-worker-reached.log") == 0

        worker_root = suite.worker_root_for(suite.project, task)
        head = json.loads((worker_root / "task-result-head.json").read_text())
        result_path = worker_root / head["artifact"]
        assert json.loads(result_path.read_text()) == result
        invocation = head["invocationId"]
        receipt_path = worker_root / f"attempts/{invocation}/managed-child-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        assert receipt["schemaVersion"] == worker_runtime.MANAGED_CHILD_RECEIPT_SCHEMA
        assert receipt["commitState"] == "committed"
        assert receipt["receiptId"] == provenance["receiptId"]
        assert receipt["receiptDigest"] == provenance["receiptDigest"]
        assert receipt["hostInvocationId"] == invocation
        assert receipt["taskExecutionKey"] == head["taskExecutionKey"]
        assert receipt["executionId"] == task["executionId"]
        assert receipt["executionVersion"] == task["executionVersion"]
        assert receipt["workspaceId"] == task["workspaceId"]
        assert receipt["profileId"] == task["profileId"]
        assert receipt["phaseId"] == task["phaseId"]
        assert receipt["attempt"] == task["attempt"]
        assert receipt["planId"] == task["planId"]
        assert receipt["taskId"] == task["taskId"]
        assert receipt["taskDigest"] == task["taskDigest"]
        assert receipt["terminalStatus"] == "completed"
        assert receipt["orderedEventCount"] == 4
        assert receipt["orderedEventDigest"].startswith("sha256:")
        assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(receipt_path.parent.stat().st_mode) == 0o700
        assert not {
            "prompt", "reasoning", "source", "credential", "payload", "events"
        }.intersection(receipt)

        binding_path = suite.project / worker_runtime._managed_child_binding_relative(
            receipt["receiptDigest"]
        )
        binding = json.loads(binding_path.read_text())
        assert binding["receiptDigest"] == receipt["receiptDigest"]
        assert binding["taskExecutionKey"] == head["taskExecutionKey"]
        assert binding["semanticResultDigest"] == result["semanticResultDigest"]
        assert binding["authoritativeResultHead"] == head
        assert stat.S_IMODE(binding_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(binding_path.parent.stat().st_mode) == 0o700

        second = suite.command(child_args(suite, "child-positive"), env=env)
        assert json.loads(second.stdout) == merge
        assert lines(state / "provider-root-reached.log") == 1
        assert lines(state / "child-reached.log") == 1
        assert lines(state / "host-worker-reached.log") == 0

        prepared, prepared_path = prepared_for(suite, "child-positive")
        task_path = suite.write_json("child-positive-task.json", task)
        draft = {
            "schemaVersion": "mana.context-runtime.delegation-result-draft/v1",
            "taskId": task["taskId"], "status": "complete",
            "verifiedFacts": [], "findings": [], "assumptions": [],
            "inferences": [], "openQuestions": [], "evidenceGaps": [],
            "artifactRefs": [],
            "uncertainty": {"level": "none", "description": None, "evidenceRefs": []},
        }
        draft_path = suite.write_json("child-positive-draft.json", draft)
        host = json.loads(suite.command([
            str(DELEGATION), "bind-result", *suite.common(),
            "--plan", str(suite.tmp / "child-positive.json"),
            "--draft", str(draft_path),
        ]).stdout)
        assert host["semanticResultDigest"] == result["semanticResultDigest"]
        assert host["executionReceiptDigest"] != result["executionReceiptDigest"]
        assert host["executionProvenance"]["executionTransport"] == "host-worker"
        assert host["executionProvenance"]["receiptId"] is None
        assert host["executionProvenance"]["receiptDigest"] is None

        host_path = suite.write_json("child-positive-host-result.json", host)
        host_merge = json.loads(suite.command([
            str(DELEGATION), "merge-results", *suite.common(),
            "--plan", str(suite.tmp / "child-positive.json"),
            "--result", str(host_path),
        ]).stdout)
        assert host_merge["mergeStatus"] == "complete"
        child_path = suite.write_json("child-positive-child-result.json", result)
        rejected_merge = suite.command([
            str(DELEGATION), "merge-results", *suite.common(),
            "--plan", str(suite.tmp / "child-positive.json"),
            "--result", str(child_path),
        ], ok=False)
        assert "no committed host receipt authority" in rejected_merge.stderr

        # Exact authoritative publication is idempotent.
        exact = worker_runtime.publish_task(
            str(suite.project), head["taskExecutionKey"], invocation,
            str(result_path), str(prepared_path), str(task_path),
        )
        assert exact["action"] == "reused"

        # The global receipt binding rejects the same provider receipt with a
        # different semantic result and cannot name a second result HEAD.
        changed_draft = deepcopy(draft)
        changed_draft["status"] = "partial"
        different = worker_runtime.delegation.bind_result(
            changed_draft, prepared["authorityPacket"], prepared["plan"], task,
            prepared.get("evidenceManifest"),
            managed_child_project_root=suite.project,
            managed_child_invocation_id=invocation,
        )
        different_head = {
            **head,
            "resultDigest": different["resultDigest"],
            "artifactDigest": worker_runtime.digest_bytes(
                worker_runtime.runtime.canonical_bytes(different)
            ),
        }
        expect_contract(
            lambda: worker_runtime._commit_managed_child_binding(
                suite.project, head["taskExecutionKey"], invocation,
                receipt, different, different_head,
            ),
            "replay conflicts",
        )
        different_path = suite.write_json("child-positive-different-result.json", different)
        expect_contract(
            lambda: worker_runtime.publish_task(
                str(suite.project), head["taskExecutionKey"], invocation,
                str(different_path), str(prepared_path), str(task_path),
            ),
            "conflicting authoritative worker result",
        )

        # Reuse revalidates both the immutable receipt and the global binding.
        saved_receipt = receipt_path.read_bytes()
        for field, value, error_fragment in (
            ("commitState", "pending", "not committed"),
            ("receiptDigest", "sha256:" + "0" * 64, "digest"),
            ("hostInvocationId", "I-foreign", "host invocation"),
        ):
            tampered = deepcopy(receipt)
            tampered[field] = value
            receipt_path.write_bytes(
                worker_runtime.runtime.canonical_bytes(tampered) + b"\n"
            )
            try:
                failed = suite.command(
                    child_args(suite, "child-positive"), env=env, ok=False
                )
                assert error_fragment in failed.stderr, failed.stderr
            finally:
                receipt_path.write_bytes(saved_receipt)
        saved_binding = binding_path.read_bytes()
        binding_path.rename(binding_path.with_suffix(".absent"))
        try:
            failed = suite.command(child_args(suite, "child-positive"), env=env, ok=False)
            assert "binding" in failed.stderr
        finally:
            binding_path.with_suffix(".absent").rename(binding_path)
            assert binding_path.read_bytes() == saved_binding
    finally:
        suite.cleanup()


def provenance_fabrication_is_rejected() -> None:
    suite = worker_suite.Suite()
    try:
        suite.setup()
        plan, task = one_task_plan(suite, "fabrication")
        draft = {
            "schemaVersion": "mana.context-runtime.delegation-result-draft/v1",
            "taskId": task["taskId"], "status": "complete",
            "verifiedFacts": [], "findings": [], "assumptions": [],
            "inferences": [], "openQuestions": [], "evidenceGaps": [],
            "artifactRefs": [],
            "uncertainty": {"level": "none", "description": None, "evidenceRefs": []},
        }
        for field in (
            "executionTransport", "rootInvocationId", "childInvocationId",
            "attestationKind", "receiptId", "receiptDigest", "executionReceiptDigest",
        ):
            forged = deepcopy(draft)
            forged[field] = "forged"
            path = suite.write_json(f"forged-{field}.json", forged)
            rejected = suite.command([
                str(DELEGATION), "bind-result", *suite.common(),
                "--plan", str(suite.tmp / "fabrication.json"),
                "--draft", str(path),
            ], ok=False)
            assert rejected.stdout == ""
        clean = suite.write_json("fabrication-clean.json", draft)
        rejected = suite.command([
            str(DELEGATION), "bind-result", *suite.common(),
            "--plan", str(suite.tmp / "fabrication.json"),
            "--draft", str(clean),
            "--execution-transport", "provider-managed-child",
            "--root-invocation-id", "root-forged",
            "--child-invocation-id", "child-forged",
        ], ok=False)
        assert "unrecognized arguments" in rejected.stderr
        assert plan["tasks"][0] == task
    finally:
        suite.cleanup()


def assert_failed_attempt(
    suite, task: dict[str, Any], state: Path, *,
    terminal: str, child_count: int, receipt_expected: bool,
) -> None:
    assert lines(state / "provider-root-reached.log") == 1
    assert lines(state / "child-reached.log") == child_count
    assert lines(state / "host-worker-reached.log") == 0
    worker_root = suite.worker_root_for(suite.project, task)
    assert not (worker_root / "task-result-head.json").exists()
    claim = json.loads((worker_root / "claim.json").read_text())
    assert claim["status"] == "terminal"
    assert claim["terminalStatus"] == terminal
    metrics = list((worker_root / "metrics").glob("I-*.json"))
    assert len(metrics) == 1
    metric = json.loads(metrics[0].read_text())
    assert metric["status"] == terminal
    events = [json.loads(path.read_text()) for path in (worker_root / "events").glob("*.json")]
    event_name = {
        "failed": "worker.failed",
        "timed_out": "worker.timed_out",
        "interrupted": "worker.interrupted",
    }[terminal]
    assert sum(event["eventType"] == event_name for event in events) == 1
    receipts = list(worker_root.glob("attempts/*/managed-child-receipt.json"))
    assert bool(receipts) is receipt_expected
    assert not list(
        suite.project.glob(".mana/runtime/managed-child-result-bindings/*.json")
    )


def negative_end_to_end_matrix() -> None:
    cases = [
        ("root-direct", 0, False),
        ("completed-before-started", 1, False),
        ("completion-without-start", 1, False),
        ("duplicate-start", 1, False),
        ("duplicate-terminal", 1, False),
        ("same-root-child", 1, False),
        ("task-digest-mismatch", 1, False),
        ("foreign", 1, False),
        ("stale", 1, False),
        ("receipt-missing", 1, False),
        ("sequence-gap", 1, False),
        ("event-after-terminal", 1, False),
        ("semantic-invalid", 1, True),
        ("child-failed", 1, True),
        ("child-nonzero", 1, False),
    ]
    suite = worker_suite.Suite()
    try:
        suite.setup()
        install_attested_fixture(suite)
        for index, (scenario, child_count, receipt_expected) in enumerate(cases):
            label = f"negative-{index}-{scenario}"
            _plan, task = one_task_plan(suite, label)
            env, state = suite.scenario_env(
                f"ctx07c-{label}", CTX07C_SCENARIO=scenario
            )
            result = suite.command(child_args(suite, label), env=env, ok=False)
            if result.stdout:
                assert json.loads(result.stdout)["mergeStatus"] == "incomplete"
            assert_failed_attempt(
                suite, task, state, terminal="failed",
                child_count=child_count, receipt_expected=receipt_expected,
            )

        _plan, timeout_task = one_task_plan(suite, "negative-timeout")
        timeout_env, timeout_state = suite.scenario_env(
            "ctx07c-negative-timeout", CTX07C_SCENARIO="timeout"
        )
        timed_out = suite.command(
            child_args(suite, "negative-timeout"), env=timeout_env, ok=False
        )
        assert timed_out.returncode == 124
        assert_failed_attempt(
            suite, timeout_task, timeout_state, terminal="timed_out",
            child_count=0, receipt_expected=False,
        )

        _plan, interrupted_task = one_task_plan(suite, "negative-interruption")
        interrupted_env, interrupted_state = suite.scenario_env(
            "ctx07c-negative-interruption", CTX07C_SCENARIO="interruption"
        )
        process = subprocess.Popen(
            child_args(suite, "negative-interruption"), cwd=ROOT,
            env=interrupted_env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 10
        while not (interrupted_state / "provider-root-reached.log").exists():
            if process.poll() is not None:
                raise AssertionError("interruption fixture exited before provider root reach")
            if time.monotonic() >= deadline:
                process.kill()
                raise AssertionError("interruption fixture did not reach provider root")
            time.sleep(0.02)
        process.send_signal(signal.SIGTERM)
        _stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 143, stderr
        assert_failed_attempt(
            suite, interrupted_task, interrupted_state, terminal="interrupted",
            child_count=0, receipt_expected=False,
        )
    finally:
        suite.cleanup()


def production_providers_remain_unknown_and_fallback() -> None:
    fixtures = {
        "claude": ROOT / "tests/fixtures/context-runtime/provider-capabilities/claude-child-supported",
        "codex": ROOT / "tests/fixtures/context-runtime/provider-capabilities/codex-supported",
        "opencode": ROOT / "tests/fixtures/context-runtime/provider-capabilities/opencode-supported",
    }
    for provider, fixture in fixtures.items():
        result = subprocess.run(
            [str(ROOT / "scripts/mana-provider-capabilities.sh"), provider,
             "--fixture", str(fixture)],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=True,
        )
        report = json.loads(result.stdout)
        assert report["capabilities"]["managedChildExecutionAttestation"]["status"] == "unknown"

    suite = worker_suite.Suite()
    try:
        suite.setup()
        env, state = suite.scenario_env(
            "ctx07c-production-prefer", CTX07B_CAPABILITY_SET="claude-supported"
        )
        result = suite.command([
            *suite.runner_args(), "--provider-children", "prefer"
        ], env=env)
        assert json.loads(result.stdout)["mergeStatus"] == "complete"
        assert "managedChildExecutionAttestation:unknown" in result.stderr
        assert all(
            (state / f"transport.{task_id}").read_text().strip() == "host"
            for task_id in ("T-economy", "T-full")
        )
        assert not list(state.glob("child-controls.*"))

        require_env, require_state = suite.scenario_env(
            "ctx07c-production-require", CTX07B_CAPABILITY_SET="claude-supported"
        )
        rejected = suite.command([
            *suite.runner_args(), "--provider-children", "require"
        ], env=require_env, ok=False)
        assert "needs_model_escalation" in rejected.stderr
        assert not require_state.exists()
    finally:
        suite.cleanup()


def shell_and_compile_regressions() -> None:
    compile_result = subprocess.run(
        [sys.executable, "-m", "py_compile",
         str(ROOT / "scripts/lib/context-delegation.py"),
         str(ROOT / "scripts/lib/context-worker-runtime.py"),
         str(ROOT / "scripts/lib/context-runtime.py"),
         str(ROOT / "tests/context-runtime-managed-child-authority.py"),
         str(ROOT / "tests/context-runtime-provider-children.py")],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    shell_files = [
        ROOT / "scripts/run-context-workers.sh",
        ROOT / "scripts/lib/context-worker-transport.sh",
        ROOT / "tests/run-context-provider-child-test-only.sh",
        PROVIDER_FIXTURE,
        ROOT / "tests/fixtures/context-runtime/ctx07c-managed-child-adapter-test-only.sh",
    ]
    syntax = subprocess.run(
        ["bash", "-n", *map(str, shell_files)], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert syntax.returncode == 0, syntax.stderr
    checked = subprocess.run(
        ["shellcheck", "-x", *map(str, shell_files)], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr


def main() -> int:
    authority_gate = subprocess.run(
        [sys.executable, str(ROOT / "tests/context-runtime-managed-child-authority.py")],
        cwd=ROOT, check=False,
    )
    assert authority_gate.returncode == 0, "CTX-07C-R3 direct Python authority gate failed"
    positive_end_to_end_and_authority()
    provenance_fabrication_is_rejected()
    negative_end_to_end_matrix()
    production_providers_remain_unknown_and_fallback()
    shell_and_compile_regressions()
    print(
        "CTX-07C-R3 provider-child regressions passed: completed receipt lookup, "
        "non-forgeable authority, anti-replay, end-to-end transport"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
