#!/usr/bin/env python3
"""Minimal O-D01/O-E01 counterexamples: same P, coherent cut, no lock evidence."""

import copy
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "fixtures", ROOT / "tests/wait-dependencies.py"
)
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def main():
    results = []
    f.WaitTests.setUpClass()
    try:
        for kind in ("required", "nested"):
            raw = {"t": f.WaitTests.models[kind]}
            timeline = json.loads(raw["t"])
            assert len(timeline["transactionModel"]["physicalTransactions"]) == 1
            observations = timeline["observations"]
            assert all(
                o["transactionContext"]["physicalId"] == "P1" for o in observations
            )
            s = {
                "schema": "mana.wait-scenario/v1",
                "id": "minimal_" + kind,
                "inputs": [{"id": "t", "sha256": f.wd.digest(raw["t"])}],
                "participants": [{"id": "a", "input": "t", "independence": None}],
                "premises": [],
                "resources": [],
                "operations": [
                    {
                        "id": "op" + str(i),
                        "participant": "a",
                        "observation": o["id"],
                        "resource": None,
                        "binding": {
                            "datasource": None,
                            "database": None,
                            "enlisted": None,
                            "premise": None,
                        },
                        "request": {"mode": None, "premise": None},
                    }
                    for i, o in enumerate(observations)
                ],
                "lockRule": {
                    "id": "none",
                    "version": 1,
                    "modes": [],
                    "compatibility": [],
                    "blockingPremise": None,
                },
                "cuts": [],
            }
            before = f.wd.build_report(raw, s)
            changed = copy.deepcopy(s)
            changed["cuts"] = [
                {
                    "id": "coherent",
                    "prefixes": {
                        "a": observations[1]["placement"]["beforeT01Sequence"]
                    },
                    "pending": ["op1"],
                    "holdings": [],
                    "temporal": {"kind": "UNKNOWN", "premise": None},
                }
            ]
            after = f.wd.build_report(raw, changed)
            f.validate_report(after, raw)
            expected = "NO_CYCLE_IN_MODELED_SCENARIO"
            assert before["assessment"]["result"] == expected
            assert not after["assessment"]["cuts"][0]["contradictions"]
            results.append(
                {
                    "case": kind,
                    "expected": expected,
                    "actual": after["assessment"],
                    "validatorAccepted": True,
                    "status": "PASS"
                    if after["assessment"]["result"] == expected
                    else "FAIL",
                    "proof": "Exactly one physical identity; D00 W1 forbids every inter-P edge independently of W4.",
                }
            )
    finally:
        f.WaitTests.tearDownClass()
    print(json.dumps(results, indent=2))
    return int(any(r["status"] == "FAIL" for r in results))


if __name__ == "__main__":
    sys.exit(main())
