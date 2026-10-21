#!/usr/bin/env python3
"""T01 bounded static oracles, negative controls and local PlantUML verification."""

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
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/transaction-boundaries"
spec = importlib.util.spec_from_file_location(
    "transaction_entry", ROOT / "scripts/mana-transaction.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


class TransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = json.loads((FIXTURE / "context.json").read_text())
        files = cli.factory.project_files(
            FIXTURE, cli.factory.adapter_for("transaction-analysis")
        )
        cls.facts = cli.java_facts(cli.factory, FIXTURE, files)
        cls.oracles = json.loads((FIXTURE / "oracles.json").read_text())

    def model(self, name="required", context=None, facts=None):
        oracle = self.oracles[name]
        scenario = copy.deepcopy(context or self.context)
        if "capabilityOverride" in oracle:
            scenario["managerCapabilities"]["tx"] = oracle["capabilityOverride"]
        result = cli.build(
            copy.deepcopy(facts or self.facts), scenario, oracle["entry"]
        )
        cli.validate_model(result)
        return result

    def test_eight_independent_oracles(self):
        for name, oracle in self.oracles.items():
            with self.subTest(name=name):
                report = self.model(name)
                self.assertEqual(
                    [f["duringState"]["physicalId"] for f in report["frames"]],
                    oracle["physicalByFrame"],
                )
                self.assertEqual(
                    [f["logicalScope"] for f in report["frames"]],
                    oracle["logicalByFrame"],
                )
                self.assertEqual(
                    len(report["physicalTransactions"]), oracle["physicalCount"]
                )
                self.assertEqual(len(report["savepoints"]), oracle["savepoints"])
                self.assertEqual(len(report["suspensions"]), oracle["suspensions"])
                self.assertEqual(
                    [f["id"] for f in report["frames"] if f["certainty"] == "UNKNOWN"],
                    oracle["unknownFrames"],
                )
                child = report["frames"][1]
                self.assertEqual(child["calleeMethod"], oracle["source"]["callee"])
                site = child["callSite"]
                self.assertEqual(site["file"], oracle["source"]["path"])
                self.assertIn(
                    oracle["source"]["callExpression"],
                    (FIXTURE / site["file"]).read_text().splitlines()[site["line"] - 1],
                )

    def test_requires_new_suspends_before_begin_and_resumes_after_end(self):
        r = self.model("requires_new")
        kinds = [e["kind"] for e in r["events"]]
        self.assertLess(
            kinds.index("SUSPEND"),
            max(i for i, k in enumerate(kinds) if k == "PHYSICAL_BEGIN"),
        )
        self.assertGreater(
            kinds.index("RESUME_CONDITIONAL"),
            kinds.index("PHYSICAL_END_OUTCOME_UNKNOWN"),
        )
        self.assertEqual(r["suspensions"][0]["physicalId"], "P1")
        self.assertEqual(r["frames"][1]["afterState"]["physicalId"], "P1")

    def test_nested_reuses_physical_and_false_capability_is_unsupported(self):
        nested = self.model("nested")
        self.assertEqual(nested["savepoints"][0]["physicalId"], "P1")
        outside = cli.build(self.facts, self.context, "fixture.B#nested()")
        self.assertEqual(len(outside["physicalTransactions"]), 1)
        self.assertFalse(outside["savepoints"])
        context = copy.deepcopy(self.context)
        context["managerCapabilities"]["tx"]["savepoints"] = False
        report = self.model("nested", context=context)
        self.assertEqual(len(report["physicalTransactions"]), 1)
        self.assertFalse(report["savepoints"])
        self.assertEqual(report["uncertainties"][-1]["classification"], "UNSUPPORTED")

    def test_missing_prior_context_never_creates_certain_physical_identity(self):
        context = {**self.context, "initialState": "UNKNOWN"}
        report = self.model(context=context)
        self.assertFalse(report["physicalTransactions"])
        self.assertEqual(report["frames"][0]["duringState"]["kind"], "UNKNOWN")
        plain = cli.build(self.facts, context, "fixture.B#plain()")
        self.assertEqual(plain["frames"][0]["certainty"], "UNKNOWN")
        self.assertIn("group #FFCCCC", cli.render(plain))
        for case in self.oracles:
            for physical in self.model(case)["physicalTransactions"]:
                self.assertEqual(physical["runtimeIdentity"], "UNKNOWN")
                self.assertEqual(physical["identity"], "SYMBOLIC_SCENARIO")

    def test_annotation_is_not_interception_and_direct_entry_bypasses(self):
        report = self.model("self_invocation")
        self.assertFalse(report["frames"][1]["proxy"]["crossed"])
        self.assertEqual(
            report["frames"][1]["configuration"]["propagation"], "REQUIRES_NEW"
        )
        self.assertIsNone(report["frames"][1]["logicalScope"])
        report = self.model(context={**self.context, "entryThroughProxy": False})
        self.assertIsNone(report["frames"][0]["logicalScope"])
        self.assertEqual(report["frames"][0]["duringState"]["kind"], "NO_TRANSACTION")

    def test_intermediate_unannotated_call_and_class_annotation(self):
        report = cli.build(self.facts, self.context, "fixture.A#intermediate()")
        self.assertEqual(
            [f["duringState"]["physicalId"] for f in report["frames"]], ["P1"] * 3
        )
        self.assertEqual(
            [f["logicalScope"] for f in report["frames"]], ["L1", None, "L2"]
        )
        self.assertEqual(report["frames"][2]["configuration"]["origin"], "class")
        override = cli.build(self.facts, self.context, "fixture.C#override()")
        self.assertEqual(
            override["frames"][0]["configuration"]["propagation"], "REQUIRES_NEW"
        )
        self.assertEqual(override["frames"][0]["configuration"]["origin"], "method")
        outside = cli.build(self.facts, self.context, "fixture.A#selfOutside()")
        self.assertFalse(outside["physicalTransactions"])
        multiple = cli.build(self.facts, self.context, "fixture.A#multiple()")
        self.assertEqual(
            [f["duringState"]["physicalId"] for f in multiple["frames"]],
            ["P1", "P1", "P2", "P1"],
        )
        cli.validate_model(multiple)

    def test_ambiguous_managers_visibility_async_and_control_flow_are_unknown(self):
        facts = copy.deepcopy(self.facts)
        config = next(c for c in facts["classes"] if c["name"] == "fixture.Config")
        extra = copy.deepcopy(config["methods"][0])
        extra["name"] = "tx2"
        config["methods"].append(extra)
        self.assertIn("MANAGER", self.model(facts=facts)["frames"][0]["reason"])
        for entry, reason in [
            ("fixture.A#async()", "ASYNC"),
            ("fixture.A#conditional()", "CONTROL_FLOW"),
        ]:
            report = cli.build(self.facts, self.context, entry)
            self.assertTrue(any(reason in u["reason"] for u in report["uncertainties"]))
        facts = copy.deepcopy(self.facts)
        config = next(c for c in facts["classes"] if c["name"] == "fixture.Config")
        config["annotations"] = [
            a
            for a in config["annotations"]
            if a["type"] != cli.build.__globals__["ENABLE"]
        ]
        self.assertIn("PROXY", self.model(facts=facts)["frames"][0]["reason"])
        facts = copy.deepcopy(self.facts)
        method = next(
            m
            for c in facts["classes"]
            if c["name"] == "fixture.A"
            for m in c["methods"]
            if m["name"] == "required"
        )
        method["flags"] = ["protected"]
        self.assertIn("VISIBILITY", self.model(facts=facts)["frames"][0]["reason"])
        facts = copy.deepcopy(self.facts)
        next(c for c in facts["classes"] if c["name"] == "fixture.A")["flags"] = [
            "final"
        ]
        self.assertIn("FINAL_CLASS", self.model(facts=facts)["frames"][0]["reason"])

    def test_jdk_proxy_dynamic_dispatch_and_unresolved_call_do_not_invent_edges(self):
        facts = copy.deepcopy(self.facts)
        config = next(c for c in facts["classes"] if c["name"] == "fixture.Config")
        next(
            a
            for a in config["annotations"]
            if a["type"].endswith("EnableTransactionManagement")
        )["args"]["proxyTargetClass"]["literal"] = False
        self.assertEqual(len(self.model(facts=facts)["frames"]), 1)
        facts = copy.deepcopy(self.facts)
        method = next(
            m
            for c in facts["classes"]
            if c["name"] == "fixture.A"
            for m in c["methods"]
            if m["name"] == "required"
        )
        method["calls"][0]["receiver"] = "dynamicFactory()"
        report = self.model(facts=facts)
        self.assertEqual(len(report["frames"]), 1)
        self.assertEqual(report["frames"][0]["continuation"], "UNKNOWN")

    def test_evidence_is_exact_and_call_site_is_in_caller(self):
        report = self.model()
        caller, callee = report["frames"]
        site = callee["callSite"]
        raw = (FIXTURE / site["file"]).read_bytes()
        self.assertEqual(site["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertGreaterEqual(site["start"], caller["evidence"]["start"])
        self.assertLessEqual(site["end"], caller["evidence"]["end"])
        self.assertIn("b.required()", raw.decode().splitlines()[site["line"] - 1])

    def test_validator_rejects_wrong_identity_and_unbalanced_trace(self):
        report = self.model("nested")
        report["savepoints"][0]["physicalId"] = "P2"
        with self.assertRaises(ValueError):
            cli.validate_model(report)
        report = self.model()
        report["frames"][1]["callSite"]["start"] = (
            report["frames"][0]["evidence"]["end"] + 1
        )
        with self.assertRaises(ValueError):
            cli.validate_model(report)
        report = self.model()
        report["logicalScopes"][1]["physicalId"] = "P99"
        with self.assertRaises(ValueError):
            cli.validate_model(report)
        report = self.model()
        report["events"].pop()
        with self.assertRaises(ValueError):
            cli.validate_model(report)
        report = self.model()
        report["physicalTransactions"][0]["runtimeIdentity"] = "certain"
        with self.assertRaises(ValueError):
            cli.validate_model(report)

    def test_reflection_unknown_continuation_and_suspension_capability(self):
        reflective = cli.build(self.facts, self.context, "fixture.A#reflective()")
        self.assertEqual(reflective["frames"][0]["continuation"], "UNKNOWN")
        self.assertTrue(reflective["uncertainties"])
        context = copy.deepcopy(self.context)
        context["managerCapabilities"]["tx"]["suspend"] = None
        r = self.model("requires_new", context=context)
        self.assertFalse(r["suspensions"])
        self.assertEqual(len(r["physicalTransactions"]), 1)
        self.assertEqual(r["frames"][1]["duringState"]["kind"], "UNKNOWN")

    def test_pipeline_write_observation_and_jdk_arguments(self):
        helper_spec = importlib.util.spec_from_file_location(
            "factory_test_helpers", ROOT / "tests/mana-skill-factory.py"
        )
        helpers = importlib.util.module_from_spec(helper_spec)
        helper_spec.loader.exec_module(helpers)
        before = snapshot(FIXTURE)
        with (
            helpers.recording_writes() as events,
            mock.patch.object(subprocess, "run", wraps=subprocess.run) as calls,
        ):
            cli.analyze(FIXTURE, FIXTURE / "context.json", "fixture.A#nested()")
        self.assertTrue(events)
        self.assertFalse(
            [
                e
                for e in events
                if FIXTURE in Path(e[1]).parents or Path(e[1]) == FIXTURE
            ]
        )
        for call in calls.call_args_list:
            cwd = Path(call.kwargs["cwd"])
            self.assertNotIn(FIXTURE, cwd.parents)
            self.assertTrue(
                all(
                    call.kwargs["env"][v] == str(cwd) for v in ["TMPDIR", "TEMP", "TMP"]
                )
            )
            self.assertFalse(any(str(FIXTURE) in str(arg) for arg in call.args[0]))
        self.assertEqual(snapshot(FIXTURE), before)

    def test_java_parser_does_not_treat_comments_or_strings_as_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            shutil.copytree(FIXTURE, root / "project")
            project = root / "project"
            path = project / "src/main/java/fixture/Scenario.java"
            path.write_text(
                path.read_text().replace(
                    "b.required();", "/* b.independent(); */ b.required();", 1
                )
            )
            before = snapshot(project)
            report = cli.analyze(
                project, project / "context.json", "fixture.A#required()"
            )
            self.assertEqual(len(report["physicalTransactions"]), 1)
            self.assertEqual(snapshot(project), before)
            path.write_text(
                path.read_text().replace(
                    "b.required();", 'String x="b.independent()";', 1
                )
            )
            report = cli.analyze(
                project, project / "context.json", "fixture.A#required()"
            )
            self.assertTrue(report["uncertainties"])
            self.assertEqual(len(report["frames"]), 1)
            path.write_text(
                path.read_text().replace(
                    'String x="b.independent()";',
                    "b.consume(() -> b.independent());",
                    1,
                )
            )
            report = cli.analyze(
                project, project / "context.json", "fixture.A#required()"
            )
            self.assertEqual(len(report["frames"]), 1)
            self.assertTrue(report["uncertainties"])

    def test_parser_temporary_isolation_and_no_target_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project = root / "project"
            shutil.copytree(FIXTURE, project)
            marker = project / "EXECUTED"
            wrapper = project / "mvnw"
            wrapper.write_text(f'#!/bin/sh\ntouch "{marker}"\n')
            wrapper.chmod(0o755)
            with (
                mock.patch.dict(os.environ, {"TMPDIR": str(project)}),
                mock.patch.object(subprocess, "run") as child,
            ):
                with self.assertRaisesRegex(ValueError, "temporary parent"):
                    cli.analyze(
                        project, project / "context.json", "fixture.A#required()"
                    )
                child.assert_not_called()
            self.assertFalse(marker.exists())

    def test_plantuml_syntax_and_svg_for_all_oracles(self):
        jar = Path(
            os.environ.get("MANA_PLANTUML_JAR", "/Applications/plantuml-1.2024.8.jar")
        )
        if not jar.is_file():
            self.skipTest(
                "local PlantUML jar unavailable; syntax qualification NOT RUN"
            )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in self.oracles:
                (root / (name + ".puml")).write_text(cli.render(self.model(name)))
            args = [
                "java",
                "-Djava.awt.headless=true",
                "-Djava.io.tmpdir=" + str(root),
                "-XX:-UsePerfData",
                "-jar",
                str(jar),
            ]
            checked = subprocess.run(
                [*args, "-checkonly", *map(str, sorted(root.glob("*.puml")))],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            rendered = subprocess.run(
                [*args, "-tsvg", *map(str, sorted(root.glob("*.puml")))],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertEqual(len(list(root.glob("*.svg"))), len(self.oracles))
            self.assertTrue(
                all("Syntax Error" not in p.read_text() for p in root.glob("*.svg"))
            )
            invalid = root / "invalid.puml"
            invalid.write_text(
                "@startuml\nparticipant A\nA -> B: message\nthis is not a valid statement {{{\n@enduml\n"
            )
            negative = subprocess.run(
                [*args, "-checkonly", str(invalid)],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertNotEqual(
                negative.returncode, 0, "PlantUML negative control must fail"
            )

    def test_renderer_contains_explicit_identity_and_no_injected_directive(self):
        r = self.model("requires_new")
        text = cli.render(r)
        for tag in ["P1", "P2", "L1", "L2", "SUSPEND", "RESUME", "UNKNOWN"]:
            self.assertIn(tag, text)
        nested = cli.render(self.model("nested"))
        self.assertIn("L2 P1", nested)
        self.assertNotIn("PHYSICAL_BEGIN P2", nested)
        self.assertIn("SAVEPOINT_CREATE SP1 P1", nested)
        r["frames"][0]["calleeMethod"] = "evil\n!include evil#method()"
        text = cli.render(r)
        self.assertNotIn("\n!include", text)


if __name__ == "__main__":
    unittest.main()
