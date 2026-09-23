#!/usr/bin/env python3
"""CTX-08 host-owned, capability-gated compaction and budget advisories."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
HOST_FRAMEWORK_ROOT = HERE.parent.parent
POLICY_RELATIVE = Path("config/context-runtime/provider-budget-policy-v1.json")
POLICY_VERSION = "mana.context-runtime.provider-budget-policy/v1"
DECISION_VERSION = "mana.context-runtime.provider-budget-decision/v1"
MODE_ORDER = ("compact", "standard", "deep")
MODES = set(MODE_ORDER)
MAX_POLICY_BYTES = 256 * 1024
MAX_DECISION_BYTES = 320 * 1024
# Implementation ceilings, not empirically calibrated workflow thresholds.
NUMERIC_CEILINGS = {
    "automaticCompactionThresholdTokens": 10000000,
    "activeContextWarningTokens": 10000000,
    "cumulativeInputWarningTokens": 1000000000,
    "cachedInputWarningTokens": 1000000000,
    "uncachedInputWarningTokens": 1000000000,
    "toolOutputRetentionTokens": 1048576,
    "maximumChildConcurrency": 32,
}
FORBIDDEN_ENV = (
    "MANA_FRAMEWORK_ROOT", "MANA_CONTEXT_FRAMEWORK_ROOT", "MANA_WORKER_FRAMEWORK_ROOT",
    "MANA_BUDGET_POLICY_PATH", "MANA_PROVIDER_BUDGET_POLICY", "MANA_BUDGET_MODE",
    "MANA_CONTEXT_BUDGET_MODE", "MANA_BUDGET_MINIMUM_MODE",
)


def _load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load("mana_context_runtime_budgets", "context-runtime.py")
CAPABILITIES = {
    "automaticCompactionThreshold": "automaticCompactionThresholdTokens",
    "customCompactionPrompt": "compactionPromptVersion",
    "compactionScope": "compactionScope",
    "toolOutputRetentionTokenLimit": "toolOutputRetentionTokens",
    "maximumChildConcurrency": "maximumChildConcurrency",
    "hardSubagentDisable": "childExecution",
}
HOST_ADAPTERS = {
    "codex": {"hardSubagentDisable"},
    "claude": {"automaticCompactionThreshold", "hardSubagentDisable"},
    "opencode": {"hardSubagentDisable"},
}
REQUIRED_PROMPT_FRAGMENTS = (
    "current human goal",
    "immutable governance constraints and approvals",
    "current profile, phase, target, base, workspace, and execution identifiers",
    "activated skills and activation reasons",
    "verified facts with evidence references",
    "open questions and required evidence",
    "Never turn an assumption or inference into a verified fact.",
    "Never remove an unresolved blocker, approval gate, safety constraint, or provenance.",
)


class BudgetError(runtime.ContractError):
    pass


def decode_object(payload: bytes) -> dict[str, Any]:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise BudgetError("duplicate JSON field")
            value[key] = item
        return value
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BudgetError("cannot decode budget JSON") from error
    if not isinstance(value, dict):
        raise BudgetError("JSON input must be an object")
    return value


def load_object(path: str) -> dict[str, Any]:
    return decode_object(runtime.safe_read_bytes(Path(path), max_bytes=MAX_DECISION_BYTES))


def validate_schema(value: dict[str, Any], filename: str) -> None:
    # CTX-03 evaluates every keyword used by these local schemas, including
    # referenced branches. No external schema or network resolver is used.
    evaluator = runtime.Evaluator()
    document = runtime.CONTRACTS / filename
    errors = evaluator.evaluate(value, evaluator.load(document), document)
    if errors:
        raise BudgetError("budget schema validation failed: " + "; ".join(errors[:6]))


def load_policy(framework_root: Path | None = None) -> dict[str, Any]:
    root = HOST_FRAMEWORK_ROOT if framework_root is None else framework_root
    runtime.validate_secure_root(root)
    # CTX-03's strict FD reader also re-attests the final inode, stable read
    # metadata and parent binding. Inline compact text is read in this object.
    payload, _identity = runtime._safe_read_file(
        POLICY_RELATIVE, project_root=root, max_bytes=MAX_POLICY_BYTES,
        require_single_link=True,
    )
    policy = decode_object(payload)
    validate_policy(policy)
    return decode_object(runtime.canonical_bytes(policy))


def require_positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise BudgetError(f"{field} must be a positive integer")
    return value


def validate_mode(mode: Any) -> dict[str, Any]:
    if not isinstance(mode, dict):
        raise BudgetError("budget mode must be an object")
    expected = {
        "automaticCompactionThresholdTokens", "activeContextWarningTokens",
        "cumulativeInputWarningTokens", "cachedInputWarningTokens",
        "uncachedInputWarningTokens", "toolOutputRetentionTokens",
        "maximumChildConcurrency", "childExecution", "compactionScope",
    }
    if set(mode) != expected:
        raise BudgetError("budget mode has an unknown or incomplete field set")
    for key in NUMERIC_CEILINGS:
        require_positive_int(mode[key], key)
        if mode[key] > NUMERIC_CEILINGS[key]:
            raise BudgetError(f"{key} exceeds its host implementation ceiling")
    if mode["childExecution"] != "disabled":
        raise BudgetError("CTX-08 child execution must remain disabled")
    if mode["compactionScope"] != "current-provider-context":
        raise BudgetError("budget compaction scope is invalid")
    if mode["activeContextWarningTokens"] > mode["automaticCompactionThresholdTokens"]:
        raise BudgetError("active context warning must not exceed compaction threshold")
    return mode


def validate_policy(policy: dict[str, Any]) -> None:
    validate_schema(policy, "provider-budget-policy-v1.schema.json")
    if set(policy) != {"schemaVersion", "policyId", "calibration", "compactionPrompt", "profiles"}:
        raise BudgetError("budget policy has an unknown or incomplete field set")
    if policy["schemaVersion"] != POLICY_VERSION or re.fullmatch(r"[A-Za-z0-9._-]{1,120}", policy["policyId"]) is None:
        raise BudgetError("budget policy identity is invalid")
    calibration = policy["calibration"]
    if not isinstance(calibration, dict) or set(calibration) != {"status", "requiredEvidence"}:
        raise BudgetError("budget policy calibration is invalid")
    if calibration["status"] != "provisional-no-empirical-baseline" or not isinstance(calibration["requiredEvidence"], str):
        raise BudgetError("CTX-08 policy must remain explicitly provisional until empirical calibration")
    prompt = policy["compactionPrompt"]
    if not isinstance(prompt, dict) or set(prompt) != {"version", "text"} or not all(isinstance(prompt[key], str) and prompt[key] for key in prompt):
        raise BudgetError("versioned compaction prompt is invalid")
    if any(fragment not in prompt["text"] for fragment in REQUIRED_PROMPT_FRAGMENTS):
        raise BudgetError("versioned compaction prompt omits a required preservation constraint")
    if re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", prompt["version"]) is None:
        raise BudgetError("compact prompt version identity is invalid")
    profiles = policy["profiles"]
    if not isinstance(profiles, dict) or "default" not in profiles:
        raise BudgetError("budget policy requires a default profile policy")
    for profile_id, selected in profiles.items():
        if re.fullmatch(r"[A-Za-z0-9_-]{1,120}", profile_id) is None:
            raise BudgetError("profile policy identity is invalid")
        for configured_mode in MODE_ORDER:
            validate_mode(selected["modes"][configured_mode])
        for key in NUMERIC_CEILINGS:
            values = [selected["modes"][name][key] for name in MODE_ORDER]
            if values != sorted(values):
                raise BudgetError(f"non-monotone profile budget: {profile_id}/{key}")


def resolve_policy(policy: dict[str, Any], profile: str, mode: str) -> dict[str, Any]:
    validate_policy(policy)
    if mode not in MODES:
        raise BudgetError("budget mode must be compact, standard, or deep")
    selected = policy["profiles"].get(profile, policy["profiles"]["default"])
    limits = selected["modes"][mode]
    return {
        "schemaVersion": "mana.context-runtime.provider-budget-resolution/v1",
        "policyId": policy["policyId"],
        "profileId": profile,
        "mode": mode,
        "calibration": json.loads(json.dumps(policy["calibration"])),
        "compactionPromptVersion": policy["compactionPrompt"]["version"],
        "limits": json.loads(json.dumps(limits)),
    }


def resolve(profile: str, mode: str) -> dict[str, Any]:
    return resolve_policy(load_policy(), profile, mode)


def mode_decision(policy: dict[str, Any], packet: dict[str, Any], requested: str | None) -> dict[str, Any]:
    validate_policy(policy)
    if requested is not None and requested not in MODES:
        raise BudgetError("invalid human mode request")
    profile = packet["profileId"]
    selected = policy["profiles"].get(profile, policy["profiles"]["default"])
    minimum = selected["minimumMode"]
    source = "host-policy"
    if packet["contextManifest"]["modelEscalationSkills"]:
        minimum, source = "deep", "profile-risk"
    effective = max((minimum, requested or minimum), key=MODE_ORDER.index)
    if requested is not None:
        source = "human-cli"
    return {
        "schemaVersion": DECISION_VERSION,
        "executionId": packet["executionId"],
        "executionVersion": packet["executionEnvelope"]["executionVersion"],
        "profileId": profile, "policyId": policy["policyId"],
        "provider": packet["provider"],
        "policyDigest": hashlib.sha256(runtime.canonical_bytes(policy)).hexdigest(),
        "minimumMode": minimum, "requestedMode": requested, "effectiveMode": effective,
        "decisionSource": source,
        "decisionReason": "human-request-raised-budget" if requested and MODE_ORDER.index(requested) > MODE_ORDER.index(minimum) else "host-minimum-preserved",
        "policySnapshot": policy,
    }


@contextmanager
def decision_lock(project_root: Path, execution_id: str):
    relative = f".mana/runtime/runs/{execution_id}/.budget-decision.lock"
    try:
        runtime.atomic_write_bytes(project_root, relative, b"", immutable=True)
    except runtime.ContractError:
        if runtime.safe_read_bytes(Path(relative), project_root=project_root, max_bytes=1) != b"":
            raise
    nofollow, directory = runtime._require_secure_dir_fd_support()
    root_fd = runtime._open_directory(project_root, dir_fd=None, nofollow=nofollow, directory=directory)
    opened, fd = [], -1
    try:
        parent, opened = runtime._walk_existing_parent(root_fd, relative.split("/")[:-1], nofollow, directory)
        fd = os.open(relative.split("/")[-1], os.O_RDWR | os.O_NONBLOCK | nofollow, dir_fd=parent)
        identity = runtime._entry_identity(os.fstat(fd))
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BudgetError("budget decision lock is not regular")
        fcntl.flock(fd, fcntl.LOCK_EX)
        if not runtime._verify_identity(parent, relative.split("/")[-1], identity) or not runtime._same_existing_directory_from_root(root_fd, relative.split("/")[:-1], parent, nofollow, directory):
            raise BudgetError("budget decision lock binding changed")
        yield
    finally:
        if fd >= 0:
            os.close(fd)
        for item in reversed(opened):
            os.close(item)
        os.close(root_fd)


def materialize_decision(args: argparse.Namespace) -> dict[str, Any]:
    pipeline = _load("mana_context_pipeline_budgets", "context-pipeline.py")
    # This root is code-owned. Production argparse has no root/policy option.
    args.framework_root = str(HOST_FRAMEWORK_ROOT)
    packet = pipeline.prepare_phase(args)
    root = Path(args.project_root)
    run = f".mana/runtime/runs/{args.execution_id}"
    relative = f"{run}/provider-budget-decision-v1.json"
    with decision_lock(root, args.execution_id):
        entries = runtime.safe_list_directory(root, run)
        if "provider-budget-decision-v1.json" in entries:
            payload, _identity = runtime.safe_read_private_bytes(Path(relative), project_root=root, max_bytes=MAX_DECISION_BYTES)
            commitment_payload, _ = runtime.safe_read_private_bytes(Path(f"{run}/provider-budget-decision-commit-v1.json"), project_root=root, max_bytes=4096)
            commitment = decode_object(commitment_payload)
            if commitment != {"schemaVersion": "mana.context-runtime.provider-budget-decision-commit/v1", "decisionDigest": hashlib.sha256(payload).hexdigest(), "device": _identity[0], "inode": _identity[1]} or commitment_payload != runtime.canonical_bytes(commitment) + b"\n":
                raise BudgetError("budget decision host commitment differs")
            decision = decode_object(payload)
            if payload != runtime.canonical_bytes(decision) + b"\n":
                raise BudgetError("noncanonical budget decision")
            validate_schema(decision, "provider-budget-decision-v1.schema.json")
            expected = mode_decision(decision["policySnapshot"], packet, decision["requestedMode"])
            if decision != expected:
                raise BudgetError("budget decision identity, digest or mode was tampered")
            if args.requested_mode and MODE_ORDER.index(args.requested_mode) > MODE_ORDER.index(decision["effectiveMode"]):
                raise BudgetError("run budget decision is immutable; stronger late request requires a new execution")
        else:
            decision = mode_decision(load_policy(), packet, args.requested_mode)
            validate_schema(decision, "provider-budget-decision-v1.schema.json")
            runtime.atomic_write_bytes(root, relative, runtime.canonical_bytes(decision) + b"\n", immutable=True)
            payload, identity = runtime.safe_read_private_bytes(Path(relative), project_root=root, max_bytes=MAX_DECISION_BYTES)
            commitment = {"schemaVersion": "mana.context-runtime.provider-budget-decision-commit/v1", "decisionDigest": hashlib.sha256(payload).hexdigest(), "device": identity[0], "inode": identity[1]}
            runtime.atomic_write_bytes(root, f"{run}/provider-budget-decision-commit-v1.json", runtime.canonical_bytes(commitment) + b"\n", immutable=True)
    resolution = resolve_policy(decision["policySnapshot"], decision["profileId"], decision["effectiveMode"])
    resolution["decision"] = {key: value for key, value in decision.items() if key != "policySnapshot"}
    return resolution


def capability_plan(resolution: dict[str, Any], capabilities_path: str) -> dict[str, Any]:
    capabilities = load_object(capabilities_path)
    runtime.validate_structure("provider-capabilities", capabilities)
    provider = capabilities.get("provider")
    if "decision" in resolution and provider != resolution["decision"]["provider"]:
        raise BudgetError("capability provider differs from materialized decision")
    if provider not in HOST_ADAPTERS:
        raise BudgetError("provider capability report has an unsupported identity")
    records = capabilities.get("capabilities")
    if not isinstance(records, dict):
        raise BudgetError("provider capability report lacks capabilities")
    controls: dict[str, Any] = {}
    for capability, source in CAPABILITIES.items():
        record = records.get(capability)
        if not isinstance(record, dict) or record.get("status") not in {"supported", "unsupported", "unknown"}:
            raise BudgetError(f"capability {capability} has no CTX-02 tri-state")
        requested = resolution["compactionPromptVersion"] if source == "compactionPromptVersion" else resolution["limits"][source]
        status = record["status"]
        adapter_available = capability in HOST_ADAPTERS[provider]
        applied = status == "supported" and adapter_available
        if status != "supported":
            reason = f"capability-{status}"
        elif not adapter_available:
            reason = "host-adapter-unimplemented"
        else:
            reason = "capability-supported"
        controls[capability] = {
            "status": status,
            "requested": requested,
            "applied": applied,
            "reason": reason,
        }
    return {
        "schemaVersion": "mana.context-runtime.provider-budget-plan/v1",
        "profileId": resolution["profileId"],
        "mode": resolution["mode"],
        "calibrationStatus": resolution["calibration"]["status"],
        "controls": controls,
    }


def prompt_check(resolution: dict[str, Any], prompt_path: str) -> dict[str, Any]:
    try:
        size = Path(prompt_path).stat().st_size
    except OSError as error:
        raise BudgetError(f"cannot measure provider prompt: {error}") from error
    tokens = math.ceil(size / 4)
    return {
        "schemaVersion": "mana.context-runtime.provider-budget-prompt-check/v1",
        "estimatedTokens": tokens,
        "estimateKind": "utf8-bytes-divided-by-four-not-measured-provider-usage",
        "warning": tokens >= resolution["limits"]["activeContextWarningTokens"],
    }


def usage_check(resolution: dict[str, Any], summary_path: str) -> dict[str, Any]:
    summary = load_object(summary_path)
    return check_usage_value(resolution, summary)


def check_usage_value(resolution: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    totals = summary.get("totals")
    status = runtime.usage_totals_status(totals, summary.get("parseErrors", 0))
    if status != "invalid" and summary.get("usageStatus") != status:
        status = "invalid"
    if status in {"invalid", "unavailable"}:
        return {"schemaVersion": "mana.context-runtime.provider-budget-usage-check/v1", "measured": False, "valid": status != "invalid", "usageStatus": status, "warnings": ["usage-invalid"] if status == "invalid" else ["usage-unavailable"], "recommendation": "human-scope-decision" if status == "invalid" else None}
    warnings: list[str] = []
    checks = (
        ("cumulative-input", "input", "cumulativeInputWarningTokens"),
        ("cached-input", "cachedInput", "cachedInputWarningTokens"),
        ("uncached-input", "uncachedInput", "uncachedInputWarningTokens"),
    )
    for name, total_key, limit_key in checks:
        value = totals.get(total_key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= resolution["limits"][limit_key]:
            warnings.append(name)
    return {
        "schemaVersion": "mana.context-runtime.provider-budget-usage-check/v1",
        "measured": status == "measured",
        "valid": True,
        "usageStatus": status,
        "warnings": warnings,
        "recommendation": "checkpoint-and-fresh-phase" if warnings else None,
    }


def advisory(resolution: dict[str, Any], summary_path: str, project: str, key: str, prompt_path: str | None = None) -> dict[str, Any]:
    if re.fullmatch(r"[A-Za-z0-9._-]{1,180}", key) is None or "decision" not in resolution:
        raise BudgetError("advisory requires a host decision and safe invocation identity")
    decision = resolution["decision"]
    summary = load_object(summary_path)
    try:
        runtime.validate_model("usage-summary", summary)
    except runtime.ContractError:
        summary = {"totals": dict.fromkeys(runtime.USAGE_FIELDS), "parseErrors": 1, "usageStatus": "unavailable"}
    value = {"schemaVersion": "mana.context-runtime.provider-budget-advisory/v1", "executionId": decision["executionId"], "invocationKey": key, "policyDigest": decision["policyDigest"], "effectiveMode": decision["effectiveMode"], "usageTotals": summary["totals"], "parseErrors": summary["parseErrors"]}
    if prompt_path:
        value["promptCheck"] = prompt_check(resolution, prompt_path)
    root = Path(project)
    relative = f".mana/runtime/runs/{decision['executionId']}/budget-advisories"
    with decision_lock(root, decision["executionId"]):
        runtime.ensure_secure_directory(root, relative)
        names = runtime.safe_list_directory(root, relative)
        records = []
        existing = None
        for name in sorted(names):
            if re.fullmatch(r"[A-Za-z0-9._-]{1,180}\.json", name) is None:
                raise BudgetError("unexpected budget advisory entry")
            payload, _identity = runtime.safe_read_private_bytes(Path(f"{relative}/{name}"), project_root=root, max_bytes=16384)
            record = decode_object(payload)
            if payload != runtime.canonical_bytes(record) + b"\n" or record["executionId"] != decision["executionId"] or record["policyDigest"] != decision["policyDigest"]:
                raise BudgetError("budget advisory identity or canonical bytes differ")
            if name == f"{key}.json":
                if any(record.get(field) != item for field, item in value.items()):
                    raise BudgetError("conflicting duplicate budget invocation")
                existing = record
            records.append(record)
        if existing is None:
            records.append(value)
        errors = sum(record["parseErrors"] for record in records)
        totals = {field: sum(record["usageTotals"][field] for record in records) if all(record["usageTotals"][field] is not None for record in records) else None for field in runtime.USAGE_FIELDS}
        status = runtime.usage_totals_status(totals, errors)
        if status == "invalid":
            errors = max(1, errors)
        aggregate = {"usageStatus": "unavailable" if status == "invalid" else status, "totals": totals if status != "invalid" else dict.fromkeys(runtime.USAGE_FIELDS), "parseErrors": errors, "invocationKeys": sorted(record["invocationKey"] for record in records)}
        if existing is None:
            invocation_check = check_usage_value(resolution, summary)
            aggregate_check = check_usage_value(resolution, aggregate)
            # Incomplete aggregate coverage must not hide a reported invocation
            # threshold. Keep both scopes explicit and forward either warning
            # through the existing runner contract, with invalidity taking priority.
            combined_check = dict(invocation_check)
            if not aggregate_check["valid"]:
                combined_check.update(measured=False, valid=False, usageStatus="invalid")
            combined_check["warnings"] = list(dict.fromkeys(invocation_check["warnings"] + aggregate_check["warnings"]))
            combined_check["recommendation"] = (
                "human-scope-decision" if not combined_check["valid"] else
                "checkpoint-and-fresh-phase" if "checkpoint-and-fresh-phase" in (invocation_check["recommendation"], aggregate_check["recommendation"]) else None
            )
            value["invocationUsageCheck"] = invocation_check
            value["aggregateUsageCheck"] = aggregate_check
            value["usageCheck"] = combined_check
            runtime.atomic_write_bytes(root, f"{relative}/{key}.json", runtime.canonical_bytes(value) + b"\n", immutable=True)
        runtime.atomic_write_bytes(root, f".mana/runtime/runs/{decision['executionId']}/provider-budget-usage-aggregate-v1.json", runtime.canonical_bytes(aggregate) + b"\n")
        return existing if existing is not None else value


def main(argv: list[str]) -> int:
    try:
        if any(name in os.environ for name in FORBIDDEN_ENV):
            raise BudgetError("caller budget authority environment override is forbidden")
        if len(argv) == 4 and argv[1] == "resolve":
            output = resolve(argv[2], argv[3])
        elif len(argv) > 2 and argv[1] == "decision":
            parser = argparse.ArgumentParser()
            parser.add_argument("execution_id")
            parser.add_argument("--project-root", required=True)
            parser.add_argument("--requested-mode", choices=MODE_ORDER)
            for option in ("static-signal", "request-skill", "deep-load-skill"):
                parser.add_argument("--" + option, action="append", default=[])
            output = materialize_decision(parser.parse_args(argv[2:]))
        elif len(argv) == 4 and argv[1] == "capability-plan":
            output = capability_plan(load_object(argv[2]), argv[3])
        elif len(argv) == 4 and argv[1] == "prompt-check":
            output = prompt_check(load_object(argv[2]), argv[3])
        elif len(argv) == 4 and argv[1] == "usage-check":
            output = usage_check(load_object(argv[2]), argv[3])
        elif len(argv) in {6, 7} and argv[1] == "advisory":
            output = advisory(load_object(argv[2]), argv[3], argv[4], argv[5], argv[6] if len(argv) == 7 else None)
        else:
            raise BudgetError("usage: context-budget.py resolve <profile> <mode> | decision <execution-id> --project-root <root> [--requested-mode <mode>] | capability-plan <resolution> <capabilities> | prompt-check <resolution> <prompt> | usage-check <resolution> <summary> | advisory <resolution> <summary> <project> <invocation-key> [prompt]")
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
        return 0
    except runtime.ContractError as error:
        print(f"ERROR: CTX-08 budget control: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
