#!/usr/bin/env python3
"""CTX-09C-R3B workspace, file-instance and deterministic recovery gates."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


support = load("r3b_support", REPO / "tests/context-runtime-live-shadow.py")
r2c = load("r3b_r2c", REPO / "tests/context-runtime-r2c.py")
live, shared, consumer = support.live, support.shared, support.consumer
FRAMEWORK = REPO / "tests/fixtures/context-runtime/ctx06a-framework"


class WorkspaceBinding(unittest.TestCase):
    setUp = support.LiveShadow.setUp
    tearDown = support.LiveShadow.tearDown
    packet = support.LiveShadow.packet
    semantic = support.LiveShadow.semantic

    def test_packet_exposes_complete_execution_workspace_and_decision_binding(self):
        payload = self.packet(comparison="execution-r3b-packet")
        packet = shared.validate_host(payload, self.project)
        required = {"comparisonExecutionId", "legacyExecutionId", "shadowExecutionId",
                    "executionVersion", "workspaceId", "workspaceBindingDigest", "profileId",
                    "targetKey", "inputPacketDigest", "evidenceSnapshotDigest",
                    "modeDecisionDigest", "budgetDecisionDigest"}
        self.assertTrue(required <= set(packet))
        self.assertEqual(packet["contextManifest"]["executionId"], packet["comparisonExecutionId"])
        self.assertEqual(packet["evidenceManifest"]["executionId"], packet["comparisonExecutionId"])
        self.assertEqual(packet["evidenceManifest"]["workspaceId"], packet["workspaceId"])

    def test_foreign_or_missing_workspace_manifest_and_packet_fail_before_producer(self):
        original = self.packet(comparison="execution-r3b-workspace")
        cases = []
        missing = shared.validate(original); missing.pop("workspaceId")
        cases.append(shared.canonical(missing))
        foreign_manifest = shared.validate(original)
        foreign_manifest["contextManifest"]["executionId"] = "execution-foreign"
        cases.append(shared.canonical(foreign_manifest))
        foreign_evidence = shared.validate(original)
        foreign_evidence["evidenceManifest"]["workspaceId"] = "W-" + "a" * 64
        cases.append(shared.canonical(foreign_evidence))
        incoherent = shared.validate(original)
        incoherent["workspaceBindingDigest"] = "0" * 64
        cases.append(shared.canonical(incoherent))
        for ordinal, payload in enumerate(cases):
            with self.subTest(case=ordinal), mock.patch.object(live.backend, "execute_supervised") as legacy, \
                    mock.patch.object(live.backend, "admit") as shadow:
                with self.assertRaises(shared.Error):
                    live.run_shared(str(self.project), payload)
                legacy.assert_not_called(); shadow.assert_not_called()

    def test_completed_state_cannot_move_between_host_workspaces(self):
        payload = self.packet(comparison="execution-r3b-copy")
        done = live.backend.ProcessResult(0, self.semantic(payload), b"exact stderr")
        with mock.patch.object(live.backend, "execute_supervised", return_value=done):
            first = live.run_shared(str(self.project), payload)
        other = self.base / "workspace-b"
        other.mkdir(mode=0o700)
        workspace = other / self.workspace
        workspace.mkdir(mode=0o700, parents=True)
        (other / ".mana").chmod(0o700); (other / ".mana/sessions").chmod(0o700)
        (workspace / "manifest.yaml").write_text(
            'workspace_type: "session"\nworkspace_id: "different-workspace"\n')
        source = self.project / ".mana/runtime/shadows/execution-r3b-copy"
        destination = other / ".mana/runtime/shadows/execution-r3b-copy"
        destination.parent.mkdir(mode=0o700, parents=True)
        import shutil
        shutil.copytree(source, destination)
        with mock.patch.object(live.backend, "execute_supervised") as producer, \
                self.assertRaises(shared.Error):
            live.run_shared(str(other), payload)
        producer.assert_not_called()
        self.assertEqual(first[2], self.semantic(payload))


class RecoveryMatrix(r2c.Reconciliation):
    def test_exact_outcome_published_pre_head_is_adopted_without_legacy_replay(self):
        payload = self.payload("exact-published")
        self.assertEqual(self.wait_child(self.child(payload, "exact-outcome-published-pre-head")), 99)
        self.assertEqual(self.counts(payload)["legacy"], 1)
        first, second = self.invoke_host(payload), self.invoke_host(payload)
        self.assertEqual(first[2:], second[2:])
        self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 1, "compare": 1})
        self.assert_chain(payload); self.assert_clean(payload)

    def test_exact_outcome_stage_pre_link_is_verified_and_aborted_without_replay(self):
        payload = self.payload("exact-stage")
        outside = self.project / "outside-exact"
        outside.write_bytes(b"unchanged")
        self.assertEqual(self.wait_child(self.child(payload, "exact-outcome-stage-pre-link")), 99)
        recovery = self.base_for(payload) / "recovery"
        self.assertTrue(list(recovery.glob(".live-shadow.stage.*")))
        before = self.counts(payload)
        first = self.invoke_host(payload)
        second = self.invoke_host(payload)
        self.assertEqual((first[0], second[0]), (2, 2))
        self.assertEqual(self.counts(payload), before)
        self.assertFalse(list(recovery.glob(".live-shadow.stage.*")))
        self.assertFalse(list(recovery.glob(".live-shadow.owner.*")))
        self.assertEqual(outside.read_bytes(), b"unchanged")
        self.assert_clean(payload)

    def test_backend_scratch_crashes_are_reconciled_and_never_orphaned(self):
        for ordinal, point in enumerate(("backend-scratch-created-pre-registration",
                                         "backend-scratch-registered-pre-cleanup")):
            payload = self.payload("scratch-" + str(ordinal))
            self.assertEqual(self.wait_child(self.child(payload, point)), 99)
            first, second = self.invoke_host(payload), self.invoke_host(payload)
            self.assertEqual(first[2:], second[2:])
            self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 1, "compare": 1})
            scratch = self.base_for(payload) / "backend-scratch"
            self.assertFalse(scratch.exists() and any(scratch.iterdir()))
            self.assert_clean(payload)


class ShadowCompletedRecovery(unittest.TestCase):
    setUp = support.LiveShadow.setUp
    tearDown = support.LiveShadow.tearDown
    packet = support.LiveShadow.packet
    semantic = support.LiveShadow.semantic

    def exercise_completed_ctx06_recovery(self, fault_point):
        suffix = fault_point.replace("after-", "").replace("shadow-", "s-")
        comparison_id = "execution-r3b-" + suffix
        profile = "ctx06c-fixture"
        snapshot = consumer.snapshot(profile, FRAMEWORK)
        manifest = shared.runtime.compile_context_manifest(FRAMEWORK, profile, comparison_id)
        inputs = shared.canonical({"legacyPrompt": "LOCAL", "legacyArgv": ["exec"],
            "economyModel": "fixture-economy", "fullModel": "fixture-full",
            "objective": "LOCAL", "pipelineSnapshot": snapshot})
        payload = shared.materialize(comparison_id, profile, {}, inputs, manifest, "codex",
                                     project_root=self.project, workspace=self.workspace)
        legacy = live.backend.ProcessResult(0, self.semantic(payload), b"legacy stderr")
        packet = shared.validate(payload)
        (self.bin / "codex").unlink()
        (self.bin / "codex").symlink_to(REPO / "tests/fixtures/context-runtime/ctx06c-provider-stub.sh")
        provider_state = self.base / "phase-provider-state"
        os.environ.update(CTX06C_FIXTURE_ROOT=str(REPO / "tests/fixtures/context-runtime"),
                          CTX06C_STATE_DIR=str(provider_state))
        class Admission:
            status, reason = "available", None
            def invoke(_self, argv, *, input_bytes, environment, cwd):
                status, output, diagnostics = consumer.consume(
                    input_bytes, "v2", Path(cwd), framework_root=FRAMEWORK)
                return live.backend.ProcessResult(status, output, diagnostics)
        @contextmanager
        def admitted(*args, **kwargs):
            yield Admission()
        with mock.patch.object(live, "_TEST_FRAMEWORK_ROOT", FRAMEWORK), \
                mock.patch.object(live.backend, "execute_supervised", return_value=legacy), \
                mock.patch.object(live.backend, "admit", side_effect=admitted):
            pid = os.fork()
            if pid == 0:
                os.environ.update(MANA_CTX09C_FAULT=fault_point,
                                  MANA_CTX09C_FAULT_EXIT="1")
                live.run_shared(str(self.project), payload)
                os._exit(98)
            _, wait_status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(wait_status), 99)
        count_before = (provider_state / "count").read_text()
        with mock.patch.object(live, "_TEST_FRAMEWORK_ROOT", FRAMEWORK), \
                mock.patch.object(live.backend, "execute_supervised") as legacy_again, \
                mock.patch.object(live.backend, "admit") as shadow_again:
            recovered = live.run_shared(str(self.project), payload)
            reused = live.run_shared(str(self.project), payload)
        legacy_again.assert_not_called(); shadow_again.assert_not_called()
        self.assertEqual(recovered[2:], reused[2:])
        self.assertEqual(recovered[1]["transactionStage"], "completed")
        self.assertEqual((provider_state / "count").read_text(), count_before)
        self.assertEqual(recovered[2:], (self.semantic(payload), b"legacy stderr"))

    def test_completed_ctx06_chain_reprojects_without_provider_reexecution(self):
        self.exercise_completed_ctx06_recovery("after-shadow-process-exit")

    def test_projection_published_pre_receipt_recovers_exactly_once(self):
        self.exercise_completed_ctx06_recovery("shadow-projection-published-pre-receipt")

    def test_receipt_published_pre_head_recovers_exactly_once(self):
        self.exercise_completed_ctx06_recovery("shadow-receipt-published-pre-live-shadow-head")


if __name__ == "__main__":
    unittest.main()
