"""Hand-written type/path expectations; javac/javap is a separate type oracle."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/transaction-type-dependencies"
spec = importlib.util.spec_from_file_location(
    "type_s01", ROOT / "scripts/mana-resource-timeline.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
from skill_factory.transactions.source import diagnostic_facts, java_facts  # noqa: E402

CONFIG = b"""package fixture;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
@Configuration @EnableTransactionManagement(proxyTargetClass=true)
class Config { @Bean public DataSourceTransactionManager tx() { return null; } }
@Service class Sink { @Transactional public void required() {} }
"""


class TypeDependencies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = {p.name: p.read_bytes() for p in FIXTURE.iterdir()}
        cls.context = json.loads((FIXTURE / "context.json").read_text())
        cls.facts = {}
        for name in cls.before:
            if name.endswith(".java") and name != "OracleTypes.java":
                cls.facts[name] = java_facts(
                    cli.t01.factory,
                    FIXTURE,
                    {name: cls.before[name], "Config.java": CONFIG},
                    source_snapshot=True,
                )

    def analyze(self, name, selector="run"):
        facts = copy.deepcopy(self.facts[name + ".java"])
        model = cli.t01.build(facts, self.context, "fixture.Entry#" + selector)
        model["evidence"] = [
            {"path": p, "sha256": hashlib.sha256(raw.encode()).hexdigest()}
            for p, raw in facts["sources"].items()
        ]
        cli.t01.validate_model(model)
        timeline = cli.build_timeline(model, facts)
        cli.validate_timeline(timeline)
        self.assertEqual(timeline["transactionModel"], model)
        return model, facts

    def blocked(self, name, reason, selector="run"):
        model, facts = self.analyze(name, selector)
        self.assertEqual(model["uncertainties"][0]["reason"], reason)
        self.assertEqual(model["frames"][0]["bodyTraversal"], "NOT_ASSERTED")
        self.assertEqual(len(model["frames"]), 1)
        return model, facts

    def test_three_irrelevant_members_and_zero_parameters(self):
        model, facts = self.analyze("Positive", "zero()")
        self.assertEqual(model["uncertainties"], [])
        self.assertEqual(len(model["frames"]), 2)
        self.assertEqual(
            [f["duringState"]["physicalId"] for f in model["frames"]], ["P1", "P1"]
        )
        self.assertEqual(
            next(c for c in facts["classes"] if c["name"] == "fixture.Entry")[
                "parents"
            ],
            [],
        )

    def test_six_parameters_same_transaction_path(self):
        model, _ = self.analyze("Positive", "six")
        self.assertEqual(model["uncertainties"], [])
        self.assertEqual(len(model["frames"]), 2)
        self.assertEqual([f["logicalScope"] for f in model["frames"]], ["L1", "L2"])

    def test_static_member_used(self):
        self.blocked("StaticUse", "OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED")

    def test_inner_member_via_field_call(self):
        self.blocked("InnerUse", "OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED")

    def test_real_unresolved_superclass(self):
        _, facts = self.blocked(
            "ExternalBase", "INHERITANCE_OR_INTERFACE_RESOLUTION_NOT_MODELED"
        )
        self.assertEqual(
            next(c for c in facts["classes"] if c["name"] == "fixture.Entry")[
                "parents"
            ],
            ["MissingBase"],
        )

    def test_real_unresolved_interface(self):
        _, facts = self.blocked(
            "InterfaceUse", "INHERITANCE_OR_INTERFACE_RESOLUTION_NOT_MODELED"
        )
        self.assertEqual(
            next(c for c in facts["classes"] if c["name"] == "fixture.Entry")[
                "parents"
            ],
            ["MissingInterface"],
        )

    def test_nested_own_extends_affects_dispatch_not_owner_parents(self):
        model, facts = self.analyze("NestedExtends")
        self.assertEqual(
            next(c for c in facts["classes"] if c["name"] == "fixture.Entry")[
                "parents"
            ],
            [],
        )
        self.assertEqual(
            model["uncertainties"][0]["reason"], "OMITTED_TYPE_DISPATCH_NOT_MODELED"
        )
        self.assertEqual(len(model["frames"]), 1)
        self.assertEqual(model["frames"][0]["bodyTraversal"], "NOT_ASSERTED")
        self.blocked(
            "NestedExtends", "OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED", "use"
        )

    def test_omitted_subtype_does_not_enable_self_dispatch(self):
        self.blocked("SelfSubtype", "OMITTED_TYPE_DISPATCH_NOT_MODELED")

    def test_omitted_subtype_in_other_owner_blocks_injected_dispatch(self):
        model, _ = self.analyze("ForeignSubtype")
        self.assertEqual(len(model["frames"]), 1)
        self.assertEqual(
            model["uncertainties"][0]["reason"], "OMITTED_TYPE_DISPATCH_NOT_MODELED"
        )
        self.assertEqual(model["frames"][0]["continuation"], "UNKNOWN")

    def test_new_limits_require_linked_evidence_and_unasserted_body(self):
        for name in ("StaticUse", "Initializer", "SelfSubtype"):
            model, _ = self.analyze(name)
            bad = copy.deepcopy(model)
            bad["uncertainties"] = []
            with self.assertRaises(ValueError):
                cli.t01.validate_model(bad)
            bad = copy.deepcopy(model)
            bad["frames"][0]["bodyTraversal"] = "STRAIGHT_LINE"
            with self.assertRaises(ValueError):
                cli.t01.validate_model(bad)

    def test_same_named_member_never_binds_top_level_bean(self):
        self.blocked("Ambiguous", "OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED")
        with self.assertRaisesRegex(ValueError, "signature unsupported"):
            self.analyze("Ambiguous", "parameter")

    def test_relevant_omission_in_unextracted_statement(self):
        _, facts = self.blocked(
            "Relevant", "OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED"
        )
        method = next(
            m
            for c in facts["classes"]
            if c["name"] == "fixture.Entry"
            for m in c["methods"]
            if m["name"] == "run"
        )
        self.assertIn("unsupported-control-or-expression", method["hazards"])
        # The dependency occurs in a variable/throw, not a supported call list.
        self.assertIn("omitted-member-type-dependency", method["hazards"])

    def test_local_and_anonymous_remain_unasserted(self):
        for method in ("local", "anonymous"):
            self.blocked(
                "LocalAnonymous",
                "OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED",
                method,
            )

    def test_constructor_dependency_is_not_erased_by_empty_method(self):
        self.blocked("ConstructorUse", "OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED")

    def test_initializer_is_execution_not_inheritance(self):
        _, facts = self.blocked(
            "Initializer", "CLASS_INITIALIZER_EXECUTION_NOT_MODELED"
        )
        self.assertEqual(
            next(c for c in facts["classes"] if c["name"] == "fixture.Entry")[
                "parents"
            ],
            [],
        )

    def test_diagnostics_and_leaf_stay_conservative(self):
        for facts in self.facts.values():
            diagnostic = json.dumps(diagnostic_facts(facts))
            self.assertNotIn("NESTED_SENTINEL_92", diagnostic)
            self.assertNotIn("INITIALIZER_SENTINEL_92", diagnostic)
            self.assertNotIn('"sources"', diagnostic)
            self.assertNotIn('"receiver"', diagnostic)
            self.assertIn("sha256", diagnostic)
        from skill_factory.transactions.resource_leaf import dispatch_blocker

        self.assertIsNotNone(dispatch_blocker(self.facts["Positive.java"]))
        self.assertEqual(
            {p.name: p.read_bytes() for p in FIXTURE.iterdir()}, self.before
        )

    def test_independent_javac_javap_type_relationships(self):
        self.assertIsNotNone(shutil.which("javac"), "Independent Java oracle required")
        self.assertIsNotNone(shutil.which("javap"), "Independent Java oracle required")
        with tempfile.TemporaryDirectory() as temp:
            subprocess.run(
                [
                    "javac",
                    "-proc:none",
                    "-source",
                    "8",
                    "-target",
                    "8",
                    "-d",
                    temp,
                    str(FIXTURE / "OracleTypes.java"),
                ],
                capture_output=True,
                check=True,
            )

            def inspect(symbol, verbose=False):
                return subprocess.run(
                    [
                        "javap",
                        "-classpath",
                        temp,
                        "-p",
                        *(["-v"] if verbose else []),
                        symbol,
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout

            self.assertNotIn("this$0", inspect("OracleTypes$StaticMember"))
            self.assertIn(
                "final OracleTypes this$0", inspect("OracleTypes$InnerMember")
            )
            self.assertIn(
                "extends Base implements Contract", inspect("OracleTypes$Derived")
            )
            self.assertIn(
                "static", inspect("OracleTypes", True).split("InnerClasses:")[1]
            )
            self.assertIn("EnclosingMethod:", inspect("OracleTypes$1Local", True))
            self.assertIn("implements java.lang.Runnable", inspect("OracleTypes$1"))


if __name__ == "__main__":
    unittest.main()
