"""Independent Java expectations at the declaration/execution contract boundary."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "exec_probe", ROOT / "tests/transaction-execution-dependencies.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
from skill_factory.transactions.executable_contract import (  # noqa: E402
    FIELD,
    build_with_dependencies,
    verify_model_dependencies,
)

CONTEXT = {
    "schema": "mana.transaction-context/v1",
    "initialState": "NO_TRANSACTION",
    "entryThroughProxy": False,
    "managerCapabilities": {},
}


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe.ExecutionDependencies.setUpClass()
        cls.probe = probe.ExecutionDependencies()
        cls.models = {}

    @classmethod
    def tearDownClass(cls):
        probe.ExecutionDependencies.tearDownClass()

    def model(self, name):
        if name in self.models:
            return copy.deepcopy(self.models[name])
        witness, _, files, facts, _ = self.probe.case(name)
        entry = "fixture." + name + "#run"
        baseline = probe.cli.t01.build(facts, CONTEXT, entry)
        before = copy.deepcopy((witness, files, facts))
        model = build_with_dependencies(
            facts,
            CONTEXT,
            entry,
            witness,
            probe.cli.t01.factory,
            probe.FIXTURE,
            files,
            self.probe.environment,
            parse_facts=facts,
            request=witness["request"],
        )
        self.assertEqual(before, (witness, files, facts))
        without = copy.deepcopy(model)
        del without[FIELD]
        if "evidence" not in baseline:
            del without["evidence"]
        self.assertEqual(without, baseline)
        timeline = probe.cli.build_timeline(model, facts)
        probe.cli.validate_timeline(timeline)
        self.assertEqual(timeline["transactionModel"], model)
        self.assertEqual(timeline["observations"], [])
        for record in model[FIELD]["records"]:
            self.assertEqual(record["admission"], "NOT_ASSERTED")
            self.assertEqual(record["reachability"], "NOT_ASSERTED")
            self.assertEqual(record["runtimeExecution"], "NOT_OBSERVED")
            self.assertEqual(record["dependencyCompleteness"], "INCOMPLETE")
        self.models[name] = model
        return copy.deepcopy(model)

    def test_01_static_binding_does_not_assert_reachability(self):
        records = self.model("Static")[FIELD]["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["dispatch"], "STATIC")
        self.assertEqual(records[0]["binding"], "VERIFIED")
        self.assertEqual(records[0]["relation"], "STATIC_BINDING")

    def test_02_nested_owner_and_site_identity(self):
        record = self.model("Static")[FIELD]["records"][0]
        self.assertEqual(record["targetMethod"], "fixture.Static.Nested#work()")
        self.assertEqual(record["callerMethod"], "fixture.Static#run()")
        self.assertEqual(record["idKind"], "SOURCE_SITE")
        self.assertNotEqual(record["callSite"], record["targetDeclaration"])

    def test_03_ambiguous_overload_never_becomes_binding(self):
        records = self.model("Ambiguous")[FIELD]["records"]
        self.assertTrue(records)
        self.assertTrue(all(r["binding"] == "UNRESOLVED" for r in records))
        self.assertTrue(all(r["targetMethod"] is None for r in records))

    def test_04_virtual_binding_does_not_resolve_runtime_target(self):
        record = self.model("Virtual")[FIELD]["records"][0]
        self.assertEqual(record["binding"], "VERIFIED")
        self.assertEqual(record["dispatchCertainty"], "UNKNOWN")
        self.assertIn("RUNTIME_DISPATCH_UNKNOWN", record["limits"])

    def test_05_declared_target_has_no_body(self):
        record = self.model("Missing")[FIELD]["records"][0]
        self.assertEqual(record["declarationAvailability"], "SOURCE")
        self.assertFalse(record["bodyAvailable"])
        self.assertIn("BODY_UNAVAILABLE", record["limits"])

    def test_06_conditional_path_remains_unasserted(self):
        model = self.model("Frontier")
        self.assertEqual(model[FIELD]["records"][0]["binding"], "VERIFIED")
        self.assertEqual(model["frames"][0]["bodyTraversal"], "NOT_ASSERTED")
        self.assertEqual(len(model["frames"]), 1)

    def test_07_annotation_does_not_establish_spring_interception(self):
        record = self.model("Propagation")[FIELD]["records"][0]
        self.assertEqual(record["transactionInterception"], "NOT_ASSERTED")
        self.assertEqual(self.model("Propagation")["logicalScopes"], [])

    def test_08_omitted_relevant_site_fails_pinned_replay(self):
        model = self.model("Static")
        model[FIELD]["records"].clear()
        with self.assertRaises(ValueError):
            probe.cli.t01.validate_model(model)
        model = self.model("Static")
        # Even a self-consistent forged catalog must fail the source replay.
        model[FIELD]["witness"]["execution"]["sites"].clear()
        model[FIELD]["records"].clear()
        witness, _, files, facts, _ = self.probe.case("Static")
        with self.assertRaisesRegex(ValueError, "contradicts pinned replay"):
            verify_model_dependencies(
                model,
                probe.cli.t01.factory,
                probe.FIXTURE,
                files,
                self.probe.environment,
                parse_facts=facts,
                request=witness["request"],
            )

    def test_09_cycle_retains_frontier_without_absence_claim(self):
        records = self.model("Cycle")[FIELD]["records"]
        self.assertEqual(
            sum("CYCLIC_EXECUTION_DEPENDENCY" in r["limits"] for r in records), 2
        )
        self.assertEqual(self.model("Cycle")[FIELD]["completeness"], "INCOMPLETE")

    def test_10_parameterized_entry_identity_is_not_rewritten(self):
        extension = self.model("Parameterized")[FIELD]
        self.assertEqual(
            extension["entryDeclaration"],
            "fixture.Parameterized#run(java.util.List<java.lang.String>)",
        )
        self.assertEqual(extension["t01Entry"], extension["entryDeclaration"])

    def test_11_unknown_and_observed_promotions_rejected(self):
        for key, value in [
            ("reachability", "KNOWN"),
            ("runtimeExecution", "OBSERVED"),
            ("dispatchCertainty", "DECLARATION_EXACT"),
            ("dependencyCompleteness", "COMPLETE"),
        ]:
            model = self.model("Virtual")
            model[FIELD]["records"][0][key] = value
            with self.assertRaises(ValueError):
                probe.cli.t01.validate_model(model)

    def test_12_provenance_and_containment_tampering_rejected(self):
        for key, value in [("start", 0), ("sha256", "0" * 64)]:
            model = self.model("Static")
            model[FIELD]["witness"]["execution"]["sites"][0]["site"][key] = value
            with self.assertRaises(ValueError):
                probe.cli.t01.validate_model(model)
        self.assertNotIn("EXEC_SECRET_LITERAL", json.dumps(self.model("Frontier")))


if __name__ == "__main__":
    unittest.main()
