#!/usr/bin/env python3
"""CTX-09C-R2D privacy and non-cooperative process regressions.

The hostile fixture performs real filesystem, socket, service-discovery and
environment reads.  If macOS refuses a nested sandbox, that is an unavailable
backend; the test deliberately does not run the fixture permissively.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ctx09c_r2d_live", REPO / "scripts/context-runtime-live-shadow.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)
shared = live.shared
test_backend = importlib.util.module_from_spec(importlib.util.spec_from_file_location("r2d_test_backend", REPO / "tests/context-shadow-backend-test-harness.py"))
test_backend.__spec__.loader.exec_module(test_backend)
BASELINE = json.loads((REPO / "tests/fixtures/context-runtime/comparison/baseline.json").read_bytes())


class R2D(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp" if sys.platform == "darwin" else "/tmp")
        self.base = Path(self.temp.name)
        self.project = self.base / "project"
        self.project.mkdir(mode=0o700)
        self.workspace = ".mana/sessions/ctx09c-r2d-workspace"
        workspace = self.project / self.workspace
        workspace.mkdir(mode=0o700, parents=True)
        (self.project / ".mana").chmod(0o700)
        (self.project / ".mana/sessions").chmod(0o700)
        (workspace / "manifest.yaml").write_text(
            'workspace_type: "session"\nworkspace_id: "ctx09c-r2d-workspace"\n')
        self.bin = self.base / "bin"
        self.bin.mkdir()
        (self.bin / "codex").symlink_to(REPO / "tests/fixtures/context-runtime/ctx09a-provider-stub.py")
        self.env = mock.patch.dict(os.environ, {"PATH": str(self.bin) + ":" + os.environ["PATH"],
            "CTX09_ACTION": "complete", "PYTHONDONTWRITEBYTECODE": "1"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def packet(self, execution):
        manifest = shared.runtime.compile_context_manifest(REPO, "jira-state-audit", execution)
        inputs = shared.canonical({"legacyPrompt": "private prompt", "legacyArgv": ["exec"],
            "economyModel": "fixture-economy", "fullModel": "fixture-full", "objective": "private objective",
            "pipelineSnapshot": None})
        return shared.materialize(execution, "jira-state-audit", {"workItem": "LOCAL-R2D"}, inputs, manifest,
                                  "codex", project_root=self.project, workspace=self.workspace)

    def semantic(self, payload):
        value = json.loads(json.dumps(BASELINE))
        packet = shared.validate(payload)
        value["profileId"] = packet["profileId"]
        value["targetKey"] = shared.digest(shared.canonical(packet["target"]))
        return live.canonical(value)

    def public_bytes(self):
        return b"".join(path.read_bytes() for path in self.project.rglob("*")
                        if path.is_file() and "recovery" not in path.parts)

    def test_host_environment_is_closed_and_its_provenance_has_no_values(self):
        canary = "CTX09C_ENVIRONMENT_CANARY"
        env = live.backend.host_environment({
            "PATH": "/safe/provider", "LANG": "C", canary: "do-not-export",
            "AWS_SECRET_ACCESS_KEY": "credential", "Authorization": "Bearer token",
            "MANA_ARBITRARY_DEBUG": "enabled", "DEBUG": "yes", "COOKIE": "cookie",
            "CTX09C_DEBUG": "user-debug", "CTX09_ACTION": "complete"})
        self.assertEqual(env["PATH"], "/safe/provider")
        self.assertEqual(env["CTX09_ACTION"], "complete")
        for forbidden in (canary, "AWS_SECRET_ACCESS_KEY", "Authorization", "MANA_ARBITRARY_DEBUG",
                          "DEBUG", "COOKIE", "CTX09C_DEBUG"):
            self.assertNotIn(forbidden, env)
        provenance = live.backend.environment_provenance()
        encoded = live.canonical(provenance)
        self.assertNotIn(b"credential", encoded)
        self.assertNotIn(b"/safe/provider", encoded)
        self.assertIn(b"ctx09c-host-allowlist-v1", encoded)

    def test_legacy_receives_allowlist_not_callers_environment(self):
        payload = self.packet("execution-r2d-env")
        canary = "CTX09C_ENVIRONMENT_CANARY"
        with mock.patch.dict(os.environ, {canary: "secret", "MANA_UNAPPROVED": "secret", "DEBUG": "1"}, clear=False), \
                mock.patch.object(live.backend, "execute_supervised", return_value=
                    live.backend.ProcessResult(0, self.semantic(payload), b"")) as invoke:
            status, result, _, _ = live.run_shared(str(self.project), payload)
        self.assertEqual(status, 0)
        received = invoke.call_args.kwargs["environment"]
        self.assertNotIn(canary, received)
        self.assertNotIn("MANA_UNAPPROVED", received)
        self.assertNotIn("DEBUG", received)
        self.assertEqual(result["environmentProvenance"]["policy"], "ctx09c-host-allowlist-v1")

    def test_all_sensitive_canaries_are_excluded_from_every_public_projection(self):
        names = ("PROMPT", "SOURCE_RAW", "CREDENTIAL", "COOKIE", "TOKEN", "ENVIRONMENT",
                 "RESPONSE_RAW", "REASONING", "PROVIDER_STDERR", "DIFF", "RAW_EVIDENCE")
        for name in names:
            payload = self.packet("execution-r2d-privacy-" + name.lower())
            canary = ("CTX09C_" + name + "_CANARY").encode()
            candidate = self.semantic(payload).replace(b'"blocked"', b'"' + canary + b'"', 1)
            with self.subTest(name=name), mock.patch.object(live.backend, "execute_supervised", return_value=
                    live.backend.ProcessResult(0, candidate, b"CTX09C_PROVIDER_STDERR_CANARY")):
                status, result, output, stderr = live.run_shared(str(self.project), payload)
            self.assertEqual((status, output, stderr), (0, candidate, b"CTX09C_PROVIDER_STDERR_CANARY"))
            self.assertEqual(result["validation"]["legacy"]["errorCategory"], "privacy-invalid")
            self.assertEqual(result["artifacts"], {})
            self.assertNotIn(canary, self.public_bytes())
            self.assertNotIn(b"CTX09C_PROVIDER_STDERR_CANARY", self.public_bytes())

    def test_test_only_backend_real_hostile_process_or_unavailable_fail_closed(self):
        outside = self.base / "outside"
        outside.mkdir()
        legacy = outside / "legacy-head"
        legacy.write_bytes(b"LEGACY_HEAD_CANARY")
        artifact = outside / "artifact.json"
        artifact.write_bytes(b"ORIGINAL")
        with test_backend.admit_test_only() as admission:
            allowed = admission.scratch / "input"
            allowed.write_bytes(b"SHARED_INPUT")
            paths = {"publish": str(outside / "publish"), "externalWrite": str(outside / "external-write"),
                     "stateMutation": str(outside / "state.json"), "approvalMutation": str(outside / "approval.json"),
                     "artifactReplacement": str(artifact), "allowedInput": str(allowed),
                     "environmentCanary": "CTX09C_ENVIRONMENT_CANARY", "reads": {"legacyHead": str(legacy)}}
            if admission.status != "available":
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    admission.invoke([sys.executable, str(REPO / "tests/context-shadow-backend-test-only.py")],
                                     input_bytes=json.dumps(paths).encode(),
                                     environment={**os.environ, "CTX09C_ENVIRONMENT_CANARY": "secret"}, cwd=self.project)
                self.assertEqual(artifact.read_bytes(), b"ORIGINAL")
                self.assertFalse((outside / "external-write").exists())
                return
            completed = admission.invoke([sys.executable, str(REPO / "tests/context-shadow-backend-test-only.py")],
                                         input_bytes=json.dumps(paths).encode(),
                                         environment={**os.environ, "CTX09C_ENVIRONMENT_CANARY": "secret"}, cwd=self.project)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        observed = json.loads(completed.stdout)
        self.assertTrue(all(observed.values()), observed)
        self.assertEqual(artifact.read_bytes(), b"ORIGINAL")
        for name in ("publish", "external-write", "state.json", "approval.json"):
            self.assertFalse((outside / name).exists())

    def test_status_contract_distinguishes_timeout_interrupt_unavailable_invalid_and_indeterminate(self):
        self.assertEqual(live.backend.shadow_status(live.backend.ProcessResult(124, b"", b"", timed_out=True)), "timed_out")
        self.assertEqual(live.backend.shadow_status(live.backend.ProcessResult(130, b"", b"", interrupted_signal=2)), "interrupted")
        self.assertEqual(live.backend.shadow_status(live.backend.ProcessResult(2, b"", b"")), "failed")
        payload = self.packet("execution-r2d-invalid")
        validation, structured = live.validate_artifact(b"{malformed", shared.validate(payload), "v2")
        self.assertIsNone(structured)
        self.assertEqual((validation["status"], validation["errorCategory"]), ("invalid", "schema-invalid"))
        unavailable = {"status": "unavailable", "reason": "backend-unavailable"}
        indeterminate = {"status": "indeterminate", "reason": "offline-comparison-rejected"}
        self.assertNotEqual(unavailable["status"], indeterminate["status"])


if __name__ == "__main__":
    unittest.main()
