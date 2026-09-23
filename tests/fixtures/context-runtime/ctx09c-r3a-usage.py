#!/usr/bin/env python3
"""Noncooperating local process: publishes numeric usage before termination."""
import json
import os
from pathlib import Path
import signal
import sys
import time

summary, execution, profile, outcome = sys.argv[1:]
path = Path(summary)
path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
value = {"schemaVersion": "1", "executionId": execution, "profileId": profile,
         "provider": "codex", "providerVersion": "offline-fixture", "status": "failed",
         "usageStatus": "measured", "phases": [], "parseErrors": 0, "rawTraceRetained": False,
         "totals": {"input": 10, "cachedInput": 2, "uncachedInput": 8, "output": 3, "reasoning": 1},
         "turns": 1, "toolCalls": 0, "workers": 0, "compactions": 0}
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    json.dump(value, stream)
    stream.flush()
    os.fsync(stream.fileno())
if outcome == "failed":
    raise SystemExit(23)
if outcome in {"SIGINT", "SIGTERM"}:
    os.kill(os.getppid(), getattr(signal, outcome))
signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(30)
