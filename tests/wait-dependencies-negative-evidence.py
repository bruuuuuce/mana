#!/usr/bin/env python3
"""F01 D00 regressions: source evidence gates negative claims independently.

Oracles: D00 sections 4-6/9; O-B01/B03/C02/D01/E01/F05/G02.
Existing synthetic examples are inputs, never expected verdict generators.
"""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from skill_factory.transactions import wait_dependencies as wd  # noqa: E402
from skill_factory.transactions import wait_validation as validator  # noqa: E402

NEGATIVE = "NO_CYCLE_IN_MODELED_SCENARIO"

# Reuse the source-only oracle, not the historical public-layout assertions.
spec = importlib.util.spec_from_file_location(
    "historical_f02_oracle", ROOT / "tests/wait-dependencies-proof-exclusions.py"
)
historical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(historical)


def load(case):
    base = ROOT / "docs/examples/transaction-01-t02-s02" / case
    scenario = json.loads((base / "scenario.json").read_bytes())
    raw = {
        i["id"]: (base / "inputs" / (i["id"] + ".json")).read_bytes()
        for i in scenario["inputs"]
    }
    return raw, scenario


def promote(report):
    forged = copy.deepcopy(report)
    forged["assessment"]["result"] = NEGATIVE
    forged["unknowns"] = []
    forged["coverage"]["status"] = "COMPLETE_MODELED_SCOPE"
    forged["coverage"]["reasons"] = []
    for cut in forged["assessment"]["cuts"]:
        cut["result"] = NEGATIVE
        cut["unknowns"] = []
    for candidate in forged["waitCandidates"]:
        candidate["status"] = "EXCLUDED"
        for w in candidate["obligations"]:
            if w["state"] == "UNKNOWN":
                w["state"] = "MODEL_EVIDENCE"
    return forged


