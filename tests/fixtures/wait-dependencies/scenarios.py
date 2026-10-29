"""Manual synthetic S02 sidecars. References are resolved against validated fixture IR.

Expected verdicts/counts live in oracles.json and D00, never in this builder.
"""

import hashlib
import json


def scenario(raw, ids, kind="A"):
    reports = {key: json.loads(value) for key, value in raw.items()}
    s = {
        "schema": "mana.wait-scenario/v1",
        "id": "synthetic_" + kind,
        "inputs": [
            {"id": key, "sha256": hashlib.sha256(value).hexdigest()}
            for key, value in raw.items()
        ],
        "participants": [
            {"id": pid, "input": key, "independence": "independent_" + pid}
            for pid, key in ids
        ],
        "premises": [],
        "resources": [],
        "operations": [],
        "lockRule": {
            "id": "opaque_exclusive",
            "version": 1,
            "modes": ["M"],
            "compatibility": [{"left": "M", "right": "M", "result": "INCOMPATIBLE"}],
            "blockingPremise": "blocking",
        },
        "cuts": [],
    }

    def premise(pid, text):
        s["premises"].append(
            {
                "id": pid,
                "statement": text,
                "scope": s["id"],
                "state": "EXPLICIT_ASSUMPTION",
                "provenance": {
                    "source": "manual-synthetic-fixture",
                    "reference": kind + "/" + pid,
                },
                "dependsOn": [],
            }
        )
        return pid

    premise(
        "blocking",
        "Abstract mode M waits on incompatible retention; no NOWAIT, skip, retry, upgrade or hidden locks.",
    )
    premise(
        "concurrent",
        "Independent participant instances have overlapping lifetimes at this common prefix cut.",
    )
    premise(
        "outer",
        "The cut lies within the resolved synchronous replacement call; suspended outer does not execute.",
    )
    premise("serial", "Alpha ends before beta begins; no common live interval.")
    for pid, _ in ids:
        premise(
            "independent_" + pid,
            "This participant is an independent invocation instance, not another name for an existing P.",
        )
    for rid in ("X", "Y"):
        refs = {
            prop: premise(rid + "_" + prop, text)
            for prop, text in (
                ("database", "Both aliases refer to the opaque shared database D."),
                (
                    "object",
                    "Selected operations mapped to this opaque alias access the same object set.",
                ),
                (
                    "overlap",
                    "Their lock targets overlap despite UNKNOWN runtime granularity; no row identity inferred.",
                ),
            )
        }
        s["resources"].append(
            {
                "id": rid,
                "database": "D",
                "databaseRelation": "SAME",
                "objectMatch": "SAME",
                "lockTargetOverlap": "SAME",
                "granularity": "UNKNOWN",
                "premises": refs,
            }
        )
    for pid, key in ids:
        for index, obs in enumerate(reports[key]["observations"], 1):
            oid = pid + str(index)
            rid = obs["resource"]["name"]
            if rid not in {"X", "Y"}:
                rid = None
            s["operations"].append(
                {
                    "id": oid,
                    "participant": pid,
                    "observation": obs["id"],
                    "resource": rid,
                    "binding": {
                        "datasource": "ds_" + pid,
                        "database": "D",
                        "enlisted": True,
                        "premise": premise(
                            oid + "_binding",
                            "Assume effective datasource, database D and JDBC participation in the original P for this operation.",
                        ),
                    },
                    "request": {
                        "mode": "M",
                        "premise": premise(
                            oid + "_request",
                            "Assume this invocation requests abstract mode M on the selected opaque target.",
                        ),
                    },
                }
            )
            premise(
                oid + "_acquire",
                "Assume this operation returned after acquisition before the cut.",
            )
            premise(
                oid + "_retain",
                "Assume acquisition is retained through the cut, including any logical end, savepoint release or physical suspension.",
            )
    return s


def clear_lock_scenario(s):
    for op in s["operations"]:
        op["request"] = {"mode": None, "premise": None}
        op["binding"] = {
            "datasource": None,
            "database": None,
            "enlisted": None,
            "premise": None,
        }
    s["lockRule"]["blockingPremise"] = None
    s["lockRule"]["compatibility"] = []
    s["cuts"] = []
    return s


def cut(s, raw, cid, pending, holds, temporal="CONCURRENT", prefixes=None):
    pmap = {p["id"]: p["input"] for p in s["participants"]}
    selected = {o["id"]: o for o in s["operations"]}

    def seq(oid):
        op = selected[oid]
        report = json.loads(raw[pmap[op["participant"]]])
        return next(
            o["placement"]["beforeT01Sequence"]
            for o in report["observations"]
            if o["id"] == op["observation"]
        )

    if prefixes is None:
        prefixes = {}
        for pid, key in pmap.items():
            pending_ops = [q for q in pending if selected[q]["participant"] == pid]
            prefixes[pid] = (
                seq(pending_ops[0])
                if pending_ops
                else len(json.loads(raw[key])["transactionModel"]["events"]) + 1
            )
    result = {
        "id": cid,
        "prefixes": prefixes,
        "pending": pending,
        "holdings": [
            {
                "operation": h,
                "acquisitionPremise": h + "_acquire",
                "retentionPremise": h + "_retain",
            }
            for h in holds
        ],
        "temporal": {
            "kind": temporal,
            "premise": "outer"
            if temporal == "OUTER_REQUIRES_NEW"
            else "serial"
            if temporal == "SERIAL"
            else "concurrent",
        },
    }
    s["cuts"].append(result)
    return result


