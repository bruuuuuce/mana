#!/usr/bin/env python3
"""Local R2B byte-delivery fixture; never contacts a provider."""
import base64
import os
import sys
import time

sys.stdin.buffer.read()
fd = os.open(os.environ["CTX09C_R2B_COUNT"], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
try:
    os.write(fd, b"legacy invocation\n")
finally:
    os.close(fd)
time.sleep(0.15)
sys.stdout.buffer.write(base64.b64decode(os.environ["CTX09C_R2B_STDOUT"]))
sys.stderr.buffer.write(base64.b64decode(os.environ["CTX09C_R2B_STDERR"]))
raise SystemExit(int(os.environ["CTX09C_R2B_EXIT"]))
