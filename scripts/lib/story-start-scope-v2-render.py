#!/usr/bin/env python3
"""Deterministic publication metadata and Markdown rendering for Story Start v2."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


RUN_SCHEMA = "mana.story-start.scope-run/v2"
PLAN_SCHEMA = "mana.story-start.implementation-plan/v2"
GOVERNANCE_SCHEMA = "mana.story-start.scope-governance-report/v2"

PUBLIC_PATHS = {
    "discovery": "evidence/story-start-discovery-v2.json",
    "triage": "planning/story-start-scope-triage-v2.json",
    "implementationPlan": "planning/story-start-implementation-plan-v2.json",
    "governanceReport": "validation/story-start-scope-governance-v2.json",
    "markdownReport": "planning/story-start-scope-v2.md",
}

PHASES = ("discovery", "triage", "planner", "governor", "rendering")


class RenderError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RenderError(f"unreadable JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise RenderError(f"JSON artifact must be an object: {path}")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{hashlib.sha256(canonical_bytes(value)).hexdigest()}"


def atomic_write(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise RenderError(f"refusing to replace output symlink: {target}")
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.tmp.", dir=str(target.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_json(path: str | Path, value: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def artifact_ref(identifier: str, kind: str) -> dict[str, str]:
    return {"id": identifier, "path": PUBLIC_PATHS[kind]}


def require_identifier(artifact: dict[str, Any], field: str, label: str) -> str:
    value = artifact.get(field)
    if not isinstance(value, str) or not value:
        raise RenderError(f"{label} has no {field}")
    return value


def finalize_run_status(payload: dict[str, Any]) -> dict[str, Any]:
    identity_payload = dict(payload)
    identity_payload.pop("runId", None)
    payload["runId"] = stable_id("run", identity_payload)
    return payload


def validate_run_status(status: dict[str, Any]) -> None:
    if status.get("schemaVersion") != RUN_SCHEMA or status.get("artifactVersion") != 2:
        raise RenderError("run status has an unsupported version")
    identity_payload = dict(status)
    actual = identity_payload.pop("runId", None)
    expected = stable_id("run", identity_payload)
    if actual != expected:
        raise RenderError("run status ID does not match its canonical content")
    artifact_refs = status.get("artifactRefs")
    if not isinstance(artifact_refs, dict):
        raise RenderError("run status has no artifactRefs object")
    for kind, expected_path in PUBLIC_PATHS.items():
        reference = artifact_refs.get(kind)
        if reference is not None and reference.get("path") != expected_path:
            raise RenderError(f"run status uses a non-canonical path for {kind}")


def passed_status(
    discovery: dict[str, Any],
    triage: dict[str, Any],
    plan: dict[str, Any],
    governance: dict[str, Any],
) -> dict[str, Any]:
    story_ids = {
        discovery.get("storyId"),
        triage.get("storyId"),
        plan.get("storyId"),
        governance.get("storyId"),
    }
    if len(story_ids) != 1 or not all(isinstance(item, str) and item for item in story_ids):
        raise RenderError("published artifacts do not share one storyId")
    if plan.get("schemaVersion") != PLAN_SCHEMA:
        raise RenderError("implementation plan is not a v2 plan")
    if governance.get("schemaVersion") != GOVERNANCE_SCHEMA:
        raise RenderError("governance report is not a v2 report")
    if governance.get("status") != "passed":
        raise RenderError("a non-passing governance report cannot publish a plan")

    plan_id = require_identifier(plan, "artifactId", "implementation plan")
    payload: dict[str, Any] = {
        "schemaVersion": RUN_SCHEMA,
        "artifactVersion": 2,
        "storyId": next(iter(story_ids)),
        "status": "passed",
        "failedPhase": "none",
        "phaseStates": {phase: "passed" for phase in PHASES},
        "artifactRefs": {
            "discovery": artifact_ref(
                require_identifier(discovery, "artifactId", "discovery"), "discovery"
            ),
            "triage": artifact_ref(
                require_identifier(triage, "artifactId", "triage"), "triage"
            ),
            "implementationPlan": artifact_ref(plan_id, "implementationPlan"),
            "governanceReport": artifact_ref(
                require_identifier(governance, "reportId", "governance report"),
                "governanceReport",
            ),
            "markdownReport": artifact_ref(f"report_{plan_id}", "markdownReport"),
        },
        "planningReview": plan.get("validationStatus", {}).get(
            "ownerReview",
            {"state": "not_required", "owner": None, "reason": None},
        ),
        "ownerReview": {"state": "not_required", "owner": None, "reason": None},
    }
    return finalize_run_status(payload)


def failed_phase_states(failed_phase: str) -> dict[str, str]:
    if failed_phase not in PHASES and failed_phase != "publication":
        raise RenderError(f"unsupported failed phase: {failed_phase}")
    states = {phase: "not_started" for phase in PHASES}
    if failed_phase == "publication":
        for phase in PHASES[:-1]:
            states[phase] = "passed"
        states["rendering"] = "failed"
        return states
    failed_index = PHASES.index(failed_phase)
    for phase in PHASES[:failed_index]:
        states[phase] = "passed"
    states[failed_phase] = "failed"
    if failed_phase != "rendering":
        states["rendering"] = "passed"
    return states


def failed_status(
    story_id: str,
    failed_phase: str,
    reason: str,
    governance: dict[str, Any] | None,
) -> dict[str, Any]:
    if not story_id:
        raise RenderError("storyId is required for owner review")
    if not reason:
        raise RenderError("owner-review reason is required")
    governance_ref = None
    if governance is not None:
        if governance.get("schemaVersion") != GOVERNANCE_SCHEMA:
            raise RenderError("owner-review governance report has an unsupported version")
        governance_ref = artifact_ref(
            require_identifier(governance, "reportId", "governance report"),
            "governanceReport",
        )
    report_identity = stable_id(
        "report_owner_review", {"storyId": story_id, "phase": failed_phase, "reason": reason}
    )
    payload: dict[str, Any] = {
        "schemaVersion": RUN_SCHEMA,
        "artifactVersion": 2,
        "storyId": story_id,
        "status": "needs_owner_review",
        "failedPhase": failed_phase,
        "phaseStates": failed_phase_states(failed_phase),
        "artifactRefs": {
            "discovery": None,
            "triage": None,
            "implementationPlan": None,
            "governanceReport": governance_ref,
            "markdownReport": artifact_ref(report_identity, "markdownReport"),
        },
        "planningReview": {
            "state": "required",
            "owner": "Story owner",
            "reason": "No governed implementation plan is available for review.",
        },
        "ownerReview": {
            "state": "required",
            "owner": "Story owner",
            "reason": reason,
        },
    }
    return finalize_run_status(payload)


def inline(value: Any) -> str:
    if value is None:
        return "not supplied"
    compact = re.sub(r"\s+", " ", str(value)).strip()
    return html.escape(compact, quote=False)


def code(value: Any) -> str:
    return f"`{inline(value).replace('`', '&#96;')}`"


def number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def effort_range(effort: dict[str, Any] | None, *, delta: bool = False) -> str:
    if not effort:
        return "not estimated"
    minimum = effort.get("minimumPersonHours", 0)
    additional = effort.get("additionalPersonHours", 0)
    maximum = minimum + additional
    prefix = "+" if delta else ""
    return f"{prefix}{number(minimum)}–{number(maximum)} person-hours"


def calendar_impact(impact: dict[str, Any] | None) -> str:
    if not impact:
        return "not supplied"
    status = impact.get("status")
    if status == "none":
        return "none"
    if status == "unknown":
        return f"unknown — {inline(impact.get('reason'))}"
    if status == "known":
        minimum = impact.get("minimumElapsedHours", 0)
        maximum = minimum + impact.get("additionalElapsedHours", 0)
        return f"{number(minimum)}–{number(maximum)} elapsed hours"
    return inline(status)


def append_empty(lines: list[str], message: str = "None reported.") -> None:
    lines.extend([message, ""])


def render_success(
    plan: dict[str, Any], governance: dict[str, Any], status: dict[str, Any]
) -> str:
    if status.get("status") != "passed":
        raise RenderError("success renderer requires a passed run status")
    if plan.get("schemaVersion") != PLAN_SCHEMA or governance.get("status") != "passed":
        raise RenderError("success renderer requires a governed v2 plan")
    if len({plan.get("storyId"), governance.get("storyId"), status.get("storyId")}) != 1:
        raise RenderError("renderer inputs do not share one storyId")

    lines = [
        "# Story Start Scope v2 report",
        "",
        f"- Story: {code(plan.get('storyId'))}",
        f"- Structured artifact: {code(plan.get('artifactId'))}",
        f"- Schema: {code(plan.get('schemaVersion'))}",
        "",
        "## 1. Story readiness",
        "",
    ]

    readiness = plan.get("readinessPrerequisites", [])
    if readiness:
        for item in readiness:
            lines.extend(
                [
                    f"### {inline(item.get('summary'))}",
                    "",
                    f"- Status: {code(item.get('status'))}; owner: {inline(item.get('owner'))}",
                    f"- Readiness engineering effort: {effort_range(item.get('engineeringEffort'))}",
                    f"- Readiness calendar impact: {calendar_impact(item.get('calendarImpact'))}",
                    f"- Evidence: {', '.join(code(ref) for ref in item.get('evidenceRefs', []))}",
                    "",
                ]
            )
    else:
        append_empty(lines)

    lines.extend(["## 2. Base implementation plan", ""])
    base_plan = plan.get("basePlan", [])
    if base_plan:
        for task in base_plan:
            lines.extend(
                [
                    f"### {inline(task.get('title'))}",
                    "",
                    f"{inline(task.get('description'))}",
                    "",
                    f"- Acceptance criteria: {', '.join(code(ref) for ref in task.get('acceptanceCriterionRefs', [])) or 'none'}",
                    f"- Source targets: {', '.join(code(ref) for ref in task.get('sourceTargets', [])) or 'none'}",
                    f"- Evidence: {', '.join(code(ref) for ref in task.get('evidenceRefs', []))}",
                    "",
                ]
            )
    else:
        append_empty(lines, "No CORE_SCOPE implementation task was approved.")
    base_effort = plan.get("scenarioEstimates", {}).get("baseEffort")
    lines.extend(
        [
            f"**Base engineering effort: {effort_range(base_effort)}.**",
            "",
            "## 3. Required enablers",
            "",
        ]
    )

    enablers = plan.get("requiredEnablers", [])
    if enablers:
        for enabler in enablers:
            lines.extend(
                [
                    f"### Mandatory additional work — {inline(enabler.get('title'))}",
                    "",
                    f"- Mandatory reason: {code(enabler.get('mandatoryReason'))}",
                    f"- Mandatory delta: **{effort_range(enabler.get('effort'), delta=True)}**",
                    f"- Acceptance criteria: {', '.join(code(ref) for ref in enabler.get('acceptanceCriterionRefs', [])) or 'none'}",
                    f"- Mandatory constraints: {', '.join(code(ref) for ref in enabler.get('mandatoryConstraintRefs', [])) or 'none'}",
                    f"- Evidence: {', '.join(code(ref) for ref in enabler.get('evidenceRefs', []))}",
                ]
            )
            for task in enabler.get("tasks", []):
                lines.append(f"- Task: {inline(task.get('title'))} — {inline(task.get('description'))}")
            lines.append("")
    else:
        append_empty(lines)

    lines.extend(["## 4. Conditional branches", ""])
    decisions = {item.get("id"): item for item in plan.get("decisionRegister", [])}
    groups = {item.get("id"): item for item in plan.get("branchGroups", [])}
    announced_groups: set[str] = set()
    branch_by_id = {item.get("id"): item for item in plan.get("conditionalBranches", [])}
    branches = []
    for group in plan.get("branchGroups", []):
        branches.extend(
            branch_by_id[reference]
            for reference in group.get("branchRefs", [])
            if reference in branch_by_id
        )
    grouped_ids = {item.get("id") for item in branches}
    branches.extend(
        item
        for item in plan.get("conditionalBranches", [])
        if item.get("id") not in grouped_ids
    )
    if branches:
        for branch in branches:
            group_ref = branch.get("groupRef")
            group = groups.get(group_ref, {})
            if group_ref not in announced_groups:
                relationship = group.get("relationship")
                selection = group.get("selectionRule")
                if relationship == "mutually_exclusive":
                    lines.extend(
                        [
                            f"**Mutually exclusive alternatives in group {code(group_ref)}; do not sum them. Selection rule: {code(selection)}.**",
                            "",
                        ]
                    )
                else:
                    lines.extend(
                        [
                            f"Branch group {code(group_ref)}: relationship {code(relationship)}, selection rule {code(selection)}.",
                            "",
                        ]
                    )
                announced_groups.add(group_ref)
            decision = decisions.get(branch.get("decisionRef"), {})
            option = next(
                (
                    item
                    for item in decision.get("options", [])
                    if item.get("id") == branch.get("decisionOptionRef")
                ),
                {},
            )
            lines.extend(
                [
                    f"### If {inline(branch.get('condition'))}",
                    "",
                    f"- Triggering decision: {inline(decision.get('question'))} ({code(branch.get('decisionRef'))})",
                    f"- Option: {inline(option.get('label'))} ({code(branch.get('decisionOptionRef'))})",
                    f"- Conditional delta: **{effort_range(branch.get('effort'), delta=True)}**",
                ]
            )
            for task in branch.get("tasks", []):
                lines.append(f"- Conditional task: {inline(task.get('title'))} — {inline(task.get('description'))}")
            lines.append("")
    else:
        append_empty(lines)

    lines.extend(["## 5. Scenario estimates", ""])
    estimate_set = plan.get("scenarioEstimates", {})
    open_decisions = estimate_set.get("openMaterialDecisionRefs", [])
    if open_decisions:
        lines.extend(
            [
                "**No final committed estimate is available while material decisions remain open.**",
                "",
            ]
        )
    for scenario in estimate_set.get("scenarios", []):
        selected = scenario.get("selectedBranchRefs", [])
        lines.extend(
            [
                f"### {inline(scenario.get('name'))}",
                "",
                f"- Scenario engineering effort: **{effort_range(scenario.get('engineeringTotal'))}**",
                f"- Selected conditional branches: {', '.join(code(ref) for ref in selected) or 'none'}",
                f"- Finality: {code(scenario.get('finality'))}",
                "",
            ]
        )
    final_estimate = estimate_set.get("finalCommittedEstimate")
    if final_estimate is not None:
        lines.extend(
            [
                f"Final committed engineering effort: **{effort_range(final_estimate)}**",
                "",
            ]
        )

    lines.extend(["## 6. Decisions required", ""])
    open_register = [item for item in plan.get("decisionRegister", []) if item.get("status") == "open"]
    if open_register:
        for decision in open_register:
            option_labels = ", ".join(inline(item.get("label")) for item in decision.get("options", []))
            lines.extend(
                [
                    f"- {inline(decision.get('question'))}",
                    f"  - Owner: {inline(decision.get('owner'))}; materiality: {code(decision.get('materiality'))}",
                    f"  - Options: {option_labels}",
                ]
            )
        lines.append("")
    else:
        append_empty(lines)

    related = plan.get("relatedFindings", [])
    defects = [item for item in related if item.get("originCategory") == "RELATED_DEFECT"]
    extras = [item for item in related if item.get("originCategory") in {"RISK_ONLY", "OPTIONAL_IMPROVEMENT"}]
    lines.extend(["## 7. Related findings not included in scope", ""])
    if defects:
        for finding in defects:
            lines.extend(
                [
                    f"- **OUT OF SCOPE — {inline(finding.get('summary'))}**",
                    f"  - Follow-up: {inline(finding.get('followUp'))}; owner: {inline(finding.get('owner'))}",
                ]
            )
        lines.append("")
    else:
        append_empty(lines)

    lines.extend(["## 8. Risks and optional improvements", ""])
    if extras:
        for finding in extras:
            lines.extend(
                [
                    f"- **OUT OF SCOPE {code(finding.get('originCategory'))}** — {inline(finding.get('summary'))}",
                    f"  - Follow-up: {inline(finding.get('followUp'))}; owner: {inline(finding.get('owner'))}",
                ]
            )
        lines.append("")
    else:
        append_empty(lines)

    lines.extend(["## 9. Evidence and provenance", ""])
    evidence = plan.get("evidenceAndProvenance", {}).get("evidenceRefs", [])
    provenance = plan.get("evidenceAndProvenance", {}).get("provenanceRefs", [])
    lines.extend(
        [
            f"- Evidence IDs ({len(evidence)}): {', '.join(code(ref) for ref in evidence[:12]) or 'none'}{'; additional IDs remain in the structured artifact' if len(evidence) > 12 else ''}",
            f"- Provenance IDs ({len(provenance)}): {', '.join(code(ref) for ref in provenance[:12]) or 'none'}{'; additional IDs remain in the structured artifact' if len(provenance) > 12 else ''}",
            "",
            "## 10. Validation/owner-review status",
            "",
            f"- Scope Governor: {code(governance.get('status'))}; semantic validation: {code(governance.get('semanticValidation'))}",
            f"- Governance report: {code(governance.get('reportId'))}; validation pass: {inline(governance.get('validationPass'))}",
            f"- Correction: {inline(governance.get('correction', {}).get('outcome'))} ({inline(governance.get('correction', {}).get('attemptCount'))} attempt)",
        ]
    )
    plan_review = plan.get("validationStatus", {}).get("ownerReview", {})
    if plan_review.get("state") == "required":
        lines.extend(
            [
                f"- Owner review: **required** — {inline(plan_review.get('reason'))}",
                f"- Review owner: {inline(plan_review.get('owner'))}",
            ]
        )
    else:
        lines.append("- Owner review: not required by the current plan state.")
    lines.append("")
    return "\n".join(lines)


def render_owner_review(
    status: dict[str, Any], governance: dict[str, Any] | None
) -> str:
    if status.get("status") != "needs_owner_review":
        raise RenderError("owner-review renderer requires a needs_owner_review status")
    failed_phase = status.get("failedPhase")
    reason = status.get("ownerReview", {}).get("reason")
    lines = [
        "# Story Start Scope v2 report",
        "",
        f"- Story: {code(status.get('storyId'))}",
        f"- Run status: {code(status.get('status'))}",
        "",
    ]
    unavailable = f"Unavailable because the validated v2 pipeline stopped at {code(failed_phase)}."
    for index, title in enumerate(
        [
            "Story readiness",
            "Base implementation plan",
            "Required enablers",
            "Conditional branches",
            "Scenario estimates",
            "Decisions required",
            "Related findings not included in scope",
            "Risks and optional improvements",
            "Evidence and provenance",
        ],
        start=1,
    ):
        lines.extend([f"## {index}. {title}", "", unavailable, ""])
    lines.extend(
        [
            "## 10. Validation/owner-review status",
            "",
            "- Owner review: **required**",
            f"- Failed phase: {code(failed_phase)}",
            f"- Reason: {inline(reason)}",
            "- No implementation plan was published and no legacy/free-form fallback was used.",
        ]
    )
    if governance is not None:
        lines.extend(
            [
                f"- Governance report: {code(governance.get('reportId'))}",
                f"- Governor status: {code(governance.get('status'))}",
            ]
        )
        codes = [item.get("code") for item in governance.get("violations", []) if item.get("code")]
        if codes:
            lines.append(f"- Violation codes: {', '.join(code(item) for item in codes)}")
    lines.append("")
    return "\n".join(lines)


def compatibility(reader_version: int, artifact_path: str) -> dict[str, Any]:
    path = Path(artifact_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {"status": "unreadable", "reason": str(exc), "safeToInterpret": False}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "status": "legacy_readable",
            "artifactKind": "legacy_markdown_or_text",
            "safeToInterpret": False,
            "handling": "preserve_as_is",
        }
    if not isinstance(value, dict):
        return {
            "status": "unsupported",
            "reason": "structured artifact root is not an object",
            "safeToInterpret": False,
        }
    schema = value.get("schemaVersion")
    if reader_version == 1 and isinstance(schema, str) and schema.endswith("/v2"):
        return {
            "status": "unsupported",
            "schemaVersion": schema,
            "reason": "v1 readers must not reinterpret v2 scope branches as cumulative tasks",
            "safeToInterpret": False,
        }
    if reader_version == 2 and schema in {PLAN_SCHEMA, RUN_SCHEMA, GOVERNANCE_SCHEMA}:
        return {
            "status": "supported",
            "schemaVersion": schema,
            "safeToInterpret": True,
        }
    return {
        "status": "unsupported",
        "schemaVersion": schema,
        "reason": "unknown Story Start artifact schema",
        "safeToInterpret": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    passed = subparsers.add_parser("status-passed")
    passed.add_argument("discovery")
    passed.add_argument("triage")
    passed.add_argument("plan")
    passed.add_argument("governance")
    passed.add_argument("output")

    failed = subparsers.add_parser("status-failed")
    failed.add_argument("story_id")
    failed.add_argument("failed_phase")
    failed.add_argument("reason")
    failed.add_argument("output")
    failed.add_argument("--governance")

    render = subparsers.add_parser("render")
    render.add_argument("status")
    render.add_argument("output")
    render.add_argument("--plan")
    render.add_argument("--governance")

    inspect = subparsers.add_parser("compatibility")
    inspect.add_argument("reader_version", type=int, choices=(1, 2))
    inspect.add_argument("artifact")

    validate = subparsers.add_parser("validate-status")
    validate.add_argument("status")

    args = parser.parse_args()
    try:
        if args.command == "status-passed":
            value = passed_status(
                load_json(args.discovery),
                load_json(args.triage),
                load_json(args.plan),
                load_json(args.governance),
            )
            atomic_json(args.output, value)
        elif args.command == "status-failed":
            governance = load_json(args.governance) if args.governance else None
            atomic_json(
                args.output,
                failed_status(args.story_id, args.failed_phase, args.reason, governance),
            )
        elif args.command == "render":
            status = load_json(args.status)
            governance = load_json(args.governance) if args.governance else None
            if status.get("status") == "passed":
                if not args.plan or governance is None:
                    raise RenderError("passed status requires plan and governance inputs")
                markdown = render_success(load_json(args.plan), governance, status)
            else:
                markdown = render_owner_review(status, governance)
            atomic_write(args.output, markdown)
        elif args.command == "compatibility":
            print(
                json.dumps(
                    compatibility(args.reader_version, args.artifact),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        else:
            validate_run_status(load_json(args.status))
    except RenderError as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
