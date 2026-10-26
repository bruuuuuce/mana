"""Literal source oracles for entry only, fixed before examining Mana output.

cases.json encodes JLS block/evaluation dependencies: no fixture is executed.
Positive/negative are D01's discriminants with Spring premises kept separate.
"""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "timeline_cli", ROOT / "scripts/mana-resource-timeline.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
from skill_factory.transactions.local_admission import (  # noqa: E402
    FIELD,
    attach_local_admission,
    evaluation_witness,
    verify_local_admission,
)
from skill_factory.transactions.source import java_facts  # noqa: E402

CONTEXT = {
    "schema": "mana.transaction-context/v1",
    "initialState": "NO_TRANSACTION",
    "entryThroughProxy": False,
    "managerCapabilities": {},
}
CASES = json.loads(
    (ROOT / "tests/fixtures/transaction-local-admission/cases.json").read_text()
)


class LocalAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        home = Path(shutil.which("javac")).resolve().parent.parent
        if home == Path("/usr"):
            home = Path(
                subprocess.check_output(["/usr/libexec/java_home"], text=True).strip()
            )
        cls.environment = {"jdkHome": str(home), "release": "8", "classpath": []}
        cls.cache = {}

    def case(self, key):
        if key in self.cache:
            return copy.deepcopy(self.cache[key])
        case = next(c for c in CASES if c["id"] == key)
        raw = case["source"].encode()
        files = {"Case.java": raw}
        if key in {"positive", "negative", "springUnknown"}:
            for p in (
                ROOT / "tests/fixtures/transaction-execution-dependencies/support"
            ).glob("*.java"):
                files["support/" + p.name] = p.read_bytes()
        facts = java_facts(cli.t01.factory, ROOT, files, source_snapshot=True)
        caller = next(
            (c, m) for c in facts["classes"] for m in c["methods"] if m["name"] == "run"
        )
        entry = caller[0]["name"] + "#run"
        ev = caller[1]["evidence"]
        start = case["source"].index(case["site"])
        site = {
            "file": "Case.java",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "start": start,
            "end": start + len(case["site"]),
            "line": 1,
        }
        witness, _ = evaluation_witness(
            cli.t01.factory, ROOT, files, ev, [], self.environment, parse_facts=facts
        )
        self.assertIn(witness["status"], {"COMPLETE", "INCOMPLETE"}, witness["reason"])
        baseline = cli.t01.build(facts, CONTEXT, entry)
        baseline["evidence"] = [
            {"path": name, "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(files.items())
        ]
        args = {
            "parse_facts": facts,
            "request": {"entry": ev, "dependencies": []},
            "requested_site": site,
        }
        before = copy.deepcopy((baseline, witness, facts, files))
        model = attach_local_admission(
            baseline, witness, cli.t01.factory, ROOT, files, self.environment, **args
        )
        self.assertEqual(before, (baseline, witness, facts, files))
        self.assertEqual(bool(model[FIELD]["entries"]), case["admitted"])
        without = copy.deepcopy(model)
        without.pop(FIELD)
        self.assertEqual(without, baseline)
        timeline = cli.build_timeline(model, facts)
        cli.validate_timeline(timeline)
        self.assertEqual(timeline["transactionModel"], model)
        self.assertEqual(
            timeline["timeline"], cli.build_timeline(baseline, facts)["timeline"]
        )
        self.assertEqual(
            timeline["observations"],
            cli.build_timeline(baseline, facts)["observations"],
        )
        for record in model[FIELD]["entries"]:
            self.assertEqual(record["completion"], "UNKNOWN")
            self.assertEqual(record["returnValue"], "UNKNOWN")
            self.assertEqual(record["runtimeExecution"], "NOT_OBSERVED")
            self.assertEqual(record["transactionInterception"], "NOT_ASSERTED")
            self.assertEqual(record["transactionContext"]["kind"], "UNKNOWN")
            self.assertEqual(record["frontier"]["bodyTraversal"], "NOT_ASSERTED")
        self.cache[key] = (model, files, facts, args)
        return copy.deepcopy(self.cache[key])

    def test_01_positive_D01(self):
        self.case("positive")

    def test_02_negative_D01(self):
        self.case("negative")

    def test_03_verified_binding(self):
        self.case("binding")

    def test_04_receiver_unknown(self):
        self.case("receiver")

    def test_05_argument_may_throw_before_entry(self):
        self.case("argument")

    def test_06_dispatch_unknown(self):
        self.case("dispatch")

    def test_07_conditional_entry_not_automatically_admitted(self):
        self.case("conditional")

    def test_08_unknown_return(self):
        self.case("unknownReturn")

    def test_09_getter_not_admitted(self):
        self.case("getter")

    def test_10_effectful_initializer(self):
        self.case("initializer")

    def test_11_Java_entry_does_not_prove_Spring(self):
        self.case("springUnknown")

    def test_12_no_negative_authority(self):
        model, *_ = self.case("negativeAuthority")
        self.assertEqual(model[FIELD]["negativeAuthority"], "NOT_ASSERTED")
        self.assertEqual(model[FIELD]["completeness"], "INCOMPLETE")
        self.assertEqual(model[FIELD]["causalTraceAuthority"], "NONE")

    def test_16_synchronized_entry_needs_monitor_proof(self):
        self.case("synchronized")

    def test_17_native_entry_needs_linkage_proof(self):
        self.case("native")

    def test_13_missing_or_mutated_premise_rejected(self):
        model, *_ = self.case("binding")
        mutations = [
            lambda r: r.pop("premises"),
            lambda r: r.update(completion="KNOWN"),
            lambda r: r.update(runtimeExecution="OBSERVED"),
            lambda r: r["evaluationProof"].update(receiver="LOCAL"),
            lambda r: r["evaluationProof"]["arguments"].reverse(),
            lambda r: r["frontier"].update(continuation="KNOWN"),
        ]
        for mutate in mutations:
            bad = copy.deepcopy(model)
            mutate(bad[FIELD]["entries"][0])
            with self.assertRaises(ValueError):
                cli.t01.validate_model(bad)

    def test_14_coherent_forgery_requires_pinned_replay(self):
        from skill_factory.transactions.local_admission import _projection

        model, files, facts, args = self.case("binding")
        witness = copy.deepcopy(model[FIELD]["witness"])
        witness["localEntry"]["arguments"][0]["parameter"] = 123
        model[FIELD] = _projection(model, witness, args["requested_site"])
        with self.assertRaises(ValueError):
            verify_local_admission(
                model, cli.t01.factory, ROOT, files, self.environment, **args
            )

    def test_18_lost_proof_restores_conservative_boundary(self):
        model, files, facts, args = self.case("binding")
        witness, _ = evaluation_witness(
            cli.t01.factory,
            ROOT,
            files,
            args["request"]["entry"],
            [],
            self.environment,
            parse_facts=facts,
            limits={"nodes": 1},
        )
        self.assertEqual(witness["status"], "BLOCKED")
        self.assertNotIn("localEntry", witness)
        baseline = copy.deepcopy(model)
        baseline.pop(FIELD)
        with self.assertRaises(ValueError):
            attach_local_admission(
                baseline,
                witness,
                cli.t01.factory,
                ROOT,
                files,
                self.environment,
                **args,
            )
        self.assertNotIn(FIELD, baseline)
        self.assertTrue(cli.t01.validate_model(baseline))

    def test_15_legacy_consumer_is_conservative(self):
        import types

        model, _, facts, _ = self.case("binding")
        legacy = types.ModuleType("skill_factory.transactions.legacy_admission_model")
        source = subprocess.check_output(
            [
                "git",
                "--no-optional-locks",
                "show",
                "HEAD:scripts/skill_factory/transactions/model.py",
            ],
            cwd=ROOT,
        ).decode()
        exec(compile(source, "legacy.py", "exec"), legacy.__dict__)
        self.assertTrue(legacy.validate_model(model))
        old = types.ModuleType("skill_factory.transactions.legacy_admission_resources")
        source = subprocess.check_output(
            [
                "git",
                "--no-optional-locks",
                "show",
                "HEAD:scripts/skill_factory/transactions/resources.py",
            ],
            cwd=ROOT,
        ).decode()
        exec(compile(source, "legacy-resources.py", "exec"), old.__dict__)
        old.validate_model = legacy.validate_model
        old.validate_timeline(cli.build_timeline(model, facts))


if __name__ == "__main__":
    unittest.main()
