"""Bounded F02-R1 dispositions and bidirectional v1 compatibility reproducer.

No historical oracle, fixture, or product file is changed. Exit 1 means the
public compatibility regression is still present. Historical modules are
reconstructed in memory from F02.patch and checked against pre-F02 hashes.
"""

import copy
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from skill_factory.transactions import wait_dependencies as wd  # noqa: E402
from skill_factory.transactions import wait_validation as val  # noqa: E402

PREFIX = ROOT / "docs/reports/TRANSACTION-01-T02-S02-I01-F02"
NEG = "NO_CYCLE_IN_MODELED_SCENARIO"


def load(case):
    base = ROOT / "docs/examples/transaction-01-t02-s02" / case
    scenario = json.loads((base / "scenario.json").read_bytes())
    raw = {
        i["id"]: (base / "inputs" / (i["id"] + ".json")).read_bytes()
        for i in scenario["inputs"]
    }
    return base, raw, scenario


def previous_source(path):
    """Reverse unified hunks in memory, verifying every current context byte."""
    lines = PREFIX.with_suffix(".patch").read_text().splitlines(keepends=True)
    start = lines.index("+++ b/" + path + "\n") + 1
    stop = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("diff --git ")),
        len(lines),
    )
    current = (ROOT / path).read_text().splitlines(keepends=True)
    result, pos, i = [], 0, start
    while i < stop:
        match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", lines[i])
        assert match, lines[i]
        at = int(match[1]) - 1
        result.extend(current[pos:at])
        pos, i = at, i + 1
        while i < stop and not lines[i].startswith("@@"):
            line = lines[i]
            i += 1
            if line[0] in " +":
                assert current[pos] == line[1:]
                pos += 1
            if line[0] in " -":
                result.append(line[1:])
    result.extend(current[pos:])
    return "".join(result)


def legacy_modules():
    receipt = json.loads(Path(str(PREFIX) + "-results.json").read_bytes())
    modules, hashes = [], {}
    for name in ("wait_dependencies", "wait_validation"):
        path = "scripts/skill_factory/transactions/" + name + ".py"
        source = previous_source(path)
        actual = hashlib.sha256(source.encode()).hexdigest()
        expected = next(
            c["before"]["sha256"]
            for c in receipt["integrity"]["authorizedChanges"]
            if c["path"] == path
        )
        assert actual == expected
        hashes[path] = actual
        module = types.ModuleType("skill_factory.transactions._f02_r1_old_" + name)
        exec(compile(source, path + "@pre-F02", "exec"), module.__dict__)
        modules.append(module)
    old_engine, old_validator = modules
    for name, value in list(old_validator.__dict__.items()):
        if hasattr(wd, name) and value is getattr(wd, name):
            old_validator.__dict__[name] = getattr(old_engine, name)
    return old_engine, old_validator, hashes


def acceptance(validator, report, raw):
    try:
        return {"accepted": validator.validate_report(report, raw)}
    except (ValueError, KeyError, TypeError) as error:
        return {"accepted": False, "error": type(error).__name__, "reason": str(error)}


def remove_proofs(report):
    result = copy.deepcopy(report)
    result["assessment"].pop("exclusionProof", None)
    for cut in result["assessment"]["cuts"]:
        cut.pop("exclusionProof", None)
    return result


def acyclic(edges):
    """Warshall reachability, independent of both product cycle algorithms."""
    nodes = {n for edge in edges for n in edge}
    reach = set(edges)
    for middle in nodes:
        reach |= {
            (a, b)
            for a in nodes
            for b in nodes
            if (a, middle) in reach and (middle, b) in reach
        }
    return not any((node, node) in reach for node in nodes)


