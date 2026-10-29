#!/usr/bin/env python3
"""Independent D00 negative-claim review; no product or historical input edits.

Expected results are manual D00 judgments. Fixtures supply validated source bytes,
not verdicts. The bounded upper-bound proof ignores W2-W5 to include every possible
DB edge permitted by source identity and prior-acquisition ordering (W1/W6).
"""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from skill_factory.transactions import wait_dependencies as wd  # noqa: E402
from skill_factory.transactions import wait_validation as val  # noqa: E402

NEG = "NO_CYCLE_IN_MODELED_SCENARIO"
RESULTS = []
OLD = None


def load(case):
    base = ROOT / "docs/examples/transaction-01-t02-s02" / case
    s = json.loads((base / "scenario.json").read_bytes())
    return {
        i["id"]: (base / "inputs" / (i["id"] + ".json")).read_bytes()
        for i in s["inputs"]
    }, s


def upper_bound(raw, s):
    """Review-only proof for closed, resolved fixture prefixes; not a producer."""
    rows = []
    for p in s["participants"]:
        t = json.loads(raw[p["input"]])
        for o in s["operations"]:
            if o["participant"] == p["id"]:
                obs = next(x for x in t["observations"] if x["id"] == o["observation"])
                rows.append(
                    {
                        "operation": o["id"],
                        "participant": p["id"],
                        "P": obs["transactionContext"]["physicalId"],
                        "frame": obs["frame"],
                        "sequence": obs["placement"]["beforeT01Sequence"],
                    }
                )
    proofs = []
    for cut in s["cuts"]:
        for p in s["participants"]:
            tx = json.loads(raw[p["input"]])["transactionModel"]
            assert not any(
                e["kind"] == "UNRESOLVED_CALL"
                and e["sequence"] < cut["prefixes"][p["id"]]
                for e in tx["events"]
            )
        assert all(r["P"] is not None and r["sequence"] is not None for r in rows)
        edges = set()
        for q in rows:
            for h in rows:
                qn = (q["participant"], q["P"])
                hn = (h["participant"], h["P"])
                if (
                    qn != hn
                    and q["sequence"] == cut["prefixes"][q["participant"]]
                    and h["sequence"] < cut["prefixes"][h["participant"]]
                ):
                    edges.add((qn, hn))
        # These witnesses have at most two P nodes; a cycle needs reciprocal arcs.
        assert len({(r["participant"], r["P"]) for r in rows}) <= 2
        proofs.append(
            {
                "cut": cut["id"],
                "possibleEdgesIgnoringLocksAndPendingList": sorted(edges),
                "acyclicUpperBound": not any((b, a) in edges for a, b in edges),
            }
        )
    return {"sourceOperations": rows, "cuts": proofs}


