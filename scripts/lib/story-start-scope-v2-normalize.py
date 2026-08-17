#!/usr/bin/env python3
"""Deterministically normalize schema-valid Story Start Scope v2 artifacts.

This is internal SS02-SS04 host support. It deliberately consumes only compact
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


def build_planning_context(
    discovery: dict[str, Any], triage: dict[str, Any]
) -> dict[str, Any]:
    if discovery["storyId"] != triage["storyId"]:
        raise NormalizationError("planning context inputs have different story IDs")
    if triage["sourceDiscoveryArtifactRef"] != discovery["artifactId"]:
        raise NormalizationError("triage does not reference the supplied discovery artifact")

    evidence_refs = {
        ref
        for classification in triage["classifications"]
        for ref in classification["evidenceRefs"]
    }
    evidence_refs.update(
        ref for decision in triage["decisions"] for ref in decision["evidenceRefs"]
    )
    evidence_by_id = {item["id"]: item for item in discovery["evidence"]}
    if evidence_refs - set(evidence_by_id):
        raise NormalizationError("triage references evidence absent from discovery")
    evidence = sorted(
        [copy.deepcopy(evidence_by_id[ref]) for ref in evidence_refs],
        key=lambda value: value["id"],
    )
    provenance_refs = {
        ref for item in evidence for ref in item["provenanceRefs"]
    }
    provenance_by_id = {item["id"]: item for item in discovery["provenance"]}
    acceptance_refs = {
        ref
        for classification in triage["classifications"]
        for ref in classification["acceptanceCriterionRefs"]
    }
    constraint_refs = {
        ref
        for classification in triage["classifications"]
        for ref in classification["mandatoryConstraintRefs"]
    }
    acceptance_by_id = {
        item["id"]: item for item in discovery["acceptanceCriteria"]
    }
    constraint_by_id = {
        item["id"]: item for item in discovery["mandatoryConstraints"]
    }
    if acceptance_refs - set(acceptance_by_id):
        raise NormalizationError("triage references an unknown acceptance criterion")
    if constraint_refs - set(constraint_by_id):
        raise NormalizationError("triage references an unknown mandatory constraint")
    provenance_refs.update(
        ref
        for acceptance_ref in acceptance_refs
        for ref in acceptance_by_id[acceptance_ref]["provenanceRefs"]
    )
    if provenance_refs - set(provenance_by_id):
        raise NormalizationError("planning evidence references unknown provenance")

    value = {
        "contextVersion": "mana.story-start.planning-context/v2",
        "storyId": discovery["storyId"],
        "sourceDiscoveryArtifactRef": discovery["artifactId"],
        "sourceTriageArtifactRef": triage["artifactId"],
        "acceptanceCriteria": sorted(
            [copy.deepcopy(acceptance_by_id[ref]) for ref in acceptance_refs],
            key=lambda item: item["id"],
        ),
        "mandatoryConstraints": sorted(
            [copy.deepcopy(constraint_by_id[ref]) for ref in constraint_refs],
            key=lambda item: item["id"],
        ),
        "evidence": evidence,
        "provenance": sorted(
            [copy.deepcopy(provenance_by_id[ref]) for ref in provenance_refs],
            key=lambda item: item["id"],
        ),
    }
    return {"contextId": stable_id("planningcontext", value), **value}


def validate_planning_context(
    context: dict[str, Any], triage: dict[str, Any]
) -> None:
    context_schema = REPOSITORY_ROOT / "contracts/story-start/scope-v2/schemas/planning-context.schema.json"
    validate(context_schema, context)
    required_keys = {
        "contextId",
        "contextVersion",
        "storyId",
        "sourceDiscoveryArtifactRef",
        "sourceTriageArtifactRef",
        "acceptanceCriteria",
        "mandatoryConstraints",
        "evidence",
        "provenance",
    }
    if set(context) != required_keys:
        raise NormalizationError("planning context has an invalid structure")
    if context["contextVersion"] != "mana.story-start.planning-context/v2":
        raise NormalizationError("unsupported planning context version")
    if context["storyId"] != triage["storyId"]:
        raise NormalizationError("planning context storyId does not match triage")
    if context["sourceTriageArtifactRef"] != triage["artifactId"]:
        raise NormalizationError("planning context does not reference triage")
    if context["sourceDiscoveryArtifactRef"] != triage["sourceDiscoveryArtifactRef"]:
        raise NormalizationError("planning context discovery reference does not match triage")
    identity = {key: copy.deepcopy(value) for key, value in context.items() if key != "contextId"}
    if context["contextId"] != stable_id("planningcontext", identity):
        raise NormalizationError("planning context ID does not match its content")

    for key in ("acceptanceCriteria", "mandatoryConstraints", "evidence", "provenance"):
        if not isinstance(context[key], list):
            raise NormalizationError(f"planning context {key} must be an array")
        old_ids(context[key], f"planning context {key}")
        if context[key] != sorted(context[key], key=lambda item: item["id"]):
            raise NormalizationError(f"planning context {key} is not canonically ordered")
    evidence_by_id = {item["id"]: item for item in context["evidence"]}
    provenance_by_id = {item["id"]: item for item in context["provenance"]}
    acceptance_ids = {item["id"] for item in context["acceptanceCriteria"]}
    constraint_ids = {item["id"] for item in context["mandatoryConstraints"]}
    required_evidence = {
        ref
        for classification in triage["classifications"]
        for ref in classification["evidenceRefs"]
    }
    required_evidence.update(
        ref for decision in triage["decisions"] for ref in decision["evidenceRefs"]
    )
    if set(evidence_by_id) != required_evidence:
        raise NormalizationError("planning context evidence does not exactly cover triage")
    required_acceptance = {
        ref
        for classification in triage["classifications"]
        for ref in classification["acceptanceCriterionRefs"]
    }
    required_constraints = {
        ref
        for classification in triage["classifications"]
        for ref in classification["mandatoryConstraintRefs"]
    }
    if acceptance_ids != required_acceptance or constraint_ids != required_constraints:
        raise NormalizationError("planning context requirement references do not cover triage")
    required_provenance = {
        ref for item in evidence_by_id.values() for ref in item["provenanceRefs"]
    }
    required_provenance.update(
        ref
        for item in context["acceptanceCriteria"]
        for ref in item["provenanceRefs"]
    )
    if set(provenance_by_id) != required_provenance:
        raise NormalizationError("planning context provenance does not exactly cover evidence")
    for item in context["acceptanceCriteria"]:
        value = {
            "sourceKey": item["sourceKey"],
            "text": item["text"],
            "approvalStatus": item["approvalStatus"],
            "provenanceRefs": sorted(set(item["provenanceRefs"])),
        }
        if item["id"] != stable_id("ac", value):
            raise NormalizationError("planning context acceptance criterion ID is invalid")
    for item in context["evidence"]:
        value = {
            "kind": item["kind"],
            "epistemicStatus": item["epistemicStatus"],
            "summary": item["summary"],
            "capabilityState": item["capabilityState"],
            "preExistingStatus": item["preExistingStatus"],
            "provenanceRefs": sorted(set(item["provenanceRefs"])),
        }
        if item["id"] != stable_id("ev", value):
            raise NormalizationError("planning context evidence ID is invalid")
    for item in context["mandatoryConstraints"]:
        value = {
            "kind": item["kind"],
            "statement": item["statement"],
            "evidenceRefs": sorted(set(item["evidenceRefs"])),
        }
        if item["id"] != stable_id("constraint", value):
            raise NormalizationError("planning context constraint ID is invalid")
    for item in context["provenance"]:
        value = normalized_provenance(item)
        if item["id"] != stable_id("provenance", value):
            raise NormalizationError("planning context provenance ID is invalid")


def effort_numbers(effort: dict[str, Any]) -> tuple[float, float]:
    return effort["minimumPersonHours"], effort["additionalPersonHours"]


def require_effort_sum(
    total: dict[str, Any], components: list[dict[str, Any]], kind: str, label: str
) -> None:
    minimum = sum(effort_numbers(item)[0] for item in components)
    additional = sum(effort_numbers(item)[1] for item in components)
    if (
        total["estimateKind"] != kind
        or total["unit"] != "person_hours"
        or total["minimumPersonHours"] != minimum
        or total["additionalPersonHours"] != additional
    ):
        raise NormalizationError(f"{label} is not the arithmetic sum of its components")


def normalize_plan(
    raw: dict[str, Any], context: dict[str, Any], triage: dict[str, Any]
) -> dict[str, Any]:
    validate_planning_context(context, triage)
    if raw["storyId"] != triage["storyId"]:
        raise NormalizationError("plan storyId does not match triage")
    if raw["sourceTriageArtifactRef"] != triage["artifactId"]:
        raise NormalizationError("plan sourceTriageArtifactRef does not match triage")

    classifications = {item["id"]: item for item in triage["classifications"]}
    categories: dict[str, set[str]] = {}
    for item in triage["classifications"]:
        categories.setdefault(item["category"], set()).add(item["id"])
    decisions = sorted(
        [normalized_decision(item) for item in raw["decisionRegister"]],
        key=lambda item: item["id"],
    )
    triage_decisions = sorted(
        [normalized_decision(item) for item in triage["decisions"]],
        key=lambda item: item["id"],
    )
    if canonical(decisions) != canonical(triage_decisions):
        raise NormalizationError("plan must preserve the triage decision register exactly")
    option_ids_by_decision = {
        item["id"]: {option["id"] for option in item["options"]}
        for item in decisions
    }
    triage_groups = {item["decisionRef"]: item for item in triage["optionGroups"]}

    evidence_by_id = {item["id"]: item for item in context["evidence"]}
    provenance_by_id = {item["id"]: item for item in context["provenance"]}
    verified_evidence = {
        ref
        for item in triage["classifications"]
        if item["category"] == "VERIFIED_FACT"
        for ref in item["evidenceRefs"]
    }

    provider_task_ids: set[str] = set()
    generated_task_ids: set[str] = set()

    def planned_task(
        item: dict[str, Any],
        allowed_evidence: set[str],
        required_evidence: set[str],
        identity_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if item["id"] in provider_task_ids:
            raise NormalizationError("duplicate provider task ID")
        provider_task_ids.add(item["id"])
        evidence_refs = sorted(set(item["evidenceRefs"]))
        test_refs = sorted(set(item["testEvidenceRefs"]))
        provenance_refs = sorted(set(item["provenanceRefs"]))
        if set(evidence_refs + test_refs) - set(evidence_by_id):
            raise NormalizationError("task references evidence outside planning context")
        if set(evidence_refs + test_refs) - allowed_evidence:
            raise NormalizationError("task references evidence outside its classification")
        if not required_evidence.issubset(set(evidence_refs)):
            raise NormalizationError("task omits its classification evidence")
        evidence_provenance = {
            ref
            for evidence_ref in evidence_refs + test_refs
            for ref in evidence_by_id[evidence_ref]["provenanceRefs"]
        }
        if set(provenance_refs) - evidence_provenance:
            raise NormalizationError("task provenance is not supported by task evidence")
        if not provenance_refs:
            raise NormalizationError("task has no provenance")
        source_refs = {provenance_by_id[ref]["sourceRef"] for ref in provenance_refs}
        source_targets = sorted(set(item["sourceTargets"]))
        if set(source_targets) - source_refs:
            raise NormalizationError("task source target is not provenance-backed")
        value = {
            "title": item["title"],
            "description": item["description"],
            "evidenceRefs": evidence_refs,
            "provenanceRefs": provenance_refs,
            "sourceTargets": source_targets,
            "testEvidenceRefs": test_refs,
        }
        task_id = stable_id("task", {**(identity_fields or {}), **value})
        if task_id in generated_task_ids:
            raise NormalizationError("duplicate semantic task identity")
        generated_task_ids.add(task_id)
        return {"id": task_id, **value}

    old_ids(raw["basePlan"], "base plan")
    base_plan: list[dict[str, Any]] = []
    base_classifications: set[str] = set()
    for item in raw["basePlan"]:
        classification = classifications.get(item["classificationRef"])
        if classification is None or classification["category"] != "CORE_SCOPE":
            raise NormalizationError("base plan task does not reference CORE_SCOPE")
        if item["classificationRef"] in base_classifications:
            raise NormalizationError("CORE_SCOPE classification appears twice in base plan")
        base_classifications.add(item["classificationRef"])
        if (
            set(item["acceptanceCriterionRefs"]) != set(classification["acceptanceCriterionRefs"])
            or set(item["mandatoryConstraintRefs"]) != set(classification["mandatoryConstraintRefs"])
        ):
            raise NormalizationError("base plan requirement links differ from triage")
        base_identity = {
            "classificationRef": item["classificationRef"],
            "originCategory": "CORE_SCOPE",
            "acceptanceCriterionRefs": sorted(set(item["acceptanceCriterionRefs"])),
            "mandatoryConstraintRefs": sorted(set(item["mandatoryConstraintRefs"])),
            "effort": copy.deepcopy(item["effort"]),
        }
        common_task = planned_task(
            item,
            set(classification["evidenceRefs"]) | verified_evidence,
            set(classification["evidenceRefs"]),
            base_identity,
        )
        value = {
            **base_identity,
            **{key: value for key, value in common_task.items() if key != "id"},
        }
        base_plan.append({"id": common_task["id"], **value})
    if base_classifications != categories.get("CORE_SCOPE", set()):
        raise NormalizationError("base plan does not exactly cover CORE_SCOPE")
    base_plan.sort(key=lambda item: item["id"])

    old_ids(raw["requiredEnablers"], "required enablers")
    required_enablers: list[dict[str, Any]] = []
    enabler_map: dict[str, str] = {}
    enabler_classifications: set[str] = set()
    for item in raw["requiredEnablers"]:
        classification = classifications.get(item["classificationRef"])
        if classification is None or classification["category"] != "REQUIRED_ENABLER":
            raise NormalizationError("enabler does not reference REQUIRED_ENABLER")
        if item["classificationRef"] in enabler_classifications:
            raise NormalizationError("REQUIRED_ENABLER classification appears twice")
        enabler_classifications.add(item["classificationRef"])
        for field in (
            "mandatoryReason",
            "evidenceRefs",
            "acceptanceCriterionRefs",
            "mandatoryConstraintRefs",
        ):
            expected = classification[field]
            actual = item[field]
            if canonical(sorted(actual) if isinstance(actual, list) else actual) != canonical(
                sorted(expected) if isinstance(expected, list) else expected
            ):
                raise NormalizationError(f"enabler {field} differs from triage")
        tasks = [
            planned_task(
                task,
                set(classification["evidenceRefs"]) | verified_evidence,
                set(classification["evidenceRefs"]),
            )
            for task in item["tasks"]
        ]
        tasks.sort(key=lambda task: task["id"])
        value = {
            "classificationRef": item["classificationRef"],
            "originCategory": "REQUIRED_ENABLER",
            "title": item["title"],
            "mandatoryReason": item["mandatoryReason"],
            "evidenceRefs": sorted(set(item["evidenceRefs"])),
            "acceptanceCriterionRefs": sorted(set(item["acceptanceCriterionRefs"])),
            "mandatoryConstraintRefs": sorted(set(item["mandatoryConstraintRefs"])),
            "tasks": tasks,
            "effort": copy.deepcopy(item["effort"]),
        }
        enabler_id = stable_id("enabler", value)
        if enabler_id in enabler_map.values():
            raise NormalizationError("duplicate semantic enabler identity")
        enabler_map[item["id"]] = enabler_id
        required_enablers.append({"id": enabler_id, **value})
    if enabler_classifications != categories.get("REQUIRED_ENABLER", set()):
        raise NormalizationError("required enablers do not exactly cover triage")
    required_enablers.sort(key=lambda item: item["id"])
    enablers_by_id = {item["id"]: item for item in required_enablers}

    old_ids(raw["readinessPrerequisites"], "readiness prerequisites")
    readiness: list[dict[str, Any]] = []
    readiness_map: dict[str, str] = {}
    readiness_classifications: set[str] = set()
    for item in raw["readinessPrerequisites"]:
        classification = classifications.get(item["classificationRef"])
        if classification is None or classification["category"] != "READINESS_PREREQUISITE":
            raise NormalizationError("readiness item has the wrong classification")
        if item["classificationRef"] in readiness_classifications:
            raise NormalizationError("readiness classification appears twice")
        readiness_classifications.add(item["classificationRef"])
        if set(item["evidenceRefs"]) != set(classification["evidenceRefs"]):
            raise NormalizationError("readiness evidence differs from triage")
        if item["owner"] != classification["suggestedOwner"]:
            raise NormalizationError("readiness owner differs from triage")
        if any(evidence_by_id[ref]["kind"] == "human_decision" for ref in item["evidenceRefs"]):
            if effort_numbers(item["engineeringEffort"]) != (0, 0):
                raise NormalizationError("pending approval cannot create engineering effort")
        value = {
            "classificationRef": item["classificationRef"],
            "originCategory": "READINESS_PREREQUISITE",
            "summary": item["summary"],
            "owner": item["owner"],
            "status": item["status"],
            "evidenceRefs": sorted(set(item["evidenceRefs"])),
            "engineeringEffort": copy.deepcopy(item["engineeringEffort"]),
            "calendarImpact": copy.deepcopy(item["calendarImpact"]),
        }
        readiness_id = stable_id("readiness", value)
        if readiness_id in readiness_map.values():
            raise NormalizationError("duplicate semantic readiness identity")
        readiness_map[item["id"]] = readiness_id
        readiness.append({"id": readiness_id, **value})
    if readiness_classifications != categories.get("READINESS_PREREQUISITE", set()):
        raise NormalizationError("readiness does not exactly cover triage")
    readiness.sort(key=lambda item: item["id"])
    readiness_by_id = {item["id"]: item for item in readiness}

    old_ids(raw["relatedFindings"], "related findings")
    related_findings: list[dict[str, Any]] = []
    related_classifications: set[str] = set()
    related_categories = {"RELATED_DEFECT", "RISK_ONLY", "OPTIONAL_IMPROVEMENT"}
    for item in raw["relatedFindings"]:
        classification = classifications.get(item["classificationRef"])
        if classification is None or classification["category"] not in related_categories:
            raise NormalizationError("related finding has the wrong classification")
        if item["classificationRef"] in related_classifications:
            raise NormalizationError("related classification appears twice")
        related_classifications.add(item["classificationRef"])
        if item["originCategory"] != classification["category"]:
            raise NormalizationError("related finding category differs from triage")
        if set(item["evidenceRefs"]) != set(classification["evidenceRefs"]):
            raise NormalizationError("related finding evidence differs from triage")
        if item["owner"] != classification["suggestedOwner"]:
            raise NormalizationError("related finding owner differs from triage")
        value = {
            "classificationRef": item["classificationRef"],
            "originCategory": item["originCategory"],
            "summary": item["summary"],
            "evidenceRefs": sorted(set(item["evidenceRefs"])),
            "owner": item["owner"],
            "followUp": item["followUp"],
            "excludedFromBasePlan": True,
        }
        related_findings.append({"id": stable_id("related", value), **value})
    expected_related = set().union(
        *(categories.get(category, set()) for category in related_categories)
    )
    if related_classifications != expected_related:
        raise NormalizationError("related findings do not exactly cover excluded triage categories")
    related_findings.sort(key=lambda item: item["id"])

    old_ids(raw["conditionalBranches"], "conditional branches")
    provisional_branches: list[dict[str, Any]] = []
    branch_map: dict[str, str] = {}
    branch_pairs: set[tuple[str, str]] = set()
    for item in raw["conditionalBranches"]:
        classification = classifications.get(item["classificationRef"])
        if classification is None or classification["category"] != "CONDITIONAL_SCOPE":
            raise NormalizationError("branch does not reference CONDITIONAL_SCOPE")
        decision_ref = classification["decisionRef"]
        if item["decisionRef"] != decision_ref:
            raise NormalizationError("branch decision differs from triage")
        if item["decisionOptionRef"] not in option_ids_by_decision[decision_ref]:
            raise NormalizationError("branch option does not belong to its decision")
        pair = (item["classificationRef"], item["decisionOptionRef"])
        if pair in branch_pairs:
            raise NormalizationError("classification option appears in more than one branch")
        branch_pairs.add(pair)
        group = triage_groups[decision_ref]
        if item["relationship"] != group["relationship"]:
            raise NormalizationError("branch relationship differs from triage")
        tasks = [
            planned_task(
                task,
                set(classification["evidenceRefs"]) | verified_evidence,
                set(classification["evidenceRefs"]),
            )
            for task in item["tasks"]
        ]
        tasks.sort(key=lambda task: task["id"])
        identity = {
            "classificationRef": item["classificationRef"],
            "originCategory": "CONDITIONAL_SCOPE",
            "decisionRef": decision_ref,
            "decisionOptionRef": item["decisionOptionRef"],
            "condition": item["condition"],
            "relationship": item["relationship"],
            "tasks": tasks,
            "effort": copy.deepcopy(item["effort"]),
        }
        branch_id = stable_id("branch", identity)
        if branch_id in branch_map.values():
            raise NormalizationError("duplicate semantic branch identity")
        branch_map[item["id"]] = branch_id
        provisional_branches.append(
            {"id": branch_id, "providerGroupRef": item["groupRef"], **identity}
        )
    expected_pairs = {
        (classification["id"], option_ref)
        for classification in triage["classifications"]
        if classification["category"] == "CONDITIONAL_SCOPE"
        for option_ref in option_ids_by_decision[classification["decisionRef"]]
    }
    if branch_pairs != expected_pairs:
        raise NormalizationError("conditional branches do not cover every decision option")

    old_ids(raw["branchGroups"], "branch groups")
    branch_groups: list[dict[str, Any]] = []
    branch_group_map: dict[str, str] = {}
    grouped_decisions: set[str] = set()
    for item in raw["branchGroups"]:
        decision_ref = item["decisionRef"]
        if decision_ref in grouped_decisions or decision_ref not in triage_groups:
            raise NormalizationError("invalid or duplicate branch-group decision")
        grouped_decisions.add(decision_ref)
        triage_group = triage_groups[decision_ref]
        if (
            item["relationship"] != triage_group["relationship"]
            or item["selectionRule"] != triage_group["selectionRule"]
        ):
            raise NormalizationError("branch group semantics differ from triage")
        try:
            branch_refs = sorted({branch_map[ref] for ref in item["branchRefs"]})
        except KeyError as exc:
            raise NormalizationError("branch group references an unknown branch") from exc
        expected_refs = {
            branch["id"]
            for branch in provisional_branches
            if branch["decisionRef"] == decision_ref
        }
        if set(branch_refs) != expected_refs:
            raise NormalizationError("branch group does not exactly cover its decision")
        value = {
            "decisionRef": decision_ref,
            "relationship": item["relationship"],
            "selectionRule": item["selectionRule"],
            "branchRefs": branch_refs,
        }
        group_id = stable_id("branchgroup", value)
        branch_group_map[item["id"]] = group_id
        branch_groups.append({"id": group_id, **value})
    conditional_decisions = {
        item["decisionRef"]
        for item in triage["classifications"]
        if item["category"] == "CONDITIONAL_SCOPE"
    }
    if grouped_decisions != conditional_decisions:
        raise NormalizationError("branch groups do not cover conditional decisions")
    branch_groups.sort(key=lambda item: item["id"])
    groups_by_id = {item["id"]: item for item in branch_groups}

    conditional_branches: list[dict[str, Any]] = []
    for item in provisional_branches:
        try:
            group_ref = branch_group_map[item.pop("providerGroupRef")]
        except KeyError as exc:
            raise NormalizationError("branch references an unknown group") from exc
        if groups_by_id[group_ref]["decisionRef"] != item["decisionRef"]:
            raise NormalizationError("branch references a group for another decision")
        conditional_branches.append({**item, "groupRef": group_ref})
    conditional_branches.sort(key=lambda item: item["id"])
    branches_by_id = {item["id"]: item for item in conditional_branches}

    approved_triage_expansions = {
        item["id"]: item
        for item in triage["scopeExpansions"]
        if item["status"] == "approved"
    }
    approved_scope_expansions: list[dict[str, Any]] = []
    seen_expansions: set[str] = set()
    for item in raw["approvedScopeExpansions"]:
        expansion = approved_triage_expansions.get(item["scopeExpansionRef"])
        if expansion is None or item["scopeExpansionRef"] in seen_expansions:
            raise NormalizationError("invalid or duplicate approved scope expansion")
        seen_expansions.add(item["scopeExpansionRef"])
        if item["originalClassificationRef"] != expansion["originalClassificationRef"]:
            raise NormalizationError("scope expansion classification differs from triage")
        classification = classifications[item["originalClassificationRef"]]
        tasks = [
            planned_task(
                task,
                set(classification["evidenceRefs"]) | verified_evidence,
                set(classification["evidenceRefs"]),
            )
            for task in item["tasks"]
        ]
        tasks.sort(key=lambda task: task["id"])
        approved_scope_expansions.append(
            {
                "scopeExpansionRef": item["scopeExpansionRef"],
                "originalClassificationRef": item["originalClassificationRef"],
                "title": item["title"],
                "tasks": tasks,
                "effort": copy.deepcopy(item["effort"]),
            }
        )
    if seen_expansions != set(approved_triage_expansions):
        raise NormalizationError("approved expansions do not exactly cover triage")
    approved_scope_expansions.sort(key=lambda item: item["scopeExpansionRef"])
    expansions_by_id = {
        item["scopeExpansionRef"]: item for item in approved_scope_expansions
    }

    estimate_set = raw["scenarioEstimates"]
    base_efforts = [item["effort"] for item in base_plan]
    require_effort_sum(
        estimate_set["baseEffort"], base_efforts, "base_effort", "base effort"
    )
    required_deltas: list[dict[str, Any]] = []
    seen_enablers: set[str] = set()
    for delta in estimate_set["requiredEnablerDeltas"]:
        try:
            enabler_ref = enabler_map[delta["enablerRef"]]
        except KeyError as exc:
            raise NormalizationError("estimate references an unknown enabler") from exc
        if enabler_ref in seen_enablers:
            raise NormalizationError("duplicate required-enabler delta")
        seen_enablers.add(enabler_ref)
        if canonical(delta["effort"]) != canonical(enablers_by_id[enabler_ref]["effort"]):
            raise NormalizationError("required-enabler delta differs from enabler effort")
        required_deltas.append(
            {"enablerRef": enabler_ref, "effort": copy.deepcopy(delta["effort"])}
        )
    if seen_enablers != set(enablers_by_id):
        raise NormalizationError("estimate set omits a required enabler")
    required_deltas.sort(key=lambda item: item["enablerRef"])

    open_material_decisions = {
        item["id"]
        for item in decisions
        if item["status"] == "open" and item["materiality"] == "material"
    }
    if set(estimate_set["openMaterialDecisionRefs"]) != open_material_decisions:
        raise NormalizationError("open material decision refs differ from decision register")
    if open_material_decisions and estimate_set["finalCommittedEstimate"] is not None:
        raise NormalizationError("open material decisions forbid a committed estimate")

    scenarios: list[dict[str, Any]] = []
    selected_across_scenarios: set[str] = set()
    old_ids(estimate_set["scenarios"], "scenarios")
    for scenario in estimate_set["scenarios"]:
        try:
            selected_refs = sorted({branch_map[ref] for ref in scenario["selectedBranchRefs"]})
        except KeyError as exc:
            raise NormalizationError("scenario selects an unknown branch") from exc
        selected_across_scenarios.update(selected_refs)
        if effort_numbers(scenario["baseEffort"]) != effort_numbers(estimate_set["baseEffort"]):
            raise NormalizationError("scenario base effort differs from estimate set")

        mandatory_deltas: list[dict[str, Any]] = []
        mandatory_refs: set[str] = set()
        for delta in scenario["mandatoryDeltas"]:
            try:
                enabler_ref = enabler_map[delta["enablerRef"]]
            except KeyError as exc:
                raise NormalizationError("scenario references an unknown enabler") from exc
            if enabler_ref in mandatory_refs:
                raise NormalizationError("scenario duplicates an enabler delta")
            mandatory_refs.add(enabler_ref)
            if canonical(delta["effort"]) != canonical(enablers_by_id[enabler_ref]["effort"]):
                raise NormalizationError("scenario enabler delta differs from plan")
            mandatory_deltas.append(
                {"enablerRef": enabler_ref, "effort": copy.deepcopy(delta["effort"])}
            )
        if mandatory_refs != set(enablers_by_id):
            raise NormalizationError("scenario omits a mandatory enabler")
        mandatory_deltas.sort(key=lambda item: item["enablerRef"])

        conditional_deltas: list[dict[str, Any]] = []
        conditional_refs: set[str] = set()
        for delta in scenario["conditionalDeltas"]:
            try:
                branch_ref = branch_map[delta["branchRef"]]
            except KeyError as exc:
                raise NormalizationError("scenario references an unknown branch delta") from exc
            if branch_ref in conditional_refs:
                raise NormalizationError("scenario duplicates a branch delta")
            conditional_refs.add(branch_ref)
            if canonical(delta["effort"]) != canonical(branches_by_id[branch_ref]["effort"]):
                raise NormalizationError("scenario branch delta differs from plan")
            conditional_deltas.append(
                {"branchRef": branch_ref, "effort": copy.deepcopy(delta["effort"])}
            )
        if conditional_refs != set(selected_refs):
            raise NormalizationError("selected branches and conditional deltas differ")
        conditional_deltas.sort(key=lambda item: item["branchRef"])

        approved_deltas: list[dict[str, Any]] = []
        approved_refs: set[str] = set()
        for delta in scenario["approvedScopeDeltas"]:
            expansion_ref = delta["scopeExpansionRef"]
            if expansion_ref not in expansions_by_id or expansion_ref in approved_refs:
                raise NormalizationError("scenario has an invalid scope-expansion delta")
            approved_refs.add(expansion_ref)
            if canonical(delta["effort"]) != canonical(expansions_by_id[expansion_ref]["effort"]):
                raise NormalizationError("scenario expansion delta differs from plan")
            approved_deltas.append(copy.deepcopy(delta))
        if approved_refs != set(expansions_by_id):
            raise NormalizationError("scenario omits an approved scope expansion")
        approved_deltas.sort(key=lambda item: item["scopeExpansionRef"])

        calendar_impacts: list[dict[str, Any]] = []
        calendar_refs: set[str] = set()
        for contribution in scenario["calendarImpacts"]:
            try:
                readiness_ref = readiness_map[contribution["readinessRef"]]
            except KeyError as exc:
                raise NormalizationError("scenario references unknown readiness") from exc
            if readiness_ref in calendar_refs:
                raise NormalizationError("scenario duplicates readiness calendar impact")
            calendar_refs.add(readiness_ref)
            if canonical(contribution["impact"]) != canonical(
                readiness_by_id[readiness_ref]["calendarImpact"]
            ):
                raise NormalizationError("scenario calendar impact differs from readiness")
            calendar_impacts.append(
                {"readinessRef": readiness_ref, "impact": copy.deepcopy(contribution["impact"])}
            )
        if calendar_refs != set(readiness_by_id):
            raise NormalizationError("scenario omits readiness calendar impact")
        calendar_impacts.sort(key=lambda item: item["readinessRef"])

        for group in branch_groups:
            selected_in_group = set(selected_refs) & set(group["branchRefs"])
            if group["selectionRule"] == "exactly_one" and len(selected_in_group) != 1:
                raise NormalizationError("scenario violates an exactly-one branch group")
            if group["selectionRule"] == "zero_or_one" and len(selected_in_group) > 1:
                raise NormalizationError("scenario violates a zero-or-one branch group")
            if group["selectionRule"] == "all_applicable" and selected_in_group != set(
                group["branchRefs"]
            ):
                raise NormalizationError("scenario omits a combinable branch")

        total_components = (
            [scenario["baseEffort"]]
            + [item["effort"] for item in mandatory_deltas]
            + [item["effort"] for item in conditional_deltas]
            + [item["effort"] for item in approved_deltas]
        )
        require_effort_sum(
            scenario["engineeringTotal"],
            total_components,
            "scenario_total",
            f"scenario {scenario['name']!r} total",
        )
        if open_material_decisions and scenario["finality"] != "scenario_only":
            raise NormalizationError("open decisions require scenario-only estimates")
        value = {
            "name": scenario["name"],
            "selectedBranchRefs": selected_refs,
            "baseEffort": copy.deepcopy(scenario["baseEffort"]),
            "mandatoryDeltas": mandatory_deltas,
            "conditionalDeltas": conditional_deltas,
            "approvedScopeDeltas": approved_deltas,
            "engineeringTotal": copy.deepcopy(scenario["engineeringTotal"]),
            "calendarImpacts": calendar_impacts,
            "finality": scenario["finality"],
        }
        scenarios.append({"id": stable_id("scenario", value), **value})
    if selected_across_scenarios != set(branches_by_id):
        raise NormalizationError("scenario set does not represent every conditional branch")
    scenarios.sort(key=lambda item: item["id"])

    scenario_estimates = {
        "baseEffort": copy.deepcopy(estimate_set["baseEffort"]),
        "requiredEnablerDeltas": required_deltas,
        "openMaterialDecisionRefs": sorted(open_material_decisions),
        "scenarios": scenarios,
        "finalCommittedEstimate": copy.deepcopy(estimate_set["finalCommittedEstimate"]),
    }

    required_evidence: set[str] = set()
    required_provenance: set[str] = set()
    for task in base_plan:
        required_evidence.update(task["evidenceRefs"] + task["testEvidenceRefs"])
        required_provenance.update(task["provenanceRefs"])
    for container in required_enablers + conditional_branches:
        if "evidenceRefs" in container:
            required_evidence.update(container["evidenceRefs"])
        for task in container["tasks"]:
            required_evidence.update(task["evidenceRefs"] + task["testEvidenceRefs"])
            required_provenance.update(task["provenanceRefs"])
    for item in approved_scope_expansions:
        for task in item["tasks"]:
            required_evidence.update(task["evidenceRefs"] + task["testEvidenceRefs"])
            required_provenance.update(task["provenanceRefs"])
    for item in readiness + related_findings + decisions:
        required_evidence.update(item["evidenceRefs"])
    required_provenance.update(
        ref
        for evidence_ref in required_evidence
        for ref in evidence_by_id[evidence_ref]["provenanceRefs"]
    )
    evidence_section = raw["evidenceAndProvenance"]
    if set(evidence_section["evidenceRefs"]) != required_evidence:
        raise NormalizationError("evidence section does not exactly cover the plan")
    if set(evidence_section["provenanceRefs"]) != required_provenance:
        raise NormalizationError("provenance section does not exactly cover the plan")

    validation_status = copy.deepcopy(raw["validationStatus"])
    validation_status["violationCodes"] = sorted(set(validation_status["violationCodes"]))
    if open_material_decisions:
        if (
            validation_status["semanticValidation"] != "needs_owner_review"
            or validation_status["ownerReview"]["state"] not in {"required", "in_progress"}
            or "OPEN_MATERIAL_DECISIONS" not in validation_status["violationCodes"]
        ):
            raise NormalizationError("open material decisions require explicit owner review")

    result = {
        "schemaVersion": raw["schemaVersion"],
        "artifactVersion": raw["artifactVersion"],
        "artifactId": raw["artifactId"],
        "storyId": raw["storyId"],
        "sourceTriageArtifactRef": raw["sourceTriageArtifactRef"],
        "readinessPrerequisites": readiness,
        "basePlan": base_plan,
        "requiredEnablers": required_enablers,
        "conditionalBranches": conditional_branches,
        "branchGroups": branch_groups,
        "approvedScopeExpansions": approved_scope_expansions,
        "scenarioEstimates": scenario_estimates,
        "decisionRegister": decisions,
        "relatedFindings": related_findings,
        "evidenceAndProvenance": {
            "evidenceRefs": sorted(required_evidence),
            "provenanceRefs": sorted(required_provenance),
        },
        "validationStatus": validation_status,
    }
    artifact_identity = {
        key: value
        for key, value in result.items()
        if key not in {"artifactId", "validationStatus"}
    }
    result["artifactId"] = stable_id("plan", artifact_identity)
    return result


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 5 and argv[1] == "normalize-discovery":
            schema_path, input_path, output_path = map(Path, argv[2:])
            with input_path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
            validate(schema_path.resolve(), raw)
            normalized = normalize_discovery(raw)
            validate(schema_path.resolve(), normalized)
        elif len(argv) == 6 and argv[1] == "normalize-triage":
            schema_path, discovery_path, input_path, output_path = map(Path, argv[2:])
            with input_path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
            validate(schema_path.resolve(), raw)
            with discovery_path.open(encoding="utf-8") as handle:
                discovery = json.load(handle)
            discovery_schema = REPOSITORY_ROOT / "contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json"
            validate(discovery_schema, discovery)
            normalized = normalize_triage(raw, discovery)
            validate(schema_path.resolve(), normalized)
        elif len(argv) == 5 and argv[1] == "build-planning-context":
            discovery_path, triage_path, output_path = map(Path, argv[2:])
            with discovery_path.open(encoding="utf-8") as handle:
                discovery = json.load(handle)
            with triage_path.open(encoding="utf-8") as handle:
                triage = json.load(handle)
            contract_root = REPOSITORY_ROOT / "contracts/story-start/scope-v2/schemas"
            validate(contract_root / "discovery-inventory.schema.json", discovery)
            validate(contract_root / "scope-triage.schema.json", triage)
            normalized = build_planning_context(discovery, triage)
            validate_planning_context(normalized, triage)
        elif len(argv) == 4 and argv[1] == "validate-planning-context":
            context_path, triage_path = map(Path, argv[2:])
            with context_path.open(encoding="utf-8") as handle:
                context = json.load(handle)
            with triage_path.open(encoding="utf-8") as handle:
                triage = json.load(handle)
            triage_schema = REPOSITORY_ROOT / "contracts/story-start/scope-v2/schemas/scope-triage.schema.json"
            validate(triage_schema, triage)
            validate_planning_context(context, triage)
            return 0
        elif len(argv) == 7 and argv[1] == "normalize-plan":
            schema_path, context_path, triage_path, input_path, output_path = map(Path, argv[2:])
            with input_path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
            with context_path.open(encoding="utf-8") as handle:
                context = json.load(handle)
            with triage_path.open(encoding="utf-8") as handle:
                triage = json.load(handle)
            validate(schema_path.resolve(), raw)
            triage_schema = REPOSITORY_ROOT / "contracts/story-start/scope-v2/schemas/scope-triage.schema.json"
            validate(triage_schema, triage)
            normalized = normalize_plan(raw, context, triage)
            validate(schema_path.resolve(), normalized)
        else:
            print(
                "Usage: story-start-scope-v2-normalize.py normalize-discovery <schema> <input> <output>\n"
                "   or: story-start-scope-v2-normalize.py normalize-triage <schema> <discovery> <input> <output>\n"
                "   or: story-start-scope-v2-normalize.py build-planning-context <discovery> <triage> <output>\n"
                "   or: story-start-scope-v2-normalize.py validate-planning-context <context> <triage>\n"
                "   or: story-start-scope-v2-normalize.py normalize-plan <schema> <context> <triage> <input> <output>",
                file=sys.stderr,
            )
            return 2
        output_path.write_text(canonical(normalized) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, NormalizationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
