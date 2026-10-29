#!/usr/bin/env python3
"""Literal F01 dispatch oracles, separate from the classifier and historical oracles."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/resource-timeline"
REVIEW = json.loads(
    (ROOT / "docs/reports/MANA-TRANSACTION-01-T02-S01-D02-R1-results.json").read_text()
)
SOURCE = (
    (FIXTURE / "src/main/java/fixture/Resources.java")
    .read_text()
    .replace("public void sequence()", "@Transactional public void sequence()")
)
OVERRIDE = """class CustomJdbc extends JdbcTemplate {
    @Override public void execute(String sql) {
        throw new IllegalStateException("custom override");
    }
}"""
# Fixed source/dispatch expectations, not inferred from engine output.
NEGATIVES = {
    "original": (
        REVIEW["counterexample"]["source"],
        "RESOURCE_LEAF_SOURCE_DISPATCH_INCOMPLETE",
    ),
    "top_level": (SOURCE + "\n" + OVERRIDE, "RESOURCE_LEAF_APPLICATION_SUBTYPE"),
    "static_member": (
        SOURCE + "\n@Configuration class CustomConfig { static " + OVERRIDE + " }",
        "RESOURCE_LEAF_SOURCE_DISPATCH_INCOMPLETE",
    ),
    "inner_member": (
        SOURCE + "\n@Configuration class CustomConfig { " + OVERRIDE + " }",
        "RESOURCE_LEAF_SOURCE_DISPATCH_INCOMPLETE",
    ),
    "concrete_bean": (
        SOURCE + "\n" + OVERRIDE + "\n@Configuration class CustomConfig { "
        "@Bean public CustomJdbc customJdbc() { return new CustomJdbc(); } }",
        "RESOURCE_LEAF_APPLICATION_SUBTYPE",
    ),
    "unknown_bean": (
        SOURCE + "\n@Configuration class CustomConfig { "
        "@Bean public Object opaqueBean() { return externalFactory.create(); } }",
        "RESOURCE_LEAF_UNRESOLVED_BEAN_IMPLEMENTATION",
    ),
    "proxy_factory": (
        SOURCE + "\n@Configuration class CustomConfig { "
        "@Bean public JdbcTemplate proxy() { return externalProxy.create(); } }",
        "RESOURCE_LEAF_UNRESOLVED_IMPLEMENTATION_FACTORY",
    ),
    "decorator": (
        SOURCE + "\nclass Decorator extends external.JdbcDecorator {}",
        "RESOURCE_LEAF_UNRESOLVED_SOURCE_SUPERTYPE",
    ),
    "virtual_hook": (
        SOURCE + "\nclass HookJdbc extends JdbcTemplate { "
        "@Override public javax.sql.DataSource getDataSource() { "
        'throw new IllegalStateException("application hook"); } }',
        "RESOURCE_LEAF_APPLICATION_SUBTYPE",
    ),
    "local_class": (
        SOURCE
        + "\nclass Provider { public Object create() { "
        + OVERRIDE
        + " return new CustomJdbc(); } }",
        "RESOURCE_LEAF_SOURCE_DISPATCH_INCOMPLETE",
    ),
    "anonymous_class": (
        SOURCE + "\nclass Provider { Object jdbc = new JdbcTemplate() { "
        "@Override public void execute(String sql) {} }; }",
        "RESOURCE_LEAF_SOURCE_DISPATCH_INCOMPLETE",
    ),
    "initializer": (
        SOURCE + "\nclass Provider { static { externalRegistry.configure(); } }",
        "RESOURCE_LEAF_SOURCE_DISPATCH_INCOMPLETE",
    ),
    "nested_nested": (
        SOURCE + "\nclass Outer { static class Middle { static " + OVERRIDE + " } }",
        "RESOURCE_LEAF_SOURCE_DISPATCH_INCOMPLETE",
    ),
    "imported_config": (
        SOURCE
        + "\n@Configuration @org.springframework.context.annotation.Import(ExternalConfig.class) "
        "class ImportedConfig {}",
        "RESOURCE_LEAF_UNRESOLVED_WIRING_ANNOTATION",
    ),
    "composed_provider": (
        SOURCE + "\n@Configuration class CustomConfig { "
        "@CustomBean public Object jdbcProvider() { return externalFactory.create(); } }",
        "RESOURCE_LEAF_UNRESOLVED_WIRING_ANNOTATION",
    ),
    "source_advisor": (
        SOURCE + "\n@org.aspectj.lang.annotation.Aspect class CustomAdvisor {}",
        "RESOURCE_LEAF_UNRESOLVED_WIRING_ANNOTATION",
    ),
}


def snapshot(project):
    return {
        str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in project.rglob("*")
        if p.is_file()
    }


class DispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.stage = Path(cls.tmp.name).resolve()
        spec = importlib.util.spec_from_file_location(
            "dispatch_cli", ROOT / "scripts/mana-resource-timeline.py"
        )
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)
        cls.reports, cls.projects = {}, {}
        sources = {name: text for name, (text, _) in NEGATIVES.items()}
        sources.update(
            standard=SOURCE,
            three=SOURCE.replace(
                'jdbc.update("DELETE FROM ledger"); }',
                'jdbc.update("DELETE FROM ledger"); '
                'jdbc.update("INSERT INTO audit (id) VALUES (1)"); }',
            ),
            overload=SOURCE.replace(
                'jdbc.execute("SELECT * FROM accounts")',
                'jdbc.execute("SELECT * FROM accounts", callback)',
            ),
        )
        for name, text in sources.items():
            # F02 positive controls use an exact allocation. NEGATIVES retain
            # their historical sources, including the byte-identical R1 HIGH.
            if name in {"standard", "three"}:
                text = text.replace(
                    "@Autowired JdbcTemplate jdbc;",
                    "private final JdbcTemplate jdbc = new JdbcTemplate();",
                )
            project = cls.stage / name
            shutil.copytree(FIXTURE, project)
            (project / "src/main/java/fixture/Resources.java").write_text(text)
            context = json.loads((project / "context.json").read_text())
            context["resourceLeafPolicy"] = "JDBC_LITERAL_V1"
            (project / "context.json").write_text(json.dumps(context))
            before = snapshot(project)
            cls.reports[name] = cls.cli.analyze(
                project, project / "context.json", "fixture.Operations#sequence()"
            )
            if before != snapshot(project):
                raise AssertionError("analysis modified source project")
            cls.projects[name] = project

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def leaves(self, report):
        return [
            e
            for e in report["transactionModel"]["events"]
            if e["kind"] == "RESOURCE_LEAF_CALL"
        ]

    def negative(self, name):
        report = self.reports[name]
        self.cli.t01.validate_model(report["transactionModel"])
        self.cli.validate_timeline(report)
        self.assertEqual(self.leaves(report), [])
        tx = report["transactionModel"]
        self.assertEqual(tx["frames"][0]["continuation"], "UNKNOWN")
        self.assertEqual(
            [e["kind"] for e in tx["events"] if e["kind"].endswith("CALL")],
            ["UNRESOLVED_CALL"],
        )
        self.assertEqual(
            [o["placement"]["status"] for o in report["observations"]],
            ["T01_FRONTIER", "UNPLACED"],
        )
        self.assertEqual(
            [o["transactionContext"]["physicalId"] for o in report["observations"]],
            ["P1", None],
        )
        if name in NEGATIVES:
            self.assertIn(
                NEGATIVES[name][1], [u["reason"] for u in tx["uncertainties"]]
            )

    def reject_both(self, report, message):
        # T02 must reject through the authoritative semantic policy too, before
        # a mismatched resource projection could hide a permissive T01 validator.
        with self.assertRaisesRegex(ValueError, message):
            self.cli.t01.validate_model(report["transactionModel"])
        with self.assertRaisesRegex(ValueError, message):
            self.cli.validate_timeline(report)

    def test_original_d02_r1_a_exact_source(self):
        raw = (
            self.projects["original"] / REVIEW["counterexample"]["sourcePath"]
        ).read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(), REVIEW["counterexample"]["sourceSha256"]
        )
        self.negative("original")

    def test_top_level_override(self):
        self.negative("top_level")

    def test_static_member_override(self):
        self.negative("static_member")

    def test_nonstatic_member_override(self):
        self.negative("inner_member")

    def test_declared_jdbc_with_application_concrete_bean(self):
        self.negative("concrete_bean")
        classes = self.reports["concrete_bean"]["sourceFacts"]["classes"]
        operations = next(c for c in classes if c["simpleName"] == "Operations")
        self.assertEqual(
            next(f for f in operations["fields"] if f["name"] == "jdbc")["type"],
            "org.springframework.jdbc.core.JdbcTemplate",
        )

    def test_bean_implementation_unresolved(self):
        self.negative("unknown_bean")

    def test_unresolved_wiring_annotations_cannot_hide_providers(self):
        for name in ["imported_config", "composed_provider", "source_advisor"]:
            with self.subTest(name=name):
                self.negative(name)

    def test_proxy_and_factory_unresolved(self):
        self.negative("proxy_factory")

    def test_decorator_and_indirect_supertype_unresolved(self):
        self.negative("decorator")

    def test_library_virtual_application_hook_without_callback_argument(self):
        # execute(String) is inherited, yet may dispatch getDataSource() to app code.
        self.negative("virtual_hook")

    def test_local_anonymous_and_deeply_nested_types(self):
        for name in ["local_class", "anonymous_class", "nested_nested", "initializer"]:
            with self.subTest(name=name):
                self.negative(name)

    def test_uncatalogued_overload(self):
        self.negative("overload")

    def test_standard_target_and_two_required_operations(self):
        report = self.reports["standard"]
        first, second = self.leaves(report)
        self.assertEqual([e["method"] for e in [first, second]], ["execute", "update"])
        self.assertEqual(
            first["witness"]["signature"],
            "org.springframework.jdbc.core.JdbcTemplate#execute(java.lang.String):void",
        )
        self.assertEqual(
            second["witness"]["signature"],
            "org.springframework.jdbc.core.JdbcTemplate#update(java.lang.String):int",
        )
        self.assertEqual(
            [e["witness"]["transactionContext"]["physicalId"] for e in [first, second]],
            ["P1", "P1"],
        )
        self.assertEqual(second["witness"]["normalReturnDependencies"], [4])
        self.assertEqual(first["witness"]["normalReturnDependencies"], [])

    def test_three_required_operations(self):
        leaves = self.leaves(self.reports["three"])
        self.assertEqual([e["sequence"] for e in leaves], [4, 5, 6])
        self.assertEqual(
            [e["witness"]["transactionContext"]["physicalId"] for e in leaves],
            ["P1", "P1", "P1"],
        )
        self.assertEqual(
            [e["witness"]["normalReturnDependencies"] for e in leaves],
            [[], [4], [4, 5]],
        )

    def test_override_has_no_false_continuation(self):
        self.negative("original")
        self.assertEqual(
            self.reports["original"]["observations"][1]["transactionContext"],
            {"kind": "UNKNOWN", "physicalId": None, "manager": None},
        )

    def test_forged_standard_witness_rejected_on_authentic_negative_facts(self):
        for name in NEGATIVES:
            with self.subTest(name=name):
                forged = copy.deepcopy(self.reports["standard"])
                new_facts = copy.deepcopy(self.reports[name]["sourceFacts"])
                new_hash = next(c["evidence"]["sha256"] for c in new_facts["classes"])

                def rehash(value):
                    if isinstance(value, dict):
                        if "sha256" in value:
                            value["sha256"] = new_hash
                        for child in value.values():
                            rehash(child)
                    elif isinstance(value, list):
                        for child in value:
                            rehash(child)

                rehash(forged)
                forged["sourceFacts"] = new_facts
                forged["transactionModel"]["resourceLeafExtension"]["sourceFacts"] = (
                    copy.deepcopy(new_facts)
                )
                self.reject_both(forged, "resource leaf dispatch not demonstrated")

    def test_witness_missing_altered_incompatible_and_unjustified_certainty(self):
        for mutation in ["missing", "signature", "receiver", "premises", "certainty"]:
            with self.subTest(mutation=mutation):
                report = copy.deepcopy(self.reports["standard"])
                leaf = self.leaves(report)[0]
                if mutation == "missing":
                    del leaf["witness"]
                elif mutation == "signature":
                    leaf["witness"]["signature"] = (
                        "app.Arbitrary#execute(java.lang.String):void"
                    )
                elif mutation == "receiver":
                    leaf["witness"]["receiverType"] = "app.Arbitrary"
                elif mutation == "premises":
                    leaf["witness"]["premises"] = [
                        "Actual dynamic target is proven standard."
                    ]
                else:
                    leaf["witness"]["certainty"] = "PROVEN"
                self.reject_both(report, "resource leaf (event requires|witness fails)")

    def test_arbitrary_application_call_cannot_be_laundered_by_witness(self):
        report = copy.deepcopy(self.reports["standard"])
        for facts in [
            report["sourceFacts"],
            report["transactionModel"]["resourceLeafExtension"]["sourceFacts"],
        ]:
            cls = next(c for c in facts["classes"] if c["simpleName"] == "Operations")
            next(f for f in cls["fields"] if f["name"] == "jdbc")["type"] = (
                "app.Arbitrary"
            )
        self.reject_both(report, "reparsed source bytes")

    def test_older_incomplete_dispatch_facts_cannot_certify_new_leaf(self):
        report = copy.deepcopy(self.reports["standard"])
        for facts in [
            report["sourceFacts"],
            report["transactionModel"]["resourceLeafExtension"]["sourceFacts"],
        ]:
            for cls in facts["classes"]:
                del cls["dispatchHazards"]
        self.reject_both(report, "resource leaf dispatch not demonstrated")

    def test_historical_bad_witness_rejected_by_both_validators(self):
        self.reject_both(
            copy.deepcopy(REVIEW["counterexample"]["fullReport"]),
            "resource leaf dispatch not demonstrated",
        )

    def test_provenance_and_resolved_signature_cannot_be_changed(self):
        for mutation in ["hash", "site", "signature"]:
            with self.subTest(mutation=mutation):
                report = copy.deepcopy(self.reports["standard"])
                leaf = self.leaves(report)[0]
                if mutation == "hash":
                    report["transactionModel"]["resourceLeafExtension"]["sourceFacts"][
                        "classes"
                    ][0]["evidence"]["sha256"] = "0" * 64
                elif mutation == "site":
                    leaf["callSite"]["start"] += 1
                else:
                    leaf["witness"]["signature"] = (
                        "JdbcTemplate#execute(java.lang.Object):void"
                    )
                self.reject_both(report, "resource leaf")

    def test_enlistment_lock_and_runtime_identity_always_unknown(self):
        for report in self.reports.values():
            for op in report["observations"]:
                self.assertEqual(op["datasource"], {"status": "UNKNOWN", "id": None})
                self.assertEqual(op["enlistment"], "UNKNOWN")
                self.assertEqual(op["lockAcquired"], "UNKNOWN")
                self.assertEqual(op["resource"]["runtimeIdentity"], "UNKNOWN")
                self.assertEqual(op["resource"]["lockGranularity"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
