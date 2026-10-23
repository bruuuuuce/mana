#!/usr/bin/env python3
"""Independent D00 A-J oracles and adversarial S02 controls, local scope only."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/wait-dependencies"
sys.path.insert(0, str(FIXTURE))
import scenarios  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "s01", ROOT / "scripts/mana-resource-timeline.py"
)
s01 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s01)
spec = importlib.util.spec_from_file_location(
    "s02", ROOT / "scripts/mana-wait-dependencies.py"
)
s02 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s02)
from skill_factory.transactions import wait_dependencies as wd  # noqa: E402
from skill_factory.transactions.wait_validation import validate_report  # noqa: E402


def snapshot(root):
    return {
        str(p.relative_to(root)): (
            hashlib.sha256(p.read_bytes()).hexdigest(),
            p.stat().st_mode,
        )
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


class WaitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = snapshot(FIXTURE)
        cls.tmp = tempfile.TemporaryDirectory(prefix="mana-s02-tests-")
        cls.stage = Path(cls.tmp.name).resolve()
        cls.oracles = json.loads((FIXTURE / "oracles.json").read_text())["cases"]
        project = FIXTURE
        files = s01.t01.factory.project_files(
            project, s01.t01.factory.adapter_for("transaction-analysis")
        )
        cls.facts = s01.t01.java_facts(s01.t01.factory, project, files)
        context = json.loads((FIXTURE / "context.json").read_text())
        cls.models = {}
        for name in (
            "xy",
            "yx",
            "outer",
            "required",
            "nested",
            "frontier",
            "unordered",
            "read",
            "request",
            "asyncCaller",
            "unknownSql",
            "outer_unknown",
            "repeated",
        ):
            ctx = copy.deepcopy(context)
            if name == "outer_unknown":
                ctx["managerCapabilities"]["tx"]["suspend"] = None
            facts = copy.deepcopy(cls.facts)
            tx = s01.t01.build(
                facts, ctx, "fixture.Paths#" + name.replace("_unknown", "") + "()"
            )
            tx["evidence"] = [
                {"path": k, "sha256": hashlib.sha256(v).hexdigest()}
                for k, v in files.items()
            ]
            report = s01.build_timeline(tx, facts)
            s01.validate_timeline(report)
            cls.models[name] = (json.dumps(report, indent=2) + "\n").encode()
        # A dedicated synthetic ASPECTJ/final variant materializes the F02
        # common ACTIVE/null identity. Historical source/fixtures stay untouched.
        variant = cls.stage / "f02"
        shutil.copytree(FIXTURE, variant)
        path = variant / "src/main/java/fixture/Waits.java"
        path.write_text(
            path.read_text()
            .replace(
                "@EnableTransactionManagement(proxyTargetClass = true)",
                "@EnableTransactionManagement(mode = org.springframework.context.annotation.AdviceMode.ASPECTJ)",
            )
            .replace("public void fresh()", "public final void fresh()")
        )
        variant_files = s01.t01.factory.project_files(
            variant, s01.t01.factory.adapter_for("transaction-analysis")
        )
        facts = s01.t01.java_facts(s01.t01.factory, variant, variant_files)
        tx = s01.t01.build(
            facts,
            {**context, "aspectjWeaving": "ASSUMED_APPLIED"},
            "fixture.Paths#outer()",
        )
        tx["evidence"] = [
            {"path": k, "sha256": hashlib.sha256(v).hexdigest()}
            for k, v in variant_files.items()
        ]
        report = s01.build_timeline(tx, facts)
        s01.validate_timeline(report)
        cls.models["outer_f02"] = (json.dumps(report, indent=2) + "\n").encode()
        cls.results = {}

    @classmethod
    def tearDownClass(cls):
        if snapshot(FIXTURE) != cls.before:
            raise AssertionError("S02 synthetic fixture was modified")
        cls.tmp.cleanup()

    def case(self, name="O-A01"):
        return scenarios.materialize(name, self.models)

    def report(self, name="O-A01"):
        raw, sidecar = self.case(name)
        result = wd.build_report(raw, sidecar)
        validate_report(result, raw)
        return result

    def test_01_all_static_manual_oracles(self):
        for oracle in self.oracles:
            oid = oracle["id"]
            with self.subTest(oracle=oid):
                if oracle["result"] == "DEFERRED_RUNTIME_ADAPTER":
                    self.results[oid] = {
                        "status": "DEFERRED",
                        "reason": "Runtime ingestion/correlation outside I01; D00 R1-R7 unchanged.",
                    }
                    continue
                raw, sidecar = self.case(oid)
                original = copy.deepcopy(sidecar)
                hashes = {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()}
                if oracle["result"] == "REJECTED_INPUT":
                    with self.assertRaises(wd.RejectedInput):
                        wd.build_report(raw, sidecar)
                    self.results[oid] = {"status": "PASS", "result": "REJECTED_INPUT"}
                    continue
                report = wd.build_report(raw, sidecar)
                self.assertEqual(
                    len(report["databaseGraph"]["edges"]), oracle["dbEdges"]
                )
                self.assertEqual(
                    len(report["applicationGraph"]["edges"]), oracle["appEdges"]
                )
                self.assertEqual(report["assessment"]["result"], oracle["result"])
                validate_report(report, raw)
                self.assertEqual(sidecar, original)
                self.assertEqual(
                    hashes, {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()}
                )
                self.results[oid] = {
                    "status": "PASS",
                    "dbEdges": oracle["dbEdges"],
                    "appEdges": oracle["appEdges"],
                    "result": oracle["result"],
                }
        self.assertEqual(len(self.results), 35)
        self.assertEqual(sum(r["status"] == "PASS" for r in self.results.values()), 31)

    def test_02_A_literal_directions_namespaces_and_future_end(self):
        report = self.report()
        claims = [c for c in report["claims"] if c["category"] == "DB_WAIT_DEPENDENCY"]
        self.assertEqual(
            {
                (
                    c["waiter"]["participantId"],
                    c["blocker"]["participantId"],
                    c["resource"],
                )
                for c in claims
            },
            {("a", "b", "Y"), ("b", "a", "X")},
        )
        self.assertTrue(
            all(
                c["waiter"]["originalPhysicalId"]
                == c["blocker"]["originalPhysicalId"]
                == "P1"
                for c in claims
            )
        )
        self.assertEqual(len(report["databaseGraph"]["nodes"]), 2)
        for c in claims:
            self.assertEqual(
                [w["id"] for w in c["obligations"]], ["W" + str(i) for i in range(1, 9)]
            )
        # END appears in the normal suffix and cannot erase pending-cut edges.
        for op in report["operations"]:
            self.assertTrue(
                any(
                    e["kind"] == "PHYSICAL_END_OUTCOME_UNKNOWN"
                    and e["sequence"] > op["t01Sequence"]
                    for e in op["lifetime"]["events"]
                )
            )
        self.assertEqual(report["coverage"]["globalRiskAbsence"], "NOT_ASSERTED")

    def test_03_C_separate_graphs_and_suspended_holder(self):
        report = self.report("O-C01")
        c = next(c for c in report["claims"] if c["category"] == "DB_WAIT_DEPENDENCY")
        self.assertEqual(
            (c["waiter"]["originalPhysicalId"], c["blocker"]["originalPhysicalId"]),
            ("P2", "P1"),
        )
        app = next(
            c
            for c in report["claims"]
            if c["category"] == "APPLICATION_WAIT_DEPENDENCY"
        )
        self.assertEqual(
            (app["caller"]["originalFrameId"], app["callee"]["originalFrameId"]),
            ("F1", "F2"),
        )
        self.assertEqual(app["resource"]["database"], "NOT_APPLICABLE")
        self.assertEqual(
            {x["type"] for x in report["crossLayerRelations"]},
            {"EXECUTES_IN", "SUSPENDS_FOR", "RESUME_REQUIRES_COMPLETION"},
        )
        self.assertEqual(
            [
                o["suspension"]["records"][0]["replacementPhysicalId"]
                for o in report["operations"]
                if o["suspension"]["records"]
            ],
            ["P2"],
        )

    def test_04_B_never_unions_cuts_into_feasible_cycle(self):
        report = self.report("O-B02")
        self.assertEqual(report["assessment"]["result"], "CYCLE_FEASIBILITY_UNKNOWN")
        self.assertEqual(
            {e["cut"] for e in report["databaseGraph"]["edges"]}, {"s1", "s2"}
        )
        self.assertTrue(
            all(
                c["result"] == "NO_CYCLE_IN_MODELED_SCENARIO"
                for c in report["assessment"]["cuts"]
            )
        )
        rejected = self.report("O-B03")
        self.assertTrue(rejected["assessment"]["cuts"][0]["contradictions"])

    def test_05_D_E_logical_and_savepoint_end_do_not_end_P(self):
        for case in ("O-D01", "O-E01"):
            report = self.report(case)
            self.assertEqual(len(report["databaseGraph"]["nodes"]), 1)
            self.assertEqual(
                [o["namespace"]["originalPhysicalId"] for o in report["operations"]],
                ["P1", "P1"],
            )
            self.assertEqual(len(report["applicationGraph"]["edges"]), 1)
            self.assertEqual(report["databaseGraph"]["edges"], [])
            self.assertEqual(
                report["operations"][1]["observation"]["enlistment"], "UNKNOWN"
            )

    def test_06_F_partial_identity_and_distinct_instances(self):
        r = self.report("O-F07")
        inner = next(
            c for c in r["claims"] if c["category"] == "APPLICATION_WAIT_DEPENDENCY"
        )
        self.assertIsNone(inner["calleePhysical"]["originalPhysicalId"])
        self.assertEqual(len(r["databaseGraph"]["nodes"]), 1)
        self.assertTrue(
            any(o["namespace"]["originalPhysicalId"] is None for o in r["operations"])
        )
        r = self.report("O-F06")
        self.assertEqual(len(r["inputs"]), 1)
        self.assertEqual(len(r["databaseGraph"]["nodes"]), 2)
        self.assertEqual(
            len({n["namespace"]["inputDigest"] for n in r["databaseGraph"]["nodes"]}), 1
        )

    def test_07_G_prefix_witness_and_async(self):
        r = self.report("O-G02")
        self.assertEqual(
            [o["observation"]["placement"]["status"] for o in r["operations"]],
            ["T01_RESOURCE_LEAF", "T01_FRONTIER", "UNPLACED"],
        )
        self.assertIsNone(r["operations"][-1]["namespace"]["originalPhysicalId"])
        bad = self.report("O-G04")
        self.assertTrue(
            any(
                w["id"] == "W8" and w["state"] == "CONTRADICTED"
                for c in bad["waitCandidates"]
                for w in c["obligations"]
            )
        )
        self.assertFalse(self.report("O-G03")["applicationGraph"]["edges"])

    def test_08_I_request_syntax_is_not_holding(self):
        read = self.report("O-I01")
        request = self.report("O-I02")
        self.assertFalse(
            any(c["category"] == "LOCK_REQUEST_CANDIDATE" for c in read["claims"])
        )
        c = next(
            c for c in request["claims"] if c["category"] == "LOCK_REQUEST_CANDIDATE"
        )
        self.assertEqual(
            (c["origin"], c["certainty"], c["mode"], c["acquisition"]),
            ("EXPLICIT_REQUEST_SYNTAX", "STATIC_SYNTAX", "UNKNOWN", "UNKNOWN"),
        )
        self.assertFalse(request["databaseGraph"]["edges"])

    def test_09_missing_or_contradicted_premises_cannot_qualify(self):
        for state in ("UNKNOWN", "CONTRADICTED"):
            raw, sidecar = self.case()
            for p in sidecar["premises"]:
                if p["id"].endswith("_retain"):
                    p["state"] = state
            r = wd.build_report(raw, sidecar)
            self.assertFalse(r["databaseGraph"]["edges"])
            self.assertTrue(
                all(
                    c["status"] == ("UNKNOWN" if state == "UNKNOWN" else "EXCLUDED")
                    for c in r["waitCandidates"]
                    if c["waiter"][0] != c["holder"][0]
                )
            )
        raw, sidecar = self.case()
        next(p for p in sidecar["premises"] if p["id"] == "a1_retain")["dependsOn"] = [
            "a1_acquire"
        ]
        next(p for p in sidecar["premises"] if p["id"] == "a1_acquire")["state"] = (
            "UNKNOWN"
        )
        self.assertEqual(
            len(wd.build_report(raw, sidecar)["databaseGraph"]["edges"]), 1
        )

    def test_10_false_digests_projections_and_witnesses_rejected(self):
        raw, sidecar = self.case()
        bad = copy.deepcopy(sidecar)
        bad["inputs"][0]["sha256"] = "0" * 64
        with self.assertRaises(wd.RejectedInput):
            wd.build_report(raw, bad)
        for target in ("context", "placement", "witness"):
            corrupted = json.loads(raw["ta"])
            if target == "context":
                corrupted["observations"][0]["transactionContext"]["physicalId"] = "P2"
            elif target == "placement":
                corrupted["observations"][0]["placement"]["beforeT01Sequence"] = 8
            else:
                leaf = next(
                    e
                    for e in corrupted["transactionModel"]["events"]
                    if e["kind"] == "RESOURCE_LEAF_CALL"
                )
                leaf["witness"]["normalReturnDependencies"] = [999]
            bad_raw = {**raw, "ta": json.dumps(corrupted).encode()}
            bad = copy.deepcopy(sidecar)
            bad["inputs"][0]["sha256"] = wd.digest(bad_raw["ta"])
            with self.assertRaises(wd.RejectedInput):
                wd.build_report(bad_raw, bad)

    def test_11_output_validator_adversarial_mutations(self):
        raw, sidecar = self.case()
        report = wd.build_report(raw, sidecar)
        for kind in (
            "observed",
            "property",
            "reverse",
            "self_loop",
            "missing_w",
            "unknown_w",
            "invented_node",
            "promotion",
            "resource",
            "missing_operation",
        ):
            bad = copy.deepcopy(report)
            c = next(c for c in bad["claims"] if c["category"] == "DB_WAIT_DEPENDENCY")
            if kind == "observed":
                c["certainty"] = "OBSERVED"
            elif kind == "property":
                c["propertyCertainty"]["runtimeWait"] = "OBSERVED"
            elif kind == "reverse":
                edge = bad["databaseGraph"]["edges"][0]
                edge["from"], edge["to"] = edge["to"], edge["from"]
            elif kind == "self_loop":
                c["blocker"] = copy.deepcopy(c["waiter"])
            elif kind == "missing_w":
                c["obligations"].pop()
            elif kind == "unknown_w":
                c["obligations"][0]["state"] = "UNKNOWN"
            elif kind == "invented_node":
                bad["databaseGraph"]["nodes"][0]["namespace"]["originalPhysicalId"] = (
                    None
                )
            elif kind == "promotion":
                bad["coverage"]["globalRiskAbsence"] = "PASS"
            elif kind == "resource":
                c["resource"] = "invented"
            elif kind == "missing_operation":
                bad["operations"].pop()
            with (
                self.subTest(mutation=kind),
                self.assertRaises((wd.RejectedInput, KeyError)),
            ):
                validate_report(bad, raw)

    def test_12_scope_overflow_preserves_inventory_and_is_incomplete(self):
        raw, sidecar = self.case()
        sidecar["resources"].append(
            {**copy.deepcopy(sidecar["resources"][0]), "id": "Z"}
        )
        report = wd.build_report(raw, sidecar)
        self.assertEqual(len(report["operations"]), 4)
        self.assertFalse(report["databaseGraph"]["edges"])
        self.assertEqual(report["assessment"]["result"], "UNKNOWN")
        self.assertEqual(report["coverage"]["status"], "INCOMPLETE")
        self.assertTrue(any("exceeds" in r for r in report["coverage"]["reasons"]))

    def test_13_byte_comparison_and_edge_budgets(self):
        raw, sidecar = self.case()
        for key in (
            "t01Bytes",
            "timelineBytes",
            "combinedBytes",
            "sidecarBytes",
            "candidateComparisons",
            "serializedEdges",
        ):
            with (
                self.subTest(budget=key),
                patch.dict(wd.BUDGETS, {key: 1}),
                self.assertRaises(wd.BudgetExceeded),
            ):
                wd.build_report(raw, sidecar)
        with self.assertRaises(wd.RejectedInput):
            wd.parse_json(b'{"x": 1, "x": 2}', 100)
        with self.assertRaises(wd.RejectedInput):
            wd.parse_json(b'{"x": NaN}', 100)
        with self.assertRaises(wd.RejectedInput):
            wd.parse_json(b"[" * 129 + b"]" * 129, 1000)

    def test_14_cli_publication_validation_and_no_overwrite(self):
        raw, sidecar = self.case()
        base = self.stage / "cli"
        base.mkdir()
        args = [sys.executable, str(ROOT / "scripts/mana-wait-dependencies.py")]
        for key, value in raw.items():
            path = base / (key + ".json")
            path.write_bytes(value)
            args += ["--timeline", key + "=" + str(path)]
        scenario = base / "scenario.json"
        scenario.write_text(json.dumps(sidecar))
        args += ["--scenario", str(scenario)]
        output = base / "output"
        run = subprocess.run(
            args + ["--output-dir", str(output)], capture_output=True, text=True
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        before = snapshot(output)
        run = subprocess.run(
            args + ["--validate", str(output / "wait-dependency.json")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(snapshot(output), before)
        run = subprocess.run(
            args + ["--output-dir", str(output)], capture_output=True, text=True
        )
        self.assertEqual(run.returncode, 2)
        self.assertEqual(snapshot(output), before)
        run = subprocess.run(
            args + ["--output-dir", str(ROOT / "build/s02-forbidden")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 2)
        self.assertFalse((ROOT / "build/s02-forbidden").exists())
        scenario.write_bytes(b" " * (wd.BUDGETS["sidecarBytes"] + 1))
        target = base / "not-published"
        run = subprocess.run(
            args + ["--output-dir", str(target)], capture_output=True, text=True
        )
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stderr)["status"], "BUDGET_EXCEEDED")
        self.assertFalse(target.exists())

    def test_15_diagrams_keep_layers_and_cut_witness_separate(self):
        r = self.report("O-C01")
        files = s02.artifacts(r)
        db = files["database-replacement.mmd"].decode()
        self.assertIn("a/P1", db)
        self.assertIn("a/P2", db)
        self.assertEqual(db.count(" -->|"), 1)
        self.assertNotIn("completion CONDITIONAL", db)
        self.assertIn("FRAME_COMPLETION", json.dumps(r))
        self.assertIn("SUSPENDS_FOR", files["cross-layer.mmd"].decode())
        union = s02.artifacts(self.report("O-B02"))
        self.assertIn("database-s1.mmd", union)
        self.assertIn("database-s2.mmd", union)
        self.assertNotIn("database.mmd", union)

    def test_16_legacy_canonical_inputs_read_only(self):
        for path in sorted(
            (ROOT / "docs/examples/transaction-01-t02-s01").glob(
                "*/resource-timeline.json"
            )
        ):
            before = path.read_bytes()
            raw = {"legacy": before}
            sidecar = scenarios.scenario(raw, [("a", "legacy")], "legacy")
            scenarios.clear_lock_scenario(sidecar)
            report = wd.build_report(raw, sidecar)
            validate_report(report, raw)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(report["databaseGraph"]["edges"])

    def test_17_unknown_sql_not_a_target_and_no_hidden_lock(self):
        raw = {"t": self.models["unknownSql"]}
        sidecar = scenarios.clear_lock_scenario(
            scenarios.scenario(raw, [("a", "t")], "unknown_sql")
        )
        report = wd.build_report(raw, sidecar)
        self.assertEqual(
            report["operations"][0]["observation"]["operationType"], "UNKNOWN"
        )
        self.assertIsNone(report["operations"][0]["observation"]["resource"]["name"])
        self.assertFalse(report["databaseGraph"]["edges"])
        self.assertFalse(
            any(c["category"] == "LOCK_REQUEST_CANDIDATE" for c in report["claims"])
        )

    def test_18_repeated_methods_use_distinct_frame_instances(self):
        raw = {"t": self.models["repeated"]}
        sidecar = scenarios.clear_lock_scenario(
            scenarios.scenario(raw, [("a", "t")], "repeated")
        )
        r = wd.build_report(raw, sidecar)
        validate_report(r, raw)
        app = [c for c in r["claims"] if c["category"] == "APPLICATION_WAIT_DEPENDENCY"]
        self.assertEqual(
            [
                (c["caller"]["originalFrameId"], c["callee"]["originalFrameId"])
                for c in app
            ],
            [("F1", "F2"), ("F1", "F3")],
        )
        self.assertNotEqual(app[0]["source"]["callSite"], app[1]["source"]["callSite"])

    def test_19_frontier_prefix_never_repairs_a_continuation(self):
        # Pending at the known frontier is allowed. A suffix cut past it is not.
        raw = {"t": self.models["frontier"]}
        sidecar = scenarios.scenario(raw, [("a", "t")], "frontier_cut")
        # Only inventory is used here: absence of a replacement P cannot invent one.
        scenarios.cut(sidecar, raw, "frontier", ["a2"], ["a1"], "OUTER_REQUIRES_NEW")
        r = wd.build_report(raw, sidecar)
        self.assertEqual(
            r["operations"][1]["observation"]["placement"]["status"], "T01_FRONTIER"
        )
        self.assertIsNone(r["operations"][2]["namespace"]["originalPhysicalId"])
        self.assertFalse(r["databaseGraph"]["edges"])
        sidecar["cuts"][0]["prefixes"]["a"] += 1
        bad = wd.build_report(raw, sidecar)
        self.assertTrue(
            any(
                "UNRESOLVED_CALL" in p
                for p in bad["assessment"]["cuts"][0]["contradictions"]
            )
        )

    def test_20_invalid_sidecar_rule_and_premise_cycles(self):
        raw, sidecar = self.case()
        for name in (
            "cyclic",
            "unknown_ref",
            "runtime_evidence",
            "asymmetric",
            "override",
        ):
            bad = copy.deepcopy(sidecar)
            if name == "cyclic":
                bad["premises"][0]["dependsOn"] = [bad["premises"][0]["id"]]
            elif name == "unknown_ref":
                bad["operations"][0]["binding"]["premise"] = "absent"
            elif name == "runtime_evidence":
                bad["premises"][0]["state"] = "RUNTIME_EVIDENCE"
            elif name == "asymmetric":
                bad["lockRule"]["modes"].append("N")
                bad["lockRule"]["compatibility"].append(
                    {"left": "M", "right": "N", "result": "INCOMPATIBLE"}
                )
            else:
                bad["operations"][0]["physicalId"] = "P9"
            with self.subTest(case=name), self.assertRaises(wd.RejectedInput):
                wd.build_report(raw, bad)
        with self.assertRaises(wd.RejectedInput):
            wd.build_report(raw, [])

    def test_21_actual_byte_thresholds_stop_before_publication(self):
        raw, sidecar = self.case()
        # The authorized byte thresholds are exercised at their actual values;
        # comparison/edge thresholds use injected small budgets in test_13.
        with self.assertRaises(wd.BudgetExceeded):
            wd.build_report(
                {"ta": raw["ta"] + b" " * wd.BUDGETS["timelineBytes"], "tb": raw["tb"]},
                sidecar,
            )
        sidecar["premises"][0]["statement"] = "a" * (wd.BUDGETS["sidecarBytes"] + 1)
        with self.assertRaises(wd.BudgetExceeded):
            wd.build_report(raw, sidecar)

    def test_22_s02_report_byte_budget_is_checked_too(self):
        raw, sidecar = self.case()
        # Fill almost the entire allowed sidecar with a provenance-bearing
        # premise. The report adds operation/claim evidence and must stop.
        sidecar["premises"][0]["statement"] += "a" * (
            wd.BUDGETS["sidecarBytes"] - len(wd.encoded(sidecar)) - 100
        )
        self.assertLess(len(wd.encoded(sidecar)), wd.BUDGETS["sidecarBytes"])
        with self.assertRaisesRegex(wd.BudgetExceeded, "S02 report"):
            wd.build_report(raw, sidecar)


if __name__ == "__main__":
    unittest.main(verbosity=2)
