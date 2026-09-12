#!/usr/bin/env python3
"""CTX-06C prompt, output, capability, and phased-metric boundaries."""

from __future__ import annotations

import importlib.util
import fcntl
import json
import os
import re
import signal
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("mana_context_runtime", HERE / "context-runtime.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load Context Runtime contracts")
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)

PACKET_SCHEMA = "mana.context-runtime.phase-execution-packet/v1"
MAX_PROVIDER_OUTPUT = 64 * 1024
MAX_CAPABILITY_REPORT = 64 * 1024
MAX_USAGE_INTEGER = 9007199254740991
SAFE_PHASE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
SAFE_EXECUTION = re.compile(r"^execution-[A-Za-z0-9._-]{1,120}$")
PHASE_METRIC = re.compile(
    r"^(?P<ordinal>[0-9]{3})-(?P<phase>[A-Za-z0-9_-]{1,80})-attempt-"
    r"(?P<attempt>[0-9]{3})-invocation-(?P<invocation>[0-9]{3})\.json$"
)
PHASE_RAW_TRACE = re.compile(
    r"^[0-9]{3}-[A-Za-z0-9_-]{1,80}-attempt-[0-9]{3}-invocation-"
    r"[0-9]{3}-raw-provider-events\.jsonl$"
)


def fail(message: str) -> None:
    raise runtime.ContractError(message)


def read_object(path: str, *, max_bytes: int) -> dict[str, Any]:
    payload = runtime.safe_read_bytes(Path(path), max_bytes=max_bytes)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot decode JSON input: {error}")
    if not isinstance(value, dict):
        fail("JSON input must be an object")
    return value


def validate_packet(packet: dict[str, Any]) -> None:
    required = {
        "schemaVersion", "executionId", "profileId", "provider", "runStatus",
        "revision", "currentAttempt", "phase", "executionEnvelope",
        "contextManifest", "phaseInput", "previousCheckpoint", "providerInvoked",
    }
    if set(packet) != required or packet.get("schemaVersion") != PACKET_SCHEMA:
        fail("phase execution packet has an invalid field set or version")
    if packet.get("providerInvoked") is not False:
        fail("phase preparation cannot claim provider execution")
    if packet.get("provider") not in {"codex", "claude", "opencode"}:
        fail("phase execution packet has an invalid provider")
    if packet.get("runStatus") not in {"active", "blocked", "completed", "interrupted"}:
        fail("phase execution packet has an invalid run status")
    if not isinstance(packet.get("revision"), int) or packet["revision"] < 0:
        fail("phase execution packet has an invalid revision")
    if not isinstance(packet.get("currentAttempt"), int) or packet["currentAttempt"] < 1:
        fail("phase execution packet has an invalid current attempt")
    envelope = packet.get("executionEnvelope")
    manifest = packet.get("contextManifest")
    if not isinstance(envelope, dict) or not isinstance(manifest, dict):
        fail("phase execution packet omits its host records")
    runtime.validate_structure("execution-envelope", envelope)
    runtime.validate_model("context-manifest", manifest)
    if (
        envelope["executionId"] != packet.get("executionId")
        or envelope["profileId"] != packet.get("profileId")
        or envelope["provider"] != packet.get("provider")
        or manifest["executionId"] != packet.get("executionId")
        or manifest["profileId"] != packet.get("profileId")
    ):
        fail("phase execution packet host identities differ")
    if packet["runStatus"] == "active":
        phase = packet.get("phase")
        phase_input = packet.get("phaseInput")
        if not isinstance(phase, dict) or not isinstance(phase_input, dict):
            fail("active phase execution packet omits phase data")
        if set(phase) != {"id", "ordinal", "policy"} or not isinstance(phase["policy"], dict):
            fail("active phase policy is malformed")
        runtime.validate_model("phase-input", phase_input)
        if (
            phase["id"] != phase_input["phaseId"]
            or phase_input["executionId"] != packet["executionId"]
        ):
            fail("active phase packet identities differ")
        previous = packet.get("previousCheckpoint")
        if previous is not None:
            if not isinstance(previous, dict):
                fail("previous checkpoint must be an object or null")
            runtime.validate_model("phase-checkpoint", previous)
            if phase_input["checkpointRef"] != previous["checkpointId"]:
                fail("phase input does not name its previous checkpoint")
    elif any(packet.get(key) is not None for key in ("phase", "phaseInput", "previousCheckpoint")):
        fail("terminal or blocked phase packet carries executable phase data")


