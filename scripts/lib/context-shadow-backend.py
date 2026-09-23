#!/usr/bin/env python3
"""Fixed native CTX-09C-R2A backend; failure never selects a weaker launcher."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path

NATIVE = Path("/usr/bin/sandbox-exec")

# A child of the live-shadow host is never a continuation of the caller's
# shell.  In particular, do not make a future provider adapter accidentally
# depend on a credential, a debug switch, or an arbitrary MANA_* setting that
# happened to be present when Mana was launched.  PATH is deliberately the
# sole inherited provider locator; test fixture controls are explicit names,
# rather than a wildcard, and exist only so the fixed offline fixtures can
# exercise byte/status recovery without a provider service.
PROVIDER_ENVIRONMENT_NAMES = ("PATH", "LANG", "LC_ALL", "TZ")
FIXTURE_ENVIRONMENT_NAMES = (
    "CTX09_ACTION", "CTX09_ARGV_CAPTURE", "CTX06C_FIXTURE_ROOT", "CTX06C_STATE_DIR",
    "CTX09C_R2B_STDOUT", "CTX09C_R2B_STDERR", "CTX09C_R2B_EXIT", "CTX09C_R2B_COUNT",
    "CTX09C_R2C_OUTPUT", "CTX09C_R2C_EXIT", "CTX09_CONFIG_CAPTURE",
)
HOST_ENVIRONMENT_VALUES = {
    "MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE": "false",
    "MANA_UPDATE_CHECK": "off",
    "MANA_CTX09_APPROVAL_COMPLETION": "disabled",
    "MANA_CTX09_SERVICE_DISCOVERY": "disabled",
    "PYTHONDONTWRITEBYTECODE": "1",
}


def host_environment(source=None, *, shadow=False):
    """Return the closed, host-owned child environment.

    Values are intentionally not recorded by this module or by callers.  The
    permitted names are a policy/provenance concern, while their values may be
    paths or locale details and must never become an artifact field.
    """
    source = os.environ if source is None else source
    env = {name: source[name] for name in PROVIDER_ENVIRONMENT_NAMES
           if isinstance(source.get(name), str) and source[name]}
    # These fixed local fixtures are the only explicit test transport.  Do
    # not generalize this to CTX09C_*, MANA_*, DEBUG, or arbitrary variables.
    env.update({name: source[name] for name in FIXTURE_ENVIRONMENT_NAMES
                if isinstance(source.get(name), str) and source[name]})
    env.update(HOST_ENVIRONMENT_VALUES)
    env["TMPDIR"] = "/private/tmp" if sys.platform == "darwin" else "/tmp"
    config_root = source.get("MANA_SHADOW_PROVIDER_CONFIG_ROOT")
    if isinstance(config_root, str) and config_root.startswith(("/private/tmp/", "/tmp/")):
        env["MANA_SHADOW_PROVIDER_CONFIG_ROOT"] = config_root
        env["CODEX_HOME"] = str(Path(config_root) / ".codex")
        env["CLAUDE_CONFIG_DIR"] = str(Path(config_root) / ".claude")
        env["OPENCODE_CONFIG_DIR"] = str(Path(config_root) / ".opencode")
    if isinstance(source.get("OPENCODE_CONFIG_CONTENT"), str):
        env["OPENCODE_CONFIG_CONTENT"] = source["OPENCODE_CONFIG_CONTENT"]
    if shadow:
        env["MANA_CTX09_SHADOW"] = "true"
    return env


def environment_provenance(*, shadow=False):
    """Safe policy-only projection; values are intentionally absent."""
    return {"policy": "ctx09c-host-allowlist-v1", "names": sorted(
        set(PROVIDER_ENVIRONMENT_NAMES) | set(FIXTURE_ENVIRONMENT_NAMES) |
        set(HOST_ENVIRONMENT_VALUES) | {"TMPDIR"} |
        ({"MANA_CTX09_SHADOW"} if shadow else set()))}


def read_roots():
    framework = Path(__file__).resolve().parents[2]
    # Executables, loader and installed host code; never the project or HOME.
    installed_code = [Path(path) for path in (
        "/opt/homebrew/Cellar", "/opt/homebrew/opt", "/usr/local/Cellar", "/usr/local/opt")
        if Path(path).is_dir()]
    host_tools = [Path(path) for path in ("/opt/homebrew/Cellar/bash", "/opt/homebrew/Cellar/jq",
        "/opt/homebrew/Cellar/oniguruma", "/usr/local/Cellar/bash", "/usr/local/Cellar/jq",
        "/usr/local/Cellar/oniguruma") if Path(path).is_dir()]
    bindings = [Path(sys.executable), Path(sys.base_prefix)] + [Path(path) for path in (
        "/opt/homebrew/bin/bash", "/opt/homebrew/bin/jq", "/opt/homebrew/bin/python3", "/opt/homebrew/opt/oniguruma",
        "/usr/local/bin/bash", "/usr/local/bin/jq", "/usr/local/bin/python3", "/usr/local/opt/oniguruma") if Path(path).exists()]
    python_packages = [parent for parent in Path(sys.base_prefix).resolve().parents
                       if parent.parent.name == "Cellar" and parent.name.startswith("python")]
    return python_packages + bindings + installed_code + host_tools + [Path(path) for path in ("/System/Library", "/System/Cryptexes/OS", "/System/Volumes/Preboot", "/usr/bin", "/usr/sbin", "/usr/lib", "/usr/share", "/bin", "/sbin", "/dev/null", "/dev/random", "/dev/urandom", "/dev/fd", "/dev/stdin", "/dev/stdout", "/dev/stderr", "/private/preboot", "/private/var/db/dyld", "/Library/Caches/com.apple.dyld")] + [
        Path(sys.base_prefix).resolve(), *[framework / name for name in
        ("scripts", "contracts", "profiles", "skills", "agents", "config")]]


def policy(scratch, run_root, metrics_root, extra_reads=()):
    quote = lambda path: json.dumps(str(path))
    writable = (scratch, run_root, metrics_root)
    readable = (*read_roots(), *writable, *extra_reads)
    aliases = [path for root in writable if Path(root).exists() for path in Path(root).rglob("*")
               if path.is_symlink() or (path.is_file() and path.stat().st_nlink != 1)]
    ancestors = sorted({parent for path in readable for parent in Path(path).parents}, key=str)
    def read_rule(path):
        return " (require-all (subpath " + quote(path) + ")" + "".join(
            " (require-not (literal " + quote(alias) + "))" for alias in aliases) + ")"
    return ("(version 1)(allow default)(deny file-read*)(deny file-write*)(deny network*)"
            '(deny mach-lookup)(allow mach-lookup (global-name "com.apple.dyld"))(deny ipc-posix-shm)(deny ipc-posix-sem)'
            '(allow file-read*'
            + "".join(read_rule(path) for path in readable) + "".join(" (literal " + quote(path) + ")" for path in ancestors) + ")"
            '(allow file-write* (literal "/dev/null")'
            + "".join(" (subpath " + quote(path) + ")" for path in writable) + ")")


def safe_tree(root):
    """No alias can import foreign bytes into a host-owned shadow read root."""
    root = Path(root)
    for parent in (root, *root.parents):
        if parent.is_symlink(): return False
    if not root.exists(): return False
    for path in (root, *root.rglob("*")):
        info = path.lstat()
        if path.is_symlink() or (path.is_file() and info.st_nlink != 1): return False
    return True


@dataclass(frozen=True)
class Admission:
    status: str
    reason: str | None
    scratch: Path | None = None
    sandbox_policy: str | None = None
    read_write_roots: tuple[Path, ...] = ()

    def invoke(self, argv, *, input_bytes, environment, cwd):
        if self.status != "available" or self.sandbox_policy is None:
            raise RuntimeError("unavailable shadow backend cannot invoke")
        if any(not safe_tree(root) for root in self.read_write_roots):
            raise RuntimeError("unsafe shadow read root")
        # No alternative backend, session launcher, or ambient completion
        # authority can be selected by provider configuration/environment.
        # Rebuild rather than subtract from `environment`: subtractive lists
        # always miss the next secret/debug knob.  Provider values stay in the
        # process only; no caller serializes this map.
        env = host_environment(environment, shadow=True)
        env.update(TMPDIR=str(self.scratch), MANA_PROVIDER_EXEC_TEMP_DIR=str(self.scratch))
        argv = list(argv)
        if argv and Path(argv[0]).resolve() == Path(sys.executable).resolve():
            argv[0] = str(Path(sys.executable).resolve())
        return execute_supervised([str(NATIVE), "-p", self.sandbox_policy, "--", *argv],
                                  input_bytes=input_bytes, environment=env, cwd=cwd,
                                  timeout_name="MANA_CTX09C_SHADOW_TIMEOUT_SECONDS")


@dataclass(frozen=True)
class ProcessResult:
    """Fully reaped process-group result.

    The status is deliberately a shell-compatible, host-owned value: timeout
    is 124 and host-observed INT/TERM are 130/143. The recovery host may retain
    legacy streams as sensitive local delivery artifacts; shadow streams are
    never durable recovery/delivery artifacts.
    """
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    interrupted_signal: int | None = None
    termination_kind: str = "exited"


def shadow_status(result):
    if getattr(result, "timed_out", False): return "timed_out"
    if getattr(result, "interrupted_signal", None) or result.returncode in (130, 143): return "interrupted"
    return "completed" if result.returncode == 0 else "failed"


def _positive_env(name, default):
    value = os.environ.get(name, str(default))
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _stop_group(process, grace):
    """TERM/KILL the whole session, then reap its leader.

    A leader exit is not accepted as completion while descendants can still
    write inherited descriptors or execute later.  `start_new_session` makes
    the leader PID the process-group ID on supported POSIX hosts.
    """
    group = process.pid
    try:
        os.killpg(group, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    try:
        os.killpg(group, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=max(1, grace + 1))
    except subprocess.TimeoutExpired:
        # The leader has already received KILL. Do not return a supposedly
        # terminal result while it is still unreaped.
        process.wait()


def execute_supervised(argv, *, input_bytes, environment, cwd, timeout_name,
                       timeout_default=30, grace_default=2):
    """Run an untrusted command in a fresh session with bounded group cleanup."""
    timeout = _positive_env(timeout_name, timeout_default)
    grace = _positive_env("MANA_CTX09C_KILL_GRACE_SECONDS", grace_default)
    with tempfile.TemporaryFile(prefix="mana-ctx09c-stdout-") as stdout, \
            tempfile.TemporaryFile(prefix="mana-ctx09c-stderr-") as stderr:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=stdout,
                                   stderr=stderr, env=environment, cwd=cwd,
                                   start_new_session=True)
        interrupted = []
        previous = {}

        def interrupted_handler(signum, _frame):
            interrupted.append(signum)
            _stop_group(process, grace)

        # These handlers belong to the supervising host, not the provider. A
        # post-legacy signal therefore becomes a shadow outcome and cannot
        # escape to replace a committed legacy result.
        if os.name == "posix":
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous[signum] = signal.getsignal(signum)
                signal.signal(signum, interrupted_handler)
        timed_out = False
        try:
            try:
                process.communicate(input_bytes, timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _stop_group(process, grace)
            if not timed_out and not interrupted:
                # Drain descendants even after a clean leader exit. This
                # prevents inherited stdout/stderr from producing late output.
                _stop_group(process, grace)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
        stdout.seek(0); output = stdout.read()
        stderr.seek(0); diagnostics = stderr.read()
    if timed_out:
        status = 124
    elif interrupted:
        status = 128 + interrupted[-1]
    elif process.returncode is not None and process.returncode < 0:
        status = 128 + (-process.returncode)
    else:
        status = process.returncode if process.returncode is not None else 1
    return ProcessResult(status, output, diagnostics, timed_out,
                         interrupted[-1] if interrupted else None,
                         "timed_out" if timed_out else "interrupted" if interrupted else
                         "signaled" if process.returncode is not None and process.returncode < 0 else "exited")


@contextmanager
def admit(run_root, metrics_root, *, scratch_path=None):
    """Prove the native read/write/network/service boundary before launch.

    A nested-sandbox denial, an unknown backend result or any failed proof is
    unavailable. The caller runs legacy independently of this admission.
    """
    if sys.platform != "darwin" or NATIVE.is_symlink() or not NATIVE.is_file():
        yield Admission("unavailable", "native-backend-absent")
        return
    parts = Path(run_root).parts
    if ".mana" in parts:
        project = Path(*parts[:parts.index(".mana")])
        namespace = project / ".mana/runtime"
        if any(root == namespace or root in namespace.parents for root in read_roots()):
            yield Admission("unavailable", "host-read-root-overlaps-runtime-namespace")
            return
    if not safe_tree(run_root) or not safe_tree(metrics_root):
        yield Admission("unavailable", "unsafe-shadow-read-root")
        return
    scratch_context = (tempfile.TemporaryDirectory(prefix="mana-ctx09c-shadow-", dir="/private/tmp")
                       if scratch_path is None else nullcontext(str(Path(scratch_path).resolve())))
    with scratch_context as temporary:
        scratch = Path(temporary).resolve()
        if scratch_path is None:
            os.chmod(scratch, 0o700)
        elif (not scratch.is_dir() or scratch.is_symlink()
              or (scratch.stat().st_mode & 0o777) != 0o700
              or scratch.stat().st_uid != os.getuid()):
            yield Admission("unavailable", "unsafe-backend-scratch")
            return
        provider_config = os.environ.get("MANA_SHADOW_PROVIDER_CONFIG_ROOT")
        extra_reads = (Path(provider_config),) if provider_config else ()
        if extra_reads and not safe_tree(extra_reads[0]):
            yield Admission("unavailable", "unsafe-provider-config-root")
            return
        fixed_policy = policy(scratch, run_root, metrics_root, extra_reads=extra_reads)
        with tempfile.TemporaryDirectory(prefix="mana-ctx09c-proof-", dir="/private/tmp") as outside:
            outside = Path(outside).resolve()
            probe_input = scratch / "input-proof"
            probe_input.write_bytes(b"SHARED_INPUT")
            read_canaries = {}
            for name in ("legacyHead", "legacyRunState", "legacyMetrics", "legacyOutput", "legacyBundles",
                         "legacyReceipts", "otherNamespace", "outsidePath"):
                path = outside / name
                path.write_bytes(b"LEGACY_CANARY")
                read_canaries[name] = str(path)
            volume_alias = Path("/System/Volumes/Data") / str(outside / "legacyHead").lstrip("/")
            if volume_alias.is_file(): read_canaries["systemVolumeAlias"] = str(volume_alias)
            symbolic, linked = scratch / "symlink-proof", scratch / "hardlink-proof"
            symbolic.symlink_to(outside / "legacyHead")
            os.link(outside / "legacyMetrics", linked)
            read_canaries.update(symlinkEscape=str(symbolic), hardlinkEscape=str(linked),
                parentTraversal=str(scratch / ".." / outside.name / "legacyHead"))
            denied, publish = outside / "external-write", outside / "local-publish"
            paths = {"publish": str(publish), "externalWrite": str(denied),
                     "reads": read_canaries, "allowedInput": str(probe_input)}
            probe_policy = policy(scratch, run_root, metrics_root, extra_reads=extra_reads)
            try:
                completed = subprocess.run([str(NATIVE), "-p", probe_policy, "--", sys.executable,
                    str(Path(__file__).resolve().parent / "context-shadow-boundary-probe.py")],
                    input=json.dumps(paths).encode(), capture_output=True, timeout=10,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                observations = json.loads(completed.stdout)
                proven = (completed.returncode == 0 and set(observations) == set(read_canaries) |
                          {"publish", "externalWrite", "network", "serviceDiscovery", "allowedInput", "allowedWrite", "dynamicHardlink", "dynamicSymlink"}
                          and all(value is True for value in observations.values())
                          and not denied.exists() and not publish.exists())
            except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
                proven = False
            finally:
                symbolic.unlink()
                linked.unlink()
                probe_input.unlink()
            if not proven:
                yield Admission("unavailable", "native-backend-unproven-or-denied")
                return
        yield Admission("available", None, scratch, fixed_policy, (scratch, Path(run_root), Path(metrics_root)))
