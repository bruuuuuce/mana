#!/usr/bin/env python3
"""Offline conditional wait scenarios from validated Timeline artifacts and a sidecar."""

import argparse
import html
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
from skill_factory.transactions.wait_dependencies import (  # noqa: E402
    BUDGETS,
    BudgetExceeded,
    RejectedInput,
    _derive_report,
    build_report,
    parse_json,
)
from skill_factory.transactions.wait_validation import validate_report  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def read_bounded(path, limit):
    if path.is_symlink() or not path.is_file():
        raise RejectedInput("input must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise BudgetExceeded("input byte budget exceeded; coverage INCOMPLETE")
    return raw


def diagram(graph, title, edges=None):
    lines = [
        "%% " + title,
        "%% CONDITIONAL only. Arrows are waiter -> blocker (or caller -> callee).",
        "flowchart LR",
    ]
    labels = {}
    for index, node in enumerate(graph["nodes"], 1):
        alias = "N" + str(index)
        labels[node["id"]] = alias
        ns = node["namespace"]
        label = (
            ns["participantId"]
            + "/"
            + (ns.get("originalPhysicalId") or ns.get("originalFrameId") or "UNKNOWN")
        )
        lines.append("  " + alias + '["' + html.escape(label, quote=True) + '"]')
    for edge in graph["edges"] if edges is None else edges:
        label = edge.get("resource", "completion") + " CONDITIONAL"
        if "cut" in edge:
            label += " cut=" + edge["cut"]
        lines.append(
            "  " + labels[edge["from"]] + ' -->|"' + label + '"| ' + labels[edge["to"]]
        )
    return "\n".join(lines) + "\n"


def artifacts(report, diagnostics=None):
    result = {
        "wait-dependency.json": (
            json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
        ).encode(),
        "application.mmd": diagram(
            report["applicationGraph"], "Application completion graph"
        ).encode(),
    }
    if len(result["wait-dependency.json"]) > BUDGETS["sidecarBytes"]:
        raise BudgetExceeded("serialized S02 report exceeds 2 MiB; coverage INCOMPLETE")
    report = diagnostics if diagnostics is not None else report
    lines = [
        "# Conditional wait dependency scenario",
        "",
        report["assessment"]["result"],
        "",
        "Coverage: "
        + report["coverage"]["status"]
        + ". Runtime: NOT RUN. Global risk absence: NOT ASSERTED.",
        "",
        "Inputs are referenced by exact-byte SHA-256; embedded T01 uses the documented canonical JSON digest.",
        "",
        "## Application graph",
        "",
        "```mermaid",
        result["application.mmd"].decode().rstrip(),
        "```",
        "",
    ]
    if report["assessment"]["result"] == "UNKNOWN":
        lines[4:4] = [
            "Insufficient evidence to qualify the modeled cut. An empty database graph does not establish absence of dependencies or cycles.",
            "",
        ]
    if report["assessment"].get("exclusionProof"):
        proof = report["assessment"]["exclusionProof"]
        lines += ["Exclusion: " + proof["kind"] + " (" + proof["rule"] + ").", ""]
    for cut in report["assessment"]["cuts"]:
        edges = [e for e in report["databaseGraph"]["edges"] if e["cut"] == cut["cut"]]
        text = diagram(
            report["databaseGraph"], "DB graph: one common cut " + cut["cut"], edges
        )
        result["database-" + cut["cut"] + ".mmd"] = text.encode()
        lines += [
            "## Cut " + cut["cut"],
            "",
            cut["result"],
            "",
            "```mermaid",
            text.rstrip(),
            "```",
            "",
        ]
        if (
            cut.get("exclusionProof")
            and cut["exclusionProof"]["kind"] == "STRUCTURAL_EXCLUSION"
        ):
            proof = cut["exclusionProof"]
            lines += ["", "Exclusion: " + proof["kind"] + " (" + proof["rule"] + ")."]
            if proof["kind"] == "STRUCTURAL_EXCLUSION":
                lines += [
                    "Acyclic source upper bound; missing lock evidence remains unknown. Possible edges in this proof are not qualified DB waits."
                ]
        for problem in cut["contradictions"] + cut["unknowns"]:
            lines.append("- " + problem)
    if not report["assessment"]["cuts"]:
        result["database.mmd"] = diagram(
            report["databaseGraph"], "No witness cut; no qualified DB waits"
        ).encode()
    lines += ["", "## Obligations", ""]
    for c in report["waitCandidates"]:
        lines += [
            "- "
            + c["id"]
            + " / "
            + c["cut"]
            + ": "
            + c["waiter"]
            + " -> "
            + c["holder"]
            + " — "
            + c["status"]
        ]
        for w in c["obligations"]:
            lines += [
                "  - "
                + w["id"]
                + " "
                + w["state"]
                + ": "
                + w["reason"]
                + " Premises: "
                + ", ".join(w["premises"])
            ]
    lines += ["", "## Coverage and limits", ""]
    if (
        report["assessment"]["result"] == "UNKNOWN"
        or any(
            c.get("exclusionProof", {}).get("kind") == "STRUCTURAL_EXCLUSION"
            for c in report["assessment"]["cuts"]
            if c.get("exclusionProof")
        )
        or report["assessment"].get("exclusionProof")
    ):
        for unknown in report["unknowns"]:
            lines.append(
                "- "
                + unknown["reason"]
                + ": "
                + ", ".join(unknown.get("missingObligations", []))
            )
    lines += [
        "- " + reason for reason in report["coverage"]["reasons"] + report["limits"]
    ]
    # Cross-layer links are deliberately outside the database diagram.
    cross = [
        "%% Typed cross-layer relations; these are not DB wait edges",
        "flowchart LR",
    ]
    aliases = {}

    def label(ns, domain):
        key = (domain, json.dumps(ns, sort_keys=True))
        if key not in aliases:
            alias = "N" + str(len(aliases) + 1)
            aliases[key] = alias
            text = (
                ns["participantId"]
                + "/"
                + (
                    ns.get("originalPhysicalId")
                    or ns.get("originalFrameId")
                    or "UNKNOWN"
                )
            )
            cross.append(
                "  "
                + alias
                + '["'
                + html.escape(domain + " " + text, quote=True)
                + '"]'
            )
        return aliases[key]

    for rel in report["crossLayerRelations"]:
        if rel["type"] == "EXECUTES_IN" and "operation" not in rel:
            a, b = label(rel["frame"], "frame"), label(rel["physical"], "P")
        elif rel["type"] != "EXECUTES_IN":
            a, b = label(rel["physical"], "P"), label(rel["replacement"], "P")
        else:
            continue
        cross.append("  " + a + " -. " + rel["type"] + " .-> " + b)
    result["cross-layer.mmd"] = ("\n".join(cross) + "\n").encode()
    lines += [
        "",
        "## Typed cross-layer links",
        "",
        "```mermaid",
        "\n".join(cross),
        "```",
        "",
    ]
    result["report.md"] = ("\n".join(line.rstrip() for line in lines) + "\n").encode()
    return result


def output_location(path):
    absolute = path.absolute()
    resolved = absolute.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise RejectedInput("output must be external to the Mana checkout")
    if any(p.is_symlink() for p in (absolute, *absolute.parents)):
        raise RejectedInput("output must use a canonical path without symlinks")
    if {".agents", ".codex", ".aws", ".git", "skills"} & set(resolved.parts):
        raise RejectedInput("output intersects a configuration/discovery surface")
    if resolved.exists():
        raise RejectedInput("output already exists; refusing overwrite")
    return resolved


def publish(output, files):
    output = output_location(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the destination exclusively; failure never touches another result.
    output.mkdir(mode=0o700)
    try:
        for name, raw in files.items():
            with (output / name).open("xb") as stream:
                stream.write(raw)
    except Exception:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", action="append", default=[], metavar="ID=PATH")
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--validate",
        type=Path,
        help="Validate an existing S02 report against its original inputs",
    )
    args = parser.parse_args()
    try:
        if bool(args.output_dir) == bool(args.validate):
            raise RejectedInput("choose exactly one of --output-dir or --validate")
        if args.output_dir:
            output_location(args.output_dir)
        raw_inputs = {}
        for value in args.timeline:
            name, sep, path = value.partition("=")
            if not sep or name in raw_inputs:
                raise RejectedInput("expected unique ID=PATH timeline arguments")
            raw_inputs[name] = read_bounded(Path(path), BUDGETS["timelineBytes"])
            if sum(len(raw) for raw in raw_inputs.values()) > BUDGETS["combinedBytes"]:
                raise BudgetExceeded(
                    "combined input exceeds 8 MiB; coverage INCOMPLETE"
                )
        sidecar = parse_json(
            read_bounded(args.scenario, BUDGETS["sidecarBytes"]),
            BUDGETS["sidecarBytes"],
        )
        if args.validate:
            # The serialized S02 report is subject to the sidecar byte budget.
            report = parse_json(
                read_bounded(args.validate, BUDGETS["sidecarBytes"]),
                BUDGETS["sidecarBytes"],
            )
            if report["scenario"] != sidecar:
                raise RejectedInput("report references another sidecar")
        else:
            report = build_report(raw_inputs, sidecar)
        validate_report(report, raw_inputs)
        diagnostics, _ = _derive_report(raw_inputs, sidecar)
        if args.output_dir:
            publish(args.output_dir, artifacts(report, diagnostics))
        print(
            json.dumps(
                {
                    "status": "VALIDATED" if args.validate else report["status"],
                    "assessment": report["assessment"]["result"],
                    "coverage": report["coverage"]["status"],
                    "exclusionProofs": [
                        c["exclusionProof"]["kind"]
                        for c in diagnostics["assessment"]["cuts"]
                        if c.get("exclusionProof")
                    ]
                    + (
                        [diagnostics["assessment"]["exclusionProof"]["kind"]]
                        if diagnostics["assessment"].get("exclusionProof")
                        else []
                    ),
                }
            )
        )
        return 0
    except (
        ValueError,
        OSError,
        RuntimeError,
        KeyError,
        TypeError,
        RecursionError,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "BUDGET_EXCEEDED"
                    if isinstance(exc, BudgetExceeded)
                    else "REJECTED_INPUT",
                    "coverage": "INCOMPLETE",
                    "published": False,
                    "reason": str(exc),
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