def alternatives(raw, scenario, cut):
    """All subsets of a source-only upper bound for the four bounded exclusions.

    This reads the whole observation inventory, never producer certificates or
    ledgers. Ignoring every lock/resource premise can only add possible edges.
    """
    rows, app, states = [], set(), {}
    for participant in scenario["participants"]:
        pid = participant["id"]
        timeline = json.loads(raw[participant["input"]])
        tx = timeline["transactionModel"]
        before = cut["prefixes"][pid]
        assert not any(
            e["kind"] == "UNRESOLVED_CALL" and e["sequence"] <= before
            for e in tx["events"]
        )
        frames = {f["id"]: f for f in tx["frames"]}
        live, suspended, stack = set(), set(), []
        for event in tx["events"]:
            if event["sequence"] >= before:
                break
            kind = event["kind"]
            if kind == "PHYSICAL_BEGIN":
                live.add(event["entity"])
            elif kind == "PHYSICAL_END_OUTCOME_UNKNOWN":
                live.discard(event["entity"])
            elif kind == "SUSPEND":
                suspended.add(event["physicalId"])
            elif kind == "RESUME_CONDITIONAL":
                suspended.discard(event["physicalId"])
            elif kind == "FRAME_ENTER":
                stack.append(event["frame"])
            elif kind == "FRAME_EXIT":
                assert stack.pop() == event["frame"]
        states[pid] = (live, suspended)
        for caller, callee in zip(stack, stack[1:]):
            a, b = (frames[f]["duringState"]["physicalId"] for f in (caller, callee))
            assert a is not None and b is not None
            if a != b:
                app.add(((pid, a), (pid, b)))
        selected = {
            o["observation"] for o in scenario["operations"] if o["participant"] == pid
        }
        assert selected == {o["id"] for o in timeline["observations"]}
        for obs in timeline["observations"]:
            physical = obs["transactionContext"]["physicalId"]
            seq = obs["placement"]["beforeT01Sequence"]
            assert physical is not None and seq is not None
            rows.append((pid, physical, seq))
    db = {
        ((p, physical), (hp, hphysical))
        for p, physical, seq in rows
        for hp, hphysical, hseq in rows
        if (p, physical) != (hp, hphysical)
        and seq == cut["prefixes"][p]
        and physical in states[p][0]
        and physical not in states[p][1]
        and hseq < cut["prefixes"][hp]
        and hphysical in states[hp][0]
    }
    possibilities = [
        acyclic(set(subset) | app)
        for size in range(len(db) + 1)
        for subset in itertools.combinations(db, size)
    ]
    return {
        "cut": cut["id"],
        "prefixes": cut["prefixes"],
        "sourceOperations": rows,
        "possibleDatabaseEdges": sorted(db),
        "activeApplicationEdges": sorted(app),
        "alternativesChecked": len(possibilities),
        "allAlternativesAcyclic": all(possibilities),
    }


