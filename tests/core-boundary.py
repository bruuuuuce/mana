#!/usr/bin/env python3
"""Focused regression tests for the restricted-core EXACT default boundary."""

import hashlib
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("exact_boundary", ROOT / "scripts/lib/exact_repair.py")
EXACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXACT)
DENIAL = {
    "schema": "mana.exact-result/v1",
    "status": "BLOCKED",
    "stop_reason": "EXPERIMENTAL_EXACT_DISABLED",
    "application_started": False,
    "applied": False,
    "provider_calls": 0,
}


class RestrictedCoreBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="mana-core-boundary-", dir="/private/tmp"))
        self.addCleanup(shutil.rmtree, self.temp)
        self.project = self.temp / "project"
        self.project.mkdir()
        self.source = self.project / "src/main/java/example/Example.java"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("class Example { int value = 1; }\n")
        self.source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.out = self.temp / "outputs"
        self.out.mkdir(mode=0o700)
        self.host = self.temp / "host"
        self.host.mkdir(mode=0o700)
        self.grant = self.host / "grant.json"
        self.grant.write_text('{"test":"must remain untouched"}\n')
        self.grant.chmod(0o600)
        self.grant_bytes = self.grant.read_bytes()

    def assert_denied(self, result):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), DENIAL)
        self.assertEqual(result.stderr, "")
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.source_hash)
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertEqual(self.grant.read_bytes(), self.grant_bytes)
        self.assertFalse(Path(str(self.grant) + ".used").exists())
        self.assertEqual(list(self.host.iterdir()), [self.grant])

    def python_tripwire(self):
        bindir = self.temp / "bin"
        bindir.mkdir(exist_ok=True)
        marker = self.temp / "python-was-started"
        shim = bindir / "python3"
        shim.write_text(f"#!/bin/sh\nprintf called > {marker}\nexit 99\n")
        shim.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = f"{bindir}:{env['PATH']}"
        return env, marker

    def invoke_shell(self, script, env):
        return subprocess.run(
            [str(ROOT / script), "--project-root", str(self.project),
             "--exact-request", str(self.temp / "missing-request.json"),
             "--host-grant", str(self.grant),
             "--provider", "none", "--json"],
            cwd=self.project, env=env, capture_output=True, text=True,
        )

    def test_public_verify_and_repair_deny_before_python_or_effects(self):
        env, marker = self.python_tripwire()
        for script in ("scripts/mana-verify.sh", "scripts/mana-repair.sh"):
            with self.subTest(script=script):
                self.assert_denied(self.invoke_shell(script, env))
                self.assertFalse(marker.exists(), "denial must happen before Python/provider startup")

    def test_bootstrapped_wrapper_dispatches_to_same_denial(self):
        git = subprocess.run(
            ["git", "-c", "init.defaultBranch=main", "init", str(self.project)],
            capture_output=True, text=True,
        )
        self.assertEqual(git.returncode, 0, git.stderr)
        subprocess.run(["git", "-C", str(self.project), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.project), "config", "user.name", "Boundary Test"], check=True)
        boot = subprocess.run(
            [str(ROOT / "scripts/bootstrap-project.sh"), "--project-root", str(self.project),
             "--mana-root", str(ROOT), "--no-links", "--no-jira-env", "--no-gitignore"],
            cwd=self.project, capture_output=True, text=True,
        )
        self.assertEqual(boot.returncode, 0, boot.stdout + boot.stderr)
        linked_readme = (self.project / ".mana/README.md").read_text()
        self.assertIn("EXACT is experimental and disabled by default", linked_readme)
        env, marker = self.python_tripwire()
        for command in ("verify", "repair"):
            with self.subTest(command=command):
                result = subprocess.run(
                    [str(self.project / "mana"), command, "--exact-request", str(self.temp / "missing-request.json"),
                     "--host-grant", str(self.grant), "--provider", "none", "--json"],
                    cwd=self.project, env=env, capture_output=True, text=True,
                )
                self.assert_denied(result)
        self.assertFalse(marker.exists())

    def test_direct_python_invocation_denies_before_argument_parsing_or_runtime(self):
        result = subprocess.run(
            ["python3", "-I", "-B", str(ROOT / "scripts/lib/exact_repair.py"),
             "--entry", "verify", "--exact-request", str(self.temp / "missing-request.json"),
             "--host-grant", str(self.grant), "--provider", "none", "--json"],
            cwd=self.project, capture_output=True, text=True,
        )
        self.assert_denied(result)

    def test_direct_denial_calls_no_runtime_executor_or_network(self):
        events = []

        def audit(event, args):
            if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
                events.append(event)

        sys.addaudithook(audit)
        stdout = io.StringIO()
        argv = ["exact_repair.py", "--entry"]
        with (
            patch.object(sys, "argv", argv),
            patch.object(EXACT, "load", side_effect=AssertionError("request read")) as load,
            patch.object(EXACT, "runtime", side_effect=AssertionError("runtime initialized")) as runtime,
            patch.object(EXACT, "validate", side_effect=AssertionError("admission called")) as validate,
            patch.object(EXACT, "execute", side_effect=AssertionError("execution started")) as execute,
            patch.object(subprocess, "run", side_effect=AssertionError("child process started")) as run,
            contextlib.redirect_stdout(stdout),
        ):
            code = EXACT.main()
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue()), DENIAL)
        for mocked in (load, runtime, validate, execute, run):
            mocked.assert_not_called()
        self.assertEqual(events, [])

    def test_malformed_and_alternate_dispatch_arguments_do_not_enable_exact(self):
        env, marker = self.python_tripwire()
        malformed = subprocess.run(
            [str(ROOT / "scripts/mana-verify.sh"), "--exact-request", "--json"],
            cwd=self.project, env=env, capture_output=True, text=True,
        )
        self.assert_denied(malformed)
        alternate = subprocess.run(
            [str(ROOT / "scripts/mana-verify.sh"), "--exact-request=missing.json"],
            cwd=self.project, env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(alternate.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.source_hash)
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertEqual(self.grant.read_bytes(), self.grant_bytes)
        self.assertFalse(Path(str(self.grant) + ".used").exists())
        self.assertEqual(list(self.host.iterdir()), [self.grant])

    def test_ordinary_verify_still_lists_skills(self):
        result = subprocess.run(
            [str(ROOT / "scripts/mana-verify.sh"), "--project-root", str(self.project), "--list"],
            cwd=self.project, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("verification", result.stdout.lower())

    def test_inventory_classifications_and_default_deny_are_machine_checked(self):
        inventory = json.loads((ROOT / "config/mana-core-capabilities-v1.json").read_text())
        self.assertEqual(inventory["schema"], "mana.core-capabilities/v1")
        bootstrap = (ROOT / "scripts/bootstrap-project.sh").read_text()
        routed = set(re.findall(r"^  ([a-z][a-z-]*)\)$", bootstrap, re.MULTILINE))
        listed = {
            entry["command"]
            for entry in inventory["entry_point_inventory"]["commands"]
            if " " not in entry["command"] and entry["command"] not in {"help", "--help", "-h"}
        }
        self.assertEqual(routed, listed)
        self.assertIn("--help", {entry["command"] for entry in inventory["entry_point_inventory"]["commands"]})
        self.assertIn("-h", {entry["command"] for entry in inventory["entry_point_inventory"]["commands"]})
        self.assertIn("remain reachable", inventory["entry_point_inventory"]["classification_semantics"])
        for entry in inventory["entry_point_inventory"]["commands"]:
            self.assertIn(entry["classification"], {"supported", "experimental", "excluded", "not_yet_qualified"})
        by_id = {entry["id"]: entry for entry in inventory["capabilities"]}
        exact = by_id["exact-fixture-execution"]
        self.assertEqual(exact["classification"], "experimental")
        self.assertEqual(exact["default"], "denied")
        self.assertIn("--experimental-exact", " ".join(exact["entry_points"]))
        for entry in inventory["capabilities"]:
            self.assertIn(entry["classification"], {"supported", "experimental", "excluded", "not_yet_qualified"})
        self.assertTrue(any("user who controls installed source" in limit for limit in inventory["boundary_limits"]))
        self.assertTrue(all(entry["classification"] == "excluded" for entry in inventory["excluded_capabilities"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