class NegativeEvidenceTests(unittest.TestCase):
    def build(self, raw, scenario):
        original = copy.deepcopy(scenario)
        raw_before = dict(raw)
        report = wd.build_report(raw, scenario)
        self.assertTrue(validator.validate_report(report, raw))
        self.assertEqual(scenario, original)
        self.assertEqual(raw, raw_before)
        return report

    def independent_rejection(self, report, raw):
        # Simulate the original failure mode: the producer repeats its own bug.
        # Acceptance must not depend on report == build_report(...).
        with patch.object(validator, "build_report", return_value=report) as producer:
            with self.assertRaises(wd.RejectedInput):
                validator.validate_report(report, raw)
            producer.assert_not_called()

    def assert_source_exclusion(self, raw, scenario, cut, expected_db_pairs):
        # Every source observation must be selected. The independent oracle reads
        # source positions/frame stacks and rejects unresolved frontiers; it never
        # reads producer verdicts, ledgers or exclusion certificates.
        for participant in scenario["participants"]:
            timeline = json.loads(raw[participant["input"]])
            self.assertEqual(
                {
                    o["observation"]
                    for o in scenario["operations"]
                    if o["participant"] == participant["id"]
                },
                {o["id"] for o in timeline["observations"]},
            )
        bound = historical.source_upper_bound(raw, scenario, cut)
        self.assertEqual(bound["dbPairs"], expected_db_pairs)
        self.assertEqual(bound["appPairs"], [])
        self.assertTrue(bound["acyclic"])

    def test_01_r1_A_and_C_missing_W4_generate_unknown(self):
        for case, app in (("A", 0), ("C", 1)):
            with self.subTest(case=case):
                raw, s = load(case)
                s["cuts"][0]["holdings"] = []
                r = self.build(raw, s)
                self.assertEqual(r["assessment"]["result"], "UNKNOWN")
                self.assertEqual(r["assessment"]["cuts"][0]["result"], "UNKNOWN")
                self.assertIn(
                    "W4: NO_ORIENTED_WAIT_HYPOTHESIS",
                    r["assessment"]["cuts"][0]["unknowns"],
                )
                self.assertEqual(r["coverage"]["status"], "INCOMPLETE")
                self.assertEqual(len(r["databaseGraph"]["edges"]), 0)
                self.assertEqual(len(r["applicationGraph"]["edges"]), app)

    def test_02_missing_W4_negative_rejected_without_reprojection(self):
        for case in ("A", "C"):
            raw, s = load(case)
            s["cuts"][0]["holdings"] = []
            self.independent_rejection(promote(self.build(raw, s)), raw)

    def test_03_complete_acyclic_B_retains_negative(self):
        raw, s = load("B")
        r = self.build(raw, s)
        self.assertEqual(r["assessment"]["result"], NEGATIVE)
        self.assertEqual(len(r["databaseGraph"]["edges"]), 1)
        # Broad inventory coverage can be incomplete due to excluded candidates;
        # this is not a missing indispensable premise for the scoped negative.
        self.assertEqual(r["assessment"]["cuts"][0]["unknowns"], [])

    def test_04_complete_A_compatible_cycle(self):
        raw, s = load("A")
        r = self.build(raw, s)
        self.assertEqual(r["assessment"]["result"], "CONDITIONAL_CYCLE_RISK")
        self.assertEqual(len(r["databaseGraph"]["edges"]), 2)
        self.independent_rejection(promote(r), raw)
        forged = promote(r)
        forged["databaseGraph"]["edges"] = []
        forged["claims"] = [
            c for c in forged["claims"] if c["category"] != "DB_WAIT_DEPENDENCY"
        ]
        for cut in forged["assessment"]["cuts"]:
            cut["claims"] = []
        self.independent_rejection(forged, raw)

    def test_05_incompatible_holdings_exclude_cycle(self):
        raw, s = load("B")
        s["cuts"][0].update(
            prefixes={"a": 5, "b": 5},
            pending=["a2", "b2"],
            holdings=[
                {
                    "operation": h,
                    "acquisitionPremise": h + "_acquire",
                    "retentionPremise": h + "_retain",
                }
                for h in ("a1", "b1")
            ],
        )
        r = self.build(raw, s)
        self.assertEqual(r["assessment"]["result"], NEGATIVE)
        self.assertFalse(r["databaseGraph"]["edges"])
        self.assertIn(
            "simultaneous incompatible holdings on the same opaque target",
            r["assessment"]["cuts"][0]["contradictions"],
        )

    def test_06_missing_W4_positive_promotion_rejected(self):
        for case in ("A", "C"):
            raw, s = load(case)
            positive = self.build(raw, s)
            s["cuts"][0]["holdings"] = []
            positive["scenario"] = s
            with self.assertRaises(wd.RejectedInput):
                validator.validate_report(positive, raw)

    def test_07_opaque_object_without_overlap_is_unknown(self):
        raw, s = load("A")
        for resource in s["resources"]:
            resource["lockTargetOverlap"] = "UNKNOWN"
        r = self.build(raw, s)
        self.assertEqual(r["assessment"]["result"], "UNKNOWN")
        self.assertFalse(r["databaseGraph"]["edges"])
        self.independent_rejection(promote(r), raw)

    def test_08_budget_never_returns_negative(self):
        raw, s = load("B")
        for budget in ("candidateComparisons", "serializedEdges"):
            with self.subTest(budget=budget), patch.dict(wd.BUDGETS, {budget: 1}):
                with self.assertRaises(wd.BudgetExceeded):
                    wd.build_report(raw, s)

    def test_09_declared_W4_does_not_replace_source_evidence(self):
        raw, s = load("A")
        for holding in s["cuts"][0]["holdings"]:
            pid = holding["acquisitionPremise"]
            next(p for p in s["premises"] if p["id"] == pid)["state"] = "UNKNOWN"
        r = self.build(raw, s)
        self.assertEqual(r["assessment"]["result"], "UNKNOWN")
        self.independent_rejection(promote(r), raw)
        # Sidecar MODEL_EVIDENCE is not an authority for the original model.
        s["premises"][0]["state"] = "MODEL_EVIDENCE"
        with self.assertRaises(wd.RejectedInput):
            wd.build_report(raw, s)

    def test_10_requires_new_application_dependencies_preserved(self):
        raw, s = load("C")
        before = self.build(raw, s)
        s["cuts"][0]["holdings"] = []
        after = self.build(raw, s)
        self.assertEqual(after["crossLayerRelations"], before["crossLayerRelations"])
        fields = (
            "caller",
            "callee",
            "callerPhysical",
            "calleePhysical",
            "source",
            "resource",
        )

        def app(r):
            return [
                {k: c[k] for k in fields}
                for c in r["claims"]
                if c["category"] == "APPLICATION_WAIT_DEPENDENCY"
            ]

        self.assertEqual(app(after), app(before))
        self.assertEqual(len(app(after)), 1)

    def test_11_missing_pending_and_premise_dependency(self):
        raw, s = load("B")
        s["cuts"][0]["pending"] = []
        self.assert_source_exclusion(raw, s, s["cuts"][0], [(("b", "P1"), ("a", "P1"))])
        r = self.build(raw, s)
        self.assertEqual(r["assessment"]["result"], NEGATIVE)
        self.assertEqual(r["coverage"]["status"], "INCOMPLETE")
        raw, s = load("A")
        for holding in s["cuts"][0]["holdings"]:
            acquire = next(
                p for p in s["premises"] if p["id"] == holding["acquisitionPremise"]
            )
            retain = next(
                p for p in s["premises"] if p["id"] == holding["retentionPremise"]
            )
            acquire["state"] = "UNKNOWN"
            retain["dependsOn"] = [acquire["id"]]
        r = self.build(raw, s)
        self.assertEqual(r["assessment"]["result"], "UNKNOWN")
        self.independent_rejection(promote(r), raw)

    def test_12_acyclic_incomplete_cuts_retain_scoped_negative(self):
        raw, s = load("B")
        missing = copy.deepcopy(s["cuts"][0])
        missing["id"] = "missing"
        missing["holdings"] = []
        s["cuts"].append(missing)
        for cut in s["cuts"]:
            self.assert_source_exclusion(raw, s, cut, [(("b", "P1"), ("a", "P1"))])
        r = self.build(raw, s)
        self.assertEqual(
            [c["result"] for c in r["assessment"]["cuts"]], [NEGATIVE, NEGATIVE]
        )
        self.assertEqual(r["assessment"]["result"], NEGATIVE)
        self.assertEqual(r["coverage"]["status"], "INCOMPLETE")
        self.assertTrue(r["assessment"]["cuts"][1]["unknowns"])
        # The negative is justified; falsely complete coverage is still rejected.
        self.independent_rejection(promote(r), raw)

    def test_13_cli_unknown_invalid_negative_and_budget(self):
        with tempfile.TemporaryDirectory(prefix="mana-f01-cli-") as tmp:
            stage = Path(tmp).resolve()
            for case in ("A", "B", "C"):
                raw, s = load(case)
                if case != "B":
                    s["cuts"][0]["holdings"] = []
                scenario = stage / (case + ".json")
                scenario.write_text(json.dumps(s))
                args = [
                    sys.executable,
                    str(ROOT / "scripts/mana-wait-dependencies.py"),
                    "--scenario",
                    str(scenario),
                ]
                for key, value in raw.items():
                    path = stage / (case + "-" + key + ".json")
                    path.write_bytes(value)
                    args += ["--timeline", key + "=" + str(path)]
                output = stage / case
                result = subprocess.run(
                    args + ["--output-dir", str(output)], capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout)["assessment"],
                    NEGATIVE if case == "B" else "UNKNOWN",
                )
                report = json.loads((output / "wait-dependency.json").read_bytes())
                if case != "B":
                    self.assertIn("W4", (output / "report.md").read_text())
                    forged = stage / (case + "-forged.json")
                    forged.write_text(json.dumps(promote(report)))
                    bad = subprocess.run(
                        args + ["--validate", str(forged)],
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(bad.returncode, 2)
                    self.assertEqual(bad.stdout, "")
                    self.assertEqual(json.loads(bad.stderr)["status"], "REJECTED_INPUT")
                    self.assertIn("W4", json.loads(bad.stderr)["reason"])
                valid = subprocess.run(
                    args + ["--validate", str(output / "wait-dependency.json")],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(valid.returncode, 0, valid.stderr)
                scenario.write_bytes(b" " * (wd.BUDGETS["sidecarBytes"] + 1))
                target = stage / (case + "-budget")
                limited = subprocess.run(
                    args + ["--output-dir", str(target)], capture_output=True, text=True
                )
                self.assertEqual(limited.returncode, 2)
                self.assertEqual(
                    json.loads(limited.stderr)["status"], "BUDGET_EXCEEDED"
                )
                self.assertFalse(target.exists())

    def test_14_partial_holder_omission_cannot_prove_acyclicity(self):
        raw, s = load("A")
        s["cuts"][0]["holdings"].pop()
        r = self.build(raw, s)
        self.assertEqual(r["assessment"]["result"], "UNKNOWN")
        self.assertEqual(len(r["databaseGraph"]["edges"]), 1)
        self.assertTrue(any("W4" in u for u in r["assessment"]["cuts"][0]["unknowns"]))
        self.independent_rejection(promote(r), raw)

    def test_15_frontier_stays_unknown_and_same_P_cut_is_acyclic(self):
        # Reuse I01's parse-only synthetic fixtures, not its verdicts/oracles.
        spec = importlib.util.spec_from_file_location(
            "i01_fixtures", ROOT / "tests/wait-dependencies.py"
        )
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        fixture.WaitTests.setUpClass()
        try:
            raw = {"t": fixture.WaitTests.models["frontier"]}
            s = fixture.scenarios.scenario(raw, [("a", "t")], "frontier_f01")
            fixture.scenarios.cut(
                s, raw, "frontier", ["a2"], ["a1"], "OUTER_REQUIRES_NEW"
            )
            s["cuts"][0]["prefixes"]["a"] += 1
            r = self.build(raw, s)
            self.assertEqual(r["assessment"]["result"], "UNKNOWN")
            self.independent_rejection(promote(r), raw)
            for kind in ("required", "nested"):
                raw = {"t": fixture.WaitTests.models[kind]}
                s = fixture.scenarios.clear_lock_scenario(
                    fixture.scenarios.scenario(raw, [("a", "t")], kind)
                )
                self.assertEqual(self.build(raw, s)["assessment"]["result"], NEGATIVE)
                fixture.scenarios.cut(s, raw, "incomplete", ["a2"], [])
                self.assert_source_exclusion(raw, s, s["cuts"][0], [])
                r = self.build(raw, s)
                self.assertEqual(r["assessment"]["result"], NEGATIVE)
                self.assertEqual(r["coverage"]["status"], "INCOMPLETE")
                # No lock/runtime completeness follows from same-P acyclicity.
                self.independent_rejection(promote(r), raw)
        finally:
            fixture.WaitTests.tearDownClass()


if __name__ == "__main__":
    unittest.main()
