#!/usr/bin/env python3
"""Render validated T01/S01/S02 artifacts offline; never run target analysis."""

import argparse
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from skill_factory.transactions.plantuml import render_integrated  # noqa: E402
from skill_factory.transactions.wait_dependencies import BUDGETS, parse_json  # noqa: E402

# Reuse the existing bounded reader and fresh-directory publication contract.
spec = importlib.util.spec_from_file_location(
    "wait_cli", Path(__file__).with_name("mana-wait-dependencies.py")
)
wait_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wait_cli)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", action="append", required=True, metavar="ID=PATH")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw_inputs = {}
        for value in args.timeline:
            name, sep, path = value.partition("=")
            if not sep or name in raw_inputs:
                raise ValueError("expected unique ID=PATH timeline arguments")
            raw_inputs[name] = wait_cli.read_bounded(
                Path(path), BUDGETS["timelineBytes"]
            )
            if sum(map(len, raw_inputs.values())) > BUDGETS["combinedBytes"]:
                raise ValueError("combined timeline byte budget exceeded")
        report = parse_json(
            wait_cli.read_bounded(args.report, BUDGETS["sidecarBytes"]),
            BUDGETS["sidecarBytes"],
        )
        scenario = parse_json(
            wait_cli.read_bounded(args.scenario, BUDGETS["sidecarBytes"]),
            BUDGETS["sidecarBytes"],
        )
        if report["scenario"] != scenario:
            raise ValueError("report references another scenario")
        views = render_integrated(report, raw_inputs)
        wait_cli.publish(
            args.output_dir,
            {name: value.encode("utf-8") for name, value in views.items()},
        )
        print("SOURCE_GENERATED / PlantUML rendering NOT_RUN")
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
            "REJECTED_INPUT / no visualization published: " + str(exc), file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
