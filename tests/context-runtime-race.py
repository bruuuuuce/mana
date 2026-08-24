#!/usr/bin/env python3
"""Adversarial CTX-03 reader and kernel-assisted publication regressions."""
from __future__ import annotations

import importlib.util
import errno
import json
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "lib" / "context-runtime.py"
SPEC = importlib.util.spec_from_file_location("mana_context_runtime_race", MODULE_PATH)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)


def expect_failure(action, invariant: str) -> None:
    try:
        action()
    except (runtime.ContractError, OSError):
        return
    raise AssertionError(f"operation did not fail closed: {invariant}")


def capture_oserror(action, invariant: str) -> OSError:
    try:
        action()
    except OSError as error:
        return error
    except runtime.ContractError as error:
        raise AssertionError(f"{invariant}: errno was not preserved") from error
    raise AssertionError(f"operation did not fail closed: {invariant}")


def capture_rollback_failure(action, invariant: str):
    try:
        action()
    except runtime.RollbackFailure as error:
        return error
    except (runtime.ContractError, OSError) as error:
        raise AssertionError(f"{invariant}: rollback failure was not distinguishable") from error
    raise AssertionError(f"operation returned success after incomplete rollback: {invariant}")


def assert_no_temps(root: Path) -> None:
    residue = [path for path in root.rglob(".*.tmp.*") if path.exists() or path.is_symlink()]
    assert not residue, f"temporary residue remains: {residue}"


def assert_rollback_contract(error, *, destination_state: str) -> None:
    metadata = error.as_dict()
    assert set(metadata) == {
        "category", "operation", "stage", "destination", "destinationState",
        "recoveryArtifact", "originalRecoveryArtifact", "stagingTemporary",
        "newContentMayRemain", "originalPreserved",
        "recoveryArtifactPermissionsRestricted", "underlyingErrno",
        "underlyingCause", "manualRecoveryRequired",
    }
    assert metadata["category"] == "publication-succeeded-rollback-failed"
    assert metadata["operation"] == "atomic-write"
    assert metadata["stage"] == "post-publication-parent-attestation"
    assert metadata["destination"] == "safe/checkpoint.json"
    assert not metadata["destination"].startswith("/")
    for name in ("recoveryArtifact", "originalRecoveryArtifact", "stagingTemporary"):
        assert metadata[name] is None or not metadata[name].startswith("/")
    assert metadata["destinationState"] == destination_state
    assert metadata["manualRecoveryRequired"] is True
    assert error.manual_recovery_required is True
    assert metadata["underlyingErrno"] == errno.EIO
    assert metadata["underlyingCause"] == "OSError"
    assert isinstance(error.__cause__, OSError)


def make_case(sandbox: Path, name: str) -> tuple[Path, Path, Path]:
    case = sandbox / name
    project, outside = case / "project", case / "outside"
    parent = project / "safe"
    parent.mkdir(parents=True)
    outside.mkdir(parents=True)
    return project, outside, parent


