"""Bounded independent F03 review: source alternatives, wire and budget guards.

Historical runners remain unchanged. This runner supplements their receipts;
it does not normalize historical failures or qualify runtime evidence.
"""

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wire = load("review_wire", "tests/wait-dependencies-wire-compatibility.py")
prior = load(
    "review_source", "docs/reports/TRANSACTION-01-T02-S02-I01-F02-R1-checks.py"
)
wd, val = wire.wd, wire.val
NEG = wire.NEG


def main():
    evidence = {"task": "MANA-TRANSACTION-01-T02-S02-I01-F03-R1", "checks": []}
    wire.f02.f.WaitTests.setUpClass()
    try:
        generations = wire.historical_modules()
        rows = []
        for case in ("A", "B", "C"):
            raw, scenario = wire.f02.load(case)
            reports = {
                "pre-F02": generations["pre-F02"][0].build_report(raw, scenario),
                "F03": wd.build_report(raw, scenario),
            }
            # Exact objects imply identical structure, fields, enum values and
            # evidence references. Parsing and semantic acceptance are separate.
            assert reports["pre-F02"] == reports["F03"]
            for producer, report in reports.items():
                decoded = json.loads(json.dumps(report, allow_nan=False))
                assert decoded == report
                for consumer, validator in (
                    ("pre-F02", generations["pre-F02"][1]),
                    ("F03", val),
                ):
                    assert validator.validate_report(decoded, raw)
                    rows.append(
                        {
                            "case": case,
                            "producer": producer,
                            "consumer": consumer,
                            "parsing": "PASS",
                            "structureFieldsEnums": "PASS",
                            "semantics": "PASS",
                            "authority": "CONDITIONAL_STATIC_ONLY",
                        }
                    )
        evidence["wireMatrix"] = rows
        for name in ("B-no-pending", "B-one-incomplete-cut", "required", "nested"):
            if name.startswith("B"):
                raw, scenario = wire.f02.load("B")
                if name == "B-no-pending":
                    scenario["cuts"][0]["pending"] = []
                else:
                    other = copy.deepcopy(scenario["cuts"][0])
                    other.update(id="missing", holdings=[])
                    scenario["cuts"].append(other)
            else:
                raw = {"t": wire.f02.f.WaitTests.models[name]}
                scenario = wire.f02.f.scenarios.clear_lock_scenario(
                    wire.f02.f.scenarios.scenario(raw, [("a", "t")], name)
                )
                wire.f02.f.scenarios.cut(scenario, raw, "incomplete", ["a2"], [])
            # Reads all observations, lifetime events and frame stacks directly;
            # enumerates every subgraph and uses Warshall reachability.
            alternatives = [
                prior.alternatives(raw, scenario, c) for c in scenario["cuts"]
            ]
            assert all(a["allAlternativesAcyclic"] for a in alternatives)
            report = wd.build_report(raw, scenario)
            assert report["assessment"]["result"] == NEG
            assert report["coverage"]["status"] == "INCOMPLETE"
            assert val.validate_report(report, raw)
            old = wire.acceptance(generations["pre-F02"][1], report, raw)
            assert not old["accepted"]
            evidence["checks"].append(
                {"case": name, "sourceAlternatives": alternatives, "oldConsumer": old}
            )
        raw, scenario = wire.f02.load("B")
        scenario["cuts"][0]["holdings"] = []
        report = wd.build_report(raw, scenario)
        diagnostics, _ = wd._derive_report(raw, scenario)
        graph_edges = sum(
            len(report[k]["edges"]) for k in ("databaseGraph", "applicationGraph")
        ) + len(report["crossLayerRelations"])
        assert report["coverage"]["serializedEdges"] == graph_edges
        assert diagnostics["coverage"]["serializedEdges"] > graph_edges
        for limits in (
            {"serializedEdges": graph_edges},
            {
                "candidateComparisons": diagnostics["coverage"]["candidateComparisons"]
                - 1
            },
        ):
            with patch.dict(wd.BUDGETS, limits):
                try:
                    wd.build_report(raw, scenario)
                except wd.BudgetExceeded:
                    pass
                else:
                    raise AssertionError("proof work escaped budget: " + str(limits))
        evidence["budgets"] = {
            "publicEdges": graph_edges,
            "internalEdges": diagnostics["coverage"]["serializedEdges"],
            "proofWorkCharged": True,
        }
        # A missing public certificate cannot turn producer declarations into
        # authority. Preserve rejection even if final reprojection is corrupted.
        for case in ("A", "C"):
            raw, scenario = wire.f02.load(case)
            scenario["cuts"][0]["holdings"] = []
            report = wd.build_report(raw, scenario)
            assert report["assessment"]["result"] == "UNKNOWN"
            report["assessment"]["result"] = NEG
            report["assessment"]["cuts"][0]["result"] = NEG
            with patch.object(val, "build_report", return_value=report) as mocked:
                try:
                    val.validate_report(report, raw)
                except wd.RejectedInput:
                    pass
                else:
                    raise AssertionError("unsupported negative accepted")
                mocked.assert_not_called()
        evidence["status"] = "PASS"
    finally:
        wire.f02.f.WaitTests.tearDownClass()
    print(json.dumps(evidence, indent=2))
    if os.environ.get("MANA_F03_R1_EVIDENCE"):
        Path(os.environ["MANA_F03_R1_EVIDENCE"]).write_text(
            json.dumps(evidence, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
