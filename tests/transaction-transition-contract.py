#!/usr/bin/env python3
"""Executable MR00 O01-O44: literal supplied IR, never generated expectations."""

import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/transaction-transition-contract/cases.json"
DATA = json.loads(FIXTURE.read_text())
spec = importlib.util.spec_from_file_location(
    "transition_mr01", ROOT / "scripts/mana-transaction.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class TransitionContractTests(unittest.TestCase):
    def check_case(self, case):
        for model in [case["model"], *case.get("variants", [])]:
            supplied = copy.deepcopy(model)
            if case["expected"] == "ACCEPT":
                self.assertTrue(cli.validate_model(supplied), case["id"])
            else:
                # A format accident (KeyError/TypeError/etc.) is never a semantic PASS.
                with self.assertRaisesRegex(ValueError, case["rejectPattern"]):
                    cli.validate_model(supplied)
            self.assertEqual(supplied, model, "validation mutated the supplied IR")

    def model(self, identity):
        return copy.deepcopy(
            next(c["model"] for c in DATA["cases"] if c["id"] == identity)
        )

    def test_literal_ids_verdicts_transitions_and_envelopes(self):
        with (ROOT / "docs/reports/MANA-TRANSACTION-01-T01-MR00-transitions.csv").open(
            newline=""
        ) as stream:
            normative = {r["id"]: r for r in csv.DictReader(stream)}
        self.assertEqual(
            [c["id"] for c in DATA["cases"]], [f"O{i:02d}" for i in range(1, 45)]
        )
        for case in DATA["cases"]:
            self.assertEqual(
                case["expected"], normative[case["id"]]["expected_verdict"]
            )
            self.assertEqual(
                case["transition"], normative[case["id"]]["source"].split(";")[0]
            )
            self.assertEqual(
                case["contradiction"], normative[case["id"]]["example_or_delta"]
            )
        covered = {c["transition"] for c in DATA["cases"] if c["expected"] == "ACCEPT"}
        covered |= {c["id"] for c in DATA["transitionPositives"]}
        self.assertEqual(covered, {f"T{i:02d}" for i in range(1, 25)})
        for case in DATA["cases"] + DATA["transitionPositives"]:
            model = case["model"]
            digest = hashlib.sha256(case["source"].encode()).hexdigest()
            self.assertEqual(
                model["evidence"], [{"path": "Synthetic.java", "sha256": digest}]
            )
            context = (json.dumps(model["context"], indent=2) + "\n").encode()
            self.assertEqual(
                model["contextEvidence"]["sha256"], hashlib.sha256(context).hexdigest()
            )
            self.assertEqual(model["entry"], model["frames"][0]["calleeMethod"])
            for frame in model["frames"]:
                self.assertEqual(frame["evidence"]["sha256"], digest)
                if frame["callSite"]:
                    self.assertEqual(frame["callSite"]["sha256"], digest)
            self.assertTrue(
                {
                    "assumptions",
                    "uncertainties",
                    "managers",
                    "contextEvidence",
                    "events",
                }
                <= model.keys()
            )

    def test_exact_nine_r4_high_payloads_rejected(self):
        receipt = json.loads(
            (ROOT / "docs/reports/MANA-TRANSACTION-01-T01-R4-results.json").read_text()
        )
        self.assertEqual(len(receipt["finding"]["variants"]), 9)
        for variant in receipt["finding"]["variants"]:
            model = receipt["reviewArtifacts"][variant["case"] + ".json"]
            with self.subTest(case=variant["case"]), self.assertRaises(ValueError):
                cli.validate_model(copy.deepcopy(model))

    def test_d2_renderer_distinguishes_marker_and_retained_lifetime(self):
        model = self.model("O33")
        self.assertTrue(cli.validate_model(model))
        text = cli.render(model)
        self.assertIn("UNRESOLVED_LOGICAL_MARKER L2", text)
        self.assertIn("execution and transactional effects NOT ESTABLISHED", text)
        self.assertIn("retained physical lifetime P1", text)
        self.assertNotIn("LOGICAL_BEGIN L2", text)
        self.assertNotIn("LOGICAL_END L2", text)
        self.assertNotIn(
            "context=ACTIVE", text.split("PHYSICAL_END_OUTCOME_UNKNOWN P1", 1)[1]
        )
        model["logicalScopes"][1]["certainty"] = "CONDITIONAL"
        with self.assertRaisesRegex(ValueError, "unresolved logical marker"):
            cli.validate_model(model)

    def test_d3_no_positive_certification_from_annotation_or_effects_alone(self):
        model = self.model("O02")
        for frame in model["frames"]:
            frame.pop("interception")
            frame["proxy"].pop("configurationEvidence")
        with self.assertRaisesRegex(ValueError, "unclassified"):
            cli.validate_model(model)
        self.assertIn("interception=UNKNOWN", cli.render(model))

    def test_d4_bare_unknown_continuation_cannot_erase_known_return(self):
        model = self.model("O02")
        frame = model["frames"][1]
        frame["afterState"] = {"kind": "UNKNOWN", "physicalId": None, "manager": None}
        frame["effectiveContext"]["after"] = "UNKNOWN"
        frame["continuation"] = "UNKNOWN"
        with self.assertRaisesRegex(
            ValueError, "unresolved continuation with evidence"
        ):
            cli.validate_model(model)

    def test_d4_unknown_cannot_justify_unsupported_effects(self):
        model = self.model("O07")
        frame = model["frames"][1]
        frame.update(
            certainty="UNKNOWN",
            bodyTraversal="NOT_ASSERTED",
            reason="SAVEPOINT_CAPABILITY_UNSUPPORTED",
        )
        frame["afterState"] = {"kind": "UNKNOWN", "physicalId": None, "manager": None}
        frame["effectiveContext"]["after"] = "UNKNOWN"
        model["uncertainties"].append(
            {
                "frame": "F2",
                "reason": frame["reason"],
                "classification": "UNSUPPORTED",
                "evidence": frame["evidence"],
            }
        )
        with self.assertRaisesRegex(ValueError, "capabilities"):
            cli.validate_model(model)

    def test_body_cannot_run_before_completed_opening(self):
        model = self.model("O02")
        event = next(
            e
            for e in model["events"]
            if e["kind"] == "LOGICAL_BEGIN" and e["frame"] == "F1"
        )
        model["events"].remove(event)
        position = (
            next(
                i
                for i, e in enumerate(model["events"])
                if e["kind"] == "FRAME_EXIT" and e["frame"] == "F2"
            )
            + 1
        )
        model["events"].insert(position, event)
        for sequence, item in enumerate(model["events"], 1):
            item["sequence"] = sequence
        with self.assertRaisesRegex(ValueError, "outside completed boundary"):
            cli.validate_model(model)

    def test_no_unknown_event_can_supply_a_terminal(self):
        model = self.model("O01")
        model["events"][-2]["kind"] = "COMMIT"
        with self.assertRaisesRegex(ValueError, "unrecognized transaction event"):
            cli.validate_model(model)

    def test_savepoint_event_must_identify_its_own_physical_transaction(self):
        model = self.model("O06")
        event = next(e for e in model["events"] if e["kind"] == "SAVEPOINT_CREATE")
        event["physicalId"] = "P2"
        with self.assertRaisesRegex(ValueError, "savepoint event contradicts"):
            cli.validate_model(model)

    def test_call_site_hash_must_match_caller_snapshot(self):
        model = self.model("O02")
        model["frames"][1]["callSite"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "call site outside caller"):
            cli.validate_model(model)

    def test_manager_and_runtime_outcome_cannot_be_invented(self):
        for field, value, message in (
            ("manager", "other", "manager"),
            ("outcome", "COMMITTED", "unsubstantiated physical outcome"),
            (
                "runtimeIdentity",
                "actual-connection",
                "unsubstantiated runtime identity",
            ),
        ):
            with self.subTest(field=field):
                model = self.model("O01")
                model["physicalTransactions"][0][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    cli.validate_model(model)

    def test_entity_kind_is_not_a_current_context_state(self):
        model = self.model("O01")
        model["frames"][0]["duringState"]["kind"] = "TRANSACTION_LOGICAL_SCOPE"
        with self.assertRaisesRegex(ValueError, "invalid context state kind"):
            cli.validate_model(model)


def oracle_test(case):
    def test(self):
        self.check_case(case)

    test.__doc__ = case.get("contradiction", case["id"])
    return test


for supplied_case in DATA["cases"] + DATA["transitionPositives"]:
    setattr(
        TransitionContractTests,
        "test_" + supplied_case["id"],
        oracle_test(supplied_case),
    )


if __name__ == "__main__":
    unittest.main()