with tempfile.TemporaryDirectory(prefix="mana-context-race-") as name:
    # Tests pass a physical absolute path so the reader can reject every
    # symlink component instead of inheriting the host's /var -> /private/var.
    sandbox = Path(name).resolve()

    # Normal absent publication is exclusive and leaves no temporary entry.
    project, outside, parent = make_case(sandbox, "absent-success")
    target = parent / "checkpoint.json"
    runtime.atomic_write(project, "safe/checkpoint.json", {"state": "new"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "new"}
    assert_no_temps(project)

    # Missing libc/kernel primitives are an explicit unsupported-platform
    # failure, never a silent fallback to plain rename.
    project, outside, parent = make_case(sandbox, "unsupported-platform")
    original_primitives = runtime._RenamePrimitives

    class UnavailablePrimitives:
        available = False

    runtime._RenamePrimitives = UnavailablePrimitives
    expect_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "new"}),
        "missing kernel rename primitives",
    )
    runtime._RenamePrimitives = original_primitives
    assert not (parent / "checkpoint.json").exists()
    assert_no_temps(project)

    # Early parent swap: the parent has been opened and validated, but its
    # root-relative binding changes before destination inspection and the
    # final pre-publication check. The anchored directory is cleaned and no
    # write follows the replacement symlink.
    project, outside, parent = make_case(sandbox, "early-parent-swap")
    moved = project / "safe-moved"
    victim = outside / "victim.json"
    victim.write_text("outside-unchanged\n", encoding="utf-8")

    def early_parent(point: str) -> None:
        if point == "after-parent-open":
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)

    runtime._TEST_SYNC_HOOK = early_parent
    expect_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "new"}),
        "early parent swap before final validation",
    )
    runtime._TEST_SYNC_HOOK = None
    assert not (moved / "checkpoint.json").exists()
    assert not (outside / "checkpoint.json").exists()
    assert victim.read_text(encoding="utf-8") == "outside-unchanged\n"
    assert_no_temps(project)

    # The primitive can be present and invoked while the filesystem rejects
    # the requested operation. Exercise both semantic errno names even when
    # the current platform aliases them to the same numeric value.
    for unsupported_name in ("EOPNOTSUPP", "ENOTSUP"):
        unsupported_errno = getattr(errno, unsupported_name)

        for destination_exists in (False, True):
            suffix = "existing" if destination_exists else "absent"
            project, outside, parent = make_case(
                sandbox, f"filesystem-{unsupported_name.lower()}-{suffix}"
            )
            target = parent / "checkpoint.json"
            victim = outside / "victim.json"
            victim.write_text("outside-unchanged\n", encoding="utf-8")
            if destination_exists:
                target.write_text("original\n", encoding="utf-8")
            calls = {"noreplace": 0, "exchange": 0}

            class FilesystemUnsupportedPrimitives:
                available = True

                def noreplace(self, *args) -> None:
                    calls["noreplace"] += 1
                    raise OSError(unsupported_errno, unsupported_name)

                def exchange(self, *args) -> None:
                    calls["exchange"] += 1
                    raise OSError(unsupported_errno, unsupported_name)

            runtime._RenamePrimitives = FilesystemUnsupportedPrimitives
            error = capture_oserror(
                lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "new"}),
                f"filesystem returns {unsupported_name} for {suffix} destination",
            )
            runtime._RenamePrimitives = original_primitives
            assert error.errno == unsupported_errno
            if destination_exists:
                assert calls == {"noreplace": 0, "exchange": 1}
                assert target.read_text(encoding="utf-8") == "original\n"
            else:
                assert calls == {"noreplace": 1, "exchange": 0}
                assert not target.exists()
            assert victim.read_text(encoding="utf-8") == "outside-unchanged\n"
            assert_no_temps(project)

    # Early destination inode swap: inode A is inspected, then moved aside and
    # replaced by inode B before the final parent check. Exchange detects B,
    # atomically restores it, and leaves the separately saved A untouched.
    project, outside, parent = make_case(sandbox, "early-destination-inode-swap")
    target, saved = parent / "checkpoint.json", parent / "original-saved.json"
    victim = outside / "victim.json"
    target.write_text("original-a\n", encoding="utf-8")
    original_identity = target.stat().st_ino
    victim.write_text("outside-unchanged\n", encoding="utf-8")

    def early_destination(point: str) -> None:
        if point == "after-destination-inspection":
            target.rename(saved)
            target.write_text("replacement-b\n", encoding="utf-8")

    runtime._TEST_SYNC_HOOK = early_destination
    expect_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "new"}),
        "early destination inode replacement",
    )
    runtime._TEST_SYNC_HOOK = None
    assert target.read_text(encoding="utf-8") == "replacement-b\n"
    assert saved.read_text(encoding="utf-8") == "original-a\n"
    assert saved.stat().st_ino == original_identity
    assert victim.read_text(encoding="utf-8") == "outside-unchanged\n"
    assert_no_temps(project)

    # A destination created after the final inspection is not overwritten.
    project, outside, parent = make_case(sandbox, "late-destination-symlink")
    target, victim = parent / "checkpoint.json", outside / "victim.json"
    victim.write_text("outside-unchanged\n", encoding="utf-8")

    def late_destination(point: str) -> None:
        if point == "after-final-prepublish-check":
            target.symlink_to(victim)

    runtime._TEST_SYNC_HOOK = late_destination
    expect_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "new"}),
        "late destination symlink",
    )
    runtime._TEST_SYNC_HOOK = None
    assert target.is_symlink()
    assert victim.read_text(encoding="utf-8") == "outside-unchanged\n"
    assert_no_temps(project)

    # A parent swapped only after every pre-publication check is detected after
    # the kernel publish and rolled back through the anchored directory FD.
    project, outside, parent = make_case(sandbox, "late-parent-absent")
    moved = project / "safe-moved"

    def late_parent(point: str) -> None:
        if point == "after-final-prepublish-check":
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)

    runtime._TEST_SYNC_HOOK = late_parent
    expect_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "new"}),
        "late parent swap for absent destination",
    )
    runtime._TEST_SYNC_HOOK = None
    assert not (outside / "checkpoint.json").exists()
    assert not (moved / "checkpoint.json").exists()
    assert_no_temps(project)

    # Existing regular destinations use atomic exchange. Success replaces the
    # expected inode; post-publication parent failure restores the old content.
    project, outside, parent = make_case(sandbox, "existing-success")
    target = parent / "checkpoint.json"
    target.write_text("original\n", encoding="utf-8")
    runtime.atomic_write(project, "safe/checkpoint.json", {"state": "replacement"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "replacement"}
    assert_no_temps(project)

    project, outside, parent = make_case(sandbox, "late-parent-existing")
    target = parent / "checkpoint.json"
    target.write_text("original\n", encoding="utf-8")
    moved = project / "safe-moved"

    def late_parent_existing(point: str) -> None:
        if point == "after-final-prepublish-check":
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)

    runtime._TEST_SYNC_HOOK = late_parent_existing
    expect_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "replacement"}),
        "late parent swap for existing destination",
    )
    runtime._TEST_SYNC_HOOK = None
    assert (moved / "checkpoint.json").read_text(encoding="utf-8") == "original\n"
    assert not (outside / "checkpoint.json").exists()
    assert_no_temps(project)

    # Rollback failure with an initially absent destination. Publication uses
    # the first no-replace call; only the rollback no-replace call is injected
    # with EIO after post-publication attestation is forced to fail.
    project, outside, parent = make_case(sandbox, "rollback-failure-absent")
    target = parent / "checkpoint.json"
    victim = outside / "victim.json"
    victim.write_text("outside-unchanged\n", encoding="utf-8")
    original_same_directory = runtime._same_directory_from_root
    attestation_calls = [0]

    def fail_post_publication_attestation(*args, **kwargs) -> bool:
        attestation_calls[0] += 1
        result = original_same_directory(*args, **kwargs)
        return False if attestation_calls[0] == 2 else result

    class FailAbsentRollbackPrimitives:
        available = True

        def __init__(self) -> None:
            self.native = original_primitives()
            self.noreplace_calls = 0

        def noreplace(self, *args) -> None:
            self.noreplace_calls += 1
            if self.noreplace_calls == 2:
                raise OSError(errno.EIO, "injected rollback failure")
            self.native.noreplace(*args)

        def exchange(self, *args) -> None:
            self.native.exchange(*args)

    runtime._same_directory_from_root = fail_post_publication_attestation
    runtime._RenamePrimitives = FailAbsentRollbackPrimitives
    rollback_absent_error = capture_rollback_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "new"}),
        "rollback primitive failure for absent destination",
    )
    runtime._RenamePrimitives = original_primitives
    runtime._same_directory_from_root = original_same_directory
    assert_rollback_contract(rollback_absent_error, destination_state="new-content-published")
    assert rollback_absent_error.new_content_may_remain is True
    assert rollback_absent_error.original_preserved is False
    assert rollback_absent_error.recovery_artifact is None
    assert rollback_absent_error.original_recovery_artifact is None
    assert rollback_absent_error.staging_temporary is None
    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "new"}
    assert victim.read_text(encoding="utf-8") == "outside-unchanged\n"
    assert_no_temps(project)

    # Rollback failure with an existing destination. The first exchange
    # publishes new content; EIO is injected only into exchange-back. The old
    # inode is retained as the declared, mode-restricted recovery artifact.
    project, outside, parent = make_case(sandbox, "rollback-failure-existing")
    target = parent / "checkpoint.json"
    victim = outside / "victim.json"
    target.write_text("original-a\n", encoding="utf-8")
    original_inode = target.stat().st_ino
    victim.write_text("outside-unchanged\n", encoding="utf-8")
    attestation_calls = [0]

    class FailExistingRollbackPrimitives:
        available = True

        def __init__(self) -> None:
            self.native = original_primitives()
            self.exchange_calls = 0

        def noreplace(self, *args) -> None:
            self.native.noreplace(*args)

        def exchange(self, *args) -> None:
            self.exchange_calls += 1
            if self.exchange_calls == 2:
                raise OSError(errno.EIO, "injected rollback failure")
            self.native.exchange(*args)

    runtime._same_directory_from_root = fail_post_publication_attestation
    runtime._RenamePrimitives = FailExistingRollbackPrimitives
    rollback_existing_error = capture_rollback_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "new"}),
        "exchange-back failure for existing destination",
    )
    runtime._RenamePrimitives = original_primitives
    runtime._same_directory_from_root = original_same_directory
    assert_rollback_contract(
        rollback_existing_error,
        destination_state="new-content-published-original-displaced",
    )
    assert rollback_existing_error.new_content_may_remain is True
    assert rollback_existing_error.original_preserved is True
    assert rollback_existing_error.recovery_artifact is not None
    assert (
        rollback_existing_error.original_recovery_artifact
        == rollback_existing_error.recovery_artifact
    )
    assert rollback_existing_error.staging_temporary is None
    assert rollback_existing_error.recovery_permissions_restricted is True
    recovery = project / rollback_existing_error.recovery_artifact
    assert recovery.read_text(encoding="utf-8") == "original-a\n"
    assert recovery.stat().st_ino == original_inode
    assert stat.S_IMODE(recovery.stat().st_mode) == 0o600
    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "new"}
    assert victim.read_text(encoding="utf-8") == "outside-unchanged\n"
    residue = [path for path in project.rglob(".*.tmp.*") if path.exists()]
    assert residue == [recovery], f"unexpected staging residue: {residue}"

    # Removed, changed-inode, and symlink substitutions after inspection all
    # fail deterministically. Exchange rollback restores the observed attacker
    # entry and never follows it or modifies its outside referent.
    project, outside, parent = make_case(sandbox, "removed-late")
    target = parent / "checkpoint.json"
    target.write_text("original\n", encoding="utf-8")

    def remove_late(point: str) -> None:
        if point == "after-final-prepublish-check":
            target.unlink()

    runtime._TEST_SYNC_HOOK = remove_late
    expect_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "replacement"}),
        "destination removed after inspection",
    )
    runtime._TEST_SYNC_HOOK = None
    assert not target.exists()
    assert_no_temps(project)

    project, outside, parent = make_case(sandbox, "changed-inode-late")
    target, saved = parent / "checkpoint.json", parent / "original-saved.json"
    target.write_text("original\n", encoding="utf-8")

    def change_inode_late(point: str) -> None:
        if point == "after-final-prepublish-check":
            target.rename(saved)
            target.write_text("attacker-entry\n", encoding="utf-8")

    runtime._TEST_SYNC_HOOK = change_inode_late
    expect_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "replacement"}),
        "destination inode changed after inspection",
    )
    runtime._TEST_SYNC_HOOK = None
    assert target.read_text(encoding="utf-8") == "attacker-entry\n"
    assert saved.read_text(encoding="utf-8") == "original\n"
    assert_no_temps(project)

    project, outside, parent = make_case(sandbox, "existing-to-symlink-late")
    target, saved, victim = parent / "checkpoint.json", parent / "original-saved.json", outside / "victim.json"
    target.write_text("original\n", encoding="utf-8")
    victim.write_text("outside-unchanged\n", encoding="utf-8")

    def symlink_late(point: str) -> None:
        if point == "after-final-prepublish-check":
            target.rename(saved)
            target.symlink_to(victim)

    runtime._TEST_SYNC_HOOK = symlink_late
    expect_failure(
        lambda: runtime.atomic_write(project, "safe/checkpoint.json", {"state": "replacement"}),
        "existing destination replaced by symlink after inspection",
    )
    runtime._TEST_SYNC_HOOK = None
    assert target.is_symlink()
    assert saved.read_text(encoding="utf-8") == "original\n"
    assert victim.read_text(encoding="utf-8") == "outside-unchanged\n"
    assert_no_temps(project)

    # Initial symlink and non-regular destinations are never publication inputs.
    project, outside, parent = make_case(sandbox, "initial-specials")
    victim = outside / "victim.json"
    victim.write_text("outside-unchanged\n", encoding="utf-8")
    (parent / "checkpoint.json").symlink_to(victim)
    expect_failure(lambda: runtime.atomic_write(project, "safe/checkpoint.json", {}), "initial destination symlink")
    assert victim.read_text(encoding="utf-8") == "outside-unchanged\n"
    (parent / "checkpoint.json").unlink()
    (parent / "checkpoint.json").mkdir()
    expect_failure(lambda: runtime.atomic_write(project, "safe/checkpoint.json", {}), "initial non-regular destination")
    assert_no_temps(project)

    # Reader parent replacement during traversal cannot turn an old directory
    # FD into a successful read under a changed authorized namespace binding.
    project, outside, parent = make_case(sandbox, "reader-parent-race")
    nested = parent / "nested"
    nested.mkdir()
    source = nested / "input.json"
    source.write_text('{"bounded":true}\n', encoding="utf-8")
    moved = project / "safe-moved"
    # Absolute path components include private/tmp/.../project/safe/nested; use
    # the stable component immediately before the final nested directory.
    nonlocal_fired = [False]
    safe_index = list(source.parts[1:-1]).index("safe")

    def reader_swap_at_safe(point: str) -> None:
        if point == f"after-parent-component:{safe_index}" and not nonlocal_fired[0]:
            nonlocal_fired[0] = True
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)

    runtime._TEST_READ_SYNC_HOOK = reader_swap_at_safe
    expect_failure(lambda: runtime.safe_read_json(source), "reader parent replaced during traversal")
    runtime._TEST_READ_SYNC_HOOK = None
    assert nonlocal_fired[0]
    assert source.parent == nested
    assert not (outside / "input.json").exists()

print("Context Runtime CTX-03 race-safe reader/writer tests passed")
