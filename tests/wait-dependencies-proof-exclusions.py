#!/usr/bin/env python3
"""F02 manual D00 oracles and adversarial source-proof checks.

The independent oracle below uses source observation positions and transitive
closure, not the engine's inventory, upper-bound builder or cycle detector.
Historical test sources and their expectations remain unmodified.
"""

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "source_fixture", ROOT / "tests/wait-dependencies.py"
)
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
wd, val = f.wd, sys.modules["skill_factory.transactions.wait_validation"]
NEG = "NO_CYCLE_IN_MODELED_SCENARIO"
WITNESSES = []


def load(case):
    base = ROOT / "docs/examples/transaction-01-t02-s02" / case
    s = json.loads((base / "scenario.json").read_bytes())
    return {
        i["id"]: (base / "inputs" / (i["id"] + ".json")).read_bytes()
        for i in s["inputs"]
    }, s


def source_upper_bound(raw, s, cut):
    """Small independent oracle; intentionally overapproximates live endpoints."""
    ops = []
    app_pairs = set()
    for p in s["participants"]:
        report = json.loads(raw[p["input"]])
        observations = {o["id"]: o for o in report["observations"]}
        for choice in s["operations"]:
            if choice["participant"] == p["id"]:
                o = observations[choice["observation"]]
                seq, physical = (
                    o["placement"]["beforeT01Sequence"],
                    o["transactionContext"]["physicalId"],
                )
                assert seq is not None and physical is not None
                ops.append((p["id"], physical, seq))
        # Read frame stack directly, without inventory()/app_sources.
        frames = {x["id"]: x for x in report["transactionModel"]["frames"]}
        stack = []
        before = cut["prefixes"][p["id"]]
        for event in report["transactionModel"]["events"]:
            if event["sequence"] >= before:
                break
            assert event["kind"] != "UNRESOLVED_CALL"
            if event["kind"] == "FRAME_ENTER":
                stack.append(event["frame"])
            elif event["kind"] == "FRAME_EXIT":
                stack.pop()
        for a, b in zip(stack, stack[1:]):
            pa, pb = (
                frames[a]["duringState"]["physicalId"],
                frames[b]["duringState"]["physicalId"],
            )
            assert pa is not None and pb is not None
            if pa != pb:
                app_pairs.add(((p["id"], pa), (p["id"], pb)))
    pairs = {
        ((p, physical), (hp, hphysical))
        for p, physical, seq in ops
        for hp, hphysical, hseq in ops
        if seq == cut["prefixes"][p]
        and hseq < cut["prefixes"][hp]
        and (p, physical) != (hp, hphysical)
    }
    closure = pairs | app_pairs
    while True:
        extended = closure | {(a, d) for a, b in closure for c, d in closure if b == c}
        if extended == closure:
            break
        closure = extended
    return {
        "dbPairs": sorted(pairs),
        "appPairs": sorted(app_pairs),
        "acyclic": not any(a == b for a, b in closure),
    }


