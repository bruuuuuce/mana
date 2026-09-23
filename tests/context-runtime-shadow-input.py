#!/usr/bin/env python3
"""R1A local regressions for canonical input, argv and isolated identities."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ctx09c_shared_input", REPO / "scripts/lib/context-shadow-input.py")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
backend = shared.load("ctx09c_native_backend", "context-shadow-backend.py")


class SharedInput(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        self.workspace = ".mana/sessions/ctx09c-input-workspace"
        path = self.project / self.workspace
        path.mkdir(mode=0o700, parents=True)
        (self.project / ".mana").chmod(0o700)
        (self.project / ".mana/sessions").chmod(0o700)
        (path / "manifest.yaml").write_text(
            'workspace_type: "session"\nworkspace_id: "ctx09c-input-workspace"\n')

    def tearDown(self):
        self.temporary.cleanup()

    def packet(self, raw=b"materialized input", evidence=()):
        manifest = shared.runtime.compile_context_manifest(REPO, "requested-pr-review", "execution-r1a-input")
        return shared.materialize("execution-r1a-input", "requested-pr-review", {"prNumber": 7},
                                  raw, manifest, "codex", evidence=evidence,
                                  project_root=self.project, workspace=self.workspace)

    def test_argv_element_by_element(self):
        argv = ["/framework with spaces/run-profile.sh", "execution-r1a-input", "--project-root",
                "/project with spaces", "--static-signal", "first", "--static-signal", "second",
                "--value", "", "quotes '\" and $(no-execution)", "line\nnext", "--"]
        completed = subprocess.run([sys.executable, str(REPO / "scripts/lib/context-shadow-input.py"),
                                    "argv", *argv], check=True, capture_output=True)
        actual = json.loads(completed.stdout)
        self.assertEqual(len(actual), len(argv))
        for index, expected in enumerate(argv):
            with self.subTest(index=index):
                self.assertEqual(actual[index], expected)

    def test_both_consumers_read_captured_bytes_after_source_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source with spaces"
            source.write_bytes(b"original sensitive input")
            payload = self.packet(source.read_bytes(), [("E-" + "a" * 64, b"authorized evidence")])
            with shared.capsule(payload) as capsule:
                source.write_bytes(b"mutated source")
                legacy = capsule.consume()
                shadow = capsule.consume()
                self.assertEqual(legacy, shadow)
                left, right = shared.validate(legacy), shared.validate(shadow)
                self.assertEqual(shared.unblob(left["input"]), b"original sensitive input")
                self.assertEqual(left["digests"]["input"], right["digests"]["input"])
                self.assertEqual(left["digests"]["policy"], right["digests"]["policy"])
                self.assertEqual(shared.unblob(right["evidenceSnapshot"][0]["payload"]), b"authorized evidence")
                self.assertEqual(capsule.path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(capsule.path.parent.stat().st_mode & 0o777, 0o700)
                path = capsule.path
            self.assertFalse(path.exists())
            self.assertFalse(path.parent.exists())

    def test_cleanup_on_runner_failure(self):
        with self.assertRaises(RuntimeError):
            with shared.capsule(self.packet()) as capsule:
                path = capsule.path
                raise RuntimeError("local runner failure")
        self.assertFalse(path.exists())

    def test_mutated_capsule_is_rejected(self):
        with shared.capsule(self.packet()) as capsule:
            capsule.path.write_bytes(b"replacement")
            with self.assertRaises(shared.Error):
                capsule.consume()

    def test_read_access_time_updates_do_not_reject_canonical_bytes(self):
        payload = self.packet()
        with shared.capsule(payload) as capsule:
            real_fstat = os.fstat
            reads = 0
            def fstat(fd):
                nonlocal reads
                metadata = real_fstat(fd)
                if fd != capsule.fd:
                    return metadata
                reads += 1
                fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
                return SimpleNamespace(**{key: getattr(metadata, key) for key in fields}, st_atime_ns=reads)
            with mock.patch.object(shared.os, "fstat", side_effect=fstat):
                self.assertEqual(capsule.consume(), payload)

    def test_rebound_capsule_is_rejected(self):
        payload = self.packet()
        with shared.capsule(payload) as capsule:
            capsule.path.rename(capsule.path.with_suffix(".old"))
            capsule.path.write_bytes(payload)
            capsule.path.chmod(0o600)
            with self.assertRaises(shared.Error):
                capsule.consume()

    def test_private_permissions_are_required(self):
        with shared.capsule(self.packet()) as capsule:
            capsule.path.chmod(0o644)
            with self.assertRaises(shared.Error):
                capsule.consume()

    def test_input_and_policy_tampering_rejected(self):
        value = shared.validate(self.packet())
        value["input"]["sha256"] = "b" * 64
        with self.assertRaises(shared.Error):
            shared.validate(shared.canonical(value))
        value = shared.validate(self.packet())
        value["policyDecision"]["effectiveMode"] = "compact"
        with self.assertRaises(shared.Error):
            shared.validate(shared.canonical(value))

    def test_duplicate_fields_and_noncanonical_json_rejected(self):
        with self.assertRaises(shared.Error):
            shared.validate(b'{"schemaVersion":1,"schemaVersion":2}')
        value = shared.validate(self.packet())
        with self.assertRaises(shared.Error):
            shared.validate(json.dumps(value, indent=2).encode())

    def test_namespaces_and_invocation_identities_distinct(self):
        identity = shared.identities("execution-r1a-input")
        for kind in ("ProducerId", "RunRoot", "MetricsRoot", "Lock", "InvocationId"):
            self.assertNotEqual(identity["legacy" + kind], identity["shadow" + kind])
        self.assertTrue(identity["shadowRunRoot"].startswith(".mana/runtime/shadows/"))
        self.assertTrue(identity["shadowMetricsRoot"].startswith(".mana/runtime/shadows/"))
        self.assertNotIn(".mana/runtime/runs/execution-r1a-input", identity.values())

    def test_persistable_metadata_excludes_sensitive_payloads(self):
        payload = self.packet(b"credential-secret", [("E-" + "a" * 64, b"raw-evidence-secret")])
        bounded = shared.canonical(shared.metadata(payload))
        self.assertNotIn(b"credential-secret", bounded)
        self.assertNotIn(b"raw-evidence-secret", bounded)
        self.assertNotIn(b"policySnapshot", bounded)
        self.assertNotIn(b"contextManifest", bounded)
        self.assertLess(len(bounded), 4096)

    def test_backend_absent_has_no_invocation(self):
        with mock.patch.object(backend, "NATIVE", Path("/nonexistent-ctx09c-backend")), \
                mock.patch.object(backend.subprocess, "run") as invocation:
            with backend.admit(Path("/unused-run"), Path("/unused-metrics")) as admission:
                self.assertEqual(admission.status, "unavailable")
                with self.assertRaises(RuntimeError):
                    admission.invoke(["provider-stub"], input_bytes=b"", environment={}, cwd="/tmp")
            invocation.assert_not_called()

    def test_nested_denial_and_unknown_proof_have_no_provider_invocation(self):
        real_temporary_directory = tempfile.TemporaryDirectory
        with real_temporary_directory(prefix="ctx09c-darwin-emulation-") as emulated_private_tmp:
            fixture_root = Path(emulated_private_tmp).resolve()
            self.assertFalse(fixture_root.is_relative_to(REPO))
            created_directories = []

            def temporary_directory(*args, **kwargs):
                call_kwargs = dict(kwargs)
                if call_kwargs.get("dir") == "/private/tmp":
                    call_kwargs["dir"] = fixture_root
                context = real_temporary_directory(*args, **call_kwargs)
                created_directories.append(Path(context.name).resolve())
                return context

            with mock.patch.object(backend.tempfile, "TemporaryDirectory",
                                   side_effect=temporary_directory):
                for result in (subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0),
                               subprocess.TimeoutExpired("native-probe", 10), PermissionError()):
                    native = mock.MagicMock(spec=Path)
                    native.is_file.return_value = True
                    native.is_symlink.return_value = False
                    native.__str__.return_value = "/usr/bin/sandbox-exec"
                    case_start = len(created_directories)
                    with self.subTest(result=type(result).__name__), \
                            mock.patch.object(backend.sys, "platform", "darwin"), \
                            mock.patch.object(backend, "NATIVE", native), \
                            mock.patch.object(backend, "safe_tree", return_value=True), \
                            mock.patch.object(backend.subprocess, "run") as invocation:
                        if isinstance(result, BaseException):
                            invocation.side_effect = result
                        else:
                            invocation.return_value = result
                        with backend.admit(Path("/unused-run"), Path("/unused-metrics")) as admission:
                            self.assertEqual(admission.status, "unavailable")
                            with self.assertRaises(RuntimeError):
                                admission.invoke(["provider-stub"], input_bytes=b"", environment={}, cwd="/tmp")
                        self.assertEqual(invocation.call_count, 1)  # native proof only
                        self.assertNotIn("provider-stub", invocation.call_args.args[0])
                    case_directories = created_directories[case_start:]
                    self.assertEqual(len(case_directories), 2)  # scratch and native proof
                    for directory in case_directories:
                        self.assertTrue(directory.is_relative_to(fixture_root))
                        self.assertFalse(directory.exists())

            self.assertTrue(all(directory.is_relative_to(fixture_root)
                                for directory in created_directories))
            self.assertTrue(all(not directory.exists() for directory in created_directories))
        self.assertFalse(fixture_root.exists())

    def test_native_containment_when_backend_is_available(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp" if sys.platform == "darwin" else "/tmp") as temporary:
            base = Path(temporary).resolve()
            runs, metrics = base / "shadow-runs", base / "shadow-metrics"
            runs.mkdir(mode=0o700)
            metrics.mkdir(mode=0o700)
            outside_read = base / "outside-read"
            outside_read.write_bytes(b"outside installed code")
            protected = base / "project/.mana/runtime/runs/legacy-HEAD"
            protected.parent.mkdir(parents=True)
            protected.write_bytes(b"legacy authority")
            external_write = base / "external-write"
            with backend.admit(runs, metrics) as admission:
                if admission.status != "available":
                    self.skipTest("native containment unavailable in this sandbox")
                code = ("import pathlib,sys\n"
                        "assert sys.stdin.buffer.read()==b'canonical packet bytes'\n"
                        "for path in sys.argv[2:4]:\n"
                        "    try: pathlib.Path(path).read_bytes()\n"
                        "    except PermissionError: pass\n"
                        "    else: sys.exit(1)\n"
                        "for path in sys.argv[3:5]:\n"
                        "    try: pathlib.Path(path).write_bytes(b'forbidden')\n"
                        "    except PermissionError: pass\n"
                        "    else: sys.exit(2)\n"
                        "pathlib.Path(sys.argv[1]).write_bytes(b'shadow metric')\n")
                completed = admission.invoke([sys.executable, "-c", code, str(metrics / "numeric.json"),
                                              str(outside_read), str(protected), str(external_write)],
                                             input_bytes=b"canonical packet bytes",
                                             environment=os.environ, cwd=base)
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(outside_read.read_bytes(), b"outside installed code")
                self.assertEqual(protected.read_bytes(), b"legacy authority")
                self.assertFalse(external_write.exists())
                self.assertEqual((metrics / "numeric.json").read_bytes(), b"shadow metric")


if __name__ == "__main__":
    unittest.main()
