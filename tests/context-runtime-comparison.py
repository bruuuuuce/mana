#!/usr/bin/env python3
"""CTX-09B local corpus, uncertainty/provenance and adversarial filesystem tests."""
import sys
sys.dont_write_bytecode = True

import copy
import importlib.util
import json
import os
import signal
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location("ctx09b_test", REPO / "scripts/lib/context-comparison.py")
comp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comp)
mode = comp.mode
FIXTURES = REPO / "tests/fixtures/context-runtime/comparison"
BASELINE = json.loads((FIXTURES / "baseline.json").read_bytes())
CORPUS = json.loads((FIXTURES / "corpus.json").read_bytes())["cases"]
OFFLINE_SPEC = importlib.util.spec_from_file_location("ctx09b_offline", REPO / "tests/lib/json_schema_subset.py")
offline = importlib.util.module_from_spec(OFFLINE_SPEC)
OFFLINE_SPEC.loader.exec_module(offline)
HARNESS_SPEC = importlib.util.spec_from_file_location("ctx09b_producers", REPO / "tests/fixtures/context-runtime/ctx09b-producer-harness.py")
harness = importlib.util.module_from_spec(HARNESS_SPEC)
HARNESS_SPEC.loader.exec_module(harness)


class Comparison(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ctx09b-", dir="/private/tmp" if sys.platform == "darwin" else "/tmp")
        self.base = Path(self.temporary.name)
        self.project = self.base / "project with spaces"
        self.artifacts = self.project / "artifacts"
        self.artifacts.mkdir(parents=True)
        self.legacy = self.artifacts / "legacy.json"
        self.v2 = self.artifacts / "v2.json"
        self.folder = self.project / mode.NAMESPACE / "test"
        self.plan = self.folder / "mode-plan-v1.json"
        self.report_file = self.folder / comp.REPORT_FILE
        self.left, self.right = copy.deepcopy(BASELINE), copy.deepcopy(BASELINE)
        self.environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

    def tearDown(self):
        comp._TEST_HOOK = None
        mode._TEST_HOOK = None
        self.temporary.cleanup()

    def register(self, execution_id="test", left=None, right=None):
        def payload(value):
            return value if isinstance(value, bytes) else mode.canonical(value)
        harness.publish_pair(mode, self.project, execution_id, payload(self.left if left is None else left),
                             payload(self.right if right is None else right))
        registered = subprocess.run([sys.executable, str(REPO / "scripts/context-runtime-mode.py"), "compare",
                                     "--project-root", str(self.project), "--execution-id", execution_id,
                                     "--profile-id", "fixture-review", "--target-key", "a" * 64,
                                     "--legacy-artifact", "artifacts/legacy.json", "--v2-artifact", "artifacts/v2.json"],
                                    env=self.environment, capture_output=True)
        self.assertEqual(registered.returncode, 0, registered.stderr)

    def run_report(self, write=False, execution_id="test"):
        return json.loads(comp.run(str(self.project), execution_id, write))

    def cli(self, *args, root=None):
        return subprocess.run([str(REPO / "scripts/mana-context-compare.sh"), "test", "--project-root",
                               str(root or self.project), *args], env=self.environment, capture_output=True)

    def dimension(self, report, name):
        return next(item for item in report["dimensions"] if item["name"] == name)

    def snapshot(self):
        return {str(path.relative_to(self.project)): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                for path in self.project.rglob("*") if path.is_file() and not path.is_symlink()}

    def no_staging(self):
        self.assertFalse([str(path) for path in self.base.rglob("*") if ".stage." in path.name])

    def test_cross_dimension_conflicts_identical_on_both_sides_never_equivalent(self):
        for index, (first, second) in enumerate((("affirmed", "denied"), ("denied", "affirmed"))):
            value = copy.deepcopy(BASELINE)
            blocker = value["dimensions"]["blockers"]["records"][0]
            blocker["value"]["stance"] = first
            finding = copy.deepcopy(blocker)
            finding["key"] = "cross-dimension-finding"
            finding["value"]["stance"] = second
            value["dimensions"]["warnings"]["records"] = [finding]
            execution = f"cross-conflict-{index}"
            self.register(execution_id=execution, left=value, right=value)
            report = self.run_report(execution_id=execution)
            self.assertEqual(report["status"], "indeterminate")
            self.assertFalse(report["complete"])
            self.assertIn("unresolved_internal_conflict", report["reasons"])
            self.assertEqual(len(report["conflicts"]), 2)
            for conflict in report["conflicts"]:
                self.assertEqual(conflict["stances"], ["affirmed", "denied"])
                self.assertEqual([p["pointer"] for p in conflict["observations"]],
                                 ["/dimensions/blockers/records/0", "/dimensions/warnings/records/0"])
                self.assertTrue(all(p["evidence"] for p in conflict["observations"]))
            self.assertEqual(comp.run(str(self.project), execution), comp.run(str(self.project), execution))

    def test_compatible_cross_dimension_claims_and_similar_text_distinct_claims(self):
        for index, same in enumerate((True, False)):
            value = copy.deepcopy(BASELINE)
            finding = copy.deepcopy(value["dimensions"]["blockers"]["records"][0])
            finding["key"] = "other-finding"
            if not same:
                finding["value"].update(predicate="approval-optional", stance="denied")
            # Exact same prose cannot merge different structured claim keys.
            value["dimensions"]["warnings"]["records"] = [finding]
            execution = f"compatible-{index}"
            self.register(execution_id=execution, left=value, right=value)
            report = self.run_report(execution_id=execution)
            self.assertEqual(report["status"], "equivalent")
            self.assertTrue(report["complete"])
            self.assertEqual(report["conflicts"], [])

    def test_conflict_declared_through_uncertainty_is_explicit(self):
        self.left["dimensions"]["blockers"]["records"][0]["uncertainty"] = ["contradictory-evidence"]
        self.right = copy.deepcopy(self.left)
        self.register()
        report = self.run_report()
        self.assertEqual(report["status"], "indeterminate")
        self.assertFalse(report["complete"])
        self.assertTrue(all(c["declaredThroughUncertainty"] for c in report["conflicts"]))
        self.assertEqual(report["conflicts"][0]["observations"][0]["uncertainty"], ["contradictory-evidence"])

    def test_multiple_conflicts_inverted_order_and_known_difference_remain_indeterminate(self):
        value = copy.deepcopy(BASELINE)
        first = value["dimensions"]["blockers"]["records"][0]
        second = copy.deepcopy(first)
        second["key"] = "second"
        second["value"]["predicate"] = "payment-allowed"
        value["dimensions"]["blockers"]["records"].append(second)
        value["dimensions"]["warnings"]["records"] = []
        for i, blocker in enumerate(value["dimensions"]["blockers"]["records"]):
            denied = copy.deepcopy(blocker)
            denied["key"] = f"denied-{i}"
            denied["value"]["stance"] = "denied"
            value["dimensions"]["warnings"]["records"].append(denied)
        right = copy.deepcopy(value)
        for name in ("blockers", "warnings"):
            right["dimensions"][name]["records"].reverse()
        right["dimensions"]["status"]["records"][0]["value"] = "pass"
        self.register(left=value, right=right)
        report = self.run_report()
        self.assertEqual(report["status"], "indeterminate")
        self.assertFalse(report["complete"])
        keys = {side: [c["semanticKey"] for c in report["conflicts"] if c["side"] == side]
                for side in ("legacy", "v2")}
        self.assertEqual(keys["legacy"], sorted(keys["legacy"]))
        self.assertEqual(keys["legacy"], keys["v2"])
        self.assertEqual(comp.run(str(self.project), "test"), comp.run(str(self.project), "test"))

    def register_command(self, left="artifacts/legacy.json", right="artifacts/v2.json", **identity):
        argv = [sys.executable, str(REPO / "scripts/context-runtime-mode.py"), "compare", "--project-root",
                str(self.project), "--execution-id", "test", "--legacy-artifact", left, "--v2-artifact", right]
        for name, val in {"profile_id": "fixture-review", "target_key": "a" * 64, **identity}.items():
            argv += ["--" + name.replace("_", "-"), val]
        return subprocess.run(argv, env=self.environment, capture_output=True)

    def publish_only(self):
        harness.publish_pair(mode, self.project, "test", mode.canonical(self.left), mode.canonical(self.right))

    def receipt_path(self, path="artifacts/v2.json", commit=False):
        namespace, key = mode.receipt_location("test", path)
        return self.project / namespace / (key + (".commit" if commit else "")) / (
            "producer-commit-v1.json" if commit else "producer-receipt-v1.json")

    def test_producer_roles_correct_and_swapped_registration(self):
        self.publish_only()
        self.assertEqual(self.register_command("artifacts/v2.json", "artifacts/legacy.json").returncode, 2)
        self.assertEqual(self.register_command("artifacts/v2.json", "artifacts/v2.json").returncode, 2)
        self.assertEqual(self.register_command("artifacts/legacy.json", "artifacts/legacy.json").returncode, 2)
        self.assertFalse(self.plan.exists())
        self.assertEqual(self.register_command(profile_id="fixture-review", target_key="a" * 64).returncode, 0)
        report = self.run_report()
        self.assertEqual(report["status"], "equivalent")
        self.assertEqual([report["sources"][s]["producerRuntime"] for s in ("legacy", "v2")], ["legacy", "v2"])

    def test_producer_receipt_missing_foreign_and_tampered_fail_closed(self):
        self.publish_only()
        self.assertEqual(self.register_command(profile_id="foreign-profile").returncode, 2)
        self.assertEqual(self.register_command(target_key="c" * 64).returncode, 2)
        receipt_path = self.receipt_path()
        original = receipt_path.read_bytes()
        receipt_path.unlink()
        self.assertEqual(self.register_command().returncode, 2)
        receipt_path.write_bytes(original)
        receipt_path.chmod(0o600)
        for field, val in (("executionId", "foreign-run"), ("profileId", "foreign-profile"),
                           ("targetKey", "d" * 64), ("producerRuntime", "legacy")):
            receipt = json.loads(original)
            receipt[field] = val
            # Even a recomputed caller receiptId cannot replace host commitment.
            receipt["receiptId"] = mode.hashlib.sha256(mode.canonical({k: v for k, v in receipt.items() if k != "receiptId"})).hexdigest()
            receipt_path.write_bytes(mode.canonical(receipt))
            with self.subTest(field=field):
                self.assertEqual(self.register_command().returncode, 2)
        receipt_path.write_bytes(original)
        self.assertEqual(self.register_command().returncode, 0)
        for field in ("producerRuntime", "profileId", "targetKey", "executionId"):
            receipt = json.loads(original)
            receipt[field] = "legacy" if field == "producerRuntime" else ("e" * 64 if field == "targetKey" else "foreign")
            receipt_path.write_bytes(mode.canonical(receipt))
            with self.subTest(revalidation=field):
                self.assertEqual(self.cli().returncode, 2)
        receipt_path.write_bytes(original)
        receipt_path.unlink()
        self.assertEqual(self.cli().returncode, 2)

    def test_receipt_commitment_and_artifact_digest_tamper(self):
        self.register()
        path = self.receipt_path()
        original = path.read_bytes()
        for field in ("sha256", "fileInstance"):
            receipt = json.loads(original)
            if field == "sha256":
                receipt["artifact"][field] = "f" * 64
            else:
                receipt["artifact"][field]["inode"] += 1
            path.write_bytes(mode.canonical(receipt))
            with self.subTest(field=field):
                self.assertEqual(self.cli("--write-report").returncode, 2)
                self.assertFalse(self.report_file.exists())
        path.write_bytes(original)
        commit = self.receipt_path(commit=True)
        commit_value = json.loads(commit.read_bytes())
        commit_value["receiptDigest"] = "0" * 64
        commit.write_bytes(mode.canonical(commit_value))
        self.assertEqual(self.cli().returncode, 2)

    def test_file_instance_same_byte_new_inode_same_inode_mutation_metadata(self):
        self.register()
        original = self.v2.read_bytes()
        before = self.v2.stat()
        self.assertEqual(self.run_report()["status"], "equivalent")
        replacement = self.artifacts / "replacement"
        replacement.write_bytes(original)
        replacement.chmod(0o600)
        self.assertNotEqual(replacement.stat().st_ino, before.st_ino)
        os.replace(replacement, self.v2)
        self.assertEqual(self.v2.read_bytes(), original)
        self.assertEqual(self.cli().returncode, 2)
        # Restore the registered instance for isolated same-inode checks on legacy.
        legacy_inode = self.legacy.stat().st_ino
        with self.legacy.open("r+b") as stream:
            stream.write(b"X")
        self.assertEqual(self.legacy.stat().st_ino, legacy_inode)
        with mode.HostRoot(self.project) as root, self.assertRaises(mode.runtime.ContractError):
            mode.producer_source(root, "test", "artifacts/legacy.json", "legacy")

    def test_metadata_only_and_same_inode_same_byte_rewrite_rejected(self):
        self.register()
        for path, operation in ((self.legacy, "mtime"), (self.v2, "rewrite")):
            before = path.stat()
            original = path.read_bytes()
            if operation == "mtime":
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000000))
            else:
                path.write_bytes(original)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(path.stat().st_ino, before.st_ino)
            with mode.HostRoot(self.project) as root, self.assertRaises(mode.runtime.ContractError):
                mode.producer_source(root, "test", "artifacts/" + path.name, "legacy" if path == self.legacy else "v2")

    def test_same_byte_replacement_during_read_fails_closed(self):
        self.register()
        opened, active = 0, False
        def replace(event):
            nonlocal opened, active
            if event == "source-opened":
                opened += 1
                active = opened == 6
            if event == "source-chunk-read" and active:
                active = False
                replacement = self.artifacts / "same-byte-replacement"
                replacement.write_bytes(self.legacy.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, self.legacy)
        mode._TEST_HOOK = replace
        with self.assertRaises(mode.runtime.ContractError):
            self.run_report(write=True)
        self.assertFalse(self.report_file.exists())

    def test_receipt_tamper_during_artifact_read_fails_closed(self):
        self.register()
        opened, active = 0, False
        def tamper(event):
            nonlocal opened, active
            if event == "source-opened":
                opened += 1
                active = opened == 6
            if event == "source-chunk-read" and active:
                active = False
                path = self.receipt_path("artifacts/legacy.json")
                value = json.loads(path.read_bytes())
                value["producerRuntime"] = "v2"
                path.write_bytes(mode.canonical(value))
        mode._TEST_HOOK = tamper
        with self.assertRaises(mode.runtime.ContractError):
            self.run_report(write=True)
        self.assertFalse(self.report_file.exists())

    def test_independently_committed_incoherent_digest_and_instance_rejected(self):
        self.publish_only()
        path = self.receipt_path()
        commit_path = self.receipt_path(commit=True)
        original, committed = path.read_bytes(), commit_path.read_bytes()
        for field in ("sha256", "fileInstance"):
            # TEST ONLY corrupt host fixtures: isolate digest/object verification
            # after a self-consistent receiptId and separate receipt commitment.
            value = json.loads(original)
            if field == "sha256":
                value["artifact"][field] = "0" * 64
            else:
                value["artifact"][field]["inode"] += 1
            value["receiptId"] = mode.hashlib.sha256(mode.canonical({k: v for k, v in value.items() if k != "receiptId"})).hexdigest()
            payload = mode.canonical(value)
            commit = json.loads(committed)
            commit.update(receiptId=value["receiptId"], receiptDigest=mode.hashlib.sha256(payload).hexdigest())
            path.write_bytes(payload)
            commit_path.write_bytes(mode.canonical(commit))
            with self.subTest(field=field):
                result = self.register_command()
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"artifact digest mismatch" if field == "sha256" else b"file instance mismatch", result.stderr)
        path.write_bytes(original)
        commit_path.write_bytes(committed)
        self.assertEqual(self.register_command().returncode, 0)

    def test_host_publication_collisions_private_records_and_path_rebinding(self):
        self.publish_only()
        for artifact, publisher, options in ((self.legacy, mode.publish_legacy_artifact, {}),
                                              (self.v2, mode.publish_v2_artifact, {"execution_version": 1})):
            before = artifact.read_bytes()
            with self.assertRaises(mode.runtime.ContractError):
                publisher(self.project, "test", "fixture-review", "a" * 64,
                          "artifacts/" + artifact.name, b"changed", **options)
            self.assertEqual(artifact.read_bytes(), before)
        path = self.receipt_path()
        for record in (path, self.receipt_path(commit=True)):
            self.assertEqual(stat.S_IMODE(record.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(record.parent.stat().st_mode), 0o700)
        for flag in ("--producer", "--receipt", "--receipt-path"):
            self.assertEqual(self.cli(flag, "legacy").returncode, 2)
            self.assertEqual(self.register_command(**{flag[2:].replace("-", "_"): "legacy"}).returncode, 2)
        moved = self.base / "moved-publication"
        def rebind(event):
            if event == "artifact-after-publication":
                self.artifacts.rename(moved)
                self.artifacts.mkdir(mode=0o700)
        mode._TEST_HOOK = rebind
        with self.assertRaises(mode.runtime.ContractError):
            mode.publish_legacy_artifact(self.project, "other-execution", "fixture-review", "a" * 64,
                                         "artifacts/new.json", b"local fixture")
        self.assertEqual(list(self.artifacts.iterdir()), [])
        self.assertFalse((moved / "new.json").exists())
        self.no_staging()

    def test_pristine_equivalence_is_scoped_and_never_authority(self):
        self.register()
        before = self.snapshot()
        report = self.run_report()
        self.assertEqual(report["status"], "equivalent")
        self.assertTrue(report["complete"])
        self.assertTrue(report["byteIdentical"])
        self.assertFalse(report["representationOnly"])
        self.assertEqual(report["authority"], "none")
        self.assertEqual(report["permissionGrant"], "none")
        self.assertEqual(report["externalActions"], "disabled")
        self.assertEqual(report["executedRuntimes"], [])
        self.assertTrue(report["humanReviewRequired"])
        self.assertEqual(report["nonDegradation"], "not-established")
        self.assertEqual(before, self.snapshot())
        self.assertEqual([item["name"] for item in report["dimensions"]], sorted(comp.DIMENSIONS))

    def test_text_format_order_and_provider_local_ids_are_inert(self):
        for name, section in self.right["dimensions"].items():
            for record in section["records"]:
                record["label"] = "PROMPT RESPONSE REASONING CREDENTIAL RAW TRACE SOURCE BODY FULL DIFF RAW EVIDENCE"
                record["evidenceRefs"] = ["provider-evidence" if ref == "E1" else ref for ref in record["evidenceRefs"]]
            section["records"].reverse()
        self.right["dimensions"]["evidenceReferences"]["records"][0]["key"] = "provider-evidence"
        self.right["dimensions"]["blockers"]["records"][0]["key"] = "provider-blocker"
        self.right["dimensions"]["warnings"]["records"][0]["key"] = "provider-warning"
        self.register(right=json.dumps(self.right, indent=4, sort_keys=False).encode())
        report = self.run_report()
        self.assertEqual(report["status"], "equivalent")
        self.assertTrue(report["representationOnly"])
        encoded = mode.canonical(report)
        for marker in (b"PROMPT", b"RESPONSE", b"REASONING", b"CREDENTIAL", b"RAW TRACE", b"SOURCE BODY", b"FULL DIFF", b"RAW EVIDENCE", b"label"):
            self.assertNotIn(marker, encoded)
        item = self.dimension(report, "blockers")["records"][0]
        self.assertEqual(item["v2"]["recordId"], "provider-blocker")
        self.assertEqual(item["v2"]["evidenceRefs"], ["provider-evidence"])
        self.assertEqual(item["v2"]["evidence"][0]["metadata"]["sourceKey"], "source-payments")

    def test_curated_semantic_regression_corpus(self):
        for index, case in enumerate(CORPUS):
            with self.subTest(case=case["name"]):
                right = copy.deepcopy(BASELINE)
                record = right["dimensions"][case["dimension"]]["records"][0]
                if case["field"] == "value":
                    record["value"] = case["value"]
                else:
                    record["value"][case["field"]] = case["value"]
                self.register(execution_id=f"corpus-{index}", right=right)
                report = self.run_report(execution_id=f"corpus-{index}")
                self.assertEqual(report["status"], case["expected"])
                self.assertEqual(self.dimension(report, case["dimension"])["status"], "different")
                self.assertFalse(report["representationOnly"])

    def test_array_order_and_declared_sets_preserve_semantics_and_real_pointers(self):
        extra_evidence = copy.deepcopy(self.left["dimensions"]["evidenceReferences"]["records"][0])
        extra_evidence["key"] = "E2"
        extra_evidence["value"]["sourceKey"] = "source-tests"
        extra_finding = copy.deepcopy(self.left["dimensions"]["blockers"]["records"][0])
        extra_finding["key"] = "second-blocker"
        extra_finding["value"]["predicate"] = "write-not-approved"
        self.left["dimensions"]["blockers"]["records"].append(extra_finding)
        self.left["dimensions"]["evidenceReferences"]["records"].append(extra_evidence)
        for record in self.left["dimensions"]["blockers"]["records"]:
            record["evidenceRefs"] = ["E1", "E2"]
        self.right = copy.deepcopy(self.left)
        for section in self.right["dimensions"].values():
            section["records"].reverse()
            for record in section["records"]:
                record["evidenceRefs"].reverse()
        self.register()
        report = self.run_report()
        self.assertEqual(report["status"], "equivalent")
        records = self.dimension(report, "blockers")["records"]
        self.assertEqual([item["semanticKey"] for item in records], sorted(item["semanticKey"] for item in records))
        for item in records:
            self.assertNotEqual(item["legacy"]["pointer"], item["v2"]["pointer"])
            for side, source in (("legacy", self.left), ("v2", self.right)):
                index = int(item[side]["pointer"].split("/")[-1])
                self.assertEqual(source["dimensions"]["blockers"]["records"][index]["key"], item[side]["recordId"])

    def test_known_blocker_removal_is_only_an_actual_one_sided_observation(self):
        self.right["dimensions"]["blockers"]["records"] = []
        self.register()
        report = self.run_report()
        blockers = self.dimension(report, "blockers")
        self.assertEqual(blockers["status"], "different")
        self.assertEqual(len(blockers["records"]), 1)
        self.assertIsNone(blockers["records"][0]["v2"])
        self.assertEqual(blockers["records"][0]["legacy"]["recordId"], "legacy-blocker-1")
        self.assertEqual(blockers["records"][0]["reasons"], ["one-sided-observation"])
        self.assertNotIn(b"missed", mode.canonical(report))
        self.assertNotIn(b"invented", mode.canonical(report))

    def test_partial_collection_does_not_prove_missing_finding(self):
        self.right["dimensions"]["blockers"].update(coverage="partial", records=[])
        self.register()
        report = self.run_report()
        self.assertEqual(report["status"], "indeterminate")
        self.assertEqual(self.dimension(report, "blockers")["records"][0]["status"], "indeterminate")

    def test_partial_matched_records_do_not_claim_equivalence_but_keep_known_changes(self):
        self.right["dimensions"]["blockers"]["coverage"] = "partial"
        self.register(execution_id="partial-match")
        report = self.run_report(execution_id="partial-match")
        self.assertEqual(report["status"], "indeterminate")
        self.assertEqual(self.dimension(report, "blockers")["records"][0]["status"], "indeterminate")
        self.right["dimensions"]["blockers"]["records"][0]["value"]["stance"] = "denied"
        self.register(execution_id="partial-change")
        report = self.run_report(execution_id="partial-change")
        self.assertEqual(report["status"], "different")
        self.assertFalse(report["complete"])
        self.assertEqual(self.dimension(report, "blockers")["records"][0]["status"], "different")

    def test_added_observations_are_not_synthesized(self):
        new = copy.deepcopy(self.right["dimensions"]["blockers"]["records"][0])
        new["key"] = "new-real-record"
        new["value"]["predicate"] = "write-not-approved"
        self.right["dimensions"]["blockers"]["records"].append(new)
        self.register()
        records = self.dimension(self.run_report(), "blockers")["records"]
        one_sided = [item for item in records if item["legacy"] is None]
        self.assertEqual(len(one_sided), 1)
        self.assertEqual(one_sided[0]["v2"]["recordId"], "new-real-record")

    def test_same_missing_dimensions_empty_input_and_unknown_are_never_equivalent(self):
        variants = []
        empty = copy.deepcopy(BASELINE)
        empty["dimensions"] = {}
        variants.append(empty)
        missing = copy.deepcopy(BASELINE)
        del missing["dimensions"]["approvalGates"]
        variants.append(missing)
        unknown = copy.deepcopy(BASELINE)
        unknown["dimensions"]["status"]["records"][0]["value"] = "unknown"
        variants.append(unknown)
        no_artifact = copy.deepcopy(BASELINE)
        no_artifact["dimensions"]["artifactCompleteness"]["records"] = []
        variants.append(no_artifact)
        for index, value in enumerate(variants):
            self.register(execution_id=f"missing-{index}", left=value, right=value)
            report = self.run_report(execution_id=f"missing-{index}")
            self.assertEqual(report["status"], "indeterminate")
            self.assertTrue(report["byteIdentical"])
            self.assertFalse(report["complete"])

    def test_uncertainty_gaps_and_declared_provenance_are_preserved(self):
        for value in (self.left, self.right):
            value["dimensions"]["blockers"]["records"][0]["uncertainty"] = ["unverified", "contradictory-evidence"]
            value["dimensions"]["requirementCoverage"]["gaps"] = ["scope-incomplete"]
        self.register()
        report = self.run_report()
        self.assertEqual(report["status"], "indeterminate")
        record = self.dimension(report, "blockers")["records"][0]
        self.assertEqual(record["legacy"]["uncertainty"], ["contradictory-evidence", "unverified"])
        self.assertEqual(record["legacy"]["pointer"], "/dimensions/blockers/records/0")
        self.assertEqual(record["legacy"]["evidence"][0]["pointer"], "/dimensions/evidenceReferences/records/0")
        self.assertEqual(self.dimension(report, "requirementCoverage")["gaps"]["v2"], ["scope-incomplete"])

    def test_unusable_or_unregistered_evidence_never_proves_equivalence(self):
        for index, change in enumerate(("sha256", "revision", "collectionStatus", "dangling", "none")):
            value = copy.deepcopy(BASELINE)
            if change in {"sha256", "revision"}:
                value["dimensions"]["evidenceReferences"]["records"][0]["value"][change] = None
            elif change == "collectionStatus":
                value["dimensions"]["evidenceReferences"]["records"][0]["value"][change] = "partial"
            else:
                value["dimensions"]["blockers"]["records"][0]["evidenceRefs"] = ["UNREGISTERED"] if change == "dangling" else []
            self.register(execution_id=f"evidence-{index}", left=value, right=value)
            self.assertEqual(self.run_report(execution_id=f"evidence-{index}")["status"], "indeterminate")

    def test_open_questions_missing_artifact_and_unavailable_escalation(self):
        variants = []
        question = copy.deepcopy(BASELINE)
        question["dimensions"]["unresolvedQuestions"]["records"] = [{"key": "Q1", "value": {
            "subject": {"domain": "application", "kind": "component", "identifier": "payments"},
            "predicate": "owner-known", "state": "open", "requiredEvidence": ["source-owner"]},
            "evidenceRefs": [], "uncertainty": []}]
        variants.append(question)
        incomplete = copy.deepcopy(BASELINE)
        incomplete["dimensions"]["artifactCompleteness"]["records"][0]["value"]["state"] = "missing"
        variants.append(incomplete)
        escalation = copy.deepcopy(BASELINE)
        escalation["dimensions"]["highRiskEscalation"]["records"][0]["value"]["status"] = "unavailable"
        variants.append(escalation)
        for index, value in enumerate(variants):
            self.register(execution_id=f"unresolved-{index}", left=value, right=value)
            self.assertEqual(self.run_report(execution_id=f"unresolved-{index}")["status"], "indeterminate")

    def test_human_usefulness_where_available_is_compared_not_inferred(self):
        for value, disposition in ((self.left, "useful"), (self.right, "not-useful")):
            value["dimensions"]["humanUsefulnessDisposition"] = {"coverage": "complete", "gaps": [], "records": [
                {"key": "humanUsefulnessDisposition", "value": disposition, "evidenceRefs": [], "uncertainty": []}]}
        self.register()
        self.assertEqual(self.run_report()["status"], "different")

    def test_identity_tokens_are_opaque_not_textual_uncertainty_inference(self):
        for value in (self.left, self.right):
            finding = value["dimensions"]["blockers"]["records"][0]["value"]
            finding["subject"]["identifier"] = "unknown"
            finding["predicate"] = "uncertain"
        self.register()
        self.assertEqual(self.run_report()["status"], "equivalent")

    def test_profile_or_target_mismatch_is_indeterminate_not_cross_run_matching(self):
        for index, field in enumerate(("profileId", "targetKey")):
            right = copy.deepcopy(BASELINE)
            right[field] = "other-profile" if field == "profileId" else "c" * 64
            right["dimensions"]["status"]["records"][0]["value"] = "pass"
            self.register(execution_id=f"target-{index}", right=right)
            self.assertEqual(self.run_report(execution_id=f"target-{index}")["status"], "indeterminate")

    def test_identical_foreign_native_headers_are_bound_to_host_receipts(self):
        for index, fields in enumerate((("profileId",), ("targetKey",), ("profileId", "targetKey"))):
            with self.subTest(fields=fields):
                value = copy.deepcopy(BASELINE)
                for field in fields:
                    value[field] = "other-profile" if field == "profileId" else "c" * 64
                execution = f"foreign-headers-{index}"
                self.register(execution_id=execution, left=value, right=value)
                payload = comp.run(str(self.project), execution)
                report = json.loads(payload)
                self.assertEqual(report["status"], "indeterminate")
                self.assertFalse(report["complete"])
                self.assertTrue(report["byteIdentical"])
                self.assertFalse(report["representationOnly"])
                self.assertEqual(report["reasons"], sorted(
                    "profile-mismatch" if field == "profileId" else "target-mismatch" for field in fields))
                self.assertEqual(payload, comp.run(str(self.project), execution))
                for side in ("legacy", "v2"):
                    self.assertEqual(report["sources"][side]["profileId"], BASELINE["profileId"])
                    self.assertEqual(report["sources"][side]["targetKey"], BASELINE["targetKey"])

    def test_native_header_binding_checks_each_side_with_unsupported_counterpart(self):
        for side in ("legacy", "v2"):
            for field, reason in (("profileId", "profile-mismatch"), ("targetKey", "target-mismatch")):
                with self.subTest(side=side, field=field):
                    value = copy.deepcopy(BASELINE)
                    value[field] = "other-profile" if field == "profileId" else "c" * 64
                    execution = f"foreign-{side}-{field.lower()}"
                    pair = (value, b"# Unsupported report\n") if side == "legacy" else (b"# Unsupported report\n", value)
                    self.register(execution_id=execution, left=pair[0], right=pair[1])
                    report = self.run_report(execution_id=execution)
                    self.assertEqual(report["status"], "indeterminate")
                    self.assertFalse(report["complete"])
                    self.assertIn(reason, report["reasons"])

    def test_foreign_native_header_prevents_known_difference_and_accepts_valid_control(self):
        self.register(execution_id="header-control")
        payload = comp.run(str(self.project), "header-control")
        report = json.loads(payload)
        self.assertEqual(report["status"], "equivalent")
        self.assertTrue(report["complete"])
        self.assertEqual(report["reasons"], [])
        self.assertEqual(payload, comp.run(str(self.project), "header-control"))
        for side in ("legacy", "v2"):
            with self.subTest(side=side):
                left, right = copy.deepcopy(BASELINE), copy.deepcopy(BASELINE)
                (left if side == "legacy" else right)["profileId"] = "other-profile"
                right["dimensions"]["status"]["records"][0]["value"] = "pass"
                execution = f"foreign-difference-{side}"
                self.register(execution_id=execution, left=left, right=right)
                report = self.run_report(execution_id=execution)
                self.assertEqual(report["status"], "indeterminate")
                self.assertFalse(report["complete"])
                self.assertIn("profile-mismatch", report["reasons"])

    def test_unsupported_identical_markdown_binary_and_native_phase_output(self):
        for index, value in enumerate((b"# Clean report\nNo blockers\n", b"\x00\xff\x80", b'{"schemaVersion":"mana.context-runtime.phase-checkpoint/v1"}')):
            self.register(execution_id=f"unsupported-{index}", left=value, right=value)
            report = self.run_report(execution_id=f"unsupported-{index}")
            self.assertEqual(report["status"], "indeterminate")
            self.assertTrue(report["byteIdentical"])
            self.assertFalse(report["representationOnly"])

    def test_invalid_closed_native_contracts_and_ambiguous_identities_fail_closed(self):
        invalid = []
        extra = copy.deepcopy(BASELINE)
        extra["PROMPT_SECRET"] = "DO_NOT_LEAK"
        invalid.append(extra)
        duplicate = copy.deepcopy(BASELINE)
        duplicate["dimensions"]["blockers"]["records"].append(copy.deepcopy(duplicate["dimensions"]["blockers"]["records"][0]))
        invalid.append(duplicate)
        duplicate_atom = copy.deepcopy(duplicate)
        duplicate_atom["dimensions"]["blockers"]["records"][1]["key"] = "alias"
        invalid.append(duplicate_atom)
        wrong = copy.deepcopy(BASELINE)
        wrong["dimensions"]["blockers"]["records"][0]["value"]["severity"] = "magic"
        invalid.append(wrong)
        invalid.append(b'{"schemaVersion":"' + comp.INPUT_VERSION.encode() + b'","dimensions":{},"dimensions":{}}')
        invalid.append(b'{"schemaVersion":"' + comp.INPUT_VERSION.encode() + b'","number":NaN}')
        invalid.append(b'{"schemaVersion":"' + comp.INPUT_VERSION.encode() + b'",')
        bad_na = copy.deepcopy(BASELINE)
        bad_na["dimensions"]["blockers"].update(coverage="not-applicable", records=[])
        invalid.append(bad_na)
        for index, value in enumerate(invalid):
            self.register(execution_id=f"invalid-{index}", right=value)
            before = self.snapshot()
            with self.assertRaises((comp.runtime.ContractError, ValueError)):
                self.run_report(write=True, execution_id=f"invalid-{index}")
            self.assertEqual(before, self.snapshot())
            self.no_staging()

    def test_source_digest_mismatch_rejects_without_mutation_or_body_leak(self):
        self.register()
        self.v2.write_bytes(b"PROMPT_SECRET_DO_NOT_LEAK")
        before = self.snapshot()
        result = self.cli("--write-report")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertNotIn(b"PROMPT_SECRET", result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_requires_existing_compare_registration_not_shadow_or_unregistered_paths(self):
        self.assertEqual(self.cli().returncode, 2)
        self.register()
        plan = json.loads(self.plan.read_bytes())
        plan["mode"] = "shadow"
        self.plan.write_bytes(mode.canonical(plan))
        self.assertEqual(self.cli().returncode, 2)
        for option in ("--legacy-artifact", "--provider", "--output", "--context-runtime"):
            self.assertEqual(self.cli(option, "anything").returncode, 2)

    def test_mode_plan_closed_canonical_and_path_validation(self):
        self.register()
        original = json.loads(self.plan.read_bytes())
        for path in ("/private/tmp/outside", "../outside", "artifacts/../v2.json", "artifacts//v2.json", "artifacts\\v2.json"):
            value = copy.deepcopy(original)
            value["artifacts"]["v2"]["path"] = path
            self.plan.write_bytes(mode.canonical(value))
            self.assertEqual(self.cli("--write-report").returncode, 2)
        self.plan.write_bytes(json.dumps(original, indent=2).encode())
        self.assertEqual(self.cli().returncode, 2)
        original["permissionGrant"] = "external-write"
        self.plan.write_bytes(mode.canonical(original))
        self.assertEqual(self.cli().returncode, 2)
        self.no_staging()

    def test_source_final_intermediate_and_root_ancestry_symlinks_rejected(self):
        self.register()
        moved = self.base / "moved-source.json"
        self.v2.rename(moved)
        self.v2.symlink_to(moved)
        self.assertEqual(self.cli().returncode, 2)
        self.v2.unlink()
        moved.rename(self.v2)
        moved_dir = self.base / "moved-artifacts"
        self.artifacts.rename(moved_dir)
        self.artifacts.symlink_to(moved_dir, target_is_directory=True)
        self.assertEqual(self.cli().returncode, 2)
        self.artifacts.unlink()
        moved_dir.rename(self.artifacts)
        alias = self.base / "alias"
        alias.symlink_to(self.project, target_is_directory=True)
        self.assertEqual(self.cli(root=alias).returncode, 2)
        parent_alias = self.base / "parent-alias"
        parent_alias.symlink_to(self.base, target_is_directory=True)
        self.assertEqual(self.cli(root=parent_alias / self.project.name).returncode, 2)

    def test_plan_symlink_hardlink_special_file_and_private_permissions(self):
        self.register()
        original = self.plan.read_bytes()
        self.plan.chmod(0o644)
        self.assertEqual(self.cli().returncode, 2)
        self.plan.chmod(0o600)
        self.folder.chmod(0o755)
        self.assertEqual(self.cli().returncode, 2)
        self.folder.chmod(0o700)
        moved = self.base / "plan"
        self.plan.rename(moved)
        self.plan.symlink_to(moved)
        self.assertEqual(self.cli().returncode, 2)
        self.plan.unlink()
        os.link(moved, self.plan)
        self.assertEqual(self.cli().returncode, 2)
        self.plan.unlink()
        os.mkfifo(self.plan, 0o600)
        self.assertEqual(self.cli().returncode, 2)
        self.plan.unlink()
        self.plan.write_bytes(original)
        self.plan.chmod(0o600)
        self.v2.unlink()
        os.mkfifo(self.v2, 0o600)
        self.assertEqual(self.cli().returncode, 2)

    def test_read_hash_parse_same_bytes_and_detect_midread_mutation(self):
        self.register()
        opened, active = 0, False
        def fault(event):
            nonlocal opened, active
            if event == "source-opened":
                opened += 1
                active = opened == 6  # schemas, registration, receipt, commit, artifact
            if event == "source-chunk-read" and active:
                active = False
                self.legacy.write_bytes(mode.canonical(self.right) + b" ")
        mode._TEST_HOOK = fault
        with self.assertRaises(comp.runtime.ContractError):
            self.run_report(write=True)
        self.assertFalse(self.report_file.exists())
        self.no_staging()

    def test_read_source_rebinding_detected(self):
        self.register()
        opened = 0
        def fault(event):
            nonlocal opened
            if event == "source-opened":
                opened += 1
                if opened == 6:
                    self.legacy.rename(self.artifacts / "old.json")
                    self.legacy.write_bytes(mode.canonical(BASELINE))
        mode._TEST_HOOK = fault
        with self.assertRaises(comp.runtime.ContractError):
            self.run_report(write=True)
        self.no_staging()

    def test_registration_and_source_parent_rebinding_detected(self):
        self.register()
        opened = 0
        def plan_fault(event):
            nonlocal opened
            if event == "source-opened":
                opened += 1
                if opened == 3:
                    payload = self.plan.read_bytes()
                    self.plan.rename(self.folder / "old-plan.json")
                    self.plan.write_bytes(payload)
                    self.plan.chmod(0o600)
        mode._TEST_HOOK = plan_fault
        with self.assertRaises(comp.runtime.ContractError):
            self.run_report(write=True)
        opened = 0
        def parent_fault(event):
            nonlocal opened
            if event == "source-opened":
                opened += 1
                if opened == 6:
                    self.artifacts.rename(self.base / "old-artifacts")
                    self.artifacts.mkdir()
        mode._TEST_HOOK = parent_fault
        with self.assertRaises(comp.runtime.ContractError):
            self.run_report(write=True)
        self.assertFalse(self.report_file.exists())
        self.no_staging()

    def test_source_and_installed_schema_hardlinks_symlinks_and_refs_fail_closed(self):
        self.register()
        os.link(self.legacy, self.artifacts / "linked-source")
        self.assertEqual(self.cli().returncode, 2)
        (self.artifacts / "linked-source").unlink()
        installed = self.base / "installed-fixture"
        contracts = installed / "contracts/context-runtime"
        contracts.mkdir(parents=True)
        for name in (comp.INPUT_SCHEMA, comp.REPORT_SCHEMA):
            (contracts / name).write_bytes((REPO / "contracts/context-runtime" / name).read_bytes())
        schema = contracts / comp.INPUT_SCHEMA
        saved = self.base / "saved-schema.json"
        schema.rename(saved)
        schema.symlink_to(saved)
        with mock.patch.object(comp, "REPO", installed):
            with self.assertRaises(OSError):
                self.run_report(write=True)
        schema.unlink()
        os.link(saved, schema)
        with mock.patch.object(comp, "REPO", installed):
            with self.assertRaises(comp.runtime.ContractError):
                self.run_report(write=True)
        schema.unlink()
        saved.rename(schema)
        with mock.patch.object(comp, "REPO", installed):
            validator = comp.Contracts()
            with self.assertRaises(comp.runtime.ContractError):
                validator.resolve_ref("../../outside.json", schema)
        self.no_staging()

    def test_root_rebinding_during_source_read_rejected(self):
        self.register()
        opened = 0
        previous = self.project
        moved = self.base / "moved-project"
        def fault(event):
            nonlocal opened
            if event == "source-opened":
                opened += 1
                if opened == 6:
                    previous.rename(moved)
                    previous.mkdir()
        mode._TEST_HOOK = fault
        with self.assertRaises(comp.runtime.ContractError):
            self.run_report(write=True)
        self.assertEqual(list(previous.iterdir()), [])
        self.assertFalse((moved / mode.NAMESPACE / "test" / comp.REPORT_FILE).exists())
        self.no_staging()

    def test_byte_limits_reject_before_output(self):
        self.register(right=b"x" * (comp.MAX_INPUT + 1))
        self.assertEqual(self.cli("--write-report").returncode, 2)
        self.assertFalse(self.report_file.exists())
        self.no_staging()

    def test_default_has_no_writes_and_cli_never_calls_a_runtime(self):
        self.register()
        before = self.snapshot()
        with mock.patch.object(mode, "shadow_legacy", side_effect=AssertionError("runtime execution")), \
                mock.patch.object(mode.subprocess, "call", side_effect=AssertionError("provider call")), \
                mock.patch.object(mode.subprocess, "run", side_effect=AssertionError("external command")):
            report = self.run_report()
        self.assertEqual(report["status"], "equivalent")
        self.assertEqual(before, self.snapshot())
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, mode.canonical(report))
        self.assertEqual(before, self.snapshot())

    def test_canonical_byte_identity_across_repeats_and_project_roots(self):
        self.register()
        first = comp.run(str(self.project), "test")
        self.assertEqual(first, comp.run(str(self.project), "test"))
        self.assertEqual(first, mode.canonical(json.loads(first)))
        self.assertNotIn(b"timestamp", first)
        previous = self.project
        alternate = self.base / "alternate"
        previous.rename(alternate)
        self.assertEqual(first, comp.run(str(alternate), "test"))
        alternate.rename(previous)

    def test_input_and_report_production_offline_schema_parity(self):
        self.register()
        report = self.run_report()
        evaluator = offline.SchemaEvaluator()
        for name, value in ((comp.INPUT_SCHEMA, BASELINE), (comp.REPORT_SCHEMA, report)):
            path = REPO / "contracts/context-runtime" / name
            self.assertEqual(evaluator.evaluate(value, evaluator.load(path), path), [])
            bad = copy.deepcopy(value)
            bad["unknownField"] = "rejected"
            self.assertTrue(evaluator.evaluate(bad, evaluator.load(path), path))
            with self.assertRaises(comp.runtime.ContractError):
                comp.Contracts().validate(bad, name)

    def test_atomic_local_report_permissions_and_unchanged_sources(self):
        self.register()
        before = self.snapshot()
        result = self.cli("--write-report")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, self.report_file.read_bytes())
        self.assertEqual(stat.S_IMODE(self.report_file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.folder.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.folder.parent.stat().st_mode), 0o700)
        after = self.snapshot()
        del after[str(self.report_file.relative_to(self.project))]
        self.assertEqual(before, after)
        self.no_staging()
        self.assertEqual(self.cli("--write-report").returncode, 2)
        self.assertEqual(self.cli().returncode, 0)  # reading diagnostic never overwrites it

    def test_report_file_directory_symlink_and_fifo_collisions_preserved(self):
        self.register()
        self.report_file.write_bytes(b"host-owned-collision")
        self.assertEqual(self.cli("--write-report").returncode, 2)
        self.assertEqual(self.report_file.read_bytes(), b"host-owned-collision")
        self.report_file.unlink()
        self.report_file.mkdir()
        self.assertEqual(self.cli("--write-report").returncode, 2)
        self.report_file.rmdir()
        outside = self.base / "outside"
        outside.write_bytes(b"unchanged")
        self.report_file.symlink_to(outside)
        self.assertEqual(self.cli("--write-report").returncode, 2)
        self.assertEqual(outside.read_bytes(), b"unchanged")
        self.report_file.unlink()
        os.mkfifo(self.report_file, 0o600)
        self.assertEqual(self.cli("--write-report").returncode, 2)
        self.no_staging()

    def test_publication_faults_cleanup_and_rollback(self):
        self.register()
        before = self.snapshot()
        for point in ("before-stage-write", "before-publication", "after-publication", "before-commit"):
            def fault(event):
                if event == point:
                    raise OSError("injected local failure")
            comp._TEST_HOOK = fault
            with self.assertRaises(OSError):
                self.run_report(write=True)
            self.assertEqual(before, self.snapshot())
            self.no_staging()

    def test_stage_byte_and_permission_tampering_rejected(self):
        self.register()
        for kind in ("bytes", "permissions"):
            def fault(event):
                if event == "before-publication":
                    stage = next(self.folder.glob(".semantic-comparison.stage.*"))
                    if kind == "bytes":
                        stage.write_bytes(b"tampered")
                    else:
                        stage.chmod(0o644)
            comp._TEST_HOOK = fault
            with self.assertRaises(comp.runtime.ContractError):
                self.run_report(write=True)
            self.assertFalse(self.report_file.exists())
            self.no_staging()

    def test_parent_rebinding_during_publication_keeps_cleanup_fd_relative(self):
        self.register()
        moved = self.base / "moved-registration"
        def fault(event):
            if event == "after-publication":
                self.folder.rename(moved)
                self.folder.mkdir(mode=0o700)
        comp._TEST_HOOK = fault
        with self.assertRaises(comp.runtime.ContractError):
            self.run_report(write=True)
        self.assertEqual(list(self.folder.iterdir()), [])
        self.assertEqual([path.name for path in moved.iterdir()], ["mode-plan-v1.json"])
        self.no_staging()

    def test_handled_signal_cleans_publication(self):
        self.register()
        for number in (signal.SIGTERM, signal.SIGINT):
            def fault(event):
                if event == "after-publication":
                    os.kill(os.getpid(), number)
            comp._TEST_HOOK = fault
            with self.assertRaises(OSError):
                self.run_report(write=True)
            self.assertFalse(self.report_file.exists())
            self.no_staging()

    def test_short_write_and_unsupported_atomic_primitive_fail_closed(self):
        self.register()
        with mock.patch.object(comp.os, "write", return_value=0):
            with self.assertRaises(OSError):
                self.run_report(write=True)
        with mock.patch.object(comp.runtime, "_require_rename_primitives", side_effect=comp.runtime.ContractError("unsupported")):
            with self.assertRaises(comp.runtime.ContractError):
                self.run_report(write=True)
        self.no_staging()
        self.assertFalse(self.report_file.exists())

    def test_fsync_failure_and_restrictive_umask_cleanup_or_private_publication(self):
        self.register()
        with mock.patch.object(comp.os, "fsync", side_effect=OSError("fsync failure")):
            with self.assertRaises(OSError):
                self.run_report(write=True)
        self.no_staging()
        self.assertFalse(self.report_file.exists())
        previous = os.umask(0o777)
        try:
            self.run_report(write=True)
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(self.report_file.stat().st_mode), 0o600)
        self.no_staging()

    def test_concurrent_publication_one_winner_and_no_overwrite(self):
        self.register()
        command = [str(REPO / "scripts/mana-context-compare.sh"), "test", "--project-root", str(self.project), "--write-report"]
        processes = [subprocess.Popen(command, env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
        results = [(process.communicate(), process.returncode) for process in processes]
        self.assertEqual(sorted(status for _, status in results), [0, 2, 2, 2])
        winner = next(output[0] for output, status in results if status == 0)
        self.assertEqual(winner, self.report_file.read_bytes())
        self.no_staging()


if __name__ == "__main__":
    unittest.main(verbosity=2)
