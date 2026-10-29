#!/usr/bin/env python3
"""Focused F01 source fixtures and independent self-invocation expectations."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/transaction-self-invocation"
spec = importlib.util.spec_from_file_location(
    "transaction_f01_entry", ROOT / "scripts/mana-transaction.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


class SelfInvocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = snapshot(FIXTURE)
        cls.oracles = json.loads((FIXTURE / "oracles.json").read_text())
        cls.facts = {}
        for name in ("proxy", "aspectj", "unknown"):
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
            raise AssertionError("analysis changed source fixtures")

    def context(self, oracle):
        context = {
            "schema": "mana.transaction-context/v1",
            "initialState": "NO_TRANSACTION",
            "entryThroughProxy": oracle["entryThroughProxy"],
            "managerCapabilities": {"tx": {"suspend": True, "savepoints": True}},
        }
        if "aspectjWeaving" in oracle:
            context["aspectjWeaving"] = oracle["aspectjWeaving"]
        return cli.context_input(None, json.dumps(context).encode())

    def model(self, name):
        oracle = self.oracles[name]
        report = cli.build(
            copy.deepcopy(self.facts[oracle["project"]]),
            self.context(oracle),
            oracle["entry"],
        )
        cli.validate_model(report)
        return report

    def assert_case(self, name):
        expected = self.oracles[name]
        report = self.model(name)
        frames = report["frames"]
        self.assertEqual(
            [f["interception"]["status"] for f in frames], expected["interception"]
        )
        self.assertEqual(
            [f["effectiveContext"]["during"] for f in frames], expected["during"]
        )
        self.assertEqual(
            [f["duringState"]["physicalId"] for f in frames], expected["physical"]
        )
        self.assertEqual([f["logicalScope"] for f in frames], expected["logical"])
        self.assertEqual(frames[1]["effectiveContext"]["after"], expected["childAfter"])
        self.assertEqual(
            frames[1]["afterState"]["physicalId"],
            frames[0]["duringState"]["physicalId"],
        )
        self.assertEqual(len(report["physicalTransactions"]), expected["physicalCount"])
        self.assertEqual(len(report["suspensions"]), expected["suspensions"])
        self.assertEqual(len(report["savepoints"]), expected["savepoints"])
        self.assertEqual(
            [
                e["kind"]
                for e in report["events"]
                if e["kind"] not in {"FRAME_ENTER", "FRAME_EXIT"}
            ],
            expected["boundaryEvents"],
        )
        site = frames[1]["callSite"]
        source = (FIXTURE / expected["project"] / site["file"]).read_text()
        callee = frames[1]["calleeMethod"].split("#")[1]
        self.assertIn("this." + callee, source.splitlines()[site["line"] - 1])
        if "reason" in expected:
            self.assertEqual(frames[1]["reason"], expected["reason"])
            self.assertEqual(
                frames[0]["effectiveContext"]["after"],
                expected.get("callerAfter", "UNKNOWN"),
            )
        else:
            self.assertFalse(report["uncertainties"])
        text = cli.render(report)
        for frame in frames:
            self.assertIn("interception=" + frame["interception"]["status"], text)
            self.assertIn("context=" + frame["effectiveContext"]["during"], text)
        if expected["during"] == ["ACTIVE", "ACTIVE"]:
            self.assertNotIn("METHOD_EXECUTION NO_TRANSACTION", text)
        if expected["project"] == "aspectj":
            self.assertTrue(all(f["proxy"]["crossed"] is False for f in frames))
            self.assertEqual(report["aspectjWeaving"]["runtimeApplication"], "UNKNOWN")
        return report

    def test_01_proxy_required_inactive(self):
        self.assert_case("proxy_required_inactive")

    def test_02_proxy_required_active(self):
        self.assert_case("proxy_required_active")

    def test_03_proxy_requires_new_active(self):
        report = self.assert_case("proxy_requires_new_active")
        self.assertIn("INHERITED P1", cli.render(report))

    def test_04_aspectj_required_conditional(self):
        report = self.assert_case("aspectj_required_conditional")
        self.assertIn("ASPECTJ weaving=ASSUMED_APPLIED", cli.render(report))

    def test_05_aspectj_requires_new_conditional(self):
        report = self.assert_case("aspectj_requires_new_conditional")
        self.assertIn("INDEPENDENT P2", cli.render(report))
        self.assertEqual(report["suspensions"][0]["physicalId"], "P1")
        self.assertEqual(report["suspensions"][0]["replacementPhysicalId"], "P2")

    def test_06_aspectj_nested_conditional(self):
        report = self.assert_case("aspectj_nested_conditional")
        self.assertEqual(report["savepoints"][0]["physicalId"], "P1")

    def test_07_aspectj_weaving_unproven(self):
        self.assert_case("aspectj_weaving_unproven")

    def test_08_unknown_mode(self):
        self.assert_case("unknown_mode")

    def test_aspectj_required_joins_active_context(self):
        oracle = self.oracles["aspectj_required_conditional"]
        report = cli.build(
            self.facts["aspectj"],
            self.context(oracle),
            "selftest.Calls#activeRequired()",
        )
        cli.validate_model(report)
        self.assertEqual([f["logicalScope"] for f in report["frames"]], ["L1", "L2"])
        self.assertEqual(
            [f["duringState"]["physicalId"] for f in report["frames"]], ["P1", "P1"]
        )

    def test_missing_capabilities_do_not_invent_aspectj_boundaries(self):
        for name, capability in [
            ("aspectj_requires_new_conditional", "suspend"),
            ("aspectj_nested_conditional", "savepoints"),
        ]:
            for value in (None, False):
                with self.subTest(name=name, capability=value):
                    oracle = self.oracles[name]
                    context = self.context(oracle)
                    context["managerCapabilities"]["tx"][capability] = value
                    report = cli.build(self.facts["aspectj"], context, oracle["entry"])
                    cli.validate_model(report)
                    self.assertEqual(
                        report["frames"][1]["interception"]["status"], "APPLIED"
                    )
                    self.assertEqual(
                        report["frames"][1]["effectiveContext"]["during"], "UNKNOWN"
                    )
                    self.assertEqual(len(report["physicalTransactions"]), 1)
                    self.assertFalse(report["suspensions"])
                    self.assertFalse(report["savepoints"])

    def test_unknown_prior_context_is_not_inactive_after_bypass(self):
        oracle = self.oracles["proxy_required_inactive"]
        context = self.context(oracle)
        context["initialState"] = "UNKNOWN"
        context["entryThroughProxy"] = False
        report = cli.build(self.facts["proxy"], context, "selftest.Calls#required()")
        cli.validate_model(report)
        self.assertEqual(report["frames"][0]["interception"]["status"], "BYPASSED")
        self.assertEqual(report["frames"][0]["effectiveContext"]["during"], "UNKNOWN")

    def test_context_rejects_weaving_truth_claims_and_unknown_fields(self):
        context = self.context(self.oracles["aspectj_required_conditional"])
        for value in (True, None, {}, "PROVEN", "APPLIED"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    cli.context_input(
                        None, json.dumps({**context, "aspectjWeaving": value}).encode()
                    )
        with self.assertRaises(ValueError):
            cli.context_input(None, json.dumps({**context, "activate": True}).encode())

    def test_original_r1_counterexample_stays_unknown(self):
        original = ROOT / "tests/fixtures/transaction-boundaries"
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            shutil.copytree(original, project)
            source = project / "src/main/java/fixture/Scenario.java"
            source.write_text(
                source.read_text().replace(
                    "@EnableTransactionManagement(proxyTargetClass = true)",
                    "@EnableTransactionManagement(mode = org.springframework.context.annotation.AdviceMode.ASPECTJ, proxyTargetClass = true)",
                )
            )
            context = project / "context.json"
            context.write_text(
                json.dumps(
                    {**json.loads(context.read_text()), "entryThroughProxy": False}
                )
            )
            before = snapshot(project)
            report = cli.analyze(project, context, "fixture.A#selfOutside()")
            self.assertEqual(snapshot(project), before)
            self.assertEqual(report["interceptionMode"], "ASPECTJ")
            self.assertEqual(report["frames"][1]["interception"]["status"], "UNKNOWN")
            self.assertEqual(
                report["frames"][1]["effectiveContext"]["during"], "UNKNOWN"
            )
            self.assertTrue(report["uncertainties"])
            self.assertFalse(report["physicalTransactions"])

    def test_validator_rejects_conflated_context_and_interception(self):
        report = self.model("proxy_requires_new_active")
        report["frames"][1]["effectiveContext"]["during"] = "INACTIVE"
        with self.assertRaises(ValueError):
            cli.validate_model(report)
        report = self.model("proxy_requires_new_active")
        report["frames"][1]["duringState"] = report["frames"][0]["previousState"]
        report["frames"][1]["effectiveContext"]["during"] = "INACTIVE"
        with self.assertRaises(ValueError):
            cli.validate_model(report)

    def test_cli_does_not_change_analyzed_projects(self):
        for name, oracle in self.oracles.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                context = Path(temp) / "context.json"
                context.write_text(json.dumps(self.context(oracle)))
                report = cli.analyze(
                    FIXTURE / oracle["project"], context, oracle["entry"]
                )
                self.assertEqual(
                    [f["interception"]["status"] for f in report["frames"]],
                    oracle["interception"],
                )
        self.assertEqual(snapshot(FIXTURE), self.before)

    def test_plantuml_syntax_and_svg_for_f01_and_historical_models(self):
        jar = Path(
            os.environ.get("MANA_PLANTUML_JAR", "/Applications/plantuml-1.2024.8.jar")
        )
        if not jar.is_file():
            self.skipTest("PlantUML unavailable: NOT RUN")
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp).resolve()
            for name in self.oracles:
                (stage / (name + ".puml")).write_text(cli.render(self.model(name)))
            examples = ROOT / "docs/examples/transaction-01-t01"
            for path in examples.glob("*/transaction-model.json"):
                model = json.loads(path.read_text())
                cli.validate_model(model)
                (stage / ("historical-" + path.parent.name + ".puml")).write_text(
                    cli.render(model)
                )
            self.assertEqual(len(list(stage.glob("*.puml"))), 16)
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
            self.assertEqual(len(list(stage.glob("*.svg"))), 16)
            self.assertTrue(
                all("Syntax Error" not in p.read_text() for p in stage.glob("*.svg"))
            )


if __name__ == "__main__":
    unittest.main()
