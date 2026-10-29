#!/usr/bin/env python3
"""Literal lifetime oracles and immutable R3 counterexamples; no runtime outcomes."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "transaction_f03", ROOT / "scripts/mana-transaction.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def physical(identity):
    return {"kind": "TRANSACTION_PHYSICAL", "physicalId": identity, "manager": "tx"}


def move(report, kind, entity, before_kind, before_entity):
    events = report["events"]
    event = next(e for e in events if e["kind"] == kind and e.get("entity") == entity)
    events.remove(event)
    index = next(
        i
        for i, e in enumerate(events)
        if e["kind"] == before_kind and e.get("entity") == before_entity
    )
    events.insert(index, event)
    for sequence, item in enumerate(events, 1):
        item["sequence"] = sequence


class PhysicalLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r3 = json.loads(
            (ROOT / "docs/reports/MANA-TRANSACTION-01-T01-R3-results.json").read_text()
        )

    def model(self, name):
        return json.loads(
            (
                ROOT
                / "docs/examples/transaction-01-t01"
                / name
                / "transaction-model.json"
            ).read_text()
        )

    def reject(self, report, message):
        with self.assertRaisesRegex(ValueError, message):
            cli.validate_model(report)

    def test_original_high_r3_and_uncertain_continuation_rejected(self):
        for name in (
            "counterexample_root_after_ended_p1.json",
            "counterexample_nonempty_caller_after.json",
            "minimal-after-counterexample.json",
        ):
            with self.subTest(name=name):
                model = copy.deepcopy(self.r3["adversarialModels"][name])
                self.assertEqual(model["frames"][0]["afterState"], physical("P1"))
                self.reject(model, "outside its active lifetime")

    def test_exact_r3_mutation_on_original_valid_model(self):
        model = copy.deepcopy(self.r3["matrixArtifacts"]["required_active"]["model"])
        self.assertTrue(cli.validate_model(model))
        self.assertEqual(
            model["events"][6],
            {
                "sequence": 7,
                "kind": "PHYSICAL_END_OUTCOME_UNKNOWN",
                "frame": "F1",
                "entity": "P1",
            },
        )
        model["frames"][0]["afterState"] = copy.deepcopy(
            model["frames"][0]["duringState"]
        )
        model["frames"][0]["effectiveContext"]["after"] = "ACTIVE"
        self.reject(model, "outside its active lifetime")

    def test_terminal_event_is_outcome_independent(self):
        # v1 has one terminal event, shared by either possible physical outcome.
        # Do not invent COMMIT/ROLLBACK events or claim either happened at runtime.
        model = self.model("required")
        self.assertEqual(model["physicalTransactions"][0]["outcome"], "UNKNOWN")
        self.assertEqual(model["events"][-2]["kind"], "PHYSICAL_END_OUTCOME_UNKNOWN")
        self.assertEqual(
            model["frames"][0]["afterState"],
            {"kind": "NO_TRANSACTION", "physicalId": None, "manager": None},
        )
        self.assertTrue(cli.validate_model(model))
        model["frames"][0]["afterState"] = physical("P1")
        self.reject(model, "outside its active lifetime")

    def test_required_logical_end_preserves_p1(self):
        model = self.model("required")
        self.assertEqual(model["frames"][1]["afterState"], physical("P1"))
        self.assertEqual(
            [
                e["entity"]
                for e in model["events"]
                if e["kind"] == "PHYSICAL_END_OUTCOME_UNKNOWN"
            ],
            ["P1"],
        )
        self.assertTrue(cli.validate_model(model))

    def test_nested_savepoint_release_preserves_p1(self):
        model = self.model("nested")
        self.assertEqual(model["savepoints"][0]["physicalId"], "P1")
        self.assertEqual(model["frames"][1]["afterState"], physical("P1"))
        self.assertTrue(cli.validate_model(model))

    def test_requires_new_restores_live_p1_after_p2_end(self):
        model = self.model("requires_new")
        self.assertEqual(model["frames"][1]["afterState"], physical("P1"))
        self.assertEqual(
            [e["kind"] for e in model["events"]][8:11],
            ["PHYSICAL_END_OUTCOME_UNKNOWN", "RESUME_CONDITIONAL", "FRAME_EXIT"],
        )
        self.assertTrue(cli.validate_model(model))

    def test_requires_new_rejects_resume_while_p2_active(self):
        model = self.model("requires_new")
        move(model, "RESUME_CONDITIONAL", "S1", "PHYSICAL_END_OUTCOME_UNKNOWN", "P2")
        self.reject(model, "ended replacement")

    def test_rejects_restore_without_resume(self):
        model = self.model("requires_new")
        model["events"] = [
            e for e in model["events"] if e["kind"] != "RESUME_CONDITIONAL"
        ]
        for sequence, event in enumerate(model["events"], 1):
            event["sequence"] = sequence
        self.reject(model, "outside its active lifetime")

    def test_rejects_after_state_retaining_ended_p2(self):
        model = self.model("requires_new")
        model["frames"][1]["afterState"] = physical("P2")
        self.reject(model, "outside its active lifetime")

    def test_rejects_begin_before_suspend(self):
        model = self.model("requires_new")
        move(model, "PHYSICAL_BEGIN", "P2", "SUSPEND", "S1")
        self.reject(model, "did not suspend")

    def test_rejects_physical_end_before_logical_closure(self):
        model = self.model("required")
        move(model, "PHYSICAL_END_OUTCOME_UNKNOWN", "P1", "LOGICAL_END", "L1")
        self.reject(model, "precedes logical scope/savepoint closure")

    def test_rejects_savepoint_before_physical_begin(self):
        model = self.model("nested")
        move(model, "PHYSICAL_BEGIN", "P1", "LOGICAL_END", "L1")
        self.reject(model, "outside its active lifetime")

    def test_rejects_identity_without_begin(self):
        model = self.model("requires_new")
        model["events"] = [
            e
            for e in model["events"]
            if not (e["kind"] == "PHYSICAL_BEGIN" and e["entity"] == "P2")
        ]
        for sequence, event in enumerate(model["events"], 1):
            event["sequence"] = sequence
        self.reject(model, "outside its active lifetime")

    def test_rejects_same_symbol_reopened_after_end(self):
        model = self.model("required")
        model["events"].insert(
            -1, {"kind": "PHYSICAL_BEGIN", "frame": "F1", "entity": "P1"}
        )
        for sequence, event in enumerate(model["events"], 1):
            event["sequence"] = sequence
        self.reject(model, "reused physical identity")

    def test_rejects_ordinary_frame_inventing_previous_identity(self):
        model = self.model("required")
        model["frames"][0]["previousState"] = physical("P1")
        self.reject(model, "initial scenario context")

    def test_rejects_ordinary_child_losing_caller_context(self):
        model = self.model("required")
        model["frames"][1]["previousState"] = {
            "kind": "UNKNOWN",
            "physicalId": None,
            "manager": None,
        }
        self.reject(model, "caller context provenance")

    def test_rejects_wrong_physical_end_owner(self):
        model = self.model("required")
        model["physicalTransactions"][0]["endFrame"] = "F2"
        self.reject(model, "physical end attached to wrong frame")

    def test_f02_conditional_properties_preserved(self):
        for name, identity in (
            ("required_active", "P1"),
            ("nested_active", "P1"),
            ("new_active", None),
        ):
            with self.subTest(name=name):
                model = copy.deepcopy(self.r3["matrixArtifacts"][name]["model"])
                child = model["frames"][1]
                self.assertEqual(child["duringState"], physical(identity))
                self.assertEqual(child["interception"]["status"], "UNKNOWN")
                self.assertEqual(child["afterState"], physical("P1"))
                self.assertTrue(cli.validate_model(model))

    def test_renderer_does_not_label_activity_beyond_terminal_event(self):
        for name in ("required", "nested", "requires_new"):
            model = self.model(name)
            self.assertTrue(cli.validate_model(model))
            diagram = cli.render(model)
            suffix = diagram.split("PHYSICAL_END_OUTCOME_UNKNOWN P1", 1)[1]
            self.assertNotIn("context=ACTIVE", suffix)
            self.assertNotIn("INHERITED P1", suffix)
            self.assertNotIn("INDEPENDENT P1", suffix)
            if name == "requires_new":
                self.assertLess(
                    diagram.index("PHYSICAL_END_OUTCOME_UNKNOWN P2"),
                    diagram.index("RESUME_CONDITIONAL S1 P1"),
                )


if __name__ == "__main__":
    unittest.main()