def main():
    old_engine, old_validator, hashes = legacy_modules()
    result = {"historicalModuleHashes": hashes, "compatibility": [], "exclusions": []}
    for case in ("A", "B", "C"):
        base, raw, scenario = load(case)
        historical = json.loads((base / "wait-dependency.json").read_bytes())
        fresh = wd.build_report(raw, scenario)
        assert old_engine.build_report(raw, scenario) == historical
        assert remove_proofs(fresh) == historical
        assert val.validate_report(fresh, raw)
        args = [
            sys.executable,
            str(ROOT / "scripts/mana-wait-dependencies.py"),
            "--scenario",
            str(base / "scenario.json"),
        ]
        for key in raw:
            args += ["--timeline", key + "=" + str(base / "inputs" / (key + ".json"))]
        process = subprocess.run(
            args + ["--validate", str(base / "wait-dependency.json")],
            capture_output=True,
            text=True,
        )
        with tempfile.TemporaryDirectory(prefix="mana-f02-r1-wire-") as temporary:
            outputs = []
            for seed in ("1", "97"):
                output = Path(temporary).resolve() / seed
                generated = subprocess.run(
                    args + ["--output-dir", str(output)],
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PYTHONHASHSEED": seed},
                )
                assert generated.returncode == 0, generated.stderr
                outputs.append((output / "wait-dependency.json").read_bytes())
            assert outputs[0] == outputs[1]
        row = {
            "case": case,
            "reportSchemaBeforeAfter": [historical["schema"], fresh["schema"]],
            "sidecarSchemaBeforeAfter": [
                historical["scenario"]["schema"],
                fresh["scenario"]["schema"],
            ],
            "oldAcceptsOld": acceptance(old_validator, historical, raw),
            "newAcceptsOld": acceptance(val, historical, raw),
            "oldAcceptsNew": acceptance(old_validator, fresh, raw),
            "newAcceptsNew": acceptance(val, fresh, raw),
            "onlyProofFieldsDiffer": True,
            "deterministicRepeatedBuild": wd.encoded(fresh)
            == wd.encoded(wd.build_report(raw, scenario)),
            "cliHistoricalExit": process.returncode,
            "cliHistoricalStderr": process.stderr,
            "deterministicCliAcrossHashSeeds": True,
            "cliJsonSha256": hashlib.sha256(outputs[0]).hexdigest(),
        }
        assert row["oldAcceptsOld"]["accepted"]
        result["compatibility"].append(row)
    # The UNKNOWN wire representation is also affected, despite null proofs.
    _, raw, scenario = load("A")
    scenario["cuts"][0]["holdings"] = []
    old_unknown = old_engine.build_report(raw, scenario)
    new_unknown = wd.build_report(raw, scenario)
    assert (
        old_unknown["assessment"]["result"]
        == new_unknown["assessment"]["result"]
        == "UNKNOWN"
    )
    old_without_proofs = remove_proofs(new_unknown)
    old_comparisons = old_unknown["coverage"]["candidateComparisons"]
    new_comparisons = new_unknown["coverage"]["candidateComparisons"]
    old_without_proofs["coverage"]["candidateComparisons"] = old_comparisons
    assert old_without_proofs == old_unknown
    result["unknownCompatibility"] = {
        "oldAcceptsOld": acceptance(old_validator, old_unknown, raw),
        "newAcceptsOld": acceptance(val, old_unknown, raw),
        "oldAcceptsNew": acceptance(old_validator, new_unknown, raw),
        "newAcceptsNew": acceptance(val, new_unknown, raw),
        "newAcceptsNewWithoutNullProofs": acceptance(
            val, remove_proofs(new_unknown), raw
        ),
        "otherWireChanges": {
            "coverage.candidateComparisons": [old_comparisons, new_comparisons]
        },
        "onlyNullProofFieldsAndComparisonCounterDiffer": True,
    }
    spec = importlib.util.spec_from_file_location(
        "f02_r1_sources", ROOT / "tests/wait-dependencies.py"
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    fixture.WaitTests.setUpClass()
    try:
        for name in ("B-no-pending", "B-one-incomplete-cut", "required", "nested"):
            if name.startswith("B"):
                _, raw, scenario = load("B")
                if name == "B-no-pending":
                    scenario["cuts"][0]["pending"] = []
                else:
                    missing = copy.deepcopy(scenario["cuts"][0])
                    missing.update(id="missing", holdings=[])
                    scenario["cuts"].append(missing)
            else:
                raw = {"t": fixture.WaitTests.models[name]}
                scenario = fixture.scenarios.clear_lock_scenario(
                    fixture.scenarios.scenario(raw, [("a", "t")], name)
                )
                fixture.scenarios.cut(scenario, raw, "incomplete", ["a2"], [])
            report = wd.build_report(raw, scenario)
            proofs = [alternatives(raw, scenario, cut) for cut in scenario["cuts"]]
            assert all(p["allAlternativesAcyclic"] for p in proofs)
            union = {
                tuple(map(tuple, edge))
                for p in proofs
                for edge in p["possibleDatabaseEdges"]
            }
            assert acyclic(union)
            assert report["assessment"]["result"] == NEG
            assert report["coverage"]["status"] == "INCOMPLETE"
            assert val.validate_report(report, raw)
            result["exclusions"].append(
                {
                    "id": name,
                    "classification": "SUPERSEDED_EXPECTATION",
                    "sourceProofs": proofs,
                    "unionAcyclic": True,
                    "assessment": report["assessment"],
                    "coverage": report["coverage"],
                }
            )
    finally:
        fixture.WaitTests.tearDownClass()
    compatible = all(
        r["newAcceptsOld"]["accepted"] and r["oldAcceptsNew"]["accepted"]
        for r in result["compatibility"]
    )
    result["compatibilityClassification"] = (
        "PRESERVED" if compatible else "BREAKING_COMPATIBILITY"
    )
    result["verdict"] = (
        "NEEDS_FIX" if not compatible else "COMPATIBILITY_RECHECK_REQUIRED"
    )
    print(json.dumps(result, indent=2) + "\n")
    return 0 if compatible else 1


if __name__ == "__main__":
    sys.exit(main())
