#!/usr/bin/env python3
"""R3A permanent gates: real consumer/processes, no provider service/model calls."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from contextlib import contextmanager
from unittest import mock

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


support = load("r3a_support", REPO / "tests/context-runtime-live-shadow.py")
real = load("r3a_real", REPO / "tests/context-runtime-r2a.py")
live, shared = support.live, support.shared


class CandidateAuthority(unittest.TestCase):
    setUp = support.LiveShadow.setUp
    tearDown = support.LiveShadow.tearDown
    packet = support.LiveShadow.packet
    semantic = support.LiveShadow.semantic

    def base_for(self, payload):
        return live.SHADOW_NAMESPACE + "/" + shared.validate(payload)["identity"]["comparisonExecutionId"]

    @contextmanager
    def host(self, payload, shadow_output, *, shadow_action=None):
        @contextmanager
        def admitted(*_, **kwargs):
            yield live.backend.Admission("available", None)
        with mock.patch.object(live.consumer, "capabilities", return_value={}), \
                mock.patch.object(live.backend, "admit", side_effect=admitted), \
                mock.patch.object(live.backend.Admission, "invoke", side_effect=shadow_action,
                    return_value=live.backend.ProcessResult(0, shadow_output, b"")), \
                mock.patch.object(live, "_shadow_candidate_context", return_value={
                    "workspaceId": shared.validate(payload)["workspaceId"],
                    "committedChainDigest": shared.digest(b"offline chain")}):
            yield

    def test_gate_stale_fail_legacy_blocked_shadow_fail_never_equivalent(self):
        snapshot = live.consumer.snapshot("ctx06c-fixture", support.FIXTURES / "ctx06a-framework")
        payload = self.packet(snapshot=snapshot)
        packet = shared.validate(payload)
        current = self.semantic(payload)  # current status = blocked
        stale = json.loads(current)
        stale["dimensions"]["status"]["records"][0]["value"] = "fail"
        stale = live.canonical(stale)
        relative = self.base_for(payload) + "/legacy-artifact-v1.json"
        live.mode.publish_legacy_artifact(str(self.project), packet["identity"]["comparisonExecutionId"],
            packet["profileId"], shared.digest(shared.canonical(packet["target"])), relative, stale)
        with self.host(payload, stale), mock.patch.object(live.backend, "execute_supervised",
                return_value=live.backend.ProcessResult(0, current, b"exact legacy stderr")):
            status, result, output, stderr = live.run_shared(str(self.project), payload)
        self.assertEqual((status, output, stderr), (0, current, b"exact legacy stderr"))
        self.assertEqual(result["validation"]["legacy"]["errorCategory"], "candidate-conflict")
        self.assertNotIn("legacy", result["artifacts"])
        self.assertNotEqual(result["comparison"].get("diagnosticStatus"), "equivalent")
        self.assertIn(result["comparison"]["status"], {"unavailable", "indeterminate"})
        self.assertEqual((self.project / relative).read_bytes(), stale)

    def test_binding_idempotence_and_each_candidate_dimension_conflicts(self):
        payload = self.packet()
        packet, structured = shared.validate(payload), self.semantic(payload)
        with live.mode.HostRoot(str(self.project)) as root:
            live._publish_outcome(root, self.base_for(payload), packet["identity"],
                live.backend.ProcessResult(0, structured, b"exact stderr"))
            valid, source = live._publish_validated_artifact(root, str(self.project), packet, "legacy", 0, structured)
            self.assertEqual(valid["status"], "valid")
            self.assertIsNotNone(source)
            self.assertEqual(live._publish_validated_artifact(root, str(self.project), packet, "legacy", 0, structured)[1], source)
            binding = self.project / self.base_for(payload) / "records/legacy-candidate-binding-v1.json"
            original = binding.read_bytes()
            record = json.loads(original)
            for field in record:
                with self.subTest(field=field):
                    changed = {**record, field: "foreign-candidate"}
                    binding.write_bytes(live.canonical(changed))
                    observation, reused = live._publish_validated_artifact(root, str(self.project), packet, "legacy", 0, structured)
                    self.assertIsNone(reused)
                    self.assertEqual(observation["errorCategory"], "candidate-conflict")
            binding.write_bytes(original)
            changed_packet = copy.deepcopy(packet)
            changed_packet["input"] = shared.blob(b"different input")
            changed_packet["digests"]["input"] = shared.digest(b"different input")
            self.assertIsNone(live._publish_validated_artifact(root, str(self.project), changed_packet, "legacy", 0, structured)[1])
            # Valid structured candidate, but not the current exact output.
            different = json.loads(structured)
            different["dimensions"]["status"]["records"][0]["value"] = "fail"
            self.assertIsNone(live._publish_validated_artifact(root, str(self.project), packet, "legacy", 0,
                live.canonical(different))[1])

    def test_real_legacy_authority_barrier_event_order(self):
        snapshot = live.consumer.snapshot("ctx06c-fixture", support.FIXTURES / "ctx06a-framework")
        payload, events = self.packet(snapshot=snapshot), []
        # Real local legacy process, exact binary stderr, semantic stdout.
        done = live.backend.execute_supervised
        fixture = REPO / "tests/fixtures/context-runtime/ctx09c-r2b-provider.py"
        import base64
        environment = {**os.environ, "CTX09C_R2B_STDOUT": base64.b64encode(self.semantic(payload)).decode(),
            "CTX09C_R2B_STDERR": base64.b64encode(b"exact\x00\xff").decode(), "CTX09C_R2B_EXIT": "0",
            "CTX09C_R2B_COUNT": str(self.base / "legacy-invocations")}

        def invoke_legacy(_argv, **kwargs):
            kwargs["environment"] = environment
            return done([sys.executable, str(fixture)], **kwargs)

        def event(name):
            if name == "legacy.projection.validated":
                outcome = self.project / self.base_for(payload) / "recovery/legacy-outcome-v1.json"
                self.assertTrue(outcome.is_file())
            if name == "shadow.invocation.started":
                head = json.loads((self.project / self.base_for(payload) / live.HEAD_NAME).read_bytes())
                self.assertEqual(head["stage"], "legacy_committed")
            events.append(name)

        with self.host(payload, self.semantic(payload)), \
                mock.patch.object(live.backend, "execute_supervised", side_effect=invoke_legacy), \
                mock.patch.object(live, "_TEST_EVENT_HOOK", event):
            status, result, output, stderr = live.run_shared(str(self.project), payload)
        self.assertEqual((status, output, stderr), (0, self.semantic(payload), b"exact\x00\xff"))
        required = ["legacy.process.exited", "legacy.streams.captured", "legacy.outcome.attested",
                    "legacy.projection.validated", "legacy.producer.published", "legacy.receipt.published",
                    "legacy.head.committed", "shadow.invocation.started"]
        self.assertEqual([name for name in events if name in required], required)
        self.assertEqual(result["authority"], "legacy")

    def test_real_process_usage_failed_timeout_sigint_sigterm(self):
        snapshot = live.consumer.snapshot("ctx06c-fixture", support.FIXTURES / "ctx06a-framework")
        for outcome, expected in (("failed", "failed"), ("timeout", "timed_out"),
                                  ("SIGINT", "interrupted"), ("SIGTERM", "interrupted")):
            with self.subTest(outcome=outcome):
                payload = self.packet(snapshot=snapshot, comparison="execution-r3a-usage-" + outcome)
                packet = shared.validate(payload)
                identity = packet["identity"]
                metrics = identity["shadowRunRoot"] + "/.mana/runtime/metrics/" + identity["shadowProducerId"] + "/usage-summary-v1.json"

                def shadow(_argv, **kwargs):
                    return live.backend.execute_supervised([sys.executable,
                        str(REPO / "tests/fixtures/context-runtime/ctx09c-r3a-usage.py"),
                        str(self.project / metrics), identity["shadowProducerId"], packet["profileId"], outcome],
                        timeout_name="MANA_CTX09C_SHADOW_TIMEOUT_SECONDS", **kwargs)

                with self.host(payload, b"", shadow_action=shadow), mock.patch.dict(os.environ,
                        {"MANA_CTX09C_SHADOW_TIMEOUT_SECONDS": "1", "MANA_CTX09C_KILL_GRACE_SECONDS": "1"}):
                    status, result, output, _ = live.run_shared(str(self.project), payload)
                self.assertEqual((status, output), (0, b"legacy-answer\n"))
                self.assertEqual(result["shadowStatus"], expected)
                side = result["usage"]["v2"]
                self.assertEqual(side["availability"], "measured")
                self.assertEqual(side["totals"], {"input": 10, "cachedInput": 2, "uncachedInput": 8, "output": 3, "reasoning": 1})
                self.assertTrue(all(value is None for value in result["usage"]["v2MinusLegacy"].values()))

    def test_production_cli_refuses_test_backend_and_environment_selector(self):
        argv = [sys.executable, str(REPO / "scripts/context-runtime-mode.py"), "shadow-run",
                "--project-root", str(self.project), "--execution-id", "execution-r3a-cli",
                "--test-only-backend", "--", str(REPO / "scripts/run-profile.sh")]
        result = subprocess.run(argv, capture_output=True, env={**os.environ, "MANA_CTX09_TEST_ONLY_CONTAINED": "1"})
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"unrecognized arguments", result.stderr)
        self.assertFalse((self.project / live.mode.NAMESPACE / "execution-r3a-cli").exists())
        with live.mode.HostRoot(str(self.project)) as root, \
                mock.patch.object(live.mode.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"denied")), \
                mock.patch.object(live.mode.subprocess, "call") as invocation, \
                mock.patch.dict(os.environ, {"MANA_CTX09_TEST_ONLY_CONTAINED": "1"}):
            with self.assertRaises(live.mode.runtime.ContractError):
                live.mode.shadow_legacy(root, [str(REPO / "tests/context-shadow-backend-test-only.py")])
            invocation.assert_not_called()

    def test_failed_usage_partial_absent_invalid_and_comparable_deltas(self):
        value = {"schemaVersion": "1", "executionId": "execution-r3a-accounting", "profileId": "jira-state-audit",
                 "provider": "codex", "providerVersion": "offline", "status": "failed", "usageStatus": "measured",
                 "phases": [], "parseErrors": 0, "rawTraceRetained": False, "turns": 1, "toolCalls": 0,
                 "workers": 0, "compactions": 0,
                 "totals": {"input": 10, "cachedInput": 2, "uncachedInput": 8, "output": 3, "reasoning": 1}}
        with live.mode.HostRoot(str(self.project)) as root:
            def read(name, summary):
                relative = live.SHADOW_NAMESPACE + "/accounting/" + name + ".json"
                live.private_write(root, relative, live.canonical(summary))
                return live.read_usage(root, relative, value["executionId"], value["profileId"], "shadow-invocation")
            measured = read("measured", value)
            self.assertEqual((measured["availability"], measured["status"]), ("measured", "failed"))
            self.assertEqual(live.usage_comparison(measured, measured)["v2MinusLegacy"], dict.fromkeys(live.USAGE_FIELDS, 0))
            partial = read("partial", {**value, "usageStatus": "partial", "totals": {**value["totals"], "reasoning": None}})
            self.assertEqual(partial["availability"], "partial")
            self.assertEqual(partial["totals"]["input"], 10)
            invalid = read("invalid", {**value, "totals": {**value["totals"], "cachedInput": 20}})
            self.assertEqual(invalid["availability"], "invalid")
            absent = live.read_usage(root, None, value["executionId"], value["profileId"], "shadow-invocation")
            self.assertEqual(absent["availability"], "unavailable")
            for side in (partial, invalid, absent):
                self.assertTrue(all(delta is None for delta in live.usage_comparison(measured, side)["v2MinusLegacy"].values()))

    def test_denied_native_backend_zero_shadow_invocation_preserves_legacy_sentinels(self):
        snapshot = live.consumer.snapshot("ctx06c-fixture", support.FIXTURES / "ctx06a-framework")
        payload = self.packet(snapshot=snapshot)
        sentinel = self.base / "outside-sentinel"
        sentinel.write_bytes(b"UNCHANGED")
        @contextmanager
        def denied(*_):
            yield live.backend.Admission("unavailable", "native-backend-unproven-or-denied")
        with mock.patch.object(live.consumer, "capabilities", return_value={}), \
                mock.patch.object(live.backend, "admit", side_effect=denied), \
                mock.patch.object(live.backend.Admission, "invoke") as invocation:
            status, result, output, _ = live.run_shared(str(self.project), payload)
        invocation.assert_not_called()
        self.assertEqual((status, output), (0, b"legacy-answer\n"))
        self.assertEqual(result["shadowStatus"], "unavailable")
        self.assertEqual(sentinel.read_bytes(), b"UNCHANGED")

    def test_production_native_hostile_process_attempts_real_operations(self):
        run, metrics = self.project / "private-shadow-run", self.project / "private-shadow-metrics"
        run.mkdir(mode=0o700)
        metrics.mkdir(mode=0o700)
        legacy = self.project / ".mana/runtime/runs/legacy/HEAD"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"LEGACY_HEAD_UNCHANGED")
        outside = self.base / "outside"
        outside.mkdir(mode=0o700)
        with live.backend.admit(run, metrics) as admission:
            if admission.status != "available":
                print("R3A native hostile process: NON ESEGUITO; " + str(admission.reason))
                with self.assertRaises(RuntimeError):
                    admission.invoke([sys.executable, str(REPO / "scripts/lib/context-shadow-boundary-probe.py")],
                        input_bytes=b"{}", environment=os.environ, cwd=run)
                self.assertEqual(legacy.read_bytes(), b"LEGACY_HEAD_UNCHANGED")
                return
            allowed = admission.scratch / "input"
            allowed.write_bytes(b"SHARED_INPUT")
            paths = {"publish": str(outside / "publish"), "externalWrite": str(outside / "external"),
                     "allowedInput": str(allowed), "reads": {"legacyHead": str(legacy)}}
            result = admission.invoke([sys.executable, str(REPO / "scripts/lib/context-shadow-boundary-probe.py")],
                input_bytes=json.dumps(paths).encode(), environment=os.environ, cwd=run)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        for operation in ("publish", "externalWrite", "legacyHead", "network", "serviceDiscovery"):
            self.assertTrue(observed[operation], operation)
        self.assertEqual(legacy.read_bytes(), b"LEGACY_HEAD_UNCHANGED")
        self.assertEqual(list(outside.iterdir()), [])


class PrecommitPrivacy(unittest.TestCase):
    setUp = real.R2A.setUp
    tearDown = real.R2A.tearDown

    def test_shadow_binding_uses_actual_current_committed_chain(self):
        packet = self.packet
        project = self.project / packet["identity"]["shadowRunRoot"]
        with live.mode.HostRoot(str(self.project)) as root:
            live.private_write(root, packet["identity"]["shadowRunRoot"] + "/.fixture", b"")
        typed = copy.deepcopy(real.BASELINE)
        typed["profileId"] = packet["profileId"]
        typed["targetKey"] = real.shared.digest(real.shared.canonical(packet["target"]))
        typed["dimensions"]["externalWritePolicy"]["records"][0]["value"] = {
            "repositoryWrite": False, "externalWrite": False, "approvedActionKeys": []}
        source = self.base / "typed.json"
        source.write_bytes(real.shared.canonical(typed))
        with mock.patch.dict(os.environ, {"CTX09C_R2A_PROJECTION_PATH": str(source)}):
            status, output, _ = real.consumer.consume(self.payload, "v2", project, framework_root=real.FRAMEWORK)
        self.assertEqual(status, 0)
        original = live._shadow_candidate_context
        with live.mode.HostRoot(str(self.project)) as root, mock.patch.object(live, "_shadow_candidate_context",
                side_effect=lambda *args: original(*args, framework_root=real.FRAMEWORK)):
            valid, artifact = live._publish_validated_artifact(root, str(self.project), packet, "v2", 0, output)
            self.assertEqual(valid["status"], "valid")
            self.assertIsNotNone(artifact)
            self.assertEqual(live._publish_validated_artifact(root, str(self.project), packet, "v2", 0, output)[1], artifact)
            record = json.loads((self.project / live.SHADOW_NAMESPACE / packet["identity"]["comparisonExecutionId"] /
                "records/v2-candidate-binding-v1.json").read_bytes())
            projection = json.loads(output)
            self.assertRegex(record["committedChainDigest"], r"^[a-f0-9]{64}$")
            self.assertNotEqual(record["committedChainDigest"], live.shared.digest(live.canonical(projection["provenance"])))
            changed = copy.deepcopy(projection)
            changed["dimensions"]["status"]["records"][0]["value"] = "fail"
            rejected, reused = live._publish_validated_artifact(root, str(self.project), packet, "v2", 0, live.canonical(changed))
            self.assertIsNone(reused)
            self.assertEqual(rejected["errorCategory"], "candidate-binding-invalid")

    def test_environment_canary_real_consumer_never_commits_checkpoint(self):
        # Real subprocess consumer uses installed local stub, not a mocked reducer.
        result = subprocess.run([sys.executable, str(REPO / "tests/context-shadow-consumer-test-only.py"),
            str(self.project)], input=self.payload, capture_output=True,
            env={**os.environ, "CTX06C_SCENARIO": "privacy-canary"})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertNotIn(b"CTX09C_ENVIRONMENT_CANARY", result.stderr)
        execution = self.packet["identity"]["shadowProducerId"]
        run = self.project / real.consumer.pipeline.relative_run_directory(execution)
        state = json.loads((run / "run-state-v1.json").read_bytes())
        self.assertNotEqual(state["status"], "completed")
        self.assertIsNone(state["transitionId"])
        self.assertEqual(list((run / "transitions").iterdir()), [])
        for path in self.project.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"CTX09C_ENVIRONMENT_CANARY", path.read_bytes(), str(path))
        self.assertEqual(list(self.project.rglob("producer-receipt-v1.json")), [])
        self.assertEqual(list(self.project.rglob("*-artifact-v1.json")), [])

    def test_shared_guard_covers_fields_and_arbitrary_environment_values(self):
        privacy = real.consumer.privacy
        for name in ("environment", "credential", "Authorization", "cookie", "token", "prompt",
                     "response", "reasoning", "providerStderr", "sourceRaw", "fullDiff", "rawEvidence"):
            with self.subTest(name=name), self.assertRaises(privacy.PrivacyError):
                privacy.validate({name: "private payload"})
        with mock.patch.dict(os.environ, {"CTX09_ARBITRARY_SECRET": "ambient-private-value"}):
            with self.assertRaises(privacy.PrivacyError):
                privacy.validate({"claim": "ambient-private-value"})


if __name__ == "__main__":
    unittest.main()
