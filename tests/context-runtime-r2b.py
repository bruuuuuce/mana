#!/usr/bin/env python3
"""Exact legacy delivery, fail-closed attestation and real caller convergence."""
import base64
import importlib.util
import json
import os
import stat
import subprocess
import sys
import unittest
from contextlib import contextmanager
from unittest import mock

spec = importlib.util.spec_from_file_location("r2b_support", __file__.replace("context-runtime-r2b.py", "context-runtime-live-shadow.py"))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
live, shared, REPO = support.live, support.shared, support.REPO
test_backend = importlib.util.module_from_spec(importlib.util.spec_from_file_location("r2b_test_backend", REPO / "tests/context-shadow-backend-test-harness.py"))
test_backend.__spec__.loader.exec_module(test_backend)


class ExactLegacy(unittest.TestCase):
    setUp = support.LiveShadow.setUp
    tearDown = support.LiveShadow.tearDown
    packet = support.LiveShadow.packet
    semantic = support.LiveShadow.semantic

    def exact(self, result):
        return result[0], result[2], result[3]

    def base_for(self, payload):
        return self.project / live.SHADOW_NAMESPACE / shared.validate(payload)["identity"]["comparisonExecutionId"]

    def assert_replay(self, payload, status, stdout, stderr):
        done = live.backend.ProcessResult(status, stdout, stderr)
        with mock.patch.object(live.backend, "execute_supervised", return_value=done) as invoke:
            first = live.run_shared(str(self.project), payload)
            second = live.run_shared(str(self.project), payload)
        self.assertEqual(self.exact(first), (status, stdout, stderr))
        self.assertEqual(self.exact(second), self.exact(first))
        self.assertEqual(invoke.call_count, 1)
        return first

    def test_noncanonical_projection_and_exact_stdout_stderr_replay(self):
        payload = self.packet()
        stdout = b" \n" + json.dumps(json.loads(self.semantic(payload)), indent=3).encode() + b"  \n\t"
        stderr = b"diagnostic  \n\x00\xff\x80"
        result = self.assert_replay(payload, 0, stdout, stderr)
        projection = (self.project / result[1]["artifacts"]["legacy"]["path"]).read_bytes()
        self.assertEqual(projection, self.semantic(payload))
        self.assertNotEqual(projection, stdout)
        self.assertNotIn("legacyOutputDigest", result[1])

    def test_arbitrary_bytes_exit_zero_and_exit_23_are_authoritative(self):
        for status in (0, 23):
            with self.subTest(status=status):
                payload = self.packet(comparison=f"execution-exact-{status}")
                result = self.assert_replay(payload, status, b"  { raw }\n\x00\xff\x80 \t", b"stderr \x00\xfe \n")
                self.assertEqual(result[1]["legacy"]["exitStatus"], status)
                self.assertNotEqual(result[1]["shadowStatus"], "completed")

    def test_sensitive_outcome_is_private_and_excluded_from_public_artifacts(self):
        payload = self.packet()
        stdout, stderr = b"CTX09C_CREDENTIAL_CANARY\xff", b"CTX09C_STDERR_CANARY\x00"
        result = self.assert_replay(payload, 0, stdout, stderr)
        base = self.base_for(payload)
        recovery = base / "recovery"
        self.assertEqual(stat.S_IMODE(recovery.stat().st_mode), 0o700)
        for path in recovery.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        manifest = json.loads((recovery / "legacy-outcome-v1.json").read_bytes())
        self.assertEqual(set(manifest), {"stdout", "stderr", "exitStatus", "terminationKind", "producerInvocationIdentity"})
        self.assertEqual(manifest["terminationKind"], "exited")
        public = live.canonical(result[1]) + (base / "live-shadow-result-v1.json").read_bytes() + (base / "usage-comparison-v1.json").read_bytes()
        for forbidden in (stdout, stderr, manifest["stdout"]["sha256"].encode(), manifest["stderr"]["sha256"].encode(), b"legacy-outcome", b"recovery/"):
            self.assertNotIn(forbidden, public)
        ignored = subprocess.run(["git", "check-ignore", "--no-index", ".mana/runtime/shadows/example/recovery/stdout.bin"], cwd=REPO, capture_output=True)
        self.assertEqual(ignored.returncode, 0)
        tracked = subprocess.run(["git", "ls-files", ".mana/runtime/shadows"], cwd=REPO, capture_output=True, check=True)
        self.assertEqual(tracked.stdout, b"")

    @unittest.skipUnless(sys.platform == "darwin", "native macOS boundary")
    def test_native_shadow_cannot_read_actual_sensitive_outcome_or_private_receipt(self):
        payload = self.packet()
        self.assert_replay(payload, 0, b"CTX09C_CREDENTIAL_CANARY", b"CTX09C_STDERR_CANARY")
        base = self.base_for(payload)
        shadow = self.project / shared.validate(payload)["identity"]["shadowRunRoot"]
        with live.mode.HostRoot(str(self.project)) as root:
            with live.private_directory(root, list(shadow.relative_to(self.project).parts)):
                pass
            # Keep the run nonempty while this host root leaves its context.
            (shadow / "input").write_bytes(b"SHARED_INPUT")
        reads = {name: str(base / relative) for name, relative in (
            ("stdout", "recovery/stdout.bin"), ("stderr", "recovery/stderr.bin"),
            ("outcome", "recovery/legacy-outcome-v1.json"),
            ("receipt", "records/legacy-receipt-v1.json"), ("legacyHead", live.HEAD_NAME))}
        with test_backend.admit_test_only(shadow) as fixture:
            paths = {"reads": reads, "allowedInput": str(shadow / "input"),
                     "publish": str(self.base / "publish"), "externalWrite": str(self.base / "external")}
            if fixture.status != "available":
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    fixture.invoke([sys.executable, str(REPO / "tests/context-shadow-backend-test-only.py")],
                                   input_bytes=json.dumps(paths).encode(), environment=os.environ.copy(), cwd=shadow)
                return
            result = fixture.invoke([sys.executable, str(REPO / "tests/context-shadow-backend-test-only.py")],
                input_bytes=json.dumps(paths).encode(), environment=os.environ.copy(), cwd=shadow)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(json.loads(result.stdout).values()))

    def test_legacy_consumer_cli_forwards_both_original_streams(self):
        payload = self.packet()
        script = REPO / "scripts/lib/context-shadow-consumer.py"
        driver = ("import runpy,subprocess,sys\nfrom unittest import mock\n"
                  "done=subprocess.CompletedProcess([],23,b'  stdout\\xff\\x00 ',b'stderr\\xfe\\n')\n"
                  "with mock.patch.object(subprocess,'run',return_value=done):\n"
                  f"    runpy.run_path({str(script)!r},run_name='__main__')\n")
        result = subprocess.run([sys.executable, "-c", driver, "legacy", "--project-root", str(self.project)],
                                input=payload, capture_output=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (23, b"  stdout\xff\x00 ", b"stderr\xfe\n"))

    def test_postcommit_runtimeerror_and_cleanup_failure_preserve_both_statuses(self):
        for status in (0, 23):
            for point in ("after-legacy-commit", "before-shadow", "final-cleanup"):
                payload = self.packet(comparison=f"execution-{status}-{point}")
                done = live.backend.ProcessResult(status, b" legacy \xff \n", b"diagnostic\x00\xfe")
                def failing_fault(actual):
                    if actual == point:
                        raise RuntimeError("sensitive exception must not reach caller")
                with self.subTest(status=status, point=point), mock.patch.object(live.backend, "execute_supervised", return_value=done) as invoke, mock.patch.object(live, "fault", side_effect=failing_fault):
                    first = live.run_shared(str(self.project), payload)
                with mock.patch.object(live.backend, "execute_supervised") as retry:
                    second = live.run_shared(str(self.project), payload)
                self.assertEqual(self.exact(first), (status, done.stdout, done.stderr))
                self.assertEqual(self.exact(second), self.exact(first))
                self.assertEqual(invoke.call_count, 1)
                retry.assert_not_called()

    def test_outer_capsule_cleanup_and_recovery_failure_use_attested_cache(self):
        payload = self.packet()
        original = live.session
        @contextmanager
        def broken_capsule(*args):
            with original(*args) as captured:
                yield captured
            raise RuntimeError("cleanup failed")
        done = live.backend.ProcessResult(23, b"not JSON  \xff", b"stderr \x00")
        with mock.patch.object(live.backend, "execute_supervised", return_value=done), mock.patch.object(live, "session", broken_capsule):
            first = live.run_shared(str(self.project), payload)
        with mock.patch.object(live.backend, "execute_supervised") as invoke, mock.patch.object(live, "_result", side_effect=RuntimeError("recovery reporting failed")):
            recovered = live.run_shared(str(self.project), payload)
        invoke.assert_not_called()
        self.assertEqual(self.exact(first), (23, done.stdout, done.stderr))
        self.assertEqual(self.exact(recovered), self.exact(first))

    def test_exception_immediately_after_legacy_head_publication_preserves_delivery(self):
        payload = self.packet()
        original = live.Journal.commit
        def commit(journal, stage, **fields):
            state = original(journal, stage, **fields)
            if stage == "legacy_committed":
                raise RuntimeError("HEAD is published, host raises before return")
            return state
        done = live.backend.ProcessResult(23, b" original \xff", b"stderr\x00")
        with mock.patch.object(live.backend, "execute_supervised", return_value=done) as invoke, mock.patch.object(live.Journal, "commit", commit):
            result = live.run_shared(str(self.project), payload)
        with mock.patch.object(live.backend, "execute_supervised") as retry:
            replay = live.run_shared(str(self.project), payload)
        self.assertEqual(invoke.call_count, 1)
        retry.assert_not_called()
        self.assertEqual(self.exact(result), (23, done.stdout, done.stderr))
        self.assertEqual(self.exact(replay), self.exact(result))

    def test_post_replace_head_fsync_failure_preserves_published_legacy_outcome(self):
        payload = self.packet()
        original_cas, original_sync = live.Journal._cas_head, os.fsync
        def cas(journal, expected, state, bundle_binding):
            if state["stage"] != "legacy_committed":
                return original_cas(journal, expected, state, bundle_binding)
            def fsync(fd):
                if journal.current.get("stage") == "legacy_committed":
                    raise RuntimeError("HEAD replacement succeeded; host fsync failed")
                return original_sync(fd)
            with mock.patch.object(os, "fsync", side_effect=fsync):
                return original_cas(journal, expected, state, bundle_binding)
        done = live.backend.ProcessResult(23, b"exact \xff", b"stderr\x00")
        with mock.patch.object(live.backend, "execute_supervised", return_value=done) as invoke, mock.patch.object(live.Journal, "_cas_head", cas):
            result = live.run_shared(str(self.project), payload)
        with mock.patch.object(live.backend, "execute_supervised") as retry:
            replay = live.run_shared(str(self.project), payload)
        self.assertEqual(invoke.call_count, 1)
        retry.assert_not_called()
        self.assertEqual(self.exact(result), (23, done.stdout, done.stderr))
        self.assertEqual(self.exact(replay), self.exact(result))

    def test_transient_lock_creation_enoent_converges_before_legacy_effect(self):
        payload = self.packet()
        original_open, attempts = os.open, []
        secure_flags = live.mode.runtime._require_secure_dir_fd_support()
        def open_file(name, flags, *args, **kwargs):
            if name == "live-shadow.lock" and not attempts:
                attempts.append(name)
                raise FileNotFoundError("concurrent name creation")
            return original_open(name, flags, *args, **kwargs)
        done = live.backend.ProcessResult(23, b"stdout\xff", b"stderr\x00")
        # Replacing os.open for fault injection changes its membership in
        # os.supports_dir_fd; retain the already-proven platform primitives.
        with mock.patch.object(live.mode.runtime, "_require_secure_dir_fd_support", return_value=secure_flags), \
                mock.patch.object(live.shared.runtime, "_require_secure_dir_fd_support", return_value=secure_flags), \
                mock.patch.object(os, "open", side_effect=open_file), \
                mock.patch.object(live.backend, "execute_supervised", return_value=done) as invoke:
            first = live.run_shared(str(self.project), payload)
            second = live.run_shared(str(self.project), payload)
        self.assertEqual(attempts, ["live-shadow.lock"])
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(self.exact(first), (23, done.stdout, done.stderr))
        self.assertEqual(self.exact(second), self.exact(first))

    def test_exact_streams_do_not_inherit_comparison_size_limit(self):
        payload = self.packet()
        self.assert_replay(payload, 0, b"\xff" * (live.mode.MAX_ARTIFACT_BYTES + 1), b"stderr\x00")

    def test_signal_timeout_and_interrupt_termination_are_attested(self):
        for kind, status in (("exited", 23), ("signaled", 143), ("timed_out", 124), ("interrupted", 130)):
            payload = self.packet(comparison="execution-termination-" + kind)
            done = live.backend.ProcessResult(status, b"stdout", b"stderr", termination_kind=kind)
            with self.subTest(kind=kind), mock.patch.object(live.backend, "execute_supervised", return_value=done):
                result = live.run_shared(str(self.project), payload)
                replay = live.run_shared(str(self.project), payload)
            manifest = json.loads((self.base_for(payload) / "recovery/legacy-outcome-v1.json").read_bytes())
            self.assertEqual(manifest["terminationKind"], kind)
            self.assertEqual(self.exact(result), (status, b"stdout", b"stderr"))
            self.assertEqual(self.exact(replay), self.exact(result))

    def test_shadow_backend_usage_and_receipt_exceptions_are_advisory(self):
        for category in ("backend", "shadow", "usage", "receipt"):
            payload = self.packet(snapshot={}, comparison="execution-postcommit-" + category)
            done = live.backend.ProcessResult(0, b"noncanonical output \xff", b"stderr \x00")
            @contextmanager
            def admission(*args):
                yield live.backend.Admission("available", None)
            original_read = live.read_usage
            original_receipt = live.Journal.receipt
            def read(*args, **kwargs):
                if "execution-shadow-" in args[2]:
                    raise RuntimeError("usage failed")
                return original_read(*args, **kwargs)
            def receipt(journal, name):
                if name == "shadow-receipt-v1.json":
                    raise RuntimeError("receipt failed")
                return original_receipt(journal, name)
            patches = {
                "backend": mock.patch.object(live.backend, "admit", side_effect=RuntimeError("backend failed")),
                "shadow": mock.patch.object(live.backend.Admission, "invoke", side_effect=RuntimeError("shadow failed")),
                "usage": mock.patch.object(live, "read_usage", side_effect=read),
                "receipt": mock.patch.object(live.Journal, "receipt", receipt),
            }
            with self.subTest(category=category), mock.patch.object(live.backend, "execute_supervised", return_value=done), mock.patch.object(live.consumer, "declaration_from_snapshot"), mock.patch.object(live.consumer, "capabilities"), mock.patch.object(live.backend, "admit", side_effect=admission), patches[category]:
                result = live.run_shared(str(self.project), payload)
            self.assertEqual(self.exact(result), (0, done.stdout, done.stderr))
            with mock.patch.object(live.backend, "execute_supervised") as retry:
                replay = live.run_shared(str(self.project), payload)
            retry.assert_not_called()
            self.assertEqual(self.exact(replay), self.exact(result))

    def test_comparison_and_artifact_failure_after_commit_preserve_exact_delivery(self):
        for category in ("artifact", "comparison"):
            payload = self.packet(snapshot={}, comparison="execution-postcommit-" + category)
            stdout = b" \n" + self.semantic(payload) + b" \t"
            done = live.backend.ProcessResult(0, stdout, b"stderr\xff")
            @contextmanager
            def admission(*args):
                yield live.backend.Admission("available", None)
            def fault(point):
                if category == "artifact" and point == "before-shadow-artifact-commit":
                    raise RuntimeError("artifact failed")
            with self.subTest(category=category), mock.patch.object(live.backend, "execute_supervised", return_value=done), mock.patch.object(live.consumer, "declaration_from_snapshot"), mock.patch.object(live.consumer, "capabilities"), mock.patch.object(live.backend, "admit", side_effect=admission), mock.patch.object(live.backend.Admission, "invoke", return_value=done), mock.patch.object(live.comparison, "run", side_effect=RuntimeError("comparison failed")), mock.patch.object(live, "fault", side_effect=fault):
                result = live.run_shared(str(self.project), payload)
            self.assertEqual(self.exact(result), (0, stdout, done.stderr))

    def test_missing_corrupt_or_replaced_outcomes_and_receipts_require_manual_recovery(self):
        for target, mutation in (("stdout.bin", "corrupt"), ("stderr.bin", "missing"), ("legacy-outcome-v1.json", "missing"), ("legacy-outcome-v1.json", "corrupt"), ("stdout.bin", "replace-identical"), ("stdout.bin", "chmod"), ("legacy-receipt-v1.json", "missing"), ("legacy-receipt-v1.json", "replace-identical")):
            payload = self.packet(comparison="execution-tamper-" + target.replace(".", "") + "-" + mutation)
            self.assert_replay(payload, 23, b"exact stdout\xff", b"stderr\x00")
            base = self.base_for(payload)
            path = base / ("records" if target == "legacy-receipt-v1.json" else "recovery") / target
            if mutation == "missing":
                path.unlink()
            elif mutation == "corrupt":
                path.write_bytes(b"tampered")
            elif mutation == "chmod":
                path.chmod(0o644)
            else:
                replacement = path.with_name("replacement")
                replacement.write_bytes(path.read_bytes())
                replacement.chmod(0o600)
                replacement.replace(path)
            with self.subTest(target=target, mutation=mutation), mock.patch.object(live.backend, "execute_supervised") as invoke:
                for _ in range(2):
                    with self.assertRaises(live.ManualRecoveryRequired) as error:
                        live.run_shared(str(self.project), payload)
                    self.assertTrue(error.exception.manualRecoveryRequired)
            invoke.assert_not_called()
            head = json.loads((base / live.HEAD_NAME).read_bytes())
            # R2C rejects the complete invalid chain before any HEAD mutation.
            # Recovery is explicit in the exception; corrupted authority cannot
            # be turned into another allegedly attested journal transition.
            self.assertEqual(head["stage"], "completed")

    def cli_environment(self, stdout, stderr, status):
        (self.bin / "codex").unlink()
        (self.bin / "codex").symlink_to(REPO / "tests/fixtures/context-runtime/ctx09c-r2b-provider.py")
        return {**os.environ, "CTX09C_R2B_STDOUT": base64.b64encode(stdout).decode(),
                "CTX09C_R2B_STDERR": base64.b64encode(stderr).decode(), "CTX09C_R2B_EXIT": str(status),
                "CTX09C_R2B_COUNT": str(self.base / "count")}

    def cli(self):
        # Import-only test host launches one fixed raw-byte producer through
        # the real supervisor. The production CLI has no command selector.
        driver = ("import importlib.util,os,sys; "
                  f"s=importlib.util.spec_from_file_location('host', {str(REPO / 'scripts/context-runtime-live-shadow.py')!r}); "
                  "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); original=m.backend.execute_supervised; "
                  f"m.backend.execute_supervised=lambda argv,**kw: original([sys.executable,{str(REPO / 'tests/fixtures/context-runtime/ctx09c-r2b-provider.py')!r}],**kw); "
                  "m.fault=lambda point: os._exit(99) if point=='after-legacy-commit' and os.environ.get('CTX09C_R2B_CRASH')=='1' else None; "
                  "sys.exit(m.main())")
        return [sys.executable, "-c", driver, "--project-root", str(self.project), "--packet-stdin"]

    def test_two_real_concurrent_callers_and_cli_stderr_converge(self):
        for ordinal, status in enumerate((0, 23) * 8):
            payload = self.packet(comparison=f"execution-concurrent-{ordinal}-{status}")
            stdout, stderr = b"  { result } \n\x00\xff\x80  ", b"legacy stderr \x00\xfe\n "
            if ordinal % 4 == 0:
                stdout = b" \n" + json.dumps(json.loads(self.semantic(payload)), indent=3).encode() + b"  \n\t"
            environment = self.cli_environment(stdout, stderr, status) if ordinal == 0 else {**environment, "CTX09C_R2B_EXIT": str(status)}
            environment["CTX09C_R2B_STDOUT"] = base64.b64encode(stdout).decode()
            first = subprocess.Popen(self.cli(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
            second = subprocess.Popen(self.cli(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
            for process in (first, second):
                process.stdin.write(payload)
                process.stdin.close()
                process.stdin = None
            left = first.communicate(timeout=30)
            right = second.communicate(timeout=30)
            with self.subTest(ordinal=ordinal, status=status):
                self.assertEqual(left, (stdout, stderr), left[1].decode(errors="backslashreplace"))
                self.assertEqual(right, left, right[1].decode(errors="backslashreplace"))
                self.assertEqual((first.returncode, second.returncode), (status, status))
                self.assertEqual((self.base / "count").read_bytes().count(b"legacy invocation\n"), ordinal + 1)

    def test_real_crash_after_committed_head_replays_exact_bytes(self):
        payload = self.packet(comparison="execution-crash-replay")
        stdout, stderr = b"  { not canonical }\n\xff\x00 ", b"stderr\xfe\x00\n"
        environment = self.cli_environment(stdout, stderr, 23)
        crashed = subprocess.run(self.cli(), input=payload, capture_output=True, env={**environment, "CTX09C_R2B_CRASH": "1"}, timeout=30)
        self.assertEqual(crashed.returncode, 99)
        head = json.loads((self.base_for(payload) / live.HEAD_NAME).read_bytes())
        self.assertEqual(head["stage"], "legacy_committed")
        replay = subprocess.run(self.cli(), input=payload, capture_output=True, env=environment, timeout=30)
        self.assertEqual((replay.returncode, replay.stdout, replay.stderr), (23, stdout, stderr))
        self.assertEqual((self.base / "count").read_bytes(), b"legacy invocation\n")


if __name__ == "__main__":
    unittest.main()
