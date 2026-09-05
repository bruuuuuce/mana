#!/usr/bin/env python3
"""Deterministic CTX-06A materialization/interruption cleanup regressions."""

from __future__ import annotations

import atexit
import importlib.util
import io
import os
import signal
import stat
import sys
import tempfile
from contextlib import redirect_stderr
from pathlib import Path


owned_temporary: tempfile.TemporaryDirectory[str] | None = None
if len(sys.argv) == 1:
    repository_root = Path(__file__).resolve().parents[1]
    module_path = repository_root / "scripts/lib/context-pipeline.py"
    framework = repository_root / "tests/fixtures/context-runtime/ctx06a-framework"
    owned_temporary = tempfile.TemporaryDirectory(prefix="mana-ctx06a-faults-")
    atexit.register(owned_temporary.cleanup)
    root = Path(owned_temporary.name).resolve()
elif len(sys.argv) == 4:
    module_path, framework, root = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
else:
    raise SystemExit(
        "usage: context-runtime-phase-runner-faults.py [MODULE FRAMEWORK TEMP_ROOT]"
    )
spec = importlib.util.spec_from_file_location("mana_context_pipeline_faults", module_path)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load pipeline module")
pipeline = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pipeline
spec.loader.exec_module(pipeline)


def arguments(project: Path, execution: str) -> list[str]:
    return [
        "context-pipeline.py", "initialize", "ctx06a-fixture",
        "--framework-root", str(framework), "--project-root", str(project),
        "--execution-id", execution, "--provider", "codex",
        "--workspace", ".mana/sessions/ctx06a-fixture",
        "--objective", "Inspect the bounded fixture.",
        "--target-repository", "mana", "--target-base", "main",
        "--target-pr-number", "17",
    ]


def prepare(name: str) -> Path:
    project = root / name
    workspace = project / ".mana/sessions/ctx06a-fixture"
    workspace.mkdir(parents=True)
    (workspace / "manifest.yaml").write_text(
        'workspace_type: "session"\nworkspace_id: "ctx06a-fixture"\n', encoding="utf-8")
    (project / "outside.txt").write_text("outside-sentinel\n", encoding="utf-8")
    return project


def assert_clean(project: Path, execution: str) -> None:
    runs = project / ".mana/runtime/runs"
    if os.path.lexists(runs / execution):
        raise AssertionError(f"failure published final run {execution}")
    if runs.exists() and any(
        path.name.startswith(".") and marker in path.name
        for path in runs.iterdir() for marker in (".stage.", ".abort.")
    ):
        raise AssertionError(f"failure left staging or quarantine for {execution}")
    if (project / "outside.txt").read_text(encoding="utf-8") != "outside-sentinel\n":
        raise AssertionError(f"failure modified outside sentinel for {execution}")


def assert_private_staging(project: Path) -> None:
    runs = project / ".mana/runtime/runs"
    stages = [path for path in runs.iterdir()
              if path.name.startswith(".") and ".stage." in path.name]
    if len(stages) != 1 or stat.S_IMODE(stages[0].stat().st_mode) != 0o700:
        raise AssertionError("initializer did not use exactly one private mode-0700 staging directory")


for failure_index in (1, 2, 4):
    execution = f"execution-materialize-failure-{failure_index}"
    project = prepare(execution)

    def fail_at(index: int, _total: int, expected: int = failure_index) -> None:
        if index == expected:
            assert_private_staging(project)
            raise pipeline.runtime.ContractError("injected materialization failure")

    pipeline._TEST_MATERIALIZE_HOOK = fail_at
    try:
        pipeline.initialize(pipeline.parser().parse_args(arguments(project, execution)[1:]))
    except pipeline.runtime.ContractError:
        pass
    else:
        raise AssertionError("injected materialization failure was accepted")
    assert_clean(project, execution)

execution = "execution-keyboard-interrupt"
project = prepare(execution)


def keyboard_interrupt(_index: int, _total: int) -> None:
    assert_private_staging(project)
    raise KeyboardInterrupt


pipeline._TEST_MATERIALIZE_HOOK = keyboard_interrupt
try:
    pipeline.initialize(pipeline.parser().parse_args(arguments(project, execution)[1:]))
except KeyboardInterrupt:
    pass
else:
    raise AssertionError("KeyboardInterrupt was accepted")
assert_clean(project, execution)

pipeline._TEST_MATERIALIZE_HOOK = None

# Signals observed before the publish syscall abort without making the final
# name visible.
for signum in (signal.SIGINT, signal.SIGTERM):
    execution = f"execution-signal-before-publication-{signum}"
    project = prepare(execution)

    def send_before(stage: str, selected: int = signum) -> None:
        if stage != "before-publication":
            return
        assert_private_staging(project)
        os.kill(os.getpid(), selected)

    pipeline._TEST_PUBLICATION_HOOK = send_before
    status = pipeline.main(arguments(project, execution))
    if status != 128 + signum:
        raise AssertionError(f"pre-publication signal {signum} returned {status}")
    assert_clean(project, execution)

