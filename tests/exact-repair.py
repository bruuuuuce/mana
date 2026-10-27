#!/usr/bin/env python3
"""Component tests use explicit doubles; they do NOT qualify native execution."""

import contextlib
import copy
import errno
import io
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("exact", ROOT / "scripts/lib/exact_repair.py")
x = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x)


def result(exit=0, timeout=False):
    return {
        "exit": exit,
        "timeout": timeout,
        "descendants_terminated": False,
        "stdout": "",
        "stderr": "",
        "argv": [],
        "duration_ms": 0,
    }


class Contract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mana-exact-unit-", dir="/private/tmp")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.dest = self.tmp / "copy"
        self.out = self.tmp / "outputs"
        self.host = self.tmp / "host"
        for p in (self.dest, self.out, self.host):
            p.mkdir(mode=0o700)
        self.source = "src/main/java/example/Example.java"
        self.test = "src/test/java/example/ExampleTest.java"
        snapshot = {}
        for name, text in [
            (self.source, "class Example {}\n"),
            (self.test, "class ExampleTest {}\n"),
            ("README.md", "public test fixture\n"),
        ]:
            p = self.dest / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            snapshot[name] = {"text": text, "sha256": x.digest(text.encode())}
        self.protected = self.host / "protected"
        self.protected.write_text("original")
        proposal = {
            "schema": "mom.operator.offline-proposal/v1",
            "status": "HUMAN_REQUIRED",
            "executable": False,
            "edit": {"path": self.source, "replacement": "final class Example {}\n"},
            "handoff": {
                "schema": "mom.operator.offline-handoff/v1",
                "mission": "test-origin",
                "request": "exact edit",
                "snapshot": snapshot,
                "snapshot_sha256": x.identity(snapshot),
                "regression_test": self.test,
            },
        }
        proposal["fingerprint"] = x.identity(proposal)
        ds = self.dest.stat()
        self.r = {
            "schema": "mana.exact-request/v1",
            "id": "unit",
            "proposal": proposal,
            "destination": str(self.dest),
            "destination_identity": {"device": ds.st_dev, "inode": ds.st_ino},
            "outputs": str(self.out),
            "result_sha256": x.digest(proposal["edit"]["replacement"].encode()),
            "verification": {
                "catalog": "java-jdk-pair/v1",
                "test_path": self.test,
                "main_class": "example.ExampleTest",
            },
            "budget": {
                "attempts": 1,
                "verification_commands": 4,
                "timeout_seconds": 1,
                "total_seconds": 12,
                "output_bytes": 16384,
                "file_bytes": 1048576,
            },
            "runtime": {"test": "component double only"},
            "authorization_reference": "test-grant",
            "protected_files": [str(self.protected)],
            "provider": "none",
            "operation": "repair-verify",
            "baseline": {"test_exit": 0, "stdout_sha256": x.digest(b"")},
        }
        self.gp = self.host / "grant.json"
        self.grant = {
            "schema": "mana.exact-host-grant/v1",
            "id": "test-grant",
            "authority": "explicit-public-fixture-test",
            "approved": True,
            "request_sha256": x.identity(self.r),
            "expires_at": int(time.time()) + 300,
            "uses": 1,
        }
        self.write_grant()
        self.calls = []

    def write_grant(self):
        self.gp.write_bytes(x.encoded(self.grant))
        self.gp.chmod(0o600)

    def rebind(self):
        self.grant["request_sha256"] = x.identity(self.r)
        self.write_grant()

    def validate(self):
        return x.validate(self.r, self.gp, {"test": "component double only"})

    def qualifier(self, request):
        self.calls.append("simulated-boundary")
        return result()

    def applier(self, request):
        self.calls.append("simulated-apply")
        (self.dest / self.source).write_text(request["proposal"]["edit"]["replacement"])
        return result()

    def runner(self, request, argv, label):
        self.calls.append(label)
        return result()

    def run_double(self, runner=None, applier=None):
        return x.execute(
            self.validate(),
            runner=runner or self.runner,
            qualifier=self.qualifier,
            applier=applier or self.applier,
        )

    def reject(self, reason=None):
        with self.assertRaises(x.Rejected) as caught:
            self.validate()
        if reason:
            self.assertIn(reason, str(caught.exception))
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertFalse(Path(str(self.gp) + ".used").exists())

    def test_exact_transformation_simulated_executor(self):
        r = self.run_double()
        self.assertEqual(r["status"], "COMPLETE")
        self.assertTrue(r["applied"])
        self.assertEqual(r["provider_calls"], 0)
        self.assertFalse(r["human_approval"])
        self.assertEqual(
            (self.dest / self.source).read_bytes(),
            self.r["proposal"]["edit"]["replacement"].encode(),
        )
        self.assertEqual([p for p in r["final"] if r["initial"][p] != r["final"][p]], [self.source])
        self.assertEqual(
            self.calls,
            [
                "simulated-boundary",
                "baseline-0",
                "baseline-1",
                "simulated-apply",
                "after-0",
                "after-1",
            ],
        )
        self.assertEqual(
            x.digest((self.out / "result.json").read_bytes()),
            (self.out / "result.sha256").read_text().strip(),
        )

    def receipt_cli(self, artifact=None, fault="open", runner=None, qualifier=None, applier=None):
        """Real CLI main/admission/execute; only native execution and sink faults doubled."""
        request = self.tmp / "request.json"
        request.write_bytes(x.encoded(self.r))
        real_execute, real_open = x.execute, Path.open

        def execute(admitted):
            return real_execute(
                admitted,
                runner=runner or self.runner,
                qualifier=qualifier or self.qualifier,
                applier=applier or self.applier,
            )

        class Sink:
            def __init__(self, file):
                self.file = file

            def __enter__(self):
                self.file.__enter__()
                return self

            def __getattr__(self, name):
                return getattr(self.file, name)

            def write(self, data):
                if fault == "write":
                    self.file.write(data[:7])
                    raise OSError(errno.ENOSPC, "test-injected receipt write failure")
                return self.file.write(data)

            def __exit__(self, *args):
                result = self.file.__exit__(*args)
                if fault == "close":
                    raise OSError(errno.ENOSPC, "test-injected receipt close failure")
                return result

        def open_sink(path, *args, **kwargs):
            if artifact and path == self.out / artifact:
                if fault == "open":
                    raise OSError(errno.ENOSPC, "test-injected receipt open failure")
                return Sink(real_open(path, *args, **kwargs))
            return real_open(path, *args, **kwargs)

        stdout, stderr = io.StringIO(), io.StringIO()
        argv = [
            "exact_repair.py",
            "--entry",
            "repair" if self.r["operation"] == "repair-verify" else "verify",
            "--exact-request",
            str(request),
            "--host-grant",
            str(self.gp),
            "--provider",
            "none",
            "--json",
        ]
        with (
            patch.object(x, "runtime", return_value=self.r["runtime"]),
            patch.object(x, "execute", side_effect=execute),
            patch.object(Path, "open", new=open_sink),
            patch.object(sys, "argv", argv),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = x.main()
        self.cli_evidence = dict(
            argv=argv, stdout=stdout.getvalue(), stderr=stderr.getvalue(), exit=code
        )
        return code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_cli_receipt_faults_preserve_effects(self):
        for artifact in ("result.json", "result.sha256"):
            for fault in ("open", "write", "close"):
                for applied in (False, True):
                    with self.subTest(artifact=artifact, fault=fault, applied=applied):
                        case = Contract("test_exact_transformation_simulated_executor")
                        case.setUp()
                        self.addCleanup(case.doCleanups)
                        before = (case.dest / case.source).read_bytes()
                        qualifier = case.qualifier if applied else lambda _: result(1)
                        code, r, stderr = case.receipt_cli(artifact, fault, qualifier=qualifier)
                        self.assertEqual(code, 2)
                        self.assertEqual(r["status"], "PARTIAL" if applied else "BLOCKED")
                        self.assertEqual(r["application_started"], applied)
                        self.assertEqual(r["applied"], applied)
                        self.assertEqual(r["receipt_error"]["artifact"], artifact)
                        self.assertIn("receipt " + fault + " failure", r["receipt_error"]["error"])
                        self.assertIn("RECEIPT_PERSISTENCE_FAILED", stderr)
                        self.assertIn(r["status"], stderr)
                        self.assertEqual(
                            (case.dest / case.source).read_bytes(),
                            case.r["proposal"]["edit"]["replacement"].encode()
                            if applied
                            else before,
                        )
                        self.assertEqual(
                            set(r["steps"]),
                            {"boundary", "baseline-0", "baseline-1", "apply", "after-0", "after-1"}
                            if applied
                            else {"boundary"},
                        )
                        for step in r["steps"].values():
                            self.assertEqual(step["exit"], 0 if applied else 1)
                        self.assertEqual(
                            r["stop_reason"],
                            "RECEIPT_PERSISTENCE_FAILED"
                            if applied
                            else "NATIVE_BOUNDARY_UNQUALIFIED",
                        )
                        reservation = Path(str(case.gp) + ".used")
                        used = reservation.read_bytes()
                        # Remove all other replay blockers; reservation alone still denies.
                        other = case.tmp / "retry-output"
                        other.mkdir(mode=0o700)
                        case.r["outputs"] = str(other)
                        if applied:
                            (case.dest / case.source).write_bytes(before)
                        case.rebind()
                        with self.assertRaisesRegex(x.Rejected, "AUTHORIZATION_CONSUMED"):
                            case.validate()
                        self.assertEqual(reservation.read_bytes(), used)
                        self.assertEqual(case.calls.count("simulated-apply"), int(applied))

    def test_cli_receipt_failure_preserves_failed_verification(self):
        def runner(req, argv, label):
            return result(1 if label == "after-1" else 0)

        code, r, _ = self.receipt_cli("result.sha256", runner=runner)
        self.assertEqual(code, 2)
        self.assertTrue(r["applied"])
        self.assertEqual(r["steps"]["after-0"]["exit"], 0)
        self.assertEqual(r["steps"]["after-1"]["exit"], 1)
        self.assertEqual(r["stop_reason"], "COMPILATION_OR_TEST_FAILED")
        self.assertIn("receipt_error", r)

    def test_cli_receipt_failure_preserves_uncertain_application(self):
        def apply(req):
            (self.dest / self.source).write_text("partial")
            raise OSError("test-injected partial application")

        code, r, _ = self.receipt_cli("result.json", applier=apply)
        self.assertEqual(code, 2)
        self.assertEqual(r["status"], "PARTIAL")
        self.assertTrue(r["application_started"])
        self.assertFalse(r["applied"])
        self.assertNotIn("after-0", r["steps"])  # NOT RUN, never inferred PASS.
        self.assertEqual((self.dest / self.source).read_text(), "partial")
        self.assertIn("receipt_error", r)

    def test_cli_receipt_failure_preserves_final_uncertainty(self):
        def qualifier(req):
            # Simulate an unexpected mutation observed by final inventory, before apply.
            (self.dest / self.source).write_text("unexpected")
            return result(1)

        code, r, _ = self.receipt_cli("result.json", qualifier=qualifier)
        self.assertEqual(code, 2)
        self.assertEqual(r["status"], "PARTIAL")
        self.assertFalse(r["application_started"])
        self.assertFalse(r["applied"])
        self.assertEqual(r["stop_reason"], "FINAL_CONTENT_MISMATCH")
        self.assertNotEqual(r["initial"], r["final"])
        self.assertIn("receipt_error", r)

    def test_cli_receipt_failure_verify_only(self):
        self.r["operation"] = "verify"
        self.r["budget"]["verification_commands"] = 2
        self.rebind()
        before = (self.dest / self.source).read_bytes()
        code, r, _ = self.receipt_cli("result.json")
        self.assertEqual(code, 2)
        self.assertEqual(r["status"], "BLOCKED")
        self.assertFalse(r["application_started"])
        self.assertFalse(r["applied"])
        self.assertEqual(set(r["steps"]), {"boundary", "verify-0", "verify-1"})
        self.assertEqual((self.dest / self.source).read_bytes(), before)

    def test_cli_rejection_before_application(self):
        self.grant["approved"] = False
        self.write_grant()
        before = (self.dest / self.source).read_bytes()
        code, r, _ = self.receipt_cli()
        self.assertEqual(code, 2)
        self.assertEqual(r["status"], "BLOCKED")
        self.assertFalse(r["application_started"])
        self.assertFalse(r["applied"])
        self.assertEqual((self.dest / self.source).read_bytes(), before)
        self.assertEqual(self.calls, [])
        self.assertFalse(Path(str(self.gp) + ".used").exists())

    def test_cli_ordinary_receipt_success(self):
        code, r, stderr = self.receipt_cli()
        self.assertEqual(code, 0)
        self.assertEqual(r["status"], "COMPLETE")
        self.assertTrue(r["applied"])
        self.assertEqual(stderr, "")
        self.assertNotIn("receipt_error", r)
        self.assertEqual(json.loads((self.out / "result.json").read_text()), r)
        self.assertEqual(
            x.digest((self.out / "result.json").read_bytes()),
            (self.out / "result.sha256").read_text().strip(),
        )

    def test_base_mismatch(self):
        (self.dest / self.source).write_text("stale")
        self.reject("BASE_MISMATCH")

    def test_protected_base_mismatch(self):
        (self.dest / self.test).write_text("altered test")
        self.reject("BASE_MISMATCH")

    def test_modified_proposal(self):
        self.r["proposal"]["edit"]["replacement"] += "other"
        self.reject("PROPOSAL_FINGERPRINT")

    def test_result_inconsistent(self):
        self.r["result_sha256"] = "0" * 64
        self.reject("RESULT_HASH")

    def test_missing_authority(self):
        self.gp.unlink()
        with self.assertRaises(FileNotFoundError):
            self.validate()
        self.assertEqual(self.calls, [])

    def test_denied_authority(self):
        self.grant["approved"] = False
        self.write_grant()
        self.reject("AUTHORIZATION")

    def test_other_effects(self):
        self.grant["request_sha256"] = "0" * 64
        self.write_grant()
        self.reject("EFFECTS")

    def test_no_human_impersonation(self):
        self.grant["authority"] = "human"
        self.write_grant()
        self.reject("TEST_AUTHORITY")

    def test_expired(self):
        self.grant["expires_at"] = int(time.time()) - 1
        self.write_grant()
        self.reject("EXPIRED")

    def test_no_sharing_or_provider_fallback(self):
        self.r["provider"] = "codex"
        self.reject("NO_PROVIDER")

    def test_revision(self):
        self.r["runtime"] = {"base_revision": "other"}
        self.reject("REVISION_NOT_ADMITTED")

    def test_budget_exhausted(self):
        self.r["budget"]["attempts"] = 0
        self.reject("BUDGET")

    def test_single_use(self):
        self.run_double()
        # Fresh empty output path still cannot replay the same authorization.
        other = self.tmp / "other"
        other.mkdir(mode=0o700)
        self.r["outputs"] = str(other)
        self.rebind()
        with self.assertRaises(x.Rejected):
            self.validate()
        self.assertEqual(self.calls.count("simulated-apply"), 1)

    def test_path_escape(self):
        self.r["proposal"]["edit"]["path"] = "../outside"
        self.refingerprint()
        self.reject("PATH")

    def test_test_mutation(self):
        self.r["proposal"]["edit"]["path"] = self.test
        self.refingerprint()
        self.reject("SOURCE_SCOPE")

    def test_config_mutation(self):
        self.r["proposal"]["edit"]["path"] = "src/main/java/config/Setting.java"
        self.refingerprint()
        self.reject("SOURCE_SCOPE")

    def refingerprint(self):
        p = self.r["proposal"]
        p["fingerprint"] = x.identity({k: v for k, v in p.items() if k != "fingerprint"})

    def test_symlink_file(self):
        p = self.dest / self.source
        p.unlink()
        p.symlink_to(self.protected)
        self.reject("SYMLINK")

    def test_symlink_ancestor(self):
        parent = self.dest / "src/main/java/example"
        shutil.rmtree(parent)
        parent.symlink_to(self.host)
        self.reject("SYMLINK")

    def test_hardlink(self):
        p = self.dest / self.source
        p.unlink()
        os.link(self.protected, p)
        self.reject("TYPE")

    def test_extra_file(self):
        (self.dest / "extra").write_text("extra")
        self.reject("DESTINATION_SCOPE")

    def test_destination_identity(self):
        self.r["destination_identity"]["inode"] += 1
        self.reject("DESTINATION_IDENTITY")

    def test_unauthorized_destination(self):
        self.r["destination"] = str(ROOT)
        self.reject()

    def test_shell_command_rejected(self):
        self.r["verification"]["command"] = "touch /tmp/no"
        self.reject("VERIFIER_FIELDS")

    def test_no_native_boundary_simulated(self):
        r = x.execute(
            self.validate(), runner=self.runner, qualifier=lambda _: result(1), applier=self.applier
        )
        self.assertEqual(r["status"], "BLOCKED")
        self.assertEqual(self.calls, [])

    def test_compilation_failure_simulated(self):
        r = self.run_double(runner=lambda *args: result(2))
        self.assertEqual(r["status"], "BLOCKED")
        self.assertFalse(r["applied"])
        self.assertNotIn("simulated-apply", self.calls)

    def test_test_failure_simulated_partial(self):
        def runner(req, argv, label):
            return result(1 if label == "after-1" else 0)

        r = self.run_double(runner=runner)
        self.assertEqual(r["status"], "PARTIAL")
        self.assertTrue(r["applied"])

    def test_timeout_simulated_partial(self):
        def runner(req, argv, label):
            return result(143, True) if label == "after-0" else result()

        r = self.run_double(runner=runner)
        self.assertEqual(r["status"], "PARTIAL")
        self.assertTrue(r["applied"])

    def test_failed_apply_records_partial(self):
        def apply(req):
            (self.dest / self.source).write_text("partial")
            raise OSError("simulated partial write")

        r = self.run_double(applier=apply)
        self.assertEqual(r["status"], "PARTIAL")
        self.assertFalse(r["applied"])
        self.assertEqual((self.dest / self.source).read_text(), "partial")

    def test_mismatched_final_result_simulated(self):
        def apply(req):
            (self.dest / self.source).write_text("wrong")
            return result()

        r = self.run_double(applier=apply)
        self.assertEqual(r["status"], "PARTIAL")
        self.assertNotIn("after-0", self.calls)

    def test_verify_only_simulated(self):
        self.r["operation"] = "verify"
        self.r["budget"]["verification_commands"] = 2
        self.rebind()
        r = self.run_double()
        self.assertEqual(r["status"], "COMPLETE")
        self.assertFalse(r["applied"])
        self.assertNotIn("simulated-apply", self.calls)

    def test_baseline_not_reproduced_stops_before_apply(self):
        def runner(req, argv, label):
            return result(1 if label == "baseline-1" else 0)

        r = self.run_double(runner=runner)
        self.assertEqual(r["status"], "BLOCKED")
        self.assertFalse(r["applied"])
        self.assertIn("BASELINE_NOT_REPRODUCED", r["stop_reason"])
        self.assertNotIn("simulated-apply", self.calls)

    def test_native_supervisor_timeout_and_descendant_cleanup(self):
        # Native supervisor only, no fixture/candidate application or sandbox claim.
        r = copy.deepcopy(self.r)
        r["runtime"]["jdk_home"] = "/no-java-needed"
        pidfile = self.out / "child.pid"
        code = (
            "import os,time;pid=os.fork();"
            "open(" + repr(str(pidfile)) + ',"w").write(str(pid)) if pid else None;'
            "time.sleep(30)"
        )
        res = x.supervise(
            r, [sys.executable, "-I", "-B", "-c", code], "native-timeout", sandbox=False
        )
        self.assertTrue(res["timeout"])
        self.assertNotEqual(res["exit"], 0)
        pid = int(pidfile.read_text())
        state = x.subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True
        ).stdout.strip()
        self.assertTrue(not state or state.startswith("Z"), state)

    def test_duplicate_keys(self):
        with self.assertRaises(x.Rejected):
            json.loads('{"a":1,"a":2}', object_pairs_hook=x.pairs)

    def test_provider_imports_absent(self):
        import ast

        source = (ROOT / "scripts/lib/exact_repair.py").read_text()
        tree = ast.parse(source)
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertFalse(any("provider" in ast.unparse(n) for n in imports))
        self.assertNotIn("MANA_REPAIR_ALLOW_STUB", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
