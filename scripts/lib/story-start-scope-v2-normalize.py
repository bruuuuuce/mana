#!/usr/bin/env python3
"""Deterministically normalize a schema-valid Story Start Scope v2 discovery.

This is internal SS02 host support. It deliberately consumes only the compact
provider artifact; it never traverses a repository or decides final scope.
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


def main(argv: list[str]) -> int:
    if len(argv) != 5 or argv[1] != "normalize-discovery":
        print(
            "Usage: story-start-scope-v2-normalize.py normalize-discovery <schema> <input> <output>",
            file=sys.stderr,
        )
        return 2
    schema_path, input_path, output_path = map(Path, argv[2:])
    try:
        with input_path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        validate(schema_path.resolve(), raw)
        normalized = normalize_discovery(raw)
        validate(schema_path.resolve(), normalized)
        output_path.write_text(canonical(normalized) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, NormalizationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
