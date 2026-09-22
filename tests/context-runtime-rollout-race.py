#!/usr/bin/env python3
"""Permanent CTX-10-R1A/R2.5 publication, recovery, and authority matrix."""
from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "scripts/context-runtime-rollout.py"
SPEC = importlib.util.spec_from_file_location("mana_ctx10_race", TOOL_PATH)
assert SPEC and SPEC.loader
rollout = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rollout
SPEC.loader.exec_module(rollout)
ctx = rollout._runtime_module()
TOOL = [sys.executable, str(TOOL_PATH)]


class ChildProcesses:
    """Bounded child ownership: failures cannot leak a lock holder."""
    def __init__(self) -> None:
        self.processes: list[subprocess.Popen[str]] = []

    def spawn(self, *args, **kwargs) -> subprocess.Popen[str]:
        process = subprocess.Popen(*args, **kwargs)
        self.processes.append(process)
        return process

    @staticmethod
    def result(process: subprocess.Popen[str], timeout: float = 30) -> tuple[str, str, int]:
        output, error = process.communicate(timeout=timeout)
        return output, error, process.returncode

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
        for process in self.processes:
            if process.poll() is None:
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)


def case(base: Path, name: str) -> tuple[Path, Path, Path]:
    project = base / name / "project"
    outside = base / name / "outside"
    parent = project / ".codex"
    parent.mkdir(parents=True)
    outside.mkdir(parents=True)
    (outside / "sentinel").write_bytes(b"outside-unchanged\n")
    return project, outside, parent


def expect_failure(action, label: str):
    try:
        action()
    except (ctx.ContractError, rollout.RolloutError, OSError) as error:
        return error
    raise AssertionError(f"expected failure: {label}")


def no_temporary(project: Path, *, recovery: Path | None = None) -> None:
    residue = [
        path for path in project.rglob("*")
        if (path.exists() or path.is_symlink()) and path != recovery
        and (".tmp." in path.name or ".stage." in path.name or ".abort." in path.name
             or "staging" in path.name or "quarantine" in path.name)
    ]
    assert residue == [], residue


def atomic(project: Path, payload: bytes, source=rollout._UNSET, fault: str | None = None) -> None:
    rollout._atomic_replace(
        project, ".codex/config.toml", payload, fault=fault, source=source
    )


def run_tool(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*TOOL, *args, "--project-root", str(project)],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=30,
    )