def render_prompt(packet: dict[str, Any]) -> str:
    validate_packet(packet)
    if packet["runStatus"] != "active":
        fail("only an active run can render a provider phase prompt")
    phase = packet["phase"]
    assert isinstance(phase, dict)
    records = {
        "executionEnvelope": packet["executionEnvelope"],
        "contextManifest": packet["contextManifest"],
        "phasePolicy": phase,
        "phaseInput": packet["phaseInput"],
        "previousCheckpoint": packet["previousCheckpoint"],
    }
    lines = [
        "Mana Context Runtime v2 — one fresh, bounded phase invocation.",
        "Treat the execution envelope as immutable host authority. Do not amend permissions or approvals.",
        "Use only the current phase policy, current phase input, the previous validated checkpoint, and explicit evidence references below.",
        "No provider transcript or prior phase instruction is available. Do not reconstruct one.",
        "Provider-managed subagents and recursive delegation are disabled for this CTX-06C worker.",
        "Return only one JSON object conforming to phase-checkpoint-v1, without Markdown fences or commentary.",
        "Bind executionId, executionVersion, profileId, and phaseId exactly to the host records.",
        "Facts require explicit evidence references; keep assumptions, inferences, uncertainty, and approval requests separate.",
        "Select only the next action permitted by the declared finite pipeline. Never add or reorder a phase.",
        "BEGIN_MANA_PHASE_PACKET",
    ]
    for name, value in records.items():
        lines.append(f"{name}={json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)}")
    lines.extend(("END_MANA_PHASE_PACKET", ""))
    return "\n".join(lines)


def normalize_output(provider: str, path: str) -> dict[str, Any]:
    if provider not in {"codex", "claude", "opencode"}:
        fail("unknown provider output adapter")
    value = read_object(path, max_bytes=MAX_PROVIDER_OUTPUT)
    candidate: Any = value
    if provider == "claude" and isinstance(value.get("structured_output"), dict):
        candidate = value["structured_output"]
    elif provider == "claude" and isinstance(value.get("result"), str):
        try:
            candidate = json.loads(value["result"])
        except json.JSONDecodeError as error:
            fail(f"Claude result does not contain a JSON checkpoint: {error}")
    if not isinstance(candidate, dict):
        fail("provider final output is not a checkpoint object")
    runtime.validate_model("phase-checkpoint", candidate)
    return candidate


def validate_capabilities(provider: str, path: str) -> dict[str, Any]:
    report = read_object(path, max_bytes=MAX_CAPABILITY_REPORT)
    runtime.validate_structure("provider-capabilities", report)
    if report["provider"] != provider:
        fail("provider capability report is bound to a different provider")
    return report


def supported_sum(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    total = sum(present)
    return total if total <= MAX_USAGE_INTEGER else None


def move_raw_trace(project_root: Path, source_relative: str, target_relative: str) -> None:
    """Move one debug trace with a directory-FD-relative no-replace rename."""
    nofollow, directory = runtime._require_secure_dir_fd_support()
    primitives = runtime._require_rename_primitives()
    source_parts = source_relative.split("/")
    target_parts = target_relative.split("/")
    root_fd = -1
    opened: list[int] = []

    def open_directory(parts: list[str]) -> int:
        current = os.dup(root_fd)
        opened.append(current)
        for part in parts:
            next_fd = os.open(part, os.O_RDONLY | nofollow | directory, dir_fd=current)
            opened.append(next_fd)
            current = next_fd
        return current

    try:
        root_fd = runtime._open_directory(
            project_root, dir_fd=None, nofollow=nofollow, directory=directory
        )
        source_parent = open_directory(source_parts[:-1])
        target_parent = open_directory(target_parts[:-1])
        source_fd = os.open(
            source_parts[-1], os.O_RDONLY | os.O_NONBLOCK | nofollow,
            dir_fd=source_parent,
        )
        try:
            metadata = os.fstat(source_fd)
            identity = runtime._entry_identity(metadata)
            if not stat.S_ISREG(metadata.st_mode):
                fail("retained provider trace is not a regular file")
            os.fchmod(source_fd, 0o600)
        finally:
            os.close(source_fd)
        primitives.noreplace(
            source_parent, source_parts[-1], target_parent, target_parts[-1]
        )
        if not runtime._verify_identity(target_parent, target_parts[-1], identity):
            fail("retained provider trace identity changed during archival")
        os.fsync(source_parent)
        if source_parent != target_parent:
            os.fsync(target_parent)
    finally:
        for fd in reversed(opened):
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)


