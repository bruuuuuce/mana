#!/usr/bin/env python3
"""Literal F02 oracles, immutable R2 counterexample and validator negative controls."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/transaction-context-alternatives"
spec = importlib.util.spec_from_file_location(
    "transaction_f02", ROOT / "scripts/mana-transaction.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


class ContextAlternativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = snapshot(FIXTURE)
        cls.oracles = json.loads((FIXTURE / "oracles.json").read_text())
        cls.facts = {}
        for name in ("r2-original", "variants", "ambiguous"):
            project = FIXTURE / name
            files = cli.factory.project_files(
                project, cli.factory.adapter_for("transaction-analysis")
            )
            cls.facts[name] = cli.java_facts(
                cli.factory, project, files, source_snapshot=True
            )

    @classmethod
    def tearDownClass(cls):
        if snapshot(FIXTURE) != cls.before:
            raise AssertionError("F02 targets changed")

    def context(self, name):
        oracle = self.oracles[name]
        context = {
            "schema": "mana.transaction-context/v1",
            "initialState": "NO_TRANSACTION",
            "entryThroughProxy": False,
            "aspectjWeaving": "ASSUMED_APPLIED",
            "managerCapabilities": {"tx": {"suspend": True, "savepoints": True}},
        }
        if "capability" in oracle:
            context["managerCapabilities"]["tx"][oracle["capability"]] = oracle[
                "capabilityValue"
            ]
        return context

    def model(self, name):
        oracle = self.oracles[name]
        report = cli.build(
            copy.deepcopy(self.facts[oracle["project"]]),
            self.context(name),
            "selftest.Calls#" + oracle["entry"] + "()",
        )
        cli.validate_model(report)
        return report

    def assert_oracle(self, name):
        expected = self.oracles[name]
        report = self.model(name)
        parent, child = report["frames"]
        self.assertEqual(child["interception"]["status"], "UNKNOWN")
        self.assertEqual(child["configuration"]["propagation"], expected["propagation"])
        self.assertEqual(child["effectiveContext"]["during"], expected["during"])
        self.assertEqual(
            child["duringState"],
            {
                "kind": expected["kind"],
                "physicalId": expected["physical"],
                "manager": expected["manager"],
            },
        )
        self.assertEqual(child["effectiveContext"]["after"], expected["after"])
        self.assertEqual(child["afterState"]["physicalId"], expected["afterPhysical"])
        self.assertEqual(parent["effectiveContext"]["after"], expected["callerAfter"])
        self.assertEqual(child["previousState"], parent["duringState"])
        applied = child["contextComposition"]["alternatives"]["APPLIED"]
        for key, oracle_key in (
            ("identity", "identity"),
            ("logicalScope", "logical"),
            ("savepoint", "savepoint"),
            ("suspension", "suspension"),
            ("resolution", "resolution"),
        ):
            self.assertEqual(applied[key], expected[oracle_key])
        self.assertEqual(len(report["physicalTransactions"]), expected["physicalCount"])
        self.assertEqual(len(report["logicalScopes"]), expected["physicalCount"])
        self.assertIsNone(child["logicalScope"])
        self.assertFalse(report["savepoints"])
        self.assertFalse(report["suspensions"])
        self.assertFalse(
            any(
                e["frame"] == child["id"]
                and e["kind"] not in {"FRAME_ENTER", "FRAME_EXIT"}
                for e in report["events"]
            )
        )
        self.assertEqual(
            child["contextComposition"]["premises"]["evidence"], child["evidence"]
        )
        self.assertEqual(report["aspectjWeaving"]["runtimeApplication"], "UNKNOWN")
        return report

    def test_01_required_preserves_active_p1(self):
        self.assert_oracle("required_active")

    def test_02_required_without_initial_transaction(self):
        self.assert_oracle("required_inactive")

    def test_03_requires_new_has_no_common_identity(self):
        self.assert_oracle("new_active")

    def test_04_nested_has_conditional_savepoint_on_same_p1(self):
        self.assert_oracle("nested_active")

    def test_05_nested_unknown_and_false_capability(self):
        for name in ("nested_unknown", "nested_false"):
            with self.subTest(name=name):
                self.assert_oracle(name)

    def test_06_ambiguous_manager_does_not_preserve_false_identity(self):
        self.assert_oracle("ambiguous")

    def test_07_caller_context_and_following_call_preserved(self):
        report = cli.build(
            self.facts["variants"],
            self.context("required_active"),
            "selftest.Calls#following()",
        )
        cli.validate_model(report)
        self.assertEqual(
            [f["duringState"]["physicalId"] for f in report["frames"]],
            ["P1", "P1", "P1"],
        )
        self.assertEqual(report["frames"][1]["afterState"]["physicalId"], "P1")
        self.assertEqual(report["frames"][0]["effectiveContext"]["after"], "INACTIVE")

    def test_08_rejects_falsely_deterministic_physical_identity(self):
        for name in ("required_inactive", "new_active", "nested_unknown", "ambiguous"):
            with self.subTest(name=name):
                report = self.model(name)
                child = report["frames"][1]
                child["duringState"] = {
                    "kind": "TRANSACTION_PHYSICAL",
                    "physicalId": "P1",
                    "manager": "tx",
                }
                child["effectiveContext"]["during"] = "ACTIVE"
                child["manager"] = "tx"
                child["contextComposition"]["duringState"] = copy.deepcopy(
                    child["duringState"]
                )
                with self.assertRaises(ValueError):
                    cli.validate_model(report)

    def test_09_validator_accepts_unknown_advice_active_p1(self):
        report = self.model("required_active")
        self.assertTrue(cli.validate_model(report))
        del report["frames"][1]["contextComposition"]
        with self.assertRaises(ValueError):
            cli.validate_model(report)

    def test_10_diagram_separates_known_context_conditional_scope_and_savepoint(self):
        required = cli.render(self.model("required_active"))
        self.assertIn("interception=UNKNOWN; context=ACTIVE; INHERITED P1", required)
        self.assertIn("CONDITIONAL_LOGICAL_SCOPE P1", required)
        self.assertIn("LOGICAL_SCOPE CONDITIONAL IF_ADVICE_APPLIED", required)
        self.assertIn("group #D6F5D6 F2", required)
        nested = cli.render(self.model("nested_active"))
        self.assertIn("SAVEPOINT CONDITIONAL IF_ADVICE_APPLIED on SAME P1", nested)
        independent = cli.render(self.model("new_active"))
        self.assertIn("context=ACTIVE; PHYSICAL_ID_UNKNOWN", independent)
        self.assertIn(
            "IF_ADVICE_APPLIED: SUSPEND P1 / FRESH PHYSICAL / RESUME on normal unwind",
            independent,
        )
        self.assertNotIn("F2 REQUIRES_NEW CONDITIONAL_LOGICAL_SCOPE P1", independent)
        self.assertIn(
            "context=UNKNOWN; UNKNOWN", cli.render(self.model("required_inactive"))
        )

    def test_original_r2_source_and_context_exact_cli_regression(self):
        receipt = json.loads(
            (ROOT / "docs/reports/MANA-TRANSACTION-01-T01-R2-results.json").read_text()
        )
        original = receipt["cases"]["counterexample"]
        self.assertEqual(
            (FIXTURE / "r2-original/src/main/java/selftest/Calls.java").read_text(),
            original["source"],
        )
        self.assertEqual(self.context("required_active"), original["context"])
        with tempfile.TemporaryDirectory() as temporary:
            context = Path(temporary).resolve() / "context.json"
            context.write_text(json.dumps(original["context"]))
            output = Path(temporary).resolve() / "result"
            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/mana-transaction.py"),
                    "--project-root",
                    str(FIXTURE / "r2-original"),
                    "--context",
                    str(context),
                    "--entry",
                    "selftest.Calls#activeRequired()",
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((output / "transaction-model.json").read_text())
            self.assertEqual(report["frames"][1]["interception"]["status"], "UNKNOWN")
            self.assertEqual(
                report["frames"][1]["duringState"],
                {"kind": "TRANSACTION_PHYSICAL", "physicalId": "P1", "manager": "tx"},
            )
            self.assertEqual(report["frames"][1]["afterState"]["physicalId"], "P1")
            self.assertFalse(json.loads(result.stdout)["candidateActivated"])

    def test_requires_new_unknown_capability_is_unresolved(self):
        self.assert_oracle("new_unknown")

    def test_nonempty_body_does_not_claim_return_context_or_follow_calls(self):
        report = cli.build(
            self.facts["variants"],
            self.context("required_active"),
            "selftest.Calls#nonempty()",
        )
        cli.validate_model(report)
        self.assertEqual(len(report["frames"]), 2)
        self.assertEqual(report["frames"][1]["duringState"]["physicalId"], "P1")
        self.assertEqual(report["frames"][1]["effectiveContext"]["after"], "UNKNOWN")
        self.assertEqual(report["frames"][0]["continuation"], "UNKNOWN")

    def test_async_and_programmatic_hazards_cannot_use_composition(self):
        for method in ("asyncCaller", "hazardCaller"):
            with self.subTest(method=method):
                report = cli.build(
                    self.facts["variants"],
                    self.context("required_active"),
                    "selftest.Calls#" + method + "()",
                )
                cli.validate_model(report)
                child = report["frames"][1]
                self.assertNotIn("contextComposition", child)
                self.assertEqual(child["effectiveContext"]["during"], "UNKNOWN")

    def test_validator_rejects_forged_applied_branch_and_missing_bypass(self):
        report = self.model("new_active")
        composition = report["frames"][1]["contextComposition"]
        composition["alternatives"]["APPLIED"]["duringState"]["physicalId"] = "P1"
        with self.assertRaises(ValueError):
            cli.validate_model(report)
        report = self.model("required_active")
        del report["frames"][1]["contextComposition"]["alternatives"]["BYPASSED"]
        with self.assertRaises(ValueError):
            cli.validate_model(report)

    def test_validator_rejects_false_capability_and_premises(self):
        for field, value in (
            ("execution", "ASYNC"),
            ("otherBoundaryMechanisms", "UNKNOWN"),
            ("evidence", {}),
        ):
            report = self.model("required_active")
            report["frames"][1]["contextComposition"]["premises"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                cli.validate_model(report)
        report = self.model("nested_active")
        report["context"]["managerCapabilities"]["tx"]["savepoints"] = None
        with self.assertRaises(ValueError):
            cli.validate_model(report)
        report = cli.build(
            self.facts["r2-original"],
            self.context("required_active"),
            "selftest.Calls#required()",
        )
        self.assertTrue(cli.validate_model(report))
        report["context"]["initialState"] = "UNKNOWN"
        with self.assertRaises(ValueError):
            cli.validate_model(report)
        report = cli.build(
            self.facts["r2-original"],
            self.context("required_active"),
            "selftest.Calls#required()",
        )
        del report["frames"][0]["contextComposition"]
        with self.assertRaises(ValueError):
            cli.validate_model(report)

    def test_validator_rejects_conditional_scope_materialized_unconditionally(self):
        report = self.model("required_active")
        report["frames"][1]["logicalScope"] = "L2"
        with self.assertRaises(ValueError):
            cli.validate_model(report)

    def test_validator_rejects_wrong_caller_identity_and_manager(self):
        for mutation in ("caller", "manager", "after"):
            report = self.model("required_active")
            frame = report["frames"][1]
            if mutation == "caller":
                frame["previousState"] = copy.deepcopy(
                    report["frames"][0]["previousState"]
                )
                frame["effectiveContext"]["before"] = "INACTIVE"
            elif mutation == "manager":
                frame["duringState"]["manager"] = "tx2"
            else:
                frame["afterState"] = copy.deepcopy(
                    report["frames"][0]["previousState"]
                )
                frame["effectiveContext"]["after"] = "INACTIVE"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                cli.validate_model(report)

    def test_historical_models_remain_valid(self):
        for path in (ROOT / "docs/examples/transaction-01-t01").glob(
            "*/transaction-model.json"
        ):
            with self.subTest(path=path):
                self.assertTrue(cli.validate_model(json.loads(path.read_text())))

    def test_composition_labels_reject_directive_injection(self):
        report = self.model("nested_active")
        composition = report["frames"][1]["contextComposition"]
        poison = "\n!include x\n@enduml\n[[http://x]] <img:x>"
        composition["premises"]["body"] = poison
        composition["alternatives"]["APPLIED"]["identity"] = poison
        text = cli.render(report)
        self.assertEqual(text.count("@startuml"), 1)
        self.assertEqual(text.count("@enduml"), 1)
        self.assertNotIn("!include", text)
        self.assertNotIn("[[", text)
        self.assertNotIn("<img", text)

    def test_plantuml_syntax_and_svg(self):
        jar = Path(
            os.environ.get("MANA_PLANTUML_JAR", "/Applications/plantuml-1.2024.8.jar")
        )
        if not jar.is_file():
            self.skipTest("PlantUML unavailable: NOT RUN")
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary).resolve()
            for name in self.oracles:
                (stage / (name + ".puml")).write_text(cli.render(self.model(name)))
            args = [
                "java",
                "-Djava.awt.headless=true",
                "-Djava.io.tmpdir=" + str(stage),
                "-XX:-UsePerfData",
                "-jar",
                str(jar),
            ]
            for flag in ("-checkonly", "-tsvg"):
                result = subprocess.run(
                    [*args, flag, *map(str, sorted(stage.glob("*.puml")))],
                    cwd=stage,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(stage.glob("*.svg"))), len(self.oracles))
            self.assertTrue(
                all(
                    "Syntax Error" not in path.read_text()
                    for path in stage.glob("*.svg")
                )
            )


if __name__ == "__main__":
    unittest.main()
