#!/usr/bin/env python3
"""MR00 AOP and body-order oracles, independent from build/compose outputs."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads(
    (ROOT / "tests/fixtures/transaction-aop-causal-order/cases.json").read_text()
)
R1 = ROOT / "docs/reports/MANA-TRANSACTION-01-T01-MR01-R1-evidence"
spec = importlib.util.spec_from_file_location(
    "transaction_aop_order", ROOT / "scripts/mana-transaction.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def model(identity):
    return copy.deepcopy(next(c["model"] for c in DATA["cases"] if c["id"] == identity))


class AopCausalOrderTests(unittest.TestCase):
    def test_original_r1_witnesses_are_exact(self):
        originals = [c for c in DATA["cases"] if c["originalWitness"]]
        self.assertEqual(len(originals), 4)
        for case in originals:
            with self.subTest(case=case["id"]):
                self.assertEqual(
                    case["model"],
                    json.loads((R1 / case["originalWitness"]).read_text()),
                )

    def test_each_finding_has_negative_near_positive_uncertainty_and_retention(self):
        by_id = {c["id"]: c for c in DATA["cases"]}
        for negative, positive, uncertain, retained in (
            ("A01", "A04", "A05", "A06"),
            ("C01", "C02", "C03", "C05"),
        ):
            self.assertEqual(by_id[negative]["expected"], "REJECT")
            for identity in (positive, uncertain, retained):
                self.assertEqual(by_id[identity]["expected"], "ACCEPT")
                self.assertTrue(by_id[identity]["normative"])

    def test_synthetic_sources_hashes_spans_and_call_sites_are_consistent(self):
        for case in DATA["cases"]:
            if case["source"] is None:  # Exact original v1 artifact, not synthetic.
                continue
            source = case["source"]
            digest = hashlib.sha256(source.encode()).hexdigest()
            report = case["model"]
            with self.subTest(case=case["id"]):
                self.assertEqual(
                    report["evidence"], [{"path": "Synthetic.java", "sha256": digest}]
                )
                for frame in report["frames"]:
                    evidence = frame["evidence"]
                    self.assertEqual(evidence["sha256"], digest)
                    method = frame["calleeMethod"].split("#")[1]
                    self.assertIn(method, source[evidence["start"] : evidence["end"]])
                    if frame["callSite"]:
                        site = frame["callSite"]
                        self.assertEqual(site["sha256"], digest)
                        self.assertIn(method, source[site["start"] : site["end"]])
                for event in report["events"]:
                    if event["kind"] == "UNRESOLVED_CALL":
                        site = event["callSite"]
                        self.assertEqual(site["sha256"], digest)
                        self.assertEqual(
                            source[site["start"] : site["end"]],
                            event["receiver"] + "." + event["method"] + "()",
                        )

    def test_aop_unknown_preserves_common_physical_properties(self):
        report = model("A06")
        self.assertTrue(cli.validate_model(report))
        child = report["frames"][1]
        self.assertEqual(child["interception"]["status"], "UNKNOWN")
        self.assertEqual(
            child["duringState"],
            {"kind": "TRANSACTION_PHYSICAL", "physicalId": None, "manager": "tx"},
        )
        self.assertEqual(child["afterState"]["physicalId"], "P1")
        self.assertEqual(report["aspectjWeaving"]["runtimeApplication"], "UNKNOWN")
        uncertain = model("A05")
        self.assertTrue(cli.validate_model(uncertain))
        self.assertEqual(uncertain["aspectjWeaving"]["application"], "UNKNOWN")
        self.assertEqual(uncertain["frames"][0]["interception"]["status"], "UNKNOWN")

    def test_unknown_context_does_not_itself_cut_proven_order(self):
        report = model("C06")
        self.assertTrue(cli.validate_model(report))
        first, following = report["frames"][1:]
        self.assertEqual(first["contextComposition"]["premises"]["body"], "EMPTY")
        self.assertEqual(first["afterState"]["kind"], "UNKNOWN")
        self.assertEqual(following["previousState"], first["afterState"])
        self.assertEqual(following["duringState"]["kind"], "UNKNOWN")
        self.assertEqual(len(report["physicalTransactions"]), 1)

    def test_known_prefix_and_physical_unwind_survive_unresolved_suffix(self):
        report = model("C05")
        self.assertTrue(cli.validate_model(report))
        original = model("C02")
        cut = next(
            i for i, e in enumerate(report["events"]) if e["kind"] == "UNRESOLVED_CALL"
        )
        self.assertEqual(report["events"][:cut], original["events"][:cut])
        self.assertEqual(report["frames"][1]["previousState"]["physicalId"], "P1")
        self.assertEqual(report["frames"][1]["afterState"]["physicalId"], "P1")
        self.assertEqual(report["frames"][0]["afterState"]["kind"], "UNKNOWN")
        self.assertEqual(
            report["physicalTransactions"], original["physicalTransactions"]
        )
        self.assertEqual(report["events"][-2]["kind"], "PHYSICAL_END_OUTCOME_UNKNOWN")


def supplied_oracle(case):
    def test(self):
        supplied = copy.deepcopy(case["model"])
        if case["expected"] == "ACCEPT":
            self.assertTrue(cli.validate_model(supplied))
        else:
            with self.assertRaisesRegex(ValueError, case["rejectPattern"]):
                cli.validate_model(supplied)
        self.assertEqual(supplied, case["model"])

    test.__doc__ = case["role"] + ": " + case["normative"]
    return test


for case in DATA["cases"]:
    setattr(AopCausalOrderTests, "test_" + case["id"], supplied_oracle(case))


if __name__ == "__main__":
    unittest.main()