def observe(name, raw, s, expected, proof=False):
    r = wd.build_report(raw, s)
    accepted = val.validate_report(r, raw)
    row = {
        "id": name,
        "expected": expected,
        "actual": r["assessment"]["result"],
        "status": "PASS" if r["assessment"]["result"] == expected else "FAIL",
        "validatorAccepted": accepted,
        "assessment": r["assessment"],
        "coverage": r["coverage"],
        "dbEdges": len(r["databaseGraph"]["edges"]),
        "appEdges": len(r["applicationGraph"]["edges"]),
        "scenario": copy.deepcopy(s),
        "inputDigests": {k: wd.digest(v) for k, v in raw.items()},
    }
    if OLD is not None:
        row["reexecutedBeforeF01"] = OLD.build_report(raw, s)["assessment"]
    if proof:
        row["independentProof"] = upper_bound(raw, s)
        assert all(c["acyclicUpperBound"] for c in row["independentProof"]["cuts"])
    with tempfile.TemporaryDirectory(prefix="mana-f01-r1-") as tmp:
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
        target = stage / "output"
        generated = subprocess.run(
            args + ["--output-dir", str(target)], capture_output=True, text=True
        )
        assert generated.returncode == 0, generated.stderr
        assert json.loads(generated.stdout)["assessment"] == row["actual"]
        validated = subprocess.run(
            args + ["--validate", str(target / "wait-dependency.json")],
            capture_output=True,
            text=True,
        )
        assert validated.returncode == 0, validated.stderr
        row["cli"] = {
            "generateExit": generated.returncode,
            "validateExit": validated.returncode,
            "stdout": generated.stdout,
        }
        if name == "complete-acyclic-B":
            changed = copy.deepcopy(s)
            changed["cuts"][0]["holdings"] = []
            scenario.write_text(json.dumps(changed))
            bad = subprocess.run(
                args + ["--validate", str(target / "wait-dependency.json")],
                capture_output=True,
                text=True,
            )
            assert bad.returncode == 2 and "another sidecar" in bad.stderr
            row["alteredSidecar"] = {"exit": bad.returncode, "stderr": bad.stderr}
            scenario.write_bytes(b" " * (wd.BUDGETS["sidecarBytes"] + 1))
            bad = subprocess.run(
                args + ["--output-dir", str(stage / "budget")],
                capture_output=True,
                text=True,
            )
            assert bad.returncode == 2 and not (stage / "budget").exists()
            assert json.loads(bad.stderr)["status"] == "BUDGET_EXCEEDED"
            row["cliBudget"] = {"exit": bad.returncode, "stderr": bad.stderr}
    RESULTS.append(row)
    return r


def forged_negative(raw, r):
    forged = copy.deepcopy(r)
    forged["assessment"]["result"] = NEG
    for c in forged["assessment"]["cuts"]:
        c["result"], c["unknowns"] = NEG, []
    forged["coverage"]["status"] = "COMPLETE_MODELED_SCOPE"
    forged["coverage"]["reasons"] = []
    forged["unknowns"] = []
    for candidate in forged["waitCandidates"]:
        for w in candidate["obligations"]:
            if w["state"] == "UNKNOWN":
                w["state"] = "MODEL_EVIDENCE"
    with patch.object(val, "build_report", return_value=forged) as producer:
        try:
            val.validate_report(forged, raw)
        except wd.RejectedInput as e:
            producer.assert_not_called()
            return str(e)
    raise AssertionError("validator accepted unsupported W4 before reprojection")


