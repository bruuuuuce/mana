#!/usr/bin/env python3
"""CTX-09C-R1A/R1B exclusively local consumer, recovery and authority regressions."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ctx09c_live", REPO / "scripts/context-runtime-live-shadow.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)
shared, consumer = live.shared, live.consumer
test_backend_spec = importlib.util.spec_from_file_location("ctx09c_test_backend", REPO / "tests/context-shadow-backend-test-harness.py")
test_backend = importlib.util.module_from_spec(test_backend_spec)
test_backend_spec.loader.exec_module(test_backend)
FIXTURES = REPO / "tests/fixtures/context-runtime"
BASELINE = json.loads((FIXTURES / "comparison/baseline.json").read_bytes())


class LiveShadow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp" if sys.platform == "darwin" else "/tmp")
        self.base = Path(self.temp.name)
        self.project = self.base / "project with spaces"
        self.project.mkdir(mode=0o700)
        self.workspace = ".mana/sessions/ctx09c-test-workspace"
        workspace = self.project / self.workspace
        workspace.mkdir(mode=0o700, parents=True)
        (self.project / ".mana").chmod(0o700)
        (self.project / ".mana/sessions").chmod(0o700)
        (workspace / "manifest.yaml").write_text(
            'workspace_type: "session"\nworkspace_id: "ctx09c-test-workspace"\n')
        self.bin = self.base / "bin"
        self.bin.mkdir()
        (self.bin / "codex").symlink_to(FIXTURES / "ctx09a-provider-stub.py")
        self.env = mock.patch.dict(os.environ, {"PATH": str(self.bin) + ":" + os.environ["PATH"],
             "CTX09_ACTION": "complete", "MANA_UPDATE_CHECK": "off", "PYTHONDONTWRITEBYTECODE": "1"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def packet(self, *, snapshot=None, prompt="original input", comparison="execution-live-r1a"):
        manifest = shared.runtime.compile_context_manifest(REPO, "jira-state-audit", comparison)
        inputs = shared.canonical({"legacyPrompt": prompt, "legacyArgv": ["exec", "--project-root", str(self.project),
            "--flag", "first", "--flag", "second", "", "quotes '\" and newline\nnext"], "economyModel": "fixture-economy", "fullModel": "fixture-full",
            "objective": "Original work item", "pipelineSnapshot": snapshot})
        return shared.materialize(comparison, "jira-state-audit", {"workItem": "LOCAL-7"}, inputs, manifest, "codex",
                                  project_root=self.project, workspace=self.workspace)

    def semantic(self, payload):
        value = json.loads(json.dumps(BASELINE))
        packet = shared.validate(payload)
        value["profileId"] = packet["profileId"]
        value["targetKey"] = shared.digest(shared.canonical(packet["target"]))
        return live.canonical(value)

    def test_production_legacy_consumes_packet_and_gap_invokes_no_shadow(self):
        payload = self.packet()
        capture_path = self.base / "actual argv.json"
        os.environ["CTX09_ARGV_CAPTURE"] = str(capture_path)
        with mock.patch.object(live.backend, "admit") as admission:
            status, result, output, _ = live.run_shared(str(self.project), payload)
        self.assertEqual(status, 0)
        self.assertEqual(output, b"legacy-answer\n")
        self.assertEqual(result["shadowStatus"], "unavailable")
        self.assertEqual(result["authority"], "legacy")
        admission.assert_not_called()
        identity = shared.validate(payload)["identity"]
        record = json.loads((self.project / identity["legacyMetricsRoot"] / "shared-input-consumption-v1.json").read_bytes())
        self.assertEqual(record["packetDigest"], shared.digest(payload))
        self.assertEqual(record["digests"], result["input"]["digests"])
        self.assertFalse((self.project / identity["shadowRunRoot"]).exists())
        expected = shared.decode(shared.unblob(shared.validate(payload)["input"]))["legacyArgv"]
        actual = json.loads(capture_path.read_bytes())
        for index, value in enumerate(expected):
            with self.subTest(argv=index):
                self.assertEqual(actual[index], value)
        persisted = b"".join(path.read_bytes() for path in self.project.rglob("*.json"))
        self.assertNotIn(b"original input", persisted)
        self.assertNotIn(b"legacy-answer", persisted)

    def test_legacy_failure_remains_authoritative_when_unavailable(self):
        os.environ["CTX09_ACTION"] = "fail"
        status, result, output, _ = live.run_shared(str(self.project), self.packet())
        self.assertEqual(status, 23)
        self.assertEqual(result["legacy"], {"status": "failed", "exitStatus": 23})
        self.assertEqual(result["shadowStatus"], "unavailable")
        self.assertEqual(output, b"legacy-answer\n")

    def test_actual_provider_capability_gap_never_starts_shadow(self):
        snapshot = consumer.snapshot("ctx06c-fixture", FIXTURES / "ctx06a-framework")
        with mock.patch.object(live.backend, "admit") as admission:
            status, result, output, _ = live.run_shared(str(self.project), self.packet(snapshot=snapshot))
        self.assertEqual((status, output), (0, b"legacy-answer\n"))
        self.assertEqual(result["shadowStatus"], "unavailable")
        self.assertIsNone(result["v2"]["exitStatus"])
        admission.assert_not_called()

    def test_successful_side_receipts_compare_only_bounded_host_metadata(self):
        # Metadata publication unit test; real native containment and real
        # v2 consumption are independently exercised below and in input tests.
        snapshot = consumer.snapshot("ctx06c-fixture", FIXTURES / "ctx06a-framework")
        payload = self.packet(snapshot=snapshot)
        @contextmanager
        def admitted(*args, **kwargs):
            yield live.backend.Admission("available", None)
        with mock.patch.object(consumer, "capabilities", return_value={}), \
                mock.patch.object(live.backend, "admit", side_effect=admitted), \
                mock.patch.object(live.backend, "execute_supervised", return_value=
                    live.backend.ProcessResult(0, self.semantic(payload), b"private provider stderr")), \
                mock.patch.object(live.backend.Admission, "invoke", return_value=
                    subprocess.CompletedProcess([], 0, self.semantic(payload), b"private provider stderr")) as invocation, \
                mock.patch.object(live, "_shadow_candidate_context", return_value={
                    "workspaceId": shared.validate(payload)["workspaceId"],
                    "committedChainDigest": shared.digest(b"fixed local test chain")}):
            status, result, output, _ = live.run_shared(str(self.project), payload)
        self.assertEqual((status, output), (0, self.semantic(payload)))
        self.assertEqual(result["shadowStatus"], "completed")
        self.assertEqual(invocation.call_args.kwargs["input_bytes"], payload)
        self.assertEqual(set(result["artifacts"]), {"legacy", "v2"})
        self.assertEqual(result["comparison"]["diagnosticStatus"], "equivalent")
        self.assertTrue(result["comparison"]["complete"])
        for role, source in result["artifacts"].items():
            self.assertEqual(source["producerRuntime"], role)
            metadata = json.loads((self.project / source["path"]).read_bytes())
            self.assertEqual(metadata["profileId"], "jira-state-audit")
        persisted = b"".join(path.read_bytes() for path in self.project.rglob("*.json"))
        self.assertNotIn(b"private shadow output", persisted)
        self.assertNotIn(b"private provider stderr", persisted)

    def test_invalid_and_private_candidates_never_publish_or_compare(self):
        payload = self.packet(comparison="execution-r1c-invalid")
        cases = [(b"{not-json", "schema-invalid", "malformed"),
                 (b'{"schemaVersion":"mana.context-runtime.semantic-comparison-input/v1"}', "semantic-invalid", "semantic")]
        cases.extend((self.semantic(payload).replace(b'"blocked"', f'"CTX09C_{name.upper()}_CANARY"'.encode()),
                      "privacy-invalid", name)
                     for name in ("prompt", "source", "credential", "cookie", "token", "response", "reasoning", "stderr", "diff", "evidence"))
        for candidate, category, name in cases:
            with self.subTest(category=category), mock.patch.object(live.backend, "execute_supervised", return_value=
                    live.backend.ProcessResult(0, candidate, b"CTX09C_STDERR_CANARY")):
                status, result, output, _ = live.run_shared(str(self.project), payload if category == "schema-invalid" else
                    self.packet(comparison="execution-r1c-" + name))
            self.assertEqual(status, 0)
            self.assertEqual(result["validation"]["legacy"]["status"], "invalid")
            self.assertEqual(result["artifacts"], {})
            self.assertNotEqual(result["comparison"].get("diagnosticStatus"), "equivalent")
            # R2B retains the exact legacy streams only in sensitive recovery;
            # privacy rejection still excludes them from every projection and
            # public diagnostic/usage/lifecycle artifact.
            persisted = b"".join(path.read_bytes() for path in self.project.rglob("*")
                                 if path.is_file() and "recovery" not in path.parts)
            self.assertNotIn(candidate, persisted)
            self.assertNotIn(b"CTX09C_STDERR_CANARY", persisted)

    def test_usage_comparison_preserves_side_identity_and_never_invents_zero(self):
        legacy = {"availability": "measured", "reportedStatus": "measured", "status": "complete",
                  "invocationId": "legacy-I", "parseErrors": 0,
                  "totals": {"input": 10, "cachedInput": 2, "uncachedInput": 8, "output": 4, "reasoning": 1}, "missing": [], "reason": None}
        missing = live._missing_usage("shadow-I")
        report = live.usage_comparison(legacy, missing)
        self.assertEqual(report["availability"], "unavailable")
        self.assertTrue(all(value is None for value in report["v2MinusLegacy"].values()))
        self.assertEqual(report["legacy"]["invocationId"], "legacy-I")
        self.assertEqual(report["v2"]["invocationId"], "shadow-I")
        partial = {**legacy, "availability": "partial", "reportedStatus": "partial",
                   "totals": {**legacy["totals"], "reasoning": None}, "missing": ["reasoning"]}
        report = live.usage_comparison(legacy, partial)
        self.assertEqual(report["availability"], "partial")
        self.assertTrue(all(value is None for value in report["v2MinusLegacy"].values()))
        invalid = {**legacy, "availability": "invalid", "parseErrors": 2}
        self.assertEqual(live.usage_comparison(legacy, invalid)["availability"], "invalid")

    def test_test_only_backend_uses_a_real_process_and_is_not_production_admission(self):
        outside = self.base / "outside"
        outside.mkdir()
        legacy = outside / "legacy-head"
        legacy.write_bytes(b"LEGACY")
        with test_backend.admit_test_only() as admission:
            allowed = admission.scratch / "input"
            allowed.write_bytes(b"SHARED_INPUT")
            paths = {"publish": str(self.project / "publish"), "externalWrite": str(outside / "write"),
                     "allowedInput": str(allowed), "reads": {"legacyHead": str(legacy)}}
            if admission.status != "available":
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    admission.invoke([sys.executable, str(REPO / "tests/context-shadow-backend-test-only.py")],
                                     input_bytes=json.dumps(paths).encode(), environment=os.environ.copy(), cwd=self.project)
                self.assertFalse((outside / "write").exists())
                return
            result = admission.invoke([sys.executable, str(REPO / "tests/context-shadow-backend-test-only.py")],
                                      input_bytes=json.dumps(paths).encode(), environment=os.environ.copy(), cwd=self.project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"externalWrite": True, "network": True, "publish": True,
                         "legacyHead": True, "allowedInput": True, "serviceDiscovery": True,
                         "dynamicHardlink": True, "dynamicSymlink": True, "allowedWrite": True})

    def test_absent_nested_denied_and_unknown_backend_still_run_legacy(self):
        for reason in ("native-backend-absent", "nested-sandbox-denied", "unknown"):
            @contextmanager
            def unavailable(*args, **kwargs):
                yield live.backend.Admission("unavailable", reason)
            with self.subTest(reason=reason), mock.patch.object(consumer, "snapshot", return_value={}), \
                    mock.patch.object(consumer, "declaration_from_snapshot"), \
                    mock.patch.object(consumer, "capabilities", return_value={}), \
                    mock.patch.object(live.backend, "admit", side_effect=unavailable), \
                    mock.patch.object(live.backend.Admission, "invoke") as shadow_invocation:
                status, result, output, _ = live.run_shared(str(self.project), self.packet(snapshot={}, comparison="execution-" + reason))
                self.assertEqual((status, output), (0, b"legacy-answer\n"))
                self.assertEqual(result["shadowStatus"], "unavailable")
                self.assertEqual(result["shadowUnavailableReason"], reason)
                shadow_invocation.assert_not_called()

    def test_source_mutation_does_not_change_legacy_prompt(self):
        source = self.base / "mutable source"
        source.write_text("source before capture")
        payload = self.packet(prompt=source.read_text())
        source.write_text("source after capture")
        os.environ["CTX09_ACTION"] = "prompt-hash"
        status, _, output, _ = live.run_shared(str(self.project), payload)
        self.assertEqual(status, 0)
        self.assertEqual(output.strip(), shared.digest(b"source before capture").encode())

    def test_existing_shared_legacy_directory_modes_are_preserved(self):
        for relative in (".mana", ".mana/runtime", ".mana/runtime/runs", ".mana/runtime/metrics"):
            path = self.project / relative
            path.mkdir(exist_ok=True)
            path.chmod(0o755)
        status, _, output, _ = live.run_shared(str(self.project), self.packet())
        self.assertEqual((status, output), (0, b"legacy-answer\n"))
        for relative in (".mana", ".mana/runtime", ".mana/runtime/runs", ".mana/runtime/metrics"):
            self.assertEqual((self.project / relative).stat().st_mode & 0o777, 0o755)

    def test_real_v2_finite_pipeline_consumes_same_captured_bytes(self):
        # Explicit internal fixture framework; production CLI offers no
        # framework, backend, launcher or arbitrary command override.
        framework = FIXTURES / "ctx06a-framework"
        state = self.base / "stub state"
        state.mkdir()
        os.environ.update(CTX06C_FIXTURE_ROOT=str(FIXTURES), CTX06C_STATE_DIR=str(state))
        profile, execution = "ctx06c-fixture", "execution-fixture-r1a"
        manifest = shared.runtime.compile_context_manifest(framework, profile, execution)
        original = "source before materialization"
        source = self.base / "source snapshot"
        source.write_text(original)
        inputs = shared.canonical({"legacyPrompt": source.read_text(), "legacyArgv": ["exec"], "economyModel": "fixture-economy",
            "fullModel": "fixture-full", "objective": original, "pipelineSnapshot": consumer.snapshot(profile, framework)})
        payload = shared.materialize(execution, profile, {}, inputs, manifest, "codex",
                                     project_root=self.project, workspace=self.workspace)
        with shared.capsule(payload) as captured:
            canonical_bytes = captured.consume()
            source.write_text("source after materialization")
            legacy_status, _, _ = consumer.consume(canonical_bytes, "legacy", self.project)
            self.assertEqual(legacy_status, 0)
            (self.bin / "codex").unlink()
            (self.bin / "codex").symlink_to(FIXTURES / "ctx06c-provider-stub.sh")
            with test_backend.admit_test_only(self.project) as admission:
                if admission.status != "available":
                    self.assertEqual(admission.reason, "native-backend-unavailable")
                    return
                state = admission.scratch / "fixture-state"
                environment = {**os.environ, "CTX06C_STATE_DIR": str(state)}
                completed = admission.invoke([sys.executable, str(REPO / "tests/context-shadow-consumer-test-only.py"),
                    str(self.project)], input_bytes=canonical_bytes, environment=environment, cwd=self.project)
                self.assertEqual(completed.returncode, 0, completed.stderr.decode())
                self.assertEqual((state / "count").read_text().strip(), "2")
                for ordinal, model in ((1, "fixture-economy"), (2, "fixture-full")):
                    prompt = (state / f"prompt.{ordinal}").read_text()
                    self.assertIn(original, prompt)
                    self.assertIn(shared.digest(shared.canonical(shared.validate(payload)["target"])), prompt)
                    self.assertNotIn("source after materialization", prompt)
                    self.assertEqual((state / f"model.{ordinal}").read_text().strip(), model)
        identity = shared.validate(payload)["identity"]
        record = json.loads((self.project / ".mana/runtime/metrics" / identity["shadowProducerId"] / "shared-input-consumption-v1.json").read_bytes())
        self.assertEqual(record["packetDigest"], shared.digest(canonical_bytes))
        self.assertEqual(record["digests"], shared.validate(payload)["digests"])
        legacy_record = json.loads((self.project / ".mana/runtime/metrics" / identity["legacyProducerId"] / "shared-input-consumption-v1.json").read_bytes())
        self.assertEqual(legacy_record["packetDigest"], record["packetDigest"])
        self.assertEqual(legacy_record["digests"], record["digests"])

    def test_completed_run_reuses_committed_legacy_output_without_a_second_call(self):
        payload = self.packet(comparison="execution-r1b-reuse")
        done = live.backend.ProcessResult(0, self.semantic(payload), b"")
        with mock.patch.object(live.backend, "execute_supervised", return_value=done) as invoke:
            first = live.run_shared(str(self.project), payload)
            second = live.run_shared(str(self.project), payload)
        self.assertEqual(first[0::2], (0, self.semantic(payload)))
        self.assertEqual(second[0::2], (0, self.semantic(payload)))
        self.assertEqual(invoke.call_count, 1)
        identity = shared.validate(payload)["identity"]
        head = json.loads((self.project / ".mana/runtime/shadows" / identity["comparisonExecutionId"] /
                           "live-shadow-head-v1.json").read_bytes())
        self.assertEqual(head["stage"], "completed")
        self.assertTrue(head["bundleId"].startswith("B-"))

    def test_receipt_before_head_recovers_without_replaying_legacy(self):
        payload = self.packet(comparison="execution-r1b-legacy-receipt")
        done = live.backend.ProcessResult(0, self.semantic(payload), b"")
        os.environ["MANA_CTX09C_FAULT"] = "after-legacy-receipt-commit"
        try:
            with mock.patch.object(live.backend, "execute_supervised", return_value=done) as invoke:
                with self.assertRaises(live.FaultInjected):
                    live.run_shared(str(self.project), payload)
                os.environ.pop("MANA_CTX09C_FAULT")
                status, result, output, _ = live.run_shared(str(self.project), payload)
            self.assertEqual((status, output), (0, self.semantic(payload)))
            self.assertEqual(invoke.call_count, 1)
            self.assertEqual(result["transactionStage"], "completed")
        finally:
            os.environ.pop("MANA_CTX09C_FAULT", None)

    def test_r1b_fault_boundaries_never_replay_an_ambiguous_legacy_effect(self):
        # Before process start a retry is safe; after an intent/process exit,
        # recovery must either use the receipt or require manual recovery.
        for point, expected_status, expected_calls in (
                ("after-input-materialization", 0, 1),
                ("after-legacy-process-exit", 2, 1),
                ("before-legacy-receipt-commit", 0, 1),
                ("after-legacy-receipt-commit", 0, 1)):
            payload = self.packet(comparison="execution-r1b-fault-" + point.replace("-", ""))
            done = live.backend.ProcessResult(0, self.semantic(payload), b"")
            os.environ["MANA_CTX09C_FAULT"] = point
            try:
                with self.subTest(point=point), mock.patch.object(live.backend, "execute_supervised", return_value=done) as invoke:
                    with self.assertRaises(live.FaultInjected):
                        live.run_shared(str(self.project), payload)
                    os.environ.pop("MANA_CTX09C_FAULT")
                    status, _, output, _ = live.run_shared(str(self.project), payload)
                    self.assertEqual(status, expected_status)
                    self.assertEqual(invoke.call_count, expected_calls)
                    if expected_status == 0:
                        self.assertEqual(output, self.semantic(payload))
            finally:
                os.environ.pop("MANA_CTX09C_FAULT", None)

    def test_supervisor_times_out_term_ignoring_group(self):
        command = [sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"]
        with mock.patch.dict(os.environ, {"MANA_CTX09C_SHADOW_TIMEOUT_SECONDS": "1", "MANA_CTX09C_KILL_GRACE_SECONDS": "1"}, clear=False):
            completed = live.backend.execute_supervised(command, input_bytes=b"", environment=os.environ.copy(),
                                                         cwd=self.project, timeout_name="MANA_CTX09C_SHADOW_TIMEOUT_SECONDS")
        self.assertEqual(completed.returncode, 124)
        self.assertTrue(completed.timed_out)

    def test_supervisor_reaps_child_and_maps_interrupt_statuses(self):
        child_pid = self.base / "shadow child pid"
        code = ("import pathlib,subprocess,sys,time\n"
                "child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'])\n"
                f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid))\n"
                "time.sleep(30)\n")
        with mock.patch.dict(os.environ, {"MANA_CTX09C_SHADOW_TIMEOUT_SECONDS": "1", "MANA_CTX09C_KILL_GRACE_SECONDS": "1"}, clear=False):
            completed = live.backend.execute_supervised([sys.executable, "-c", code], input_bytes=b"",
                                                         environment=os.environ.copy(), cwd=self.project,
                                                         timeout_name="MANA_CTX09C_SHADOW_TIMEOUT_SECONDS")
        self.assertEqual(completed.returncode, 124)
        # A just-killed orphan can briefly be a kernel zombie while adopted by
        # init; it cannot execute or emit output. The supervisor has already
        # killed the entire session before returning 124.
        self.assertTrue(child_pid.is_file())
        for signal_name, expected in (("SIGINT", 130), ("SIGTERM", 143)):
            code = f"import os,signal; os.kill(os.getpid(), signal.{signal_name})"
            completed = live.backend.execute_supervised([sys.executable, "-c", code], input_bytes=b"",
                                                         environment=os.environ.copy(), cwd=self.project,
                                                         timeout_name="MANA_CTX09C_SHADOW_TIMEOUT_SECONDS")
            self.assertEqual(completed.returncode, expected)


if __name__ == "__main__":
    unittest.main()