class ProofExclusions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f.WaitTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        f.WaitTests.tearDownClass()

    def build(self, raw, s):
        original = copy.deepcopy(s)
        report = wd.build_report(raw, s)
        self.assertTrue(val.validate_report(report, raw))
        self.assertEqual(s, original)
        return report

    def same_p(self, kind):
        raw = {"t": f.WaitTests.models[kind]}
        s = f.scenarios.clear_lock_scenario(
            f.scenarios.scenario(raw, [("a", "t")], kind)
        )
        f.scenarios.cut(s, raw, "incomplete", ["a2"], [])
        return raw, s

    def expect(self, name, raw, s, result, kind=None):
        report = self.build(raw, s)
        self.assertEqual(report["assessment"]["result"], result)
        if kind:
            self.assertEqual(
                report["assessment"]["cuts"][0]["exclusionProof"]["kind"], kind
            )
        proof = (
            source_upper_bound(raw, s, s["cuts"][0])
            if name != "frontier-incomplete-cut"
            else None
        )
        WITNESSES.append(
            {
                "id": name,
                "expected": result,
                "actual": report["assessment"],
                "coverage": report["coverage"],
                "unknowns": report["unknowns"],
                "scenario": copy.deepcopy(s),
                "inputDigests": {k: wd.digest(v) for k, v in raw.items()},
                "independentOracle": proof,
            }
        )
        return report

    def reject_before_producer(self, report, raw):
        with patch.object(val, "build_report", return_value=report) as producer:
            with self.assertRaises(wd.RejectedInput):
                val.validate_report(report, raw)
            producer.assert_not_called()

    def forged(self, case):
        raw, s = load(case)
        s["cuts"][0]["holdings"] = []
        r = self.build(raw, s)
        r["assessment"]["result"] = NEG
        r["assessment"]["cuts"][0]["result"] = NEG
        r["assessment"]["cuts"][0]["exclusionProof"] = {
            "kind": "STRUCTURAL_EXCLUSION",
            "rule": "ACYCLIC_CAUSAL_SUPERGRAPH",
            "operationRefs": sorted(o["id"] for o in r["operations"]),
            "prefixes": s["cuts"][0]["prefixes"],
            "upperBoundEdges": [],
            "scope": "Selected operations at this cut; no lock or runtime absence asserted.",
        }
        return raw, r

    def test_01_four_justified_degradations_remain_unknown(self):
        for case in ("A", "C"):
            raw, s = load(case)
            s["cuts"][0]["holdings"] = []
            r = self.expect(case + "-R1-no-holdings", raw, s, "UNKNOWN")
            self.assertFalse(WITNESSES[-1]["independentOracle"]["acyclic"])
            self.assertEqual(len(r["applicationGraph"]["edges"]), int(case == "C"))
        raw, s = load("A")
        s["cuts"][0]["holdings"].pop()
        self.expect("A-partial-holder-omission", raw, s, "UNKNOWN")
        raw = {"t": f.WaitTests.models["frontier"]}
        s = f.scenarios.scenario(raw, [("a", "t")], "frontier_f02")
        f.scenarios.cut(s, raw, "frontier", ["a2"], ["a1"], "OUTER_REQUIRES_NEW")
        s["cuts"][0]["prefixes"]["a"] += 1
        self.expect("frontier-incomplete-cut", raw, s, "UNKNOWN")

    def test_02_four_unnecessary_degradations_recovered(self):
        raw, s = load("B")
        s["cuts"][0]["pending"] = []
        self.expect("B-no-pending", raw, s, NEG, "STRUCTURAL_EXCLUSION")
        self.assertTrue(WITNESSES[-1]["independentOracle"]["acyclic"])
        raw, s = load("B")
        missing = copy.deepcopy(s["cuts"][0])
        missing.update(id="missing", holdings=[])
        s["cuts"].append(missing)
        r = self.expect(
            "B-one-incomplete-cut", raw, s, NEG, "EVIDENCE_COMPLETE_EXCLUSION"
        )
        self.assertEqual(
            r["assessment"]["cuts"][1]["exclusionProof"]["kind"], "STRUCTURAL_EXCLUSION"
        )
        for kind in ("required", "nested"):
            raw, s = self.same_p(kind)
            self.expect(kind + "-incomplete-cut", raw, s, NEG, "STRUCTURAL_EXCLUSION")
            self.assertTrue(WITNESSES[-1]["independentOracle"]["acyclic"])

    def test_03_complete_acyclic_evidence_route(self):
        raw, s = load("B")
        r = self.build(raw, s)
        self.assertEqual(r["assessment"]["result"], NEG)
        self.assertEqual(
            r["assessment"]["cuts"][0]["exclusionProof"]["kind"],
            "EVIDENCE_COMPLETE_EXCLUSION",
        )

    def test_04_positive_cycles_and_cross_layer_unchanged(self):
        for case, result, db in (
            ("A", "CONDITIONAL_CYCLE_RISK", 2),
            ("C", "CONDITIONAL_CROSS_LAYER_COMPLETION_RISK", 1),
        ):
            raw, s = load(case)
            r = self.build(raw, s)
            self.assertEqual(r["assessment"]["result"], result)
            self.assertEqual(len(r["databaseGraph"]["edges"]), db)
            self.assertIsNone(r["assessment"]["cuts"][0]["exclusionProof"])

    def test_05_forged_empty_structural_proof_A_rejected(self):
        raw, r = self.forged("A")
        self.reject_before_producer(r, raw)

    def test_06_forged_C_cannot_ignore_application_completion(self):
        raw, r = self.forged("C")
        self.reject_before_producer(r, raw)

    def test_07_exact_but_cyclic_certificate_rejected_independently(self):
        raw, r = self.forged("A")
        cut = r["assessment"]["cuts"][0]
        ops = {o["id"]: o for o in r["operations"]}
        cut["exclusionProof"]["upperBoundEdges"] = [
            {
                "from": wd.node_id(ops[q]["namespace"]),
                "to": wd.node_id(ops[h]["namespace"]),
                "type": "POSSIBLE_DB_WAIT",
                "evidence": [q, h],
            }
            for q, h in (("a/O2", "b/O1"), ("b/O2", "a/O1"))
        ]
        self.reject_before_producer(r, raw)

    def test_08_removed_edge_from_valid_proof_rejected(self):
        raw, s = load("B")
        s["cuts"][0]["holdings"] = []
        r = self.build(raw, s)
        r["assessment"]["cuts"][0]["exclusionProof"]["upperBoundEdges"] = []
        self.reject_before_producer(r, raw)

    def test_09_proof_scope_and_prefix_tampering_rejected(self):
        raw, s = self.same_p("required")
        for field, value in (
            ("prefixes", {"a": 1}),
            ("operationRefs", []),
            ("kind", "EVIDENCE_COMPLETE_EXCLUSION"),
        ):
            r = self.build(raw, s)
            r["assessment"]["cuts"][0]["exclusionProof"][field] = value
            self.reject_before_producer(r, raw)

    def test_10_missing_evidence_stays_visible(self):
        raw, s = load("B")
        s["cuts"][0]["holdings"] = []
        r = self.build(raw, s)
        self.assertEqual(r["coverage"]["status"], "INCOMPLETE")
        self.assertTrue(r["assessment"]["cuts"][0]["unknowns"])
        for field in ("coverage", "cut-unknowns", "global-unknowns"):
            forged = copy.deepcopy(r)
            if field == "coverage":
                forged["coverage"]["status"] = "COMPLETE_MODELED_SCOPE"
            elif field == "cut-unknowns":
                forged["assessment"]["cuts"][0]["unknowns"] = []
            else:
                forged["unknowns"] = []
            self.reject_before_producer(forged, raw)

    def test_11_null_or_unplaced_identity_no_structural_proof(self):
        for oid in ("O-F07", "O-G01", "O-G03"):
            raw, s = f.WaitTests.case(f.WaitTests, oid)
            r = self.build(raw, s)
            self.assertEqual(r["assessment"]["result"], "UNKNOWN")

    def test_12_partial_inventory_preserves_enlistment_unknown(self):
        raw, s = f.WaitTests.case(f.WaitTests, "O-F02")
        self.assertEqual(self.build(raw, s)["assessment"]["result"], "UNKNOWN")

    def test_13_same_P_minimal_no_assumptions(self):
        for kind in ("required", "nested"):
            raw, s = self.same_p(kind)
            s["resources"], s["premises"] = [], []
            s["participants"][0]["independence"] = None
            s["lockRule"] = {
                "id": "none",
                "version": 1,
                "modes": [],
                "compatibility": [],
                "blockingPremise": None,
            }
            s["cuts"][0]["temporal"] = {"kind": "UNKNOWN", "premise": None}
            for op in s["operations"]:
                op["resource"] = None
            r = self.build(raw, s)
            self.assertEqual(r["assessment"]["result"], NEG)
            self.assertFalse(r["databaseGraph"]["edges"])
            self.assertEqual(
                r["assessment"]["cuts"][0]["exclusionProof"]["upperBoundEdges"], []
            )

    def test_14_same_P_without_cut_independent_validator(self):
        raw, s = self.same_p("required")
        s["cuts"] = []
        r = self.build(raw, s)
        self.assertEqual(
            r["assessment"]["exclusionProof"]["kind"], "STRUCTURAL_EXCLUSION"
        )
        with patch.object(wd, "single_physical_scope", return_value=False):
            with patch.object(val, "build_report", return_value=r):
                self.assertTrue(val.validate_report(r, raw))

    def test_15_unknown_acquisition_and_dependencies_still_block_A(self):
        raw, s = load("A")
        for h in s["cuts"][0]["holdings"]:
            acquire = next(
                p for p in s["premises"] if p["id"] == h["acquisitionPremise"]
            )
            retain = next(p for p in s["premises"] if p["id"] == h["retentionPremise"])
            acquire["state"] = "UNKNOWN"
            retain["dependsOn"] = [acquire["id"]]
        self.assertEqual(self.build(raw, s)["assessment"]["result"], "UNKNOWN")

    def test_16_no_sidecar_can_self_certify_model_evidence(self):
        raw, s = load("B")
        s["premises"][0]["state"] = "MODEL_EVIDENCE"
        with self.assertRaises(wd.RejectedInput):
            wd.build_report(raw, s)

    def test_17_budget_guards_include_serialized_proof_edges(self):
        raw, s = load("B")
        s["cuts"][0]["holdings"] = []
        r = self.build(raw, s)
        graph_edges = sum(
            len(r[k]["edges"]) for k in ("databaseGraph", "applicationGraph")
        ) + len(r["crossLayerRelations"])
        self.assertGreater(r["coverage"]["serializedEdges"], graph_edges)
        with patch.dict(wd.BUDGETS, {"serializedEdges": graph_edges}):
            with self.assertRaises(wd.BudgetExceeded):
                wd.build_report(raw, s)
        with patch.dict(wd.BUDGETS, {"candidateComparisons": 1}):
            with self.assertRaises(wd.BudgetExceeded):
                wd.build_report(raw, s)

    def test_18_incompatible_cuts_and_holdings_still_distinct(self):
        for oid, expected in (
            ("O-B02", "CYCLE_FEASIBILITY_UNKNOWN"),
            ("O-B03", NEG),
            ("O-G04", NEG),
        ):
            raw, s = f.WaitTests.case(f.WaitTests, oid)
            self.assertEqual(self.build(raw, s)["assessment"]["result"], expected)

    def test_19_cli_proof_unknown_budget_and_altered_sidecar(self):
        for case in ("A", "B", "C"):
            raw, s = load(case)
            s["cuts"][0]["holdings"] = []
            with tempfile.TemporaryDirectory(prefix="mana-f02-cli-") as tmp:
                stage = Path(tmp).resolve()
                scenario = stage / "scenario.json"
                scenario.write_text(json.dumps(s))
                args = [
                    sys.executable,
                    str(ROOT / "scripts/mana-wait-dependencies.py"),
                    "--scenario",
                    str(scenario),
                ]
                for key, value in raw.items():
                    path = stage / (key + ".json")
                    path.write_bytes(value)
                    args += ["--timeline", key + "=" + str(path)]
                generated = subprocess.run(
                    args + ["--output-dir", str(stage / "out")],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(generated.returncode, 0, generated.stderr)
                summary = json.loads(generated.stdout)
                self.assertEqual(
                    summary["assessment"], NEG if case == "B" else "UNKNOWN"
                )
                self.assertEqual(
                    summary["exclusionProofs"],
                    ["STRUCTURAL_EXCLUSION"] if case == "B" else [],
                )
                markdown = (stage / "out/report.md").read_text()
                self.assertIn("W4", markdown)
                if case == "B":
                    self.assertIn("STRUCTURAL_EXCLUSION", markdown)
                validated = subprocess.run(
                    args + ["--validate", str(stage / "out/wait-dependency.json")],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(validated.returncode, 0, validated.stderr)
                s["cuts"][0]["pending"] = []
                scenario.write_text(json.dumps(s))
                altered = subprocess.run(
                    args + ["--validate", str(stage / "out/wait-dependency.json")],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(altered.returncode, 2)
                scenario.write_bytes(b" " * (wd.BUDGETS["sidecarBytes"] + 1))
                limited = subprocess.run(
                    args + ["--output-dir", str(stage / "budget")],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(limited.returncode, 2)
                self.assertFalse((stage / "budget").exists())

    def test_20_structural_union_cannot_promote_incompatible_directions(self):
        raw, s = load("B")
        first = copy.deepcopy(s["cuts"][0])
        first["holdings"] = []
        other = copy.deepcopy(first)
        other.update(id="reverse", prefixes={"a": 4, "b": 5}, pending=["a1", "b2"])
        s["cuts"] = [first, other]
        r = self.build(raw, s)
        self.assertTrue(all(c["result"] == NEG for c in r["assessment"]["cuts"]))
        self.assertEqual(r["assessment"]["result"], "CYCLE_FEASIBILITY_UNKNOWN")
        r["assessment"]["result"] = NEG
        self.reject_before_producer(r, raw)

    def test_21_namespace_never_merges_replicated_local_P1(self):
        raw, s = load("A")
        s["cuts"][0]["holdings"] = []
        self.assertEqual(len(self.build(raw, s)["databaseGraph"]["nodes"]), 2)
        self.assertFalse(source_upper_bound(raw, s, s["cuts"][0])["acyclic"])

    def test_22_validator_does_not_call_structural_producer(self):
        raw, s = load("B")
        s["cuts"][0]["holdings"] = []
        r = self.build(raw, s)
        with patch.object(
            wd,
            "structural_exclusion",
            side_effect=AssertionError("producer must not run"),
        ):
            with patch.object(val, "build_report", return_value=r):
                self.assertTrue(val.validate_report(r, raw))

    def test_24_evidence_complete_cannot_hide_cross_layer_circuit(self):
        raw, s = load("C")
        r = self.build(raw, s)
        r["assessment"]["result"] = NEG
        cut = r["assessment"]["cuts"][0]
        cut["result"] = NEG
        cut["exclusionProof"] = {
            "kind": "EVIDENCE_COMPLETE_EXCLUSION",
            "rule": "QUALIFIED_OR_CONTRADICTED_CANDIDATES",
            "candidateRefs": [c["id"] for c in r["waitCandidates"]],
        }
        self.reject_before_producer(r, raw)

    def test_23_historical_example_semantics_and_diagrams_preserved(self):
        for case in ("A", "B", "C"):
            raw, s = load(case)
            r = self.build(raw, s)
            historical = json.loads(
                (
                    ROOT
                    / "docs/examples/transaction-01-t02-s02"
                    / case
                    / "wait-dependency.json"
                ).read_bytes()
            )
            normalized = copy.deepcopy(r)
            normalized["assessment"].pop("exclusionProof")
            for c in normalized["assessment"]["cuts"]:
                c.pop("exclusionProof")
            self.assertEqual(normalized, historical)
            artifacts = f.s02.artifacts(r)
            for name, value in artifacts.items():
                if name.endswith(".mmd"):
                    self.assertEqual(
                        value,
                        (
                            ROOT / "docs/examples/transaction-01-t02-s02" / case / name
                        ).read_bytes(),
                    )


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProofExclusions)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if os.environ.get("MANA_F02_WITNESSES"):
        Path(os.environ["MANA_F02_WITNESSES"]).write_text(
            json.dumps(WITNESSES, indent=2) + "\n"
        )
    sys.exit(not result.wasSuccessful())
