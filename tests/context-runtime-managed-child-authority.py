#!/usr/bin/env python3
"""CTX-07C-R3 direct Python regressions for the two CTX-07G bypasses.

Only local fixtures. In particular, forged results below recompute every
digest and provenance field just as the independent gate's caller did.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ctx07c_authority_fixture", ROOT / "tests/context-runtime-provider-children.py")
assert spec is not None and spec.loader is not None
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
worker = fixture.worker_runtime
delegation = worker.delegation
runtime = delegation.runtime


def sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(runtime.canonical_bytes(value)).hexdigest()


def rejected(action: Callable[[], Any], fragment: str = "") -> None:
    try:
        action()
    except (runtime.ContractError, worker.runtime.ContractError) as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError("Python authority API accepted forged or revoked proof")


class Case:
    def __init__(self, label: str, terminal: str | None) -> None:
        self.suite = fixture.worker_suite.Suite()
        self.suite.setup()
        self.plan, self.task = fixture.one_task_plan(self.suite, label)
        self.prepared, self.prepared_path = fixture.prepared_for(self.suite, label)
        self.task_path = self.suite.write_json(label + "-task.json", self.task)
        self.packet = self.prepared["authorityPacket"]
        self.evidence = self.prepared.get("evidenceManifest")
        self.claim = worker.claim_task(str(self.suite.project), str(self.prepared_path), str(self.task_path))
        assert self.claim["action"] == "claimed"
        self.key = self.claim["taskExecutionKey"]
        self.invocation = self.claim["invocationId"]
        self.root = self.suite.project
        self.base = self.root / worker._execution_relative(self.key)
        self.receipt_path = self.root / worker._managed_child_receipt_relative(self.key, self.invocation)
        self.commit_path = self.receipt_path.with_name("managed-child-receipt-commit.json")
        self.draft = {
            "schemaVersion": "mana.context-runtime.delegation-result-draft/v1",
            "taskId": self.task["taskId"], "status": "complete",
            "verifiedFacts": [], "findings": [], "assumptions": [], "inferences": [],
            "openQuestions": [], "evidenceGaps": [], "artifactRefs": [],
            "uncertainty": {"level": "none", "description": None, "evidenceRefs": []},
        }
        self.draft_path = self.suite.write_json(label + "-draft.json", self.draft)
        self.host_result = delegation.bind_result(self.draft, self.packet, self.plan, self.task, self.evidence)
        self.events = [
            {"sequence": 1, "eventType": "root.started", "rootInvocationId": "native-root",
             **{field: self.task[field] for field in (*delegation.BINDING_FIELDS, "planId")}},
            {"sequence": 2, "eventType": "child.started", "rootInvocationId": "native-root", "childInvocationId": "native-child"},
            {"sequence": 3, "eventType": "child.task.bound", "rootInvocationId": "native-root", "childInvocationId": "native-child",
             "taskId": self.task["taskId"], "taskDigest": self.task["taskDigest"]},
            {"sequence": 4, "eventType": "child." + (terminal or "completed"),
             "rootInvocationId": "native-root", "childInvocationId": "native-child",
             "taskId": self.task["taskId"], "taskDigest": self.task["taskDigest"], "status": terminal or "completed"},
        ]
        self.receipt = None
        if terminal is not None:
            output = self.suite.write_json(label + "-output.json", {
                "structured_output": self.draft,
                "managedChildExecutionAttestation": {
                    "attestationKind": "provider-native-managed-child-event-receipt/v1", "events": self.events,
                },
            })
            published = worker.publish_managed_child_receipt(
                str(self.root), self.key, self.invocation, "claude", str(output), str(self.prepared_path), str(self.task_path)
            )
            self.receipt = published["receiptObject"]
            assert "receiptAuthority" not in published
        provenance = {
            "executionTransport": "provider-managed-child", "provider": "claude",
            "rootInvocationId": "native-root", "childInvocationId": "native-child",
            "attestationKind": "provider-native-managed-child-event-receipt/v1",
            "receiptId": "R-" + "1" * 64, "receiptDigest": "sha256:" + "1" * 64,
        }
        if self.receipt is not None:
            provenance.update({field: self.receipt[field] for field in ("receiptId", "receiptDigest")})
        self.result = self.forged_result(provenance)
        self.result_path = self.suite.write_json(label + "-result.json", self.result)

    def forged_result(self, provenance: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(self.host_result)
        result["executionProvenance"] = deepcopy(provenance)
        # Semantic identity is unchanged by transport/provenance reconstruction.
        assert delegation.result_digest(result) == result["semanticResultDigest"]
        result["executionReceiptDigest"] = sha({
            "identityVersion": "mana.context-runtime.execution-receipt/v2",
            "semanticResultDigest": result["semanticResultDigest"],
            "providerReceiptDigest": provenance["receiptDigest"], "executionProvenance": provenance,
        })
        runtime.validate_model("delegation-result", result)
        return result

    def bind(self):
        return delegation.bind_result(
            self.draft, self.packet, self.plan, self.task, self.evidence,
            managed_child_project_root=self.root, managed_child_invocation_id=self.invocation,
        )

    def publish(self):
        return worker.publish_task(str(self.root), self.key, self.invocation, str(self.result_path), str(self.prepared_path), str(self.task_path))

    def reuse(self):
        return worker.claim_task(str(self.root), str(self.prepared_path), str(self.task_path))

    def merge(self):
        return worker.merge_authoritative_results(str(self.root), str(self.prepared_path))

    def direct_merge(self):
        return delegation.merge(self.plan, [self.result], self.packet, self.evidence, managed_child_project_root=self.root)

    def write_private(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(runtime.canonical_bytes(value) + b"\n")
        path.chmod(0o600)

    def fabricate_head(self) -> None:
        self.head = {
            "schemaVersion": "mana.context-runtime.worker-result-head/v1", "taskExecutionKey": self.key,
            "invocationId": self.invocation, "artifact": f"attempts/{self.invocation}/result.json",
            "resultDigest": self.result["resultDigest"], "artifactDigest": sha(self.result),
        }
        self.write_private(self.base / self.head["artifact"], self.result)
        self.write_private(self.base / "task-result-head.json", self.head)
        p = self.result["executionProvenance"]
        binding = {
            "schemaVersion": worker.MANAGED_CHILD_BINDING_SCHEMA, "receiptId": p["receiptId"], "receiptDigest": p["receiptDigest"],
            "taskExecutionKey": self.key, "hostInvocationId": self.invocation,
            "semanticResultDigest": self.result["semanticResultDigest"], "executionReceiptDigest": self.result["executionReceiptDigest"],
            "resultArtifactDigest": self.head["artifactDigest"], "authoritativeResultHead": self.head,
        }
        self.write_private(self.root / worker._managed_child_binding_relative(p["receiptDigest"]), binding)

    def all_rejected(self, fragment: str = "") -> None:
        for name, action in (("bind", self.bind), ("publication", self.publish), ("reuse", self.reuse), ("merge", self.merge), ("Python merge", self.direct_merge)):
            rejected(action, fragment)
        rejected(lambda: worker._read_authoritative_head(self.root, self.key, self.prepared, self.task), fragment)
        rejected(lambda: worker._validate_receipt(
            worker._make_receipt(json.loads((self.base / "claim.json").read_bytes()), self.key, "complete", None, self.result),
            self.key, self.prepared, self.task, root=self.root,
        ), fragment)


def failed_receipt_bypass() -> None:
    case = Case("r3-failed", "failed")
    try:
        assert case.receipt is not None and case.receipt["terminalStatus"] == "failed"
        audit = delegation.read_committed_managed_child_receipt_record(case.root, case.invocation, case.packet, case.task)
        assert audit == case.receipt
        # A: real committed child.failed plus semantically valid draft.
        rejected(lambda: worker.bind_authoritative_result(
            str(case.root), case.key, case.invocation, str(case.draft_path), str(case.prepared_path), str(case.task_path), managed_child=True,
        ), "completed required")
        # B/C/D: the caller reconstructs coherent result/provenance/digests and
        # even a canonical HEAD/global binding. None confers success authority.
        case.fabricate_head()
        case.all_rejected("completed required")
        for artifact in (case.base / "task-result-head.json", case.base / case.head["artifact"], case.root / worker._managed_child_binding_relative(case.receipt["receiptDigest"])):
            artifact.unlink()
        # E: failure provenance and lifecycle remain readable after closure.
        worker.finalize_task(str(case.root), case.key, case.invocation, "failed")
        assert delegation.read_committed_managed_child_receipt_record(case.root, case.invocation, case.packet, case.task) == audit
        events = [json.loads(p.read_bytes()) for p in (case.base / "events").glob("*.json")]
        assert sum(e["eventType"] == "worker.failed" for e in events) == 1
        assert not any(e["eventType"] in {"worker.completed", "worker.result.accepted"} for e in events)
        assert worker._read_receipt(case.root, case.key, case.invocation)["claim"]["terminalStatus"] == "failed"
        print("Failed-receipt bypass: bind/publication/reuse/merge/reconciliation rejected; audit retained")
    finally:
        case.suite.cleanup()


def direct_authority_fabrication() -> None:
    case = Case("r3-arbitrary", None)
    try:
        assert not hasattr(delegation, "managed_child_execution_authority")
        base = deepcopy(case.result["executionProvenance"])
        variants = [("authority dict without artifact", base)]
        for field, value in (("rootInvocationId", "arbitrary-root"), ("childInvocationId", "arbitrary-child"),
                             ("receiptId", "R-" + "a" * 64), ("receiptDigest", "sha256:" + "b" * 64)):
            variants.append((field, {**base, field: value}))
        for label, provenance in variants:
            case.result = case.forged_result(provenance)
            case.result_path = case.suite.write_json("arbitrary-result.json", case.result)
            case.fabricate_head()
            # Exercise the exact Python APIs that accepted a manually built DTO.
            for supplied in (provenance, delegation.ExecutionAuthority(provenance)):
                rejected(lambda: delegation.bind_result(case.draft, case.packet, case.plan, case.task, case.evidence, authority=supplied))
                rejected(lambda: delegation.validate_result(case.result, case.packet, case.plan, case.task, case.evidence, authority=supplied))
                rejected(lambda: delegation.merge(case.plan, [case.result], case.packet, case.evidence, authorities={case.task["taskId"]: supplied}))
            case.all_rejected("no committed receipt artifact")
            print(f"Direct Python fabrication rejected: {label}")
        # A caller-selected receipt path/dict/digest is not an API surface.
        for field, value in (("receipt_path", str(case.suite.tmp / "nonexistent.json")), ("receipt", base), ("receipt_digest", base["receiptDigest"]), ("authority", delegation.ExecutionAuthority(base))):
            for action, arguments in (
                (worker.bind_authoritative_result, (str(case.root), case.key, case.invocation, str(case.draft_path), str(case.prepared_path), str(case.task_path))),
                (worker.publish_task, (str(case.root), case.key, case.invocation, str(case.result_path), str(case.prepared_path), str(case.task_path))),
                (worker.claim_task, (str(case.root), str(case.prepared_path), str(case.task_path))),
                (worker.merge_authoritative_results, (str(case.root), str(case.prepared_path))),
            ):
                try:
                    action(*arguments, **{field: value})
                except TypeError as error:
                    assert "unexpected keyword" in str(error)
                else:
                    raise AssertionError("worker API accepted caller-selected authority")
    finally:
        case.suite.cleanup()


def completed_lookup_revocation_and_consistency() -> None:
    case = Case("r3-completed", "completed")
    try:
        assert case.bind() == case.result
        assert worker.bind_authoritative_result(str(case.root), case.key, case.invocation, str(case.draft_path), str(case.prepared_path), str(case.task_path), managed_child=True) == case.result
        # Two independent Python publishers race the same claim/result. The
        # existing directory lock/no-replace/CAS protocol must still converge.
        code = (
            "import importlib.util,sys,json; "
            "s=importlib.util.spec_from_file_location('r3race',sys.argv[1]); "
            "m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); "
            "print(json.dumps(m.publish_task(*sys.argv[2:]),sort_keys=True))"
        )
        args = [sys.executable, "-c", code, str(ROOT / "scripts/lib/context-worker-runtime.py"), str(case.root), case.key, case.invocation, str(case.result_path), str(case.prepared_path), str(case.task_path)]
        processes = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        actions = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, stderr
            actions.append(json.loads(stdout)["action"])
        assert sorted(actions) == ["published", "reused"]
        assert case.publish()["action"] == "reused"
        assert case.reuse()["resultObject"] == case.result
        assert case.merge()["mergeStatus"] == "complete"
        assert case.direct_merge() == case.merge()
        assert case.direct_merge()["taskResults"][0]["executionProvenance"] == case.result["executionProvenance"]
        changed = deepcopy(case.draft)
        changed["status"] = "partial"
        different = delegation.bind_result(changed, case.packet, case.plan, case.task, case.evidence,
            managed_child_project_root=case.root, managed_child_invocation_id=case.invocation)
        different_path = case.suite.write_json("completed-different.json", different)
        rejected(lambda: worker.publish_task(str(case.root), case.key, case.invocation, str(different_path), str(case.prepared_path), str(case.task_path)), "conflicting authoritative worker result")

        saved = case.receipt_path.read_bytes()
        assert case.receipt is not None
        # Prior successful lookup/DTO construction cannot cache success proof.
        resolved = delegation.load_committed_completed_managed_child_receipt(case.root, case.invocation, case.packet, case.task)
        manual = delegation.ExecutionAuthority(case.result["executionProvenance"])
        rejected(lambda: delegation.bind_result(case.draft, case.packet, case.plan, case.task, case.evidence, authority=manual), "caller-supplied")
        for field, value in (
            ("commitState", "pending"), ("executionId", "execution-foreign"),
            ("attempt", case.task["attempt"] + 1), ("provider", "codex"),
            ("hostInvocationId", "I-" + "f" * 32), ("receiptId", "R-" + "0" * 64),
            ("receiptDigest", "sha256:" + "0" * 64), ("orderedEventDigest", "sha256:" + "0" * 64),
        ):
            tampered = {**case.receipt, field: value}
            case.write_private(case.receipt_path, tampered)
            try:
                case.all_rejected()
            finally:
                case.receipt_path.write_bytes(saved)
        for field in ("rootInvocationId", "childInvocationId"):
            # A self-consistent canonical replacement passes record validation,
            # but its complete artifact differs from the host commitment.
            events = deepcopy(case.events)
            for event in events:
                if field in event:
                    event[field] = "replacement-" + field
            replacement = {**case.receipt, field: "replacement-" + field, "orderedEventDigest": sha(events)}
            replacement["receiptDigest"] = sha({
                "identityVersion": "mana.context-runtime.provider-native-receipt/v1",
                **{name: replacement[name] for name in ("provider", "attestationKind", "orderedEventCount", "orderedEventDigest")},
            })
            replacement["receiptId"] = "R-" + replacement["receiptDigest"][7:]
            delegation.validate_managed_child_receipt_record(replacement, case.key, case.invocation, case.packet, case.task)
            alternate = case.receipt_path.with_name("replacement.json")
            case.write_private(alternate, replacement)
            held = case.receipt_path.with_name("original-receipt")
            case.receipt_path.rename(held)
            alternate.replace(case.receipt_path)
            try:
                case.all_rejected("host commitment")
            finally:
                held.replace(case.receipt_path)
        for kind in ("missing", "uncommitted", "mode", "parent-mode", "symlink", "type", "noncanonical", "byte-identical-replacement", "hardlink"):
            held = case.receipt_path.with_name("saved-receipt")
            if kind in {"missing", "symlink", "type"}:
                case.receipt_path.rename(held)
                if kind == "symlink":
                    case.receipt_path.symlink_to(held)
                elif kind == "type":
                    case.receipt_path.mkdir()
            elif kind == "uncommitted":
                case.commit_path.rename(case.commit_path.with_suffix(".held"))
            elif kind == "mode":
                case.receipt_path.chmod(0o644)
            elif kind == "parent-mode":
                case.receipt_path.parent.chmod(0o755)
            elif kind == "noncanonical":
                case.receipt_path.write_bytes(saved + b" ")
            elif kind == "byte-identical-replacement":
                case.receipt_path.rename(held)
                case.write_private(case.receipt_path, case.receipt)
            elif kind == "hardlink":
                held.hardlink_to(case.receipt_path)
            try:
                case.all_rejected()
                rejected(lambda: delegation.validate_result(case.result, case.packet, case.plan, case.task, case.evidence, authority=manual))
            finally:
                if kind in {"missing", "symlink", "type", "byte-identical-replacement"}:
                    if kind == "symlink":
                        case.receipt_path.unlink()
                    elif kind == "type":
                        case.receipt_path.rmdir()
                    elif kind == "byte-identical-replacement":
                        case.receipt_path.unlink()
                    held.rename(case.receipt_path)
                elif kind == "hardlink":
                    held.unlink()
                elif kind == "uncommitted":
                    case.commit_path.with_suffix(".held").rename(case.commit_path)
                case.receipt_path.write_bytes(saved)
                case.receipt_path.chmod(0o600)
                case.receipt_path.parent.chmod(0o700)
            print(f"Receipt revocation rejected at every Python boundary: {kind}")
        assert resolved == case.receipt

        claim_path = case.base / "claim.json"
        saved_claim = claim_path.read_bytes()
        foreign_claim = {**json.loads(saved_claim), "invocationId": "I-" + "e" * 32}
        case.write_private(claim_path, foreign_claim)
        try:
            case.all_rejected()
        finally:
            claim_path.write_bytes(saved_claim)

        run_path = case.root / f".mana/runtime/runs/{case.task['executionId']}"
        for filename, field, value in (
            ("run-state-v1.json", "executionVersion", case.task["executionVersion"] + 1),
            ("run-state-v1.json", "currentAttempt", case.task["attempt"] + 1),
            ("execution-envelope-v1.json", "workspaceId", "W-" + "a" * 64),
        ):
            path = run_path / filename
            saved_run = path.read_bytes()
            case.write_private(path, {**json.loads(saved_run), field: value})
            try:
                case.all_rejected("current run HEAD")
                assert delegation.read_committed_managed_child_receipt_record(case.root, case.invocation, case.packet, case.task) == case.receipt
            finally:
                path.write_bytes(saved_run)

        head_path = case.base / "task-result-head.json"
        saved_head = head_path.read_bytes()
        case.write_private(head_path, {**json.loads(saved_head), "invocationId": "I-" + "d" * 32})
        try:
            for action in (case.bind, case.publish, case.reuse):
                rejected(action, "different invocations")
            rejected(case.direct_merge)
        finally:
            head_path.write_bytes(saved_head)

        # Mutating/replacing the file after the safe reader opens it also fails.
        for kind in ("tamper", "replace"):
            fired = False
            def during_read(point: str) -> None:
                nonlocal fired
                if point == "after-final-open" and not fired:
                    fired = True
                    if kind == "tamper":
                        case.receipt_path.write_bytes(saved + b" ")
                    else:
                        path = case.receipt_path.with_name("read-replacement")
                        path.write_bytes(saved)
                        path.chmod(0o600)
                        case.receipt_path.rename(case.receipt_path.with_name("read-original"))
                        path.replace(case.receipt_path)
            runtime._TEST_READ_SYNC_HOOK = during_read
            try:
                rejected(case.bind, "identity changed during read")
                assert fired
            finally:
                runtime._TEST_READ_SYNC_HOOK = None
                if kind == "replace":
                    case.receipt_path.with_name("read-original").replace(case.receipt_path)
                else:
                    case.receipt_path.write_bytes(saved)
        assert case.publish()["action"] == "reused"
        assert case.reuse()["action"] == "reused"
        assert case.merge()["mergeStatus"] == "complete"
        print("Completed positive E2E: bind/publication/reuse/merge/replay passed; concurrent publication converged")
    finally:
        case.suite.cleanup()


def main() -> int:
    failed_receipt_bypass()
    direct_authority_fabrication()
    completed_lookup_revocation_and_consistency()
    print("CTX-07C-R3 direct Python authority regressions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
