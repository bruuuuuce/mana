#!/usr/bin/env python3
"""Fixed host fixture root, unreachable through production CLI/environment."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mana_budget_fixture", ROOT / "scripts/lib/context-budget.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.HOST_FRAMEWORK_ROOT = ROOT / "tests/fixtures/context-runtime/ctx06a-framework"
raise SystemExit(module.main(sys.argv))