def materialize(case_id, models):
    """Hand-defined scenarios for all static D00 rows. No S02 calls here."""
    pair = case_id[:3] in {"O-A", "O-B", "O-F", "O-H"}
    if case_id in {"O-C01", "O-C02", "O-C03", "O-F07"}:
        names = {
            "t": "outer_unknown"
            if case_id == "O-C03"
            else "outer_f02"
            if case_id == "O-F07"
            else "outer"
        }
    elif case_id.startswith("O-D"):
        names = {"t": "required"}
    elif case_id.startswith("O-E"):
        names = {"t": "nested"}
    elif case_id == "O-G01":
        names = {"t": "unordered"}
    elif case_id == "O-G02":
        names = {"t": "frontier"}
    elif case_id == "O-G03":
        names = {"t": "asyncCaller"}
    elif case_id.startswith("O-I"):
        names = {"t": "read" if case_id == "O-I01" else "request"}
    elif case_id.startswith("O-B"):
        names = {"ta": "xy", "tb": "xy"}
    elif pair:
        names = {"ta": "xy", "tb": "yx"}
    else:
        names = {"t": "xy"}
    raw = {key: models[name] for key, name in names.items()}
    ids = [("a", "ta"), ("b", "tb")] if "ta" in names else [("a", "t")]
    if case_id == "O-F06":
        raw = {"t": models["xy"]}
        ids = [("a", "t"), ("b", "t")]
    s = scenario(raw, ids, case_id.replace("-", "_"))
    if (
        case_id in {"O-A01", "O-H03"}
        or case_id.startswith("O-F")
        and case_id not in {"O-F06", "O-F07"}
    ):
        cut(s, raw, "common", ["a2", "b2"], ["a1", "b1"])
    elif case_id == "O-A03":
        cut(s, raw, "common", ["a2", "b2"], ["a1", "b1"], "UNKNOWN")
    elif case_id == "O-A04":
        cut(s, raw, "serial", ["a2", "b2"], ["a1", "b1"], "SERIAL")
    elif case_id == "O-B01":
        cut(s, raw, "one_wait", ["a2", "b1"], ["a1"])
    elif case_id == "O-B02":
        cut(s, raw, "s1", ["b1"], ["a1"], prefixes={"a": 5, "b": 4})
        cut(s, raw, "s2", ["a1"], ["b1"], prefixes={"a": 4, "b": 5})
    elif case_id == "O-B03":
        cut(s, raw, "impossible", ["a1", "b1"], ["a1", "b1"])
    elif case_id == "O-C01":
        cut(s, raw, "replacement", ["a2"], ["a1"], "OUTER_REQUIRES_NEW")
    elif case_id == "O-G04":
        cut(s, raw, "impossible", ["a1", "a2"], ["a1"], prefixes={"a": 5})
    elif case_id == "O-H01":
        cut(s, raw, "ended", ["a2", "b2"], ["a1", "b1"], prefixes={"a": 9, "b": 9})
    if case_id in {
        "O-A02",
        "O-C02",
        "O-C03",
        "O-D01",
        "O-D02",
        "O-E01",
        "O-E02",
        "O-F01",
        "O-F04",
        "O-F06",
        "O-F07",
        "O-G01",
        "O-G02",
        "O-G03",
        "O-I01",
        "O-I02",
    }:
        clear_lock_scenario(s)
    if case_id == "O-F02":
        s["operations"] = [o for o in s["operations"] if o["id"] in {"a2", "b1"}]
        s["operations"][0]["binding"]["enlisted"] = None
        s["cuts"][0]["pending"] = ["a2"]
        s["cuts"][0]["holdings"] = [
            h for h in s["cuts"][0]["holdings"] if h["operation"] == "b1"
        ]
    elif case_id == "O-F03":
        for r in s["resources"]:
            r["databaseRelation"] = "DISJOINT"
            r["objectMatch"] = "DISJOINT"
            r["lockTargetOverlap"] = "DISJOINT"
    elif case_id == "O-F04":
        for op in s["operations"]:
            op["binding"]["datasource"] = "different_ds_" + op["participant"]
    elif case_id == "O-F05":
        for r in s["resources"]:
            r["lockTargetOverlap"] = "UNKNOWN"
    if case_id in {"O-D02", "O-E02"}:
        # Ritenzione non asserita nonostante P viva dopo LOGICAL_END/SP_RELEASE.
        s["operations"] = []
    if case_id == "O-H02":
        bad = json.loads(raw["ta"])
        bad["transactionModel"]["frames"][0]["afterState"] = {
            "kind": "TRANSACTION_PHYSICAL",
            "physicalId": "P1",
            "manager": "tx",
        }
        raw["ta"] = (json.dumps(bad) + "\n").encode()
        s["inputs"][0]["sha256"] = hashlib.sha256(raw["ta"]).hexdigest()
    if case_id == "O-J05":
        s["runtimeIdentity"] = "invented"
        s["certainty"] = "OBSERVED"
    return raw, s
