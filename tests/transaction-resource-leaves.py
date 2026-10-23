#!/usr/bin/env python3
"""Independent D02 source/path oracles, legacy compatibility and forged-witness negatives."""

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
FIXTURE = ROOT / "tests/fixtures/resource-timeline"
ORACLES = json.loads((FIXTURE / "resource-leaf-oracles.json").read_text())
spec = importlib.util.spec_from_file_location(
    "resource_cli", ROOT / "scripts/mana-resource-timeline.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

VARIANTS = """
    @Autowired org.springframework.transaction.support.TransactionTemplate template;
    org.springframework.transaction.support.TransactionCallback callback;
    @Transactional public void three() { jdbc.execute("SELECT * FROM accounts"); jdbc.update("DELETE FROM ledger"); jdbc.update("INSERT INTO audit (id) VALUES (1)"); }
    @Transactional public void followed() { jdbc.update("DELETE FROM accounts"); empty(); jdbc.update("DELETE FROM ledger"); }
    public void empty() {}
    @Transactional public void opaque() { jdbc.update("DELETE FROM accounts"); unknownReceiver.run(); jdbc.update("DELETE FROM ledger"); }
    @Transactional public void programmatic() { jdbc.update("DELETE FROM accounts"); template.execute(callback); jdbc.update("DELETE FROM ledger"); }
    @Transactional public void callbackArgument() { jdbc.execute(callback); jdbc.update("DELETE FROM ledger"); }
    @Transactional public void callbackLambda() { jdbc.execute(con -> { return null; }); jdbc.update("DELETE FROM ledger"); }
    @Transactional public void manual() { jdbc.update("DELETE FROM accounts"); connection.commit(); jdbc.update("DELETE FROM ledger"); }
    @Transactional public void autoCommit() { connection.setAutoCommit(false); jdbc.update("DELETE FROM ledger"); }
    @Transactional public void sqlCommit() { jdbc.execute("COMMIT"); jdbc.update("DELETE FROM ledger"); }
    @Transactional public void uncatalogued() { jdbc.batchUpdate("DELETE FROM accounts"); jdbc.update("DELETE FROM ledger"); }
    @Transactional public void unordered() { if (flag) { jdbc.update("DELETE FROM accounts"); } jdbc.update("DELETE FROM ledger"); }
    @Transactional public void conditionalArgument() { opaqueReceiver.run(flag ? jdbc.update("DELETE FROM accounts") : jdbc.update("DELETE FROM ledger")); }
    @Transactional public void mayThrow() { jdbc.execute("SELECT * FROM missing_table"); jdbc.update("DELETE FROM ledger"); }
    @Transactional public void explicitThis() { this.jdbc.update("DELETE FROM accounts"); }
    @Transactional public void variableSql() { jdbc.update(sqlA); jdbc.update("DELETE FROM ledger"); }
    @Transactional public void emptyRequired() {}
"""


def snapshot(project):
    return {
        str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in project.rglob("*")
        if p.is_file()
    }


class LeafTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.stage = Path(cls.tmp.name).resolve()
        cls.context = json.loads((FIXTURE / "context.json").read_text())
        # F02: explicitly migrate positive path fixtures to a proven allocation.
        # Historical injected-source oracles remain unchanged on disk and are
        # independently rerun as degraded cases in transaction-resource-binding.
        cls.projects = {}
        for name in ["original", "r1", "variants"]:
            project = cls.stage / name
            shutil.copytree(FIXTURE, project)
            source = project / "src/main/java/fixture/Resources.java"
            text = source.read_text().replace(
                "@Autowired JdbcTemplate jdbc;",
                "private final JdbcTemplate jdbc = new JdbcTemplate();",
            )
            if name == "r1":
                text = text.replace(
                    "public void sequence()", "@Transactional public void sequence()"
                )
            elif name == "variants":
                text = text.replace(
                    "class Operations {", "class Operations {" + VARIANTS
                )
                text = text.replace(
                    "class Entry {",
                    "class Entry {\n    public void afterTerminated() { operations.emptyRequired(); operations.write(); }",
                )
            source.write_text(text)
            if name == "variants":
                text = text.replace(
                    "class Operations {",
                    "class Operations {\n    @Transactional public void longSequence() { "
                    + 'jdbc.update("DELETE FROM accounts"); ' * 129
                    + 'jdbc.update("DELETE FROM ledger"); }\n',
                )
                source.write_text(text)
            cls.projects[name] = project
        cls.facts = {}
        cls.snapshots = {}
        for name, project in cls.projects.items():
            cls.snapshots[name] = snapshot(project)
            files = cli.t01.factory.project_files(
                project, cli.t01.factory.adapter_for("transaction-analysis")
            )
            cls.facts[name] = cli.t01.java_facts(
                cli.t01.factory, project, files, source_snapshot=True
            )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def model(
        self,
        entry="fixture.Operations#sequence()",
        fixture="r1",
        context=None,
        facts=None,
    ):
        source_facts = copy.deepcopy(
            facts if facts is not None else self.facts[fixture]
        )
        scenario = (
            {**self.context, "resourceLeafPolicy": "JDBC_LITERAL_V1"}
            if context is None
            else context
        )
        tx = cli.t01.build(source_facts, scenario, entry)
        if "evidence" not in tx:
            tx["evidence"] = [
                {"path": c["evidence"]["file"], "sha256": c["evidence"]["sha256"]}
                for c in source_facts["classes"]
            ]
        cli.t01.validate_model(tx)
        report = cli.build_timeline(tx, source_facts)
        cli.validate_timeline(report)
        return report

    def leaves(self, report):
        return [
            e
            for e in report["transactionModel"]["events"]
            if e["kind"] == "RESOURCE_LEAF_CALL"
        ]

    def test_literal_independent_path_oracles(self):
        for oracle in ORACLES["cases"]:
            with self.subTest(entry=oracle["entry"]):
                report = self.model(oracle["entry"], oracle["fixture"])
                tx, ops, leaves = (
                    report["transactionModel"],
                    report["observations"],
                    self.leaves(report),
                )
                self.assertEqual(
                    [o["transactionContext"]["physicalId"] for o in ops],
                    oracle["physicalIds"],
                )
                self.assertEqual(
                    [o["resource"]["name"] for o in ops], oracle["resources"]
                )
                self.assertEqual(
                    [e["sequence"] for e in leaves], oracle["leafSequences"]
                )
                self.assertEqual(
                    [e["witness"]["normalReturnDependencies"] for e in leaves],
                    oracle["dependencies"],
                )
                self.assertEqual(
                    len(tx["physicalTransactions"]), oracle["physicalCount"]
                )
                self.assertEqual(len(tx["savepoints"]), oracle["savepoints"])
                self.assertEqual(len(tx["suspensions"]), oracle["suspensions"])
                self.assertTrue(
                    all(o["placement"]["status"] == "T01_RESOURCE_LEAF" for o in ops)
                )
                for leaf in leaves:
                    self.assertEqual(
                        leaf["witness"]["signature"],
                        ORACLES["signatures"][leaf["method"]],
                    )

    def test_call_sites_match_migrated_r1_source_and_owner(self):
        report = self.model()
        self.assertEqual(len(report["transactionModel"]["frames"]), 1)
        for leaf, expected in zip(
            self.leaves(report),
            [
                'jdbc.execute("SELECT * FROM accounts")',
                'jdbc.update("DELETE FROM ledger")',
            ],
        ):
            site = leaf["callSite"]
            self.assertEqual(
                (site["start"], site["end"]),
                (2654, 2692) if leaf["method"] == "execute" else (2694, 2727),
            )
            raw = (self.projects["r1"] / site["file"]).read_bytes()
            self.assertEqual(site["sha256"], hashlib.sha256(raw).hexdigest())
            utf16 = raw.decode().encode("utf-16-le")
            self.assertEqual(
                utf16[site["start"] * 2 : site["end"] * 2].decode("utf-16-le"), expected
            )
            self.assertEqual(leaf["frame"], "F1")

    def test_may_throw_only_conditions_suffix_on_normal_return(self):
        report = self.model("fixture.Operations#mayThrow()", "variants")
        first, second = self.leaves(report)
        self.assertEqual(
            second["witness"]["normalReturnDependencies"], [first["sequence"]]
        )
        self.assertIn(
            "Normal synchronous return is assumed only for continuation of this path.",
            first["witness"]["premises"],
        )
        self.assertIn(
            "Exceptional return does not reach this path's suffix; exception handling and outcome are not modeled.",
            first["witness"]["limits"],
        )
        self.assertTrue(
            any(
                "Normal returns required" in p
                for p in report["observations"][1]["premises"]
            )
        )
        self.assertEqual(
            report["transactionModel"]["physicalTransactions"][0]["outcome"], "UNKNOWN"
        )
        self.assertEqual(report["status"], "CONDITIONAL_STATIC_SCENARIO")

    def test_real_unresolved_frontiers_still_cut_the_suffix(self):
        for method in ["opaque", "programmatic", "manual"]:
            with self.subTest(method=method):
                report = self.model(f"fixture.Operations#{method}()", "variants")
                self.assertEqual(len(self.leaves(report)), 1)
                self.assertEqual(
                    report["observations"][-1]["placement"]["status"], "UNPLACED"
                )
                self.assertIsNone(
                    report["observations"][-1]["transactionContext"]["physicalId"]
                )
                self.assertEqual(
                    report["transactionModel"]["frames"][0]["continuation"], "UNKNOWN"
                )
                self.assertEqual(
                    [
                        e["kind"]
                        for e in report["transactionModel"]["events"]
                        if e["kind"].endswith("CALL")
                    ],
                    ["RESOURCE_LEAF_CALL", "UNRESOLVED_CALL"],
                )

    def test_callback_nonliteral_uncatalogued_and_demarcation_are_not_leaves(self):
        for method in [
            "callbackArgument",
            "autoCommit",
            "sqlCommit",
            "uncatalogued",
            "variableSql",
        ]:
            with self.subTest(method=method):
                report = self.model(f"fixture.Operations#{method}()", "variants")
                self.assertFalse(self.leaves(report))
                self.assertTrue(
                    any(
                        e["kind"] == "UNRESOLVED_CALL"
                        for e in report["transactionModel"]["events"]
                    )
                )
                self.assertEqual(
                    report["observations"][-1]["placement"]["status"], "UNPLACED"
                )

    def test_unknown_control_flow_async_and_lambda_bodies_not_traversed(self):
        for method in ["unordered", "callbackLambda", "async"]:
            with self.subTest(method=method):
                report = self.model(f"fixture.Operations#{method}()", "variants")
                self.assertFalse(self.leaves(report))
                self.assertTrue(
                    all(
                        o["placement"]["status"] == "UNPLACED"
                        for o in report["observations"]
                    )
                )

    def test_unknown_context_cannot_acquire_leaf_continuation(self):
        report = self.model(
            context={
                **self.context,
                "resourceLeafPolicy": "JDBC_LITERAL_V1",
                "initialState": "UNKNOWN",
            }
        )
        self.assertFalse(self.leaves(report))
        self.assertTrue(
            all(
                o["transactionContext"]["kind"] == "UNKNOWN"
                for o in report["observations"]
            )
        )

    def test_leaf_budget_preserves_prefix_and_cuts_remaining_suffix(self):
        report = self.model("fixture.Operations#longSequence()", "variants")
        self.assertEqual(len(self.leaves(report)), 128)
        self.assertEqual(
            report["transactionModel"]["frames"][0]["continuation"], "UNKNOWN"
        )
        self.assertIn(
            "RESOURCE_LEAF_BUDGET_EXCEEDED",
            [u["reason"] for u in report["transactionModel"]["uncertainties"]],
        )
        self.assertEqual(report["observations"][-1]["placement"]["status"], "UNPLACED")

    def test_nested_conditional_arguments_cannot_become_a_linear_leaf_path(self):
        report = self.model("fixture.Operations#conditionalArgument()", "variants")
        self.assertFalse(self.leaves(report))
        self.assertEqual(
            report["transactionModel"]["frames"][0]["continuation"], "UNKNOWN"
        )

    def test_observed_override_or_shadow_blocks_standard_dispatch(self):
        for declaration in [
            "class Derived extends JdbcTemplate {}",
            "class JdbcTemplate {}",
        ]:
            with (
                self.subTest(declaration=declaration),
                tempfile.TemporaryDirectory() as tmp,
            ):
                project = Path(tmp).resolve() / "fixture"
                shutil.copytree(self.projects["r1"], project)
                source = project / "src/main/java/fixture/Resources.java"
                source.write_text(source.read_text() + "\n" + declaration)
                files = cli.t01.factory.project_files(
                    project, cli.t01.factory.adapter_for("transaction-analysis")
                )
                facts = cli.t01.java_facts(
                    cli.t01.factory, project, files, source_snapshot=True
                )
                self.assertFalse(self.leaves(self.model(facts=facts)))

    def test_qualified_or_initialized_receiver_and_wrong_type_not_catalogued(self):
        for change in ["qualifier", "initialized", "type"]:
            with self.subTest(change=change):
                facts = copy.deepcopy(self.facts["r1"])
                field = next(
                    f
                    for c in facts["classes"]
                    if c["simpleName"] == "Operations"
                    for f in c["fields"]
                    if f["name"] == "jdbc"
                )
                if change == "qualifier":
                    field["annotations"].append(
                        {
                            "type": "org.springframework.beans.factory.annotation.Qualifier",
                            "args": {},
                        }
                    )
                elif change == "initialized":
                    # F02 requires a direct initialized final field; an absent
                    # allocation is the corresponding negative now.
                    field["initialized"] = False
                else:
                    field["type"] = "opaque.JdbcTemplate"
                self.assertFalse(self.leaves(self.model(facts=facts)))

    def test_explicit_this_receiver_is_supported(self):
        self.assertEqual(
            len(
                self.leaves(self.model("fixture.Operations#explicitThis()", "variants"))
            ),
            1,
        )

    def test_enlistment_datasource_and_acquired_lock_stay_unknown(self):
        for oracle in ORACLES["cases"]:
            report = self.model(oracle["entry"], oracle["fixture"])
            for op in report["observations"]:
                self.assertEqual(op["enlistment"], "UNKNOWN")
                self.assertEqual(op["datasource"], {"status": "UNKNOWN", "id": None})
                self.assertEqual(op["lockAcquired"], "UNKNOWN")
                self.assertEqual(op["resource"]["lockGranularity"], "UNKNOWN")

    def test_after_real_termination_no_p1_is_reused(self):
        report = self.model("fixture.Entry#afterTerminated()", "variants")
        leaf = self.leaves(report)[0]
        self.assertEqual(
            leaf["witness"]["transactionContext"],
            {"kind": "NO_TRANSACTION", "physicalId": None, "manager": None},
        )
        self.assertLess(
            next(
                e["sequence"]
                for e in report["transactionModel"]["events"]
                if e["kind"] == "PHYSICAL_END_OUTCOME_UNKNOWN"
            ),
            leaf["sequence"],
        )

    def test_witness_missing_incompatible_or_forged_is_rejected(self):
        for change in [
            "missing",
            "rule",
            "signature",
            "safe",
            "premises",
            "dependency",
            "context",
            "source",
            "ordinal",
        ]:
            with self.subTest(change=change):
                tx = copy.deepcopy(self.model()["transactionModel"])
                leaf = next(
                    e for e in tx["events"] if e["kind"] == "RESOURCE_LEAF_CALL"
                )
                witness = leaf["witness"]
                if change == "missing":
                    del leaf["witness"]
                elif change == "rule":
                    witness["rule"]["version"] = 999
                elif change == "signature":
                    witness["signature"] = "java.sql.Connection#commit():void"
                elif change == "safe":
                    witness["safe"] = True
                elif change == "premises":
                    witness["premises"] = []
                elif change == "dependency":
                    witness["normalReturnDependencies"] = [999]
                elif change == "context":
                    witness["transactionContext"]["physicalId"] = "P2"
                elif change == "source":
                    witness["bindingEvidence"]["sha256"] = "0" * 64
                elif change == "ordinal":
                    witness["sourceCallOrdinal"] = 3
                with self.assertRaises(ValueError):
                    cli.t01.validate_model(tx)

    def test_reclassification_checks_facts_instead_of_trusting_safe_flag(self):
        tx = copy.deepcopy(self.model()["transactionModel"])
        facts = tx["resourceLeafExtension"]["sourceFacts"]
        call = next(
            m for c in facts["classes"] for m in c["methods"] if m["name"] == "sequence"
        )["calls"][0]
        call["arguments"][0]["kind"] = "IDENTIFIER"
        call["safe"] = True
        with self.assertRaisesRegex(ValueError, "reparsed source bytes"):
            cli.t01.validate_model(tx)

    def test_coordinated_call_span_outside_owner_is_rejected(self):
        tx = self.model()["transactionModel"]
        leaf = next(e for e in tx["events"] if e["kind"] == "RESOURCE_LEAF_CALL")
        call = next(
            m
            for c in tx["resourceLeafExtension"]["sourceFacts"]["classes"]
            for m in c["methods"]
            if m["name"] == "sequence"
        )["calls"][0]
        for site in [call["evidence"], leaf["callSite"], leaf["witness"]["callSite"]]:
            site["start"] = 0
            site["end"] = 10
        with self.assertRaises(ValueError):
            cli.t01.validate_model(tx)

    def test_source_facts_hash_and_t02_snapshot_must_agree(self):
        report = self.model()
        report["transactionModel"]["resourceLeafExtension"]["sourceFacts"]["classes"][
            0
        ]["evidence"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            cli.validate_timeline(report)
        report = self.model()
        report["sourceFacts"]["classes"][0]["simpleName"] = "Forged"
        with self.assertRaises(ValueError):
            cli.validate_timeline(report)

    def test_authoritative_rule_rejects_async_or_unknown_caller_annotations_in_facts(
        self,
    ):
        for ann in [
            "org.springframework.scheduling.annotation.Async",
            "unresolved.CustomAdvisor",
        ]:
            tx = self.model()["transactionModel"]
            method = next(
                m
                for c in tx["resourceLeafExtension"]["sourceFacts"]["classes"]
                for m in c["methods"]
                if m["name"] == "sequence"
            )
            method["annotations"].append({"type": ann, "args": {}})
            with self.subTest(annotation=ann), self.assertRaises(ValueError):
                cli.t01.validate_model(tx)

    def test_event_reorder_removal_and_past_terminal_rejected(self):
        for change in ["reorder", "remove", "terminal"]:
            with self.subTest(change=change):
                tx = copy.deepcopy(self.model()["transactionModel"])
                if change == "reorder":
                    tx["events"][3], tx["events"][4] = tx["events"][4], tx["events"][3]
                elif change == "remove":
                    tx["events"].pop(4)
                else:
                    tx["events"].insert(-1, tx["events"].pop(4))
                for i, event in enumerate(tx["events"], 1):
                    event["sequence"] = i
                with self.assertRaises(ValueError):
                    cli.t01.validate_model(tx)

    def test_reordered_facts_and_witnesses_cannot_override_source_statement_order(self):
        tx = self.model()["transactionModel"]
        method = next(
            m
            for c in tx["resourceLeafExtension"]["sourceFacts"]["classes"]
            for m in c["methods"]
            if m["name"] == "sequence"
        )
        method["calls"].reverse()
        tx["events"][3], tx["events"][4] = tx["events"][4], tx["events"][3]
        for ordinal, event in enumerate(tx["events"][3:5], 1):
            event["sequence"] = ordinal + 3
            event["witness"]["t01Sequence"] = ordinal + 3
            event["witness"]["sourceCallOrdinal"] = ordinal
            event["witness"]["normalReturnDependencies"] = [] if ordinal == 1 else [4]
        with self.assertRaisesRegex(ValueError, "reparsed source bytes"):
            cli.t01.validate_model(tx)

    def test_leaf_after_real_unresolved_call_cannot_restore_order(self):
        tx = copy.deepcopy(
            self.model("fixture.Operations#opaque()", "variants")["transactionModel"]
        )
        leaf = copy.deepcopy(
            next(e for e in tx["events"] if e["kind"] == "RESOURCE_LEAF_CALL")
        )
        method = next(
            m
            for c in tx["resourceLeafExtension"]["sourceFacts"]["classes"]
            for m in c["methods"]
            if m["name"] == "opaque"
        )
        call = method["calls"][2]
        leaf["callSite"] = copy.deepcopy(call["evidence"])
        leaf["witness"]["callSite"] = copy.deepcopy(call["evidence"])
        leaf["witness"]["argumentEvidence"] = copy.deepcopy(
            call["arguments"][0]["evidence"]
        )
        leaf["witness"]["sourceCallOrdinal"] = 3
        leaf["witness"]["t01Sequence"] = 6
        leaf["witness"]["normalReturnDependencies"] = [4]
        tx["events"].insert(5, leaf)
        for i, event in enumerate(tx["events"], 1):
            event["sequence"] = i
        with self.assertRaisesRegex(ValueError, "unresolved execution order"):
            cli.t01.validate_model(tx)

    def test_renderer_rejects_unsupported_event_and_extension_versions(self):
        tx = self.model()["transactionModel"]
        tx["resourceLeafExtension"]["schema"] = "mana.transaction-resource-leaves/v99"
        with self.assertRaises(ValueError):
            cli.t01.render(tx)
        tx = self.model(context=self.context)["transactionModel"]
        tx["events"][3]["kind"] = "FUTURE_OPAQUE_CALL"
        with self.assertRaises(ValueError):
            cli.t01.render(tx)

    def test_context_cannot_inject_project_defined_safe_rules(self):
        raw = json.dumps({**self.context, "safe": True}).encode()
        with self.assertRaises(ValueError):
            cli.t01.context_input(Path("unused"), raw)

    def test_numeric_boolean_rule_version_is_not_a_catalog_version(self):
        tx = self.model()["transactionModel"]
        next(e for e in tx["events"] if e["kind"] == "RESOURCE_LEAF_CALL")["witness"][
            "rule"
        ]["version"] = True
        with self.assertRaises(ValueError):
            cli.t01.validate_model(tx)

    def test_post_terminal_leaf_rejected_even_with_matching_event_sequence(self):
        tx = copy.deepcopy(self.model()["transactionModel"])
        leaf = tx["events"].pop(4)
        tx["events"].insert(-1, leaf)
        for index, event in enumerate(tx["events"], 1):
            event["sequence"] = index
        leaf["witness"]["t01Sequence"] = leaf["sequence"]
        with self.assertRaisesRegex(ValueError, "active lifetime"):
            cli.t01.validate_model(tx)

    def test_leaf_on_suspended_p1_cannot_replace_current_p2(self):
        tx = self.model("fixture.Entry#independent()", "original")["transactionModel"]
        leaf = next(e for e in tx["events"] if e["kind"] == "RESOURCE_LEAF_CALL")
        leaf["witness"]["transactionContext"]["physicalId"] = "P1"
        with self.assertRaises(ValueError):
            cli.t01.validate_model(tx)

    def test_legacy_ir_remains_identical_and_valid(self):
        r1 = json.loads(
            (
                ROOT / "docs/reports/MANA-TRANSACTION-01-T02-S01-R1-results.json"
            ).read_text()
        )["counterexampleFullReport"]
        before = copy.deepcopy(r1)
        cli.validate_timeline(r1)
        self.assertEqual(r1, before)
        legacy = self.model(context=self.context)
        self.assertNotIn("resourceLeafExtension", legacy["transactionModel"])
        self.assertEqual(legacy["observations"][1]["placement"]["status"], "UNPLACED")

    def test_unsupported_capability_version_or_implicit_activation_rejected(self):
        for change in ["version", "policy", "extension"]:
            tx = copy.deepcopy(self.model()["transactionModel"])
            if change == "version":
                tx["resourceLeafExtension"]["schema"] = (
                    "mana.transaction-resource-leaves/v99"
                )
            elif change == "policy":
                del tx["context"]["resourceLeafPolicy"]
            else:
                del tx["resourceLeafExtension"]
            with self.subTest(change=change), self.assertRaises(ValueError):
                cli.t01.validate_model(tx)

    def test_rendering_does_not_hide_conditional_leaf_or_change_unresolved_meaning(
        self,
    ):
        diagram = cli.t01.render(self.model()["transactionModel"])
        self.assertIn("RESOURCE_LEAF_CALL", diagram)
        self.assertIn("IF normal return", diagram)
        self.assertIn("runtime execution UNKNOWN", diagram)
        diagram = cli.t01.render(
            self.model("fixture.Operations#opaque()", "variants")["transactionModel"]
        )
        self.assertIn("remaining order NOT ASSERTED", diagram)

    def test_real_cli_opt_in_and_source_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp).resolve() / "context.json"
            context.write_text(
                json.dumps({**self.context, "resourceLeafPolicy": "JDBC_LITERAL_V1"})
            )
            output = Path(tmp).resolve() / "out"
            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/mana-resource-timeline.py"),
                    "--project-root",
                    str(self.projects["r1"]),
                    "--context",
                    str(context),
                    "--entry",
                    "fixture.Operations#sequence()",
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((output / "resource-timeline.json").read_text())
            cli.validate_timeline(report)
            self.assertEqual(
                [o["transactionContext"]["physicalId"] for o in report["observations"]],
                ["P1", "P1"],
            )
        for name, project in self.projects.items():
            self.assertEqual(snapshot(project), self.snapshots[name])


if __name__ == "__main__":
    unittest.main()