def decision_case(base: Path, name: str) -> tuple[Path, str, str, list[str]]:
    project = base / name / "decision-project"
    project.mkdir(parents=True)
    policy = {
        "schemaVersion": rollout.POLICY_VERSION,
        "defaultMode": "legacy",
        "profiles": {"authority": {"mode": "v2", "failClosed": True}},
    }
    rollout._atomic_replace(
        project, rollout.POLICY_RELATIVE, rollout._canonical(policy), source=None,
    )
    execution_id = "execution-race-" + name
    workspace_id = "W-" + hashlib.sha256(name.encode()).hexdigest()
    args = [
        "materialize-decision", "--profile", "authority",
        "--execution-id", execution_id, "--execution-version", "1",
        "--workspace-id", workspace_id,
    ]
    return project, execution_id, workspace_id, args


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mana-ctx10-r1a-") as temporary, ChildProcesses() as children:
        base = Path(temporary).resolve()

        # Absent and existing success use CTX-03 no-replace/exchange. Existing
        # mode and user bytes are preserved, and the host lock inode persists.
        project, outside, parent = case(base, "success")
        target = parent / "config.toml"
        atomic(project, b"created\n", source=None)
        assert target.read_bytes() == b"created\n"
        lock = project / rollout.LOCK_RELATIVE
        first_lock = lock.stat()
        assert stat.S_IMODE(first_lock.st_mode) == 0o600 and first_lock.st_size == 0
        os.chmod(target, 0o640)
        atomic(project, b"replacement\r\n", source=b"created\n")
        assert target.read_bytes() == b"replacement\r\n"
        assert stat.S_IMODE(target.stat().st_mode) == 0o640
        assert (lock.stat().st_dev, lock.stat().st_ino) == (
            first_lock.st_dev, first_lock.st_ino
        )
        no_temporary(project)
        assert (outside / "sentinel").read_bytes() == b"outside-unchanged\n"

        # Failure before publication and late destination appearance leave the
        # observed/or newly appeared destination untouched.
        project, outside, parent = case(base, "prepublication")
        target = parent / "config.toml"
        target.write_bytes(b"original\n")
        expect_failure(
            lambda: atomic(project, b"new\n", source=b"original\n", fault="before-publication"),
            "failure before publication",
        )
        assert target.read_bytes() == b"original\n"
        no_temporary(project)

        project, outside, parent = case(base, "late-appearance")
        target = parent / "config.toml"

        def late_destination(point: str) -> None:
            if point == "after-final-prepublish-check":
                target.write_bytes(b"late-owner\n")

        ctx._TEST_SYNC_HOOK = late_destination
        try:
            expect_failure(
                lambda: atomic(project, b"new\n", source=None),
                "late destination appearance",
            )
        finally:
            ctx._TEST_SYNC_HOOK = None
        assert target.read_bytes() == b"late-owner\n"
        no_temporary(project)

        # Early and late parent swaps cannot redirect publication through the
        # replacement symlink. The anchored old tree is cleaned or rolled back.
        for point, label in (
            ("after-parent-open", "early-parent-swap"),
            ("after-final-prepublish-check", "late-parent-swap"),
        ):
            project, outside, parent = case(base, label)
            moved = project / ".codex-moved"

            def swap_parent(observed: str, *, expected=point) -> None:
                if observed == expected:
                    parent.rename(moved)
                    parent.symlink_to(outside, target_is_directory=True)

            ctx._TEST_SYNC_HOOK = swap_parent
            try:
                expect_failure(
                    lambda: atomic(project, b"new\n", source=None), label
                )
            finally:
                ctx._TEST_SYNC_HOOK = None
            assert not (outside / "config.toml").exists()
            assert not (moved / "config.toml").exists()
            no_temporary(project)

        # Destination inode substitution is exchanged back exactly; the
        # separately saved original and outside sentinel are untouched.
        project, outside, parent = case(base, "destination-inode-swap")
        target = parent / "config.toml"
        saved = parent / "original-saved"
        target.write_bytes(b"original-a\n")

        def swap_destination(point: str) -> None:
            if point == "after-final-prepublish-check":
                target.rename(saved)
                target.write_bytes(b"attacker-b\n")

        ctx._TEST_SYNC_HOOK = swap_destination
        try:
            expect_failure(
                lambda: atomic(project, b"new\n", source=b"original-a\n"),
                "destination inode swap",
            )
        finally:
            ctx._TEST_SYNC_HOOK = None
        assert target.read_bytes() == b"attacker-b\n"
        assert saved.read_bytes() == b"original-a\n"
        no_temporary(project)

        # The exact post-publication sync point detects a pathname parent swap
        # and rolls back both absent and existing destinations through held FDs.
        for existing in (False, True):
            project, outside, parent = case(
                base, "post-publication-existing" if existing else "post-publication-absent"
            )
            target = parent / "config.toml"
            original = b"original\n" if existing else None
            if original is not None:
                target.write_bytes(original)
            moved = project / ".codex-moved"

            def swap_after_publish(point: str) -> None:
                if point == "after-publication-before-commit":
                    parent.rename(moved)
                    parent.symlink_to(outside, target_is_directory=True)

            ctx._TEST_SYNC_HOOK = swap_after_publish
            try:
                expect_failure(
                    lambda: atomic(project, b"new\n", source=original),
                    "post-publication parent swap",
                )
            finally:
                ctx._TEST_SYNC_HOOK = None
            assert not (outside / "config.toml").exists()
            if existing:
                assert (moved / "config.toml").read_bytes() == original
            else:
                assert not (moved / "config.toml").exists()
            no_temporary(project)

        # A post-publication injected failure demonstrates successful rollback
        # for absent and existing targets without ambiguous staging residue.
        for existing in (False, True):
            project, outside, parent = case(
                base, "rollback-success-existing" if existing else "rollback-success-absent"
            )
            target = parent / "config.toml"
            original = b"original\n" if existing else None
            if original is not None:
                target.write_bytes(original)
            expect_failure(
                lambda: atomic(
                    project, b"new\n", source=original,
                    fault="after-publication-pre-cleanup",
                ),
                "post-publication rollback",
            )
            assert (target.read_bytes() if target.exists() else None) == original
            no_temporary(project)

        # Rollback primitive failure is typed. With an existing destination the
        # exact original inode survives as a project-relative mode-0600 artifact.
        native_primitives = ctx._RenamePrimitives
        for existing in (False, True):
            project, outside, parent = case(
                base, "rollback-failure-existing" if existing else "rollback-failure-absent"
            )
            target = parent / "config.toml"
            original = b"original\n" if existing else None
            original_inode = None
            if original is not None:
                target.write_bytes(original)
                os.chmod(target, 0o640)
                original_inode = target.stat().st_ino

            class FailRollback:
                available = True

                def __init__(self) -> None:
                    self.native = native_primitives()
                    self.calls = 0

                def noreplace(self, *args) -> None:
                    self.calls += 1
                    if not existing and self.calls == 2:
                        raise OSError(errno.EIO, "injected rollback failure")
                    self.native.noreplace(*args)

                def exchange(self, *args) -> None:
                    self.calls += 1
                    if existing and self.calls == 2:
                        raise OSError(errno.EIO, "injected rollback failure")
                    self.native.exchange(*args)

            ctx._RenamePrimitives = FailRollback
            try:
                error = expect_failure(
                    lambda: atomic(
                        project, b"new\n", source=original,
                        fault="after-publication-pre-cleanup",
                    ),
                    "rollback primitive failure",
                )
            finally:
                ctx._RenamePrimitives = native_primitives
            assert isinstance(error, ctx.RollbackFailure)
            metadata = error.as_dict()
            assert metadata["manualRecoveryRequired"] is True
            assert metadata["destination"] == ".codex/config.toml"
            assert metadata["newContentMayRemain"] is True
            assert metadata["underlyingErrno"] == errno.EIO
            assert not metadata["destination"].startswith("/")
            if existing:
                assert metadata["originalPreserved"] is True
                assert metadata["recoveryArtifact"] == metadata["originalRecoveryArtifact"]
                recovery = project / metadata["recoveryArtifact"]
                assert recovery.read_bytes() == original
                assert recovery.stat().st_ino == original_inode
                assert stat.S_IMODE(recovery.stat().st_mode) == 0o600
                no_temporary(project, recovery=recovery)
            else:
                assert metadata["originalPreserved"] is False
                assert metadata["recoveryArtifact"] is None
                no_temporary(project)
            assert (outside / "sentinel").read_bytes() == b"outside-unchanged\n"

        # Unsupported primitives fail closed before publication.
        project, outside, parent = case(base, "unsupported")

        class Unsupported:
            available = False

        ctx._RenamePrimitives = Unsupported
        try:
            expect_failure(lambda: atomic(project, b"new\n", source=None), "unsupported primitive")
        finally:
            ctx._RenamePrimitives = native_primitives
        assert not (parent / "config.toml").exists()
        no_temporary(project)

        # Unsafe stable lock entries and lock-parent swaps fail before target
        # effects. Wrong mode is rejected rather than silently normalized.
        for kind in ("symlink", "fifo", "wrong-mode"):
            project, outside, parent = case(base, "unsafe-lock-" + kind)
            lock = project / rollout.LOCK_RELATIVE
            lock.parent.mkdir(parents=True)
            if kind == "symlink":
                lock.symlink_to(outside / "sentinel")
            elif kind == "fifo":
                os.mkfifo(lock)
            else:
                lock.write_bytes(b"")
                os.chmod(lock, 0o644)
            expect_failure(lambda: atomic(project, b"new\n", source=None), kind)
            assert not (parent / "config.toml").exists()
            assert (outside / "sentinel").read_bytes() == b"outside-unchanged\n"

        project, outside, parent = case(base, "lock-parent-swap")
        lock_parent = project / ".mana/context-runtime"
        moved_lock_parent = project / ".mana/context-runtime-moved"

        def swap_lock_parent(point: str) -> None:
            if point == "after-lock-acquired":
                lock_parent.rename(moved_lock_parent)
                lock_parent.symlink_to(outside, target_is_directory=True)

        ctx._TEST_LOCK_SYNC_HOOK = swap_lock_parent
        try:
            expect_failure(lambda: atomic(project, b"new\n", source=None), "lock parent swap")
        finally:
            ctx._TEST_LOCK_SYNC_HOOK = None
        assert not (parent / "config.toml").exists()
        assert not (outside / "config.toml").exists()

        # A process crash releases flock but does not remove/recreate the inode.
        project, outside, parent = case(base, "crashed-lock-holder")
        crash_code = """
import importlib.util, os, pathlib, sys
tool = pathlib.Path(sys.argv[1]); project = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location('crash_rollout', tool)
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
spec.loader.exec_module(module); ctx = module._runtime_module()
with ctx.stable_file_lock(project, module.LOCK_RELATIVE): os._exit(17)
"""
        crashed = subprocess.run(
            [sys.executable, "-c", crash_code, str(TOOL_PATH), str(project)],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=15,
        )
        assert crashed.returncode == 17
        lock = project / rollout.LOCK_RELATIVE
        crashed_inode = (lock.stat().st_dev, lock.stat().st_ino)
        atomic(project, b"after-crash\n", source=None)
        assert (lock.stat().st_dev, lock.stat().st_ino) == crashed_inode

        # Two concurrent bootstraps plus a third contender converge without a
        # lock-inode split or loss of user-owned bytes.
        project, outside, parent = case(base, "three-bootstrap")
        target = parent / "config.toml"
        user = b"# user-owned\r\n[custom]\r\nvalue = 1\r\n"
        target.write_bytes(user)
        processes = [
            children.spawn(
                [*TOOL, "bootstrap", "--project-root", str(project)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            for _ in range(3)
        ]
        results = [children.result(process) for process in processes]
        assert all(returncode == 0 for _out, _err, returncode in results), results
        assert target.read_bytes().startswith(user)
        assert (outside / "sentinel").read_bytes() == b"outside-unchanged\n"
        lock = project / rollout.LOCK_RELATIVE
        stable_inode = (lock.stat().st_dev, lock.stat().st_ino)
        again = run_tool(project, "bootstrap")
        assert again.returncode == 0, again.stderr
        assert (lock.stat().st_dev, lock.stat().st_ino) == stable_inode
        assert stat.S_IMODE(lock.stat().st_mode) == 0o600 and lock.stat().st_size == 0
        no_temporary(project)

        # Hold the first process exactly after LOCK_UN and before close. Two
        # later bootstraps (including the third contender) must acquire the
        # still-named same inode, proving there is no unlock/unlink split.
        project, outside, parent = case(base, "unlock-window")
        marker = base / "unlock-window.marker"
        release = base / "unlock-window.release"
        holder_code = """
import importlib.util, pathlib, sys, time
tool, project, marker, release = map(pathlib.Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location('holder_rollout', tool)
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
spec.loader.exec_module(module); ctx = module._runtime_module(); fired = [False]
def hook(point):
    if point == 'after-lock-release-before-close' and not fired[0]:
        fired[0] = True
        lock = project / module.LOCK_RELATIVE
        marker.write_text(str(lock.stat().st_ino), encoding='ascii')
        while not release.exists(): time.sleep(0.01)
ctx._TEST_LOCK_SYNC_HOOK = hook
raise SystemExit(module.main(['bootstrap', '--project-root', str(project)]))
"""
        holder = children.spawn(
            [
                sys.executable, "-c", holder_code, str(TOOL_PATH), str(project),
                str(marker), str(release),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        deadline = time.monotonic() + 10
        while not marker.exists() and holder.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), children.result(holder, timeout=5)
        window_inode = int(marker.read_text(encoding="ascii"))
        contenders = [
            children.spawn(
                [*TOOL, "bootstrap", "--project-root", str(project)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            for _ in range(2)
        ]
        contender_results = [children.result(process) for process in contenders]
        release.write_text("continue\n", encoding="ascii")
        holder_result = children.result(holder)
        assert holder_result[2] == 0, holder_result
        assert all(result[2] == 0 for result in contender_results), contender_results
        lock = project / rollout.LOCK_RELATIVE
        assert lock.stat().st_ino == window_inode
        assert stat.S_IMODE(lock.stat().st_mode) == 0o600 and lock.stat().st_size == 0
        assert (outside / "sentinel").read_bytes() == b"outside-unchanged\n"
        no_temporary(project)

        # Two production materializers for the same execution serialize on the
        # stable host lock, publish one immutable bundle/HEAD and return the
        # same decision without last-write-wins behavior.
        project, execution_id, workspace_id, decision_args = decision_case(
            base, "decision-concurrent",
        )
        user_owned = project / "user-owned.txt"
        user_owned.write_bytes(b"preserve-user-content\n")
        user_identity = (user_owned.stat().st_dev, user_owned.stat().st_ino,
                         user_owned.read_bytes())
        contenders = [
            children.spawn(
                [*TOOL, *decision_args, "--project-root", str(project)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            for _ in range(2)
        ]
        decisions = [children.result(process) for process in contenders]
        assert all(result[2] == 0 for result in decisions), decisions
        assert json.loads(decisions[0][0]) == json.loads(decisions[1][0])
        artifact = json.loads(decisions[0][0])
        identity_value = {key: artifact[key] for key in (
            "executionId", "executionVersion", "workspaceId", "profileId",
            "projectRootBinding",
        )}
        namespace = project / rollout._decision_namespace(identity_value)
        bundles = [path for path in (namespace / "bundles").iterdir() if not path.name.startswith(".")]
        assert len(bundles) == 1 and (namespace / "HEAD/decision-head-v1.json").is_file()
        lock = project / rollout.LOCK_RELATIVE
        lock_identity = (lock.stat().st_dev, lock.stat().st_ino)
        reused = run_tool(project, *decision_args)
        assert reused.returncode == 0 and json.loads(reused.stdout) == artifact
        assert (lock.stat().st_dev, lock.stat().st_ino) == lock_identity
        assert (user_owned.stat().st_dev, user_owned.stat().st_ino,
                user_owned.read_bytes()) == user_identity
        no_temporary(project)

        # A conflicting pair of complete pre-HEAD bundles is ambiguous.  The
        # production materializer refuses to choose either and creates no HEAD.
        project, execution_id, workspace_id, decision_args = decision_case(
            base, "decision-conflict",
        )
        identity_value = rollout._decision_identity(
            execution_id, 1, workspace_id, "authority", project,
        )
        policy_v2, _ = rollout.load_policy(project)
        assert policy_v2 is not None
        policy_shadow = json.loads(json.dumps(policy_v2))
        policy_shadow["profiles"]["authority"] = {"mode": "shadow", "failClosed": True}
        with ctx.stable_file_lock(project, rollout.LOCK_RELATIVE):
            rollout._publish_decision_bundle(
                project, identity_value, "authority", policy_v2,
                rollout._sha256(rollout._canonical(policy_v2)),
            )
            rollout._publish_decision_bundle(
                project, identity_value, "authority", policy_shadow,
                rollout._sha256(rollout._canonical(policy_shadow)),
            )
        conflict = run_tool(project, *decision_args)
        assert conflict.returncode == 2
        assert "CTX10_DECISION_AUTHORITY_REJECTED" in conflict.stderr
        namespace = project / rollout._decision_namespace(identity_value)
        assert not (namespace / "HEAD").exists()
        no_temporary(project)

        # Real process deaths cover complete staging, published bundle before
        # HEAD, the HEAD rename/CAS window, and committed HEAD before cleanup.
        crash_code = """
import importlib.util, os, pathlib, sys
tool, project, point, execution, workspace = sys.argv[1:]
spec = importlib.util.spec_from_file_location('crash_decision', pathlib.Path(tool))
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
spec.loader.exec_module(module)
def hook(observed):
    if observed == point: os._exit(71)
module._TEST_DECISION_HOOK = hook
raise SystemExit(module.main(['materialize-decision', '--project-root', project,
    '--profile', 'authority', '--execution-id', execution,
    '--execution-version', '1', '--workspace-id', workspace]))
"""
        for point in (
            "after-authority-initialization-staging",
            "after-authority-initialization",
            "after-bundle-staging",
            "after-bundle-publication-pre-head",
            "during-head-cas",
            "after-head-cas-pre-cleanup",
            "before-parent-commitment",
            "during-parent-cas",
            "after-parent-commit-pre-cleanup",
            "during-reconciliation",
        ):
            project, execution_id, workspace_id, decision_args = decision_case(
                base, "crash-" + point,
            )
            crashed = subprocess.run(
                [sys.executable, "-c", crash_code, str(TOOL_PATH), str(project),
                 point, execution_id, workspace_id],
                text=True, capture_output=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=30,
            )
            assert crashed.returncode == 71, (point, crashed.stderr)
            resolve_args = [
                "resolve", "--profile", "authority", "--execution-id", execution_id,
                "--execution-version", "1", "--workspace-id", workspace_id,
            ]
            observed = run_tool(project, *resolve_args)
            if point in {"during-parent-cas", "after-parent-commit-pre-cleanup"}:
                assert observed.returncode == 0, (point, observed.stderr)
            else:
                assert observed.returncode == 2
                assert "CTX10_DECISION_AUTHORITY_REJECTED" in observed.stderr
            recovered = run_tool(project, *decision_args)
            assert recovered.returncode == 0, (point, recovered.stderr)
            identity_value = {key: json.loads(recovered.stdout)[key] for key in (
                "executionId", "executionVersion", "workspaceId", "profileId",
                "projectRootBinding",
            )}
            namespace = project / rollout._decision_namespace(identity_value)
            bundles = [path for path in (namespace / "bundles").iterdir()
                       if not path.name.startswith(".")]
            assert len(bundles) == 1
            assert (namespace / "HEAD/decision-head-v1.json").is_file()
            no_temporary(project)

        # Interrupt a real reconciliation with an abandoned complete bundle
        # stage, then prove another retry cleans and converges from the intent.
        project, execution_id, workspace_id, decision_args = decision_case(
            base, "reconciliation-pending-stage",
        )
        for point in ("after-bundle-staging", "during-reconciliation"):
            crashed = subprocess.run(
                [sys.executable, "-c", crash_code, str(TOOL_PATH), str(project),
                 point, execution_id, workspace_id],
                text=True, capture_output=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=30,
            )
            assert crashed.returncode == 71, (point, crashed.stderr)
        identity_value = rollout._decision_identity(
            execution_id, 1, workspace_id, "authority", project)
        staged = project / rollout._decision_namespace(identity_value) / "bundles"
        assert any(".stage." in item.name for item in staged.iterdir())
        recovered = run_tool(project, *decision_args)
        assert recovered.returncode == 0, recovered.stderr
        no_temporary(project)

    print("Context Runtime CTX-10-R2.5 race, rollback recovery, stable-lock, external parent CAS, and crash matrix passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
