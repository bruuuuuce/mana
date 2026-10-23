#!/usr/bin/env python3
"""Independent literal resource/causal oracles and adversarial T01 integration checks."""

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
spec = importlib.util.spec_from_file_location(
    "resource_cli", ROOT / "scripts/mana-resource-timeline.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
from skill_factory.transactions.resources import sql_operation  # noqa: E402


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


class ResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = json.loads((FIXTURE / "context.json").read_text())
        cls.files = cli.t01.factory.project_files(
            FIXTURE, cli.t01.factory.adapter_for("transaction-analysis")
        )
        cls.facts = cli.t01.java_facts(
            cli.t01.factory, FIXTURE, cls.files, source_snapshot=True
        )

    def model(self, entry="fixture.Entry#required()", context=None, facts=None):
        facts = copy.deepcopy(facts or self.facts)
        transaction = cli.t01.build(facts, context or self.context, entry)
        transaction["evidence"] = [
            {"path": p, "sha256": hashlib.sha256(b).hexdigest()}
            for p, b in self.files.items()
        ]
        report = cli.build_timeline(transaction, facts)
        cli.validate_timeline(report)
        return report

    def test_independent_fixture_oracles(self):
        oracles = json.loads((FIXTURE / "oracles.json").read_text())["cases"]
        for oracle in oracles:
            with self.subTest(entry=oracle["entry"]):
                context = copy.deepcopy(self.context)
                context["initialState"] = oracle.get("initialState", "NO_TRANSACTION")
                report = self.model(oracle["entry"], context)
                self.assertEqual(len(report["observations"]), 1)
                op = report["observations"][0]
                self.assertEqual(
                    op["transactionContext"]["physicalId"], oracle["physicalId"]
                )
                self.assertEqual(op["transactionContext"]["manager"], oracle["manager"])
                self.assertEqual(op["operationType"], oracle["type"])
                self.assertEqual(op["resource"]["name"], oracle["resource"])
                self.assertEqual(op["placement"]["status"], oracle["placement"])
                tx = report["transactionModel"]
                self.assertEqual(
                    len(tx["physicalTransactions"]), oracle["physicalCount"]
                )
                self.assertEqual(len(tx["suspensions"]), oracle["suspensions"])
                self.assertEqual(len(tx["savepoints"]), oracle["savepoints"])
                for key in ["lockAcquired", "enlistment"]:
                    self.assertEqual(op[key], "UNKNOWN")
                self.assertEqual(op["datasource"], {"status": "UNKNOWN", "id": None})
                self.assertEqual(op["resource"]["lockGranularity"], "UNKNOWN")

    def test_closed_sql_grammar_literal_positive_and_negative_controls(self):
        cases = [
            ("SELECT * FROM account", "queryForList", "READ", "account"),
            (
                "select * from Account FOR UPDATE",
                "execute",
                "EXPLICIT_LOCK_REQUEST",
                "Account",
            ),
            ("INSERT INTO account (id) VALUES (1)", "update", "WRITE", "account"),
            ("UPDATE account SET id = 1", "execute", "WRITE", "account"),
            ("DELETE FROM account", "update", "WRITE", "account"),
            ("SELECT * FROM account; DELETE FROM ledger", "execute", "UNKNOWN", None),
            ("SELECT * FROM schema.account", "execute", "UNKNOWN", None),
            ("SELECT * FROM account WHERE id = ?", "queryForList", "UNKNOWN", None),
            ("/* SELECT * FROM account */", "execute", "UNKNOWN", None),
            ("SELECT * FROM account", "update", "UNKNOWN", None),
            ("DELETE FROM account", "queryForList", "UNKNOWN", None),
            (None, "execute", "UNKNOWN", None),
        ]
        for sql, api, kind, resource in cases:
            with self.subTest(sql=sql, api=api):
                self.assertEqual(sql_operation(sql, api), (kind, resource))

    def test_source_positions_match_actual_invocation_and_literal(self):
        report = self.model()
        op = report["observations"][0]
        source = (FIXTURE / op["callSite"]["file"]).read_text()
        # JDK positions are UTF-16 code units, including for non-ASCII sources.
        raw = source.encode("utf-16-le")
        for evidence in op["evidence"]:
            self.assertEqual(
                evidence["sha256"],
                hashlib.sha256((FIXTURE / evidence["file"]).read_bytes()).hexdigest(),
            )
        site = op["callSite"]
        self.assertEqual(
            raw[site["start"] * 2 : site["end"] * 2].decode("utf-16-le"),
            'jdbc.update("UPDATE accounts SET balance = 1")',
        )
        self.assertIn(
            'jdbc.update("UPDATE accounts SET balance = 1")',
            source.splitlines()[site["line"] - 1],
        )

    def test_resource_annotation_does_not_override_unknown_context(self):
        report = self.model(
            "fixture.Operations#required()", {**self.context, "initialState": "UNKNOWN"}
        )
        self.assertEqual(report["observations"][0]["placement"]["status"], "UNPLACED")
        self.assertIsNone(report["observations"][0]["transactionContext"]["physicalId"])

    def test_unplaced_observation_cannot_be_inserted_in_timeline(self):
        report = self.model("fixture.Entry#async()")
        report["timeline"].insert(
            1, {"sequence": 2, "kind": "RESOURCE_OPERATION", "observation": "O1"}
        )
        with self.assertRaises(ValueError):
            cli.validate_timeline(report)

    def test_literal_requires_new_timeline(self):
        report = self.model("fixture.Entry#independent()")
        expected = [
            "FRAME_ENTER",
            "PHYSICAL_BEGIN",
            "LOGICAL_BEGIN",
            "FRAME_ENTER",
            "SUSPEND",
            "PHYSICAL_BEGIN",
            "LOGICAL_BEGIN",
            "RESOURCE_OPERATION",
            "UNRESOLVED_CALL",
            "LOGICAL_END",
            "PHYSICAL_END_OUTCOME_UNKNOWN",
            "RESUME_CONDITIONAL",
            "FRAME_EXIT",
            "LOGICAL_END",
            "PHYSICAL_END_OUTCOME_UNKNOWN",
            "FRAME_EXIT",
        ]
        self.assertEqual(
            [e.get("event", e)["kind"] for e in report["timeline"]], expected
        )
        self.assertEqual(
            [
                e["event"]["entity"]
                for e in report["timeline"]
                if e.get("event", {}).get("kind") == "PHYSICAL_END_OUTCOME_UNKNOWN"
            ],
            ["P2", "P1"],
        )
        # P1 begins before suspension and ends only after P2's operation/end/resume.
        tx = report["transactionModel"]
        self.assertEqual(tx["suspensions"][0]["physicalId"], "P1")
        self.assertEqual(tx["suspensions"][0]["replacementPhysicalId"], "P2")

    def test_nested_savepoint_does_not_end_p1(self):
        report = self.model("fixture.Entry#nested()")
        events = report["transactionModel"]["events"]
        self.assertEqual(
            [
                e["entity"]
                for e in events
                if e["kind"] == "PHYSICAL_END_OUTCOME_UNKNOWN"
            ],
            ["P1"],
        )
        self.assertEqual(
            report["transactionModel"]["savepoints"][0]["physicalId"], "P1"
        )
        self.assertEqual(report["observations"][0]["lockAcquired"], "UNKNOWN")

    def test_restore_uses_live_p1_after_p2_ends(self):
        report = self.model("fixture.Entry#afterIndependent()")
        self.assertEqual(
            report["observations"][0]["transactionContext"]["physicalId"], "P1"
        )
        self.assertEqual(
            [p["id"] for p in report["transactionModel"]["physicalTransactions"]],
            ["P1", "P2"],
        )

    def test_ended_transaction_operation_rejected(self):
        report = self.model()
        event = next(e for e in report["timeline"] if e["kind"] == "RESOURCE_OPERATION")
        report["timeline"].remove(event)
        report["timeline"].append(event)
        for i, item in enumerate(report["timeline"], 1):
            item["sequence"] = i
        with self.assertRaises(ValueError):
            cli.validate_timeline(report)

    def test_ended_p2_cannot_receive_restored_p1_operation(self):
        report = self.model("fixture.Entry#afterIndependent()")
        report["observations"][0]["transactionContext"]["physicalId"] = "P2"
        with self.assertRaises(ValueError):
            cli.validate_timeline(report)

    def test_suspended_p1_cannot_receive_p2_operation(self):
        report = self.model("fixture.Entry#independent()")
        report["observations"][0]["transactionContext"]["physicalId"] = "P1"
        with self.assertRaises(ValueError):
            cli.validate_timeline(report)

    def test_no_continuation_after_jdbc_frontier(self):
        report = self.model("fixture.Operations#sequence()")
        self.assertEqual(len(report["observations"]), 2)
        self.assertEqual(report["observations"][0]["resource"]["name"], "accounts")
        self.assertEqual(report["observations"][1]["placement"]["status"], "UNPLACED")
        self.assertEqual(
            report["observations"][1]["transactionContext"]["kind"], "UNKNOWN"
        )
        self.assertEqual(
            sum(e["kind"] == "RESOURCE_OPERATION" for e in report["timeline"]), 1
        )
        self.assertEqual(
            report["transactionModel"]["frames"][0]["continuation"], "UNKNOWN"
        )

    def test_no_continuation_after_unresolved_child(self):
        report = self.model("fixture.Entry#unresolved()")
        self.assertEqual(len(report["observations"]), 1)
        self.assertEqual(report["observations"][0]["operationType"], "UNKNOWN")
        self.assertNotIn(
            "fixture.Operations#write()",
            [f["calleeMethod"] for f in report["transactionModel"]["frames"]],
        )

    def test_dynamic_sql_nested_expression_unknown(self):
        report = self.model("fixture.Operations#dynamic()")
        self.assertTrue(report["observations"])
        self.assertTrue(
            all(o["operationType"] == "UNKNOWN" for o in report["observations"])
        )
        self.assertTrue(
            all(o["resource"]["name"] is None for o in report["observations"])
        )

    def test_manager_ambiguity_does_not_assign_physical_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp).resolve() / "project"
            shutil.copytree(FIXTURE, project)
            path = project / "src/main/java/fixture/Resources.java"
            path.write_text(
                path.read_text().replace(
                    "class Config {",
                    "class Config {\n    @Bean public DataSourceTransactionManager other() { return new DataSourceTransactionManager(); }",
                )
            )
            before = snapshot(project)
            report = cli.analyze(
                project, project / "context.json", "fixture.Operations#required()"
            )
            self.assertEqual(snapshot(project), before)
            op = report["observations"][0]
            self.assertEqual(op["placement"]["status"], "UNPLACED")
            self.assertEqual(
                op["transactionContext"],
                {"kind": "UNKNOWN", "physicalId": None, "manager": None},
            )

    def test_unknown_interception_does_not_traverse_body(self):
        context = copy.deepcopy(self.context)
        context["entryThroughProxy"] = False
        facts = copy.deepcopy(self.facts)
        config = next(c for c in facts["classes"] if c["name"] == "fixture.Config")
        config["annotations"] = [
            a
            for a in config["annotations"]
            if not a["type"].endswith("EnableTransactionManagement")
        ]
        report = self.model("fixture.Operations#required()", context, facts)
        self.assertEqual(report["observations"][0]["placement"]["status"], "UNPLACED")
        self.assertFalse(
            any(e["kind"] == "RESOURCE_OPERATION" for e in report["timeline"])
        )

    def test_comments_are_not_operations(self):
        report = self.model("fixture.Operations#commented()")
        self.assertEqual(len(report["observations"]), 1)
        self.assertEqual(report["observations"][0]["resource"]["name"], "accounts")

    def test_acquired_lock_and_granularity_claims_rejected(self):
        for path, value in [
            ("lockAcquired", True),
            ("enlistment", "PROVEN"),
            ("certainty", "CERTAIN"),
        ]:
            with self.subTest(field=path):
                report = self.model()
                report["observations"][0][path] = value
                with self.assertRaises(ValueError):
                    cli.validate_timeline(report)
        report = self.model()
        report["observations"][0]["resource"]["lockGranularity"] = "ROW"
        with self.assertRaises(ValueError):
            cli.validate_timeline(report)

    def test_source_hash_mismatch_rejected(self):
        report = self.model()
        report["sourceFacts"]["classes"][0]["evidence"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source hash"):
            cli.validate_timeline(report)

    def test_t01_events_must_remain_intact(self):
        report = self.model("fixture.Entry#independent()")
        report["transactionModel"]["events"] = [
            e for e in report["transactionModel"]["events"] if e["kind"] != "SUSPEND"
        ]
        with self.assertRaises(ValueError):
            cli.validate_timeline(report)

    def test_real_pipeline_preserves_target_and_t01_model(self):
        before = snapshot(FIXTURE)
        report = cli.analyze(
            FIXTURE, FIXTURE / "context.json", "fixture.Entry#independent()"
        )
        original = cli.t01.analyze(
            FIXTURE, FIXTURE / "context.json", "fixture.Entry#independent()"
        )
        self.assertEqual(report["transactionModel"], original)
        self.assertEqual(snapshot(FIXTURE), before)
        self.assertEqual(json.loads(json.dumps(report)), report)
        cli.validate_timeline(json.loads(json.dumps(report)))

    def test_cli_external_output_and_overwrite_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "output"
            args = [
                "python3",
                str(ROOT / "scripts/mana-resource-timeline.py"),
                "--project-root",
                str(FIXTURE),
                "--context",
                str(FIXTURE / "context.json"),
                "--entry",
                "fixture.Entry#independent()",
                "--output-dir",
                str(output),
            ]
            first = subprocess.run(args, capture_output=True, text=True, timeout=60)
            self.assertEqual(first.returncode, 0, first.stderr)
            raw = (output / "resource-timeline.json").read_bytes()
            cli.validate_timeline(json.loads(raw))
            second = subprocess.run(args, capture_output=True, text=True, timeout=60)
            self.assertEqual(second.returncode, 2)
            self.assertEqual((output / "resource-timeline.json").read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
