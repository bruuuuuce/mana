#!/usr/bin/env python3
"""CTX-06A/B state runtime and CTX-06C authoritative phase preparation."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("mana_context_runtime", HERE / "context-runtime.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load context-runtime contract library")
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)

RUN_SCHEMA = "mana.context-runtime.phase-run-directory/v1"
STATE_SCHEMA = "mana.context-runtime.run-state/v1"
TRANSITION_SCHEMA = "mana.context-runtime.transition-bundle/v1"
TRANSITION_RESULT_SCHEMA = "mana.context-runtime.transition-publication-result/v1"
PHASE_EXECUTION_PACKET_SCHEMA = "mana.context-runtime.phase-execution-packet/v1"
DIGEST = re.compile(r"^sha256-[a-f0-9]{64}$")
TRANSITION_ID = re.compile(r"^T-[a-f0-9]{64}$")
HEAD_TEMPORARY = re.compile(r"^\.run-state-v1\.json\.tmp\.[a-f0-9]{16}$")
POLICY_ID = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
EVIDENCE_REF = re.compile(r"^E-[a-f0-9]{64}$")
WORKSPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
MAX_OBJECTIVE_CHARS = 1024
TRANSCRIPT_ROLE_MARKER = re.compile(
    r"(?:\A\s*|[;|]\s*)(?:user|assistant|system|developer|tool)\s*:",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PhasePolicy:
    identity: str
    ordinal: int
    model_tier: str
    output_schema: str
    subagents: str
    evidence_kinds: tuple[str, ...]
    evidence_statuses: tuple[str, ...]
    retry_limit: int

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.identity, "ordinal": self.ordinal, "policy": {
            "modelTier": self.model_tier, "outputSchema": self.output_schema,
            "subagents": self.subagents, "evidenceKinds": list(self.evidence_kinds),
            "evidenceStatuses": list(self.evidence_statuses), "retryLimit": self.retry_limit,
        }}


@dataclass(frozen=True)
class PipelineDeclaration:
    profile_id: str
    workspace_kind: str
    target_kind: str
    human_gates: tuple[str, ...]
    phases: tuple[PhasePolicy, ...]


class PipelineSignal(BaseException):
    def __init__(self, signum: int, *, committed: bool = False) -> None:
        super().__init__(f"interrupted by signal {signum}")
        self.signum = signum
        self.committed = committed


class PublicationSignalGuard:
    """Record signals and linearize them around one explicit commit barrier."""

    def __init__(self) -> None:
        self._previous_handlers: dict[int, Any] = {}
        self._events: list[tuple[int, bool]] = []
        self._barrier_crossed = False

    def _record(self, signum: int, _frame: Any) -> None:
        self._events.append((signum, self._barrier_crossed))

    def __enter__(self) -> "PublicationSignalGuard":
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, self._record)
        return self

    def _first_event(self, *, after_barrier: bool) -> int | None:
        return next(
            (signum for signum, committed in self._events
             if committed is after_barrier),
            None,
        )

    def abort_if_observed(self) -> None:
        """Abort before publication when a signal has already been recorded."""
        before = self._first_event(after_barrier=False)
        if before is not None:
            raise PipelineSignal(before)

    def commit(self, staging: Any) -> None:
        """Cross the barrier exactly once, then mark the publication committed."""
        self.abort_if_observed()
        self._barrier_crossed = True
        # A handler that ran between the preceding check and this single state
        # transition classified its event as pre-commit, so this second check
        # closes that race without masking or sigpending().
        before = self._first_event(after_barrier=False)
        if before is not None:
            self._barrier_crossed = False
            raise PipelineSignal(before)
        staging.commit_publication()

    def __exit__(self, exception_type: Any, _exception: Any, _traceback: Any) -> bool:
        for signum, handler in self._previous_handlers.items():
            signal.signal(signum, handler)
        if exception_type is None:
            after = self._first_event(after_barrier=True)
            if after is not None:
                raise PipelineSignal(after, committed=True)
        return False


# Tests may inject deterministic failures. No CLI or environment surface exposes it.
_TEST_MATERIALIZE_HOOK: Callable[[int, int], None] | None = None
_TEST_PUBLICATION_HOOK: Callable[[str], None] | None = None
_TEST_TRANSITION_HOOK: Callable[[str], None] | None = None
_RUN_COMMITTED = False


def fail(message: str) -> None:
    raise runtime.ContractError(message)


def safe_absolute(path: str) -> Path:
    value = Path(path)
    return Path(os.path.abspath(value if value.is_absolute() else Path.cwd() / value))


def _inline_list(value: str, label: str) -> tuple[str, ...]:
    if not (value.startswith("[") and value.endswith("]")):
        fail(f"{label} must be an inline YAML list")
    content = value[1:-1].strip()
    if not content:
        return ()
    values = tuple(item.strip() for item in content.split(","))
    if any(POLICY_ID.fullmatch(item) is None for item in values):
        fail(f"{label} contains a malformed identifier")
    if len(values) != len(set(values)):
        fail(f"{label} contains duplicate entries")
    return values


def _profile_scalar(text: str, key: str) -> str:
    values = []
    for line in text.splitlines():
        match = re.fullmatch(rf"{re.escape(key)}:[ ]*(.*?)[ ]*", line)
        if match:
            values.append(match.group(1))
    if len(values) != 1 or not values[0]:
        fail(f"profile must declare exactly one non-empty {key}")
    return values[0]


def parse_pipeline_declaration(text: str, profile_id: str) -> PipelineDeclaration:
    lines = text.splitlines()
    occurrences = [(index, line) for index, line in enumerate(lines)
                   if re.match(r"^[ \t]*context_runtime[ \t]*:", line)]
    if not occurrences:
        fail(f"profile {profile_id!r} has no context_runtime.pipeline; runtime v2 is not configured")
    if len(occurrences) != 1 or occurrences[0][1] != "context_runtime:":
        fail(f"profile {profile_id!r} has a malformed or duplicate context_runtime declaration")
    block: list[str] = []
    for line in lines[occurrences[0][0] + 1:]:
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        block.append(line)

    top: dict[str, str] = {}
    phase_records: list[dict[str, str]] = []
    in_pipeline = False
    for line in block:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line:
            fail(f"profile {profile_id!r} has tab-indented context_runtime metadata")
        indent = len(line) - len(line.lstrip(" "))
        content = line[indent:]
        if indent == 2:
            match = re.fullmatch(
                r"(version|workspace_kind|target_kind|human_gates|pipeline):[ ]*(.*)", content)
            if match is None:
                fail(f"profile {profile_id!r} has an unknown context_runtime key")
            key, value = match.groups()
            if key in top:
                fail(f"profile {profile_id!r} duplicates context_runtime.{key}")
            top[key] = value
            in_pipeline = key == "pipeline"
            if in_pipeline and value:
                fail("context_runtime.pipeline must be a block list")
            continue
        if indent == 4 and in_pipeline:
            match = re.fullmatch(r"-[ ]+id:[ ]+([A-Za-z0-9_-]{1,80})[ ]*", content)
            if match is None:
                fail(f"profile {profile_id!r} has a malformed pipeline phase")
            phase_records.append({"id": match.group(1)})
            continue
        if indent == 6 and in_pipeline and phase_records:
            match = re.fullmatch(
                r"(ordinal|model_tier|output_schema|subagents|evidence_kinds|evidence_statuses|retry_limit):[ ]+(.+?)[ ]*",
                content)
            if match is None:
                fail(f"profile {profile_id!r} has an unknown or malformed phase policy")
            key, value = match.groups()
            if key in phase_records[-1]:
                fail(f"profile {profile_id!r} duplicates phase policy {key}")
            phase_records[-1][key] = value
            continue
        fail(f"profile {profile_id!r} has malformed context_runtime indentation")

    required_top = {"version", "workspace_kind", "target_kind", "human_gates", "pipeline"}
    if set(top) != required_top or top["version"] != "2" or not phase_records:
        fail(f"profile {profile_id!r} has no complete context_runtime.pipeline v2 declaration")
    if len(phase_records) > 128:
        fail(f"profile {profile_id!r} declares more than 128 runtime phases")
    if top["workspace_kind"] not in {"feature", "session", "either"}:
        fail("context_runtime.workspace_kind is invalid")
    if top["target_kind"] not in {"none", "repository", "pull_request"}:
        fail("context_runtime.target_kind is invalid")
    gates = _inline_list(top["human_gates"], "context_runtime.human_gates")
    if any(re.fullmatch(r"GATE-[A-Za-z0-9._-]{1,120}", gate) is None for gate in gates):
        fail("context_runtime.human_gates must contain canonical host gate IDs")

    phases: list[PhasePolicy] = []
    phase_ids: set[str] = set()
    required_phase = {"id", "ordinal", "model_tier", "output_schema", "subagents",
                      "evidence_kinds", "evidence_statuses", "retry_limit"}
    for expected_ordinal, record in enumerate(phase_records, start=1):
        if set(record) != required_phase:
            fail(f"phase {record['id']!r} has incomplete or unknown policy")
        identity = record["id"]
        if identity in phase_ids:
            fail(f"profile {profile_id!r} declares duplicate phase {identity!r}")
        phase_ids.add(identity)
        try:
            ordinal = int(record["ordinal"])
        except ValueError:
            fail(f"phase {identity!r} ordinal is invalid")
        if ordinal != expected_ordinal:
            fail(f"profile {profile_id!r} pipeline phase order does not match declared ordinals")
        if record["model_tier"] not in {"host", "economy", "full"}:
            fail(f"phase {identity!r} model_tier is invalid")
        if POLICY_ID.fullmatch(record["output_schema"]) is None:
            fail(f"phase {identity!r} output_schema is invalid")
        if record["subagents"] not in {"forbidden", "optional"}:
            fail(f"phase {identity!r} subagents policy is invalid")
        kinds = _inline_list(record["evidence_kinds"], f"phase {identity} evidence_kinds")
        statuses = _inline_list(record["evidence_statuses"], f"phase {identity} evidence_statuses")
        if any(status not in {"complete", "partial", "failed", "unavailable"}
               for status in statuses):
            fail(f"phase {identity!r} evidence status policy is invalid")
        try:
            retry_limit = int(record["retry_limit"])
        except ValueError:
            fail(f"phase {identity!r} retry_limit is invalid")
        if str(retry_limit) != record["retry_limit"] or not 0 <= retry_limit <= 16:
            fail(f"phase {identity!r} retry_limit must be a canonical integer from 0 through 16")
        phases.append(PhasePolicy(identity, ordinal, record["model_tier"],
                                  record["output_schema"], record["subagents"], kinds, statuses,
                                  retry_limit))

    approval_required = _profile_scalar(text, "human_approval_requirement")
    if approval_required not in {"true", "false"}:
        fail("human_approval_requirement must be true or false")
    if approval_required == "true" and not gates:
        fail(f"profile {profile_id!r} requires human approval but declares no context_runtime.human_gates")
    return PipelineDeclaration(
        profile_id, top["workspace_kind"], top["target_kind"], gates, tuple(phases)
    )


def load_declaration(framework_root: Path, profile_id: str) -> PipelineDeclaration:
    if runtime.IDENTIFIER.fullmatch(profile_id) is None:
        fail("profile id is malformed")
    text = runtime._host_text(framework_root / "profiles" / f"{profile_id}.yaml",
                              f"profile {profile_id}")
    if _profile_scalar(text, "name") != profile_id:
        fail("authoritative profile name does not match profile id")
    return parse_pipeline_declaration(text, profile_id)


def validate_objective(objective: str) -> None:
    if not objective.strip() or len(objective) > MAX_OBJECTIVE_CHARS:
        fail(f"objective must contain 1 through {MAX_OBJECTIVE_CHARS} characters")
    if objective.splitlines() != [objective] or any(ord(character) < 0x20 for character in objective):
        fail("objective must be one non-transcript line")
    try:
        structured = json.loads(objective)
    except json.JSONDecodeError:
        structured = None
    if isinstance(structured, (dict, list)):
        fail("objective must be a bounded instruction, not structured transcript data")
    if TRANSCRIPT_ROLE_MARKER.search(objective) is not None:
        fail("objective must not contain role-labelled transcript turns")


def validate_workspace(project_root: Path, workspace: str, declared_kind: str) -> str:
    workspace_id = runtime.derive_workspace_id(project_root, workspace)
    components = workspace.split("/")
    actual_kind = "feature" if components[1] == "features" else "session"
    if declared_kind != "either" and declared_kind != actual_kind:
        fail("workspace kind is not authorized by the profile")
    return workspace_id


def _bounded_target_value(label: str, value: str | None) -> str | None:
    if value is None:
        return None
    if (
        not value or value.strip() != value or len(value) > 256
        or any(ord(character) < 0x20 for character in value)
    ):
        fail(f"{label} is outside its bounded host-input contract")
    return value


def build_target(args: argparse.Namespace, target_kind: str) -> dict[str, Any]:
    repository = _bounded_target_value("target repository", args.target_repository)
    base = _bounded_target_value("target base", args.target_base)
    pr_number = args.target_pr_number
    if target_kind == "none":
        if repository is not None or base is not None or pr_number is not None:
            fail("profile does not permit a target")
    elif target_kind == "repository":
        if repository is None:
            fail("profile requires a repository target")
        if pr_number is not None:
            fail("repository target policy does not permit a pull request number")
    elif repository is None or base is None or pr_number is None:
        fail("profile requires repository, base, and pull request target metadata")
    return {"repository": repository, "base": base, "prNumber": pr_number}


def load_evidence_refs(project_root: Path, execution_id: str,
                       manifest_argument: str | None, requested_refs: list[str],
                       initial_phase: PhasePolicy, workspace_id: str,
                       ) -> tuple[list[str], str | None]:
    if len(requested_refs) != len(set(requested_refs)):
        fail("duplicate evidence reference")
    if any(EVIDENCE_REF.fullmatch(reference) is None for reference in requested_refs):
        fail("evidence reference must be a canonical CTX-05 evidence ID")
    if manifest_argument is None:
        if requested_refs:
            fail("evidence references require an authoritative CTX-05 evidence manifest")
        return [], None
    expected_relative = f".mana/runtime-evidence/executions/{execution_id}/manifest.json"
    if manifest_argument != expected_relative:
        fail("evidence manifest must be the canonical CTX-05 manifest for this execution and project")
    payload = runtime.safe_read_bytes(Path(expected_relative), project_root=project_root,
                                      max_bytes=runtime.MAX_BYTES["evidence-manifest"])
    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot read authoritative evidence manifest: {error}")
    if not isinstance(manifest, dict):
        fail("authoritative evidence manifest must be an object")
    runtime.validate_model("evidence-manifest", manifest)
    if manifest["executionId"] != execution_id:
        fail("evidence manifest belongs to a different execution")
    if manifest["workspaceId"] != workspace_id:
        fail("evidence manifest belongs to a different authoritative workspace")
    records = {item["evidenceId"]: item for item in manifest["items"]}
    for reference in requested_refs:
        if reference not in records:
            fail(f"evidence reference is absent from the authoritative manifest: {reference}")
        record = records[reference]
        if record["kind"] not in initial_phase.evidence_kinds:
            fail(f"evidence reference is not allowed by initial phase kind policy: {reference}")
        if record["collectionStatus"] not in initial_phase.evidence_statuses:
            fail(f"evidence reference status is not allowed by initial phase policy: {reference}")
    return requested_refs, expected_relative


def relative_run_directory(execution_id: str) -> str:
    return f".mana/runtime/runs/{execution_id}"


def validate_run_directory(value: dict[str, Any], declaration: PipelineDeclaration) -> None:
    expected_keys = {"schemaVersion", "executionId", "profileId", "provider", "phaseOrder",
                     "pipeline", "initialPhaseId", "executionEnvelopeRef", "contextManifestRef",
                     "workspace", "workspaceId", "evidenceManifestPath"}
    if set(value) != expected_keys:
        fail("run directory record has an invalid field set")
    if value["schemaVersion"] != RUN_SCHEMA:
        fail("run directory schema version is invalid")
    if re.fullmatch(r"execution-[A-Za-z0-9._-]{1,120}", value["executionId"]) is None:
        fail("run directory execution id is invalid")
    if value["profileId"] != declaration.profile_id:
        fail("run directory profile id does not match the authoritative declaration")
    if value["provider"] not in {"codex", "claude", "opencode"}:
        fail("run directory provider is invalid")
    if value["pipeline"] != [phase.as_dict() for phase in declaration.phases]:
        fail("run directory pipeline does not match the authoritative declaration")
    if value["phaseOrder"] != [phase.identity for phase in declaration.phases]:
        fail("run directory phase order does not match the authoritative declaration")
    if value["initialPhaseId"] != declaration.phases[0].identity:
        fail("run directory initial phase does not match the authoritative declaration")
    if value["executionEnvelopeRef"] != "G-001" or value["contextManifestRef"] != "M-001":
        fail("run directory host references are invalid")
    if not runtime.is_safe_relative_path(value["workspace"]):
        fail("run directory workspace binding is invalid")
    if re.fullmatch(r"W-[a-f0-9]{64}", value["workspaceId"]) is None:
        fail("run directory workspace identity is invalid")
    evidence_path = value["evidenceManifestPath"]
    if evidence_path is not None and evidence_path != (
        f".mana/runtime-evidence/executions/{value['executionId']}/manifest.json"
    ):
        fail("run directory evidence binding is invalid")


def _state_value(execution_id: str, profile_id: str, declaration: PipelineDeclaration,
                 *, current_phase: str, latest_checkpoint: str | None = None,
                 status: str = "active", attempts: dict[str, int] | None = None,
                 revision: int = 0) -> dict[str, Any]:
    phase_by_id = {phase.identity: phase for phase in declaration.phases}
    current_ordinal = phase_by_id[current_phase].ordinal
    if attempts is None:
        attempts = {phase.identity: (1 if phase.ordinal == 1 else 0)
                    for phase in declaration.phases}
    return {
        "schemaVersion": STATE_SCHEMA,
        "executionId": execution_id,
        "executionVersion": 1,
        "profileId": profile_id,
        "revision": revision,
        "status": status,
        "currentPhaseId": current_phase,
        "currentPhaseOrdinal": current_ordinal,
        "currentAttempt": attempts[current_phase],
        "latestCheckpointRef": latest_checkpoint,
        "transitionId": None,
        "previousStateDigest": None,
        "attempts": attempts,
    }


def validate_state(value: dict[str, Any], execution_id: str, profile_id: str,
                   declaration: PipelineDeclaration) -> None:
    runtime.validate_structure("run-state", value)
    if declaration.profile_id != profile_id:
        fail("run state declaration is bound to a different authoritative profile")
    if (value["executionId"] != execution_id or value["executionVersion"] != 1
            or value["profileId"] != profile_id):
        fail("run state identity is invalid")
    phase_ids = {phase.identity for phase in declaration.phases}
    if value["currentPhaseId"] not in phase_ids:
        fail("run state current phase is undeclared")
    phase = next(phase for phase in declaration.phases if phase.identity == value["currentPhaseId"])
    if value["currentPhaseOrdinal"] != phase.ordinal:
        fail("run state phase ordinal is inconsistent")
    if set(value["attempts"]) != phase_ids:
        fail("run state attempts are invalid")
    for declared in declaration.phases:
        attempt = value["attempts"][declared.identity]
        if attempt > 1 + declared.retry_limit:
            fail("run state attempts exceed the host-owned phase retry limit")
        if declared.ordinal <= phase.ordinal and attempt < 1:
            fail("run state omits a host-materialized phase attempt")
        if declared.ordinal > phase.ordinal and attempt != 0:
            fail("run state claims an attempt for a future phase")
    if value["currentAttempt"] != value["attempts"][phase.identity]:
        fail("run state current attempt is inconsistent")
    minimum_revision = sum(value["attempts"].values()) - 1
    if value["revision"] < minimum_revision:
        fail("run state revision is below its host-derived attempt history")
    if value["latestCheckpointRef"] is None:
        if (value["revision"] != 0 or value["status"] != "active" or phase.ordinal != 1
                or value["transitionId"] is not None
                or value["previousStateDigest"] is not None):
            fail("only the host-derived initial state may omit a checkpoint reference")
    elif (value["revision"] == 0
          or TRANSITION_ID.fullmatch(value["transitionId"] or "") is None
          or DIGEST.fullmatch(value["previousStateDigest"] or "") is None):
        fail("a checkpoint-bearing run state must have a transition-bound positive revision")
    if value["status"] == "completed" and phase.ordinal != len(declaration.phases):
        fail("completed run state must remain on the terminal declared phase")


@dataclass(frozen=True)
class CheckpointTransition:
    """One pure R1A decision; R1B will own durable multi-file publication."""

    kind: str
    previous_revision: int
    state: dict[str, Any]
    effective_authority: runtime.EffectiveAuthority

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "previousRevision": self.previous_revision,
            "state": self.state,
            "effectiveAuthority": self.effective_authority.as_dict(),
        }


def _phase_by_id(declaration: PipelineDeclaration, phase_id: str) -> PhasePolicy:
    try:
        return next(phase for phase in declaration.phases if phase.identity == phase_id)
    except StopIteration:
        fail("checkpoint phase is not host-declared")


def _evidence_records(evidence_manifest: dict[str, Any] | None,
                      execution_id: str, workspace_id: str) -> dict[str, dict[str, Any]]:
    if evidence_manifest is None:
        return {}
    runtime.validate_model("evidence-manifest", evidence_manifest)
    if evidence_manifest["executionId"] != execution_id:
        fail("CTX-05 evidence manifest is bound to a different authoritative execution")
    if evidence_manifest["workspaceId"] != workspace_id:
        fail("CTX-05 evidence manifest is bound to a different authoritative workspace")
    records = {item["evidenceId"]: item for item in evidence_manifest["items"]}
    if len(records) != len(evidence_manifest["items"]):
        fail("CTX-05 evidence manifest contains duplicate evidence IDs")
    return records


def _nested_evidence_refs(checkpoint: dict[str, Any]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if key == "evidenceRefs" and path != "$":
                    refs.extend((f"{child_path}[{index}]", ref)
                                for index, ref in enumerate(child))
                else:
                    visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(checkpoint, "$")
    return refs


def _validate_evidence_refs(refs: list[tuple[str, str]],
                            records: dict[str, dict[str, Any]],
                            phase: PhasePolicy) -> None:
    for path, ref in refs:
        record = records.get(ref)
        if record is None:
            fail(f"{path} is absent from the authoritative CTX-05 manifest")
        if (record["kind"] not in phase.evidence_kinds
                or record["collectionStatus"] not in phase.evidence_statuses):
            fail(f"{path} is outside phase {phase.identity!r} evidence policy")


def _validate_authority_binding(
    authority: runtime.HostAuthorityContext | None,
    envelope: dict[str, Any], declaration: PipelineDeclaration,
) -> None:
    if authority is None:
        return
    if not isinstance(authority, runtime.HostAuthorityContext):
        fail("authority must be a validated HostAuthorityContext")
    host = authority.value
    identity = host["executionIdentity"]
    expected_identity = (
        envelope["executionId"], envelope["executionVersion"], envelope["profileId"]
    )
    if (identity["executionId"], identity["executionVersion"], identity["profileId"]) != expected_identity:
        fail("host authority is bound to a different execution or profile")
    if host["effectivePermissions"] != envelope["permissions"]:
        fail("host authority permissions do not match the authoritative execution envelope")
    if {gate["gateId"] for gate in host["humanGates"]} != set(declaration.human_gates):
        fail("host authority gates do not match the authoritative profile pipeline")


def _digest_bytes(payload: bytes) -> str:
    return "sha256-" + hashlib.sha256(payload).hexdigest()


def _digest_value(value: Any) -> str:
    return _digest_bytes(runtime.canonical_bytes(value))


def _authority_digest(authority: runtime.HostAuthorityContext | None) -> str | None:
    return None if authority is None else _digest_value(authority.value)


def _operation_digest(
    operation: str, checkpoint: dict[str, Any],
    authority: runtime.HostAuthorityContext | None,
) -> str:
    return _digest_value({
        "schemaVersion": "mana.context-runtime.transition-operation/v1",
        "operation": operation,
        "checkpoint": checkpoint,
        "authority": None if authority is None else authority.value,
    })


def _transition_id(
    operation: str, previous_state_digest: str, checkpoint: dict[str, Any],
    authority: runtime.HostAuthorityContext | None,
) -> str:
    seed = {
        "schemaVersion": "mana.context-runtime.transition-identity/v1",
        "operation": operation,
        "previousStateDigest": previous_state_digest,
        "checkpointDigest": _digest_value(checkpoint),
        "authorityDigest": _authority_digest(authority),
    }
    return "T-" + hashlib.sha256(runtime.canonical_bytes(seed)).hexdigest()


def _derive_state(previous: dict[str, Any], checkpoint_id: str, *, status: str,
                  transition_id: str, previous_state_digest: str,
                  phase: PhasePolicy | None = None,
                  attempts: dict[str, int] | None = None) -> dict[str, Any]:
    result = dict(previous)
    result["revision"] = previous["revision"] + 1
    result["status"] = status
    result["latestCheckpointRef"] = checkpoint_id
    result["transitionId"] = transition_id
    result["previousStateDigest"] = previous_state_digest
    if attempts is not None:
        result["attempts"] = attempts
    if phase is not None:
        result["currentPhaseId"] = phase.identity
        result["currentPhaseOrdinal"] = phase.ordinal
    result["currentAttempt"] = result["attempts"][result["currentPhaseId"]]
    return result


def reduce_checkpoint_transition(
    previous_state: dict[str, Any], checkpoint: dict[str, Any], *,
    declaration: PipelineDeclaration, envelope: dict[str, Any],
    context_manifest: dict[str, Any], evidence_manifest: dict[str, Any] | None,
    framework_root: Path,
    authority: runtime.HostAuthorityContext | None = None,
    static_signals: list[str] | None = None,
    requested_skills: list[str] | None = None,
    deep_load_skills: list[str] | None = None,
) -> CheckpointTransition:
    """Validate one checkpoint and derive the sole permissible next run state."""
    runtime.validate_model("phase-checkpoint", checkpoint)
    runtime.validate_structure("execution-envelope", envelope)
    runtime.validate_model("context-manifest", context_manifest)
    execution_id = envelope["executionId"]
    profile_id = envelope["profileId"]
    workspace_id = envelope["workspaceId"]
    validate_state(previous_state, execution_id, profile_id, declaration)
    if envelope["executionVersion"] != previous_state["executionVersion"]:
        fail("execution envelope and previous state versions do not match")
    if tuple(envelope["humanGates"]) != declaration.human_gates:
        fail("execution envelope gates do not match the authoritative profile pipeline")
    if previous_state["status"] in {"completed", "interrupted"}:
        fail("terminal or interrupted run state does not accept checkpoint transitions in R1A")
    expected_identity = (execution_id, envelope["executionVersion"], profile_id)
    if (checkpoint["executionId"], checkpoint["executionVersion"], checkpoint["profileId"]) \
            != expected_identity:
        fail("checkpoint is bound to a different authoritative execution or profile")
    if checkpoint["phaseId"] != previous_state["currentPhaseId"]:
        fail("checkpoint phase is not the current host-derived phase")
    if previous_state["status"] == "blocked":
        if checkpoint["checkpointId"] != previous_state["latestCheckpointRef"]:
            fail("a blocked run can only reconsider its accepted checkpoint with host authority")
    elif checkpoint["checkpointId"] == previous_state["latestCheckpointRef"]:
        fail("checkpoint ID was already consumed by the reducer")

    if (context_manifest["executionId"] != execution_id
            or context_manifest["profileId"] != profile_id):
        fail("CTX-04 manifest is bound to a different authoritative execution or profile")
    runtime.authoritative_validate_context_manifest(
        context_manifest, framework_root, profile_id, execution_id,
        static_signals=static_signals, requested_skills=requested_skills,
        deep_load_skills=deep_load_skills,
    )
    if not set(checkpoint["activatedSkills"]).issubset(
            {item["id"] for item in context_manifest["activatedSkills"]}):
        fail("checkpoint activates a skill outside the authoritative CTX-04 manifest")

    current = _phase_by_id(declaration, checkpoint["phaseId"])
    action = checkpoint["nextActionRequest"]
    if action is None:
        fail("checkpoint must declare one next action")
    next_phase = declaration.phases[current.ordinal] \
        if current.ordinal < len(declaration.phases) else None
    if checkpoint["status"] in {"partial", "blocked"}:
        if action["kind"] != "repeat-current-phase" or action["targetId"] != current.identity:
            fail("partial or blocked checkpoint may request only the current declared phase")
        target_phase = current
    elif action["kind"] == "next-declared-phase":
        if next_phase is None or action["targetId"] != next_phase.identity:
            fail("checkpoint cannot select a phase outside the host-declared order")
        target_phase = next_phase
    elif action["kind"] == "stop":
        if action["targetId"] is not None or current.ordinal != len(declaration.phases):
            fail("stop is valid only after the terminal declared pipeline phase")
        target_phase = current
    else:
        fail("complete checkpoint must advance or stop at the declared terminal phase")

    records = _evidence_records(evidence_manifest, execution_id, workspace_id)
    _validate_evidence_refs(_nested_evidence_refs(checkpoint), records, current)
    _validate_evidence_refs(
        [(f"$.evidenceRefs[{index}]", ref)
         for index, ref in enumerate(checkpoint["evidenceRefs"])],
        records, target_phase,
    )

    requests = checkpoint["approvalRequests"]
    request_gates = [request["gateId"] for request in requests]
    if len(request_gates) != len(set(request_gates)):
        fail("checkpoint contains multiple approval requests for one human gate")
    if not set(request_gates).issubset(declaration.human_gates):
        fail("checkpoint requests a gate outside the authoritative profile pipeline")
    if action["kind"] == "stop" and set(request_gates) != set(declaration.human_gates):
        fail("terminal completion must request every authoritative human gate exactly once")
    _validate_authority_binding(authority, envelope, declaration)
    effective = runtime.evaluate_checkpoint(checkpoint, authority)
    operation = "resume" if previous_state["status"] == "blocked" else "accept-checkpoint"
    previous_state_digest = _digest_value(previous_state)
    transition_id = _transition_id(
        operation, previous_state_digest, checkpoint, authority
    )
    authority_resolved = bool(requests) and not effective.unresolved_approvals
    if previous_state["status"] == "blocked" and not authority_resolved:
        fail("blocked run is not resumable without matching host approval authority")

    should_block = bool(effective.unresolved_approvals)
    if checkpoint["status"] == "blocked" and not authority_resolved:
        should_block = True
    if action["kind"] == "repeat-current-phase" \
            and previous_state["attempts"][current.identity] >= 1 + current.retry_limit:
        should_block = True
    if previous_state["status"] == "blocked" and should_block:
        fail("host authority cannot override an exhausted retry limit or unresolved gate")
    if should_block:
        next_state = _derive_state(
            previous_state, checkpoint["checkpointId"], status="blocked",
            transition_id=transition_id, previous_state_digest=previous_state_digest,
        )
        validate_state(next_state, execution_id, profile_id, declaration)
        return CheckpointTransition(
            "blocked", previous_state["revision"], next_state, effective
        )

    attempts = dict(previous_state["attempts"])
    if action["kind"] == "repeat-current-phase":
        attempts[current.identity] += 1
        next_state = _derive_state(
            previous_state, checkpoint["checkpointId"], status="active",
            transition_id=transition_id, previous_state_digest=previous_state_digest,
            phase=current, attempts=attempts,
        )
        kind = "repeat-current-phase"
    elif action["kind"] == "next-declared-phase":
        assert next_phase is not None
        if attempts[next_phase.identity] != 0:
            fail("host state already records an attempt for the next declared phase")
        attempts[next_phase.identity] = 1
        next_state = _derive_state(
            previous_state, checkpoint["checkpointId"], status="active",
            transition_id=transition_id, previous_state_digest=previous_state_digest,
            phase=next_phase, attempts=attempts,
        )
        kind = "next-declared-phase"
    else:
        if effective.unresolved_approvals:
            fail("terminal human gates are unresolved")
        next_state = _derive_state(
            previous_state, checkpoint["checkpointId"], status="completed",
            transition_id=transition_id, previous_state_digest=previous_state_digest,
        )
        kind = "completed"
    validate_state(next_state, execution_id, profile_id, declaration)
    return CheckpointTransition(kind, previous_state["revision"], next_state, effective)


@dataclass(frozen=True)
class RunContext:
    project_root: Path
    framework_root: Path
    run_relative: str
    declaration: PipelineDeclaration
    run_directory: dict[str, Any]
    envelope: dict[str, Any]
    context_manifest: dict[str, Any]
    evidence_manifest: dict[str, Any] | None
    objective: str
    state: dict[str, Any]
    state_bytes: bytes


@dataclass(frozen=True)
class PublishedBundle:
    manifest: dict[str, Any]
    checkpoint: dict[str, Any]
    state: dict[str, Any]
    phase_input: dict[str, Any] | None
    authority: runtime.HostAuthorityContext | None


def _decode_canonical_object(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot decode {label}: {error}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    if payload != runtime.canonical_bytes(value) + b"\n":
        fail(f"{label} is not canonical immutable JSON")
    return value


def _read_run_object(
    project_root: Path, relative: str, label: str, *, max_bytes: int,
) -> tuple[dict[str, Any], bytes]:
    payload = runtime.safe_read_bytes(
        Path(relative), project_root=project_root, max_bytes=max_bytes
    )
    return _decode_canonical_object(payload, label), payload


def _load_run_context(args: argparse.Namespace) -> RunContext:
    project_root = safe_absolute(args.project_root)
    framework_root = safe_absolute(args.framework_root)
    runtime.validate_secure_root(project_root)
    runtime.validate_secure_root(framework_root)
    run_relative = relative_run_directory(args.execution_id)
    run_directory, _ = _read_run_object(
        project_root, f"{run_relative}/run-directory-v1.json", "run directory", max_bytes=64 * 1024
    )
    declaration = load_declaration(framework_root, run_directory.get("profileId", ""))
    validate_run_directory(run_directory, declaration)
    if run_directory["executionId"] != args.execution_id:
        fail("run directory is bound to a different execution")
    envelope, _ = _read_run_object(
        project_root, f"{run_relative}/execution-envelope-v1.json",
        "execution envelope", max_bytes=runtime.MAX_BYTES["execution-envelope"] or 0,
    )
    runtime.validate_structure("execution-envelope", envelope)
    workspace_id = runtime.derive_workspace_id(project_root, run_directory["workspace"])
    if (
        run_directory["workspaceId"] != workspace_id
        or envelope["workspace"] != run_directory["workspace"]
        or envelope["workspaceId"] != workspace_id
    ):
        fail("execution envelope and run record workspace bindings differ")
    context_manifest, _ = _read_run_object(
        project_root, f"{run_relative}/context-manifest-v1.json",
        "context manifest", max_bytes=runtime.MAX_BYTES["context-manifest"] or 0,
    )
    runtime.validate_model("context-manifest", context_manifest)
    state, state_bytes = _read_run_object(
        project_root, f"{run_relative}/run-state-v1.json",
        "run-state HEAD", max_bytes=runtime.MAX_BYTES["run-state"] or 0,
    )
    validate_state(state, args.execution_id, run_directory["profileId"], declaration)
    if (envelope["executionId"] != args.execution_id
            or envelope["profileId"] != run_directory["profileId"]):
        fail("execution envelope is not bound to the run directory")
    evidence_manifest = None
    evidence_path = run_directory["evidenceManifestPath"]
    if evidence_path is not None:
        evidence_manifest, _ = _read_run_object(
            project_root, evidence_path, "evidence manifest",
            max_bytes=runtime.MAX_BYTES["evidence-manifest"] or 0,
        )
        runtime.validate_model("evidence-manifest", evidence_manifest)
        if (
            evidence_manifest["executionId"] != args.execution_id
            or evidence_manifest["workspaceId"] != workspace_id
        ):
            fail("evidence manifest is not bound to the authoritative run workspace")
    initial = declaration.phases[0]
    initial_input, _ = _read_run_object(
        project_root,
        f"{run_relative}/phases/{initial.ordinal:03d}-{initial.identity}/phase-input-v1.json",
        "initial phase input", max_bytes=runtime.MAX_BYTES["phase-input"] or 0,
    )
    runtime.validate_model("phase-input", initial_input)
    if (initial_input["executionId"] != args.execution_id
            or initial_input["phaseId"] != initial.identity
            or initial_input["checkpointRef"] is not None):
        fail("initial phase input is not bound to the authoritative run")
    return RunContext(
        project_root, framework_root, run_relative, declaration, run_directory,
        envelope, context_manifest, evidence_manifest, initial_input["objective"],
        state, state_bytes,
    )


def _bundle_relative(context: RunContext, transition_id: str) -> str:
    return f"{context.run_relative}/transitions/{transition_id}"


def _load_published_bundle(context: RunContext, transition_id: str) -> PublishedBundle:
    if TRANSITION_ID.fullmatch(transition_id) is None:
        fail("published transition directory name is malformed")
    relative = _bundle_relative(context, transition_id)
    manifest, _ = _read_run_object(
        context.project_root, f"{relative}/transition-v1.json", "transition bundle",
        max_bytes=runtime.MAX_BYTES["transition-bundle"] or 0,
    )
    runtime.validate_structure("transition-bundle", manifest)
    if manifest["transitionId"] != transition_id:
        fail("transition bundle directory and identity differ")
    if (manifest["executionId"] != context.envelope["executionId"]
            or manifest["executionVersion"] != context.envelope["executionVersion"]
            or manifest["profileId"] != context.envelope["profileId"]):
        fail("transition bundle is bound to a different run")
    checkpoint, _ = _read_run_object(
        context.project_root, f"{relative}/{manifest['checkpointRef']}",
        "bundled checkpoint", max_bytes=runtime.MAX_BYTES["phase-checkpoint"] or 0,
    )
    runtime.validate_model("phase-checkpoint", checkpoint)
    state, _ = _read_run_object(
        context.project_root, f"{relative}/{manifest['runStateRef']}",
        "bundled run state", max_bytes=runtime.MAX_BYTES["run-state"] or 0,
    )
    validate_state(
        state, context.envelope["executionId"], context.envelope["profileId"],
        context.declaration,
    )
    phase_input = None
    if manifest["phaseInputRef"] is not None:
        phase_input, _ = _read_run_object(
            context.project_root, f"{relative}/{manifest['phaseInputRef']}",
            "bundled phase input", max_bytes=runtime.MAX_BYTES["phase-input"] or 0,
        )
        runtime.validate_model("phase-input", phase_input)
    authority = None
    if manifest["authorityRef"] is not None:
        authority_value, _ = _read_run_object(
            context.project_root, f"{relative}/{manifest['authorityRef']}",
            "bundled authority", max_bytes=runtime.MAX_BYTES["host-authority-context"] or 0,
        )
        authority = runtime.load_host_authority(authority_value)
    if manifest["operation"] == "resume" and authority is None:
        fail("resume bundle omits its host authority snapshot")
    if manifest["operation"] == "accept-checkpoint" and authority is not None:
        fail("checkpoint acceptance bundle must not contain resume authority")
    expected_transition_id = _transition_id(
        manifest["operation"], manifest["previousStateDigest"], checkpoint, authority
    )
    if expected_transition_id != transition_id:
        fail("transition ID is not the deterministic digest of its immutable operation")
    if manifest["operationDigest"] != _operation_digest(
            manifest["operation"], checkpoint, authority):
        fail("transition operation digest does not match its immutable inputs")
    if (manifest["checkpointId"] != checkpoint["checkpointId"]
            or manifest["checkpointDigest"] != _digest_value(checkpoint)
            or manifest["authorityDigest"] != _authority_digest(authority)
            or manifest["nextStateDigest"] != _digest_value(state)):
        fail("transition bundle content digest mismatch")
    if (state["revision"] != manifest["previousRevision"] + 1
            or state["previousStateDigest"] != manifest["previousStateDigest"]
            or state["transitionId"] != transition_id
            or state["latestCheckpointRef"] != checkpoint["checkpointId"]):
        fail("bundled run state is not bound to its transition manifest")
    expected_previous_id = manifest["previousTransitionId"]
    if expected_previous_id is not None and TRANSITION_ID.fullmatch(expected_previous_id) is None:
        fail("transition bundle has a malformed previous transition ID")
    if phase_input is None:
        if state["status"] == "active":
            fail("active transition bundle omits its next authoritative phase input")
    elif (state["status"] != "active"
          or phase_input["executionId"] != state["executionId"]
          or phase_input["phaseId"] != state["currentPhaseId"]
          or phase_input["checkpointRef"] != checkpoint["checkpointId"]
          or phase_input["objective"] != context.objective
          or phase_input["evidenceRefs"] != checkpoint["evidenceRefs"]):
        fail("bundled phase input is not derived from its checkpoint and next state")
    return PublishedBundle(manifest, checkpoint, state, phase_input, authority)


def _published_bundles(context: RunContext) -> dict[str, PublishedBundle]:
    transitions_relative = f"{context.run_relative}/transitions"
    try:
        names = runtime.safe_list_directory(context.project_root, transitions_relative)
    except runtime.ContractError as error:
        if "cannot list directory" in str(error):
            return {}
        raise
    bundles: dict[str, PublishedBundle] = {}
    for name in names:
        if name.startswith("."):
            continue
        if TRANSITION_ID.fullmatch(name) is None:
            fail("transition store contains an unexpected public entry")
        bundles[name] = _load_published_bundle(context, name)
    return bundles


def _committed_transition_ids(
    context: RunContext, bundles: dict[str, PublishedBundle], args: argparse.Namespace,
) -> set[str]:
    state = context.state
    committed: set[str] = set()
    reverse_chain: list[PublishedBundle] = []
    transition_id = state["transitionId"]
    expected_digest = _digest_value(state)
    expected_revision = state["revision"]
    while transition_id is not None:
        if transition_id in committed:
            fail("authoritative transition chain contains a cycle")
        bundle = bundles.get(transition_id)
        if bundle is None:
            fail("run-state HEAD references a missing transition bundle")
        manifest = bundle.manifest
        if (manifest["nextStateDigest"] != expected_digest
                or bundle.state["revision"] != expected_revision):
            fail("run-state HEAD transition chain has a digest or revision mismatch")
        committed.add(transition_id)
        reverse_chain.append(bundle)
        transition_id = manifest["previousTransitionId"]
        expected_digest = manifest["previousStateDigest"]
        expected_revision = manifest["previousRevision"]
    if expected_revision != 0:
        fail("authoritative transition chain does not terminate at initial revision zero")
    initial = _state_value(
        context.envelope["executionId"], context.envelope["profileId"],
        context.declaration, current_phase=context.declaration.phases[0].identity,
    )
    if expected_digest != _digest_value(initial):
        fail("authoritative transition chain does not bind to the derived initial state")
    previous = initial
    for bundle in reversed(reverse_chain):
        replay_context = RunContext(
            context.project_root, context.framework_root, context.run_relative,
            context.declaration, context.run_directory, context.envelope,
            context.context_manifest, context.evidence_manifest, context.objective,
            previous, runtime.canonical_bytes(previous) + b"\n",
        )
        transition, phase_input = _reduce_durable_operation(
            replay_context, bundle.manifest["operation"], bundle.checkpoint,
            bundle.authority, args,
        )
        expected_manifest = _bundle_manifest(
            replay_context, bundle.manifest["operation"], bundle.checkpoint,
            bundle.authority, transition, phase_input,
        )
        if (transition.state != bundle.state or phase_input != bundle.phase_input
                or expected_manifest != bundle.manifest):
            fail("authoritative transition bundle does not replay from its previous state")
        previous = bundle.state
    if previous != state:
        fail("authoritative transition replay does not reproduce run-state HEAD")
    return committed


def _reconcile_head_exchange_residue_unlocked(
    context: RunContext, bundles: dict[str, PublishedBundle], committed: set[str],
) -> bool:
    """Remove only the verified displaced HEAD of the current committed CAS."""
    nofollow, directory = runtime._require_secure_dir_fd_support()
    root_fd, parent_fds = -1, []
    try:
        root_fd = runtime._open_directory(
            context.project_root, dir_fd=None, nofollow=nofollow, directory=directory
        )
        components = context.run_relative.split("/")
        run_fd, parent_fds = runtime._walk_existing_parent(
            root_fd, components, nofollow, directory
        )
        names = [
            name for name in os.listdir(run_fd)
            if name.startswith(".run-state-v1.json.tmp.")
        ]
        if not names:
            return False
        if len(names) != 1 or HEAD_TEMPORARY.fullmatch(names[0]) is None:
            fail("run-state HEAD exchange residue is ambiguous")
        if context.state["transitionId"] is None:
            fail("initial run-state cannot authorize HEAD residue cleanup")
        transition_id = context.state["transitionId"]
        if transition_id not in committed:
            fail("HEAD residue is not associated with a committed transition")
        current_bundle = bundles[transition_id]
        previous_id = current_bundle.manifest["previousTransitionId"]
        if previous_id is None:
            expected_state = _state_value(
                context.envelope["executionId"], context.envelope["profileId"],
                context.declaration,
                current_phase=context.declaration.phases[0].identity,
            )
        else:
            previous_bundle = bundles.get(previous_id)
            if previous_bundle is None or previous_id not in committed:
                fail("committed HEAD residue has no authoritative previous state")
            expected_state = previous_bundle.state
        expected_bytes = runtime.canonical_bytes(expected_state) + b"\n"
        if current_bundle.manifest["previousStateDigest"] != _digest_value(expected_state):
            fail("committed transition does not bind the displaced HEAD")

        name = names[0]
        residue_fd = -1
        try:
            residue_fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | nofollow, dir_fd=run_fd)
            metadata = os.fstat(residue_fd)
            identity = runtime._entry_identity(metadata)
            if not runtime.stat.S_ISREG(metadata.st_mode):
                fail("run-state HEAD exchange residue is not a regular file")
            chunks: list[bytes] = []
            total = 0
            limit = runtime.MAX_BYTES["run-state"] or 0
            while True:
                chunk = os.read(residue_fd, 64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    fail("run-state HEAD exchange residue exceeds its bound")
                chunks.append(chunk)
            if (
                b"".join(chunks) != expected_bytes
                or not runtime._verify_identity(run_fd, name, identity)
                or not runtime._same_existing_directory_from_root(
                    root_fd, components, run_fd, nofollow, directory
                )
            ):
                fail("run-state HEAD exchange residue is not the verified displaced HEAD")
            os.unlink(name, dir_fd=run_fd)
            os.fsync(run_fd)
        finally:
            if residue_fd >= 0:
                os.close(residue_fd)
        return True
    except OSError as error:
        fail(f"cannot reconcile run-state HEAD exchange residue: {error}")
    finally:
        for opened_fd in reversed(parent_fds):
            os.close(opened_fd)
        if root_fd >= 0:
            os.close(root_fd)


def _phase_input_for(
    context: RunContext, transition: CheckpointTransition, checkpoint: dict[str, Any],
) -> dict[str, Any] | None:
    if transition.state["status"] != "active":
        return None
    value = {
        "schemaVersion": "mana.context-runtime.phase-input/v1",
        "executionId": context.envelope["executionId"],
        "phaseId": transition.state["currentPhaseId"],
        "executionEnvelopeRef": "G-001",
        "contextManifestRef": "M-001",
        "objective": context.objective,
        "checkpointRef": checkpoint["checkpointId"],
        "evidenceRefs": list(checkpoint["evidenceRefs"]),
    }
    runtime.validate_model("phase-input", value)
    return value


def _reduce_durable_operation(
    context: RunContext, operation: str, checkpoint: dict[str, Any],
    authority: runtime.HostAuthorityContext | None, args: argparse.Namespace,
) -> tuple[CheckpointTransition, dict[str, Any] | None]:
    if operation == "accept-checkpoint":
        if context.state["status"] == "blocked" or authority is not None:
            fail("blocked runs require resume and checkpoint acceptance takes no authority")
    elif operation == "resume":
        if context.state["status"] != "blocked" or authority is None:
            fail("resume requires a blocked HEAD and host authority")
    else:
        fail("unknown durable transition operation")
    if _TEST_TRANSITION_HOOK is not None:
        _TEST_TRANSITION_HOOK("before-checkpoint-acceptance")
    transition = reduce_checkpoint_transition(
        context.state, checkpoint, declaration=context.declaration,
        envelope=context.envelope, context_manifest=context.context_manifest,
        evidence_manifest=context.evidence_manifest, framework_root=context.framework_root,
        authority=authority, static_signals=args.static_signal,
        requested_skills=args.request_skill, deep_load_skills=args.deep_load_skill,
    )
    if _TEST_TRANSITION_HOOK is not None:
        _TEST_TRANSITION_HOOK("after-checkpoint-acceptance")
    expected_operation = "resume" if context.state["status"] == "blocked" else "accept-checkpoint"
    expected_id = _transition_id(
        expected_operation, _digest_value(context.state), checkpoint, authority
    )
    if transition.state["transitionId"] != expected_id:
        fail("reducer did not derive the deterministic transition identity")
    if _TEST_TRANSITION_HOOK is not None:
        _TEST_TRANSITION_HOOK("before-next-phase-creation")
    phase_input = _phase_input_for(context, transition, checkpoint)
    if _TEST_TRANSITION_HOOK is not None:
        _TEST_TRANSITION_HOOK("after-next-phase-creation")
    return transition, phase_input


def _bundle_manifest(
    context: RunContext, operation: str, checkpoint: dict[str, Any],
    authority: runtime.HostAuthorityContext | None, transition: CheckpointTransition,
    phase_input: dict[str, Any] | None,
) -> dict[str, Any]:
    transition_id = transition.state["transitionId"]
    value = {
        "schemaVersion": TRANSITION_SCHEMA,
        "transitionId": transition_id,
        "operation": operation,
        "operationDigest": _operation_digest(operation, checkpoint, authority),
        "executionId": context.envelope["executionId"],
        "executionVersion": context.envelope["executionVersion"],
        "profileId": context.envelope["profileId"],
        "previousRevision": context.state["revision"],
        "previousTransitionId": context.state["transitionId"],
        "previousStateDigest": _digest_value(context.state),
        "checkpointId": checkpoint["checkpointId"],
        "checkpointDigest": _digest_value(checkpoint),
        "authorityDigest": _authority_digest(authority),
        "nextStateDigest": _digest_value(transition.state),
        "checkpointRef": "checkpoint-v1.json",
        "runStateRef": "run-state-v1.json",
        "phaseInputRef": "phase-input-v1.json" if phase_input is not None else None,
        "authorityRef": "authority-v1.json" if authority is not None else None,
        "effectiveAuthority": transition.effective_authority.as_dict(),
    }
    runtime.validate_structure("transition-bundle", value)
    return value


def _publication_result(
    context: RunContext, bundle: PublishedBundle, *, duplicate: bool, reconciled: bool,
) -> dict[str, Any]:
    phase_ref = None
    if bundle.phase_input is not None:
        phase_ref = f"{_bundle_relative(context, bundle.manifest['transitionId'])}/phase-input-v1.json"
    return {
        "schemaVersion": TRANSITION_RESULT_SCHEMA,
        "executionId": context.envelope["executionId"],
        "transitionId": bundle.manifest["transitionId"],
        "revision": bundle.state["revision"],
        "status": bundle.state["status"],
        "kind": bundle.manifest["operation"],
        "phaseInput": phase_ref,
        "duplicate": duplicate,
        "reconciled": reconciled,
        "providerInvoked": False,
    }


@contextlib.contextmanager
def _head_cas_lock(context: RunContext):
    """Lock one inode-stable run-local CAS mutex through anchored descriptors."""
    nofollow, directory = runtime._require_secure_dir_fd_support()
    root_fd, parent_fds, lock_fd = -1, [], -1
    components = context.run_relative.split("/")
    lock_name = ".transition-head.lock"
    try:
        root_fd = runtime._open_directory(
            context.project_root, dir_fd=None, nofollow=nofollow, directory=directory
        )
        parent_fd, parent_fds = runtime._walk_existing_parent(
            root_fd, components, nofollow, directory
        )
        lock_fd = os.open(lock_name, os.O_RDWR | nofollow, dir_fd=parent_fd)
        metadata = os.fstat(lock_fd)
        identity = runtime._entry_identity(metadata)
        if (not runtime.stat.S_ISREG(metadata.st_mode)
                or not runtime._verify_identity(parent_fd, lock_name, identity)
                or not runtime._same_existing_directory_from_root(
                    root_fd, components, parent_fd, nofollow, directory
                )):
            fail("run-state CAS lock binding is invalid")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if (not runtime._verify_identity(parent_fd, lock_name, identity)
                or not runtime._same_existing_directory_from_root(
                    root_fd, components, parent_fd, nofollow, directory
                )):
            fail("run-state CAS lock binding changed while waiting")
        yield
    except OSError as error:
        fail(f"cannot acquire run-state CAS lock: {error}")
    finally:
        if lock_fd >= 0:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        for opened_fd in reversed(parent_fds):
            os.close(opened_fd)
        if root_fd >= 0:
            os.close(root_fd)


def _reconcile_head_exchange_residue(
    context: RunContext, bundles: dict[str, PublishedBundle], committed: set[str],
) -> bool:
    """Serialize cleanup with HEAD CAS and reject a stale reconciliation view."""
    with _head_cas_lock(context):
        _current, current_bytes = _read_run_object(
            context.project_root,
            f"{context.run_relative}/run-state-v1.json",
            "run-state HEAD",
            max_bytes=runtime.MAX_BYTES["run-state"] or 0,
        )
        if current_bytes != context.state_bytes:
            fail("run-state HEAD changed before residue reconciliation")
        return _reconcile_head_exchange_residue_unlocked(context, bundles, committed)


def _commit_bundle_head(
    context: RunContext, bundle: PublishedBundle, *, duplicate: bool,
) -> dict[str, Any]:
    global _RUN_COMMITTED

    target = f"{context.run_relative}/run-state-v1.json"
    next_bytes = runtime.canonical_bytes(bundle.state) + b"\n"
    if _TEST_TRANSITION_HOOK is not None:
        _TEST_TRANSITION_HOOK("before-head-cas")
    with _head_cas_lock(context):
        current, current_bytes = _read_run_object(
            context.project_root, target, "run-state HEAD",
            max_bytes=runtime.MAX_BYTES["run-state"] or 0,
        )
        if current_bytes == next_bytes:
            validate_state(
                current, context.envelope["executionId"], context.envelope["profileId"],
                context.declaration,
            )
            reconciled = True
        elif current_bytes != context.state_bytes:
            fail("run-state HEAD changed before compare-and-swap")
        else:
            runtime.atomic_write_bytes(
                context.project_root, target, next_bytes,
                expected_current=context.state_bytes,
            )
            reconciled = duplicate
    _RUN_COMMITTED = True
    if _TEST_TRANSITION_HOOK is not None:
        _TEST_TRANSITION_HOOK("after-head-cas")
    return _publication_result(context, bundle, duplicate=duplicate, reconciled=reconciled)


def _publish_bundle(
    context: RunContext, manifest: dict[str, Any], checkpoint: dict[str, Any],
    state: dict[str, Any], phase_input: dict[str, Any] | None,
    authority: runtime.HostAuthorityContext | None,
) -> PublishedBundle:
    parent = f"{context.run_relative}/transitions"
    transition_id = manifest["transitionId"]
    staging = runtime.PrivateStagingDirectory.create(
        context.project_root, parent, transition_id
    )
    published = False
    collision = False
    try:
        records: list[tuple[str, dict[str, Any]]] = [
            ("checkpoint-v1.json", checkpoint),
            ("run-state-v1.json", state),
        ]
        if phase_input is not None:
            records.append(("phase-input-v1.json", phase_input))
        if authority is not None:
            records.append(("authority-v1.json", authority.value))
        records.append(("transition-v1.json", manifest))
        for relative, value in records:
            staging.write_bytes(relative, runtime.canonical_bytes(value) + b"\n")
        for relative, value in records:
            if staging.read_bytes(relative, max_bytes=256 * 1024) != runtime.canonical_bytes(value) + b"\n":
                fail("private transition staging changed before publication")
        if _TEST_TRANSITION_HOOK is not None:
            _TEST_TRANSITION_HOOK("before-bundle-publication")
        try:
            staging.publish_noreplace(transition_id)
        except runtime.ContractError as error:
            if "phase run directory collision" not in str(error):
                raise
            collision = True
        if not collision:
            staging.commit_publication()
            published = True
        if _TEST_TRANSITION_HOOK is not None:
            _TEST_TRANSITION_HOOK(
                "after-bundle-collision" if collision else "after-bundle-publication"
            )
    finally:
        try:
            staging.cleanup()
        finally:
            staging.close()
    if collision:
        existing = _load_published_bundle(context, transition_id)
        if (existing.manifest != manifest or existing.checkpoint != checkpoint
                or existing.state != state or existing.phase_input != phase_input
                or (None if existing.authority is None else existing.authority.value)
                != (None if authority is None else authority.value)):
            fail("deterministic transition ID collided with different immutable content")
        return existing
    if not published:
        fail("transition bundle publication did not complete")
    return _load_published_bundle(context, transition_id)


def _matching_operation(
    bundles: dict[str, PublishedBundle], operation: str, checkpoint_id: str,
    operation_digest: str, *, committed: set[str] | None = None,
) -> PublishedBundle | None:
    candidates = [
        bundle for bundle in bundles.values()
        if bundle.manifest["operation"] == operation
        and bundle.manifest["checkpointId"] == checkpoint_id
    ]
    identical = [
        bundle for bundle in candidates
        if bundle.manifest["operationDigest"] == operation_digest
    ]
    committed_identical = [
        bundle for bundle in identical
        if committed is not None and bundle.manifest["transitionId"] in committed
    ]
    if len(committed_identical) == 1:
        return committed_identical[0]
    if len(committed_identical) > 1:
        fail("identical operation appears more than once in committed history")
    conflicts = [
        bundle for bundle in candidates
        if bundle.manifest["operationDigest"] != operation_digest
    ]
    if conflicts:
        fail("conflicting duplicate transition operation")
    if len(identical) > 1:
        fail("identical operation was published against multiple previous states")
    return identical[0] if identical else None


def _handle_existing_operation(
    context: RunContext, bundle: PublishedBundle,
    bundles: dict[str, PublishedBundle], args: argparse.Namespace,
) -> dict[str, Any]:
    committed = _committed_transition_ids(context, bundles, args)
    transition_id = bundle.manifest["transitionId"]
    if transition_id in committed:
        return _publication_result(context, bundle, duplicate=True, reconciled=False)
    if bundle.manifest["previousStateDigest"] == _digest_value(context.state):
        return _commit_bundle_head(context, bundle, duplicate=True)
    fail("identical published operation is stale against the committed HEAD")


def _load_authority_argument(path: str | None) -> runtime.HostAuthorityContext | None:
    if path is None:
        return None
    return runtime.load_host_authority(runtime.safe_read_json(Path(path)))


def accept_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    context = _load_run_context(args)
    checkpoint = runtime.safe_read_json(Path(args.checkpoint))
    runtime.validate_model("phase-checkpoint", checkpoint)
    operation = "accept-checkpoint"
    operation_digest = _operation_digest(operation, checkpoint, None)
    bundles = _published_bundles(context)
    committed = _committed_transition_ids(context, bundles, args)
    _reconcile_head_exchange_residue(context, bundles, committed)
    existing = _matching_operation(
        bundles, operation, checkpoint["checkpointId"], operation_digest,
        committed=committed,
    )
    if existing is not None:
        return _handle_existing_operation(context, existing, bundles, args)
    transition, phase_input = _reduce_durable_operation(
        context, operation, checkpoint, None, args
    )
    manifest = _bundle_manifest(
        context, operation, checkpoint, None, transition, phase_input
    )
    bundle = _publish_bundle(
        context, manifest, checkpoint, transition.state, phase_input, None
    )
    return _commit_bundle_head(context, bundle, duplicate=False)


def resume(args: argparse.Namespace) -> dict[str, Any]:
    context = _load_run_context(args)
    bundles = _published_bundles(context)
    committed = _committed_transition_ids(context, bundles, args)
    _reconcile_head_exchange_residue(context, bundles, committed)
    authority = _load_authority_argument(args.authority)
    assert authority is not None
    operation = "resume"
    if context.state["status"] != "blocked" or context.state["transitionId"] is None:
        # A retry after the resume CAS observes the resulting active/completed
        # HEAD. Resolve the exact committed operation from the immutable chain.
        retry_candidates = [
            bundle for transition_id, bundle in bundles.items()
            if transition_id in committed
            and bundle.manifest["operation"] == operation
            and bundle.manifest["authorityDigest"] == _authority_digest(authority)
            and bundle.manifest["operationDigest"] == _operation_digest(
                operation, bundle.checkpoint, authority
            )
        ]
        if len(retry_candidates) == 1:
            return _publication_result(
                context, retry_candidates[0], duplicate=True, reconciled=False
            )
        if len(retry_candidates) > 1:
            fail("resume retry is ambiguous across committed transition history")
        if context.state["transitionId"] is not None:
            latest = bundles[context.state["transitionId"]]
            if latest.manifest["operation"] == operation:
                _matching_operation(
                    bundles, operation, latest.checkpoint["checkpointId"],
                    _operation_digest(operation, latest.checkpoint, authority),
                )
        fail("resume requires an authoritative blocked HEAD")
    if context.state["transitionId"] not in committed:
        fail("blocked HEAD does not reference an authoritative checkpoint bundle")
    checkpoint = bundles[context.state["transitionId"]].checkpoint
    operation_digest = _operation_digest(operation, checkpoint, authority)
    existing = _matching_operation(
        bundles, operation, checkpoint["checkpointId"], operation_digest,
        committed=committed,
    )
    if existing is not None:
        return _handle_existing_operation(context, existing, bundles, args)
    transition, phase_input = _reduce_durable_operation(
        context, operation, checkpoint, authority, args
    )
    manifest = _bundle_manifest(
        context, operation, checkpoint, authority, transition, phase_input
    )
    bundle = _publish_bundle(
        context, manifest, checkpoint, transition.state, phase_input, authority
    )
    return _commit_bundle_head(context, bundle, duplicate=False)


def reconcile(args: argparse.Namespace) -> dict[str, Any]:
    context = _load_run_context(args)
    bundles = _published_bundles(context)
    committed = _committed_transition_ids(context, bundles, args)
    cleaned_head_residue = _reconcile_head_exchange_residue(context, bundles, committed)
    eligible = [
        bundle for transition_id, bundle in bundles.items()
        if transition_id not in committed
        and bundle.manifest["previousStateDigest"] == _digest_value(context.state)
        and bundle.manifest["previousTransitionId"] == context.state["transitionId"]
    ]
    if not eligible:
        return {
            "schemaVersion": TRANSITION_RESULT_SCHEMA,
            "executionId": context.envelope["executionId"],
            "transitionId": context.state["transitionId"],
            "revision": context.state["revision"],
            "status": context.state["status"],
            "kind": "reconcile",
            "phaseInput": None,
            "duplicate": True,
            "reconciled": cleaned_head_residue,
            "providerInvoked": False,
        }
    winner = min(eligible, key=lambda item: item.manifest["transitionId"])
    transition, phase_input = _reduce_durable_operation(
        context, winner.manifest["operation"], winner.checkpoint, winner.authority, args
    )
    expected_manifest = _bundle_manifest(
        context, winner.manifest["operation"], winner.checkpoint, winner.authority,
        transition, phase_input,
    )
    if (expected_manifest != winner.manifest or transition.state != winner.state
            or phase_input != winner.phase_input):
        fail("published transition bundle does not reproduce from authoritative HEAD")
    return _commit_bundle_head(context, winner, duplicate=True)


def prepare_phase(args: argparse.Namespace) -> dict[str, Any]:
    """Resolve one provider packet exclusively through authoritative HEAD.

    This is the CTX-06C read boundary.  It deliberately returns canonical
    objects rather than caller-reopenable paths, so a provider prompt cannot
    select a crash-visible or losing transition bundle through directory
    discovery.
    """
    context = _load_run_context(args)
    runtime.authoritative_validate_context_manifest(
        context.context_manifest, context.framework_root,
        context.envelope["profileId"], context.envelope["executionId"],
        static_signals=args.static_signal,
        requested_skills=args.request_skill,
        deep_load_skills=args.deep_load_skill,
    )
    bundles = _published_bundles(context)
    committed = _committed_transition_ids(context, bundles, args)
    _reconcile_head_exchange_residue(context, bundles, committed)

    phase = None
    phase_input = None
    previous_checkpoint = None
    if context.state["status"] == "active":
        declared = _phase_by_id(context.declaration, context.state["currentPhaseId"])
        phase = declared.as_dict()
        if context.state["transitionId"] is None:
            phase_input, _ = _read_run_object(
                context.project_root,
                f"{context.run_relative}/phases/{declared.ordinal:03d}-{declared.identity}/phase-input-v1.json",
                "initial phase input",
                max_bytes=runtime.MAX_BYTES["phase-input"] or 0,
            )
            runtime.validate_model("phase-input", phase_input)
        else:
            transition_id = context.state["transitionId"]
            if transition_id not in committed:
                fail("active HEAD does not name an authoritative transition")
            bundle = bundles[transition_id]
            if bundle.phase_input is None:
                fail("active HEAD transition omits its authoritative phase input")
            phase_input = bundle.phase_input
            previous_checkpoint = bundle.checkpoint
        if (
            phase_input["executionId"] != context.envelope["executionId"]
            or phase_input["phaseId"] != declared.identity
        ):
            fail("authoritative phase input does not match active HEAD")

    return {
        "schemaVersion": PHASE_EXECUTION_PACKET_SCHEMA,
        "executionId": context.envelope["executionId"],
        "profileId": context.envelope["profileId"],
        "provider": context.run_directory["provider"],
        "runStatus": context.state["status"],
        "revision": context.state["revision"],
        "currentAttempt": context.state["currentAttempt"],
        "phase": phase,
        "executionEnvelope": context.envelope,
        "contextManifest": context.context_manifest,
        "phaseInput": phase_input,
        "previousCheckpoint": previous_checkpoint,
        "providerInvoked": False,
    }


def _materialize(staging: Any,
                 records: list[tuple[str, dict[str, Any], str]],
                 declaration: PipelineDeclaration) -> None:
    total = len(records)
    for index, (relative, value, _) in enumerate(records, start=1):
        if _TEST_MATERIALIZE_HOOK is not None:
            _TEST_MATERIALIZE_HOOK(index, total)
        staging.write_bytes(relative, runtime.canonical_bytes(value) + b"\n")
    for relative, expected, kind in records:
        payload = staging.read_bytes(relative, max_bytes=256 * 1024)
        if payload != runtime.canonical_bytes(expected) + b"\n":
            fail(f"staged materialization changed canonical bytes: {relative}")
        actual = json.loads(payload)
        if kind == "execution-envelope":
            runtime.validate_structure(kind, actual)
        elif kind in {"context-manifest", "phase-input"}:
            runtime.validate_model(kind, actual)
        elif kind == "run-directory":
            validate_run_directory(actual, declaration)
        elif kind == "run-state":
            validate_state(actual, expected["executionId"], expected["profileId"], declaration)


def initialize(args: argparse.Namespace) -> dict[str, Any]:
    global _RUN_COMMITTED

    project_root, framework_root = safe_absolute(args.project_root), safe_absolute(args.framework_root)
    runtime.validate_secure_root(project_root)
    runtime.validate_secure_root(framework_root)
    validate_objective(args.objective)
    declaration = load_declaration(framework_root, args.profile)
    workspace_id = validate_workspace(
        project_root, args.workspace, declaration.workspace_kind
    )
    target = build_target(args, declaration.target_kind)
    manifest = runtime.compile_context_manifest(
        framework_root, args.profile, args.execution_id,
        static_signals=args.static_signal, requested_skills=args.request_skill,
        deep_load_skills=args.deep_load_skill)
    if manifest["profileId"] != args.profile or manifest["executionId"] != args.execution_id:
        fail("compiled manifest identity mismatch")
    initial_phase = declaration.phases[0]
    evidence_refs, evidence_manifest_path = load_evidence_refs(
        project_root, args.execution_id, args.evidence_manifest, args.evidence_ref,
        initial_phase, workspace_id)
    envelope = {
        "schemaVersion": "mana.context-runtime.execution-envelope/v1",
        "executionId": args.execution_id, "executionVersion": 1,
        "profileId": args.profile, "projectRoot": ".",
        "workspace": args.workspace, "workspaceId": workspace_id, "target": target,
        "permissions": {"repositoryWrite": False, "externalWrite": False,
                        "approvedExternalActions": []},
        "humanGates": list(declaration.human_gates), "provider": args.provider,
        "runtimeMode": "context-v2",
    }
    runtime.validate_structure("execution-envelope", envelope)
    run_directory = {
        "schemaVersion": RUN_SCHEMA, "executionId": args.execution_id,
        "profileId": args.profile, "provider": args.provider,
        "phaseOrder": [phase.identity for phase in declaration.phases],
        "pipeline": [phase.as_dict() for phase in declaration.phases],
        "initialPhaseId": initial_phase.identity, "executionEnvelopeRef": "G-001",
        "contextManifestRef": "M-001", "workspace": args.workspace,
        "workspaceId": workspace_id,
        "evidenceManifestPath": evidence_manifest_path,
    }
    validate_run_directory(run_directory, declaration)
    phase_input = {
        "schemaVersion": "mana.context-runtime.phase-input/v1",
        "executionId": args.execution_id, "phaseId": initial_phase.identity,
        "executionEnvelopeRef": "G-001", "contextManifestRef": "M-001",
        "objective": args.objective, "checkpointRef": None, "evidenceRefs": evidence_refs,
    }
    runtime.validate_model("phase-input", phase_input)
    run_state = _state_value(
        args.execution_id, args.profile, declaration, current_phase=initial_phase.identity
    )
    validate_state(run_state, args.execution_id, args.profile, declaration)

    run_relative, runs_parent = relative_run_directory(args.execution_id), ".mana/runtime/runs"
    staging = runtime.PrivateStagingDirectory.create(
        project_root, runs_parent, args.execution_id)
    phase_relative = f"phases/{initial_phase.ordinal:03d}-{initial_phase.identity}"
    records = [
        ("execution-envelope-v1.json", envelope, "execution-envelope"),
        ("context-manifest-v1.json", manifest, "context-manifest"),
        ("run-directory-v1.json", run_directory, "run-directory"),
        (f"{phase_relative}/phase-input-v1.json", phase_input, "phase-input"),
        ("run-state-v1.json", run_state, "run-state"),
    ]
    try:
        staging.write_bytes(".transition-head.lock", b"")
        if staging.read_bytes(".transition-head.lock", max_bytes=1) != b"":
            fail("private run-state CAS lock materialization changed")
        staging.ensure_directory("transitions")
        staging.ensure_directory(phase_relative)
        _materialize(staging, records, declaration)
        with PublicationSignalGuard() as signal_guard:
            if _TEST_PUBLICATION_HOOK is not None:
                _TEST_PUBLICATION_HOOK("before-publication")
            signal_guard.abort_if_observed()
            staging.publish_noreplace(args.execution_id)
            if _TEST_PUBLICATION_HOOK is not None:
                _TEST_PUBLICATION_HOOK("after-publication")
            signal_guard.commit(staging)
            _RUN_COMMITTED = True
            if _TEST_PUBLICATION_HOOK is not None:
                _TEST_PUBLICATION_HOOK("after-commit-barrier")
        if _TEST_PUBLICATION_HOOK is not None:
            _TEST_PUBLICATION_HOOK("after-publication-guard")
    finally:
        try:
            staging.cleanup()
        finally:
            staging.close()
    return {"schemaVersion": RUN_SCHEMA, "executionId": args.execution_id,
            "runDirectory": run_relative,
            "phaseInputs": [f"{run_relative}/{phase_relative}/phase-input-v1.json"],
            "providerInvoked": False}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Initialize, transition, and prepare a Context Runtime v2 run without invoking a provider.")
    subcommands = result.add_subparsers(dest="command", required=True)
    init = subcommands.add_parser("initialize")
    init.add_argument("profile")
    init.add_argument("--project-root", required=True)
    init.add_argument("--execution-id", required=True)
    init.add_argument("--provider", choices=("codex", "claude", "opencode"), required=True)
    init.add_argument("--workspace", required=True)
    init.add_argument("--objective", required=True)
    init.add_argument("--target-repository")
    init.add_argument("--target-base")
    init.add_argument("--target-pr-number", type=int)
    init.add_argument("--evidence-manifest")
    init.add_argument("--evidence-ref", action="append", default=[])
    init.add_argument("--static-signal", action="append", default=[])
    init.add_argument("--request-skill", action="append", default=[])
    init.add_argument("--deep-load-skill", action="append", default=[])
    init.add_argument("--framework-root", default=str(HERE.parent.parent))
    init.set_defaults(handler=initialize)

    def transition_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("execution_id")
        command.add_argument("--project-root", required=True)
        command.add_argument("--static-signal", action="append", default=[])
        command.add_argument("--request-skill", action="append", default=[])
        command.add_argument("--deep-load-skill", action="append", default=[])
        command.add_argument("--framework-root", default=str(HERE.parent.parent))

    accept = subcommands.add_parser("accept-checkpoint")
    transition_arguments(accept)
    accept.add_argument("--checkpoint", required=True)
    accept.set_defaults(handler=accept_checkpoint)
    resume_command = subcommands.add_parser("resume")
    transition_arguments(resume_command)
    resume_command.add_argument("--authority", required=True)
    resume_command.set_defaults(handler=resume)
    reconcile_command = subcommands.add_parser("reconcile")
    transition_arguments(reconcile_command)
    reconcile_command.set_defaults(handler=reconcile)
    prepare_command = subcommands.add_parser("prepare-phase")
    transition_arguments(prepare_command)
    prepare_command.set_defaults(handler=prepare_phase)
    return result


def main(argv: list[str]) -> int:
    global _RUN_COMMITTED

    _RUN_COMMITTED = False
    previous_handlers: dict[int, Any] = {}

    def interrupt(signum: int, _frame: Any) -> None:
        raise PipelineSignal(signum, committed=_RUN_COMMITTED)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, interrupt)
    try:
        args = parser().parse_args(argv[1:])
        result = args.handler(args)
        sys.stdout.buffer.write(runtime.canonical_bytes(result) + b"\n")
        return 0
    except PipelineSignal as error:
        if error.committed:
            print(
                f"ERROR: interrupted by signal {error.signum} after commit; "
                "run remains committed",
                file=sys.stderr,
            )
        else:
            print(f"ERROR: interrupted by signal {error.signum} before commit; run aborted",
                  file=sys.stderr)
        return 128 + error.signum
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr)
        return 130
    except runtime.RollbackFailure as error:
        print(json.dumps({"error": error.as_dict()}, sort_keys=True), file=sys.stderr)
        return 1
    except (runtime.ContractError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
