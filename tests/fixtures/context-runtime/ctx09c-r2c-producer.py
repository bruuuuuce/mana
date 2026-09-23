#!/usr/bin/env python3
"""Fixed local producer for real R2C process/crash tests; no provider/API."""
import base64
import os
import sys
import time

sys.stdin.buffer.read()
role, counter = sys.argv[1:]
fd = os.open(counter, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
try:
    os.write(fd, (role + " invocation\n").encode())
    os.fsync(fd)
finally:
    os.close(fd)
time.sleep(0.05)
sys.stdout.buffer.write(base64.b64decode(os.environ["CTX09C_R2C_OUTPUT"]))
sys.stderr.buffer.write(b"legacy stderr\x00\xfe" if role == "legacy" else b"shadow stderr")
raise SystemExit(int(os.environ.get("CTX09C_R2C_EXIT", "0")) if role == "legacy" else 0)
