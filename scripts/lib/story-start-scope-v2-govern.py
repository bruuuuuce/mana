#!/usr/bin/env python3
"""Pure cross-artifact semantic governor for Story Start Scope v2.

The governor reads only the supplied v2 artifacts plus their host-owned JSON
Schemas.  It never inspects a repository, ticket system, workspace, or network.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = REPOSITORY_ROOT / "contracts/story-start/scope-v2/schemas"
sys.path.insert(0, str(REPOSITORY_ROOT / "tests" / "lib"))
from json_schema_subset import SchemaEvaluator  # noqa: E402


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def as_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def string_refs(value: Any) -> list[str]:
    return [item for item in as_list(value) if isinstance(item, str)]


def object_items(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [item for item in as_list(document.get(key)) if isinstance(item, dict)]


def by_id(items: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for item in items
        if isinstance(item.get("id"), str)
    }


def effort_pair(value: Any) -> tuple[float, float] | None:
    value = as_object(value)
    minimum = value.get("minimumPersonHours")
    additional = value.get("additionalPersonHours")
    if (
        isinstance(minimum, (int, float))
        and not isinstance(minimum, bool)
        and isinstance(additional, (int, float))
        and not isinstance(additional, bool)
    ):
        return float(minimum), float(additional)
    return None


def normalized_decisions(items: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for value in as_list(items):
        if not isinstance(value, dict):
            continue
        item = copy.deepcopy(value)
        item["options"] = sorted(
            [entry for entry in as_list(item.get("options")) if isinstance(entry, dict)],
            key=lambda entry: str(entry.get("id", "")),
        )
        item["evidenceRefs"] = sorted(set(string_refs(item.get("evidenceRefs"))))
        result.append(item)
    return sorted(result, key=lambda item: str(item.get("id", "")))


def report_sort_key(item: dict[str, Any]) -> tuple[str, ...]:
    return (
        item["code"],
        item["kind"],
        item["artifact"],
        item["path"],
        item["entityId"] or "",
        canonical(item["relatedRefs"]),
        item["message"],
    )


def sorted_violations(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {canonical(item): item for item in values}
    return sorted(unique.values(), key=report_sort_key)


class ScopeGovernor:
    def __init__(
        self,
        discovery: dict[str, Any],
        triage: dict[str, Any],
        plan: dict[str, Any],
        parse_errors: dict[str, str] | None = None,
    ) -> None:
        self.discovery = discovery
        self.triage = triage
        self.plan = plan
        self.parse_errors = parse_errors or {}
        self.violations: list[dict[str, Any]] = []
        self.schema_state = {
            "discovery": "valid",
            "triage": "valid",
            "implementationPlan": "valid",
        }

        self.acceptance = by_id(object_items(discovery, "acceptanceCriteria"))
        self.constraints = by_id(object_items(discovery, "mandatoryConstraints"))
        self.evidence = by_id(object_items(discovery, "evidence"))
        self.findings = by_id(object_items(discovery, "findings"))
        self.provenance = by_id(object_items(discovery, "provenance"))
        self.discovery_decisions = by_id(object_items(discovery, "decisions"))
        self.classifications = by_id(object_items(triage, "classifications"))
        self.triage_decisions = by_id(object_items(triage, "decisions"))
        self.option_groups = by_id(object_items(triage, "optionGroups"))
        self.scope_expansions = by_id(object_items(triage, "scopeExpansions"))
        self.plan_decisions = by_id(object_items(plan, "decisionRegister"))
        self.base_tasks = object_items(plan, "basePlan")
        self.enablers = by_id(object_items(plan, "requiredEnablers"))
        self.branches = by_id(object_items(plan, "conditionalBranches"))
        self.branch_groups = by_id(object_items(plan, "branchGroups"))
        self.readiness = by_id(object_items(plan, "readinessPrerequisites"))
        self.related = by_id(object_items(plan, "relatedFindings"))
        self.approved_expansions = {
            item.get("scopeExpansionRef"): item
            for item in object_items(plan, "approvedScopeExpansions")
            if isinstance(item.get("scopeExpansionRef"), str)
        }

        self.entity_types: dict[str, set[str]] = {}
        for entity_type, index in (
            ("acceptance_criterion", self.acceptance),
            ("mandatory_constraint", self.constraints),
            ("evidence", self.evidence),
            ("finding", self.findings),
            ("provenance", self.provenance),
            ("classification", self.classifications),
            ("decision", self.triage_decisions),
            ("option_group", self.option_groups),
            ("scope_expansion", self.scope_expansions),
            ("enabler", self.enablers),
            ("branch", self.branches),
            ("branch_group", self.branch_groups),
            ("readiness", self.readiness),
            ("related_finding", self.related),
        ):
            for identifier in index:
                self.entity_types.setdefault(identifier, set()).add(entity_type)
        for decision in self.triage_decisions.values():
            for option in object_items(decision, "options"):
                identifier = option.get("id")
                if isinstance(identifier, str):
                    self.entity_types.setdefault(identifier, set()).add("decision_option")
        for task, _ in self.all_tasks():
            identifier = task.get("id")
            if isinstance(identifier, str):
                self.entity_types.setdefault(identifier, set()).add("task")

    def add(
        self,
        code: str,
        artifact: str,
        path: str,
        message: str,
        *,
        kind: str = "semantic",
        entity_id: Any = None,
        related_refs: Iterable[str] = (),
    ) -> None:
        self.violations.append(
            {
                "code": code,
                "kind": kind,
                "artifact": artifact,
                "path": path,
                "entityId": entity_id if isinstance(entity_id, str) else None,
                "relatedRefs": sorted(set(related_refs)),
                "message": message[:4000],
            }
        )

    def all_tasks(self) -> list[tuple[dict[str, Any], str]]:
        result = [
            (task, f"/basePlan/{index}")
            for index, task in enumerate(self.base_tasks)
        ]
        for index, enabler in enumerate(object_items(self.plan, "requiredEnablers")):
            result.extend(
                (task, f"/requiredEnablers/{index}/tasks/{task_index}")
                for task_index, task in enumerate(object_items(enabler, "tasks"))
            )
        for index, branch in enumerate(object_items(self.plan, "conditionalBranches")):
            result.extend(
                (task, f"/conditionalBranches/{index}/tasks/{task_index}")
                for task_index, task in enumerate(object_items(branch, "tasks"))
            )
        for index, expansion in enumerate(object_items(self.plan, "approvedScopeExpansions")):
            result.extend(
                (task, f"/approvedScopeExpansions/{index}/tasks/{task_index}")
                for task_index, task in enumerate(object_items(expansion, "tasks"))
            )
        return result

    def schema_checks(self) -> None:
        evaluator = SchemaEvaluator()
        for label, artifact, schema_name, state_key in (
            ("discovery", self.discovery, "discovery-inventory.schema.json", "discovery"),
            ("triage", self.triage, "scope-triage.schema.json", "triage"),
            ("implementation_plan", self.plan, "implementation-plan.schema.json", "implementationPlan"),
        ):
            parse_error = self.parse_errors.get(label)
            if parse_error:
                self.schema_state[state_key] = "invalid"
                self.add(
                    "STRUCTURAL_JSON_INVALID",
                    label,
                    "",
                    parse_error,
                    kind="structural",
                )
                continue
            schema_path = SCHEMA_ROOT / schema_name
            schema = evaluator.load(schema_path)
            errors = evaluator.evaluate(artifact, schema, schema_path)
            if errors:
                self.schema_state[state_key] = "invalid"
                self.add(
                    "STRUCTURAL_SCHEMA_INVALID",
                    label,
                    "",
                    "; ".join(errors[:8]),
                    kind="structural",
                )

    def duplicate_ids(self) -> None:
        collections: list[tuple[str, str, list[dict[str, Any]]]] = [
            ("discovery", "/acceptanceCriteria", object_items(self.discovery, "acceptanceCriteria")),
            ("discovery", "/mandatoryConstraints", object_items(self.discovery, "mandatoryConstraints")),
            ("discovery", "/evidence", object_items(self.discovery, "evidence")),
            ("discovery", "/findings", object_items(self.discovery, "findings")),
            ("discovery", "/decisions", object_items(self.discovery, "decisions")),
            ("discovery", "/openQuestions", object_items(self.discovery, "openQuestions")),
            ("discovery", "/provenance", object_items(self.discovery, "provenance")),
            ("triage", "/classifications", object_items(self.triage, "classifications")),
            ("triage", "/decisions", object_items(self.triage, "decisions")),
            ("triage", "/optionGroups", object_items(self.triage, "optionGroups")),
            ("triage", "/scopeExpansions", object_items(self.triage, "scopeExpansions")),
            ("implementation_plan", "/basePlan", self.base_tasks),
            ("implementation_plan", "/requiredEnablers", object_items(self.plan, "requiredEnablers")),
            ("implementation_plan", "/conditionalBranches", object_items(self.plan, "conditionalBranches")),
            ("implementation_plan", "/branchGroups", object_items(self.plan, "branchGroups")),
            ("implementation_plan", "/readinessPrerequisites", object_items(self.plan, "readinessPrerequisites")),
            ("implementation_plan", "/relatedFindings", object_items(self.plan, "relatedFindings")),
        ]
        for artifact, path, items in collections:
            counts = Counter(item.get("id") for item in items if isinstance(item.get("id"), str))
            for identifier in sorted(value for value, count in counts.items() if count > 1):
                self.add(
                    "DUPLICATE_ID",
                    artifact,
                    path,
                    "Entity IDs must be unique within their collection.",
                    entity_id=identifier,
                )
        task_counts = Counter(
            task.get("id")
            for task, _ in self.all_tasks()
            if isinstance(task.get("id"), str)
        )
        for identifier in sorted(value for value, count in task_counts.items() if count > 1):
            self.add(
                "DUPLICATE_TASK_ID",
                "implementation_plan",
                "",
                "Task IDs must be unique across every plan section.",
                entity_id=identifier,
            )
        for decision, decision_path, artifact in (
            *(
                (item, f"/decisions/{index}", "discovery")
                for index, item in enumerate(object_items(self.discovery, "decisions"))
            ),
            *(
                (item, f"/decisions/{index}", "triage")
                for index, item in enumerate(object_items(self.triage, "decisions"))
            ),
            *(
                (item, f"/decisionRegister/{index}", "implementation_plan")
                for index, item in enumerate(object_items(self.plan, "decisionRegister"))
            ),
        ):
            counts = Counter(
                option.get("id")
                for option in object_items(decision, "options")
                if isinstance(option.get("id"), str)
            )
            for identifier in sorted(value for value, count in counts.items() if count > 1):
                self.add(
                    "DUPLICATE_ID",
                    artifact,
                    f"{decision_path}/options",
                    "Decision option IDs must be unique within the decision.",
                    entity_id=identifier,
                )

    def require_ref(
        self,
        ref: Any,
        expected: dict[str, Any] | set[str],
        code: str,
        artifact: str,
        path: str,
        entity_id: Any,
        expected_type: str,
    ) -> bool:
        if not isinstance(ref, str):
            self.add(code, artifact, path, f"A {expected_type} reference is required.", entity_id=entity_id)
            return False
        if ref in expected:
            return True
        actual_types = self.entity_types.get(ref, set())
        if actual_types:
            self.add(
                "REFERENCE_ENTITY_TYPE_MISMATCH",
                artifact,
                path,
                f"Reference resolves to {sorted(actual_types)}, not {expected_type}.",
                entity_id=entity_id,
                related_refs=[ref],
            )
        else:
            self.add(
                code,
                artifact,
                path,
                f"Referenced {expected_type} does not exist.",
                entity_id=entity_id,
                related_refs=[ref],
            )
        return False

    def check_ref_list(
        self,
        refs: Any,
        expected: dict[str, Any] | set[str],
        code: str,
        artifact: str,
        path: str,
        entity_id: Any,
        expected_type: str,
    ) -> None:
        for index, ref in enumerate(as_list(refs)):
            self.require_ref(
                ref,
                expected,
                code,
                artifact,
                f"{path}/{index}",
                entity_id,
                expected_type,
            )

    def artifact_links_and_references(self) -> None:
        story_ids = {
            value
            for value in (
                self.discovery.get("storyId"),
                self.triage.get("storyId"),
                self.plan.get("storyId"),
            )
            if isinstance(value, str)
        }
        if len(story_ids) != 1:
            self.add(
                "ARTIFACT_STORY_MISMATCH",
                "artifact_set",
                "",
                "Discovery, triage, and plan must reference one story ID.",
                related_refs=story_ids,
            )
        if self.triage.get("sourceDiscoveryArtifactRef") != self.discovery.get("artifactId"):
            self.add(
                "TRIAGE_DISCOVERY_REF_MISMATCH",
                "triage",
                "/sourceDiscoveryArtifactRef",
                "Triage must reference the supplied Discovery artifact.",
            )
        if self.plan.get("sourceTriageArtifactRef") != self.triage.get("artifactId"):
            self.add(
                "PLAN_TRIAGE_REF_MISMATCH",
                "implementation_plan",
                "/sourceTriageArtifactRef",
                "Plan must reference the supplied Scope Triage artifact.",
            )

        for index, criterion in enumerate(object_items(self.discovery, "acceptanceCriteria")):
            self.check_ref_list(criterion.get("provenanceRefs"), self.provenance, "REFERENCE_PROVENANCE_NOT_FOUND", "discovery", f"/acceptanceCriteria/{index}/provenanceRefs", criterion.get("id"), "provenance")
        for index, evidence in enumerate(object_items(self.discovery, "evidence")):
            self.check_ref_list(evidence.get("provenanceRefs"), self.provenance, "REFERENCE_PROVENANCE_NOT_FOUND", "discovery", f"/evidence/{index}/provenanceRefs", evidence.get("id"), "provenance")
        for index, constraint in enumerate(object_items(self.discovery, "mandatoryConstraints")):
            self.check_ref_list(constraint.get("evidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "discovery", f"/mandatoryConstraints/{index}/evidenceRefs", constraint.get("id"), "evidence")
        for index, finding in enumerate(object_items(self.discovery, "findings")):
            base = f"/findings/{index}"
            self.check_ref_list(finding.get("evidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "discovery", f"{base}/evidenceRefs", finding.get("id"), "evidence")
            self.check_ref_list(finding.get("acceptanceCriterionRefs"), self.acceptance, "REFERENCE_AC_NOT_FOUND", "discovery", f"{base}/acceptanceCriterionRefs", finding.get("id"), "acceptance criterion")
            self.check_ref_list(finding.get("mandatoryConstraintRefs"), self.constraints, "REFERENCE_CONSTRAINT_NOT_FOUND", "discovery", f"{base}/mandatoryConstraintRefs", finding.get("id"), "mandatory constraint")
            self.check_ref_list(finding.get("decisionRefs"), self.discovery_decisions, "REFERENCE_DECISION_NOT_FOUND", "discovery", f"{base}/decisionRefs", finding.get("id"), "decision")
        for index, question in enumerate(object_items(self.discovery, "openQuestions")):
            base = f"/openQuestions/{index}"
            self.check_ref_list(question.get("evidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "discovery", f"{base}/evidenceRefs", question.get("id"), "evidence")
            self.check_ref_list(question.get("acceptanceCriterionRefs"), self.acceptance, "REFERENCE_AC_NOT_FOUND", "discovery", f"{base}/acceptanceCriterionRefs", question.get("id"), "acceptance criterion")
        for index, decision in enumerate(object_items(self.discovery, "decisions")):
            self.check_ref_list(decision.get("evidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "discovery", f"/decisions/{index}/evidenceRefs", decision.get("id"), "evidence")

        for index, classification in enumerate(object_items(self.triage, "classifications")):
            base = f"/classifications/{index}"
            entity_id = classification.get("id")
            self.require_ref(classification.get("findingRef"), self.findings, "REFERENCE_FINDING_NOT_FOUND", "triage", f"{base}/findingRef", entity_id, "finding")
            self.check_ref_list(classification.get("evidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "triage", f"{base}/evidenceRefs", entity_id, "evidence")
            self.check_ref_list(classification.get("acceptanceCriterionRefs"), self.acceptance, "REFERENCE_AC_NOT_FOUND", "triage", f"{base}/acceptanceCriterionRefs", entity_id, "acceptance criterion")
            self.check_ref_list(classification.get("mandatoryConstraintRefs"), self.constraints, "REFERENCE_CONSTRAINT_NOT_FOUND", "triage", f"{base}/mandatoryConstraintRefs", entity_id, "mandatory constraint")
            decision_ref = classification.get("decisionRef")
            if decision_ref is not None:
                self.require_ref(decision_ref, self.triage_decisions, "REFERENCE_DECISION_NOT_FOUND", "triage", f"{base}/decisionRef", entity_id, "decision")
            assessment = as_object(classification.get("promotionAssessment"))
            self.check_ref_list(assessment.get("failingAcceptanceCriterionRefs"), self.acceptance, "REFERENCE_AC_NOT_FOUND", "triage", f"{base}/promotionAssessment/failingAcceptanceCriterionRefs", entity_id, "acceptance criterion")
            self.check_ref_list(assessment.get("failingMandatoryConstraintRefs"), self.constraints, "REFERENCE_CONSTRAINT_NOT_FOUND", "triage", f"{base}/promotionAssessment/failingMandatoryConstraintRefs", entity_id, "mandatory constraint")
            self.check_ref_list(assessment.get("dependencyEvidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "triage", f"{base}/promotionAssessment/dependencyEvidenceRefs", entity_id, "evidence")
        for index, group in enumerate(object_items(self.triage, "optionGroups")):
            base = f"/optionGroups/{index}"
            decision_ref = group.get("decisionRef")
            self.require_ref(decision_ref, self.triage_decisions, "REFERENCE_DECISION_NOT_FOUND", "triage", f"{base}/decisionRef", group.get("id"), "decision")
            options = {
                option.get("id")
                for option in object_items(self.triage_decisions.get(decision_ref, {}), "options")
                if isinstance(option.get("id"), str)
            }
            self.check_ref_list(group.get("optionRefs"), options, "REFERENCE_DECISION_OPTION_NOT_FOUND", "triage", f"{base}/optionRefs", group.get("id"), "decision option")
        for index, expansion in enumerate(object_items(self.triage, "scopeExpansions")):
            base = f"/scopeExpansions/{index}"
            self.require_ref(expansion.get("originalClassificationRef"), self.classifications, "REFERENCE_CLASSIFICATION_NOT_FOUND", "triage", f"{base}/originalClassificationRef", expansion.get("id"), "classification")
            self.require_ref(expansion.get("decisionRef"), self.triage_decisions, "REFERENCE_DECISION_NOT_FOUND", "triage", f"{base}/decisionRef", expansion.get("id"), "decision")
            self.check_ref_list(expansion.get("approvalEvidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "triage", f"{base}/approvalEvidenceRefs", expansion.get("id"), "evidence")

        for task, path in self.all_tasks():
            entity_id = task.get("id")
            self.check_ref_list(task.get("evidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "implementation_plan", f"{path}/evidenceRefs", entity_id, "evidence")
            self.check_ref_list(task.get("testEvidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "implementation_plan", f"{path}/testEvidenceRefs", entity_id, "evidence")
            self.check_ref_list(task.get("provenanceRefs"), self.provenance, "REFERENCE_PROVENANCE_NOT_FOUND", "implementation_plan", f"{path}/provenanceRefs", entity_id, "provenance")
            provenance_sources = {
                self.provenance[ref].get("sourceRef")
                for ref in string_refs(task.get("provenanceRefs"))
                if ref in self.provenance
            }
            for target in string_refs(task.get("sourceTargets")):
                if target not in provenance_sources:
                    self.add("TASK_SOURCE_NOT_PROVENANCE_BACKED", "implementation_plan", f"{path}/sourceTargets", "Task source target is not backed by its direct provenance.", entity_id=entity_id)
        for index, enabler in enumerate(object_items(self.plan, "requiredEnablers")):
            base = f"/requiredEnablers/{index}"
            self.require_ref(enabler.get("classificationRef"), self.classifications, "REFERENCE_CLASSIFICATION_NOT_FOUND", "implementation_plan", f"{base}/classificationRef", enabler.get("id"), "classification")
            self.check_ref_list(enabler.get("evidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "implementation_plan", f"{base}/evidenceRefs", enabler.get("id"), "evidence")
            self.check_ref_list(enabler.get("acceptanceCriterionRefs"), self.acceptance, "REFERENCE_AC_NOT_FOUND", "implementation_plan", f"{base}/acceptanceCriterionRefs", enabler.get("id"), "acceptance criterion")
            self.check_ref_list(enabler.get("mandatoryConstraintRefs"), self.constraints, "REFERENCE_CONSTRAINT_NOT_FOUND", "implementation_plan", f"{base}/mandatoryConstraintRefs", enabler.get("id"), "mandatory constraint")
        for key, collection in (
            ("readinessPrerequisites", object_items(self.plan, "readinessPrerequisites")),
            ("relatedFindings", object_items(self.plan, "relatedFindings")),
        ):
            for index, item in enumerate(collection):
                base = f"/{key}/{index}"
                self.require_ref(item.get("classificationRef"), self.classifications, "REFERENCE_CLASSIFICATION_NOT_FOUND", "implementation_plan", f"{base}/classificationRef", item.get("id"), "classification")
                self.check_ref_list(item.get("evidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "implementation_plan", f"{base}/evidenceRefs", item.get("id"), "evidence")
        for index, expansion in enumerate(object_items(self.plan, "approvedScopeExpansions")):
            base = f"/approvedScopeExpansions/{index}"
            self.require_ref(expansion.get("scopeExpansionRef"), self.scope_expansions, "REFERENCE_SCOPE_EXPANSION_NOT_FOUND", "implementation_plan", f"{base}/scopeExpansionRef", None, "scope expansion")
            self.require_ref(expansion.get("originalClassificationRef"), self.classifications, "REFERENCE_CLASSIFICATION_NOT_FOUND", "implementation_plan", f"{base}/originalClassificationRef", None, "classification")
        evidence_section = as_object(self.plan.get("evidenceAndProvenance"))
        self.check_ref_list(evidence_section.get("evidenceRefs"), self.evidence, "REFERENCE_EVIDENCE_NOT_FOUND", "implementation_plan", "/evidenceAndProvenance/evidenceRefs", None, "evidence")
        self.check_ref_list(evidence_section.get("provenanceRefs"), self.provenance, "REFERENCE_PROVENANCE_NOT_FOUND", "implementation_plan", "/evidenceAndProvenance/provenanceRefs", None, "provenance")

    def decision_legality(self) -> None:
        if canonical(normalized_decisions(self.discovery.get("decisions"))) != canonical(normalized_decisions(self.triage.get("decisions"))) or canonical(normalized_decisions(self.triage.get("decisions"))) != canonical(normalized_decisions(self.plan.get("decisionRegister"))):
            self.add("DECISION_REGISTER_MISMATCH", "artifact_set", "", "Discovery, triage, and plan must preserve the same decision register.")
        for artifact, key, decisions in (
            ("discovery", "decisions", object_items(self.discovery, "decisions")),
            ("triage", "decisions", object_items(self.triage, "decisions")),
            ("implementation_plan", "decisionRegister", object_items(self.plan, "decisionRegister")),
        ):
            for index, decision in enumerate(decisions):
                selected = decision.get("selectedOptionId")
                options = {
                    option.get("id")
                    for option in object_items(decision, "options")
                    if isinstance(option.get("id"), str)
                }
                if decision.get("status") == "open" and selected is not None:
                    self.add("OPEN_DECISION_SELECTED_OPTION", artifact, f"/{key}/{index}/selectedOptionId", "An open decision cannot select a final option.", entity_id=decision.get("id"), related_refs=[selected] if isinstance(selected, str) else [])
                if selected is not None and selected not in options:
                    self.add("DECISION_SELECTED_OPTION_NOT_MEMBER", artifact, f"/{key}/{index}/selectedOptionId", "Selected option does not belong to its decision.", entity_id=decision.get("id"), related_refs=[selected] if isinstance(selected, str) else [])

    def triage_legality(self) -> None:
        seen_findings = Counter(
            item.get("findingRef")
            for item in object_items(self.triage, "classifications")
            if isinstance(item.get("findingRef"), str)
        )
        if set(seen_findings) != set(self.findings) or any(count != 1 for count in seen_findings.values()):
            self.add("TRIAGE_FINDING_COVERAGE_INVALID", "triage", "/classifications", "Every Discovery finding must be classified exactly once.")
        constraint_reason = {
            "security_constraint": "security",
            "compliance_constraint": "compliance",
            "authorization_constraint": "authorization",
            "data_integrity_constraint": "data_integrity",
        }
        for index, classification in enumerate(object_items(self.triage, "classifications")):
            base = f"/classifications/{index}"
            category = classification.get("category")
            finding = self.findings.get(classification.get("findingRef"), {})
            assessment = as_object(classification.get("promotionAssessment"))
            if finding.get("findingKind") == "evidence_gap" and category != "RISK_ONLY":
                self.add("EVIDENCE_GAP_PROMOTED_TO_SCOPE", "triage", f"{base}/category", "An evidence gap cannot be replaced with a scoped architecture.", entity_id=classification.get("id"))
            if category == "REQUIRED_ENABLER":
                if finding.get("findingKind") == "optional_opportunity":
                    self.add("OPTIONAL_AS_REQUIRED_ENABLER", "triage", f"{base}/category", "Optional improvement cannot masquerade as mandatory work.", entity_id=classification.get("id"))
                if not string_refs(classification.get("evidenceRefs")):
                    self.add("ENABLER_EVIDENCE_MISSING", "triage", f"{base}/evidenceRefs", "Required enabler needs evidence.", entity_id=classification.get("id"))
                if not (string_refs(classification.get("acceptanceCriterionRefs")) or string_refs(classification.get("mandatoryConstraintRefs"))):
                    self.add("ENABLER_REQUIREMENT_REF_MISSING", "triage", base, "Required enabler needs an AC or mandatory constraint.", entity_id=classification.get("id"))
                reason = classification.get("mandatoryReason")
                if not isinstance(reason, str):
                    self.add("ENABLER_MANDATORY_REASON_MISSING", "triage", f"{base}/mandatoryReason", "Required enabler needs an explicit mandatory reason.", entity_id=classification.get("id"))
                if reason == "story_regression_prevention" and assessment.get("storyImpact") != "introduces_regression":
                    self.add("ENABLER_CAUSALITY_UNSUPPORTED", "triage", f"{base}/promotionAssessment/storyImpact", "Regression prevention requires introduced-regression evidence.", entity_id=classification.get("id"))
                if reason == "aggravated_defect_remediation" and assessment.get("storyImpact") != "aggravates_pre_existing_issue":
                    self.add("ENABLER_CAUSALITY_UNSUPPORTED", "triage", f"{base}/promotionAssessment/storyImpact", "Aggravated remediation requires aggravation evidence.", entity_id=classification.get("id"))
                if reason == "criterion_dependency" and not string_refs(assessment.get("failingAcceptanceCriterionRefs")):
                    self.add("ENABLER_CAUSALITY_UNSUPPORTED", "triage", f"{base}/promotionAssessment/failingAcceptanceCriterionRefs", "Criterion dependency must identify a failing AC.", entity_id=classification.get("id"))
                if reason in constraint_reason:
                    kinds = {
                        self.constraints[ref].get("kind")
                        for ref in string_refs(assessment.get("failingMandatoryConstraintRefs"))
                        if ref in self.constraints
                    }
                    if constraint_reason[reason] not in kinds:
                        self.add("ENABLER_CAUSALITY_UNSUPPORTED", "triage", f"{base}/promotionAssessment/failingMandatoryConstraintRefs", "Mandatory reason is not backed by a matching constraint.", entity_id=classification.get("id"))
                known_statuses = {
                    self.evidence[ref].get("preExistingStatus")
                    for ref in string_refs(classification.get("evidenceRefs"))
                    if ref in self.evidence and self.evidence[ref].get("preExistingStatus") in {"yes", "no"}
                }
                if len(known_statuses) == 1 and assessment.get("preExistingStatus") not in known_statuses:
                    self.add("ENABLER_PREEXISTING_STATUS_CHANGED", "triage", f"{base}/promotionAssessment/preExistingStatus", "Required enabler must preserve known pre-existing status.", entity_id=classification.get("id"))

    def base_and_enabler_legality(self) -> None:
        base_refs: list[str] = []
        for index, task in enumerate(self.base_tasks):
            path = f"/basePlan/{index}"
            classification_ref = task.get("classificationRef")
            if isinstance(classification_ref, str):
                base_refs.append(classification_ref)
            classification = self.classifications.get(classification_ref)
            if classification is None:
                self.require_ref(classification_ref, self.classifications, "REFERENCE_CLASSIFICATION_NOT_FOUND", "implementation_plan", f"{path}/classificationRef", task.get("id"), "classification")
                continue
            if classification.get("category") != "CORE_SCOPE" or task.get("originCategory") != "CORE_SCOPE":
                self.add("BASE_ORIGIN_NOT_CORE_SCOPE", "implementation_plan", f"{path}/classificationRef", "Base-plan tasks may originate only from CORE_SCOPE.", entity_id=task.get("id"), related_refs=[classification_ref])
            if not (string_refs(task.get("acceptanceCriterionRefs")) or string_refs(task.get("mandatoryConstraintRefs"))):
                self.add("BASE_TASK_REQUIREMENT_REF_MISSING", "implementation_plan", path, "Base-plan task needs an AC or mandatory constraint.", entity_id=task.get("id"))
            self.check_ref_list(task.get("acceptanceCriterionRefs"), self.acceptance, "REFERENCE_AC_NOT_FOUND", "implementation_plan", f"{path}/acceptanceCriterionRefs", task.get("id"), "acceptance criterion")
            self.check_ref_list(task.get("mandatoryConstraintRefs"), self.constraints, "REFERENCE_CONSTRAINT_NOT_FOUND", "implementation_plan", f"{path}/mandatoryConstraintRefs", task.get("id"), "mandatory constraint")
            decision_ref = classification.get("decisionRef")
            if decision_ref in self.triage_decisions and self.triage_decisions[decision_ref].get("status") == "open":
                self.add("OPEN_DECISION_WORK_COMMITTED", "implementation_plan", path, "Work depending on an open decision must remain conditional.", entity_id=task.get("id"), related_refs=[decision_ref])
        expected_base = {
            identifier
            for identifier, classification in self.classifications.items()
            if classification.get("category") == "CORE_SCOPE"
        }
        if set(base_refs) != expected_base or len(base_refs) != len(set(base_refs)):
            self.add("BASE_CLASSIFICATION_COVERAGE_INVALID", "implementation_plan", "/basePlan", "Base plan must cover each CORE_SCOPE classification exactly once.")

        enabler_refs: list[str] = []
        for index, enabler in enumerate(object_items(self.plan, "requiredEnablers")):
            path = f"/requiredEnablers/{index}"
            classification_ref = enabler.get("classificationRef")
            if isinstance(classification_ref, str):
                enabler_refs.append(classification_ref)
            classification = self.classifications.get(classification_ref)
            if classification is None:
                self.require_ref(classification_ref, self.classifications, "REFERENCE_CLASSIFICATION_NOT_FOUND", "implementation_plan", f"{path}/classificationRef", enabler.get("id"), "classification")
                continue
            if classification.get("category") != "REQUIRED_ENABLER" or enabler.get("originCategory") != "REQUIRED_ENABLER":
                self.add("ENABLER_ORIGIN_NOT_REQUIRED_ENABLER", "implementation_plan", f"{path}/classificationRef", "Required-enabler section may contain only REQUIRED_ENABLER classifications.", entity_id=enabler.get("id"), related_refs=[classification_ref])
                if classification.get("category") == "OPTIONAL_IMPROVEMENT":
                    self.add("OPTIONAL_AS_REQUIRED_ENABLER", "implementation_plan", f"{path}/classificationRef", "Optional improvement cannot masquerade as a required enabler.", entity_id=enabler.get("id"), related_refs=[classification_ref])
            if not string_refs(enabler.get("evidenceRefs")):
                self.add("ENABLER_EVIDENCE_MISSING", "implementation_plan", f"{path}/evidenceRefs", "Required enabler needs evidence.", entity_id=enabler.get("id"))
            if not (string_refs(enabler.get("acceptanceCriterionRefs")) or string_refs(enabler.get("mandatoryConstraintRefs"))):
                self.add("ENABLER_REQUIREMENT_REF_MISSING", "implementation_plan", path, "Required enabler needs an AC or mandatory constraint.", entity_id=enabler.get("id"))
            if enabler.get("mandatoryReason") != classification.get("mandatoryReason"):
                self.add("ENABLER_MANDATORY_REASON_MISMATCH", "implementation_plan", f"{path}/mandatoryReason", "Plan mandatory reason must match triage.", entity_id=enabler.get("id"))
            decision_ref = classification.get("decisionRef")
            if decision_ref in self.triage_decisions and self.triage_decisions[decision_ref].get("status") == "open":
                self.add("OPEN_DECISION_WORK_COMMITTED", "implementation_plan", path, "Work depending on an open decision must remain conditional.", entity_id=enabler.get("id"), related_refs=[decision_ref])
        expected_enablers = {
            identifier
            for identifier, classification in self.classifications.items()
            if classification.get("category") == "REQUIRED_ENABLER"
        }
        if set(enabler_refs) != expected_enablers or len(enabler_refs) != len(set(enabler_refs)):
            self.add("ENABLER_CLASSIFICATION_COVERAGE_INVALID", "implementation_plan", "/requiredEnablers", "Plan must cover each REQUIRED_ENABLER exactly once.")

        creation_verb = re.compile(r"\b(add|create|provision|introduce|register)\b", re.IGNORECASE)
        capability_word = re.compile(r"\b(config(?:uration)?|channel|entry|capability)\b", re.IGNORECASE)
        for task, path in self.all_tasks():
            refs = string_refs(task.get("evidenceRefs"))
            existing = any(self.evidence[ref].get("capabilityState") == "already_exists" for ref in refs if ref in self.evidence)
            change = any(self.evidence[ref].get("capabilityState") == "requires_change" for ref in refs if ref in self.evidence)
            text = f"{task.get('title', '')} {task.get('description', '')}"
            if existing and not change and creation_verb.search(text) and capability_word.search(text):
                self.add("EXISTING_CAPABILITY_CREATION_TASK", "implementation_plan", path, "Verified existing capability cannot become creation work without separate change evidence.", entity_id=task.get("id"), related_refs=refs)

    def task_grounding_legality(self) -> None:
        verified_evidence = {
            ref
            for classification in self.classifications.values()
            if classification.get("category") == "VERIFIED_FACT"
            for ref in string_refs(classification.get("evidenceRefs"))
        }
        task_contexts: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
        for index, task in enumerate(self.base_tasks):
            task_contexts.append((task, f"/basePlan/{index}", self.classifications.get(task.get("classificationRef"), {})))
        for index, enabler in enumerate(object_items(self.plan, "requiredEnablers")):
            classification = self.classifications.get(enabler.get("classificationRef"), {})
            task_contexts.extend(
                (task, f"/requiredEnablers/{index}/tasks/{task_index}", classification)
                for task_index, task in enumerate(object_items(enabler, "tasks"))
            )
        for index, branch in enumerate(object_items(self.plan, "conditionalBranches")):
            classification = self.classifications.get(branch.get("classificationRef"), {})
            task_contexts.extend(
                (task, f"/conditionalBranches/{index}/tasks/{task_index}", classification)
                for task_index, task in enumerate(object_items(branch, "tasks"))
            )
        for index, expansion in enumerate(object_items(self.plan, "approvedScopeExpansions")):
            classification = self.classifications.get(expansion.get("originalClassificationRef"), {})
            task_contexts.extend(
                (task, f"/approvedScopeExpansions/{index}/tasks/{task_index}", classification)
                for task_index, task in enumerate(object_items(expansion, "tasks"))
            )

        required_evidence: set[str] = set()
        required_provenance: set[str] = set()
        for task, path, classification in task_contexts:
            entity_id = task.get("id")
            classification_evidence = set(string_refs(classification.get("evidenceRefs")))
            task_evidence = set(string_refs(task.get("evidenceRefs")))
            test_evidence = set(string_refs(task.get("testEvidenceRefs")))
            allowed = classification_evidence | verified_evidence
            if not classification_evidence.issubset(task_evidence) or (task_evidence | test_evidence) - allowed:
                self.add("TASK_EVIDENCE_NOT_CLASSIFICATION_GROUNDED", "implementation_plan", path, "Task evidence must include its classification evidence and may add only VERIFIED_FACT support.", entity_id=entity_id, related_refs=task_evidence | test_evidence)
            evidence_provenance = {
                ref
                for evidence_ref in task_evidence | test_evidence
                if evidence_ref in self.evidence
                for ref in string_refs(self.evidence[evidence_ref].get("provenanceRefs"))
            }
            task_provenance = set(string_refs(task.get("provenanceRefs")))
            if not task_provenance or task_provenance - evidence_provenance:
                self.add("TASK_PROVENANCE_NOT_EVIDENCE_BACKED", "implementation_plan", f"{path}/provenanceRefs", "Every task needs direct provenance supplied by its evidence.", entity_id=entity_id, related_refs=task_provenance)
            required_evidence.update(task_evidence | test_evidence)
            required_provenance.update(task_provenance)

        for item in object_items(self.plan, "requiredEnablers") + object_items(self.plan, "readinessPrerequisites") + object_items(self.plan, "relatedFindings") + object_items(self.plan, "decisionRegister"):
            required_evidence.update(string_refs(item.get("evidenceRefs")))
        required_provenance.update(
            ref
            for evidence_ref in required_evidence
            if evidence_ref in self.evidence
            for ref in string_refs(self.evidence[evidence_ref].get("provenanceRefs"))
        )
        section = as_object(self.plan.get("evidenceAndProvenance"))
        if set(string_refs(section.get("evidenceRefs"))) != required_evidence:
            self.add("PLAN_EVIDENCE_COVERAGE_INVALID", "implementation_plan", "/evidenceAndProvenance/evidenceRefs", "Evidence section must exactly cover plan evidence.")
        if set(string_refs(section.get("provenanceRefs"))) != required_provenance:
            self.add("PLAN_PROVENANCE_COVERAGE_INVALID", "implementation_plan", "/evidenceAndProvenance/provenanceRefs", "Provenance section must exactly cover plan provenance.")

    def branch_legality(self) -> None:
        expected_pairs = {
            (classification_id, option.get("id"))
            for classification_id, classification in self.classifications.items()
            if classification.get("category") == "CONDITIONAL_SCOPE"
            for option in object_items(self.triage_decisions.get(classification.get("decisionRef"), {}), "options")
            if isinstance(option.get("id"), str)
        }
        actual_pairs: list[tuple[str, str]] = []
        for index, branch in enumerate(object_items(self.plan, "conditionalBranches")):
            path = f"/conditionalBranches/{index}"
            entity_id = branch.get("id")
            classification_ref = branch.get("classificationRef")
            classification = self.classifications.get(classification_ref)
            if classification is None or classification.get("category") != "CONDITIONAL_SCOPE":
                self.add("BRANCH_ORIGIN_NOT_CONDITIONAL_SCOPE", "implementation_plan", f"{path}/classificationRef", "Conditional branch must originate from CONDITIONAL_SCOPE.", entity_id=entity_id, related_refs=[classification_ref] if isinstance(classification_ref, str) else [])
            decision_ref = branch.get("decisionRef")
            if decision_ref is None:
                self.add("BRANCH_DECISION_REF_MISSING", "implementation_plan", f"{path}/decisionRef", "Conditional branch requires a decision reference.", entity_id=entity_id)
            elif not self.require_ref(decision_ref, self.triage_decisions, "REFERENCE_DECISION_NOT_FOUND", "implementation_plan", f"{path}/decisionRef", entity_id, "decision"):
                pass
            elif classification and classification.get("decisionRef") != decision_ref:
                self.add("BRANCH_DECISION_MISMATCH", "implementation_plan", f"{path}/decisionRef", "Branch decision must match its classification.", entity_id=entity_id, related_refs=[decision_ref])
            if not isinstance(branch.get("condition"), str) or not branch.get("condition", "").strip():
                self.add("BRANCH_CONDITION_MISSING", "implementation_plan", f"{path}/condition", "Conditional branch requires an explicit condition.", entity_id=entity_id)
            options = {
                option.get("id")
                for option in object_items(self.triage_decisions.get(decision_ref, {}), "options")
                if isinstance(option.get("id"), str)
            }
            option_ref = branch.get("decisionOptionRef")
            if option_ref not in options:
                self.add("BRANCH_OPTION_NOT_IN_DECISION", "implementation_plan", f"{path}/decisionOptionRef", "Branch option must belong to its decision.", entity_id=entity_id, related_refs=[option_ref] if isinstance(option_ref, str) else [])
            if isinstance(classification_ref, str) and isinstance(option_ref, str):
                actual_pairs.append((classification_ref, option_ref))
            group_ref = branch.get("groupRef")
            group = self.branch_groups.get(group_ref)
            if group is None:
                self.add("BRANCH_GROUP_REF_INVALID", "implementation_plan", f"{path}/groupRef", "Branch must reference an existing branch group.", entity_id=entity_id, related_refs=[group_ref] if isinstance(group_ref, str) else [])
            elif entity_id not in string_refs(group.get("branchRefs")) or group.get("decisionRef") != decision_ref or group.get("relationship") != branch.get("relationship"):
                self.add("BRANCH_GROUP_MEMBERSHIP_MISMATCH", "implementation_plan", path, "Branch and group references must be reciprocal and semantically consistent.", entity_id=entity_id, related_refs=[group_ref])
        if set(actual_pairs) != expected_pairs or len(actual_pairs) != len(set(actual_pairs)):
            self.add("CONDITIONAL_BRANCH_COVERAGE_INVALID", "implementation_plan", "/conditionalBranches", "Conditional branches must cover every classification/decision-option pair exactly once.")

        for index, group in enumerate(object_items(self.plan, "branchGroups")):
            path = f"/branchGroups/{index}"
            refs = string_refs(group.get("branchRefs"))
            decision_ref = group.get("decisionRef")
            self.require_ref(decision_ref, self.triage_decisions, "REFERENCE_DECISION_NOT_FOUND", "implementation_plan", f"{path}/decisionRef", group.get("id"), "decision")
            for ref in refs:
                self.require_ref(ref, self.branches, "REFERENCE_BRANCH_NOT_FOUND", "implementation_plan", f"{path}/branchRefs", group.get("id"), "branch")
            expected_refs = {
                identifier
                for identifier, branch in self.branches.items()
                if branch.get("decisionRef") == decision_ref
            }
            if set(refs) != expected_refs or any(
                self.branches[ref].get("groupRef") != group.get("id")
                for ref in refs
                if ref in self.branches
            ):
                self.add("BRANCH_GROUP_MEMBERSHIP_MISMATCH", "implementation_plan", path, "Branch group must exactly and reciprocally cover branches for its decision.", entity_id=group.get("id"), related_refs=refs)
            triage_group = next(
                (
                    item
                    for item in self.option_groups.values()
                    if item.get("decisionRef") == decision_ref
                ),
                None,
            )
            if triage_group is None or group.get("relationship") != triage_group.get("relationship") or group.get("selectionRule") != triage_group.get("selectionRule"):
                self.add("BRANCH_GROUP_TRIAGE_MISMATCH", "implementation_plan", path, "Plan branch-group semantics must match Scope Triage.", entity_id=group.get("id"))
            if group.get("selectionRule") == "exactly_one" and group.get("relationship") != "mutually_exclusive":
                self.add("BRANCH_GROUP_SELECTION_INVALID", "implementation_plan", path, "exactly_one groups must be mutually exclusive.", entity_id=group.get("id"))
            if group.get("relationship") == "combinable" and group.get("selectionRule") != "all_applicable":
                self.add("BRANCH_GROUP_SELECTION_INVALID", "implementation_plan", path, "Combinable groups must select all applicable branches.", entity_id=group.get("id"))

    def readiness_and_related_legality(self) -> None:
        expected_readiness = {
            identifier
            for identifier, classification in self.classifications.items()
            if classification.get("category") == "READINESS_PREREQUISITE"
        }
        actual_readiness = {item.get("classificationRef") for item in self.readiness.values()}
        if actual_readiness != expected_readiness:
            self.add("READINESS_CLASSIFICATION_COVERAGE_INVALID", "implementation_plan", "/readinessPrerequisites", "Readiness section must exactly cover readiness classifications.")
        for index, readiness in enumerate(object_items(self.plan, "readinessPrerequisites")):
            path = f"/readinessPrerequisites/{index}"
            classification = self.classifications.get(readiness.get("classificationRef"))
            if classification is None or classification.get("category") != "READINESS_PREREQUISITE":
                self.add("READINESS_ORIGIN_INVALID", "implementation_plan", f"{path}/classificationRef", "Readiness must not enter implementation scope.", entity_id=readiness.get("id"))
            refs = string_refs(readiness.get("evidenceRefs"))
            approval = any(self.evidence[ref].get("kind") == "human_decision" for ref in refs if ref in self.evidence)
            pair = effort_pair(readiness.get("engineeringEffort"))
            if approval and pair != (0.0, 0.0):
                self.add("READINESS_APPROVAL_EFFORT_NONZERO", "implementation_plan", f"{path}/engineeringEffort", "Pending approval calendar delay cannot become developer effort.", entity_id=readiness.get("id"), related_refs=refs)

        related_categories = {"RELATED_DEFECT", "RISK_ONLY", "OPTIONAL_IMPROVEMENT"}
        expected_related = {
            identifier
            for identifier, classification in self.classifications.items()
            if classification.get("category") in related_categories
        }
        actual_related = {item.get("classificationRef") for item in self.related.values()}
        if actual_related != expected_related:
            self.add("RELATED_FINDING_COVERAGE_INVALID", "implementation_plan", "/relatedFindings", "Excluded findings must remain outside implementation tasks.")

    def estimate_legality(self) -> None:
        effort_entries: list[tuple[Any, str, str]] = []
        for index, task in enumerate(self.base_tasks):
            effort_entries.append((task.get("effort"), f"/basePlan/{index}/effort", "implementation_plan"))
        for key in ("requiredEnablers", "conditionalBranches", "readinessPrerequisites"):
            for index, item in enumerate(object_items(self.plan, key)):
                field = "engineeringEffort" if key == "readinessPrerequisites" else "effort"
                effort_entries.append((item.get(field), f"/{key}/{index}/{field}", "implementation_plan"))
        estimates = as_object(self.plan.get("scenarioEstimates"))
        effort_entries.append((estimates.get("baseEffort"), "/scenarioEstimates/baseEffort", "implementation_plan"))
        for index, delta in enumerate(object_items(estimates, "requiredEnablerDeltas")):
            effort_entries.append((delta.get("effort"), f"/scenarioEstimates/requiredEnablerDeltas/{index}/effort", "implementation_plan"))
        for scenario_index, scenario in enumerate(object_items(estimates, "scenarios")):
            for field in ("baseEffort", "engineeringTotal"):
                effort_entries.append((scenario.get(field), f"/scenarioEstimates/scenarios/{scenario_index}/{field}", "implementation_plan"))
            for field in ("mandatoryDeltas", "conditionalDeltas", "approvedScopeDeltas"):
                for index, delta in enumerate(object_items(scenario, field)):
                    effort_entries.append((delta.get("effort"), f"/scenarioEstimates/scenarios/{scenario_index}/{field}/{index}/effort", "implementation_plan"))
        final_estimate = estimates.get("finalCommittedEstimate")
        if final_estimate is not None:
            effort_entries.append((final_estimate, "/scenarioEstimates/finalCommittedEstimate", "implementation_plan"))
        for effort, path, artifact in effort_entries:
            pair = effort_pair(effort)
            if pair is None or pair[0] < 0 or pair[1] < 0:
                self.add("EFFORT_RANGE_INVALID", artifact, path, "Effort lower bound and additional uncertainty must be non-negative numbers.")

        base_pairs = [pair for pair in (effort_pair(task.get("effort")) for task in self.base_tasks) if pair is not None]
        expected_base = (sum(pair[0] for pair in base_pairs), sum(pair[1] for pair in base_pairs))
        if effort_pair(estimates.get("baseEffort")) != expected_base:
            self.add("BASE_EFFORT_MISMATCH", "implementation_plan", "/scenarioEstimates/baseEffort", "Base effort must sum base-plan tasks only.")

        required_deltas = object_items(estimates, "requiredEnablerDeltas")
        required_refs = [item.get("enablerRef") for item in required_deltas if isinstance(item.get("enablerRef"), str)]
        if set(required_refs) != set(self.enablers) or len(required_refs) != len(set(required_refs)):
            self.add("MANDATORY_DELTA_COVERAGE_INVALID", "implementation_plan", "/scenarioEstimates/requiredEnablerDeltas", "Every required enabler must have one separate mandatory delta.")
        for index, delta in enumerate(required_deltas):
            ref = delta.get("enablerRef")
            self.require_ref(ref, self.enablers, "REFERENCE_ENABLER_NOT_FOUND", "implementation_plan", f"/scenarioEstimates/requiredEnablerDeltas/{index}/enablerRef", None, "required enabler")
            if ref in self.enablers and canonical(delta.get("effort")) != canonical(self.enablers[ref].get("effort")):
                self.add("MANDATORY_DELTA_MISMATCH", "implementation_plan", f"/scenarioEstimates/requiredEnablerDeltas/{index}/effort", "Mandatory delta must equal its enabler effort.", related_refs=[ref])

        open_material = {
            identifier
            for identifier, decision in self.triage_decisions.items()
            if decision.get("status") == "open" and decision.get("materiality") == "material"
        }
        declared_open = set(string_refs(estimates.get("openMaterialDecisionRefs")))
        for index, ref in enumerate(as_list(estimates.get("openMaterialDecisionRefs"))):
            self.require_ref(ref, self.triage_decisions, "REFERENCE_DECISION_NOT_FOUND", "implementation_plan", f"/scenarioEstimates/openMaterialDecisionRefs/{index}", None, "decision")
        if declared_open != open_material:
            self.add("OPEN_MATERIAL_DECISION_SET_MISMATCH", "implementation_plan", "/scenarioEstimates/openMaterialDecisionRefs", "Open material decision set must be reproduced exactly.")
        if open_material and estimates.get("finalCommittedEstimate") is not None:
            self.add("OPEN_MATERIAL_DECISION_FINAL_TOTAL", "implementation_plan", "/scenarioEstimates/finalCommittedEstimate", "No authoritative final estimate is legal while material decisions remain open.", related_refs=open_material)

        selected_across: set[str] = set()
        for scenario_index, scenario in enumerate(object_items(estimates, "scenarios")):
            path = f"/scenarioEstimates/scenarios/{scenario_index}"
            selected = string_refs(scenario.get("selectedBranchRefs"))
            selected_set = set(selected)
            selected_across.update(selected_set)
            for ref in selected:
                self.require_ref(ref, self.branches, "REFERENCE_BRANCH_NOT_FOUND", "implementation_plan", f"{path}/selectedBranchRefs", scenario.get("id"), "branch")
            if effort_pair(scenario.get("baseEffort")) != effort_pair(estimates.get("baseEffort")):
                self.add("SCENARIO_BASE_EFFORT_MISMATCH", "implementation_plan", f"{path}/baseEffort", "Scenario base effort must equal the base-only estimate.", entity_id=scenario.get("id"))

            mandatory = object_items(scenario, "mandatoryDeltas")
            mandatory_refs = [item.get("enablerRef") for item in mandatory if isinstance(item.get("enablerRef"), str)]
            if set(mandatory_refs) != set(self.enablers) or len(mandatory_refs) != len(set(mandatory_refs)):
                self.add("SCENARIO_MANDATORY_DELTA_COVERAGE_INVALID", "implementation_plan", f"{path}/mandatoryDeltas", "Scenario must include each mandatory delta exactly once.", entity_id=scenario.get("id"))
            for delta in mandatory:
                ref = delta.get("enablerRef")
                self.require_ref(ref, self.enablers, "REFERENCE_ENABLER_NOT_FOUND", "implementation_plan", f"{path}/mandatoryDeltas", scenario.get("id"), "required enabler")
                if ref in self.enablers and canonical(delta.get("effort")) != canonical(self.enablers[ref].get("effort")):
                    self.add("MANDATORY_DELTA_MISMATCH", "implementation_plan", f"{path}/mandatoryDeltas", "Scenario mandatory delta differs from its enabler.", entity_id=scenario.get("id"), related_refs=[ref])

            conditional = object_items(scenario, "conditionalDeltas")
            conditional_refs = [item.get("branchRef") for item in conditional if isinstance(item.get("branchRef"), str)]
            if set(conditional_refs) != selected_set or len(conditional_refs) != len(set(conditional_refs)):
                self.add("SCENARIO_CONDITIONAL_DELTA_SELECTION_MISMATCH", "implementation_plan", f"{path}/conditionalDeltas", "Conditional deltas must exactly match selected branches.", entity_id=scenario.get("id"))
            for delta in conditional:
                ref = delta.get("branchRef")
                self.require_ref(ref, self.branches, "REFERENCE_BRANCH_NOT_FOUND", "implementation_plan", f"{path}/conditionalDeltas", scenario.get("id"), "branch")
                if ref in self.branches and canonical(delta.get("effort")) != canonical(self.branches[ref].get("effort")):
                    self.add("CONDITIONAL_DELTA_MISMATCH", "implementation_plan", f"{path}/conditionalDeltas", "Conditional delta differs from its selected branch.", entity_id=scenario.get("id"), related_refs=[ref])

            for group in self.branch_groups.values():
                in_group = selected_set & set(string_refs(group.get("branchRefs")))
                rule = group.get("selectionRule")
                if rule == "exactly_one" and len(in_group) != 1:
                    code = "SCENARIO_EXCLUSIVE_BRANCH_CONFLICT" if len(in_group) > 1 else "SCENARIO_EXACTLY_ONE_BRANCH_MISSING"
                    self.add(code, "implementation_plan", f"{path}/selectedBranchRefs", "Scenario violates exactly-one branch selection.", entity_id=scenario.get("id"), related_refs=in_group or string_refs(group.get("branchRefs")))
                if rule == "zero_or_one" and len(in_group) > 1:
                    self.add("SCENARIO_ZERO_OR_ONE_BRANCH_CONFLICT", "implementation_plan", f"{path}/selectedBranchRefs", "Scenario selects more than one zero-or-one branch.", entity_id=scenario.get("id"), related_refs=in_group)
                if rule == "all_applicable" and in_group != set(string_refs(group.get("branchRefs"))):
                    self.add("SCENARIO_COMBINABLE_BRANCH_MISSING", "implementation_plan", f"{path}/selectedBranchRefs", "Scenario must include every explicitly combinable branch.", entity_id=scenario.get("id"), related_refs=string_refs(group.get("branchRefs")))

            approved = object_items(scenario, "approvedScopeDeltas")
            approved_refs = [item.get("scopeExpansionRef") for item in approved if isinstance(item.get("scopeExpansionRef"), str)]
            if set(approved_refs) != set(self.approved_expansions) or len(approved_refs) != len(set(approved_refs)):
                self.add("SCENARIO_APPROVED_DELTA_COVERAGE_INVALID", "implementation_plan", f"{path}/approvedScopeDeltas", "Scenario must include each approved expansion delta exactly once.", entity_id=scenario.get("id"))
            for delta in approved:
                self.require_ref(delta.get("scopeExpansionRef"), self.approved_expansions, "REFERENCE_SCOPE_EXPANSION_NOT_FOUND", "implementation_plan", f"{path}/approvedScopeDeltas", scenario.get("id"), "approved scope expansion")

            calendars = object_items(scenario, "calendarImpacts")
            calendar_refs = [item.get("readinessRef") for item in calendars if isinstance(item.get("readinessRef"), str)]
            if set(calendar_refs) != set(self.readiness) or len(calendar_refs) != len(set(calendar_refs)):
                self.add("SCENARIO_CALENDAR_COVERAGE_INVALID", "implementation_plan", f"{path}/calendarImpacts", "Calendar impacts must remain separate and cover readiness exactly.", entity_id=scenario.get("id"))
            for contribution in calendars:
                ref = contribution.get("readinessRef")
                self.require_ref(ref, self.readiness, "REFERENCE_READINESS_NOT_FOUND", "implementation_plan", f"{path}/calendarImpacts", scenario.get("id"), "readiness prerequisite")
                if ref in self.readiness and canonical(contribution.get("impact")) != canonical(self.readiness[ref].get("calendarImpact")):
                    self.add("SCENARIO_CALENDAR_IMPACT_MISMATCH", "implementation_plan", f"{path}/calendarImpacts", "Scenario calendar impact differs from readiness.", entity_id=scenario.get("id"), related_refs=[ref])

            component_pairs = [effort_pair(scenario.get("baseEffort"))]
            component_pairs += [effort_pair(item.get("effort")) for item in mandatory]
            component_pairs += [effort_pair(item.get("effort")) for item in conditional]
            component_pairs += [effort_pair(item.get("effort")) for item in approved]
            valid_pairs = [pair for pair in component_pairs if pair is not None]
            expected_total = (sum(pair[0] for pair in valid_pairs), sum(pair[1] for pair in valid_pairs))
            if len(valid_pairs) != len(component_pairs) or effort_pair(scenario.get("engineeringTotal")) != expected_total:
                self.add("SCENARIO_TOTAL_MISMATCH", "implementation_plan", f"{path}/engineeringTotal", "Scenario engineering total must be reproducible from base, mandatory, selected conditional, and approved deltas only.", entity_id=scenario.get("id"))
            if open_material and scenario.get("finality") != "scenario_only":
                self.add("OPEN_DECISION_SCENARIO_MARKED_COMMITTED", "implementation_plan", f"{path}/finality", "Open material decisions require scenario-only estimates.", entity_id=scenario.get("id"))
        if selected_across != set(self.branches):
            self.add("SCENARIO_BRANCH_COVERAGE_INVALID", "implementation_plan", "/scenarioEstimates/scenarios", "Scenario set must represent every conditional branch.")

    def deterministic_identity(self) -> None:
        def check_entity(
            item: dict[str, Any], prefix: str, value: dict[str, Any], artifact: str, path: str
        ) -> None:
            identifier = item.get("id")
            if isinstance(identifier, str) and identifier != stable_id(prefix, value):
                self.add(
                    "DETERMINISTIC_ENTITY_ID_INVALID",
                    artifact,
                    f"{path}/id",
                    "Entity ID does not match its canonical semantic identity.",
                    entity_id=identifier,
                )

        for index, item in enumerate(object_items(self.discovery, "provenance")):
            check_entity(
                item,
                "provenance",
                {key: item.get(key) for key in ("sourceType", "sourceRef", "sourceDigest", "summary")},
                "discovery",
                f"/provenance/{index}",
            )
        for index, item in enumerate(object_items(self.discovery, "acceptanceCriteria")):
            check_entity(
                item,
                "ac",
                {
                    "sourceKey": item.get("sourceKey"),
                    "text": item.get("text"),
                    "approvalStatus": item.get("approvalStatus"),
                    "provenanceRefs": sorted(set(string_refs(item.get("provenanceRefs")))),
                },
                "discovery",
                f"/acceptanceCriteria/{index}",
            )
        for index, item in enumerate(object_items(self.discovery, "evidence")):
            check_entity(
                item,
                "ev",
                {
                    "kind": item.get("kind"),
                    "epistemicStatus": item.get("epistemicStatus"),
                    "summary": item.get("summary"),
                    "capabilityState": item.get("capabilityState"),
                    "preExistingStatus": item.get("preExistingStatus"),
                    "provenanceRefs": sorted(set(string_refs(item.get("provenanceRefs")))),
                },
                "discovery",
                f"/evidence/{index}",
            )
        for index, item in enumerate(object_items(self.discovery, "mandatoryConstraints")):
            check_entity(
                item,
                "constraint",
                {
                    "kind": item.get("kind"),
                    "statement": item.get("statement"),
                    "evidenceRefs": sorted(set(string_refs(item.get("evidenceRefs")))),
                },
                "discovery",
                f"/mandatoryConstraints/{index}",
            )
        for decision_index, decision in enumerate(object_items(self.discovery, "decisions")):
            options: list[dict[str, Any]] = []
            for option_index, option in enumerate(object_items(decision, "options")):
                option_value = {"label": option.get("label"), "summary": option.get("summary")}
                check_entity(option, "option", option_value, "discovery", f"/decisions/{decision_index}/options/{option_index}")
                options.append({"id": option.get("id"), **option_value})
            decision_value = {
                "question": decision.get("question"),
                "owner": decision.get("owner"),
                "status": decision.get("status"),
                "materiality": decision.get("materiality"),
                "options": sorted(options, key=lambda option: str(option.get("id", ""))),
                "selectedOptionId": decision.get("selectedOptionId"),
                "evidenceRefs": sorted(set(string_refs(decision.get("evidenceRefs")))),
            }
            check_entity(decision, "decision", decision_value, "discovery", f"/decisions/{decision_index}")
        for index, item in enumerate(object_items(self.discovery, "findings")):
            check_entity(
                item,
                "finding",
                {
                    "findingKind": item.get("findingKind"),
                    "summary": item.get("summary"),
                    "evidenceRefs": sorted(set(string_refs(item.get("evidenceRefs")))),
                    "acceptanceCriterionRefs": sorted(set(string_refs(item.get("acceptanceCriterionRefs")))),
                    "mandatoryConstraintRefs": sorted(set(string_refs(item.get("mandatoryConstraintRefs")))),
                    "decisionRefs": sorted(set(string_refs(item.get("decisionRefs")))),
                    "storyCausality": item.get("storyCausality"),
                    "suggestedOwner": item.get("suggestedOwner"),
                },
                "discovery",
                f"/findings/{index}",
            )
        for index, item in enumerate(object_items(self.discovery, "openQuestions")):
            check_entity(
                item,
                "question",
                {
                    "question": item.get("question"),
                    "suggestedOwner": item.get("suggestedOwner"),
                    "evidenceRefs": sorted(set(string_refs(item.get("evidenceRefs")))),
                    "acceptanceCriterionRefs": sorted(set(string_refs(item.get("acceptanceCriterionRefs")))),
                    "decisionNeeded": item.get("decisionNeeded"),
                },
                "discovery",
                f"/openQuestions/{index}",
            )

        for index, item in enumerate(object_items(self.triage, "classifications")):
            value = {key: copy.deepcopy(entry) for key, entry in item.items() if key != "id"}
            for field in ("evidenceRefs", "acceptanceCriterionRefs", "mandatoryConstraintRefs"):
                value[field] = sorted(set(string_refs(value.get(field))))
            assessment = value.get("promotionAssessment")
            if isinstance(assessment, dict):
                for field in ("failingAcceptanceCriterionRefs", "failingMandatoryConstraintRefs", "dependencyEvidenceRefs"):
                    assessment[field] = sorted(set(string_refs(assessment.get(field))))
            check_entity(item, "classification", value, "triage", f"/classifications/{index}")
        for index, item in enumerate(object_items(self.triage, "optionGroups")):
            value = {key: copy.deepcopy(entry) for key, entry in item.items() if key != "id"}
            value["optionRefs"] = sorted(set(string_refs(value.get("optionRefs"))))
            check_entity(item, "optiongroup", value, "triage", f"/optionGroups/{index}")
        for index, item in enumerate(object_items(self.triage, "scopeExpansions")):
            value = {key: copy.deepcopy(entry) for key, entry in item.items() if key != "id"}
            value["approvalEvidenceRefs"] = sorted(set(string_refs(value.get("approvalEvidenceRefs"))))
            value["resultingWorkRefs"] = sorted(set(string_refs(value.get("resultingWorkRefs"))))
            check_entity(item, "expansion", value, "triage", f"/scopeExpansions/{index}")

        for task, path in self.all_tasks():
            value = {key: copy.deepcopy(entry) for key, entry in task.items() if key != "id"}
            for field in (
                "evidenceRefs", "provenanceRefs", "sourceTargets", "testEvidenceRefs",
                "acceptanceCriterionRefs", "mandatoryConstraintRefs",
            ):
                if field in value:
                    value[field] = sorted(set(string_refs(value.get(field))))
            check_entity(task, "task", value, "implementation_plan", path)
        for key, prefix in (
            ("requiredEnablers", "enabler"),
            ("readinessPrerequisites", "readiness"),
            ("relatedFindings", "related"),
            ("branchGroups", "branchgroup"),
        ):
            for index, item in enumerate(object_items(self.plan, key)):
                value = {field: copy.deepcopy(entry) for field, entry in item.items() if field != "id"}
                check_entity(item, prefix, value, "implementation_plan", f"/{key}/{index}")
        for index, item in enumerate(object_items(self.plan, "conditionalBranches")):
            value = {
                field: copy.deepcopy(entry)
                for field, entry in item.items()
                if field not in {"id", "groupRef"}
            }
            check_entity(item, "branch", value, "implementation_plan", f"/conditionalBranches/{index}")
        estimates = as_object(self.plan.get("scenarioEstimates"))
        for index, item in enumerate(object_items(estimates, "scenarios")):
            value = {field: copy.deepcopy(entry) for field, entry in item.items() if field != "id"}
            check_entity(item, "scenario", value, "implementation_plan", f"/scenarioEstimates/scenarios/{index}")

        identities = [
            (
                "discovery",
                self.discovery,
                "discovery",
                {
                    key: self.discovery.get(key)
                    for key in (
                        "schemaVersion", "artifactVersion", "storyId", "acceptanceCriteria",
                        "mandatoryConstraints", "evidence", "findings", "decisions",
                        "openQuestions", "provenance",
                    )
                },
            ),
            (
                "triage",
                self.triage,
                "triage",
                {
                    key: self.triage.get(key)
                    for key in (
                        "schemaVersion", "artifactVersion", "storyId",
                        "sourceDiscoveryArtifactRef", "classifications", "decisions",
                        "optionGroups", "scopeExpansions",
                    )
                },
            ),
            (
                "implementation_plan",
                self.plan,
                "plan",
                {
                    key: value
                    for key, value in self.plan.items()
                    if key not in {"artifactId", "validationStatus"}
                },
            ),
        ]
        for artifact, document, prefix, identity in identities:
            identifier = document.get("artifactId")
            if isinstance(identifier, str) and identifier != stable_id(prefix, identity):
                self.add("DETERMINISTIC_ARTIFACT_ID_INVALID", artifact, "/artifactId", "Artifact ID does not match canonical semantic content.", entity_id=identifier)

    def run(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        self.schema_checks()
        self.duplicate_ids()
        self.artifact_links_and_references()
        self.decision_legality()
        self.triage_legality()
        self.base_and_enabler_legality()
        self.task_grounding_legality()
        self.branch_legality()
        self.readiness_and_related_legality()
        self.estimate_legality()
        self.deterministic_identity()
        return sorted_violations(self.violations), self.schema_state


def load_document(path: Path, label: str) -> tuple[dict[str, Any], str | None]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if isinstance(value, dict):
            return value, None
        return {}, f"{label} root must be a JSON object"
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{label} could not be parsed: {exc}"


def artifact_ref(document: dict[str, Any]) -> str | None:
    value = document.get("artifactId")
    return value if isinstance(value, str) and re.fullmatch(r"(discovery|triage|decisions|plan|estimates|provenance)_[0-9a-f]{64}", value) else None


def make_report(
    discovery: dict[str, Any],
    triage: dict[str, Any],
    plan: dict[str, Any],
    violations: list[dict[str, Any]],
    schema_state: dict[str, str],
    *,
    validation_pass: int = 1,
    initial_violations: list[dict[str, Any]] | None = None,
    correction_outcome: str = "not_attempted",
    force_owner_review: bool = False,
) -> dict[str, Any]:
    structural = any(item["kind"] == "structural" for item in violations)
    semantic = any(item["kind"] == "semantic" for item in violations)
    status = "passed" if not violations else ("needs_owner_review" if force_owner_review else "failed")
    story_id = next(
        (
            value
            for value in (discovery.get("storyId"), triage.get("storyId"), plan.get("storyId"))
            if isinstance(value, str) and value
        ),
        "story-unknown",
    )
    value: dict[str, Any] = {
        "schemaVersion": "mana.story-start.scope-governance-report/v2",
        "artifactVersion": 2,
        "storyId": story_id,
        "artifactRefs": {
            "discovery": artifact_ref(discovery),
            "triage": artifact_ref(triage),
            "implementationPlan": artifact_ref(plan),
        },
        "status": status,
        "validationPass": validation_pass,
        "schemaValidation": schema_state,
        "semanticValidation": "passed" if not violations else ("failed" if semantic else "not_run"),
        "violations": sorted_violations(violations),
        "initialViolations": sorted_violations(initial_violations or []),
        "correction": {
            "attemptCount": validation_pass - 1,
            "outcome": correction_outcome,
        },
        "ownerReview": {
            "state": "required" if force_owner_review else "not_required",
            "owner": "Story owner" if force_owner_review else None,
            "reason": "Corrected artifact failed full Scope Governor validation." if force_owner_review else None,
        },
    }
    if structural and not semantic:
        value["semanticValidation"] = "not_run"
    return {"reportId": stable_id("governance", value), **value}


def validate_report(report: dict[str, Any]) -> None:
    evaluator = SchemaEvaluator()
    schema_path = SCHEMA_ROOT / "governance-report.schema.json"
    schema = evaluator.load(schema_path)
    errors = evaluator.evaluate(report, schema, schema_path)
    if errors:
        raise ValueError("invalid governance report: " + "; ".join(errors[:8]))
    identity = {key: value for key, value in report.items() if key != "reportId"}
    if report["reportId"] != stable_id("governance", identity):
        raise ValueError("governance report ID does not match its content")
    if report["violations"] != sorted_violations(report["violations"]):
        raise ValueError("governance violations are not canonically ordered")
    if report["initialViolations"] != sorted_violations(report["initialViolations"]):
        raise ValueError("initial governance violations are not canonically ordered")


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError(f"unsafe output symlink: {path}")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(canonical(value) + "\n")
    os.replace(temporary, path)


def govern_paths(discovery_path: Path, triage_path: Path, plan_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    discovery, discovery_error = load_document(discovery_path, "discovery")
    triage, triage_error = load_document(triage_path, "triage")
    plan, plan_error = load_document(plan_path, "implementation plan")
    errors = {
        key: value
        for key, value in (
            ("discovery", discovery_error),
            ("triage", triage_error),
            ("implementation_plan", plan_error),
        )
        if value is not None
    }
    governor = ScopeGovernor(discovery, triage, plan, errors)
    violations, schema_state = governor.run()
    return discovery, triage, plan, violations, schema_state


def read_valid_report(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        report = json.load(handle)
    validate_report(report)
    return report


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 6 and argv[1] == "validate":
            discovery_path, triage_path, plan_path, report_path = map(Path, argv[2:])
            discovery, triage, plan, violations, schema_state = govern_paths(discovery_path, triage_path, plan_path)
            report = make_report(discovery, triage, plan, violations, schema_state)
            validate_report(report)
            atomic_write(report_path, report)
            return 0 if report["status"] == "passed" else 1
        if len(argv) == 7 and argv[1] == "revalidate":
            initial_path, discovery_path, triage_path, plan_path, report_path = map(Path, argv[2:])
            initial = read_valid_report(initial_path)
            if initial["status"] != "failed" or initial["validationPass"] != 1 or not initial["violations"]:
                raise ValueError("correction requires a failed first-pass report")
            discovery, triage, plan, violations, schema_state = govern_paths(discovery_path, triage_path, plan_path)
            passed = not violations
            report = make_report(
                discovery,
                triage,
                plan,
                violations,
                schema_state,
                validation_pass=2,
                initial_violations=initial["violations"],
                correction_outcome="succeeded" if passed else "failed",
                force_owner_review=not passed,
            )
            validate_report(report)
            atomic_write(report_path, report)
            return 0 if passed else 1
        if len(argv) == 5 and argv[1] == "provider-failed":
            initial_path, report_path = map(Path, argv[2:4])
            reason = argv[4]
            initial = read_valid_report(initial_path)
            violations = list(initial["violations"])
            violations.append(
                {
                    "code": "CORRECTION_PROVIDER_FAILED",
                    "kind": "semantic",
                    "artifact": "artifact_set",
                    "path": "",
                    "entityId": None,
                    "relatedRefs": [],
                    "message": reason[:4000],
                }
            )
            value = {key: copy.deepcopy(item) for key, item in initial.items() if key != "reportId"}
            value.update(
                {
                    "status": "needs_owner_review",
                    "validationPass": 2,
                    "semanticValidation": "failed",
                    "violations": sorted_violations(violations),
                    "initialViolations": sorted_violations(initial["violations"]),
                    "correction": {"attemptCount": 1, "outcome": "provider_failed"},
                    "ownerReview": {
                        "state": "required",
                        "owner": "Story owner",
                        "reason": "The single bounded corrective provider attempt failed.",
                    },
                }
            )
            report = {"reportId": stable_id("governance", value), **value}
            validate_report(report)
            atomic_write(report_path, report)
            return 1
        if len(argv) == 3 and argv[1] == "validate-report":
            read_valid_report(Path(argv[2]))
            return 0
        print(
            "Usage: story-start-scope-v2-govern.py validate <discovery> <triage> <plan> <report>\n"
            "   or: story-start-scope-v2-govern.py revalidate <initial-report> <discovery> <triage> <corrected-plan> <report>\n"
            "   or: story-start-scope-v2-govern.py provider-failed <initial-report> <report> <reason>\n"
            "   or: story-start-scope-v2-govern.py validate-report <report>",
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
