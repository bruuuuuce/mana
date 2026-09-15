#!/usr/bin/env python3
"""Full re-attestation, real abrupt deaths and process caller convergence.

The import-only host fixture substitutes two fixed local producers for model
calls. Producers, comparator, filesystem publications, flock, CAS and os._exit
are real. Native read/write containment is separately gated by R2A canaries.
"""
import base64
import importlib.util
import json
import os
import stat
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location("r2c_support", str(Path(__file__).with_name("context-runtime-live-shadow.py")))
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
live, shared, REPO = support.live, support.shared, support.REPO


class Reconciliation(unittest.TestCase):
    setUp = support.LiveShadow.setUp
    tearDown = support.LiveShadow.tearDown
    packet = support.LiveShadow.packet
    semantic = support.LiveShadow.semantic

    def payload(self, name):
        snapshot = live.consumer.snapshot("ctx06c-fixture", support.FIXTURES / "ctx06a-framework")
        return self.packet(snapshot=snapshot, comparison="execution-r2c-" + name)

    def base_for(self, payload):
        return self.project / live.SHADOW_NAMESPACE / shared.validate(payload)["identity"]["comparisonExecutionId"]

    def counters(self, payload):
        identity = shared.validate(payload)["identity"]
        return {"legacy": self.project / identity["legacyMetricsRoot"] / "r2c-invocations",
                "shadow": self.project / identity["shadowRunRoot"] / "r2c-invocations",
                "compare": self.base_for(payload) / "r2c-comparator-invocations"}

    def counts(self, payload):
        return {key: path.read_bytes().count(b"invocation\n") if path.exists() else 0
                for key, path in self.counters(payload).items()}

    @contextmanager
    def host(self, payload):
        supervised, compare = live.backend.execute_supervised, live.comparison.run
        counters = self.counters(payload)
        fixture = REPO / "tests/fixtures/context-runtime/ctx09c-r2c-producer.py"
        def invoke(role, **kwargs):
            counters[role].parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            environment = {**kwargs.pop("environment"), "CTX09C_R2C_OUTPUT": base64.b64encode(self.semantic(payload)).decode()}
            kwargs.setdefault("timeout_name", "MANA_CTX09C_SHADOW_TIMEOUT_SECONDS")
            return supervised([sys.executable, str(fixture), role, str(counters[role])], environment=environment, **kwargs)
        class Admission:
            status, reason = "available", None
            def invoke(self, argv, **kwargs):
                return invoke("shadow", **kwargs)
        @contextmanager
        def admit(*args, **kwargs):
            yield Admission()
        def comparator(*args):
            fd = os.open(counters["compare"], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, b"compare invocation\n")
                os.fsync(fd)
            finally:
                os.close(fd)
            if os.environ.get("CTX09C_R2C_COMPARATOR_CRASH") == "1":
                os._exit(99)
            return compare(*args)
        with mock.patch.object(live.backend, "execute_supervised", side_effect=lambda argv, **kw: invoke("legacy", **kw)), \
                mock.patch.object(live.backend, "admit", side_effect=admit), \
                mock.patch.object(live.consumer, "capabilities", return_value={}), \
                mock.patch.object(live, "_shadow_candidate_context", return_value={
                    "workspaceId": shared.validate(payload)["workspaceId"],
                    "committedChainDigest": shared.digest(b"fixed local test chain")}), \
                mock.patch.object(live.comparison, "run", side_effect=comparator):
            yield

    def invoke_host(self, payload):
        with self.host(payload):
            return live.run_shared(str(self.project), payload)

    def child(self, payload, point=None, stage=None, destination="child", comparator_crash=False):
        pid = os.fork()
        if pid == 0:
            try:
                if point:
                    os.environ.update(MANA_CTX09C_FAULT=point, MANA_CTX09C_FAULT_EXIT="1")
                if stage:
                    os.environ["MANA_CTX09C_FAULT_STAGE"] = stage
                if comparator_crash:
                    os.environ["CTX09C_R2C_COMPARATOR_CRASH"] = "1"
                status, result, stdout, stderr = self.invoke_host(payload)
                for suffix, value in (("stdout", stdout), ("stderr", stderr), ("result", live.canonical(result))):
                    (self.base / (destination + "." + suffix)).write_bytes(value)
                os._exit(status)
            except BaseException:
                os._exit(98)
        return pid

    def wait_child(self, pid):
        # Bounded wait: failures must not leave a test blocked on a dead flock.
        import time
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                return os.waitstatus_to_exitcode(status)
            time.sleep(0.02)
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        self.fail("R2C child did not converge within 30 seconds")

    def assert_clean(self, payload):
        base = self.base_for(payload)
        self.assertFalse((base / "input").exists())
        self.assertFalse(list(base.rglob("*.stage.*")))
        self.assertFalse(list(base.rglob("shared-input-v1.json")))

    def outside_snapshot(self):
        return {str(path.relative_to(self.project)): (stat.S_IMODE(path.lstat().st_mode),
                    path.read_bytes() if path.is_file() else None)
                for path in self.project.rglob("*") if ".mana" not in path.relative_to(self.project).parts}

    def assert_chain(self, payload):
        base = self.base_for(payload)
        with live.mode.HostRoot(str(self.project)) as root:
            journal = live.Journal(root, str(base.relative_to(self.project)), payload)
            state = journal.current
            self.assertEqual(state["stage"], "completed")
            stages = []
            while state:
                stages.append(state["stage"])
                bundle = json.loads((base / "bundles" / state["bundleId"] / "bundle-v1.json").read_bytes())
                previous = bundle["previousBundle"]
                state = json.loads((self.project / previous["path"]).read_bytes())["state"] if previous else None
            for stage in ("legacy_committed", "shadow_completed", "comparison_completed"):
                self.assertEqual(stages.count(stage), 1)
            self.assertEqual(len(stages), journal.current["revision"])

    def test_real_fault_matrix_adopts_artifacts_and_never_reinvokes(self):
        points = [("after-packet-publication", None), ("after-input-materialization", None),
                  ("after-legacy-artifact-pre-head", None), ("after-legacy-head", None),
                  ("after-shadow-artifact-pre-head", None), ("after-shadow-head", None),
                  ("after-comparison-artifact-pre-head", None), ("during-head-cas", "comparison_completed"),
                  ("after-comparison-head-pre-cleanup", None)]
        for ordinal, (point, stage) in enumerate(points):
            payload = self.payload("crash-" + str(ordinal))
            outside = self.project / "outside-canary"
            outside.write_bytes(b"unchanged outside invariant")
            outside_before = self.outside_snapshot()
            tmp_before = set(Path("/private/tmp").glob("mana-ctx09c-input-*"))
            with self.subTest(point=point):
                self.assertEqual(self.wait_child(self.child(payload, point, stage)), 99)
                private_packet = self.base_for(payload) / "input/shared-input-v1.json"
                self.assertTrue(private_packet.exists())
                self.assertEqual(stat.S_IMODE(private_packet.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(private_packet.parent.stat().st_mode), 0o700)
                head = json.loads((self.base_for(payload) / live.HEAD_NAME).read_bytes())
                self.assertEqual(head["packetReference"]["path"], str(private_packet.relative_to(self.project)))
                before = self.counts(payload)
                first, second = self.invoke_host(payload), self.invoke_host(payload)
                self.assertEqual(first[0], 0)
                self.assertEqual(first[2:], (self.semantic(payload), b"legacy stderr\x00\xfe"))
                self.assertEqual(second[0], first[0])
                self.assertEqual(second[2:], first[2:])
                self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 1, "compare": 1})
                if before["compare"] == 1:
                    self.assertEqual(self.counts(payload)["compare"], before["compare"])
                self.assertEqual(outside.read_bytes(), b"unchanged outside invariant")
                self.assertEqual(self.outside_snapshot(), outside_before)
                self.assertEqual(set(Path("/private/tmp").glob("mana-ctx09c-input-*")), tmp_before)
                self.assert_clean(payload)
                self.assert_chain(payload)

    def test_two_real_concurrent_harnesses_converge_after_each_crash(self):
        for ordinal, point in enumerate((None, "after-legacy-head", "after-shadow-artifact-pre-head",
                                         "after-comparison-artifact-pre-head", "during-head-cas")):
            payload = self.payload("concurrent-" + str(ordinal))
            if point:
                self.assertEqual(self.wait_child(self.child(payload, point, "comparison_completed" if point == "during-head-cas" else None)), 99)
            left = self.child(payload, destination="left")
            right = self.child(payload, destination="right")
            self.assertEqual(self.wait_child(left), 0)
            self.assertEqual(self.wait_child(right), 0)
            for suffix in ("stdout", "stderr", "result"):
                self.assertEqual((self.base / ("left." + suffix)).read_bytes(), (self.base / ("right." + suffix)).read_bytes())
            self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 1, "compare": 1})
            self.assert_chain(payload)
            self.assert_clean(payload)

    def test_ambiguous_process_or_comparator_crash_is_terminal_without_replay(self):
        for ordinal, point in enumerate(("after-legacy-process-exit", "after-shadow-process-exit", "comparator")):
            payload = self.payload("ambiguous-" + str(ordinal))
            self.assertEqual(self.wait_child(self.child(payload, point if point != "comparator" else None,
                                                       comparator_crash=point == "comparator")), 99)
            before = self.counts(payload)
            for _ in range(2):
                result = self.invoke_host(payload)
                self.assertEqual(result[0], 2 if point == "after-legacy-process-exit" else 0)
            self.assertEqual(self.counts(payload), before)
            self.assert_clean(payload)

    def test_terminal_failure_cleans_packet(self):
        payload = self.payload("failure")
        with mock.patch.dict(os.environ, {"CTX09C_R2C_EXIT": "23"}):
            first, second = self.invoke_host(payload), self.invoke_host(payload)
        self.assertEqual(first[0], 23)
        self.assertEqual(second[2:], first[2:])
        self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 0, "compare": 0})
        self.assert_clean(payload)

    def mutate(self, path, mutation):
        if mutation == "missing":
            path.unlink()
        elif mutation == "identical-inode":
            replacement = path.with_name("replacement")
            replacement.write_bytes(path.read_bytes())
            replacement.chmod(0o600)
            replacement.replace(path)
        else:
            path.write_bytes(b"tampered")

    def test_completed_reuse_rejects_every_reachable_commitment(self):
        cases = [(name, action) for name in ("legacy-artifact-v1.json", "v2-artifact-v1.json",
                 "records/legacy-candidate-binding-v1.json", "records/v2-candidate-binding-v1.json",
                 "records/legacy-receipt-v1.json", "records/shadow-receipt-v1.json",
                 "records/comparison-attempt-v1.json", "records/comparison-attempt-commit-v1.json", "records/comparison-report-v1.json",
                 "recovery/legacy-outcome-v1.json", "recovery/stdout.bin", "recovery/stderr.bin")
                 for action in ("missing", "tamper", "identical-inode")]
        cases += [("producer-receipt", "tamper"), ("producer-receipt", "identical-inode"),
                  ("producer-commit", "missing"), ("chain", "missing"), ("chain", "tamper"),
                  ("chain", "identical-inode"), ("bundle", "tamper"),
                  ("bundle", "identical-inode"), ("head", "identical-inode")]
        for ordinal, (name, mutation) in enumerate(cases):
            payload = self.payload("tamper-" + str(ordinal))
            self.invoke_host(payload)
            base = self.base_for(payload)
            head_bytes = (base / live.HEAD_NAME).read_bytes()
            head = json.loads(head_bytes)
            if name.startswith("producer-"):
                namespace, key = live.mode.receipt_location(head["comparisonExecutionId"], head["artifacts"]["v2"]["path"])
                path = self.project / (f"{namespace}/{key}/producer-receipt-v1.json" if name == "producer-receipt"
                                       else f"{namespace}/{key}.commit/producer-commit-v1.json")
            elif name in {"chain", "bundle"}:
                path = base / "bundles" / head["bundleId"] / "bundle-v1.json"
                if name == "chain":
                    path = self.project / json.loads(path.read_bytes())["previousBundle"]["path"]
            elif name == "head":
                path = base / live.HEAD_NAME
            else:
                path = base / name
            self.mutate(path, mutation)
            with self.subTest(name=name, mutation=mutation), self.host(payload):
                for _ in range(2):
                    with self.assertRaises(live.ManualRecoveryRequired):
                        live.run_shared(str(self.project), payload)
            self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 1, "compare": 1})
            self.assertEqual((base / live.HEAD_NAME).read_bytes(), head_bytes)
            self.assert_clean(payload)

    def test_foreign_bundle_chain_digest_and_expected_stage_rejected(self):
        for ordinal, field in enumerate(("bundleId", "previousHeadDigest", "stage", "comparisonExecutionId", "packetDigest")):
            payload = self.payload("foreign-" + str(ordinal))
            self.invoke_host(payload)
            head_path = self.base_for(payload) / live.HEAD_NAME
            head = json.loads(head_path.read_bytes())
            head[field] = "shadow_completed" if field == "stage" else ("0" * 64)
            head_path.write_bytes(live.canonical(head))
            with self.subTest(field=field), self.assertRaises(live.ManualRecoveryRequired):
                self.invoke_host(payload)
            self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 1, "compare": 1})
            self.assert_clean(payload)

    def test_orphan_attempt_tampering_is_discarded_without_second_comparison(self):
        for ordinal, field in enumerate(("inputReceiptDigest", "pairIdentity", "report", "result")):
            payload = self.payload("orphan-" + str(ordinal))
            self.assertEqual(self.wait_child(self.child(payload, "after-comparison-artifact-pre-head")), 99)
            path = self.base_for(payload) / "records/comparison-attempt-v1.json"
            value = json.loads(path.read_bytes())
            value[field] = {} if field != "inputReceiptDigest" else "0" * 64
            path.write_bytes(live.canonical(value))
            first, second = self.invoke_host(payload), self.invoke_host(payload)
            self.assertEqual(first[0], 0)
            self.assertEqual(first[1]["comparison"]["status"], "indeterminate")
            self.assertEqual(first[2:], second[2:])
            self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 1, "compare": 1})
            self.assert_clean(payload)

    def test_orphan_attempt_file_instance_and_seal_must_be_complete(self):
        for ordinal, (name, mutation) in enumerate((("comparison-attempt-v1.json", "identical-inode"),
                ("comparison-attempt-v1.json", "missing"), ("comparison-attempt-commit-v1.json", "missing"),
                ("comparison-attempt-commit-v1.json", "tamper"))):
            payload = self.payload("orphan-seal-" + str(ordinal))
            self.assertEqual(self.wait_child(self.child(payload, "after-comparison-artifact-pre-head")), 99)
            self.mutate(self.base_for(payload) / "records" / name, mutation)
            first, second = self.invoke_host(payload), self.invoke_host(payload)
            self.assertEqual(first[1]["comparison"]["status"], "indeterminate")
            self.assertEqual(first[2:], second[2:])
            self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 1, "compare": 1})
            self.assert_clean(payload)

    def test_invalid_head_reconciliation_still_removes_crashed_packet(self):
        payload = self.payload("invalid-head-packet")
        self.assertEqual(self.wait_child(self.child(payload, "after-input-materialization")), 99)
        (self.base_for(payload) / live.HEAD_NAME).write_bytes(b"invalid HEAD")
        with self.assertRaises(live.ManualRecoveryRequired):
            self.invoke_host(payload)
        self.assert_clean(payload)
        self.assertEqual(self.counts(payload), {"legacy": 0, "shadow": 0, "compare": 0})

    def test_rehashed_bundle_cannot_relabel_a_completed_shadow_as_failed(self):
        payload = self.payload("rehashed-stage")
        self.assertEqual(self.wait_child(self.child(payload, "after-shadow-head")), 99)
        base = self.base_for(payload)
        head_path = base / live.HEAD_NAME
        state = json.loads(head_path.read_bytes())
        bundle = json.loads((base / "bundles" / state["bundleId"] / "bundle-v1.json").read_bytes())
        state.pop("bundleId")
        state["stage"] = "shadow_failed"
        bundle_id = "B-" + shared.digest(live.canonical({"previous": state["previousHeadDigest"], "state": state}))
        state["bundleId"] = bundle_id
        bundle.update(bundleId=bundle_id, state=state, stateDigest=shared.digest(live.canonical(state)))
        with live.mode.HostRoot(str(self.project)) as root:
            live.private_write(root, str((base / "bundles" / bundle_id / "bundle-v1.json").relative_to(self.project)), live.canonical(bundle))
        head_path.write_bytes(live.canonical(state))
        with self.assertRaises(live.ManualRecoveryRequired):
            self.invoke_host(payload)
        self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 1, "compare": 0})
        self.assert_clean(payload)

    def test_packet_rebinding_before_consumption_fails_closed_and_cleans(self):
        payload = self.payload("packet-rebinding")
        def fault(point):
            if point == "after-input-materialization":
                self.mutate(self.base_for(payload) / "input/shared-input-v1.json", "identical-inode")
        with mock.patch.object(live, "fault", side_effect=fault), self.assertRaises(live.mode.runtime.ContractError):
            self.invoke_host(payload)
        self.assert_clean(payload)
        self.assertEqual(self.counts(payload), {"legacy": 0, "shadow": 0, "compare": 0})

    def test_failed_packet_publication_reconciles_private_staging_bytes(self):
        payload = self.payload("packet-staging")
        original = live.private_write
        def fail(root, relative, encoded):
            if relative.endswith("/input/shared-input-v1.json"):
                original(root, relative.rsplit("/", 1)[0] + "/.live-shadow.stage." + "a" * 32, encoded)
                raise OSError("packet publication failed after materialization")
            return original(root, relative, encoded)
        with mock.patch.object(live, "private_write", side_effect=fail), self.assertRaises(OSError):
            self.invoke_host(payload)
        self.assert_clean(payload)
        self.invoke_host(payload)
        self.assertEqual(self.counts(payload), {"legacy": 1, "shadow": 1, "compare": 1})
        self.assert_clean(payload)


if __name__ == "__main__":
    unittest.main()
