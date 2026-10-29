"""Independent MR01-R1 review probes; never derives expected verdicts from build."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location(
    "independent_review_cli", ROOT / "scripts/mana-transaction.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
data = json.loads(
    (ROOT / "tests/fixtures/transaction-transition-contract/cases.json").read_text()
)
r4 = json.loads(
    (ROOT / "docs/reports/MANA-TRANSACTION-01-T01-R4-results.json").read_text()
)


def outcome(model):
    supplied = copy.deepcopy(model)
    try:
        accepted = bool(cli.validate_model(supplied))
        error = None
    except Exception as exc:
        accepted, error = False, f"{type(exc).__name__}: {exc}"
    return {"accepted": accepted, "error": error, "inputUnchanged": supplied == model}


oracle_results = []
for case in data["cases"] + data["transitionPositives"]:
    variants = []
    for model in [case["model"], *case.get("variants", [])]:
        row = outcome(model)
        row["matched"] = row["accepted"] == (case["expected"] == "ACCEPT")
        if not row["accepted"]:
            row["semanticDiagnosticMatched"] = bool(
                row["error"].startswith("ValueError:")
                and re.search(case["rejectPattern"], row["error"])
            )
        variants.append(row)
    oracle_results.append(
        {
            "id": case["id"],
            "transition": case.get("transition", case["id"]),
            "expected": case["expected"],
            "variants": variants,
        }
    )

r4_results = []
for name in [v["case"] for v in r4["finding"]["variants"]] + [
    "hand-unknown-" + p for p in ("REQUIRED", "NESTED", "REQUIRES_NEW")
]:
    model = r4["reviewArtifacts"][name + ".json"]
    raw = (json.dumps(model, indent=2) + "\n").encode()
    row = {
        "case": name,
        "archivePointer": "reviewArtifacts/" + name + ".json",
        "canonicalSha256": hashlib.sha256(raw).hexdigest(),
        **outcome(model),
    }
    if name.startswith("hand-unknown-"):
        row.update(
            classification="LEGITIMATELY_REJECTED",
            globalMode=model["interceptionMode"],
            weaving=model["aspectjWeaving"],
            framePremises=[
                {
                    "id": f["id"],
                    "proxy": f["proxy"],
                    "interception": f.get("interception"),
                }
                for f in model["frames"]
            ],
        )
    r4_results.append(row)

counterexamples = []
for identity in ("O27", "O28", "O29"):
    case = next(c for c in data["cases"] if c["id"] == identity)
    original = case["model"]
    model = copy.deepcopy(original)
    model["frames"][1]["proxy"].update(crossed=True, reason="SCENARIO_PROXY_CALL")
    name = identity + "-aspectj-proxy-contradiction.json"
    raw = (json.dumps(model, indent=2) + "\n").encode()
    (OUT / name).write_bytes(raw)
    (OUT / (identity + "-Synthetic.java")).write_text(case["source"])
    counterexamples.append(
        {
            "finding": "R1-F01",
            "base": identity,
            "baseline": outcome(original),
            "expected": "REJECT",
            "actual": outcome(model),
            "payload": name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "sourceUnchanged": True,
            "rendererIdenticalToValidBaseline": cli.render(original)
            == cli.render(model),
        }
    )

# A real source call precedes the later asserted F2 invocation. Recompute all
# affected source spans and hashes, so provenance accidents cannot explain it.
case = next(c for c in data["cases"] if c["id"] == "O02")
model = copy.deepcopy(case["model"])
old_source = case["source"]
position = old_source.index("other.inner();")
prefix = "System.gc(); "
source = old_source[:position] + prefix + old_source[position:]
old_hash = hashlib.sha256(old_source.encode()).hexdigest()
new_hash = hashlib.sha256(source.encode()).hexdigest()


def rebase_spans(value):
    if isinstance(value, dict):
        if value.get("sha256") == old_hash:
            value["sha256"] = new_hash
        if value.get("file") == "Synthetic.java" and "start" in value:
            if value["start"] >= position:
                value["start"] += len(prefix)
                value["end"] += len(prefix)
            elif value["end"] > position:
                value["end"] += len(prefix)
        for item in value.values():
            rebase_spans(item)
    elif isinstance(value, list):
        for item in value:
            rebase_spans(item)


rebase_spans(model)
site = {
    "file": "Synthetic.java",
    "start": position,
    "end": position + len("System.gc()"),
    "line": source[:position].count("\n") + 1,
    "sha256": new_hash,
}
assert source[site["start"] : site["end"]] == "System.gc()"
child_site = model["frames"][1]["callSite"]
assert source[child_site["start"] : child_site["end"]] == "other.inner()"
model["events"].insert(
    3,
    {
        "kind": "UNRESOLVED_CALL",
        "frame": "F1",
        "callSite": site,
        "receiver": "System",
        "method": "gc",
    },
)
for number, event in enumerate(model["events"], 1):
    event["sequence"] = number
model["uncertainties"].append(
    {
        "frame": "F1",
        "reason": "UNRESOLVED_RECEIVER_OR_NON_INJECTED_REFERENCE",
        "classification": "UNKNOWN",
        "evidence": copy.deepcopy(site),
    }
)
frame = model["frames"][0]
frame["continuation"] = "UNKNOWN"
frame["afterState"] = {"kind": "UNKNOWN", "physicalId": None, "manager": None}
frame["effectiveContext"]["after"] = "UNKNOWN"
name = "O02-child-after-unresolved-call.json"
raw = (json.dumps(model, indent=2) + "\n").encode()
(OUT / name).write_bytes(raw)
(OUT / "O02-unresolved-Synthetic.java").write_text(source)
(OUT / "O02-child-after-unresolved-call.puml").write_text(cli.render(model))
counterexamples.append(
    {
        "finding": "R1-F02",
        "base": "O02",
        "baseline": outcome(case["model"]),
        "expected": "REJECT",
        "actual": outcome(model),
        "payload": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sourceSha256": new_hash,
        "laterChildCallSource": source[child_site["start"] : child_site["end"]],
        "unresolvedCallSource": source[site["start"] : site["end"]],
        "sourceSpansRecomputed": True,
        "rendererClaimsRemainingOrderNotAssertedBeforeF2": "remaining order NOT ASSERTED"
        in cli.render(model),
    }
)

# Independent positive: two nested suspensions must be restored in LIFO order.
case = next(c for c in data["cases"] if c["id"] == "O04")
model = copy.deepcopy(case["model"])
old_source = case["source"]
body_pos = old_source.index("public void inner() { ") + len("public void inner() { ")
class_end = old_source.rfind("}")
add_method = '  @Transactional(propagation = Propagation.REQUIRES_NEW, transactionManager = "tx")\n  public void third() { }\n'
insertions = [(body_pos, "other.third(); "), (class_end, add_method)]
source = old_source
for pos, added in reversed(insertions):
    source = source[:pos] + added + source[pos:]
old_hash = hashlib.sha256(old_source.encode()).hexdigest()
new_hash = hashlib.sha256(source.encode()).hexdigest()


def shift_nested(value):
    if isinstance(value, dict):
        if value.get("sha256") == old_hash:
            value["sha256"] = new_hash
        if value.get("file") == "Synthetic.java" and "start" in value:
            before_start, before_end = value["start"], value["end"]
            value["start"] += sum(len(s) for p, s in insertions if p <= before_start)
            value["end"] += sum(len(s) for p, s in insertions if p < before_end)
        for item in value.values():
            shift_nested(item)
    elif isinstance(value, list):
        for item in value:
            shift_nested(item)


shift_nested(model)
frame = copy.deepcopy(model["frames"][1])
third_start = source.rfind("@Transactional(")
third_end = source.index("}", source.index("public void third()")) + 1
third_evidence = {
    "file": "Synthetic.java",
    "start": third_start,
    "end": third_end,
    "line": source[:third_start].count("\n") + 1,
    "sha256": new_hash,
}
third_site_start = source.index("other.third()")
third_site = {
    "file": "Synthetic.java",
    "start": third_site_start,
    "end": third_site_start + len("other.third()"),
    "line": source[:third_site_start].count("\n") + 1,
    "sha256": new_hash,
}
frame.update(
    id="F3",
    depth=2,
    callerMethod="Other#inner()",
    calleeMethod="Other#third()",
    callSite=third_site,
    evidence=third_evidence,
    logicalScope="L3",
)
frame["configuration"]["evidence"] = copy.deepcopy(third_evidence)
for key, identity in (
    ("previousState", "P2"),
    ("duringState", "P3"),
    ("afterState", "P2"),
):
    frame[key]["physicalId"] = identity
model["frames"].append(frame)
item = copy.deepcopy(model["physicalTransactions"][1])
item.update(id="P3", beginFrame="F3", endFrame="F3")
model["physicalTransactions"].append(item)
item = copy.deepcopy(model["logicalScopes"][1])
item.update(id="L3", frame="F3", physicalId="P3")
model["logicalScopes"].append(item)
item = copy.deepcopy(model["suspensions"][0])
item.update(id="S2", frame="F3", physicalId="P2", replacementPhysicalId="P3")
model["suspensions"].append(item)
third_events = copy.deepcopy([e for e in model["events"] if e["frame"] == "F2"])
mapping = {"F2": "F3", "P1": "P2", "P2": "P3", "L2": "L3", "S1": "S2"}
for event in third_events:
    for key in ("frame", "entity", "physicalId"):
        if key in event:
            event[key] = mapping.get(event[key], event[key])
model["events"][7:7] = third_events
for number, event in enumerate(model["events"], 1):
    event["sequence"] = number
raw = (json.dumps(model, indent=2) + "\n").encode()
(OUT / "nested-new-three-frames.json").write_bytes(raw)
(OUT / "nested-new-Synthetic.java").write_text(source)
positive_nested = {
    "expected": "ACCEPT",
    "actual": outcome(model),
    "payload": "nested-new-three-frames.json",
    "sha256": hashlib.sha256(raw).hexdigest(),
    "sourceSha256": new_hash,
    "suspensions": len(model["suspensions"]),
    "eventOrder": [
        {k: e[k] for k in ("kind", "entity", "physicalId") if k in e}
        for e in model["events"]
        if e["kind"] in {"SUSPEND", "RESUME_CONDITIONAL"}
    ],
}

result = {
    "oracles": oracle_results,
    "r4": r4_results,
    "counterexamples": counterexamples,
    "positiveNested": positive_nested,
}
(OUT / "independent-replay.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            "oracleRows": len(oracle_results),
            "oracleVariants": sum(len(x["variants"]) for x in oracle_results),
            "allOracleVariantsMatched": all(
                v["matched"] for c in oracle_results for v in c["variants"]
            ),
            "r4HighRejected": sum(not x["accepted"] for x in r4_results[:9]),
            "historicalPositivesRejected": sum(
                not x["accepted"] for x in r4_results[9:]
            ),
            "falseAcceptances": sum(x["actual"]["accepted"] for x in counterexamples),
        }
    )
)
