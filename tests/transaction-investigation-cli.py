#!/usr/bin/env python3
"""End-to-end contract checks for the standalone investigation workflow."""

import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/transaction-investigation"
CLI = ROOT / "scripts/mana-investigate-transactions.py"
ORACLES = {item["entry"]: item for item in json.loads((FIXTURE / "expected-outcomes.json").read_text())["cases"]}


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


class InvestigationCliTests(unittest.TestCase):
    def run_cli(self, entry, context=True, extra=()):
        temp = tempfile.TemporaryDirectory(prefix="mana-investigation-test-", dir="/private/tmp")
        self.addCleanup(temp.cleanup)
        output = Path(temp.name) / "output"
        command = [
            "python3", str(CLI), "--project-root", str(FIXTURE),
            "--output-dir", str(output),
        ]
        entries = entry if isinstance(entry, (list, tuple)) else [entry]
        for selected_entry in entries:
            command += ["--entry", selected_entry]
        if context:
            context_path = context if isinstance(context, (str, Path)) else FIXTURE / "context.json"
            command += ["--context", str(context_path)]
        command += list(extra)
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        return completed, output

    def test_conditional_transaction_workflow_and_evidence(self):
        before = tree_digest(FIXTURE)
        completed, output = self.run_cli("investigation.OrderService#process()")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(tree_digest(FIXTURE), before, "target fixture was modified")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "CONDITIONAL_STATIC_SCENARIO")
        self.assertTrue((output / "report.md").is_file())
        self.assertTrue((output / "sequence.puml").is_file())
        model = json.loads((output / "transaction-model.json").read_text())
        timeline = json.loads((output / "resource-timeline.json").read_text())
        self.assertEqual(model["schema"], "mana.transaction-model/v1")
        self.assertEqual(timeline["schema"], "mana.resource-timeline/v1")
        self.assertEqual(model["contextEvidence"]["origin"], "EXPLICIT_SCENARIO_NOT_RUNTIME_PROOF")
        self.assertTrue(model["evidence"])
        expected_process = ORACLES["investigation.OrderService#process()"]
        self.assertEqual(model["frames"][0]["calleeMethod"], expected_process["entry"])
        self.assertEqual(model["frames"][0]["configuration"]["propagation"], "REQUIRED")
        self.assertEqual(len(model["physicalTransactions"]), 1)
        self.assertEqual(timeline["observations"][0]["resource"]["name"], "inventory")
        self.assertIn("UNRESOLVED_CALL", [event["kind"] for event in model["events"]])
        report = (output / "report.md").read_text()
        for section in ["Transaction call tree", "Physical transaction identities", "Conditional concurrency risks", "Evidence and reproduction commands"]:
            self.assertIn(section, report)
        self.assertIn("UNKNOWN", report)
        self.assertIn("--context", report)

    def test_missing_context_is_explicitly_conservative(self):
        completed, output = self.run_cli("investigation.OrderService#process()", context=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        model = json.loads((output / "transaction-model.json").read_text())
        evidence = json.loads((output / "evidence.json").read_text())
        self.assertEqual(evidence["contextOrigin"], "CONSERVATIVE_DEFAULT_NOT_RUNTIME_PROOF")
        self.assertEqual([item["entryThroughProxy"] for item in evidence["proxyEntryAlternatives"]], [False, True])
        self.assertEqual(model["context"]["initialState"], "UNKNOWN")
        self.assertIn("generated conservative input", (output / "report.md").read_text())
        self.assertIn("Default-context proxy entry alternatives", (output / "report.md").read_text())

    def test_unresolved_entry_fails_without_publishing(self):
        completed, output = self.run_cli("investigation.OrderService#missing()")
        self.assertEqual(completed.returncode, ORACLES["investigation.OrderService#missing()"]["expectedExitCode"])
        self.assertFalse(output.exists())

    def test_dynamic_sql_stays_unknown(self):
        completed, output = self.run_cli("investigation.DynamicSqlService#runDynamic()")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        timeline = json.loads((output / "resource-timeline.json").read_text())
        expected = ORACLES["investigation.DynamicSqlService#runDynamic()"]
        self.assertEqual(timeline["observations"][0]["operationType"], expected["expectedOperation"])
        self.assertEqual(timeline["observations"][0]["resource"]["name"], expected["expectedResource"])

    def test_proxy_self_invocation_is_bypassed(self):
        completed, output = self.run_cli("investigation.OrderService#selfInvocation()")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        model = json.loads((output / "transaction-model.json").read_text())
        self_call = next(frame for frame in model["frames"] if frame["calleeMethod"] == "investigation.OrderService#selfRequiresNew()")
        expected = ORACLES["investigation.OrderService#selfInvocation()"]
        self.assertEqual(self_call["interception"]["status"], expected["expectedSelfCall"])
        self.assertEqual(self_call["configuration"]["propagation"], expected["expectedPropagation"][1])

    def test_independent_and_nested_boundaries_keep_distinct_identities(self):
        independent, output = self.run_cli("investigation.OrderService#newBoundary()")
        self.assertEqual(independent.returncode, 0, independent.stderr)
        model = json.loads((output / "transaction-model.json").read_text())
        expected = ORACLES["investigation.OrderService#newBoundary()"]
        self.assertEqual(len(model["physicalTransactions"]), expected["physicalTransactions"])
        self.assertEqual(len(model["suspensions"]), expected["suspensions"])

        nested, output = self.run_cli(
            "investigation.OrderService#nestedBoundary()",
            context=FIXTURE / "context-savepoints.json",
        )
        self.assertEqual(nested.returncode, 0, nested.stderr)
        model = json.loads((output / "transaction-model.json").read_text())
        expected = ORACLES["investigation.OrderService#nestedBoundary()"]
        self.assertEqual(len(model["physicalTransactions"]), expected["physicalTransactions"])
        self.assertEqual(len(model["savepoints"]), expected["savepoints"])
        self.assertEqual(model["savepoints"][0]["physicalId"], "P1")

    def test_default_output_is_private_and_external(self):
        completed = subprocess.run(
            ["python3", str(CLI), "--project-root", str(FIXTURE), "--entry", "investigation.OrderService#process()"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = Path(json.loads(completed.stdout)["outputDir"])
        try:
            self.assertFalse(output.is_relative_to(FIXTURE))
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertTrue((output / "report.md").is_file())
        finally:
            shutil.rmtree(output)

    def test_structured_scenario_reuses_s02_and_vis(self):
        examples = ROOT / "docs/examples/transaction-01-t02-s02/A"
        completed, output = self.run_cli(
            "investigation.OrderService#process()",
            extra=(
                "--wait-scenario", str(examples / "scenario.json"),
                "--wait-timeline", f"ta={examples / 'inputs/ta.json'}",
                "--wait-timeline", f"tb={examples / 'inputs/tb.json'}",
            ),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertIn("waitScenario", result)
        self.assertTrue((output / "wait-wait-dependency.json").is_file())
        self.assertTrue((output / "wait-report.md").is_file())
        self.assertTrue((output / "vis-sequence-a.puml").is_file())
        self.assertIn("Validated S02 scenario result", (output / "report.md").read_text())
        evidence = json.loads((output / "evidence.json").read_text())
        self.assertEqual(evidence["waitScenario"]["scenarioId"], "synthetic_O_A01")
        self.assertEqual(len(evidence["waitScenario"]["timelineInputs"]), 2)

    def test_multiple_entries_keep_models_and_symbolic_ids_separate(self):
        selected = [
            "investigation.OrderService#newBoundary()",
            "investigation.OrderService#nestedBoundary()",
        ]
        completed, output = self.run_cli(selected, context=FIXTURE / "context-savepoints.json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        index = json.loads((output / "entries.json").read_text())
        self.assertEqual(index["schema"], "mana.transaction-investigation-entries/v1")
        self.assertEqual([item["entry"] for item in index["entries"]], selected)
        first = json.loads((output / index["entries"][0]["transactionModel"]).read_text())
        second = json.loads((output / index["entries"][1]["transactionModel"]).read_text())
        self.assertEqual(first["physicalTransactions"][-1]["id"], "P2")
        self.assertEqual(second["physicalTransactions"][0]["id"], "P1")
        self.assertTrue((output / "entry-02.sequence.puml").is_file())
        report = (output / "report.md").read_text()
        self.assertIn("Comparative Java/Spring transaction investigation", report)
        self.assertIn("--entry", report)

    def test_opposite_source_orders_are_comparable_without_deadlock_claim(self):
        completed, output = self.run_cli(
            [
                "investigation.OrderService#accountThenLedger()",
                "investigation.OrderService#ledgerThenAccount()",
            ],
            context=FIXTURE / "context-savepoints.json",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        index = json.loads((output / "entries.json").read_text())
        timelines = [json.loads((output / item["resourceTimeline"]).read_text()) for item in index["entries"]]
        first_resources = [o["resource"]["name"] for o in timelines[0]["observations"] if o["resource"]["name"]]
        second_resources = [o["resource"]["name"] for o in timelines[1]["observations"] if o["resource"]["name"]]
        self.assertEqual(first_resources[:1], ORACLES["investigation.OrderService#accountThenLedger()"]["expectedResourceOrder"][:1])
        self.assertEqual(second_resources[:1], ORACLES["investigation.OrderService#ledgerThenAccount()"]["expectedResourceOrder"][:1])
        report = (output / "report.md").read_text()
        self.assertIn("No wait/deadlock scenario is derived from lexical SQL similarity", report)


if __name__ == "__main__":
    unittest.main()
