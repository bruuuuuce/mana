"""Literal binding expectations and an independent javac/javap oracle.

Only synthetic fixture bytecode is generated, solely by the external oracle;
no fixture bytecode is executed. The adapter itself must generate none.
"""

import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/transaction-member-bindings"
spec = importlib.util.spec_from_file_location(
    "hybrid_cli", ROOT / "scripts/mana-resource-timeline.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
from skill_factory.transactions.source import java_facts  # noqa: E402
from skill_factory.transactions.semantic import member_bindings, verify_member_snapshot  # noqa: E402


def jdk_home():
    java = Path(shutil.which("javac")).resolve()
    # macOS /usr/bin/javac is a launcher, not a toolchain.
    if java == Path("/usr/bin/javac") and Path("/usr/libexec/java_home").exists():
        return subprocess.check_output(["/usr/libexec/java_home"], text=True).strip()
    return str(java.parent.parent)


class MemberBindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = {"jdkHome": jdk_home(), "release": "8", "classpath": []}
        cls.before = {p.name: p.read_bytes() for p in FIXTURE.iterdir()}
        cls.facts = {
            name: java_facts(
                cli.t01.factory, FIXTURE, {name: raw}, source_snapshot=True
            )
            for name, raw in cls.before.items()
            if name.endswith(".java")
        }
        cls.cache = {}

    @classmethod
    def tearDownClass(cls):
        assert cls.before == {p.name: p.read_bytes() for p in FIXTURE.iterdir()}

    def analyze(self, name="Good", method="run", dependencies=None, **kwargs):
        filename = name + ".java"
        facts = self.facts[filename]
        evidence = next(
            m["evidence"]
            for c in facts["classes"]
            if c["name"] == "fixture." + name
            for m in c["methods"]
            if m["name"] == method
        )
        deps = (
            dependencies
            if dependencies is not None
            else ["fixture." + name + ".Result"]
        )
        return member_bindings(
            cli.t01.factory,
            FIXTURE,
            {filename: self.before[filename]},
            evidence,
            deps,
            kwargs.pop("environment", self.environment),
            parse_facts=kwargs.pop("parse_facts", facts),
            **kwargs,
        )

    def good(self):
        if "good" not in self.cache:
            self.cache["good"] = self.analyze(
                dependencies=["fixture.Good.Result", "fixture.Good.Failure"]
            )
        return copy.deepcopy(self.cache["good"])

    def test_plain_has_no_supplement_requirement(self):
        witness, _ = self.analyze("Plain", dependencies=[])
        self.assertEqual(witness["status"], "COMPLETE")
        self.assertEqual(witness["types"], [])
        facts = self.facts["Plain.java"]
        context = {
            "schema": "mana.transaction-context/v1",
            "initialState": "NO_TRANSACTION",
            "entryThroughProxy": False,
            "managerCapabilities": {},
        }
        before = cli.t01.build(facts, context, "fixture.Plain#run()")
        self.analyze("Plain", dependencies=[])
        self.assertEqual(before, cli.t01.build(facts, context, "fixture.Plain#run()"))

    def test_static_member_identity_owner_and_members(self):
        witness, _ = self.good()
        self.assertEqual(witness["status"], "COMPLETE", witness["reason"])
        result = next(
            t for t in witness["types"] if t["identity"] == "fixture.Good.Result"
        )
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["owner"], "fixture.Good")
        self.assertEqual(result["relation"], "TYPE_CONTAINMENT")
        self.assertIn("static", result["modifiers"])
        self.assertTrue(
            any(
                m["identity"] == "fixture.Good.Result#value()"
                for m in result["members"]
            )
        )

    def test_nonstatic_member_remains_unresolved(self):
        witness, _ = self.analyze(method="inner", dependencies=["fixture.Good.Inner"])
        self.assertEqual(witness["status"], "INCOMPLETE")
        self.assertTrue(all(r["status"] == "UNRESOLVED" for r in witness["relations"]))
        self.assertEqual(witness["types"][0]["reason"], "NON_STATIC_MEMBER")

    def test_used_types_and_production_and_constructor_binding(self):
        witness, _ = self.good()
        targets = {r["target"] for r in witness["relations"]}
        self.assertIn("fixture.Good#produce()", targets)
        self.assertIn("fixture.Good.Failure#<init>(java.lang.String)", targets)
        self.assertIn("fixture.Good.Result#value()", targets)
        productions = [
            r for r in witness["relations"] if r["relation"] == "VALUE_PRODUCTION"
        ]
        self.assertTrue(productions)
        self.assertTrue(
            all(
                r["valueDeclaration"]["start"] < r["site"]["start"]
                and r["typeSite"]["end"] <= r["site"]["start"]
                for r in productions
            )
        )
        self.assertTrue(
            all(
                r["site"]["sha256"] == witness["sources"]["Good.java"]
                for r in witness["relations"]
            )
        )

    def test_irrelevant_type_not_expanded(self):
        witness, _ = self.good()
        self.assertNotIn(
            "fixture.Good.Irrelevant", {t["identity"] for t in witness["types"]}
        )
        witness, _ = self.analyze(method="zero", dependencies=["fixture.Good.Result"])
        self.assertEqual(witness["relations"], [])

    def test_actual_superclass_and_inherited_method(self):
        witness, _ = self.good()
        result = next(
            t for t in witness["types"] if t["identity"] == "fixture.Good.Result"
        )
        self.assertIn("fixture.Good.Base", {p["target"] for p in result["parents"]})
        self.assertIn(
            "fixture.Good.Base#inherited()", {r["target"] for r in witness["relations"]}
        )
        self.assertTrue(
            all(p["relation"] == "TYPE_INHERITANCE" for p in result["parents"])
        )

    def test_actual_interface(self):
        witness, _ = self.good()
        result = next(
            t for t in witness["types"] if t["identity"] == "fixture.Good.Result"
        )
        self.assertIn("fixture.Good.Relevant", {p["target"] for p in result["parents"]})

    def test_member_shadows_top_level(self):
        witness, _ = self.analyze("Shadow")
        self.assertEqual(witness["status"], "COMPLETE")
        self.assertIn(
            "fixture.Shadow.Result#<init>()",
            {r["target"] for r in witness["relations"]},
        )
        self.assertNotIn("fixture.Result", {r["target"] for r in witness["relations"]})

    def test_ambiguous_binding_never_selects_candidate(self):
        witness, _ = self.analyze("Ambiguous")
        self.assertEqual(witness["status"], "INCOMPLETE")
        self.assertTrue(witness["diagnostics"])
        self.assertTrue(
            all(
                m["declaredSignature"] and m["identity"] is None
                for m in witness["types"][0]["members"]
            )
        )
        self.assertFalse(any(r["status"] == "VERIFIED" for r in witness["relations"]))
        self.assertTrue(all(r["target"] is None for r in witness["relations"]))

    def test_missing_dependency_and_no_implicit_classpath(self):
        for name in ("Missing", "External"):
            witness, _ = self.analyze(name)
            self.assertEqual(witness["status"], "INCOMPLETE")
            self.assertEqual(witness["types"][0]["status"], "UNRESOLVED")
            self.assertFalse(
                any(r["status"] == "VERIFIED" for r in witness["relations"])
            )
        witness, _ = self.analyze(dependencies=["fixture.Good.Absent"])
        self.assertEqual(witness["types"][0]["status"], "ABSENT")

    def test_overload_and_six_parameters(self):
        witness, _ = self.analyze(method="six")
        self.assertEqual(witness["status"], "COMPLETE")
        targets = {r["target"] for r in witness["relations"]}
        self.assertIn("fixture.Good#produce(java.lang.String)", targets)
        self.assertNotIn("fixture.Good#produce()", targets)
        self.assertTrue(
            all(r["runtimeDispatch"] == "UNKNOWN" for r in witness["relations"])
        )

    def test_cycle_does_not_expand_call_graph(self):
        witness, metrics = self.analyze(method="cycle")
        self.assertEqual(witness["status"], "COMPLETE")
        self.assertLess(metrics["nodes"], 1000)
        self.assertEqual(witness["transactionTraversal"], "NOT_ASSERTED")

    def test_node_depth_source_time_and_output_budgets(self):
        for limits, reason in (
            ({"nodes": 2}, "NODE_OR_DEPTH_BUDGET"),
            ({"depth": 2}, "NODE_OR_DEPTH_BUDGET"),
            ({"sourceBytes": 1}, "SOURCE_BUDGET"),
            ({"outputBytes": 1}, "OUTPUT_BUDGET"),
        ):
            witness, _ = self.analyze(limits=limits)
            self.assertEqual(witness["status"], "BLOCKED", (limits, witness["reason"]))
            self.assertEqual(witness["reason"], reason)
            self.assertEqual(witness["relations"], [])
        with patch(
            "skill_factory.transactions.semantic.subprocess.run",
            side_effect=subprocess.TimeoutExpired("fixed-helper", 60),
        ):
            witness, _ = self.analyze()
        self.assertEqual(witness["reason"], "TIME_BUDGET")
        self.assertEqual(witness["relations"], [])

    def test_verifier_tool_failure_is_not_a_fact_conflict(self):
        with patch(
            "skill_factory.transactions.semantic.verify_leaf_snapshot",
            side_effect=ValueError("JDK parser timeout HYBRID_SECRET_ARGUMENT"),
        ):
            witness, _ = self.analyze()
        self.assertEqual(witness["status"], "BLOCKED")
        self.assertEqual(witness["reason"], "PARSE_VERIFICATION_UNAVAILABLE")
        self.assertNotIn("HYBRID_SECRET_ARGUMENT", json.dumps(witness))

    def test_conflicting_parser_facts_are_not_preferred(self):
        facts = copy.deepcopy(self.facts["Good.java"])
        facts["classes"][0]["methods"][0]["name"] = "wrongTarget"
        witness, _ = self.analyze(parse_facts=facts)
        self.assertEqual(witness["status"], "CONFLICT")
        self.assertEqual(witness["relations"], [])

    def test_determinism_and_independent_snapshot_replay(self):
        witness, _ = self.good()
        other, _ = self.analyze(
            dependencies=["fixture.Good.Failure", "fixture.Good.Result"]
        )
        self.assertEqual(witness, other)
        self.assertEqual(
            verify_member_snapshot(
                witness,
                cli.t01.factory,
                FIXTURE,
                {"Good.java": self.before["Good.java"]},
                self.environment,
                parse_facts=self.facts["Good.java"],
                request=witness["request"],
            ),
            "COMPLETE",
        )
        tampered = copy.deepcopy(witness)
        tampered["relations"][0]["target"] = "fixture.Wrong"
        with self.assertRaises(ValueError):
            verify_member_snapshot(
                tampered,
                cli.t01.factory,
                FIXTURE,
                {"Good.java": self.before["Good.java"]},
                self.environment,
                parse_facts=self.facts["Good.java"],
                request=witness["request"],
            )

    def test_source_containment_and_tool_failure(self):
        witness, _ = self.good()
        self.assertNotIn("HYBRID_SECRET_ARGUMENT", json.dumps(witness))
        self.assertNotIn("sources", json.dumps(witness["types"]))
        env = self.environment | {"jdkHome": "/missing-jdk-HYBRID_SECRET_ARGUMENT"}
        failed, _ = self.analyze(environment=env)
        self.assertEqual(failed["status"], "BLOCKED")
        self.assertNotIn("HYBRID_SECRET_ARGUMENT", json.dumps(failed))

    def test_manifest_classpath_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="mana-hybrid-manifest-") as temporary:
            jar = Path(temporary) / "dependency.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr(
                    "META-INF/MANIFEST.MF",
                    "Manifest-Version: 1.0\nClass-Path: elsewhere.jar\n",
                )
            witness, _ = self.analyze(
                environment=self.environment | {"classpath": [str(jar)]}
            )
            self.assertEqual(witness["reason"], "IMPLICIT_MANIFEST_CLASSPATH")

    def test_offline_classpath_binding_and_changed_environment_rejected(self):
        with tempfile.TemporaryDirectory(prefix="mana-hybrid-offline-") as temporary:
            stage = Path(temporary).resolve()
            base = stage / "Base.java"
            base.write_text("package offline; public class Base {}")
            home = Path(self.environment["jdkHome"])
            subprocess.run(
                [str(home / "bin/javac"), "-proc:none", "-d", str(stage), str(base)],
                check=True,
                capture_output=True,
                timeout=60,
            )
            jar = stage / "offline.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.write(stage / "offline/Base.class", "offline/Base.class")
            env = self.environment | {"classpath": [str(jar)]}
            limited, _ = self.analyze(
                "External", environment=env, limits={"classpathBytes": 1}
            )
            self.assertEqual(limited["reason"], "CLASSPATH_BUDGET")
            witness, _ = self.analyze("External", environment=env)
            self.assertEqual(witness["status"], "COMPLETE")
            self.assertEqual(
                witness["types"][0]["parents"][0]["target"], "offline.Base"
            )
            with zipfile.ZipFile(jar, "a") as archive:
                archive.writestr("changed.txt", "different offline environment")
            with self.assertRaises(ValueError):
                verify_member_snapshot(
                    witness,
                    cli.t01.factory,
                    FIXTURE,
                    {"External.java": self.before["External.java"]},
                    env,
                    parse_facts=self.facts["External.java"],
                    request=witness["request"],
                )

    def test_cli_safe_output_and_negative_frontier(self):
        with tempfile.TemporaryDirectory(prefix="mana-hybrid-cli-") as temporary:
            stage = Path(temporary).resolve()
            for name in ("Good", "Ambiguous"):
                request = {
                    "sources": [name + ".java"],
                    "entry": "fixture." + name + "#run",
                    "dependencies": ["fixture." + name + ".Result"],
                    "environment": self.environment,
                }
                path = stage / (name + ".json")
                path.write_text(json.dumps(request))
                out = stage / (name + "-output")
                result = subprocess.run(
                    [
                        "python3",
                        str(ROOT / "scripts/mana-java-member-bindings.py"),
                        "--project-root",
                        str(FIXTURE),
                        "--request",
                        str(path),
                        "--output-dir",
                        str(out),
                    ],
                    capture_output=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0 if name == "Good" else 2)
                self.assertNotIn(
                    b"HYBRID_SECRET_ARGUMENT", result.stdout + result.stderr
                )
                self.assertEqual(result.stderr, b"")
                witness = json.loads((out / "member-bindings.json").read_text())
                self.assertEqual(
                    witness["status"], "COMPLETE" if name == "Good" else "INCOMPLETE"
                )
                self.assertNotIn("HYBRID_SECRET_ARGUMENT", json.dumps(witness))
                self.assertEqual(
                    set(p.name for p in out.iterdir()),
                    {"member-bindings.json", "cost.json"},
                )

    def test_external_javac_javap_oracles(self):
        # Expectations are literal, independent of Mana output. Compile each
        # inventory separately: Missing/Ambiguous are deliberately invalid.
        home = Path(self.environment["jdkHome"])
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in (
                "JAVA_TOOL_OPTIONS",
                "_JAVA_OPTIONS",
                "JDK_JAVA_OPTIONS",
                "JDK_JAVAC_OPTIONS",
                "CLASSPATH",
            )
        }
        with tempfile.TemporaryDirectory(prefix="mana-hybrid-oracle-") as temporary:
            stage = Path(temporary).resolve()
            for name in ("Good", "Plain", "Shadow", "Ambiguous", "Missing", "External"):
                out = stage / name
                out.mkdir()
                result = subprocess.run(
                    [
                        str(home / "bin/javac"),
                        "-proc:none",
                        "-source",
                        "8",
                        "-target",
                        "8",
                        "-classpath",
                        str(out),
                        "-d",
                        str(out),
                        str(FIXTURE / (name + ".java")),
                    ],
                    env=env,
                    capture_output=True,
                    timeout=60,
                )
                if name in ("Ambiguous", "Missing", "External"):
                    self.assertNotEqual(result.returncode, 0)
                    if name == "Ambiguous":
                        self.assertIn(b"ambiguous", result.stderr)
                    continue
                self.assertEqual(result.returncode, 0)
                output = subprocess.check_output(
                    [
                        str(home / "bin/javap"),
                        "-p",
                        "-c",
                        "-s",
                        "-classpath",
                        str(out),
                        "fixture." + name,
                    ],
                    env=env,
                    timeout=60,
                ).decode()
                if name == "Good":
                    self.assertIn(
                        "produce:(Ljava/lang/String;)Lfixture/Good$Result;", output
                    )
                    self.assertIn('Good$Failure."<init>":(Ljava/lang/String;)V', output)
                    self.assertIn("Good$Result.value:()I", output)
                    nested = subprocess.check_output(
                        [
                            str(home / "bin/javap"),
                            "-p",
                            "-classpath",
                            str(out),
                            "fixture.Good$Result",
                        ],
                        env=env,
                        timeout=60,
                    ).decode()
                    self.assertIn(
                        "extends fixture.Good$Base implements fixture.Good$Relevant",
                        nested,
                    )
                    inner = subprocess.check_output(
                        [
                            str(home / "bin/javap"),
                            "-p",
                            "-classpath",
                            str(out),
                            "fixture.Good$Inner",
                        ],
                        env=env,
                        timeout=60,
                    ).decode()
                    self.assertIn("this$0", inner)
                elif name == "Shadow":
                    self.assertIn('Shadow$Result."<init>":()V', output)
                else:
                    self.assertIn("public void run();", output)


if __name__ == "__main__":
    unittest.main()
