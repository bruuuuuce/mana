#!/usr/bin/env python3
"""Operational native admission probe: every deny boolean follows a real failed operation."""
import json
import importlib.util
import os
import socket
import sys
from pathlib import Path


def denied(operation):
    try:
        operation()
    except PermissionError:
        return True
    return False


def write(path):
    with open(path, "xb") as stream:
        stream.write(b"FORBIDDEN")


def main():
    paths = json.loads(sys.stdin.buffer.read())
    spec = importlib.util.spec_from_file_location("ctx09c_probe_publication", Path(__file__).resolve().parents[1] / "context-runtime-mode.py")
    publication = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publication)
    def publish():
        target = Path(paths["publish"])
        publication.publish_v2_artifact(str(target.parent), "execution-boundary-probe", "boundary-probe",
            "a" * 64, target.name, b"{}\n", execution_version=1)
    result = {"publish": denied(publish),
              "externalWrite": denied(lambda: write(paths["externalWrite"]))}
    # These are deliberately separate attempts: state and approval files are
    # not merely aliases for a generic output path in the hostile coverage.
    for name in ("stateMutation", "approvalMutation"):
        if name in paths:
            result[name] = denied(lambda name=name: write(paths[name]))
    if "artifactReplacement" in paths:
        replacement = Path(paths["allowedInput"]).parent / "replacement-source"
        replacement.write_bytes(b"REPLACEMENT")
        try:
            result["artifactReplacement"] = denied(lambda: os.replace(replacement, paths["artifactReplacement"]))
        finally:
            try: replacement.unlink()
            except FileNotFoundError: pass
    if "environmentCanary" in paths:
        # Reading a missing secret is not an enforcement success; the
        # allowlisted child environment makes this exfiltration attempt empty.
        result["environment"] = paths["environmentCanary"] not in "\0".join(
            key + "=" + value for key, value in os.environ.items())
    # Denial is checked before any connection: no remote endpoint is contacted.
    def network_attempt():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.connect(("127.0.0.1", 9))
    result["network"] = denied(network_attempt)
    # macOS native mach service lookup, without invoking a discovered service.
    import ctypes
    library = ctypes.CDLL(None)
    bootstrap = ctypes.c_uint.in_dll(library, "bootstrap_port").value
    port = ctypes.c_uint()
    result["serviceDiscovery"] = library.bootstrap_look_up(bootstrap, b"com.apple.cfprefsd.daemon", ctypes.byref(port)) != 0
    for name, path in paths["reads"].items():
        result[name] = denied(lambda path=path: Path(path).read_bytes())
    # Try creating aliases after launch, when they cannot be pre-enumerated.
    source = Path(paths["reads"]["legacyHead"])
    dynamic_link = Path(paths["allowedInput"]).parent / "dynamic-hardlink"
    dynamic_symbolic = Path(paths["allowedInput"]).parent / "dynamic-symlink"
    def hardlink_escape():
        os.link(source, dynamic_link)
        dynamic_link.read_bytes()
    def symlink_escape():
        dynamic_symbolic.symlink_to(source)
        dynamic_symbolic.read_bytes()
    result["dynamicHardlink"] = denied(hardlink_escape)
    result["dynamicSymlink"] = denied(symlink_escape)
    for alias in (dynamic_link, dynamic_symbolic):
        try: alias.unlink()
        except FileNotFoundError: pass
    contained = Path(paths["allowedInput"]).parent / "contained-write"
    with contained.open("xb") as stream: stream.write(b"CONTAINED")
    result["allowedWrite"] = contained.read_bytes() == b"CONTAINED"
    contained.unlink()
    result["allowedInput"] = Path(paths["allowedInput"]).read_bytes() == b"SHARED_INPUT"
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0 if all(result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
