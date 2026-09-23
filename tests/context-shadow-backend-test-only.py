#!/usr/bin/env python3
"""Fixed hostile fixture, using actual syscalls under the native boundary."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/lib/context-shadow-boundary-probe.py"), run_name="__main__")
