#!/usr/bin/env python3
"""Explicit legacy/v2 consumers of the canonical host packet.

Shadow uses fresh CTX-06 provider packets and the unchanged pure reducer. Its
state and checkpoints use CTX-06 committed HEAD; comparison is non-authoritative.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import tempfile
import copy
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ctx09c_consumer_input", HERE / "context-shadow-input.py")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
pipeline = shared.load("ctx09c_consumer_pipeline", "context-pipeline.py")
phase = shared.load("ctx09c_consumer_phase", "context-phase-runtime.py")
privacy = shared.load("ctx09c_consumer_privacy", "context-shadow-privacy.py")


def capabilities(provider):
    completed = subprocess.run([str(HERE.parent / "mana-provider-capabilities.sh"), provider],
                               capture_output=True, env={**os.environ, "MANA_UPDATE_CHECK": "off"})
    if completed.returncode:
        raise shared.Error("shadow capability probe failed")
    report = shared.decode(completed.stdout)
    phase.runtime.validate_structure("provider-capabilities", report)
    if report["provider"] != provider:
        raise shared.Error("shadow capability identity mismatch")
    if any(report["capabilities"][key]["status"] != "supported" for key in
           ("freshInvocation", "ephemeralSession", "explicitModelSelection", "hardSubagentDisable")):
        raise shared.Error("shadow provider capability gap")
    return report


def snapshot(profile, framework_root=None):
    declaration = pipeline.load_declaration(framework_root or HERE.parent.parent, profile)
    return {"workspaceKind": declaration.workspace_kind, "targetKind": declaration.target_kind,
            "humanGates": list(declaration.human_gates),
            "phases": [item.as_dict() for item in declaration.phases]}


def declaration_from_snapshot(profile, value):
    if not isinstance(value, dict) or set(value) != {"workspaceKind", "targetKind", "humanGates", "phases"}:
        raise shared.Error("invalid host pipeline snapshot")
    if value["workspaceKind"] not in {"feature", "session", "either"} or value["targetKind"] not in {"none", "repository", "pull_request"}:
        raise shared.Error("invalid host pipeline policy")
    phases = []
    for ordinal, record in enumerate(value["phases"], 1):
        policy = record["policy"]
        if (set(record) != {"id", "ordinal", "policy"} or record["ordinal"] != ordinal
                or set(policy) != {"modelTier", "outputSchema", "subagents", "evidenceKinds", "evidenceStatuses", "retryLimit"}
                or policy["modelTier"] not in {"economy", "full", "host"}
                or policy["outputSchema"] != "phase-checkpoint-v1"
                or policy["subagents"] not in {"forbidden", "optional"}
                or type(policy["retryLimit"]) is not int or not 0 <= policy["retryLimit"] <= 16):
            raise shared.Error("invalid host phase snapshot")
        phases.append(pipeline.PhasePolicy(record["id"], ordinal, policy["modelTier"], policy["outputSchema"],
            policy["subagents"], tuple(policy["evidenceKinds"]), tuple(policy["evidenceStatuses"]), policy["retryLimit"]))
    if not phases or len(phases) > 128 or len({phase.identity for phase in phases}) != len(phases):
        raise shared.Error("invalid host phase order")
    return pipeline.PipelineDeclaration(profile, value["workspaceKind"], value["targetKind"], tuple(value["humanGates"]), tuple(phases))


def invoke(provider, project, profile, execution, prompt, argv):
    return subprocess.run(["bash", str(HERE / "context-shadow-provider.sh"), provider, str(project), profile,
                           execution, *argv], input=prompt, capture_output=True)


def run_args(project, framework, execution, inputs):
    return argparse.Namespace(project_root=str(project), framework_root=str(framework), execution_id=execution,
        static_signal=inputs.get("staticSignals", []), request_skill=inputs.get("requestedSkills", []),
        deep_load_skill=inputs.get("deepLoadSkills", []))


def commit_initial(project, framework, declaration, envelope, manifest, inputs, evidence_manifest):
    """Materialize the captured packet, without recompiling or resuming legacy."""
    if snapshot(declaration.profile_id, framework) != inputs["pipelineSnapshot"]:
        raise shared.Error("host pipeline snapshot differs from installed declaration")
    execution = envelope["executionId"]
    first = declaration.phases[0]
    run = {"schemaVersion": pipeline.RUN_SCHEMA, "executionId": execution,
        "profileId": envelope["profileId"], "provider": envelope["provider"],
        "phaseOrder": [item.identity for item in declaration.phases],
        "pipeline": [item.as_dict() for item in declaration.phases], "initialPhaseId": first.identity,
        "executionEnvelopeRef": "G-001", "contextManifestRef": "M-001",
        "workspace": envelope["workspace"], "workspaceId": envelope["workspaceId"],
        "evidenceManifestPath": f".mana/runtime-evidence/executions/{execution}/manifest.json"}
    initial_input = {"schemaVersion": "mana.context-runtime.phase-input/v1", "executionId": execution,
        "phaseId": first.identity, "executionEnvelopeRef": "G-001", "contextManifestRef": "M-001",
        "objective": inputs["objective"], "checkpointRef": None, "evidenceRefs": []}
    state = pipeline._state_value(execution, envelope["profileId"], declaration, current_phase=first.identity)
    evidence_path = run["evidenceManifestPath"]
    shared.runtime.atomic_write_bytes(project, evidence_path, shared.canonical(evidence_manifest), immutable=True)
    staging = shared.runtime.PrivateStagingDirectory.create(project, ".mana/runtime/runs", execution)
    phase_ref = f"phases/{first.ordinal:03d}-{first.identity}"
    try:
        staging.write_bytes(".transition-head.lock", b"")
        staging.ensure_directory("transitions")
        staging.ensure_directory(phase_ref)
        pipeline._materialize(staging, [("execution-envelope-v1.json", envelope, "execution-envelope"),
            ("context-manifest-v1.json", manifest, "context-manifest"),
            ("run-directory-v1.json", run, "run-directory"),
            (phase_ref + "/phase-input-v1.json", initial_input, "phase-input"),
            ("run-state-v1.json", state, "run-state")], declaration)
        staging.publish_noreplace(execution)
        staging.commit_publication()
    finally:
        staging.cleanup()
        staging.close()


def project_completed(project, framework, packet, inputs):
    """Read only HEAD's chain; replay host transitions before projecting observations.

    CTX-06 prose has no typed predicate/severity/coverage. It is recorded as
    unprojected provenance, never interpreted into a CTX-09B semantic fact.
    Optional typed observations are digest-bound inside the committed checkpoint.
    """
    args = run_args(project, framework, packet["identity"]["shadowProducerId"], inputs)
    context = pipeline._load_run_context(args)
    if (context.state["status"] != "completed" or context.envelope["executionVersion"] != packet["executionVersion"]
            or context.envelope["profileId"] != packet["profileId"]
            or context.envelope["executionId"] != packet["shadowExecutionId"]
            or context.envelope["workspace"] != packet["workspace"]
            or context.envelope["workspaceId"] != packet["workspaceId"]
            or context.run_directory["executionId"] != packet["shadowExecutionId"]
            or context.run_directory["workspaceId"] != packet["workspaceId"]
            or context.context_manifest != {**packet["contextManifest"], "executionId": packet["shadowExecutionId"]}
            or context.evidence_manifest is None
            or context.evidence_manifest["executionId"] != packet["shadowExecutionId"]
            or context.evidence_manifest["workspaceId"] != packet["workspaceId"]
            or snapshot(packet["profileId"], framework) != inputs["pipelineSnapshot"]):
        raise shared.Error("comparison requires a completed matching v2 execution")
    bundles = {}
    transition = context.state["transitionId"]
    while transition is not None:
        if transition in bundles:
            raise shared.Error("cyclic comparison chain")
        bundle = pipeline._load_published_bundle(context, transition)
        bundles[transition] = bundle
        transition = bundle.manifest["previousTransitionId"]
    pipeline._committed_transition_ids(context, bundles, args)
    final = bundles[context.state["transitionId"]].checkpoint
    target_key = shared.digest(shared.canonical(packet["target"]))
    comparison = shared.load("ctx09c_projection_comparison", "context-comparison.py")
    projection = final.get("comparisonProjection")
    if projection is None:
        projection = {"schemaVersion": comparison.INPUT_VERSION, "profileId": packet["profileId"],
                      "targetKey": target_key, "dimensions": {}}
    projection = shared.decode(shared.canonical(projection))
    if projection["profileId"] != packet["profileId"] or projection["targetKey"] != target_key:
        raise shared.Error("foreign committed comparison observations")
    dimensions = projection["dimensions"]
    # Earlier declared uncertainty remains visible even if a final handoff
    # omits it. A complete final collection cannot silently erase an atom.
    for bundle in sorted(bundles.values(), key=lambda item: item.state["revision"]):
        earlier = bundle.checkpoint.get("comparisonProjection")
        if earlier is None or bundle.checkpoint is final:
            continue
        if earlier["profileId"] != packet["profileId"] or earlier["targetKey"] != target_key:
            raise shared.Error("foreign committed comparison observations")
        comparison.native_input(shared.canonical(earlier), comparison.Contracts())
        for name, source in earlier["dimensions"].items():
            if name not in dimensions:
                dimensions[name] = shared.decode(shared.canonical(source))
                continue
            dest = dimensions[name]
            dest["gaps"] = sorted(set(dest["gaps"] + source["gaps"]))
            if source["coverage"] in {"partial", "unavailable"} and dest["coverage"] in {"complete", "not-applicable"}:
                dest["coverage"] = "partial"
            for record in source["records"]:
                match = next((item for item in dest["records"]
                    if comparison.semantic_key(name, item) == comparison.semantic_key(name, record)), None)
                if match is None:
                    dest["records"].append(shared.decode(shared.canonical(record)))
                    dest["coverage"] = "partial"
                    dest["gaps"] = sorted(set(dest["gaps"] + ["scope-incomplete"]))
                else:
                    match["uncertainty"] = sorted(set(match["uncertainty"] + record["uncertainty"]))
                    if match["value"] != record["value"] or match["evidenceRefs"] != record["evidenceRefs"]:
                        dest["gaps"] = sorted(set(dest["gaps"] + ["contradictory-evidence"]))
    unprojected = []
    validated_bytes = {
        "run-state-v1.json": context.state_bytes,
        "execution-envelope-v1.json": shared.canonical(context.envelope),
        "context-manifest-v1.json": shared.canonical(context.context_manifest),
        "run-directory-v1.json": shared.canonical(context.run_directory),
        context.run_directory["evidenceManifestPath"]: shared.canonical(context.evidence_manifest),
        context.envelope["workspace"] + "/manifest.yaml": shared.unblob(packet["workspaceManifest"]),
    }
    for identity, bundle in bundles.items():
        for name, value in (("transition-v1.json", bundle.manifest),
                            ("checkpoint-v1.json", bundle.checkpoint),
                            ("run-state-v1.json", bundle.state)):
            validated_bytes[f"transitions/{identity}/{name}"] = shared.canonical(value)
    merge_gaps = set()
    for identity, bundle in bundles.items():
        committed_ref = bundle.checkpoint.get("comparisonMergeRef")
        if committed_ref is None:
            continue
        declared = pipeline._phase_by_id(context.declaration, bundle.checkpoint["phaseId"])
        expected_ref = f"phases/{declared.ordinal:03d}-{declared.identity}/delegation-merge-v1.json"
        if committed_ref["ref"] != expected_ref:
            raise shared.Error("comparison merge is not bound to checkpoint phase")
        data = shared.runtime.safe_read_bytes(Path(context.run_relative + "/" + expected_ref),
            project_root=project, max_bytes=shared.runtime.MAX_BYTES["delegation-merge"])
        if shared.digest(data) != committed_ref["sha256"]:
            raise shared.Error("committed comparison merge digest mismatch")
        merge = shared.decode(data)
        if data != shared.canonical(merge):
            raise shared.Error("comparison merge is not canonical")
        shared.runtime.validate_structure("delegation-merge", merge)
        previous_id = bundle.manifest["previousTransitionId"]
        attempt = bundles[previous_id].state["currentAttempt"] if previous_id else 1
        if (merge["executionId"], merge["executionVersion"], merge["workspaceId"], merge["profileId"],
            merge["phaseId"], merge["attempt"]) != (args.execution_id, context.envelope["executionVersion"],
            context.envelope["workspaceId"], packet["profileId"], declared.identity, attempt):
            raise shared.Error("foreign committed comparison merge")
        validated_bytes[expected_ref] = data
        # CTX-07A has stance/predicate/provenance, but no finding validation or
        # requirement coverage. Retain exact artifact refs; do not invent those.
        for field in ("verifiedFacts", "findings", "assumptions", "inferences", "openQuestions", "evidenceGaps",
                      "evidenceRefs", "artifactRefs", "uncertainty", "missingTaskIds", "conflicts"):
            if merge[field]: unprojected.append(expected_ref + "/" + field)
        if merge["mergeStatus"] != "complete": merge_gaps.add("scope-incomplete")
        if merge["conflicts"]: merge_gaps.add("contradictory-evidence")
        if merge["evidenceGaps"]: merge_gaps.add("missing-evidence")
        if any(item["level"] != "none" for item in merge["uncertainty"]): merge_gaps.add("unverified")
    for identity, bundle in bundles.items():
        for field in ("verifiedFacts", "assumptions", "inferences", "openQuestions", "closedHypotheses", "candidateFindings"):
            if bundle.checkpoint[field]:
                unprojected.append(f"transitions/{identity}/checkpoint-v1.json/{field}")
    # No complete collection assertion can erase untyped observations.
    affected = set()
    if any(ref.endswith(("candidateFindings", "findings", "verifiedFacts", "inferences", "closedHypotheses")) for ref in unprojected):
        affected.update(("blockers", "warnings", "evidenceReferences"))
    if any(ref.endswith("openQuestions") for ref in unprojected): affected.add("unresolvedQuestions")
    if any(ref.endswith("assumptions") for ref in unprojected): affected.update(comparison.DIMENSIONS)
    if merge_gaps: affected.update(comparison.DIMENSIONS)
    for name in comparison.DIMENSIONS:
        dimensions.setdefault(name, {"coverage": "unavailable", "records": [], "gaps": ["scope-incomplete"]})
        if name in affected:
            section = dimensions[name]
            if section["coverage"] in {"complete", "not-applicable"}: section["coverage"] = "partial"
            section["gaps"] = sorted(set(section["gaps"] + ["unverified"] + list(merge_gaps)))
    # Policy is a host-owned observation, never a permission grant.
    host_policy = {"repositoryWrite": False, "externalWrite": False, "approvedActionKeys": []}
    declared_policy = dimensions["externalWritePolicy"]
    if declared_policy["records"]:
        if any(record["value"] != host_policy for record in declared_policy["records"]):
            raise shared.Error("committed comparison policy conflicts with host envelope")
    else:
        dimensions["externalWritePolicy"] = {"coverage": "complete", "records": [{"key": "externalWritePolicy",
            "value": host_policy, "evidenceRefs": [], "uncertainty": []}], "gaps": declared_policy["gaps"]
            if declared_policy["coverage"] != "unavailable" else []}
    if dimensions["artifactCompleteness"]["coverage"] == "unavailable":
        dimensions["artifactCompleteness"] = {"coverage": "partial", "gaps": ["scope-incomplete"], "records": [
            {"key": final["checkpointId"], "value": {"state": "present", "schemaVersion": final["schemaVersion"],
             "mediaType": "json"}, "evidenceRefs": [], "uncertainty": []}]}
    for gate in context.envelope["humanGates"]:
        section = dimensions["approvalGates"]
        for record in section["records"]:
            if record["key"] == gate:
                # Host authority is the only source of gate completion. The
                # shadow consumer does not read or grant human approvals.
                if record["value"]["state"] == "completed":
                    record["uncertainty"] = sorted(set(record["uncertainty"] + ["unverified"]))
        if not any(record["key"] == gate for record in section["records"]):
            if section["coverage"] == "unavailable": section["coverage"] = "partial"
            section["records"].append({"key": gate, "value": {"requirement": "mandatory", "state": "unknown"},
                                       "evidenceRefs": [], "uncertainty": ["unverified"]})
    artifacts = []
    for ref in sorted(validated_bytes):
        relative = ref if ref.startswith(".mana/") else context.run_relative + "/" + ref
        data = shared.runtime.safe_read_bytes(Path(relative), project_root=project, max_bytes=1024*1024)
        if data != validated_bytes[ref]:
            raise shared.Error("committed comparison artifact changed during projection")
        artifacts.append({"ref": ref, "sha256": shared.digest(data)})
    projection["provenance"] = {"authority": "none", "executionId": args.execution_id, "executionVersion": 1,
        "headDigest": shared.digest(context.state_bytes), "artifacts": artifacts, "unprojected": sorted(unprojected)}
    comparison.native_input(shared.canonical(projection), comparison.Contracts())
    privacy.validate(projection)
    # Reject a concurrently replaced HEAD; projection never commits v2 state.
    if shared.runtime.safe_read_bytes(Path(context.run_relative + "/run-state-v1.json"), project_root=project,
                                     max_bytes=1024*1024) != context.state_bytes:
        raise shared.Error("comparison HEAD changed")
    return projection


def consume(payload, role, project, *, framework_root=None):
    framework = framework_root or HERE.parent.parent
    packet = shared.validate(payload)
    inputs = shared.decode(shared.unblob(packet["input"]))
    provider = packet["policyDecision"]["provider"]
    profile = packet["profileId"]
    identity = packet["identity"]
    producer = identity["legacyProducerId"] if role == "legacy" else identity["shadowProducerId"]
    expected_execution = packet["legacyExecutionId"] if role == "legacy" else packet["shadowExecutionId"]
    if producer != expected_execution or packet["comparisonExecutionId"] != identity["comparisonExecutionId"]:
        raise shared.Error("foreign packet producer identity")
    consumption = {**shared.metadata(payload), "producerId": producer,
                   "invocationId": identity["legacyInvocationId"] if role == "legacy" else identity["shadowInvocationId"]}
    try:
        shared.runtime.atomic_write_bytes(project, f".mana/runtime/metrics/{producer}/shared-input-consumption-v1.json",
                                         shared.canonical(consumption), immutable=True)
    except (shared.Error, OSError):
        # A metadata collision cannot replace legacy execution authority.
        pass
    if role == "legacy":
        prompt = inputs["legacyPrompt"].encode()
        if packet["evidenceSnapshot"]:
            prompt += b"\nAuthorized evidence snapshot:\n" + shared.canonical(packet["evidenceSnapshot"])
        completed = invoke(provider, project, profile, identity["legacyProducerId"],
                           prompt, inputs["legacyArgv"])
        return completed.returncode, completed.stdout, completed.stderr
    declaration = declaration_from_snapshot(profile, inputs["pipelineSnapshot"])
    report = capabilities(provider)
    execution = identity["shadowProducerId"]
    # The manifest and mode decision are deterministic identity projections of
    # the common packet, never a independently initialized or resumed run.
    manifest = {**packet["contextManifest"], "executionId": execution}
    workspace = packet["workspace"]
    shared.runtime.atomic_write_bytes(project, workspace + "/manifest.yaml",
                                      shared.unblob(packet["workspaceManifest"]), immutable=True)
    if shared.runtime.derive_workspace_id(project, workspace) != packet["workspaceId"]:
        raise shared.Error("shadow workspace manifest binding mismatch")
    evidence_manifest = copy.deepcopy(packet["evidenceManifest"])
    evidence_manifest["executionId"] = execution
    rebound = []
    for item in evidence_manifest["items"]:
        item["evidenceId"] = shared.runtime.evidence_record_id(execution, packet["workspaceId"], item)
        rebound.append(item["evidenceId"])
    shared.runtime.validate_model("evidence-manifest", evidence_manifest)
    target = {key: packet["target"].get(key) for key in ("repository", "base", "prNumber")}
    if declaration.target_kind == "none":
        target = dict.fromkeys(target)
    envelope = {"schemaVersion": "mana.context-runtime.execution-envelope/v1",
                "executionId": execution, "executionVersion": packet["executionVersion"], "profileId": profile,
                "projectRoot": ".", "workspace": workspace, "workspaceId": packet["workspaceId"],
                "target": target,
                "permissions": {"repositoryWrite": False, "externalWrite": False, "approvedExternalActions": []},
                "humanGates": list(declaration.human_gates), "provider": provider, "runtimeMode": "context-v2"}
    state = pipeline._state_value(execution, profile, declaration, current_phase=declaration.phases[0].identity)
    commit_initial(project, framework, declaration, envelope, manifest, inputs, evidence_manifest)
    durable_args = run_args(project, framework, execution, inputs)
    previous = None
    resolution = shared.budget.resolve_policy(packet["policyDecision"]["policySnapshot"], profile,
                                              packet["policyDecision"]["effectiveMode"])
    resolution["decision"] = {**{key: value for key, value in packet["policyDecision"].items() if key != "policySnapshot"},
                              "executionId": execution}
    with tempfile.TemporaryDirectory(prefix="mana-shadow-controls-", dir=os.environ.get("TMPDIR")) as temporary:
        capability_path = Path(temporary).resolve() / "capabilities.json"
        capability_path.write_bytes(shared.canonical(report))
        capability_path.chmod(0o600)
        plan = shared.budget.capability_plan(resolution, str(capability_path))
    control = plan["controls"]["automaticCompactionThreshold"]
    threshold = str(control["requested"]) if control["applied"] else ""
    previous_evidence = []
    for _ in range(sum(1 + item.retry_limit for item in declaration.phases) + 1):
        if state["status"] != "active":
            break
        declared = pipeline._phase_by_id(declaration, state["currentPhaseId"])
        prepared = {"schemaVersion": phase.PACKET_SCHEMA, "executionId": execution, "profileId": profile,
                    "provider": provider, "runStatus": state["status"], "revision": state["revision"],
                    "currentAttempt": state["currentAttempt"], "phase": declared.as_dict(),
                    "executionEnvelope": envelope, "contextManifest": manifest, "previousCheckpoint": previous,
                    "phaseInput": {"schemaVersion": "mana.context-runtime.phase-input/v1", "executionId": execution,
                                   "phaseId": declared.identity, "executionEnvelopeRef": "G-001", "contextManifestRef": "M-001",
                                   "objective": inputs["objective"], "checkpointRef": None if previous is None else previous["checkpointId"],
                                   "evidenceRefs": previous_evidence}, "providerInvoked": False}
        phase.validate_packet(prepared)
        prompt = phase.render_prompt(prepared)
        # Include the captured input and authorized evidence snapshot; neither
        # consumer follows source locators after host materialization.
        prompt += "\nCanonical shared input:\n" + shared.unblob(packet["input"]).decode()
        prompt += "\nComparison observation binding:\n" + shared.canonical({
            "profileId": profile, "targetKey": shared.digest(shared.canonical(packet["target"]))}).decode()
        prompt += "\nAuthorized evidence snapshot:\n" + shared.canonical(packet["evidenceSnapshot"]).decode()
        model = inputs["fullModel"] if declared.model_tier == "full" else inputs["economyModel"]
        if declared.model_tier not in {"economy", "full"}:
            raise shared.Error("shadow host phase adapter unavailable")
        # Build and consume the CTX-06 argv in the same shell array. No text
        # serialization/split or eval participates in the transport.
        completed = subprocess.run(["bash", str(HERE / "context-shadow-phase-provider.sh"), provider, str(project),
            profile, execution, model,
            "true" if report["capabilities"]["structuredOutputSchema"]["status"] == "supported" else "false", threshold],
            input=prompt.encode(), capture_output=True)
        try:
            archived = phase.archive_metrics(str(project), execution, profile, provider, declared.identity, declared.ordinal,
                                            state["currentAttempt"], report["providerVersion"],
                                            "complete" if completed.returncode == 0 else "failed")
            with tempfile.TemporaryDirectory(prefix="mana-shadow-budget-", dir=os.environ.get("TMPDIR")) as temporary:
                prompt_path = Path(temporary).resolve() / "prompt.txt"
                prompt_path.write_bytes(prompt.encode())
                prompt_path.chmod(0o600)
                shared.budget.advisory(resolution, str(project / archived["summaryRef"]), str(project),
                    f"{declared.ordinal}-{declared.identity}-{state['currentAttempt']}-{archived['invocation']}", str(prompt_path))
        except (phase.runtime.ContractError, shared.Error, OSError, ValueError, TypeError):
            print("WARNING: shadow usage advisory unavailable", file=sys.stderr)
        if completed.returncode:
            return completed.returncode, b"", b""
        with tempfile.TemporaryDirectory(prefix="mana-shadow-checkpoint-", dir=os.environ.get("TMPDIR")) as temporary:
            checkpoint_path = Path(temporary).resolve() / "checkpoint.json"
            checkpoint_path.write_bytes(completed.stdout)
            checkpoint_path.chmod(0o600)
            checkpoint = phase.normalize_output(provider, str(checkpoint_path))
        # Admission precedes every CTX-06 checkpoint/bundle/HEAD publication.
        # The reducer and the general CTX-06/07 runtimes remain unchanged.
        privacy.validate(checkpoint)
        observations = checkpoint.get("comparisonProjection")
        if observations is not None:
            comparison = shared.load("ctx09c_precommit_comparison", "context-comparison.py")
            comparison.native_input(shared.canonical(observations), comparison.Contracts())
            if (observations["profileId"] != profile or observations["targetKey"] !=
                    shared.digest(shared.canonical(packet["target"]))):
                raise shared.Error("foreign precommit comparison observations")
        with tempfile.TemporaryDirectory(prefix="mana-shadow-commit-", dir=os.environ.get("TMPDIR")) as temporary:
            checkpoint_path = Path(temporary).resolve() / "checkpoint.json"
            checkpoint_path.write_bytes(shared.canonical(checkpoint))
            checkpoint_path.chmod(0o600)
            durable_args.checkpoint = str(checkpoint_path)
            pipeline.accept_checkpoint(durable_args)
        state = pipeline._load_run_context(durable_args).state
        previous, previous_evidence = checkpoint, checkpoint["evidenceRefs"]
    if state["status"] != "completed":
        return 3, b"", b""
    return 0, shared.canonical(project_completed(project, framework, packet, inputs)), b""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("legacy", "v2"))
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    try:
        payload = sys.stdin.buffer.read(shared.MAX_BYTES + 1)
        status, output, diagnostics = consume(payload, args.role, Path(args.project_root))
        sys.stdout.buffer.write(output)
        sys.stderr.buffer.write(diagnostics)
        raise SystemExit(status)
    except (shared.Error, privacy.PrivacyError, pipeline.runtime.ContractError, phase.runtime.ContractError,
            OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        print("ERROR: canonical shadow consumer rejected", file=sys.stderr)
        raise SystemExit(2)