def phase_metric_record(
    summary: dict[str, Any], match: re.Match[str]
) -> dict[str, Any]:
    return {
        "phaseId": match.group("phase"),
        "ordinal": int(match.group("ordinal")),
        "attempt": int(match.group("attempt")),
        "invocation": int(match.group("invocation")),
        "providerVersion": summary["providerVersion"],
        "status": summary["status"],
        "usageStatus": summary["usageStatus"],
        "totals": summary["totals"],
        "turns": summary["turns"],
        "toolCalls": summary["toolCalls"],
        "workers": summary["workers"],
        "compactions": summary["compactions"],
        "rawTraceRetained": summary["rawTraceRetained"],
        "parseErrors": summary["parseErrors"],
    }


def aggregate_metrics(
    project_root: Path, execution_id: str, profile_id: str, provider: str,
    run_status: str,
) -> dict[str, Any]:
    phase_root = f".mana/runtime/metrics/{execution_id}/phases"
    names = runtime.safe_list_directory(project_root, phase_root)
    records: list[dict[str, Any]] = []
    for name in sorted(names):
        match = PHASE_METRIC.fullmatch(name)
        if match is None:
            if PHASE_RAW_TRACE.fullmatch(name) is not None:
                continue
            fail("phase metrics directory contains an unexpected entry")
        payload = runtime.safe_read_bytes(
            Path(f"{phase_root}/{name}"), project_root=project_root,
            max_bytes=runtime.MAX_BYTES["usage-summary"],
        )
        try:
            summary = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            fail(f"cannot decode phase usage summary: {error}")
        if not isinstance(summary, dict):
            fail("phase usage summary must be an object")
        runtime.validate_model("usage-summary", summary)
        if (
            summary["executionId"] != execution_id
            or summary["profileId"] != profile_id
            or summary["provider"] != provider
            or summary["phases"] != []
        ):
            fail("phase usage summary identity or shape differs from its run")
        records.append(phase_metric_record(summary, match))
    records.sort(key=lambda item: (item["ordinal"], item["attempt"], item["invocation"]))
    versions = {record["providerVersion"] for record in records}
    aggregate = {
        "schemaVersion": "1",
        "executionId": execution_id,
        "profileId": profile_id,
        "provider": provider,
        "providerVersion": next(iter(versions)) if len(versions) == 1 else None,
        "status": run_status,
        "usageStatus": "unavailable",
        "phases": records,
        "totals": {
            key: supported_sum([record["totals"][key] for record in records]) if all(record["totals"][key] is not None for record in records) else None
            for key in ("input", "cachedInput", "uncachedInput", "output", "reasoning")
        },
        "turns": supported_sum([record["turns"] for record in records]),
        "toolCalls": supported_sum([record["toolCalls"] for record in records]),
        "workers": supported_sum([record["workers"] for record in records]),
        "compactions": supported_sum([record["compactions"] for record in records]),
        "rawTraceRetained": any(record["rawTraceRetained"] for record in records),
        "parseErrors": sum(record["parseErrors"] for record in records),
    }
    if any(all(record["totals"][key] is not None for record in records)
           and sum(record["totals"][key] for record in records) > MAX_USAGE_INTEGER
           for key in runtime.USAGE_FIELDS):
        aggregate["parseErrors"] += 1
    classification = runtime.usage_totals_status(aggregate["totals"], aggregate["parseErrors"])
    if classification == "invalid":
        aggregate["totals"] = dict.fromkeys(runtime.USAGE_FIELDS)
        aggregate["parseErrors"] = max(1, aggregate["parseErrors"])
    else:
        aggregate["usageStatus"] = classification
    runtime.validate_model("usage-summary", aggregate)
    return aggregate


