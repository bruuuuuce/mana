#!/usr/bin/env python3
"""CTX-09A host-only, local mode hand-offs; no semantic comparison or live v2."""
import argparse
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("ctx09_contract", Path(__file__).parent / "lib/context-runtime.py")
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
EXECUTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
NAMESPACE = ".mana/runtime/comparisons"
PRODUCERS = ".mana/runtime/producers"
_TEST_HOOK = None  # Import-only fault injection; never CLI/environment authority.


def sync(point):
    if _TEST_HOOK is not None:
        _TEST_HOOK(point)


def canonical(value):
    return runtime.canonical_bytes(value) + b"\n"


def relative_path(value):
    if not runtime.is_safe_relative_path(value) or any(ord(c) < 32 for c in value):
        raise runtime.ContractError("artifact path must be a safe project-relative path")
    return value.split("/")


def identity(fd):
    return runtime._entry_identity(os.fstat(fd))


def private_mkdir(name, parent):
    # The CLI is single-threaded; ensure restrictive caller umasks cannot make
    # the directory inaccessible before its descriptor can be acquired.
    previous = os.umask(0o077)
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
    finally:
        os.umask(previous)


@contextmanager
def publication_signals():
    def interrupted(number, frame):
        raise OSError(errno.EINTR, 'mode publication interrupted')
    previous = {number: signal.signal(number, interrupted) for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


class HostRoot:
    """Hold and re-attest the complete root ancestry, including root parents."""

    def __init__(self, supplied):
        self.nofollow, self.directory = runtime._require_secure_dir_fd_support()
        path = os.fspath(supplied)
        if not os.path.isabs(path):
            path = os.getcwd() + "/" + path
        self.parts = path.strip("/").split("/")
        if any(p in {"", ".", ".."} for p in self.parts):
            raise runtime.ContractError("host root must have canonical, non-traversing components")
        self.path = Path(path)
        self.fds = []
        self.created = []
        try:
            self.fds.append(self.open_dir("/"))
            for part in self.parts:
                self.fds.append(self.open_dir(part, self.fds[-1]))
            self.fd = self.fds[-1]
            if os.fstat(self.fd).st_uid != os.getuid():
                raise runtime.ContractError("project root must be host-owned")
            self.attest()
        except BaseException:
            self.close()
            raise

    def open_dir(self, name, parent=None):
        return runtime._open_directory(name, dir_fd=parent, nofollow=self.nofollow, directory=self.directory)

    def attest(self):
        current = self.open_dir("/")
        try:
            if identity(current) != identity(self.fds[0]):
                raise runtime.ContractError("host root anchor changed")
            for part, expected in zip(self.parts, self.fds[1:]):
                child = self.open_dir(part, current)
                os.close(current)
                current = child
                if identity(current) != identity(expected):
                    raise runtime.ContractError("host root binding changed")
        finally:
            os.close(current)

    @contextmanager
    def directory_fd(self, components, create=False, private=False):
        opened = [os.dup(self.fd)]
        try:
            for index, part in enumerate(components):
                parent = opened[-1]
                try:
                    child = self.open_dir(part, parent)
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        private_mkdir(part, parent)
                        made = True
                    except FileExistsError:
                        made = False
                    child = self.open_dir(part, parent)
                    if made:
                        os.fchmod(child, 0o700)
                        self.created.append((os.dup(parent), part, identity(child)))
                opened.append(child)
                metadata = os.fstat(child)
                if metadata.st_uid != os.getuid():
                    raise runtime.ContractError("mode-plan directory component must be host-owned")
                # .mana/runtime are shared with legacy. The comparison namespace
                # and every descendant must be private; never chmod existing state.
                if (private or (components[:3] in [NAMESPACE.split("/"), PRODUCERS.split("/")] and index >= 2)) and stat.S_IMODE(metadata.st_mode) != 0o700:
                    raise runtime.ContractError("mode-plan directory component must be mode 0700")
            yield opened[-1]
        finally:
            for fd in reversed(opened):
                os.close(fd)

    def attest_directory(self, components, expected, private=False):
        self.attest()
        with self.directory_fd(components, private=private) as current:
            if identity(current) != identity(expected):
                raise runtime.ContractError("mode-plan parent binding changed")

    def close(self):
        # Only empty, identity-matching directories created by this operation.
        for parent, name, expected in reversed(self.created):
            try:
                if runtime._verify_identity(parent, name, expected):
                    os.rmdir(name, dir_fd=parent)
            except OSError as error:
                if error.errno not in {errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST}:
                    raise
            finally:
                os.close(parent)
        self.created.clear()
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def file_instance(metadata):
    """Local filesystem/run identity, not a universal content address."""
    return {name: getattr(metadata, field) for name, field in (
        ("device", "st_dev"), ("inode", "st_ino"), ("mode", "st_mode"),
        ("size", "st_size"), ("mtime_ns", "st_mtime_ns"), ("ctime_ns", "st_ctime_ns"))}


def project_file(root, supplied, *, with_bytes=False, private=False, max_bytes=MAX_ARTIFACT_BYTES,
                 expected_instance=None, with_instance=False):
    """CTX-09B may parse the same captured bytes that this CTX-09A reader hashes.

    Defaults preserve the CTX-09A metadata-only API and its byte limit.
    """
    components = relative_path(supplied)
    with root.directory_fd(components[:-1]) as parent:
        fd = os.open(components[-1], os.O_RDONLY | os.O_NONBLOCK | root.nofollow, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise runtime.ContractError("compare source must be a regular single-link file")
            if ((with_bytes and before.st_uid != os.getuid())
                    or (private and stat.S_IMODE(before.st_mode) != 0o600)):
                raise runtime.ContractError("compare source ownership or permissions are invalid")
            if expected_instance is not None and file_instance(before) != expected_instance:
                raise runtime.ContractError("registered file instance mismatch")
            sync("source-opened")
            root.attest_directory(components[:-1], parent)
            digest, total, captured = hashlib.sha256(), 0, []
            while True:
                chunk = os.read(fd, 64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > min(max_bytes, MAX_ARTIFACT_BYTES):
                    raise runtime.ContractError("compare source exceeds byte limit")
                digest.update(chunk)
                if with_bytes:
                    captured.append(chunk)
                sync("source-chunk-read")
            after = os.fstat(fd)
            named = os.stat(components[-1], dir_fd=parent, follow_symlinks=False)
            fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            if (any(getattr(before, field) != getattr(after, field) for field in fields)
                    or any(getattr(named, field) != getattr(after, field) for field in fields)
                    or (expected_instance is not None and file_instance(after) != expected_instance)
                    or total != before.st_size):
                raise runtime.ContractError("compare source identity changed during read")
            root.attest_directory(components[:-1], parent)
            metadata = {"path": supplied, "sha256": digest.hexdigest()}
            if with_instance:
                metadata["fileInstance"] = file_instance(after)
            return (metadata, b"".join(captured)) if with_bytes else metadata
        finally:
            os.close(fd)


def absent(parent, name):
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise runtime.ContractError("mode artifact already exists")


RECEIPT_VERSION = "mana.context-runtime.producer-receipt/v1"
PRODUCER_CONTRACT = "mana.context-runtime.artifact-publication/v1"
COMMIT_VERSION = "mana.context-runtime.producer-commit/v1"


def receipt_location(execution_id, path):
    if not EXECUTION_ID.fullmatch(execution_id):
        raise runtime.ContractError("invalid producer execution identity")
    relative_path(path)
    key = hashlib.sha256(path.encode("utf-8")).hexdigest()
    return f"{PRODUCERS}/{execution_id}", key


def _read_record(root, path):
    metadata, payload = project_file(root, path, with_bytes=True, private=True, max_bytes=16 * 1024)
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise runtime.ContractError("duplicate producer field")
            result[key] = item
        return result
    def nonfinite(_):
        raise runtime.ContractError("non-finite producer value")
    value = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    if canonical(value) != payload:
        raise runtime.ContractError("producer record is not canonical")
    return metadata, value


def producer_source(root, execution_id, path, role, *, profile_id=None, target_key=None,
                    with_bytes=False, max_bytes=MAX_ARTIFACT_BYTES, execution_version=None):
    """Resolve only host-derived receipt/commit locations; never caller receipts."""
    namespace, key = receipt_location(execution_id, path)
    metadata, receipt = _read_record(root, f"{namespace}/{key}/producer-receipt-v1.json")
    _, commit = _read_record(root, f"{namespace}/{key}.commit/producer-commit-v1.json")
    fields = {"schemaVersion", "receiptId", "producerRuntime", "executionId", "executionVersion",
              "profileId", "targetKey", "artifact", "producerContractVersion"}
    if (not isinstance(receipt, dict) or set(receipt) != fields
            or receipt["schemaVersion"] != RECEIPT_VERSION
            or receipt["producerContractVersion"] != PRODUCER_CONTRACT
            or receipt["producerRuntime"] != role or role not in {"legacy", "v2"}
            or receipt["executionId"] != execution_id
            or not isinstance(receipt["profileId"], str) or not re.fullmatch("[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", receipt["profileId"])
            or not isinstance(receipt["targetKey"], str) or not re.fullmatch("[a-f0-9]{64}", receipt["targetKey"])
            or (role == "legacy" and receipt["executionVersion"] is not None)
            or (role == "v2" and (type(receipt["executionVersion"]) is not int or receipt["executionVersion"] < 1))
            or (execution_version is not None and receipt["executionVersion"] != execution_version)
            or (profile_id is not None and receipt["profileId"] != profile_id)
            or (target_key is not None and receipt["targetKey"] != target_key)):
        raise runtime.ContractError("producer receipt identity mismatch")
    identity_value = {k: v for k, v in receipt.items() if k != "receiptId"}
    receipt_id = hashlib.sha256(canonical(identity_value)).hexdigest()
    if receipt["receiptId"] != receipt_id or commit != {
            "schemaVersion": COMMIT_VERSION, "receiptId": receipt_id,
            "receiptDigest": metadata["sha256"], "executionId": execution_id, "artifactPath": path}:
        raise runtime.ContractError("producer receipt commitment mismatch")
    artifact = receipt["artifact"]
    if (not isinstance(artifact, dict) or set(artifact) != {"path", "sha256", "fileInstance"}
            or artifact["path"] != path):
        raise runtime.ContractError("producer artifact binding mismatch")
    validate_file_instance(artifact["fileInstance"])
    source, payload = project_file(root, path, with_bytes=True, with_instance=True,
                                   expected_instance=artifact["fileInstance"], max_bytes=max_bytes)
    if source != artifact:
        raise runtime.ContractError("producer artifact digest mismatch")
    reread, again = _read_record(root, metadata["path"])
    _, committed_again = _read_record(root, f"{namespace}/{key}.commit/producer-commit-v1.json")
    if reread != metadata or again != receipt or committed_again != commit:
        raise runtime.ContractError("producer receipt changed during artifact read")
    source.update(producerRuntime=role, producerReceiptDigest=metadata["sha256"],
                  profileId=receipt["profileId"], targetKey=receipt["targetKey"], executionVersion=receipt["executionVersion"])
    return (source, payload) if with_bytes else source


def validate_file_instance(value):
    if (not isinstance(value, dict) or set(value) != {"device", "inode", "mode", "size", "mtime_ns", "ctime_ns"}
            or any(type(item) is not int or item < 0 for item in value.values())
            or not stat.S_ISREG(value["mode"])):
        raise runtime.ContractError("invalid file-instance commitment")


def _publish_artifact_bytes(root, parent, components, payload):
    """CTX-03 FD-relative atomic no-replace publication; retain the real FD."""
    primitives = runtime._require_rename_primitives()
    name = ".producer-artifact.stage." + secrets.token_hex(16)
    fd, expected, published = None, None, False
    try:
        old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        try:
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | root.nofollow, 0o600, dir_fd=parent)
            expected = identity(fd)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
        os.fchmod(fd, 0o600)
        offset = 0
        while offset < len(payload):
            count = os.write(fd, payload[offset:])
            if count <= 0:
                raise OSError(errno.EIO, "short artifact write")
            offset += count
        os.fsync(fd)
        def attest(entry):
            before = os.fstat(fd)
            if (not runtime._verify_identity(parent, entry, expected)
                    or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600):
                raise runtime.ContractError("artifact publication identity changed")
            os.lseek(fd, 0, os.SEEK_SET)
            actual = bytearray()
            while len(actual) <= len(payload):
                chunk = os.read(fd, min(65536, len(payload) + 1 - len(actual)))
                if not chunk:
                    break
                actual.extend(chunk)
            after = os.fstat(fd)
            named = os.stat(entry, dir_fd=parent, follow_symlinks=False)
            if (bytes(actual) != payload or file_instance(before) != file_instance(after)
                    or file_instance(named) != file_instance(after) or named.st_nlink != 1):
                raise runtime.ContractError("artifact publication changed during read")
            root.attest_directory(components[:-1], parent, private=True)
            return file_instance(after)
        attest(name)
        sync("artifact-before-publication")
        root.attest_directory(components[:-1], parent, private=True)
        primitives.noreplace(parent, name, parent, components[-1])
        published = True
        sync("artifact-after-publication")
        instance = attest(components[-1])
        os.fsync(parent)
        artifact = {"path": "/".join(components), "sha256": hashlib.sha256(payload).hexdigest(),
                    "fileInstance": instance}
        retained = fd
        fd = None
        return retained, artifact
    except BaseException:
        if published:
            if not runtime._verify_identity(parent, components[-1], expected):
                raise runtime.ContractError("artifact rollback identity changed; host recovery required") from None
            primitives.noreplace(parent, components[-1], parent, name)
            published = False
        raise
    finally:
        if fd is not None:
            try:
                if not published and expected is not None and runtime._verify_identity(parent, name, expected):
                    os.unlink(name, dir_fd=parent)
                    os.fsync(parent)
            finally:
                os.close(fd)


def _publish_runtime_artifact(project_root, execution_id, profile_id, target_key, path, payload, role, execution_version):
    """Host publication primitive. Role is fixed by the runtime entry point.

    There is deliberately no CLI for attesting an existing caller artifact.
    A receipt alone is not committed: a separate immutable host record binds it.
    """
    namespace, key = receipt_location(execution_id, path)
    if (not isinstance(payload, bytes) or len(payload) > MAX_ARTIFACT_BYTES
            or not isinstance(profile_id, str) or not re.fullmatch("[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", profile_id)
            or not isinstance(target_key, str) or not re.fullmatch("[a-f0-9]{64}", target_key)
            or (role == "v2" and (type(execution_version) is not int or execution_version < 1))):
        raise runtime.ContractError("invalid host publication")
    with HostRoot(project_root) as root, publication_signals():
        with root.directory_fd(namespace.split("/"), create=True) as receipts:
            fcntl.flock(receipts, fcntl.LOCK_EX)
            absent(receipts, key)
            absent(receipts, key + ".commit")
            components = relative_path(path)
            with root.directory_fd(components[:-1], create=True, private=True) as parent:
                root.attest_directory(components[:-1], parent, private=True)
                fd, artifact = _publish_artifact_bytes(root, parent, components, payload)
                expected = identity(fd)
                try:
                    instance = artifact["fileInstance"]
                    current, actual = project_file(root, path, with_bytes=True, with_instance=True,
                                                   private=True, expected_instance=instance)
                    if actual != payload or current != artifact:
                        raise runtime.ContractError("published artifact bytes mismatch")
                    receipt = {"schemaVersion": RECEIPT_VERSION, "producerRuntime": role,
                               "executionId": execution_id,
                               "executionVersion": execution_version,
                               "profileId": profile_id, "targetKey": target_key, "artifact": artifact,
                               "producerContractVersion": PRODUCER_CONTRACT}
                    receipt["receiptId"] = hashlib.sha256(canonical(receipt)).hexdigest()
                    publish(root, receipts, key, receipt, namespace=namespace, filename="producer-receipt-v1.json")
                    # Re-attest the object and anchored path before the commit.
                    current = project_file(root, path, with_instance=True, expected_instance=instance, private=True)
                    if current != artifact:
                        raise runtime.ContractError("artifact changed before producer commit")
                    commit = {"schemaVersion": COMMIT_VERSION, "receiptId": receipt["receiptId"],
                              "receiptDigest": hashlib.sha256(canonical(receipt)).hexdigest(),
                              "executionId": execution_id, "artifactPath": path}
                    publish(root, receipts, key + ".commit", commit, namespace=namespace,
                            filename="producer-commit-v1.json")
                    producer_source(root, execution_id, path, role, profile_id=profile_id, target_key=target_key)
                    os.fsync(parent)
                except BaseException:
                    # Orphan receipts are not authority and cannot be reused.
                    if runtime._verify_identity(parent, components[-1], expected):
                        os.unlink(components[-1], dir_fd=parent)
                        os.fsync(parent)
                    raise
                finally:
                    os.close(fd)


def publish_legacy_artifact(project_root, execution_id, profile_id, target_key, path, payload):
    return _publish_runtime_artifact(project_root, execution_id, profile_id, target_key, path, payload, "legacy", None)


def publish_v2_artifact(project_root, execution_id, profile_id, target_key, path, payload, *, execution_version):
    return _publish_runtime_artifact(project_root, execution_id, profile_id, target_key, path, payload, "v2", execution_version)


def publish(root, parent, execution_id, value, *, namespace=NAMESPACE, filename="mode-plan-v1.json"):
    payload = canonical(value)  # Fail before creating any final/staging entry.
    primitives = runtime._require_rename_primitives()
    root.attest_directory(namespace.split("/"), parent)
    absent(parent, execution_id)
    name = ".mode-plan.stage." + secrets.token_hex(16)
    fd, stage_identity = None, None
    published = False
    try:
        # Defer handled signals over mkdir/open so cleanup always has an anchor.
        old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        try:
            private_mkdir(name, parent)
            stage_identity = runtime._entry_identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
            fd = root.open_dir(name, parent)
            if identity(fd) != stage_identity:
                raise runtime.ContractError("mode staging identity changed during creation")
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
        os.fchmod(fd, 0o700)
        file_fd = os.open(filename, os.O_RDWR | os.O_CREAT | os.O_EXCL | root.nofollow, 0o600, dir_fd=fd)
        try:
            os.fchmod(file_fd, 0o600)
            offset = 0
            while offset < len(payload):
                sync("before-stage-write")
                count = os.write(file_fd, payload[offset:])
                if count <= 0:
                    raise OSError(errno.EIO, "short staged write")
                offset += count
            os.fsync(file_fd)
            file_identity = identity(file_fd)
            def attest_payload():
                metadata = os.fstat(file_fd)
                if (not runtime._verify_identity(fd, filename, file_identity)
                        or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != 0o600
                        or stat.S_IMODE(os.fstat(fd).st_mode) != 0o700
                        or sorted(os.listdir(fd)) != [filename]):
                    raise runtime.ContractError("mode payload identity or permissions changed")
                os.lseek(file_fd, 0, os.SEEK_SET)
                actual = bytearray()
                while len(actual) <= len(payload):
                    chunk = os.read(file_fd, min(65536, len(payload) + 1 - len(actual)))
                    if not chunk:
                        break
                    actual.extend(chunk)
                if bytes(actual) != payload:
                    raise runtime.ContractError("mode payload bytes changed")
                after = os.fstat(file_fd)
                if (any(getattr(metadata, field) != getattr(after, field)
                        for field in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"))
                        or not runtime._verify_identity(fd, filename, file_identity)):
                    raise runtime.ContractError("mode payload changed during attestation")
            os.fsync(fd)
            sync("before-publication")
            root.attest_directory(namespace.split("/"), parent)
            if not runtime._verify_identity(parent, name, stage_identity):
                raise runtime.ContractError("mode staging identity changed")
            attest_payload()
            primitives.noreplace(parent, name, parent, execution_id)
            published = True
            sync("after-publication")
            root.attest_directory(namespace.split("/"), parent)
            if not runtime._verify_identity(parent, execution_id, stage_identity):
                raise runtime.ContractError("mode publication identity changed")
            os.fsync(parent)
            sync("before-commit")
            root.attest_directory(namespace.split("/"), parent)
            attest_payload()
        finally:
            os.close(file_fd)
    except BaseException:
        if published:
            primitives.noreplace(parent, execution_id, parent, name)
            published = False
            if not runtime._verify_identity(parent, name, stage_identity):
                primitives.noreplace(parent, name, parent, execution_id)
                raise runtime.ContractError("mode rollback identity changed; host recovery required")
        raise
    finally:
        try:
            if not published and stage_identity is not None and runtime._verify_identity(parent, name, stage_identity):
                if fd is not None:
                    runtime._remove_directory_contents(fd, root.nofollow, root.directory)
                os.rmdir(name, dir_fd=parent)
                os.fsync(parent)
        finally:
            if fd is not None:
                os.close(fd)


def shadow_policy(scratch, metrics):
    quote = lambda path: json.dumps(str(path))
    return ('(version 1)(allow default)(deny file-write*)(deny network*)'
            '(allow file-write* (literal "/dev/null") (subpath ' + quote(scratch) + ')'
            ' (subpath ' + quote(metrics) + '))')


def shadow_legacy(root, command):
    # A fixed host backend contains the entire legacy process and descendants,
    # including MCP/services. There is no caller backend or prompt-only fallback.
    backend = Path("/usr/bin/sandbox-exec")
    if sys.platform != "darwin" or backend.is_symlink() or not backend.is_file():
        raise runtime.ContractError("shadow host write/network isolation is unavailable")
    with root.directory_fd([".mana", "runtime", "metrics"], create=True) as metrics:
        root.attest_directory([".mana", "runtime", "metrics"], metrics)
        with tempfile.TemporaryDirectory(prefix="mana-shadow-", dir="/private/tmp") as temporary:
            scratch = Path(temporary).resolve()
            os.chmod(scratch, 0o700)
            policy = shadow_policy(scratch, root.path / ".mana/runtime/metrics")
            with tempfile.TemporaryDirectory(prefix="mana-shadow-probe-", dir="/private/tmp") as outside:
                os.chmod(outside, 0o700)
                probe = subprocess.run([str(backend), "-p", policy, "--", sys.executable, "-c",
                    "import os,sys;\ntry: os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT,0o600)\n"
                    "except PermissionError: sys.exit(0)\nelse: sys.exit(1)",
                    str(Path(outside).resolve() / "denied")], capture_output=True)
                if probe.returncode != 0:
                    raise runtime.ContractError("shadow host isolation probe failed")
            environment = os.environ.copy()
            for key in list(environment):
                if key.startswith("MANA_CTX07B_ISOLATION_") or key == "MANA_PROVIDER_SESSION_LAUNCHER":
                    del environment[key]
            environment.update(TMPDIR=str(scratch), MANA_PROVIDER_EXEC_TEMP_DIR=str(scratch),
                               MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE="false", MANA_UPDATE_CHECK="off")
            root.attest()
            return subprocess.call([str(backend), "-p", policy, "--", *command], env=environment)


def main():
    parser = argparse.ArgumentParser(description="CTX-09A host-local hand-off")
    parser.add_argument("mode", choices=("shadow", "compare", "shadow-preflight", "shadow-run"))
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--legacy-artifact")
    parser.add_argument("--v2-artifact")
    parser.add_argument("--legacy-exit-status", type=int)
    parser.add_argument("--profile-id")
    parser.add_argument("--target-key")
    argv = sys.argv[1:]
    separator = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:separator])
    args.command = argv[separator + 1:]
    if not EXECUTION_ID.fullmatch(args.execution_id) or (args.legacy_exit_status is not None and not 0 <= args.legacy_exit_status <= 255):
        raise runtime.ContractError("invalid execution identity or legacy exit status")
    if (args.mode == "shadow") != (args.legacy_exit_status is not None):
        raise runtime.ContractError("explicit legacy exit status is required only for host shadow registration")
    value = {"schemaVersion": "mana.context-runtime.mode-plan/v1", "executionId": args.execution_id,
             "mode": "shadow" if args.mode.startswith("shadow") else "compare",
             "authority": "none" if args.mode == "compare" else "legacy",
             "externalActions": "disabled", "permissionGrant": "none", "comparison": "deferred-ctx-09b"}
    legacy_status = None
    try:
        with HostRoot(args.project_root) as root:
            if args.mode == "shadow-preflight":
                if args.legacy_artifact or args.v2_artifact or args.command:
                    raise runtime.ContractError("shadow preflight accepts no artifacts or command")
                try:
                    with root.directory_fd(NAMESPACE.split("/")) as parent:
                        root.attest_directory(NAMESPACE.split("/"), parent)
                        absent(parent, args.execution_id)
                except FileNotFoundError:
                    pass
                return 0
            if args.mode == "compare":
                if not args.legacy_artifact or not args.v2_artifact or args.command:
                    raise runtime.ContractError("compare requires --legacy-runtime-artifact and --v2-runtime-artifact")
                if not args.profile_id or not args.target_key or not re.fullmatch("[a-f0-9]{64}", args.target_key):
                    raise runtime.ContractError("compare requires expected host profile and target identity")
                legacy = producer_source(root, args.execution_id, args.legacy_artifact, "legacy",
                                         profile_id=args.profile_id, target_key=args.target_key)
                v2 = producer_source(root, args.execution_id, args.v2_artifact, "v2",
                                     profile_id=args.profile_id or legacy["profileId"],
                                     target_key=args.target_key or legacy["targetKey"])
                value["artifacts"] = {"legacy": legacy, "v2": v2}
            else:
                if args.legacy_artifact or args.v2_artifact:
                    raise runtime.ContractError("shadow accepts no comparison artifacts")
                value.update(v2Execution="deferred-ctx-09c", publication="disabled")
            with root.directory_fd(NAMESPACE.split("/"), create=True) as parent:
                fcntl.flock(parent, fcntl.LOCK_EX)
                root.attest_directory(NAMESPACE.split("/"), parent)
                absent(parent, args.execution_id)
                if args.mode == "shadow-run":
                    command = args.command[1:] if args.command[:1] == ["--"] else args.command
                    expected = Path(__file__).parent / "run-profile.sh"
                    if not command or command[0] != str(expected):
                        raise runtime.ContractError("shadow-run requires the installed legacy host entry point")
                    legacy_status = shadow_legacy(root, [*command, "--context-runtime", "legacy"])
                    if legacy_status < 0:
                        legacy_status = 128 - legacy_status
                elif args.command:
                    raise runtime.ContractError("mode artifact writer accepts no command")
                if args.mode != "compare":
                    status = args.legacy_exit_status if legacy_status is None else legacy_status
                    value["legacyExecution"] = {"status": "completed" if status == 0 else "failed", "exitStatus": status}
                else:
                    for role, source in value["artifacts"].items():
                        current = producer_source(root, args.execution_id, source["path"], role,
                                                  profile_id=args.profile_id, target_key=args.target_key,
                                                  execution_version=source["executionVersion"])
                        if current != source:
                            raise runtime.ContractError("producer binding changed before registration")
                with publication_signals():
                    publish(root, parent, args.execution_id, value)
    except (runtime.ContractError, OSError, UnicodeError, ValueError, TypeError) as error:
        # No provider/body/error-string persistence; legacy authority survives
        # a local registration failure. Pre-execution failures remain closed.
        if legacy_status is None:
            raise
        print(canonical({"mode": "shadow", "handOff": "failed", "category": type(error).__name__,
                         "legacyExitStatus": legacy_status, "v2Execution": "deferred-ctx-09c"}).decode(), end="", file=sys.stderr)
        return legacy_status
    result = {"mode": value["mode"], "modePlan": f"{NAMESPACE}/{args.execution_id}/mode-plan-v1.json",
              "execution": "none" if legacy_status is None else "legacy", "handOff": "registered"}
    print(canonical(result).decode(), end="", file=sys.stderr if legacy_status is not None else sys.stdout)
    return 0 if legacy_status is None else legacy_status


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (runtime.ContractError, OSError, UnicodeError, ValueError, TypeError) as error:
        print(f"ERROR: {error}" if isinstance(error, runtime.ContractError) else f"ERROR: mode hand-off failed ({type(error).__name__})", file=sys.stderr)
        raise SystemExit(2)
