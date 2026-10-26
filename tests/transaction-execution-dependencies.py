"""Recovery-only executable facts, checked by an independent Java oracle.

All cases also check that recovery does not authorize canonical T01 traversal.
The Java probe never generates or runs application/fixture bytecode.
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

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/transaction-execution-dependencies"
spec = importlib.util.spec_from_file_location(
    "execution_cli", ROOT / "scripts/mana-resource-timeline.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
from skill_factory.transactions.execution import (  # noqa: E402
    execution_dependencies,
    verify_execution_snapshot,
)
from skill_factory.transactions.source import java_facts  # noqa: E402


class ExecutionDependencies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = Path(shutil.which("javac")).resolve()
        home = compiler.parent.parent
        if compiler == Path("/usr/bin/javac"):
            home = Path(
                subprocess.check_output(["/usr/libexec/java_home"], text=True).strip()
            )
        cls.environment = {"jdkHome": str(home), "release": "8", "classpath": []}
        cls.home = home
        cls.stage = tempfile.TemporaryDirectory(prefix="mana-exec-oracle-")
        cls.empty = Path(cls.stage.name) / "empty"
        cls.empty.mkdir()
        cls.classes = Path(cls.stage.name) / "classes"
        cls.classes.mkdir()
        cls.cp = str(cls.classes)
        if (home / "lib/tools.jar").exists():
            cls.cp += os.pathsep + str(home / "lib/tools.jar")
        result = subprocess.run(
            [
                str(home / "bin/javac"),
                "-J-Xmx128m",
                "-proc:none",
                "-cp",
                cls.cp,
                "-d",
                str(cls.classes),
                str(FIXTURE / "ExecutionOracle.java"),
            ],
            capture_output=True,
            timeout=60,
        )
        assert result.returncode == 0, "independent oracle compilation failed"
        cls.cache = {}

    @classmethod
    def tearDownClass(cls):
        cls.stage.cleanup()

    def case(self, name):
        if name in self.cache:
            return self.cache[name]
        files = {name + ".java": (FIXTURE / (name + ".java")).read_bytes()}
        if name == "Propagation":
            files.update(
                {
                    "support/" + p.name: p.read_bytes()
                    for p in (FIXTURE / "support").glob("*.java")
                }
            )
        facts = java_facts(cli.t01.factory, FIXTURE, files, source_snapshot=True)
        evidence = next(
            m["evidence"]
            for c in facts["classes"]
            for m in c["methods"]
            if m["name"] == "run"
        )
        deps = ["fixture." + name + ".Nested"]
        witness, cost = execution_dependencies(
            cli.t01.factory,
            FIXTURE,
            files,
            evidence,
            deps,
            self.environment,
            parse_facts=facts,
        )
        oracle = subprocess.run(
            [
                str(self.home / "bin/java"),
                "-XX:-UsePerfData",
                "-Xmx128m",
                "-Xss1m",
                "-cp",
                self.cp,
                "ExecutionOracle",
                str(self.empty),
                str(self.empty),
                *[str(FIXTURE / p) for p in files],
            ],
            capture_output=True,
            timeout=60,
        )
        self.assertEqual(oracle.returncode, 0)
        rows = [json.loads(line) for line in oracle.stdout.splitlines()]
        execution = witness.get("execution", {})
        for site in execution.get("sites", []):
            if site["binding"] != "VERIFIED":
                continue
            matches = [
                r
                for r in rows
                if r.get("kind") == "CALL"
                and all(
                    r[k] == site[k]
                    for k in ("caller", "target", "dispatch", "bodyAvailable")
                )
                and all(r[k] == site["site"][k] for k in ("start", "end"))
            ]
            self.assertTrue(
                matches, "independent invocation identity/dispatch/body/span mismatch"
            )
        self.assertNotIn("EXEC_SECRET_LITERAL", json.dumps(witness))
        context = {
            "schema": "mana.transaction-context/v1",
            "initialState": "NO_TRANSACTION",
            "entryThroughProxy": False,
            "managerCapabilities": {},
        }
        model = cli.t01.build(facts, context, "fixture." + name + "#run")
        cli.t01.validate_model(model)
        if name != "Irrelevant":
            self.assertEqual(len(model["frames"]), 1)
            self.assertEqual(model["frames"][0]["bodyTraversal"], "NOT_ASSERTED")
        self.cache[name] = witness, rows, files, facts, cost
        return self.cache[name]

    def sites(self, name):
        return self.case(name)[0]["execution"]["sites"]

    def test_01_static_nested_body(self):
        site = self.sites("Static")[0]
        self.assertEqual(site["target"], "fixture.Static.Nested#work()")
        self.assertTrue(site["bodyAvailable"])
        self.assertEqual(site["dispatchCertainty"], "DECLARATION_EXACT")

    def test_02_nonstatic_enclosing_instance_remains_unknown(self):
        sites = self.sites("Member")
        self.assertTrue(any("ENCLOSING_INSTANCE_UNKNOWN" in s["limits"] for s in sites))

    def test_03_constructor_is_not_ordinary_method_execution(self):
        site = self.sites("Constructor")[0]
        self.assertEqual(site["dispatch"], "CONSTRUCTOR")
        self.assertIn("CONSTRUCTION_LIFECYCLE_NOT_MODELED", site["limits"])

    def test_04_unique_overload_preserves_argument_limit(self):
        site = self.sites("Unique")[0]
        self.assertEqual(site["target"], "fixture.Unique.Nested#work(java.lang.String)")
        self.assertIn("ARGUMENT_EXECUTION_NOT_MODELED", site["limits"])

    def test_05_ambiguous_overload_never_certified(self):
        witness, rows, *_ = self.case("Ambiguous")
        self.assertTrue(rows[-1]["errors"])
        self.assertTrue(any("ambiguous" in r.get("diagnostic", "") for r in rows))
        self.assertFalse(
            any(s["binding"] == "VERIFIED" for s in witness["execution"]["sites"])
        )

    def test_06_virtual_target_stays_unknown(self):
        site = self.sites("Virtual")[0]
        self.assertEqual(site["binding"], "VERIFIED")
        self.assertEqual(site["dispatchCertainty"], "UNKNOWN")

    def test_07_declaration_does_not_supply_body(self):
        site = self.sites("Missing")[0]
        self.assertFalse(site["bodyAvailable"])
        self.assertIn("BODY_UNAVAILABLE", site["limits"])

    def test_08_irrelevant_member_is_not_expanded(self):
        witness = self.case("Irrelevant")[0]
        self.assertEqual(witness["execution"]["sites"], [])
        self.assertEqual(len(witness["execution"]["methods"]), 1)

    def test_09_cycle_is_bounded_but_repeated_calls_are_not_cycles(self):
        sites = self.sites("Cycle")
        root = [s for s in sites if s["level"] == 0]
        self.assertEqual(len(root), 2)
        self.assertTrue(
            all("CYCLIC_EXECUTION_DEPENDENCY" not in s["limits"] for s in root)
        )
        self.assertEqual(
            sum("CYCLIC_EXECUTION_DEPENDENCY" in s["limits"] for s in sites), 2
        )

    def test_10_transaction_annotation_is_not_interception(self):
        witness = self.case("Propagation")[0]
        method = next(
            m
            for m in witness["execution"]["methods"]
            if m["identity"].endswith("#work()")
        )
        self.assertEqual(method["transaction"][0]["propagation"], "REQUIRES_NEW")
        self.assertEqual(method["transaction"][0]["effect"], "NOT_ASSERTED")

    def test_11_parameterized_entry_preserved(self):
        witness = self.case("Parameterized")[0]
        self.assertEqual(
            witness["execution"]["methods"][0]["identity"],
            "fixture.Parameterized#run(java.util.List<java.lang.String>)",
        )

    def test_12_control_frontier_remains_unasserted(self):
        witness = self.case("Frontier")[0]
        self.assertIn("UNSUPPORTED_IF", witness["execution"]["methods"][0]["hazards"])
        self.assertTrue(
            all(s["traversal"] == "NOT_ASSERTED" for s in witness["execution"]["sites"])
        )

    def test_13_replay_rejects_body_tampering(self):
        witness, _, files, facts, _ = self.case("Static")
        changed = copy.deepcopy(witness)
        changed["execution"]["sites"][0]["bodyAvailable"] = False
        with self.assertRaisesRegex(ValueError, "contradicts pinned replay"):
            verify_execution_snapshot(
                changed,
                cli.t01.factory,
                FIXTURE,
                files,
                self.environment,
                parse_facts=facts,
                request=witness["request"],
            )

    def test_14_budget_retains_no_positive_execution_facts(self):
        witness, _, files, facts, _ = self.case("Static")
        blocked, _ = execution_dependencies(
            cli.t01.factory,
            FIXTURE,
            files,
            witness["request"]["entry"],
            witness["request"]["dependencies"],
            self.environment,
            parse_facts=facts,
            limits={"nodes": 1},
        )
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertNotIn("execution", blocked)


if __name__ == "__main__":
    unittest.main()