# Signals delivered from inside the publication method are recorded by the
# guard; after the syscall completes the final entry is atomically moved to a
# private abort name and removed through the held staging FD.
original_primitives = pipeline.runtime._require_rename_primitives
for signum in (signal.SIGINT, signal.SIGTERM):
    execution = f"execution-signal-during-publication-{signum}"
    project = prepare(execution)
    delegate = original_primitives()

    class SignallingPrimitives:
        def __init__(self) -> None:
            self.sent = False

        def noreplace(self, *args: object) -> None:
            if not self.sent:
                self.sent = True
                os.kill(os.getpid(), signum)
            delegate.noreplace(*args)

    wrapper = SignallingPrimitives()
    pipeline.runtime._require_rename_primitives = lambda: wrapper
    pipeline._TEST_PUBLICATION_HOOK = None
    try:
        status = pipeline.main(arguments(project, execution))
    finally:
        pipeline.runtime._require_rename_primitives = original_primitives
    if status != 128 + signum:
        raise AssertionError(f"publication signal {signum} returned {status}")
    assert_clean(project, execution)

# Signals delivered immediately after the kernel no-replace syscall, before
# publish_noreplace can record or attest the final name, remain pre-barrier and
# must revoke the visible final entry.
for signum in (signal.SIGINT, signal.SIGTERM):
    execution = f"execution-signal-after-publish-syscall-{signum}"
    project = prepare(execution)
    delegate = original_primitives()

    class AfterPublishSyscallPrimitives:
        def __init__(self) -> None:
            self.sent = False

        def noreplace(self, *args: object) -> None:
            delegate.noreplace(*args)
            if not self.sent:
                self.sent = True
                os.kill(os.getpid(), signum)

    wrapper = AfterPublishSyscallPrimitives()
    pipeline.runtime._require_rename_primitives = lambda: wrapper
    pipeline._TEST_PUBLICATION_HOOK = None
    try:
        status = pipeline.main(arguments(project, execution))
    finally:
        pipeline.runtime._require_rename_primitives = original_primitives
    if status != 128 + signum:
        raise AssertionError(f"post-publish-syscall signal {signum} returned {status}")
    assert_clean(project, execution)

# Signals after the explicit barrier are not pre-commit aborts. Exercise both
# the guarded post-barrier point and the outer-handler window after the guard:
# both report committed state and retain the complete final run.
for signal_stage in ("after-commit-barrier", "after-publication-guard"):
    for signum in (signal.SIGINT, signal.SIGTERM):
        execution = f"execution-signal-{signal_stage}-{signum}"
        project = prepare(execution)

        def send_after_commit(
            stage: str, selected: int = signum, selected_stage: str = signal_stage,
        ) -> None:
            if stage == selected_stage:
                os.kill(os.getpid(), selected)

        pipeline._TEST_PUBLICATION_HOOK = send_after_commit
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            status = pipeline.main(arguments(project, execution))
        if status != 128 + signum:
            raise AssertionError(
                f"post-barrier signal {signum} at {signal_stage} returned {status}")
        runs = project / ".mana/runtime/runs"
        if not (runs / execution).is_dir():
            raise AssertionError(
                f"post-barrier signal {signum} at {signal_stage} removed the committed run")
        if any(marker in path.name for path in runs.iterdir()
               for marker in (".stage.", ".abort.")):
            raise AssertionError(
                f"post-barrier signal {signum} at {signal_stage} left private residue")
        if (project / "outside.txt").read_text(encoding="utf-8") != "outside-sentinel\n":
            raise AssertionError(
                f"post-barrier signal {signum} at {signal_stage} modified outside sentinel")
        expected = f"interrupted by signal {signum} after commit; run remains committed"
        if expected not in stderr.getvalue():
            raise AssertionError(
                f"post-barrier signal {signum} at {signal_stage} was reported as an abort")

# The ordinary path crosses the barrier, retains the final run, and leaves no
# private staging or abort residue.
execution = "execution-publication-success"
project = prepare(execution)
pipeline._TEST_PUBLICATION_HOOK = None
pipeline.initialize(pipeline.parser().parse_args(arguments(project, execution)[1:]))
runs = project / ".mana/runtime/runs"
if not (runs / execution).is_dir():
    raise AssertionError("signal-free publication did not commit the final run")
if any(marker in path.name for path in runs.iterdir()
       for marker in (".stage.", ".abort.")):
    raise AssertionError("signal-free publication left private residue")
if (project / "outside.txt").read_text(encoding="utf-8") != "outside-sentinel\n":
    raise AssertionError("signal-free publication modified outside sentinel")

print("CTX-06A-R2 deterministic failure, signal, and commit-barrier tests passed")
if owned_temporary is not None:
    owned_temporary.cleanup()
