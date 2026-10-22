#!/usr/bin/env python3
"""Explicit read-only Java/Spring scenario analysis; never activates a candidate."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "mana_factory_host", ROOT / "scripts/mana-skill-factory.py"
)
factory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(factory)
from skill_factory.transactions.model import build, validate_model  # noqa: E402
from skill_factory.transactions.plantuml import render  # noqa: E402
from skill_factory.transactions.source import java_facts  # noqa: E402


def context_input(path, raw=None):
    context = factory.bounded_json(factory.read_file(path) if raw is None else raw)
    required = {
        "schema",
        "initialState",
        "entryThroughProxy",
        "managerCapabilities",
    }
    if (
        not isinstance(context, dict)
        or not required <= set(context)
        or set(context) - required - {"aspectjWeaving", "resourceLeafPolicy"}
    ):
        raise factory.FactoryError("invalid transaction context fields")
    if context.get("resourceLeafPolicy", "DISABLED") not in (
        "DISABLED",
        "JDBC_LITERAL_V1",
    ):
        raise factory.FactoryError(
            "resourceLeafPolicy must be DISABLED or JDBC_LITERAL_V1"
        )
    if context.get("aspectjWeaving", "UNKNOWN") not in (
        "UNKNOWN",
        "ASSUMED_APPLIED",
    ):
        raise factory.FactoryError(
            "aspectjWeaving must be UNKNOWN or ASSUMED_APPLIED; never runtime proof"
        )
    if (
        context["schema"] != "mana.transaction-context/v1"
        or context["initialState"] not in ["NO_TRANSACTION", "UNKNOWN"]
        or type(context["entryThroughProxy"]) is not bool
    ):
        raise factory.FactoryError("invalid explicit entry scenario")
    if not isinstance(context["managerCapabilities"], dict):
        raise factory.FactoryError("managerCapabilities must be an object")
    for caps in context["managerCapabilities"].values():
        if (
            not isinstance(caps, dict)
            or set(caps) != {"suspend", "savepoints"}
            or any(v is not None and type(v) is not bool for v in caps.values())
        ):
            raise factory.FactoryError(
                "manager capabilities require explicit true/false/null suspend and savepoints"
            )
    return context


def analyze(project, context_path, entry, *, include_facts=False):
    project = factory.canonical_project(project)
    context_raw = factory.read_file(context_path)
    context = context_input(context_path, context_raw)
    adapter = factory.adapter_for("transaction-analysis")
    files = factory.project_files(project, adapter)
    adapter.specialize(
        files
    )  # Same technology/applicability gate; generation is separate.
    facts = java_facts(factory, project, files)
    report = build(facts, context, entry)
    report["evidence"] = [
        {"path": p, "sha256": factory.digest(raw)} for p, raw in sorted(files.items())
    ]
    report["contextEvidence"] = {
        "sha256": factory.digest(context_raw),
        "origin": "EXPLICIT_SCENARIO_NOT_RUNTIME_PROOF",
        "path": context_path.resolve().relative_to(project).as_posix()
        if project in context_path.resolve().parents
        else "EXTERNAL_CONTEXT",
    }
    validate_model(report)
    # Detect source changes during the bounded run, never repair/reset the target.
    if (
        factory.project_files(project, adapter) != files
        or factory.read_file(context_path) != context_raw
    ):
        raise factory.FactoryError(
            "source changed during analysis; result not published"
        )
    return (report, facts) if include_facts else report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--entry", required=True, help="Fully qualified Class#method()")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        project = factory.canonical_project(args.project_root)
        output = factory.candidate_location(args.output_dir, project)
        if output.exists():
            raise factory.FactoryError("output already exists; refusing overwrite")
        report = analyze(project, args.context, args.entry)
        diagram = render(report)
        raw = (json.dumps(report, indent=2) + "\n").encode()
        if len(raw) > 4 * 1024 * 1024:
            raise factory.FactoryError("transaction result exceeds 4 MiB output budget")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(mode=0o700)
        try:
            (output / "transaction-model.json").write_bytes(raw)
            (output / "sequence.puml").write_text(diagram, encoding="utf-8")
        except Exception:
            for name in ["transaction-model.json", "sequence.puml"]:
                (output / name).unlink(missing_ok=True)
            output.rmdir()
            raise
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "frames": len(report["frames"]),
                    "uncertainties": len(report["uncertainties"]),
                    "candidateActivated": False,
                }
            )
        )
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(
            json.dumps(
                {"status": "blocked", "reason": str(exc), "candidateActivated": False}
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
