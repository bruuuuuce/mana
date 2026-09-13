#!/usr/bin/env python3
"""Local CTX-09A transport only; never contacts a provider or service."""
import json
import hashlib
import os
import socket
import sys
from pathlib import Path

if sys.argv[1:] == ["--version"]:
    print("codex-cli ctx09a-local-stub")
    sys.exit(0)

action = os.environ.get("CTX09_ACTION", "complete")
answer = "legacy-answer"
if action == "attack":
    results = []
    paths = json.loads(os.environ["CTX09_DENIED_PATHS"])
    escape = Path(os.environ['MANA_PROVIDER_EXEC_TEMP_DIR']) / 'escape-symlink'
    escape.symlink_to(paths[0])
    for supplied in [*paths, str(escape)]:
        try:
            with open(supplied, "wb") as handle:
                handle.write(b"MUTATION")
        except PermissionError:
            results.append(True)
        else:
            results.append(False)
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
    except PermissionError:
        results.append(True)
    else:
        results.append(False)
    answer = json.dumps({"blocked": results}, sort_keys=True)
elif action == "prompt-hash":
    answer = hashlib.sha256(sys.argv[-1].encode()).hexdigest()
elif action == "mode-output":
    answer = '{"mode":"v2","runtimeMode":"compare","approval":"granted"}'

if "--output-last-message" in sys.argv:
    Path(sys.argv[sys.argv.index("--output-last-message") + 1]).write_text(answer + "\n")
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1}}))
sys.exit(23 if action == "fail" else 0)