def main():
    global OLD
    # Recover only the historical source bytes; never apply the patch to Git.
    path = "scripts/skill_factory/transactions/wait_dependencies.py"
    patch_text = (ROOT / "docs/reports/TRANSACTION-01-T02-S02-I01.patch").read_text()
    section = patch_text.split("diff --git a/" + path + " b/" + path + "\n", 1)[
        1
    ].split("diff --git ", 1)[0]
    source = "".join(
        line[1:]
        for line in section.splitlines(keepends=True)
        if line.startswith("+") and not line.startswith("+++")
    )
    assert (
        wd.digest(source.encode())
        == "6b95d22c0aafcbd443c1d53f894caaca7cc86197305a358119217696c2453cd1"
    )
    import types

    OLD = types.ModuleType("skill_factory.transactions.review_before_f01")
    OLD.__package__ = "skill_factory.transactions"
    exec(compile(source, "I01.patch:wait_dependencies.py", "exec"), OLD.__dict__)
    for case, expected in (
        ("A", "CONDITIONAL_CYCLE_RISK"),
        ("B", NEG),
        ("C", "CONDITIONAL_CROSS_LAYER_COMPLETION_RISK"),
    ):
        raw, s = load(case)
        observe(
            "complete-acyclic-B" if case == "B" else "complete-" + case,
            raw,
            s,
            expected,
        )
    for case in ("A", "C"):
        raw, s = load(case)
        s["cuts"][0]["holdings"] = []
        r = observe(case + "-R1-no-holdings", raw, s, "UNKNOWN")
        RESULTS[-1]["forgedNegativeRejectedBeforeProducer"] = forged_negative(raw, r)
    raw, s = load("A")
    s["cuts"][0]["holdings"].pop()
    observe("A-partial-holder-omission", raw, s, "UNKNOWN")
    raw, s = load("B")
    s["cuts"][0]["pending"] = []
    observe("B-no-pending", raw, s, NEG, proof=True)
    raw, s = load("B")
    missing = copy.deepcopy(s["cuts"][0])
    missing.update(id="missing", holdings=[])
    s["cuts"].append(missing)
    observe("B-one-incomplete-cut", raw, s, NEG, proof=True)
    raw, s = load("A")
    for h in s["cuts"][0]["holdings"]:
        next(p for p in s["premises"] if p["id"] == h["acquisitionPremise"])[
            "state"
        ] = "UNKNOWN"
    r = observe("W4-declared-without-acquisition", raw, s, "UNKNOWN")
    RESULTS[-1]["forgedNegativeRejectedBeforeProducer"] = forged_negative(raw, r)
    s["premises"][0]["state"] = "MODEL_EVIDENCE"
    try:
        wd.build_report(raw, s)
    except wd.RejectedInput as e:
        RESULTS.append(
            {"id": "self-certified-sidecar", "status": "PASS", "reason": str(e)}
        )
    else:
        raise AssertionError("MODEL_EVIDENCE accepted from sidecar")
    raw, s = load("B")
    for budget in ("candidateComparisons", "serializedEdges"):
        with patch.dict(wd.BUDGETS, {budget: 1}):
            try:
                wd.build_report(raw, s)
            except wd.BudgetExceeded as e:
                RESULTS.append(
                    {"id": "budget-" + budget, "status": "PASS", "reason": str(e)}
                )
            else:
                raise AssertionError("budget returned a report")
    spec = importlib.util.spec_from_file_location(
        "source_fixtures", ROOT / "tests/wait-dependencies.py"
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    fixture.WaitTests.setUpClass()
    try:
        for kind in ("required", "nested"):
            raw = {"t": fixture.WaitTests.models[kind]}
            # Reproduce the historical degradation, but do not reuse its oracle.
            s = fixture.scenarios.clear_lock_scenario(
                fixture.scenarios.scenario(raw, [("a", "t")], kind)
            )
            fixture.scenarios.cut(s, raw, "incomplete", ["a2"], [])
            observe(kind + "-incomplete-cut", raw, s, NEG, proof=True)
            # Minimal independent sidecar: no resource rules or lock assumptions.
            s = copy.deepcopy(s)
            s["resources"], s["premises"] = [], []
            s["participants"][0]["independence"] = None
            s["lockRule"] = {
                "id": "none",
                "version": 1,
                "modes": [],
                "compatibility": [],
                "blockingPremise": None,
            }
            for op in s["operations"]:
                op["resource"] = None
            s["cuts"][0]["temporal"] = {"kind": "UNKNOWN", "premise": None}
            r = observe(kind + "-minimal-counterexample", raw, s, NEG, proof=True)
            RESULTS[-1]["qualifiedNegativeRejectedBeforeProducer"] = forged_negative(
                raw, r
            )
            s["cuts"] = []
            observe(kind + "-same-source-without-cut", raw, s, NEG)
        raw = {"t": fixture.WaitTests.models["frontier"]}
        s = fixture.scenarios.scenario(raw, [("a", "t")], "frontier_f01")
        fixture.scenarios.cut(s, raw, "frontier", ["a2"], ["a1"], "OUTER_REQUIRES_NEW")
        s["cuts"][0]["prefixes"]["a"] += 1
        observe("frontier-incomplete-cut", raw, s, "UNKNOWN")
    finally:
        fixture.WaitTests.tearDownClass()
    output = {
        "basis": "D00 sections 4-6/9; O-A01/B01/C02/D01/E01/G02; independent W1/W6 acyclic upper bound",
        "checks": RESULTS,
    }
    print(json.dumps(output, indent=2))
    return int(any(r["status"] == "FAIL" for r in RESULTS))


if __name__ == "__main__":
    sys.exit(main())