def archive_metrics(
    project_root_value: str, execution_id: str, profile_id: str, provider: str,
    phase_id: str, ordinal: int, attempt: int, provider_version: str,
    run_status: str,
) -> dict[str, Any]:
    if SAFE_EXECUTION.fullmatch(execution_id) is None or SAFE_PHASE.fullmatch(phase_id) is None:
        fail("metric identity is malformed")
    if not 1 <= ordinal <= 128 or not 1 <= attempt <= 17:
        fail("phase metric ordinal or attempt is outside the runtime contract")
    if run_status not in {"complete", "failed", "interrupted"}:
        fail("aggregate metric status is invalid")
    project_root = Path(os.path.abspath(project_root_value))
    runtime.validate_secure_root(project_root)
    metrics_root = f".mana/runtime/metrics/{execution_id}"
    source_relative = f"{metrics_root}/usage-summary-v1.json"
    payload = runtime.safe_read_bytes(
        Path(source_relative), project_root=project_root, max_bytes=256 * 1024
    )
    try:
        summary = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot decode current provider usage summary: {error}")
    if not isinstance(summary, dict):
        fail("current provider usage summary must be an object")
    runtime.validate_model("usage-summary", summary)
    if (
        summary["executionId"] != execution_id
        or summary["profileId"] != profile_id
        or summary["provider"] != provider
        or summary["phases"] != []
    ):
        fail("current provider usage summary is not one unarchived phase invocation")
    summary["providerVersion"] = provider_version
    phase_root = f"{metrics_root}/phases"
    runtime.ensure_secure_directory(project_root, phase_root)
    prefix = f"{ordinal:03d}-{phase_id}-attempt-{attempt:03d}-invocation-"
    existing = runtime.safe_list_directory(project_root, phase_root)
    invocation = 1 + max(
        (
            int(match.group("invocation"))
            for name in existing
            if (match := PHASE_METRIC.fullmatch(name)) is not None
            and name.startswith(prefix)
        ),
        default=0,
    )
    if invocation > 999:
        fail("phase invocation metric limit is exhausted")
    name = f"{prefix}{invocation:03d}.json"
    relative = f"{phase_root}/{name}"
    runtime.atomic_write_bytes(
        project_root, relative, runtime.canonical_bytes(summary) + b"\n",
        immutable=True,
    )
    if summary["rawTraceRetained"]:
        move_raw_trace(
            project_root, f"{metrics_root}/raw-provider-events.jsonl",
            f"{phase_root}/{name[:-5]}-raw-provider-events.jsonl",
        )
    aggregate = aggregate_metrics(
        project_root, execution_id, profile_id, provider, run_status
    )
    runtime.atomic_write_bytes(
        project_root, source_relative, runtime.canonical_bytes(aggregate) + b"\n"
    )
    markdown = [
        "# Mana usage summary v1", "",
        f"Execution ID         {execution_id}",
        f"Profile ID           {profile_id}",
        f"Provider             {provider}",
        f"Status               {run_status}",
        f"Usage status         {aggregate['usageStatus']}",
        f"Phase invocations    {len(aggregate['phases'])}",
        f"Input                {json.dumps(aggregate['totals']['input'])}",
        f"Cached input         {json.dumps(aggregate['totals']['cachedInput'])}",
        f"Uncached input       {json.dumps(aggregate['totals']['uncachedInput'])}",
        f"Output               {json.dumps(aggregate['totals']['output'])}",
        f"Reasoning            {json.dumps(aggregate['totals']['reasoning'])}",
        f"Raw trace retained   {str(aggregate['rawTraceRetained']).lower()}",
        f"Parse errors         {aggregate['parseErrors']}", "",
    ]
    runtime.atomic_write_bytes(
        project_root, f"{metrics_root}/usage-summary-v1.md",
        "\n".join(markdown).encode("utf-8"),
    )
    return {
        "schemaVersion": "mana.context-runtime.phase-metric-archive/v1",
        "executionId": execution_id,
        "phaseId": phase_id,
        "ordinal": ordinal,
        "attempt": attempt,
        "invocation": invocation,
        "summaryRef": relative,
    }


