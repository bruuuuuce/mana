#!/usr/bin/env python3
"""F03 wire checks with byte-verified historical consumers, never simulations.

--diagnostic-replay runs the unchanged F02 assertions against the private proof
representation. The ordinary F02 entry point remains a separate historical gate.
"""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from skill_factory.transactions import wait_dependencies as wd  # noqa: E402
from skill_factory.transactions import wait_validation as val  # noqa: E402

PREFIX = ROOT / "docs/reports/TRANSACTION-01-T02-S02-I01"
NEG = "NO_CYCLE_IN_MODELED_SCENARIO"
EVIDENCE = {}


def fixture_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


f02 = fixture_module("f03_f02", "tests/wait-dependencies-proof-exclusions.py")


def patch_source(source, patch_path, path):
    """Apply only the named file's hunks in memory, checking all old bytes."""
    lines = patch_path.read_text().splitlines(keepends=True)
    start = lines.index("+++ b/" + path + "\n") + 1
    stop = next(
        (
            i
            for i in range(start, len(lines))
            if lines[i].startswith(("diff --git ", "--- "))
        ),
        len(lines),
    )
    old = source.splitlines(keepends=True)
    result, pos, i = [], 0, start
    while i < stop:
        match = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", lines[i])
        assert match, lines[i]
        at = max(0, int(match[1]) - 1)
        assert at >= pos
        result.extend(old[pos:at])
        pos, i = at, i + 1
        while i < stop and not lines[i].startswith("@@"):
            line = lines[i]
            i += 1
            assert line[0] in " +-", line
            if line[0] in " -":
                assert old[pos] == line[1:], (path, pos)
                pos += 1
            if line[0] in " +":
                result.append(line[1:])
    result.extend(old[pos:])
    return "".join(result)


def historical_modules():
    receipts = {
        version: json.loads(
            Path(str(PREFIX) + "-" + version + "-results.json").read_bytes()
        )
        for version in ("F01", "F02")
    }
    sources, hashes = {}, {}
    for name in ("wait_dependencies", "wait_validation"):
        path = "scripts/skill_factory/transactions/" + name + ".py"
        source = patch_source("", PREFIX.with_suffix(".patch"), path)
        for version in ("F01", "F02"):
            record = next(
                c
                for c in receipts[version]["integrity"][
                    "changedAuthorizedFiles"
                    if version == "F01"
                    else "authorizedChanges"
                ]
                if c["path"] == path
            )
            actual = hashlib.sha256(source.encode()).hexdigest()
            assert actual == record["before"]["sha256"], (version, name, actual)
            if version == "F02":
                sources.setdefault("pre-F02", {})[name] = source
            source = patch_source(
                source, Path(str(PREFIX) + "-" + version + ".patch"), path
            )
            assert (
                hashlib.sha256(source.encode()).hexdigest() == record["after"]["sha256"]
            )
        sources.setdefault("F02", {})[name] = source
    generations = {}
    for version, records in sources.items():
        modules = []
        hashes[version] = {}
        for name, source in records.items():
            module = types.ModuleType("skill_factory.transactions._f03_" + name)
            exec(compile(source, name + "@" + version, "exec"), module.__dict__)
            modules.append(module)
            hashes[version][name] = hashlib.sha256(source.encode()).hexdigest()
        engine, validator = modules
        for name, value in list(validator.__dict__.items()):
            if hasattr(wd, name) and value is getattr(wd, name):
                validator.__dict__[name] = getattr(engine, name)
        generations[version] = (engine, validator)
    EVIDENCE["historicalModuleHashes"] = hashes
    return generations


def acceptance(validator, report, raw):
    try:
        return {"accepted": validator.validate_report(report, raw)}
    except (ValueError, KeyError, TypeError) as error:
        return {"accepted": False, "error": type(error).__name__, "reason": str(error)}


class WireCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f02.f.WaitTests.setUpClass()
        cls.generations = historical_modules()

    @classmethod
    def tearDownClass(cls):
        f02.f.WaitTests.tearDownClass()

    def build(self, raw, scenario):
        report = wd.build_report(raw, scenario)
        self.assertNotIn("exclusionProof", report["assessment"])
        for cut in report["assessment"]["cuts"]:
            self.assertNotIn("exclusionProof", cut)
        wire = (
            json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False).encode()
            + b"\n"
        )
        decoded = wd.parse_json(wire, wd.BUDGETS["sidecarBytes"])
        self.assertEqual(decoded, report)
        self.assertTrue(val.validate_report(decoded, raw))
        return report

    def reject_before_producer(self, report, raw):
        with patch.object(val, "build_report", return_value=report) as producer:
            with self.assertRaises(wd.RejectedInput):
                val.validate_report(report, raw)
            producer.assert_not_called()

    def test_01_actual_consumer_matrix_before_and_after(self):
        rows = []
        for case in ("A", "B", "C"):
            raw, scenario = f02.load(case)
            reports = {
                v: e.build_report(raw, scenario)
                for v, (e, _) in self.generations.items()
            }
            reports["F03"] = self.build(raw, scenario)
            historical = json.loads(
                (
                    ROOT
                    / "docs/examples/transaction-01-t02-s02"
                    / case
                    / "wait-dependency.json"
                ).read_bytes()
            )
            self.assertEqual(reports["pre-F02"], historical)
            self.assertEqual(reports["F03"], historical)
            consumers = {v: vld for v, (_, vld) in self.generations.items()}
            consumers["F03"] = val
            matrix = {
                producer: {
                    consumer: acceptance(vld, r, raw)
                    for consumer, vld in consumers.items()
                }
                for producer, r in reports.items()
            }
            self.assertTrue(matrix["pre-F02"]["pre-F02"]["accepted"])
            self.assertFalse(matrix["pre-F02"]["F02"]["accepted"])
            self.assertFalse(matrix["F02"]["pre-F02"]["accepted"])
            self.assertTrue(matrix["F02"]["F02"]["accepted"])
            for producer in reports:
                self.assertTrue(matrix[producer]["F03"]["accepted"])
            self.assertTrue(matrix["F03"]["pre-F02"]["accepted"])
            rows.append({"case": case, "matrix": matrix})
        EVIDENCE["compatibility"] = rows

    def test_02_unknown_wire_and_historical_counters(self):
        raw, scenario = f02.load("A")
        scenario["cuts"][0]["holdings"] = []
        report = self.build(raw, scenario)
        engine, validator = self.generations["pre-F02"]
        self.assertEqual(report, engine.build_report(raw, scenario))
        self.assertTrue(validator.validate_report(report, raw))
        self.assertEqual(report["assessment"]["result"], "UNKNOWN")
        f02_unknown = self.generations["F02"][0].build_report(raw, scenario)
        self.assertTrue(val.validate_report(f02_unknown, raw))
        EVIDENCE["unknownCompatibility"] = {
            "preF02AcceptsF03": True,
            "F03AcceptsHistoricalF02": True,
            "candidateComparisons": report["coverage"]["candidateComparisons"],
        }

    def test_03_four_structural_exclusions(self):
        variants = []
        for name in ("B-no-pending", "B-one-incomplete-cut", "required", "nested"):
            if name.startswith("B"):
                raw, scenario = f02.load("B")
                if name == "B-no-pending":
                    scenario["cuts"][0]["pending"] = []
                else:
                    other = copy.deepcopy(scenario["cuts"][0])
                    other.update(id="missing", holdings=[])
                    scenario["cuts"].append(other)
            else:
                raw = {"t": f02.f.WaitTests.models[name]}
                scenario = f02.f.scenarios.clear_lock_scenario(
                    f02.f.scenarios.scenario(raw, [("a", "t")], name)
                )
                f02.f.scenarios.cut(scenario, raw, "incomplete", ["a2"], [])
            report = self.build(raw, scenario)
            self.assertEqual(report["assessment"]["result"], NEG)
            self.assertEqual(report["coverage"]["status"], "INCOMPLETE")
            self.assertTrue(
                all(
                    f02.source_upper_bound(raw, scenario, cut)["acyclic"]
                    for cut in scenario["cuts"]
                )
            )
            variants.append(
                {
                    "id": name,
                    "assessment": report["assessment"],
                    "coverage": report["coverage"],
                    "oldConsumer": acceptance(
                        self.generations["pre-F02"][1], report, raw
                    ),
                }
            )
        EVIDENCE["structuralExclusions"] = variants

    def test_04_four_justified_unknowns_and_forged_negatives(self):
        variants = []
        for name in ("A", "C", "partial-A", "frontier"):
            if name == "frontier":
                raw = {"t": f02.f.WaitTests.models["frontier"]}
                scenario = f02.f.scenarios.scenario(raw, [("a", "t")], "frontier_f03")
                f02.f.scenarios.cut(
                    scenario, raw, "frontier", ["a2"], ["a1"], "OUTER_REQUIRES_NEW"
                )
                scenario["cuts"][0]["prefixes"]["a"] += 1
            else:
                raw, scenario = f02.load("A" if name == "partial-A" else name)
                if name == "partial-A":
                    scenario["cuts"][0]["holdings"].pop()
                else:
                    scenario["cuts"][0]["holdings"] = []
            report = self.build(raw, scenario)
            self.assertEqual(report["assessment"]["result"], "UNKNOWN")
            forged = copy.deepcopy(report)
            forged["assessment"]["result"] = NEG
            for cut in forged["assessment"]["cuts"]:
                cut["result"] = NEG
            self.reject_before_producer(forged, raw)
            variants.append(
                {
                    "id": name,
                    "assessment": report["assessment"],
                    "forgedNegativeRejectedBeforeReprojection": True,
                }
            )
        EVIDENCE["degradations"] = variants

    def test_05_original_false_negatives_are_semantic_rejections(self):
        witness = json.loads(Path(str(PREFIX) + "-F01-witnesses.json").read_bytes())
        EVIDENCE["originalWitnessKeys"] = list(witness)
        # I01 producer is recovered independently of the tightened pre-F02 one.
        path = "scripts/skill_factory/transactions/wait_dependencies.py"
        source = patch_source("", PREFIX.with_suffix(".patch"), path)
        engine = types.ModuleType("skill_factory.transactions._f03_i01")
        exec(compile(source, path + "@I01", "exec"), engine.__dict__)
        for case in ("A", "C"):
            raw, scenario = f02.load(case)
            scenario["cuts"][0]["holdings"] = []
            old = engine.build_report(raw, scenario)
            self.assertEqual(old["assessment"]["result"], NEG)
            self.reject_before_producer(old, raw)

    def test_06_no_proof_field_can_bypass_source_authority(self):
        for case in ("A", "C"):
            raw, scenario = f02.load(case)
            scenario["cuts"][0]["holdings"] = []
            forged = self.build(raw, scenario)
            forged["assessment"]["result"] = NEG
            cut = forged["assessment"]["cuts"][0]
            cut["result"] = NEG
            cut["exclusionProof"] = {
                "kind": "EVIDENCE_COMPLETE_EXCLUSION",
                "rule": "QUALIFIED_OR_CONTRADICTED_CANDIDATES",
                "candidateRefs": [],
            }
            self.reject_before_producer(forged, raw)

    def test_07_proofless_exclusion_does_not_hide_missing_evidence(self):
        raw, scenario = f02.load("B")
        scenario["cuts"][0]["holdings"] = []
        report = self.build(raw, scenario)
        for field in ("coverage", "cut", "global"):
            forged = copy.deepcopy(report)
            if field == "coverage":
                forged["coverage"]["status"] = "COMPLETE_MODELED_SCOPE"
            elif field == "cut":
                forged["assessment"]["cuts"][0]["unknowns"] = []
            else:
                forged["unknowns"] = []
            self.reject_before_producer(forged, raw)

    def test_08_structural_validation_independent_of_proof_builder(self):
        raw, scenario = f02.load("B")
        scenario["cuts"][0]["holdings"] = []
        report = self.build(raw, scenario)
        with patch.object(
            wd,
            "structural_exclusion",
            side_effect=AssertionError("producer must not run"),
        ):
            with patch.object(val, "build_report", return_value=report):
                self.assertTrue(val.validate_report(report, raw))

    def test_09_actual_cli_roundtrip_and_deterministic_serialization(self):
        rows = []
        for case in ("A", "B", "C"):
            base = ROOT / "docs/examples/transaction-01-t02-s02" / case
            raw, scenario = f02.load(case)
            args = [
                sys.executable,
                str(ROOT / "scripts/mana-wait-dependencies.py"),
                "--scenario",
                str(base / "scenario.json"),
            ]
            for key in raw:
                args += [
                    "--timeline",
                    key + "=" + str(base / "inputs" / (key + ".json")),
                ]
            with tempfile.TemporaryDirectory(prefix="mana-f03-wire-") as tmp:
                stage = Path(tmp).resolve()
                outputs = []
                for seed in ("1", "97"):
                    output = stage / seed
                    generated = subprocess.run(
                        args + ["--output-dir", str(output)],
                        capture_output=True,
                        text=True,
                        env={**os.environ, "PYTHONHASHSEED": seed},
                    )
                    self.assertEqual(generated.returncode, 0, generated.stderr)
                    outputs.append((output / "wait-dependency.json").read_bytes())
                    checked = subprocess.run(
                        args + ["--validate", str(output / "wait-dependency.json")],
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(checked.returncode, 0, checked.stderr)
                self.assertEqual(outputs[0], outputs[1])
                self.assertEqual(
                    outputs[0], (base / "wait-dependency.json").read_bytes()
                )
                legacy = stage / "historical-f02.json"
                legacy.write_text(
                    json.dumps(self.generations["F02"][0].build_report(raw, scenario))
                )
                legacy_checked = subprocess.run(
                    args + ["--validate", str(legacy)], capture_output=True, text=True
                )
                self.assertEqual(legacy_checked.returncode, 0, legacy_checked.stderr)
                for name in (
                    "application.mmd",
                    "cross-layer.mmd",
                    "report.md",
                    *(p.name for p in base.glob("database*.mmd")),
                ):
                    self.assertEqual(
                        (stage / "1" / name).read_bytes(),
                        (base / name).read_bytes(),
                        (case, name),
                    )
                rows.append(
                    {
                        "case": case,
                        "cliExit": 0,
                        "cliHistoricalF02Exit": legacy_checked.returncode,
                        "hashSeeds": [1, 97],
                        "allArtifactsByteIdenticalToHistorical": True,
                        "jsonSha256": hashlib.sha256(outputs[0]).hexdigest(),
                    }
                )
        EVIDENCE["serialization"] = rows

    def test_10_closed_envelope_and_unrecognized_values(self):
        raw, scenario = f02.load("A")
        report = self.build(raw, scenario)
        for name in (
            "extra-envelope",
            "missing-field",
            "schema",
            "certainty",
            "result",
        ):
            forged = copy.deepcopy(report)
            if name == "extra-envelope":
                forged["extra"] = None
            elif name == "missing-field":
                del forged["status"]
            elif name == "schema":
                forged["schema"] = "mana.wait-dependency/v2"
            elif name == "certainty":
                forged["claims"][0]["certainty"] = "OBSERVED"
            else:
                forged["assessment"]["result"] = "DEADLOCK_FREE"
            self.assertFalse(acceptance(val, forged, raw)["accepted"])
        for raw_json in (b'{"x":1,"x":2}', b'{"x":NaN}', b"{broken"):
            with self.assertRaises(ValueError):
                wd.parse_json(raw_json, 1024)

    def test_11_evidence_complete_cuts_do_not_union_unqualified_bounds(self):
        raw, scenario = f02.load("B")
        first = scenario["cuts"][0]
        other = copy.deepcopy(first)
        other.update(id="reverse", prefixes={"a": 4, "b": 5}, pending=["a1", "b2"])
        other["holdings"] = [
            {
                "operation": "b1",
                "acquisitionPremise": "b1_acquire",
                "retentionPremise": "b1_retain",
            }
        ]
        scenario["cuts"].append(other)
        # Explicit contradictory resource relation excludes all DB candidates;
        # a cycle in a coarser source bound cannot override this complete proof.
        for resource in scenario["resources"]:
            resource["databaseRelation"] = "DISJOINT"
        report = self.build(raw, scenario)
        self.assertEqual(report["assessment"]["result"], NEG)
        self.assertFalse(report["databaseGraph"]["edges"])
        legacy = self.generations["F02"][0].build_report(raw, scenario)
        self.assertEqual(legacy["assessment"]["result"], NEG)
        self.assertTrue(val.validate_report(legacy, raw))


class DiagnosticReplay(f02.ProofExclusions):
    """Retain all 24 historical assertions; select only the internal proof API."""

    def build(self, raw, scenario):
        original = copy.deepcopy(scenario)
        report, _ = wd._derive_report(raw, scenario)
        self.assertTrue(val.validate_report(report, raw))
        self.assertEqual(scenario, original)
        return report


if __name__ == "__main__":
    diagnostic = "--diagnostic-replay" in sys.argv
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        DiagnosticReplay if diagnostic else WireCompatibility
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    EVIDENCE.update(
        testsRun=result.testsRun,
        failures=len(result.failures),
        errors=len(result.errors),
        mode="F02 internal diagnostic replay" if diagnostic else "F03 public wire",
        status="PASS" if result.wasSuccessful() else "FAIL",
    )
    if os.environ.get("MANA_F03_EVIDENCE"):
        Path(os.environ["MANA_F03_EVIDENCE"]).write_text(
            json.dumps(EVIDENCE, indent=2) + "\n"
        )
    sys.exit(not result.wasSuccessful())
