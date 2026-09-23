#!/usr/bin/env python3
"""R2A real CTX-06 consumer/publication/comparison and kernel read canaries."""
import copy
import importlib.util
import json
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("r2a_live", REPO / "scripts/context-runtime-live-shadow.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)
consumer, shared = live.consumer, live.shared
FRAMEWORK = REPO / "tests/fixtures/context-runtime/ctx06a-framework"
test_backend = importlib.util.module_from_spec(importlib.util.spec_from_file_location("r2a_test_backend", REPO / "tests/context-shadow-backend-test-harness.py"))
test_backend.__spec__.loader.exec_module(test_backend)
FIXTURES = REPO / "tests/fixtures/context-runtime"
BASELINE = json.loads((FIXTURES / "comparison/baseline.json").read_bytes())


class R2A(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp" if sys.platform == "darwin" else "/tmp")
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir(mode=0o700)
        self.workspace = ".mana/sessions/ctx09c-test-workspace"
        workspace = self.project / self.workspace
        workspace.mkdir(mode=0o700, parents=True)
        (self.project / ".mana").chmod(0o700)
        (self.project / ".mana/sessions").chmod(0o700)
        (workspace / "manifest.yaml").write_text(
            'workspace_type: "session"\nworkspace_id: "ctx09c-test-workspace"\n')
        self.bin = self.base / "bin"
        self.bin.mkdir()
        (self.bin / "codex").symlink_to(FIXTURES / "ctx06c-provider-stub.sh")
        self.env = mock.patch.dict(os.environ, {"PATH": str(self.bin) + ":" + os.environ["PATH"],
            "CTX06C_FIXTURE_ROOT": str(FIXTURES), "CTX06C_STATE_DIR": str(self.project / "provider-state"),
            "MANA_UPDATE_CHECK": "off", "PYTHONDONTWRITEBYTECODE": "1"})
        self.env.start()
        profile, execution = "ctx06c-fixture", "execution-r2a"
        self.inputs = {"legacyPrompt": "LOCAL", "legacyArgv": ["exec"], "economyModel": "fixture-economy",
            "fullModel": "fixture-full", "objective": "LOCAL", "pipelineSnapshot": consumer.snapshot(profile, FRAMEWORK)}
        manifest = shared.runtime.compile_context_manifest(FRAMEWORK, profile, execution)
        self.payload = shared.materialize(execution, profile, {}, shared.canonical(self.inputs), manifest, "codex",
                                          project_root=self.project, workspace=self.workspace)
        self.packet = shared.validate(self.payload)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def run_v2(self, typed=True):
        source = copy.deepcopy(BASELINE)
        source["profileId"] = self.packet["profileId"]
        source["targetKey"] = shared.digest(shared.canonical(self.packet["target"]))
        source["dimensions"]["externalWritePolicy"]["records"][0]["value"] = {
            "repositoryWrite": False, "externalWrite": False, "approvedActionKeys": []}
        if typed:
            projection = self.project / "typed-input.json"
            projection.write_bytes(shared.canonical(source))
            os.environ["CTX09C_R2A_PROJECTION_PATH"] = str(projection)
        status, output, _ = consumer.consume(self.payload, "v2", self.project, framework_root=FRAMEWORK)
        self.assertEqual(status, 0)
        return json.loads(output), source

    def compare(self, left, right, execution):
        root = self.project
        identity = self.packet["identity"]
        left_ref, right_ref = f"artifacts/{execution}-legacy.json", f"artifacts/{execution}-v2.json"
        live.mode.publish_legacy_artifact(str(root), execution, self.packet["profileId"],
            right["targetKey"], left_ref, shared.canonical(left))
        receipt = live.mode.publish_v2_artifact(str(root), execution, self.packet["profileId"],
            right["targetKey"], right_ref, shared.canonical(right), execution_version=1)
        registered = subprocess.run([sys.executable, str(REPO / "scripts/context-runtime-mode.py"), "compare",
            "--project-root", str(root), "--execution-id", execution, "--profile-id", self.packet["profileId"],
            "--target-key", right["targetKey"], "--legacy-artifact", left_ref, "--v2-artifact", right_ref], capture_output=True)
        self.assertEqual(registered.returncode, 0, registered.stderr)
        return json.loads(live.comparison.run(str(root), execution)), receipt

    def test_real_consumer_committed_projection_receipt_all_comparison_outcomes(self):
        right, left = self.run_v2()
        self.assertEqual(right["dimensions"], left["dimensions"])
        self.assertEqual(right["provenance"]["authority"], "none")
        self.assertEqual(len(right["provenance"]["artifacts"]), 12)
        report, receipt = self.compare(left, right, "equivalent")
        self.assertEqual(report["status"], "equivalent")
        changed = copy.deepcopy(left)
        changed["dimensions"]["status"]["records"][0]["value"] = "fail"
        report, _ = self.compare(changed, right, "different")
        self.assertEqual(report["status"], "different")
        unknown = copy.deepcopy(right)
        unknown["dimensions"]["status"]["records"][0]["uncertainty"] = ["missing-evidence"]
        report, _ = self.compare(left, unknown, "indeterminate")
        self.assertEqual(report["status"], "indeterminate")

    def test_untyped_final_is_structured_unknown_never_equivalent(self):
        right, _ = self.run_v2(typed=False)
        report, _ = self.compare(right, right, "unknown")
        self.assertEqual(report["status"], "indeterminate")
        self.assertEqual(right["dimensions"]["status"]["coverage"], "unavailable")

    def test_head_only_orphans_incomplete_foreign_and_tamper_fail_closed(self):
        self.run_v2()
        run = self.project / consumer.pipeline.relative_run_directory(self.packet["identity"]["shadowProducerId"])
        orphan = run / "transitions" / "ignored-orphan"
        orphan.mkdir()
        (orphan / "checkpoint-v1.json").write_text("RAW_PROVIDER_CANARY")
        consumer.project_completed(self.project, FRAMEWORK, self.packet, self.inputs)
        head = run / "run-state-v1.json"
        original = head.read_bytes()
        for field, value in (("status", "active"), ("executionId", "execution-foreign"), ("revision", 999)):
            state = json.loads(original)
            state[field] = value
            head.write_bytes(shared.canonical(state))
            with self.assertRaises((consumer.shared.Error, consumer.pipeline.runtime.ContractError)):
                consumer.project_completed(self.project, FRAMEWORK, self.packet, self.inputs)
        head.write_bytes(original)

    def test_earlier_uncertainty_is_not_erased_by_final_checkpoint(self):
        earlier = copy.deepcopy(BASELINE)
        earlier["profileId"] = self.packet["profileId"]
        earlier["targetKey"] = shared.digest(shared.canonical(self.packet["target"]))
        earlier["dimensions"] = {"blockers": earlier["dimensions"]["blockers"]}
        earlier["dimensions"]["blockers"]["records"][0]["uncertainty"] = ["contradictory-evidence"]
        path = self.project / "early.json"
        path.write_bytes(shared.canonical(earlier))
        os.environ["CTX09C_R2A_EARLY_PROJECTION_PATH"] = str(path)
        right, left = self.run_v2()
        report, _ = self.compare(left, right, "earlier-uncertainty")
        self.assertEqual(report["status"], "indeterminate")
        self.assertIn("contradictory-evidence", right["dimensions"]["blockers"]["records"][0]["uncertainty"])

    def test_artifact_changed_after_chain_validation_cannot_export_stale_observations(self):
        self.run_v2()
        replay = consumer.pipeline._committed_transition_ids

        def replace_after_validation(context, bundles, args):
            result = replay(context, bundles, args)
            ref = f"transitions/{context.state['transitionId']}/checkpoint-v1.json"
            checkpoint = self.project / context.run_relative / ref
            changed = json.loads(checkpoint.read_bytes())
            changed["comparisonProjection"]["dimensions"]["status"]["records"][0]["value"] = "fail"
            checkpoint.write_bytes(shared.canonical(changed))
            return result

        with mock.patch.object(consumer.pipeline, "_committed_transition_ids", side_effect=replace_after_validation):
            with self.assertRaisesRegex(consumer.shared.Error, "artifact changed"):
                consumer.project_completed(self.project, FRAMEWORK, self.packet, self.inputs)

    def test_committed_ctx07a_merge_is_read_and_tampered_merge_rejected(self):
        execution = self.packet["identity"]["shadowProducerId"]
        workspace = self.workspace
        merge = {"schemaVersion": "mana.context-runtime.delegation-merge/v1", "executionId": execution,
            "executionVersion": 1, "workspaceId": self.packet["workspaceId"],
            "profileId": self.packet["profileId"], "phaseId": "synthesize", "attempt": 1,
            "planId": "P-" + "a" * 64, "mergeStatus": "incomplete", "missingTaskIds": ["T-missing"]}
        merge.update({field: [] for field in ("taskResults", "verifiedFacts", "findings", "assumptions", "inferences",
            "openQuestions", "evidenceGaps", "evidenceRefs", "artifactRefs", "uncertainty", "conflicts")})
        path = self.project / "merge-source.json"
        path.write_bytes(shared.canonical(merge))
        os.environ["CTX09C_R2A_MERGE_PATH"] = str(path)
        # workspace manifest is immutable and identical to the consumer's bytes.
        (self.project / workspace / "manifest.yaml").chmod(0o600)
        right, left = self.run_v2()
        self.assertTrue(any(ref.endswith("missingTaskIds") for ref in right["provenance"]["unprojected"]))
        report, _ = self.compare(left, right, "merge-incomplete")
        self.assertEqual(report["status"], "indeterminate")
        merge_ref = next(item for item in right["provenance"]["artifacts"] if item["ref"].endswith("delegation-merge-v1.json"))
        committed = self.project / consumer.pipeline.relative_run_directory(execution) / merge_ref["ref"]
        committed.write_bytes(b"{}\n")
        with self.assertRaises(consumer.shared.Error):
            consumer.project_completed(self.project, FRAMEWORK, self.packet, self.inputs)

    def test_shadow_status_classification_preserves_supervision_outcomes(self):
        # Real supervision mapping is covered by the original INT/TERM/timeout
        # process tests; this checks the persisted journal classification.
        for result, expected in ((live.backend.ProcessResult(124, b"", b"", True), "timed_out"),
                                 (live.backend.ProcessResult(143, b"", b"", False, 15), "interrupted"),
                                 (live.backend.ProcessResult(23, b"", b""), "failed"),
                                 (live.backend.ProcessResult(0, b"", b""), "completed")):
            self.assertEqual(live.backend.shadow_status(result), expected)

    def test_native_and_test_backend_operational_canaries(self):
        outside = self.base / "outside"
        outside.mkdir()
        shadow = self.project / ".mana/runtime/shadows/comparison/runs/execution-shadow"
        shadow.mkdir(parents=True, mode=0o700)
        reads = {}
        canonical_paths = {
            "legacyHead": ".mana/runtime/runs/execution-legacy/HEAD",
            "legacyRunState": ".mana/runtime/runs/execution-legacy/run-state-v1.json",
            "legacyMetrics": ".mana/runtime/metrics/execution-legacy/usage-summary-v1.json",
            "legacyOutput": ".mana/runtime/shadows/comparison/records/legacy-output-capsule.json",
            "legacyBundles": ".mana/runtime/runs/execution-legacy/transitions/bundle/checkpoint-v1.json",
            "legacyReceipts": ".mana/runtime/producers/execution-legacy/receipt.json",
            "otherNamespace": ".mana/runtime/shadows/other-comparison/records/result.json"}
        for name, relative in canonical_paths.items():
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"LEGACY_CANARY")
            reads[name] = str(path)
        (outside / "canary").write_bytes(b"OUTSIDE_CANARY")
        reads["outsidePath"] = str(outside / "canary")
        volume_alias = Path("/System/Volumes/Data") / reads["legacyHead"].lstrip("/")
        if volume_alias.is_file(): reads["systemVolumeAlias"] = str(volume_alias)
        with test_backend.admit_test_only(shadow) as fixture:
            allowed = shadow / "input"
            allowed.write_bytes(b"SHARED_INPUT")
            reads["parentTraversal"] = str(shadow / ".." / ".." / ".." / ".." / "runs" / "execution-legacy" / "HEAD")
            symlink = fixture.scratch / "symlink"
            symlink.symlink_to(reads["legacyHead"])
            hardlink = fixture.scratch / "hardlink"
            os.link(reads["legacyMetrics"], hardlink)
            reads.update(symlinkEscape=str(symlink), hardlinkEscape=str(hardlink))
            # Host alias admission is fail-closed, independent of the kernel probe.
            self.assertFalse(live.backend.safe_tree(fixture.scratch))
            paths = {"publish": str(outside / "publish"), "externalWrite": str(outside / "external"),
                     "reads": reads, "allowedInput": str(allowed)}
            if fixture.status != "available":
                # Nested sandboxes are an unavailable backend, not evidence
                # that the hostile process was contained.
                symlink.unlink()
                hardlink.unlink()
                self.assertFalse((outside / "publish").exists())
                self.assertFalse((outside / "external").exists())
                return
            policy = live.backend.policy(fixture.scratch, shadow, shadow,
                (REPO / "tests/context-shadow-backend-test-only.py",))
            native = live.backend.Admission("available", None, fixture.scratch, policy)
            result = native.invoke([sys.executable, str(REPO / "tests/context-shadow-backend-test-only.py")],
                                  input_bytes=json.dumps(paths).encode(), environment=os.environ.copy(), cwd=self.project)
            self.assertEqual(result.returncode, 0, (result.stderr, result.stdout))
            self.assertTrue(all(json.loads(result.stdout).values()))
            symlink.unlink()
            hardlink.unlink()
            result = fixture.invoke([sys.executable, str(REPO / "tests/context-shadow-backend-test-only.py")],
                input_bytes=json.dumps({**paths, "reads": {key: value for key, value in reads.items()
                    if key not in ("symlinkEscape", "hardlinkEscape")}}).encode(), environment=os.environ.copy(), cwd=self.project)
            self.assertEqual(result.returncode, 0, (result.stderr, result.stdout))
        self.assertFalse((outside / "publish").exists())
        self.assertFalse((outside / "external").exists())


if __name__ == "__main__":
    unittest.main()
