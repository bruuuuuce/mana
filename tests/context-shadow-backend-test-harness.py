#!/usr/bin/env python3
"""Import-only native fixture backend; production has no selector or implementation."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ctx09c_production_backend", REPO / "scripts/lib/context-shadow-backend.py")
production = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = production
spec.loader.exec_module(production)


class TestOnlyAdmission:
    def __init__(self, scratch, run_root, metrics_root, status="available", reason=None):
        self.scratch, self.run_root, self.metrics_root = scratch, run_root, metrics_root
        self.status, self.reason = status, reason

    def invoke(self, argv, *, input_bytes, environment, cwd):
        if self.status != "available":
            raise RuntimeError("unavailable test-only shadow backend")
        fixtures = {REPO / "tests/context-shadow-backend-test-only.py",
                    REPO / "tests/context-shadow-consumer-test-only.py"}
        if len(argv) < 2 or Path(argv[0]).resolve() != Path(sys.executable).resolve() or Path(argv[1]) not in fixtures:
            raise RuntimeError("test backend accepts only fixed local fixtures")
        if not production.safe_tree(self.run_root) or not production.safe_tree(self.scratch):
            raise RuntimeError("unsafe fixture read root")
        fixture_provider = shutil.which("codex", path=environment.get("PATH"))
        bindings = []
        if fixture_provider and Path(fixture_provider).resolve() in {
                REPO / "tests/fixtures/context-runtime/ctx06c-provider-stub.sh",
                REPO / "tests/fixtures/context-runtime/ctx09a-provider-stub.py"}:
            bindings.append(Path(fixture_provider))
        reads = (REPO / "tests/fixtures/context-runtime", *fixtures, *bindings)
        admission = production.Admission("available", None, self.scratch,
            production.policy(self.scratch, self.run_root, self.metrics_root, reads))
        return admission.invoke(argv, input_bytes=input_bytes, environment=environment, cwd=cwd)


@contextmanager
def admit_test_only(run_root=None, metrics_root=None):
    with tempfile.TemporaryDirectory(prefix="mana-ctx09c-test-only-", dir="/private/tmp" if sys.platform == "darwin" else "/tmp") as temporary:
        scratch = Path(temporary).resolve()
        os.chmod(scratch, 0o700)
        run_root = Path(run_root) if run_root is not None else scratch
        metrics_root = Path(metrics_root) if metrics_root is not None else run_root
        if sys.platform != "darwin" or production.NATIVE.is_symlink() or not production.NATIVE.is_file():
            yield TestOnlyAdmission(scratch, run_root, metrics_root, "unavailable", "native-backend-absent")
            return
        try:
            proof = subprocess.run([str(production.NATIVE), "-p", "(version 1)(allow default)(deny network*)", "--", "/usr/bin/true"],
                capture_output=True, timeout=5, env=production.host_environment())
            available = proof.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            available = False
        yield TestOnlyAdmission(scratch, run_root, metrics_root, "available" if available else "unavailable",
                                None if available else "native-backend-unavailable")
