#!/usr/bin/env python3
"""Fixed offline CTX-09A registration harness; never installed or selected by production."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mode_fixture", REPO / "scripts/context-runtime-mode.py")
mode = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mode)


def fixture(root, command):
    provider = shutil.which("codex")
    if not provider or Path(provider).resolve() != REPO / "tests/fixtures/context-runtime/ctx09a-provider-stub.py":
        raise mode.runtime.ContractError("test harness requires the fixed offline provider")
    with tempfile.TemporaryDirectory(dir="/private/tmp" if sys.platform == "darwin" else "/tmp") as temporary:
        scratch = Path(temporary).resolve()
        environment = {**os.environ, "TMPDIR": str(scratch), "MANA_PROVIDER_EXEC_TEMP_DIR": str(scratch),
                       "MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE": "false", "MANA_UPDATE_CHECK": "off",
                       "MANA_CTX09_TEST_ONLY_CONTAINED": "1", "MANA_CTX09_NATIVE_PROBE": "unavailable"}
        print(json.dumps({"shadowBackend": "test-only", "nativeIsolationProbe": "unavailable"}),
              end="", file=sys.stderr)
        return subprocess.call([str(REPO / "tests/fixtures/context-runtime/isolation-pass-through.sh"),
            "-f", mode.shadow_policy(scratch, root.path / ".mana/runtime/metrics"), "--", *command], env=environment)


if __name__ == "__main__":
    mode.shadow_legacy = fixture
    try:
        raise SystemExit(mode.main())
    except (mode.runtime.ContractError, OSError, ValueError):
        print("ERROR: test-only mode fixture rejected", file=sys.stderr)
        raise SystemExit(2)
