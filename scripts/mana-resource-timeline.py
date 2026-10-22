#!/usr/bin/env python3
"""Explicit bounded resource syntax analysis consuming Transaction Model v1."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "mana_t01", ROOT / "scripts/mana-transaction.py"
)
t01 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t01)
from skill_factory.transactions.resources import build_timeline, validate_timeline  # noqa: E402


def analyze(project, context, entry):
    transaction, facts = t01.analyze(project, context, entry, include_facts=True)
    report = build_timeline(transaction, facts)
    validate_timeline(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        project = t01.factory.canonical_project(args.project_root)
        output = t01.factory.candidate_location(args.output_dir, project)
        if output.exists():
            raise ValueError("output already exists; refusing overwrite")
        report = analyze(project, args.context, args.entry)
        raw = (json.dumps(report, indent=2) + "\n").encode()
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("resource timeline exceeds 4 MiB output budget")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(mode=0o700)
        try:
            (output / "resource-timeline.json").write_bytes(raw)
        except Exception:
            (output / "resource-timeline.json").unlink(missing_ok=True)
            output.rmdir()
            raise
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "observations": len(report["observations"]),
                }
            )
        )
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
