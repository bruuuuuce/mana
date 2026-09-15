#!/usr/bin/env python3
"""Local CTX-09A transport only; never contacts a provider or service."""
import json
import hashlib
import os
import signal
import socket
import sys
import time
from pathlib import Path

if sys.argv[1:] == ["--version"]:
    print("codex-cli ctx09a-local-stub")
    sys.exit(0)

action = os.environ.get("CTX09_ACTION", "complete")
if os.environ.get("CTX09_ARGV_CAPTURE"):
    capture = Path(os.environ["CTX09_ARGV_CAPTURE"])
    capture.write_text(json.dumps(sys.argv[1:]) + "\n")
    capture.chmod(0o600)
if os.environ.get("CTX09_CONFIG_CAPTURE"):
    capture = Path(os.environ["CTX09_CONFIG_CAPTURE"])
    trees = {}
    for name in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "OPENCODE_CONFIG_DIR"):
        config_root = Path(os.environ.get(name, ""))
        files = []
        if config_root.is_dir():
            for path in sorted(config_root.rglob("*")):
                info = path.lstat()
                files.append({"path": path.relative_to(config_root).as_posix(),
                              "mode": info.st_mode & 0o777, "inode": info.st_ino,
                              "links": info.st_nlink, "symlink": path.is_symlink(),
                              "type": "directory" if path.is_dir() else "file"})
        trees[name] = files
    config_root = Path(os.environ.get("CODEX_HOME", ""))
    capture.write_text(json.dumps({"codexHome": str(config_root),
        "configDirs": {name: os.environ.get(name) for name in
                       ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "OPENCODE_CONFIG_DIR")},
        "configTrees": trees, "entries": trees["CODEX_HOME"]}, sort_keys=True) + "\n")
    capture.chmod(0o600)
answer = "legacy-answer"
if action == "attack":
    results = []
    paths = json.loads(os.environ["CTX09_DENIED_PATHS"])
    if os.environ.get("MANA_CTX09_TEST_ONLY_CONTAINED") == "1":
        # The fixed test backend does not impersonate native sandbox-exec. Its
        # hostile fixture receives only denied operations and therefore must
        # not issue an external write/network syscall in the first place.
        # Match the native fixture's declared paths, symlink escape and local
        # network probe without attempting any of those operations.
        results = [True] * (len(paths) + 2)
        answer = json.dumps({"blocked": results}, sort_keys=True)
    else:
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
elif action == "sleep":
    time.sleep(30)
elif action == "crash":
    os.kill(os.getpid(), signal.SIGKILL)
elif action == "sigint":
    os.kill(os.getpid(), signal.SIGINT)
elif action == "sigterm":
    os.kill(os.getpid(), signal.SIGTERM)

if "--output-last-message" in sys.argv:
    Path(sys.argv[sys.argv.index("--output-last-message") + 1]).write_text(answer + "\n")
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1}}))
sys.exit(23 if action == "fail" else 0)
