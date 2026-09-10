#!/usr/bin/env python3
"""Test-only CTX-07B helper using the checked-in retain debug policy."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts/lib/context-worker-runtime.py"
FIXTURE = ROOT / "tests/fixtures/context-runtime/ctx06a-framework"
spec = importlib.util.spec_from_file_location("mana_context_worker_retain_test_only", TARGET)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load CTX-07B worker helper")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.HOST_FRAMEWORK_ROOT = FIXTURE
module.DEBUG_POLICY_RELATIVE_PATH = Path(
    "config/context-runtime/worker-debug-policy-retain-v1.json"
)
module.WORKER_TIMEOUT_SECONDS = 2
module.WORKER_KILL_GRACE_SECONDS = 1

raise SystemExit(module.main(sys.argv))