def with_run_lock(project_root_value: str, execution_id: str, command: list[str]) -> int:
    """Serialize provider work while leaving CTX-06B HEAD as state authority."""
    if SAFE_EXECUTION.fullmatch(execution_id) is None or not command:
        fail("run lock requires a safe execution ID and command")
    project_root = Path(os.path.abspath(project_root_value))
    runtime.validate_secure_root(project_root)
    relative = f".mana/runtime/runs/{execution_id}/.provider-phase.lock"
    try:
        runtime.atomic_write_bytes(project_root, relative, b"", immutable=True)
    except runtime.ContractError as error:
        # Concurrent first use may win the no-replace publication after this
        # process observed absence. Converge only on the exact empty lock file.
        if "destination appeared before exclusive publication" not in str(error):
            raise
        if runtime.safe_read_bytes(
            Path(relative), project_root=project_root, max_bytes=1
        ) != b"":
            raise
    nofollow, directory = runtime._require_secure_dir_fd_support()
    root_fd = runtime._open_directory(
        project_root, dir_fd=None, nofollow=nofollow, directory=directory
    )
    opened: list[int] = []
    lock_fd = -1
    child: subprocess.Popen[bytes] | None = None
    previous_handlers: dict[int, Any] = {}
    try:
        parent_fd, opened = runtime._walk_existing_parent(
            root_fd, relative.split("/")[:-1], nofollow, directory
        )
        lock_fd = os.open(
            relative.split("/")[-1], os.O_RDWR | os.O_NONBLOCK | nofollow,
            dir_fd=parent_fd,
        )
        metadata = os.fstat(lock_fd)
        identity = runtime._entry_identity(metadata)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or not runtime._verify_identity(
                parent_fd, relative.split("/")[-1], identity
            )
            or not runtime._same_existing_directory_from_root(
                root_fd, relative.split("/")[:-1], parent_fd, nofollow, directory
            )
        ):
            fail("provider phase lock is not a regular file")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if (
            not runtime._verify_identity(
                parent_fd, relative.split("/")[-1], identity
            )
            or not runtime._same_existing_directory_from_root(
                root_fd, relative.split("/")[:-1], parent_fd, nofollow, directory
            )
        ):
            fail("provider phase lock binding changed while waiting")
        environment = os.environ.copy()
        environment["MANA_CONTEXT_PHASE_LOCK_HELD"] = execution_id
        child = subprocess.Popen(command, env=environment)

        def forward(signum: int, _frame: Any) -> None:
            if child is not None and child.poll() is None:
                child.send_signal(signum)

        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, forward)
        return child.wait()
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait()
        if lock_fd >= 0:
            os.close(lock_fd)
        for fd in reversed(opened):
            os.close(fd)
        os.close(root_fd)


def usage() -> int:
    print(
        "Usage:\n"
        "  context-phase-runtime.py render-prompt <packet.json>\n"
        "  context-phase-runtime.py normalize-output <provider> <output.json>\n"
        "  context-phase-runtime.py validate-capabilities <provider> <report.json>\n"
        "  context-phase-runtime.py with-run-lock <project-root> <execution-id> <command> [args...]\n"
        "  context-phase-runtime.py archive-metrics <project-root> <execution-id> <profile-id> <provider> <phase-id> <ordinal> <attempt> <provider-version> <complete|failed|interrupted>",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 3 and argv[1] == "render-prompt":
            sys.stdout.write(render_prompt(read_object(argv[2], max_bytes=256 * 1024)))
            return 0
        if len(argv) == 4 and argv[1] == "normalize-output":
            sys.stdout.buffer.write(runtime.canonical_bytes(normalize_output(argv[2], argv[3])) + b"\n")
            return 0
        if len(argv) == 4 and argv[1] == "validate-capabilities":
            report = validate_capabilities(argv[2], argv[3])
            sys.stdout.buffer.write(runtime.canonical_bytes(report) + b"\n")
            return 0
        if len(argv) >= 5 and argv[1] == "with-run-lock":
            return with_run_lock(argv[2], argv[3], argv[4:])
        if len(argv) == 11 and argv[1] == "archive-metrics":
            result = archive_metrics(
                argv[2], argv[3], argv[4], argv[5], argv[6], int(argv[7]),
                int(argv[8]), argv[9], argv[10],
            )
            sys.stdout.buffer.write(runtime.canonical_bytes(result) + b"\n")
            return 0
        return usage()
    except (runtime.ContractError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
