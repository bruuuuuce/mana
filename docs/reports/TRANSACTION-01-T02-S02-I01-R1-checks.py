"""Independent bounded review controls; no implementation or input mutations."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from skill_factory.transactions import wait_dependencies as wd  # noqa: E402
from skill_factory.transactions.wait_validation import validate_report  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "cli", ROOT / "scripts/mana-wait-dependencies.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
results = []


def load(case="A"):
    base = ROOT / "docs/examples/transaction-01-t02-s02" / case
    s = json.loads((base / "scenario.json").read_bytes())
    return {
        i["id"]: (base / "inputs" / (i["id"] + ".json")).read_bytes()
        for i in s["inputs"]
    }, s


def check(name, fn):
    try:
        detail = fn()
        results.append({"id": name, "status": "PASS", "detail": detail})
    except Exception as e:
        results.append({"id": name, "status": "FAIL", "error": repr(e)})


def run(s, raw):
    r = wd.build_report(raw, s)
    validate_report(r, raw)
    return r


def summary(r):
    return {
        "result": r["assessment"]["result"],
        "db": len(r["databaseGraph"]["edges"]),
        "app": len(r["applicationGraph"]["edges"]),
        "coverage": r["coverage"]["status"],
    }


def positive():
    raw, s = load()
    r = run(s, raw)
    pairs = {
        (c["waiter"]["participantId"], c["blocker"]["participantId"], c["resource"])
        for c in r["claims"]
        if c["category"] == "DB_WAIT_DEPENDENCY"
    }
    assert pairs == {("a", "b", "Y"), ("b", "a", "X")}
    assert r["assessment"]["result"] == "CONDITIONAL_CYCLE_RISK"
    assert len(r["databaseGraph"]["nodes"]) == 2
    assert all(c["certainty"] != "OBSERVED" for c in r["claims"])
    return summary(r)


check("A-compatible-common-cut", positive)


def exclusive():
    raw, s = load("B")
    template = copy.deepcopy(s["cuts"][0])
    s["cuts"] = []
    for cid, prefix, pending, held in [
        ("alpha_holds", {"a": 5, "b": 4}, ["b1"], "a1"),
        ("beta_holds", {"a": 4, "b": 5}, ["a1"], "b1"),
    ]:
        c = copy.deepcopy(template)
        c.update(
            id=cid,
            prefixes=prefix,
            pending=pending,
            holdings=[
                {
                    "operation": held,
                    "acquisitionPremise": held + "_acquire",
                    "retentionPremise": held + "_retain",
                }
            ],
        )
        s["cuts"].append(c)
    r = run(s, raw)
    assert r["assessment"]["result"] == "CYCLE_FEASIBILITY_UNKNOWN"
    assert len(r["databaseGraph"]["edges"]) == 2
    assert all(
        c["result"] == "NO_CYCLE_IN_MODELED_SCENARIO" for c in r["assessment"]["cuts"]
    )
    # Both first operations returned, both exclusive holdings now simultaneous.
    s["cuts"] = [copy.deepcopy(template)]
    c = s["cuts"][0]
    c.update(
        prefixes={"a": 5, "b": 5},
        pending=["a2", "b2"],
        holdings=[
            {
                "operation": h,
                "acquisitionPremise": h + "_acquire",
                "retentionPremise": h + "_retain",
            }
            for h in ["a1", "b1"]
        ],
    )
    bad = run(s, raw)
    assert not bad["databaseGraph"]["edges"]
    assert (
        "simultaneous incompatible holdings on the same opaque target"
        in bad["assessment"]["cuts"][0]["contradictions"]
    )
    return {"separate": summary(r), "conjoined": summary(bad)}


check("B-exclusive-schedules-and-returned-holdings", exclusive)


def ended():
    raw, s = load()
    c = s["cuts"][0]
    c["prefixes"] = {"a": 9, "b": 5}
    c["pending"] = ["b2"]
    c["holdings"] = c["holdings"][:1]
    r = run(s, raw)
    assert not r["databaseGraph"]["edges"]
    assert any(
        w["id"] == "W1" and w["state"] == "CONTRADICTED"
        for x in r["waitCandidates"]
        for w in x["obligations"]
    )
    return summary(r)


check("C-ended-holder-independent-of-pending-position", ended)


def mixed():
    raw, s = load("C")
    r = run(s, raw)
    assert r["assessment"]["result"] == "CONDITIONAL_CROSS_LAYER_COMPLETION_RISK"
    assert len(r["databaseGraph"]["edges"]) == len(r["applicationGraph"]["edges"]) == 1
    c = next(c for c in r["claims"] if c["category"] == "DB_WAIT_DEPENDENCY")
    assert (c["waiter"]["originalPhysicalId"], c["blocker"]["originalPhysicalId"]) == (
        "P2",
        "P1",
    )
    assert not wd.structural_cycle(r["databaseGraph"]["edges"])
    live, suspended = wd.prefix_state(
        wd.Scenario(s, wd.Inputs(raw, wd.unique(s["inputs"]))), "a", 9
    )
    assert live == {"P1", "P2"} and suspended == {"P1"}
    return summary(r)


check("D-mixed-completion-not-db-deadlock", mixed)


def no_locks():
    raw, s = load()
    for o in s["operations"]:
        o["request"] = {"mode": None, "premise": None}
    s["cuts"][0]["holdings"] = []
    r = run(s, raw)
    assert not r["databaseGraph"]["edges"]
    assert not any(c["category"] == "LOCK_REQUEST_CANDIDATE" for c in r["claims"])
    assert r["assessment"]["result"] == "UNKNOWN", summary(r)
    return summary(r)


check("WRITE-does-not-acquire-or-request", no_locks)


def missing(kind):
    raw, s = load()
    if kind == "overlap":
        for r in s["resources"]:
            r["lockTargetOverlap"] = "UNKNOWN"
    elif kind == "binding":
        for o in s["operations"]:
            o["binding"]["enlisted"] = None
    elif kind == "independence":
        for p in s["participants"]:
            p["independence"] = None
    elif kind == "retention":
        for c in s["cuts"]:
            for h in c["holdings"]:
                h["retentionPremise"] = None
    elif kind == "pending-prefix":
        s["cuts"][0]["prefixes"]["a"] = 6
    elif kind == "serial":
        s["cuts"][0]["temporal"] = {"kind": "SERIAL", "premise": "serial"}
    r = run(s, raw)
    assert not r["databaseGraph"]["edges"]
    assert r["coverage"]["globalRiskAbsence"] == "NOT_ASSERTED"
    return summary(r)


for kind in [
    "overlap",
    "binding",
    "independence",
    "retention",
    "pending-prefix",
    "serial",
]:
    check("missing-or-incompatible-" + kind, lambda kind=kind: missing(kind))


def reject_authority(kind):
    raw, s = load()
    if kind in ["MODEL_EVIDENCE", "RUNTIME_EVIDENCE"]:
        s["premises"][0]["state"] = kind
    elif kind == "digest":
        s["inputs"][0]["sha256"] = "0" * 64
    elif kind == "witness":
        t = json.loads(raw["ta"])
        e = next(
            e
            for e in t["transactionModel"]["events"]
            if e["kind"] == "RESOURCE_LEAF_CALL"
        )
        e["witness"]["normalReturnDependencies"] = [999]
        raw["ta"] = json.dumps(t).encode()
        s["inputs"][0]["sha256"] = wd.digest(raw["ta"])
    try:
        wd.build_report(raw, s)
    except wd.RejectedInput as e:
        return str(e)
    raise AssertionError("forged input accepted")


for kind in ["MODEL_EVIDENCE", "RUNTIME_EVIDENCE", "digest", "witness"]:
    check("forgery-" + kind, lambda kind=kind: reject_authority(kind))


def reject_report(kind):
    raw, s = load()
    r = run(s, raw)
    if kind == "assessment":
        r["assessment"]["result"] = "NO_CYCLE_IN_MODELED_SCENARIO"
    elif kind == "observed":
        r["claims"][0]["certainty"] = "OBSERVED"
    elif kind == "witness":
        r["operations"][0]["normalReturnDependencies"] = [999]
    elif kind == "cut":
        r["databaseGraph"]["edges"][0]["cut"] = "invented"
    try:
        validate_report(r, raw)
    except wd.RejectedInput as e:
        return str(e)
    raise AssertionError("forged output accepted")


for kind in ["assessment", "observed", "witness", "cut"]:
    check("report-" + kind, lambda kind=kind: reject_report(kind))


def budget(key):
    raw, s = load()
    # Reduced thresholds test enforcement; actual-byte cases are in the I01 suite.
    with patch.dict(wd.BUDGETS, {key: 1}):
        try:
            wd.build_report(raw, s)
        except wd.BudgetExceeded as e:
            return str(e)
    raise AssertionError("budget silently exceeded")


for key in wd.BUDGETS:
    check("budget-" + key, lambda key=key: budget(key))


def scope():
    raw, s = load()
    s["resources"].append({**copy.deepcopy(s["resources"][0]), "id": "Z"})
    r = run(s, raw)
    assert (
        r["coverage"]["status"] == "INCOMPLETE"
        and r["assessment"]["result"] == "UNKNOWN"
        and len(r["operations"]) == 4
        and not r["databaseGraph"]["edges"]
    )
    return summary(r)


check("scope-incomplete-keeps-inventory", scope)


def visual():
    for case in ["A", "B", "C"]:
        raw, s = load(case)
        r = run(s, raw)
        files = cli.artifacts(r)
        base = ROOT / "docs/examples/transaction-01-t02-s02" / case
        for name, b in files.items():
            assert b == (base / name).read_bytes(), (case, name)
        for c in r["assessment"]["cuts"]:
            lines = files["database-" + c["cut"] + ".mmd"].decode().splitlines()
            assert sum(" -->|" in line for line in lines) == sum(
                e["cut"] == c["cut"] for e in r["databaseGraph"]["edges"]
            )
    return "A/B/C exact regeneration; edge counts, cut and layer labels checked; external renderer NOT_RUN"


check("visual-json-mermaid-parity", visual)
if OUT is not None:
    assert OUT.is_dir() and OUT != ROOT and ROOT not in OUT.parents
    (OUT / "independent-results.json").write_text(json.dumps(results, indent=2) + "\n")
for r in results:
    print(r["id"], r["status"], json.dumps(r.get("detail", r.get("error"))))
sys.exit(any(r["status"] != "PASS" for r in results))
