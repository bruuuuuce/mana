#!/usr/bin/env python3
"""Small literal entry/signature oracles and AST disclosure negative controls."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/transaction-entry-parameters"
spec = importlib.util.spec_from_file_location(
    "entry_s01", ROOT / "scripts/mana-resource-timeline.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
from skill_factory.transactions.source import diagnostic_facts, java_facts  # noqa: E402

SENTINELS = [
    "RECEIVER_SENTINEL_73",
    "ARGUMENT_SENTINEL_73",
    "SENTINEL_TABLE_73",
    "TARGET_EXECUTION_SENTINEL_73",
]


class EntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = cli.t01.factory.project_files(
            FIXTURE, cli.t01.factory.adapter_for("transaction-analysis")
        )
        cls.before = {p: hashlib.sha256(b).hexdigest() for p, b in cls.files.items()}
        cls.facts = java_facts(
            cli.t01.factory, FIXTURE, cls.files, source_snapshot=True
        )
        cls.context = json.loads((FIXTURE / "context.json").read_text())

    def model(self, selector, context=None, facts=None):
        facts = copy.deepcopy(facts or self.facts)
        report = cli.t01.build(
            facts, context or self.context, "fixture.Entry#" + selector
        )
        report["evidence"] = [{"path": p, "sha256": h} for p, h in self.before.items()]
        cli.t01.validate_model(report)
        timeline = cli.build_timeline(report, facts)
        cli.validate_timeline(timeline)
        return report, timeline

    def parameters(self, timeline):
        root = timeline["transactionModel"]["frames"][0]
        return next(
            m["parameters"]
            for c in timeline["sourceFacts"]["classes"]
            for m in c["methods"]
            if m["evidence"] == root["evidence"]
        )

    def test_zero_one_six_annotations_and_generics(self):
        cases = {
            "zero()": [],
            "one(java.lang.String)": ["value"],
            "six(java.lang.String,int,long,boolean,java.util.List<java.lang.String>,byte[])": list(
                "abcdef"
            ),
            "annotated(java.lang.String)": ["value"],
            "generic(java.util.Map<java.lang.String,java.util.List<java.lang.Integer>>)": [
                "values"
            ],
        }
        for signature, names in cases.items():
            with self.subTest(signature=signature):
                report, timeline = self.model(signature)
                self.assertEqual(report["entry"], "fixture.Entry#" + signature)
                root, child = report["frames"]
                self.assertEqual([p["name"] for p in self.parameters(timeline)], names)
                self.assertTrue(
                    all(
                        p["runtimeValue"] == "UNKNOWN"
                        for p in self.parameters(timeline)
                    )
                )
                self.assertEqual(
                    [f["duringState"]["physicalId"] for f in [root, child]],
                    ["P1", "P1"],
                )
                self.assertEqual(
                    [f["logicalScope"] for f in [root, child]], ["L1", "L2"]
                )
                self.assertEqual(child["calleeMethod"], "fixture.Sink#required()")
                self.assertEqual(timeline["transactionModel"], report)
                site = root["evidence"]
                self.assertEqual(site["sha256"], self.before[site["file"]])
                params = self.parameters(timeline)
                self.assertTrue(
                    all(
                        site["start"]
                        <= p["evidence"]["start"]
                        < p["evidence"]["end"]
                        <= site["end"]
                        for p in params
                    )
                )

    def test_overloads_require_exact_signature(self):
        for signature in [
            "arity()",
            "arity(int)",
            "overload(int)",
            "overload(java.lang.String)",
        ]:
            report, _ = self.model(signature)
            self.assertEqual(
                report["frames"][0]["calleeMethod"], "fixture.Entry#" + signature
            )
        for selector in ["arity", "overload", "overload()", "overload(long)"]:
            with (
                self.subTest(selector=selector),
                self.assertRaisesRegex(ValueError, "alternatives.*signature"),
            ):
                self.model(selector)
        self.assertEqual(
            self.model("six")[0]["entry"],
            "fixture.Entry#six(java.lang.String,int,long,boolean,java.util.List<java.lang.String>,byte[])",
        )

    def test_unresolvable_signature_and_malformed_selector(self):
        for selector in ["unresolved", "variable", "missing()"]:
            with (
                self.subTest(selector=selector),
                self.assertRaisesRegex(
                    ValueError, "signature unsupported; alternatives"
                ),
            ):
                self.model(selector)
        with self.assertRaisesRegex(ValueError, "invalid entry selector"):
            self.model('one("EXPRESSION_SENTINEL_73")')

    def test_wildcard_declaration_identity_never_guesses_namespace(self):
        facts = copy.deepcopy(self.facts)
        report = cli.t01.build(facts, self.context, "fixture.Wildcard#unique")
        cli.t01.validate_model(report)
        self.assertEqual(report["entry"], "fixture.Wildcard#unique(Payload)")
        parameter = next(
            m
            for c in facts["classes"]
            for m in c["methods"]
            if m["evidence"] == report["frames"][0]["evidence"]
        )["parameters"][0]
        self.assertIsNone(parameter["type"])
        self.assertEqual(parameter["declaredType"], "Payload")
        self.assertEqual(parameter["typeResolution"], "DECLARED_ONLY")
        for selector in ["ambiguous", "ambiguous(Payload)", "ambiguous(int)"]:
            with (
                self.subTest(selector=selector),
                self.assertRaisesRegex(ValueError, "alternatives"),
            ):
                cli.t01.build(facts, self.context, "fixture.Wildcard#" + selector)

    def test_no_parameter_value_binding_or_dispatch(self):
        report, timeline = self.model("shadow")
        self.assertEqual(len(report["frames"]), 1)
        self.assertEqual(
            report["uncertainties"][0]["reason"],
            "PARAMETER_RECEIVER_RUNTIME_VALUE_UNKNOWN",
        )
        self.assertEqual(timeline["observations"][0]["operationType"], "UNKNOWN")
        report, _ = self.model("parameterCall")
        self.assertEqual(len(report["frames"]), 1)
        self.assertEqual(report["frames"][0]["continuation"], "UNKNOWN")
        context = dict(self.context, resourceLeafPolicy="JDBC_LITERAL_V1")
        report, timeline = self.model("shadowJdbc", context)
        self.assertFalse(
            any(e["kind"] == "RESOURCE_LEAF_CALL" for e in report["events"])
        )
        self.assertEqual(timeline["observations"][0]["operationType"], "UNKNOWN")

    def test_s01_frontier_in_parameterized_method(self):
        report, timeline = self.model("literal")
        observation = timeline["observations"][0]
        self.assertEqual(observation["placement"]["status"], "T01_FRONTIER")
        self.assertEqual(observation["transactionContext"]["physicalId"], "P1")
        self.assertEqual(observation["operationType"], "WRITE")
        self.assertEqual(len(report["frames"]), 1)

    def test_safe_ast_diagnostics_and_receiver_metadata(self):
        default = java_facts(cli.t01.factory, FIXTURE, self.files)
        self.assertEqual(default, diagnostic_facts(self.facts))
        diagnostic = json.dumps(default)
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, diagnostic)
        self.assertNotIn('"receiver"', diagnostic)
        self.assertNotIn('"sources"', diagnostic)
        self.assertIn("sha256", diagnostic)
        self.assertIn("start", diagnostic)
        self.assertIn("fixture.Entry", diagnostic)

    def test_cli_channels_and_explicit_local_artifacts(self):
        for script in ["mana-transaction.py", "mana-resource-timeline.py"]:
            with self.subTest(script=script), tempfile.TemporaryDirectory() as temp:
                result = subprocess.run(
                    [
                        "python3",
                        str(ROOT / "scripts" / script),
                        "--project-root",
                        str(FIXTURE),
                        "--context",
                        str(FIXTURE / "context.json"),
                        "--entry",
                        "fixture.Entry#sentinel",
                        "--output-dir",
                        str(Path(temp).resolve() / "authorized"),
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                for sentinel in SENTINELS:
                    self.assertNotIn(sentinel, result.stdout + result.stderr)
                # S01's versioned snapshot is source-bearing by contract; only the
                # explicitly selected artifact path may contain it. No dump/log.
                self.assertEqual(
                    sorted(p.name for p in Path(temp).iterdir()), ["authorized"]
                )
                if script == "mana-resource-timeline.py":
                    raw = (Path(temp) / "authorized/resource-timeline.json").read_text()
                    self.assertIn("RECEIVER_SENTINEL_73", raw)
                else:
                    for path in (Path(temp) / "authorized").iterdir():
                        for sentinel in SENTINELS:
                            self.assertNotIn(sentinel, path.read_text())

    def test_parser_failures_do_not_echo_source_or_subprocess_stderr(self):
        with self.assertRaises(ValueError) as caught:
            java_facts(
                cli.t01.factory,
                FIXTURE,
                {
                    "Broken.java": b'class Broken { void x() { "ERROR_SENTINEL_73" broken } }'
                },
            )
        self.assertNotIn("ERROR_SENTINEL_73", str(caught.exception))
        self.assertIn("Java syntax unsupported/invalid", str(caught.exception))
        with mock.patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, b"", b"STDERR_SENTINEL_73"),
        ):
            with self.assertRaises(ValueError) as caught:
                java_facts(cli.t01.factory, FIXTURE, self.files)
        self.assertNotIn("STDERR_SENTINEL_73", str(caught.exception))

    def test_parse_only_and_fixture_immutability(self):
        with mock.patch("subprocess.run", wraps=subprocess.run) as calls:
            report = cli.analyze(FIXTURE, FIXTURE / "context.json", "fixture.Entry#six")
        self.assertEqual(
            self.parameters(report)[0]["runtimeValue"],
            "UNKNOWN",
        )
        for call in calls.call_args_list:
            argv = call.args[0]
            self.assertFalse(any("ExecutionTrap" in str(a) for a in argv))
            self.assertNotIn(str(FIXTURE), " ".join(argv))
            if Path(argv[0]).name == "javac":
                self.assertIn("-proc:none", argv)
                self.assertEqual(sum(a.endswith(".java") for a in argv), 1)
                self.assertTrue(argv[-1].endswith("JavaFacts.java"))
        current = cli.t01.factory.project_files(
            FIXTURE, cli.t01.factory.adapter_for("transaction-analysis")
        )
        self.assertEqual(current, self.files)

    def test_historical_leaf_snapshot_remains_valid(self):
        report = json.loads(
            (ROOT / "docs/examples/transaction-01-t02-s02/A/inputs/ta.json").read_text()
        )
        cli.t01.validate_model(report["transactionModel"])

    def test_erasure_collision_is_controlled_with_alternatives(self):
        facts = copy.deepcopy(self.facts)
        cls = next(c for c in facts["classes"] if c["name"] == "fixture.Entry")
        method = copy.deepcopy(
            next(m for m in cls["methods"] if m["name"] == "generic")
        )
        method["parameters"][0]["type"] = (
            "java.util.Map<java.lang.Integer,java.lang.String>"
        )
        cls["methods"].append(method)
        with self.assertRaisesRegex(
            ValueError, "duplicate/ambiguous.*alternatives.*signature.*evidence"
        ):
            cli.t01.build(facts, self.context, "fixture.Entry#generic")


if __name__ == "__main__":
    unittest.main()
