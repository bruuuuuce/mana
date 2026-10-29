#!/usr/bin/env python3
"""Explicit offline javac member-binding witness; no transaction decisions."""

import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "member_factory", ROOT / "scripts/mana-skill-factory.py"
)
factory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(factory)
from skill_factory.transactions.entry import select_methods  # noqa: E402
from skill_factory.transactions.semantic import member_bindings, verify_member_snapshot  # noqa: E402
from skill_factory.transactions.source import java_facts  # noqa: E402


def analyze(project, request):
    if not isinstance(request, dict) or set(request) != {
        "sources",
        "entry",
        "dependencies",
        "environment",
    }:
        raise ValueError("invalid explicit member binding request")
    names = request["sources"]
    if (
        not isinstance(names, list)
        or not 1 <= len(names) <= 64
        or len(set(names)) != len(names)
    ):
        raise ValueError("source request budget or duplicate source")
    files = {}
    for name in names:
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or str(relative) != name
            or not name.endswith(".java")
        ):
            raise ValueError("invalid relative source path")
        path = project / name
        if not path.resolve().is_relative_to(project) or path.is_symlink():
            raise ValueError("source path escapes explicit project")
        files[name] = factory.read_file(path)
        if sum(map(len, files.values())) > 2 * 1024 * 1024:
            raise ValueError("source byte budget")
    facts = java_facts(factory, project, files, source_snapshot=True)
    methods, entry = select_methods(
        {c["name"]: c for c in facts["classes"]}, request["entry"]
    )
    evidence = methods[entry][1]["evidence"]
    witness, cost = member_bindings(
        factory,
        project,
        files,
        evidence,
        request["dependencies"],
        request["environment"],
        parse_facts=facts,
    )
    # Dedicated replay is mandatory for a published witness, including negatives.
    verify_member_snapshot(
        witness,
        factory,
        project,
        files,
        request["environment"],
        parse_facts=facts,
        request={
            "entry": evidence,
            "dependencies": sorted(set(request["dependencies"])),
        },
    )
    if any(factory.read_file(project / name) != raw for name, raw in files.items()):
        raise ValueError("source changed during binding analysis")
    return witness, cost


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        project = factory.canonical_project(args.project_root)
        output = factory.candidate_location(args.output_dir, project)
        if output.exists():
            raise ValueError("output already exists")
        raw = factory.read_file(args.request)
        witness, cost = analyze(project, factory.bounded_json(raw))
        if factory.read_file(args.request) != raw:
            raise ValueError("request changed during analysis")
        payload = (json.dumps(witness, indent=2) + "\n").encode()
        if len(payload) > 4 * 1024 * 1024:
            raise ValueError("output budget")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(mode=0o700)
        try:
            (output / "member-bindings.json").write_bytes(payload)
            (output / "cost.json").write_text(json.dumps(cost, indent=2) + "\n")
        except Exception:
            for name in ("member-bindings.json", "cost.json"):
                (output / name).unlink(missing_ok=True)
            output.rmdir()
            raise
        print(
            json.dumps(
                {
                    "status": witness["status"],
                    "reason": witness["reason"],
                    "transactionTraversal": "NOT_ASSERTED",
                }
            )
        )
        return 0 if witness["status"] == "COMPLETE" else 2
    except (ValueError, OSError, RuntimeError, TypeError, KeyError):
        # A malformed request/path/compiler exception may contain source text.
        print(
            json.dumps(
                {"status": "BLOCKED", "reason": "INPUT_TOOLING_OR_VERIFICATION_FAILED"}
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
