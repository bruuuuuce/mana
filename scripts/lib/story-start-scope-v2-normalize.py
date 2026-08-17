#!/usr/bin/env python3
"""Deterministically normalize schema-valid Story Start Scope v2 artifacts.

This is internal SS02/SS03 host support. It deliberately consumes only compact
artifacts; it never traverses a repository or creates implementation work.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "tests" / "lib"))
from json_schema_subset import SchemaEvaluator  # noqa: E402


class NormalizationError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(prefix: str, identity: Any) -> str:
    digest = hashlib.sha256(canonical(identity).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def remap(refs: list[str], mapping: dict[str, str], label: str) -> list[str]:
    try:
        return sorted({mapping[ref] for ref in refs})
    except KeyError as exc:
        raise NormalizationError(f"{label} references unknown ID {exc.args[0]!r}") from exc


def old_ids(items: list[dict[str, Any]], label: str) -> None:
    identifiers = [item["id"] for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise NormalizationError(f"duplicate provider IDs in {label}")


def normalized_provenance(item: dict[str, Any]) -> dict[str, Any]:
    source_ref = item["sourceRef"]
    if source_ref.startswith(("/", "\\")) or "/../" in source_ref or source_ref.startswith("../"):
        raise NormalizationError("provenance sourceRef must be a bounded, non-absolute reference")
    if re.search(r"(?i)(token|password|secret|api[_-]?key)\s*[:=]", source_ref):
        raise NormalizationError("provenance sourceRef appears to contain a credential")
    return {
        "sourceType": item["sourceType"],
        "sourceRef": source_ref,
        "sourceDigest": item["sourceDigest"],
        "summary": item["summary"],
    }


def finalized(
    items: list[dict[str, Any]],
    prefix: str,
    label: str,
    build: Any,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    old_ids(items, label)
    output: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}
    for item in items:
        result = build(item)
        new_id = stable_id(prefix, result)
        if new_id in mapping.values():
            raise NormalizationError(f"duplicate semantic identity in {label}")
        mapping[item["id"]] = new_id
        output.append({"id": new_id, **result})
    return sorted(output, key=lambda value: value["id"]), mapping


def validate(schema_path: Path, instance: Any) -> None:
    evaluator = SchemaEvaluator()
    schema = evaluator.load(schema_path)
    errors = evaluator.evaluate(instance, schema, schema_path)
    if errors:
        raise NormalizationError("; ".join(errors[:8]))


def normalize_discovery(raw: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(raw)

    provenance, provenance_map = finalized(
        raw["provenance"],
        "provenance",
        "provenance",
        normalized_provenance,
    )
    acceptance, acceptance_map = finalized(
        raw["acceptanceCriteria"],
        "ac",
        "acceptance criteria",
        lambda item: {
            "sourceKey": item["sourceKey"],
            "text": item["text"],
            "approvalStatus": item["approvalStatus"],
            "provenanceRefs": remap(item["provenanceRefs"], provenance_map, "acceptance criterion"),
        },
    )
    evidence, evidence_map = finalized(
        raw["evidence"],
        "ev",
        "evidence",
        lambda item: {
            "kind": item["kind"],
            "epistemicStatus": item["epistemicStatus"],
            "summary": item["summary"],
            "capabilityState": item["capabilityState"],
            "preExistingStatus": item["preExistingStatus"],
            "provenanceRefs": remap(item["provenanceRefs"], provenance_map, "evidence"),
        },
    )
    constraints, constraint_map = finalized(
        raw["mandatoryConstraints"],
        "constraint",
        "mandatory constraints",
        lambda item: {
            "kind": item["kind"],
            "statement": item["statement"],
            "evidenceRefs": remap(item["evidenceRefs"], evidence_map, "mandatory constraint"),
        },
    )

    option_map: dict[str, str] = {}
    normalized_decisions: list[dict[str, Any]] = []
    old_ids(raw["decisions"], "decisions")
    for decision in raw["decisions"]:
        old_ids(decision["options"], f"decision options for {decision['id']}")
        options: list[dict[str, Any]] = []
        local_option_map: dict[str, str] = {}
        for option in decision["options"]:
            option_value = {"label": option["label"], "summary": option["summary"]}
            option_id = stable_id("option", option_value)
            if option_id in local_option_map.values():
                raise NormalizationError(f"duplicate semantic option in {decision['id']}")
            local_option_map[option["id"]] = option_id
            option_map[option["id"]] = option_id
            options.append({"id": option_id, **option_value})
        selected = decision["selectedOptionId"]
        if selected is not None and selected not in local_option_map:
            raise NormalizationError(f"decision {decision['id']} selects an option it does not contain")
        decision_value = {
            "question": decision["question"],
            "owner": decision["owner"],
            "status": decision["status"],
            "materiality": decision["materiality"],
            "options": sorted(options, key=lambda value: value["id"]),
            "selectedOptionId": None if selected is None else local_option_map[selected],
            "evidenceRefs": remap(decision["evidenceRefs"], evidence_map, "decision"),
        }
        normalized_decisions.append({"id": stable_id("decision", decision_value), **decision_value})
    decision_ids = [decision["id"] for decision in normalized_decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise NormalizationError("duplicate semantic identity in decisions")
    decision_map = {
        old["id"]: new["id"] for old, new in zip(raw["decisions"], normalized_decisions)
    }
    decisions = sorted(normalized_decisions, key=lambda value: value["id"])

    findings, _ = finalized(
        raw["findings"],
        "finding",
        "findings",
        lambda item: {
            "findingKind": item["findingKind"],
            "summary": item["summary"],
            "evidenceRefs": remap(item["evidenceRefs"], evidence_map, "finding"),
            "acceptanceCriterionRefs": remap(item["acceptanceCriterionRefs"], acceptance_map, "finding"),
            "mandatoryConstraintRefs": remap(item["mandatoryConstraintRefs"], constraint_map, "finding"),
            "decisionRefs": remap(item["decisionRefs"], decision_map, "finding"),
            "storyCausality": item["storyCausality"],
            "suggestedOwner": item["suggestedOwner"],
        },
    )
    questions, _ = finalized(
        raw["openQuestions"],
        "question",
        "open questions",
        lambda item: {
            "question": item["question"],
            "suggestedOwner": item["suggestedOwner"],
            "evidenceRefs": remap(item["evidenceRefs"], evidence_map, "open question"),
            "acceptanceCriterionRefs": remap(item["acceptanceCriterionRefs"], acceptance_map, "open question"),
            "decisionNeeded": item["decisionNeeded"],
        },
    )

    result["provenance"] = provenance
    result["acceptanceCriteria"] = acceptance
    result["evidence"] = evidence
    result["mandatoryConstraints"] = constraints
    result["decisions"] = decisions
    result["findings"] = findings
    result["openQuestions"] = questions
    result["validationStatus"]["violationCodes"] = sorted(result["validationStatus"]["violationCodes"])
    artifact_identity = {
        "schemaVersion": result["schemaVersion"],
        "artifactVersion": result["artifactVersion"],
        "storyId": result["storyId"],
        "acceptanceCriteria": acceptance,
        "mandatoryConstraints": constraints,
        "evidence": evidence,
        "findings": findings,
        "decisions": decisions,
        "openQuestions": questions,
        "provenance": provenance,
    }
    result["artifactId"] = stable_id("discovery", artifact_identity)
    return result


def normalized_decision(decision: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(decision)
    result["options"] = sorted(result["options"], key=lambda value: value["id"])
    result["evidenceRefs"] = sorted(set(result["evidenceRefs"]))
    return result


def normalize_triage(raw: dict[str, Any], discovery: dict[str, Any]) -> dict[str, Any]:
    if raw["storyId"] != discovery["storyId"]:
        raise NormalizationError("triage storyId does not match discovery")
    if raw["sourceDiscoveryArtifactRef"] != discovery["artifactId"]:
        raise NormalizationError("triage sourceDiscoveryArtifactRef does not match discovery")

    evidence_ids = {item["id"] for item in discovery["evidence"]}
    acceptance_ids = {item["id"] for item in discovery["acceptanceCriteria"]}
    constraint_ids = {item["id"] for item in discovery["mandatoryConstraints"]}
    finding_ids = {item["id"] for item in discovery["findings"]}
    findings_by_id = {item["id"]: item for item in discovery["findings"]}
    decisions = sorted(
        [normalized_decision(item) for item in raw["decisions"]],
        key=lambda value: value["id"],
    )
    discovery_decisions = sorted(
        [normalized_decision(item) for item in discovery["decisions"]],
        key=lambda value: value["id"],
    )
    if canonical(decisions) != canonical(discovery_decisions):
        raise NormalizationError("triage must preserve discovery decisions exactly")
    decision_ids = {item["id"] for item in decisions}
    decision_status_by_id = {item["id"]: item["status"] for item in decisions}
    option_ids_by_decision = {
        item["id"]: {option["id"] for option in item["options"]} for item in decisions
    }

    old_ids(raw["classifications"], "classifications")
    classifications: list[dict[str, Any]] = []
    classification_map: dict[str, str] = {}
    seen_findings: set[str] = set()
    for item in raw["classifications"]:
        finding_ref = item["findingRef"]
        if finding_ref not in finding_ids:
            raise NormalizationError(f"classification references unknown finding {finding_ref!r}")
        if finding_ref in seen_findings:
            raise NormalizationError(f"finding is classified more than once: {finding_ref}")
        seen_findings.add(finding_ref)
        finding = findings_by_id[finding_ref]
        for refs, allowed, finding_refs, label in (
            (item["evidenceRefs"], evidence_ids, finding["evidenceRefs"], "evidence"),
            (
                item["acceptanceCriterionRefs"],
                acceptance_ids,
                finding["acceptanceCriterionRefs"],
                "acceptance criterion",
            ),
            (
                item["mandatoryConstraintRefs"],
                constraint_ids,
                finding["mandatoryConstraintRefs"],
                "mandatory constraint",
            ),
        ):
            unknown = set(refs) - allowed
            if unknown:
                raise NormalizationError(f"classification references unknown {label}: {sorted(unknown)}")
            ungrounded = set(refs) - set(finding_refs)
            if ungrounded:
                raise NormalizationError(
                    f"classification references {label} not linked to its finding: {sorted(ungrounded)}"
                )
        decision_ref = item["decisionRef"]
        if decision_ref is not None and decision_ref not in decision_ids:
            raise NormalizationError(f"classification references unknown decision {decision_ref!r}")
        if decision_ref is not None and decision_ref not in finding["decisionRefs"]:
            raise NormalizationError("classification decision is not linked to its finding")
        if item["suggestedOwner"] != finding["suggestedOwner"]:
            raise NormalizationError("classification must preserve the discovery finding owner")
        assessment = copy.deepcopy(item["promotionAssessment"])
        if assessment is not None:
            assessment["failingAcceptanceCriterionRefs"] = sorted(set(assessment["failingAcceptanceCriterionRefs"]))
            assessment["failingMandatoryConstraintRefs"] = sorted(set(assessment["failingMandatoryConstraintRefs"]))
            assessment["dependencyEvidenceRefs"] = sorted(set(assessment["dependencyEvidenceRefs"]))
            if set(assessment["failingAcceptanceCriterionRefs"]) - acceptance_ids:
                raise NormalizationError("promotion assessment references unknown acceptance criterion")
            if set(assessment["failingMandatoryConstraintRefs"]) - constraint_ids:
                raise NormalizationError("promotion assessment references unknown mandatory constraint")
            if set(assessment["dependencyEvidenceRefs"]) - evidence_ids:
                raise NormalizationError("promotion assessment references unknown evidence")
            if set(assessment["failingAcceptanceCriterionRefs"]) - set(item["acceptanceCriterionRefs"]):
                raise NormalizationError("promotion assessment AC is not linked by its classification")
            if set(assessment["failingMandatoryConstraintRefs"]) - set(item["mandatoryConstraintRefs"]):
                raise NormalizationError("promotion assessment constraint is not linked by its classification")
            if set(assessment["dependencyEvidenceRefs"]) - set(item["evidenceRefs"]):
                raise NormalizationError("promotion assessment evidence is not linked by its classification")
            unresolved = assessment["unresolvedDecisionRef"]
            if unresolved is not None and unresolved not in decision_ids:
                raise NormalizationError("promotion assessment references unknown decision")
            if unresolved is not None and decision_status_by_id[unresolved] != "open":
                raise NormalizationError("promotion assessment decision is not open")
            if unresolved != decision_ref:
                raise NormalizationError("promotion assessment decision does not match classification decision")
            expected = {
                "CORE_SCOPE": "core_scope_supported",
                "REQUIRED_ENABLER": "required_enabler_supported",
            }.get(item["category"])
            if expected is None or assessment["conclusion"] != expected:
                raise NormalizationError("promotion assessment conclusion does not match category")
        classification_value = {
            "findingRef": finding_ref,
            "category": item["category"],
            "evidenceRefs": sorted(set(item["evidenceRefs"])),
            "acceptanceCriterionRefs": sorted(set(item["acceptanceCriterionRefs"])),
            "mandatoryConstraintRefs": sorted(set(item["mandatoryConstraintRefs"])),
            "decisionRef": decision_ref,
            "condition": item["condition"],
            "mandatoryReason": item["mandatoryReason"],
            "includedInBasePlan": item["includedInBasePlan"],
            "rationale": item["rationale"],
            "scopeExpansionRef": item["scopeExpansionRef"],
            "suggestedOwner": item["suggestedOwner"],
            "promotionAssessment": assessment,
        }
        classification_id = stable_id("classification", classification_value)
        if classification_id in classification_map.values():
            raise NormalizationError("duplicate semantic classification identity")
        classification_map[item["id"]] = classification_id
        classifications.append({"id": classification_id, **classification_value})
    if seen_findings != finding_ids:
        raise NormalizationError(
            f"triage must classify every discovery finding; missing {sorted(finding_ids - seen_findings)}"
        )
    classifications.sort(key=lambda value: value["id"])

    groups: list[dict[str, Any]] = []
    grouped_decisions: set[str] = set()
    old_ids(raw["optionGroups"], "option groups")
    for item in raw["optionGroups"]:
        decision_ref = item["decisionRef"]
        if decision_ref not in option_ids_by_decision:
            raise NormalizationError("option group references unknown decision")
        if decision_ref in grouped_decisions:
            raise NormalizationError("decision appears in more than one option group")
        grouped_decisions.add(decision_ref)
        option_refs = sorted(set(item["optionRefs"]))
        if set(option_refs) != option_ids_by_decision[decision_ref]:
            raise NormalizationError("option group must contain exactly its decision options")
        group_value = {
            "decisionRef": decision_ref,
            "relationship": item["relationship"],
            "selectionRule": item["selectionRule"],
            "optionRefs": option_refs,
        }
        groups.append({"id": stable_id("optiongroup", group_value), **group_value})
    if grouped_decisions != decision_ids:
        raise NormalizationError(
            f"triage must group every decision; missing {sorted(decision_ids - grouped_decisions)}"
        )
    group_ids = [item["id"] for item in groups]
    if len(group_ids) != len(set(group_ids)):
        raise NormalizationError("duplicate semantic option-group identity")
    groups.sort(key=lambda value: value["id"])

    expansions: list[dict[str, Any]] = []
    old_ids(raw["scopeExpansions"], "scope expansions")
    for item in raw["scopeExpansions"]:
        if item["originalClassificationRef"] not in classification_map:
            raise NormalizationError("scope expansion references unknown classification")
        if item["decisionRef"] not in decision_ids:
            raise NormalizationError("scope expansion references unknown decision")
        if set(item["approvalEvidenceRefs"]) - evidence_ids:
            raise NormalizationError("scope expansion references unknown evidence")
        expansion_value = {
            "originalClassificationRef": classification_map[item["originalClassificationRef"]],
            "decisionRef": item["decisionRef"],
            "approvalEvidenceRefs": sorted(set(item["approvalEvidenceRefs"])),
            "status": item["status"],
            "resultingWorkRefs": sorted(set(item["resultingWorkRefs"])),
        }
        expansions.append({"id": stable_id("expansion", expansion_value), **expansion_value})
    expansions.sort(key=lambda value: value["id"])

    result = copy.deepcopy(raw)
    result["classifications"] = classifications
    result["decisions"] = decisions
    result["optionGroups"] = groups
    result["scopeExpansions"] = expansions
    result["validationStatus"]["violationCodes"] = sorted(result["validationStatus"]["violationCodes"])
    evidence_gap_refs = {
        item["id"] for item in discovery["findings"] if item["findingKind"] == "evidence_gap"
    }
    if evidence_gap_refs:
        gap_classifications = [
            item for item in classifications if item["findingRef"] in evidence_gap_refs
        ]
        if any(item["category"] != "RISK_ONLY" or item["suggestedOwner"] is None for item in gap_classifications):
            raise NormalizationError("discovery evidence gaps require RISK_ONLY with a suggested owner")
        review = result["validationStatus"]["ownerReview"]
        if review["state"] not in {"required", "in_progress"}:
            raise NormalizationError("discovery evidence gaps require triage owner review")
        if result["validationStatus"]["semanticValidation"] != "needs_owner_review":
            raise NormalizationError("discovery evidence gaps require needs_owner_review status")
        if "EVIDENCE_GAP_REQUIRES_OWNER_REVIEW" not in result["validationStatus"]["violationCodes"]:
            raise NormalizationError("discovery evidence gaps require an explicit violation code")
    artifact_identity = {
        "schemaVersion": result["schemaVersion"],
        "artifactVersion": result["artifactVersion"],
        "storyId": result["storyId"],
        "sourceDiscoveryArtifactRef": result["sourceDiscoveryArtifactRef"],
        "classifications": classifications,
        "decisions": decisions,
        "optionGroups": groups,
        "scopeExpansions": expansions,
    }
    result["artifactId"] = stable_id("triage", artifact_identity)
    return result


def main(argv: list[str]) -> int:
    if len(argv) == 5 and argv[1] == "normalize-discovery":
        schema_path, input_path, output_path = map(Path, argv[2:])
        discovery_path = None
    elif len(argv) == 6 and argv[1] == "normalize-triage":
        schema_path, discovery_path, input_path, output_path = map(Path, argv[2:])
    else:
        print(
            "Usage: story-start-scope-v2-normalize.py normalize-discovery <schema> <input> <output>\n"
            "   or: story-start-scope-v2-normalize.py normalize-triage <schema> <discovery> <input> <output>",
            file=sys.stderr,
        )
        return 2
    try:
        with input_path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        validate(schema_path.resolve(), raw)
        if discovery_path is None:
            normalized = normalize_discovery(raw)
        else:
            with discovery_path.open(encoding="utf-8") as handle:
                discovery = json.load(handle)
            discovery_schema = REPOSITORY_ROOT / "contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json"
            validate(discovery_schema, discovery)
            normalized = normalize_triage(raw, discovery)
        validate(schema_path.resolve(), normalized)
        output_path.write_text(canonical(normalized) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, NormalizationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
