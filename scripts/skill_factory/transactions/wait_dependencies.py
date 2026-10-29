"""Bounded offline S02 scenarios. No SQL, propagation or runtime reconstruction."""

from collections import deque
import copy
import hashlib
import json
import re

from .resources import validate_timeline

MIB = 1024 * 1024
BUDGETS = {
    "t01Bytes": 4 * MIB,
    "timelineBytes": 4 * MIB,
    "combinedBytes": 8 * MIB,
    "sidecarBytes": 2 * MIB,
    "candidateComparisons": 100_000,
    "serializedEdges": 5_000,
}
SCOPE = {
    "inputArtifacts": 2,
    "participants": 2,
    "resources": 2,
    "selectedOperations": 4,
    "requiresNewLevels": 1,
}
STATES = {"EXPLICIT_ASSUMPTION", "UNKNOWN", "CONTRADICTED"}
LIMITS = [
    "Conditional static scenario only; execution, locks and waits are not observed.",
    "Opaque targets and abstract compatibility are explicit scenario assumptions.",
    "No JDBC wiring, SQL target resolution, runtime adapter or schedule enumeration.",
    "NO_CYCLE_IN_MODELED_SCENARIO applies only to the modeled scope and cut(s).",
    "No conclusion of general risk absence, deadlock freedom, commit or rollback.",
    "Input digests establish byte identity, not external source authenticity.",
]


class RejectedInput(ValueError):
    """Structurally false, unsupported version, forged certainty or bad reference."""


class BudgetExceeded(ValueError):
    """Stop before publication; coverage is incomplete, never silently truncated."""


def encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, reason):
    if not condition:
        raise RejectedInput(reason)


def keys(value, required, optional=()):
    require(
        isinstance(value, dict)
        and set(required) <= value.keys()
        and value.keys() <= set(required) | set(optional),
        "invalid or extra fields; expected " + ", ".join(required),
    )


def ident(value):
    require(
        isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value),
        "invalid local identifier",
    )
    return value


def unique(items, field="id"):
    require(isinstance(items, list), "expected array")
    result = {}
    for item in items:
        require(isinstance(item, dict) and field in item, "missing identity")
        key = ident(item[field])
        require(key not in result, "duplicate identity " + key)
        result[key] = item
    return result


def parse_json(raw, limit):
    """Reject duplicate keys/nonfinite values and bound depth before JSON decoding."""
    if len(raw) > limit:
        raise BudgetExceeded("JSON byte budget exceeded; coverage INCOMPLETE")
    depth = 0
    quoted = escaped = False
    for char in raw.decode("utf-8"):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            require(depth <= 128, "JSON nesting budget exceeded")
        elif char in "]}":
            depth -= 1

    def pairs(entries):
        obj = {}
        for key, value in entries:
            require(key not in obj, "duplicate JSON key")
            obj[key] = value
        return obj

    def nonfinite(_):
        raise RejectedInput("nonfinite JSON number")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


class Inputs:
    """Index the validated, unmodified T02/T01 records, not a new state machine."""

    def __init__(self, raw_inputs, declarations):
        require(isinstance(raw_inputs, dict) and raw_inputs, "Timeline input required")
        require(
            set(raw_inputs) == set(declarations),
            "input declarations differ from supplied artifacts",
        )
        if sum(len(raw) for raw in raw_inputs.values()) > BUDGETS["combinedBytes"]:
            raise BudgetExceeded("combined input exceeds 8 MiB; coverage INCOMPLETE")
        self.reports, self.meta = {}, {}
        for name, raw in raw_inputs.items():
            if len(raw) > BUDGETS["timelineBytes"]:
                raise BudgetExceeded("Timeline exceeds 4 MiB; coverage INCOMPLETE")
            item = declarations[name]
            keys(item, ("id", "sha256"))
            require(item["sha256"] == digest(raw), "Timeline digest mismatch")
            report = parse_json(raw, BUDGETS["timelineBytes"])
            require(isinstance(report, dict), "Timeline must be an object")
            tx_bytes = encoded(report.get("transactionModel"))
            if len(tx_bytes) > BUDGETS["t01Bytes"]:
                raise BudgetExceeded("embedded T01 exceeds 4 MiB; coverage INCOMPLETE")
            try:
                validate_timeline(report)
            except (KeyError, TypeError, AssertionError, ValueError) as exc:
                raise RejectedInput(
                    "invalid authoritative Timeline/T01: " + str(exc)
                ) from exc
            self.reports[name] = report
            self.meta[name] = {
                "id": name,
                "sha256": digest(raw),
                "bytes": len(raw),
                "t01Sha256": digest(tx_bytes),
                "t01Bytes": len(tx_bytes),
                "t01Encoding": "sorted-compact-ascii-json/v1",
            }


class Scenario:
    def __init__(self, value, inputs):
        if len(encoded(value)) > BUDGETS["sidecarBytes"]:
            raise BudgetExceeded("sidecar exceeds 2 MiB; coverage INCOMPLETE")
        keys(
            value,
            (
                "schema",
                "id",
                "inputs",
                "participants",
                "premises",
                "resources",
                "operations",
                "lockRule",
                "cuts",
            ),
        )
        require(
            value["schema"] == "mana.wait-scenario/v1", "unsupported sidecar version"
        )
        ident(value["id"])
        self.value, self.inputs = value, inputs
        self.participants = unique(value["participants"])
        require(self.participants, "at least one participant required")
        for p in self.participants.values():
            keys(p, ("id", "input", "independence"))
            require(p["input"] in inputs.reports, "unknown participant input")
        self.premises = unique(value["premises"])
        for p in self.premises.values():
            keys(p, ("id", "statement", "scope", "state", "provenance", "dependsOn"))
            require(
                p["state"] in STATES,
                "runtime/model evidence cannot be self-certified by a sidecar",
            )
            require(p["scope"] == value["id"], "premise belongs to another scenario")
            require(
                isinstance(p["statement"], str) and p["statement"].strip(),
                "empty premise statement",
            )
            keys(p["provenance"], ("source", "reference"))
            require(
                all(isinstance(x, str) and x.strip() for x in p["provenance"].values()),
                "missing provenance",
            )
            require(isinstance(p["dependsOn"], list), "invalid premise dependencies")
            require(
                all(d in self.premises for d in p["dependsOn"]),
                "unknown premise dependency",
            )
        # Resolve the premise DAG iteratively, bounded by the supplied sidecar.
        self.states = {}
        parents = {pid: set(p["dependsOn"]) for pid, p in self.premises.items()}
        children = {pid: [] for pid in parents}
        for pid, deps in parents.items():
            for dep in deps:
                children[dep].append(pid)
        ready = deque(pid for pid, deps in parents.items() if not deps)
        while ready:
            pid = ready.popleft()
            vals = [self.premises[pid]["state"]] + [
                self.states[d] for d in self.premises[pid]["dependsOn"]
            ]
            self.states[pid] = (
                "CONTRADICTED"
                if "CONTRADICTED" in vals
                else "UNKNOWN"
                if "UNKNOWN" in vals
                else "EXPLICIT_ASSUMPTION"
            )
            for child in children[pid]:
                parents[child].remove(pid)
                if not parents[child]:
                    ready.append(child)
        require(len(self.states) == len(self.premises), "cyclic premise dependencies")
        for p in self.participants.values():
            self.ref(p["independence"])
        self.resources = unique(value["resources"])
        for r in self.resources.values():
            keys(
                r,
                (
                    "id",
                    "database",
                    "databaseRelation",
                    "objectMatch",
                    "lockTargetOverlap",
                    "granularity",
                    "premises",
                ),
            )
            require(
                r["database"] is None
                or isinstance(r["database"], str)
                and r["database"],
                "invalid database alias",
            )
            require(
                r["granularity"] in {"UNKNOWN", "OPAQUE_TARGET"},
                "I01 does not resolve physical granularity",
            )
            for prop in ("databaseRelation", "objectMatch", "lockTargetOverlap"):
                require(
                    r[prop] in {"SAME", "DISJOINT", "UNKNOWN"},
                    "invalid resource relation",
                )
            keys(r["premises"], ("database", "object", "overlap"))
            for ref in r["premises"].values():
                self.ref(ref)
        self.selected = unique(value["operations"])
        for op in self.selected.values():
            keys(
                op,
                ("id", "participant", "observation", "resource", "binding", "request"),
            )
            require(
                op["participant"] in self.participants, "unknown operation participant"
            )
            report = self.report(op["participant"])
            require(
                op["observation"] in {o["id"] for o in report["observations"]},
                "unknown observation",
            )
            require(
                op["resource"] is None or op["resource"] in self.resources,
                "unknown opaque resource",
            )
            b = op["binding"]
            keys(b, ("datasource", "database", "enlisted", "premise"))
            require(
                all(
                    b[k] is None or isinstance(b[k], str) and b[k]
                    for k in ("datasource", "database")
                ),
                "invalid binding alias",
            )
            require(
                b["enlisted"] is None or type(b["enlisted"]) is bool,
                "invalid enlistment",
            )
            self.ref(b["premise"])
            q = op["request"]
            keys(q, ("mode", "premise"))
            self.ref(q["premise"])
        require(
            len({(o["participant"], o["observation"]) for o in self.selected.values()})
            == len(self.selected),
            "duplicate selection",
        )
        rule = value["lockRule"]
        keys(rule, ("id", "version", "modes", "compatibility", "blockingPremise"))
        ident(rule["id"])
        require(
            type(rule["version"]) is int and rule["version"] > 0,
            "invalid abstract rule version",
        )
        require(
            isinstance(rule["modes"], list) and len(rule["modes"]) <= 8,
            "abstract mode budget exceeded",
        )
        require(
            len(set(rule["modes"])) == len(rule["modes"]), "duplicate abstract mode"
        )
        for mode in rule["modes"]:
            ident(mode)
        self.ref(rule["blockingPremise"])
        self.compatibility = {}
        require(isinstance(rule["compatibility"], list), "invalid compatibility table")
        for pair in rule["compatibility"]:
            keys(pair, ("left", "right", "result"))
            key = (pair["left"], pair["right"])
            require(
                all(m in rule["modes"] for m in key) and key not in self.compatibility,
                "invalid compatibility pair",
            )
            require(
                pair["result"] in {"INCOMPATIBLE", "COMPATIBLE", "UNKNOWN"},
                "invalid abstract compatibility",
            )
            self.compatibility[key] = pair["result"]
        require(
            all(
                self.compatibility.get((b, a)) == v
                for (a, b), v in self.compatibility.items()
            ),
            "compatibility table must be symmetric",
        )
        for op in self.selected.values():
            require(
                op["request"]["mode"] is None or op["request"]["mode"] in rule["modes"],
                "undefined abstract mode",
            )
        self.cuts = unique(value["cuts"])
        for cut in self.cuts.values():
            keys(cut, ("id", "prefixes", "pending", "holdings", "temporal"))
            require(
                isinstance(cut["prefixes"], dict)
                and set(cut["prefixes"]) == set(self.participants),
                "cut requires every participant prefix",
            )
            for pid, seq in cut["prefixes"].items():
                require(
                    type(seq) is int
                    and 1
                    <= seq
                    <= len(self.report(pid)["transactionModel"]["events"]) + 1,
                    "invalid T01 prefix",
                )
            require(
                isinstance(cut["pending"], list)
                and len(set(cut["pending"])) == len(cut["pending"]),
                "invalid pending requests",
            )
            require(
                all(q in self.selected for q in cut["pending"]),
                "unknown pending operation",
            )
            require(isinstance(cut["holdings"], list), "invalid holdings")
            held = set()
            for hold in cut["holdings"]:
                keys(hold, ("operation", "acquisitionPremise", "retentionPremise"))
                require(
                    hold["operation"] in self.selected
                    and hold["operation"] not in held,
                    "unknown or duplicate holding",
                )
                held.add(hold["operation"])
                self.ref(hold["acquisitionPremise"])
                self.ref(hold["retentionPremise"])
            keys(cut["temporal"], ("kind", "premise"))
            require(
                cut["temporal"]["kind"]
                in {"CONCURRENT", "SERIAL", "OUTER_REQUIRES_NEW", "UNKNOWN"},
                "invalid temporal relation",
            )
            self.ref(cut["temporal"]["premise"])

    def ref(self, ref):
        require(
            ref is None or isinstance(ref, str) and ref in self.premises,
            "unknown premise reference",
        )

    def report(self, participant):
        return self.inputs.reports[self.participants[participant]["input"]]

    def state(self, refs):
        values = [self.states.get(ref, "UNKNOWN") for ref in refs]
        return (
            "CONTRADICTED"
            if "CONTRADICTED" in values
            else "UNKNOWN"
            if not values or "UNKNOWN" in values
            else "EXPLICIT_ASSUMPTION"
        )

    def relation(self, a, b):
        # No lexical matching, datasource-name inference or implicit cross-alias union.
        if a["resource"] is None or a["resource"] != b["resource"]:
            return "UNKNOWN", []
        r = self.resources[a["resource"]]
        refs = list(r["premises"].values())
        if self.state(refs) == "CONTRADICTED":
            return "CONTRADICTED", refs
        props = [r[k] for k in ("databaseRelation", "objectMatch", "lockTargetOverlap")]
        if any(
            r[k] == "DISJOINT"
            and self.state([r["premises"][p]]) == "EXPLICIT_ASSUMPTION"
            for k, p in (
                ("databaseRelation", "database"),
                ("objectMatch", "object"),
                ("lockTargetOverlap", "overlap"),
            )
        ):
            return "DISJOINT", refs
        if (
            props == ["SAME"] * 3
            and r["database"]
            and self.state(refs) == "EXPLICIT_ASSUMPTION"
        ):
            return "SAME", refs
        return "UNKNOWN", refs

    def incompatible(self, a, b):
        return self.compatibility.get(
            (a["request"]["mode"], b["request"]["mode"]), "UNKNOWN"
        )


def namespace(scenario, participant, original, domain="P"):
    p = scenario.participants[participant]
    meta = scenario.inputs.meta[p["input"]]
    return {
        "scenarioId": scenario.value["id"],
        "participantId": participant,
        "inputDigest": meta["sha256"],
        "originalPhysicalId" if domain == "P" else "originalFrameId": original,
    }


def node_id(ns):
    # JSON arrays retain tuple boundaries without delimiter collisions.
    return json.dumps(list(ns.values()), separators=(",", ":"))


def inventory(s):
    operations, apps, cross = [], [], []
    for pid, p in s.participants.items():
        report = s.report(pid)
        tx = report["transactionModel"]
        events = tx["events"]
        indexed = {e["sequence"]: e for e in events}
        for obs in report["observations"]:
            physical = obs["transactionContext"]["physicalId"]
            seq = obs["placement"]["beforeT01Sequence"]
            event = indexed.get(seq)
            wraps = [
                e["sequence"]
                for e in report["timeline"]
                if e.get("observation") == obs["id"]
            ]
            opid = pid + "/" + obs["id"]
            operation = {
                "id": opid,
                "namespace": namespace(s, pid, physical),
                "observation": copy.deepcopy(obs),
                "timelineSequence": wraps[0] if wraps else None,
                "t01Sequence": seq,
                "event": copy.deepcopy(event),
                "normalReturnDependencies": event.get("witness", {}).get(
                    "normalReturnDependencies", []
                )
                if event
                else [],
                "lifetime": {
                    "physicalId": physical,
                    "status": "IDENTIFIED" if physical else "UNKNOWN",
                    "events": [
                        copy.deepcopy(e)
                        for e in events
                        if e.get("entity") == physical
                        and e["kind"]
                        in {"PHYSICAL_BEGIN", "PHYSICAL_END_OUTCOME_UNKNOWN"}
                    ],
                },
                "suspension": {
                    "status": "PRESENT"
                    if any(x["physicalId"] == physical for x in tx["suspensions"])
                    else "UNKNOWN"
                    if physical is None
                    else "ABSENT",
                    "records": [
                        copy.deepcopy(x)
                        for x in tx["suspensions"]
                        if x["physicalId"] == physical
                    ],
                    "events": [
                        copy.deepcopy(e)
                        for e in events
                        if e.get("physicalId") == physical
                        and e["kind"] in {"SUSPEND", "RESUME_CONDITIONAL"}
                    ],
                },
                "selectedForDatabase": any(
                    o["participant"] == pid and o["observation"] == obs["id"]
                    for o in s.selected.values()
                ),
            }
            operations.append(operation)
            cross.append(
                {
                    "type": "EXECUTES_IN",
                    "operation": opid,
                    "frame": namespace(s, pid, obs["frame"], "F"),
                    "physical": operation["namespace"],
                    "certainty": "CONDITIONAL" if physical else "UNKNOWN",
                    "evidence": [opid],
                }
            )
        frames = {f["id"]: f for f in tx["frames"]}
        stack, leaves, frontier = [], [], False
        for e in events:
            frame = frames[e["frame"]]
            if e["kind"] == "FRAME_ENTER":
                if stack:
                    parent = frames[stack[-1]]
                    # T01 resolves a frame independently of transaction boundary success.
                    # Async is a frontier, not a synchronous completion obligation.
                    async_frame = any(
                        u.get("frame") == frame["id"]
                        and u.get("reason") == "ASYNC_EXECUTION_CONTEXT"
                        for u in tx["uncertainties"]
                    )
                    if frame["callSite"] and not async_frame and not frontier:
                        apps.append(
                            {
                                "participant": pid,
                                "caller": parent["id"],
                                "callee": frame["id"],
                                "callerPhysical": parent["duringState"]["physicalId"],
                                "calleePhysical": frame["duringState"]["physicalId"],
                                "enterT01Sequence": e["sequence"],
                                "exitT01Sequence": next(
                                    x["sequence"]
                                    for x in events
                                    if x["frame"] == frame["id"]
                                    and x["kind"] == "FRAME_EXIT"
                                ),
                                "callSite": copy.deepcopy(frame["callSite"]),
                                "normalReturnDependencies": list(leaves),
                            }
                        )
                stack.append(frame["id"])
                cross.append(
                    {
                        "type": "EXECUTES_IN",
                        "frame": namespace(s, pid, frame["id"], "F"),
                        "physical": namespace(
                            s, pid, frame["duringState"]["physicalId"]
                        ),
                        "certainty": "CONDITIONAL"
                        if frame["duringState"]["physicalId"]
                        else "UNKNOWN",
                        "evidence": [
                            {
                                "input": p["input"],
                                "frame": frame["id"],
                                "enterT01Sequence": e["sequence"],
                            }
                        ],
                    }
                )
            elif e["kind"] == "FRAME_EXIT":
                stack.pop()
            elif e["kind"] == "RESOURCE_LEAF_CALL":
                leaves.append(e["sequence"])
            elif e["kind"] == "UNRESOLVED_CALL":
                frontier = True
        for susp in tx["suspensions"]:
            evidence = [
                copy.deepcopy(e) for e in events if e.get("entity") == susp["id"]
            ]
            for typ in ("SUSPENDS_FOR", "RESUME_REQUIRES_COMPLETION"):
                cross.append(
                    {
                        "type": typ,
                        "participant": pid,
                        "suspension": copy.deepcopy(susp),
                        "physical": namespace(s, pid, susp["physicalId"]),
                        "replacement": namespace(s, pid, susp["replacementPhysicalId"]),
                        "frame": namespace(s, pid, susp["frame"], "F"),
                        "certainty": "CONDITIONAL",
                        "evidence": evidence,
                    }
                )
    return operations, apps, cross


def prefix_state(s, pid, before):
    live, suspended = set(), set()
    for e in s.report(pid)["transactionModel"]["events"]:
        if e["sequence"] >= before:
            break
        if e["kind"] == "PHYSICAL_BEGIN":
            live.add(e["entity"])
        elif e["kind"] == "PHYSICAL_END_OUTCOME_UNKNOWN":
            live.remove(e["entity"])
        elif e["kind"] == "SUSPEND":
            suspended.add(e["physicalId"])
        elif e["kind"] == "RESUME_CONDITIONAL":
            suspended.remove(e["physicalId"])
    return live, suspended


def cut_consistency(s, cut, selected, compare=None):
    """Check the whole common prefix, including mutually exclusive held states."""
    problems, unresolved = [], []
    for pid, before in cut["prefixes"].items():
        pending = [
            selected[q]
            for q in cut["pending"]
            if selected[q]["namespace"]["participantId"] == pid
        ]
        for op in pending:
            if op["t01Sequence"] is None:
                unresolved.append("UNPLACED pending request " + op["id"])
            elif op["t01Sequence"] != before:
                problems.append(
                    "pending invocation is not the prefix boundary: " + op["id"]
                )
        if len(pending) > 1:
            problems.append("multiple pending invocations on one synchronous path")
        for e in s.report(pid)["transactionModel"]["events"]:
            if e["sequence"] < before and e["kind"] == "UNRESOLVED_CALL":
                # The proposed continuation contradicts the known prefix, but
                # the unmodeled suffix still prevents an exhaustive negative.
                problems.append("prefix crosses UNRESOLVED_CALL frontier")
                unresolved.append("prefix crosses UNRESOLVED_CALL frontier")
        # Normal-return dependencies are structured witness data, never prose.
        blocked = {o["t01Sequence"] for o in pending}
        for op in selected.values():
            if (
                op["namespace"]["participantId"] == pid
                and op["t01Sequence"] is not None
                and op["t01Sequence"] <= before
            ):
                if blocked.intersection(op["normalReturnDependencies"]):
                    problems.append(
                        "normal return of pending request required by " + op["id"]
                    )
    holds = cut["holdings"]
    for hold in holds:
        op = selected[hold["operation"]]
        seq = op["t01Sequence"]
        if seq is None:
            unresolved.append("UNPLACED acquisition " + op["id"])
        elif seq >= cut["prefixes"][op["namespace"]["participantId"]]:
            problems.append("acquisition has not returned before cut: " + op["id"])
    for i, ha in enumerate(holds):
        for hb in holds[i + 1 :]:
            if compare is not None:
                compare()
            a, b = s.selected[ha["operation"]], s.selected[hb["operation"]]
            oa, ob = selected[ha["operation"]], selected[hb["operation"]]
            if (
                oa["namespace"] != ob["namespace"]
                and s.relation(a, b)[0] == "SAME"
                and s.incompatible(a, b) == "INCOMPATIBLE"
                and s.state(
                    [
                        ha["acquisitionPremise"],
                        ha["retentionPremise"],
                        hb["acquisitionPremise"],
                        hb["retentionPremise"],
                    ]
                )
                == "EXPLICIT_ASSUMPTION"
            ):
                problems.append(
                    "simultaneous incompatible holdings on the same opaque target"
                )
    if (
        cut["temporal"]["kind"] == "SERIAL"
        and s.state([cut["temporal"]["premise"]]) == "EXPLICIT_ASSUMPTION"
    ):
        problems.append("serial lifetimes contradict common overlap")
    # No candidate pair is not evidence of no dependency. W4 requires a
    # separate acquisition/retention hypothesis even when no ledger is built.
    if not cut["pending"] or not cut["holdings"]:
        unresolved.append("W4: NO_ORIENTED_WAIT_HYPOTHESIS")
    return problems, unresolved


def obligations(s, cut, waiter, holder, held, selected, consistency):
    """W1-W8 proof ledger. Missing/contradicted obligations cannot create an edge."""
    a, b = selected[waiter["id"]], selected[holder["id"]]
    ap, bp = a["namespace"]["originalPhysicalId"], b["namespace"]["originalPhysicalId"]
    pa, pb = waiter["participant"], holder["participant"]
    al, asp = prefix_state(s, pa, cut["prefixes"][pa])
    bl, bsp = prefix_state(s, pb, cut["prefixes"][pb])
    result = []

    def add(w, truth, refs, reason, evidence=None):
        state = s.state(refs) if refs else "MODEL_EVIDENCE"
        state = (
            "CONTRADICTED"
            if truth is False or state == "CONTRADICTED"
            else "UNKNOWN"
            if truth is None or state == "UNKNOWN"
            else state
        )
        result.append(
            {
                "id": w,
                "state": state,
                "premises": [r for r in refs if r is not None],
                "reason": reason,
                "evidence": evidence or [a["id"], b["id"]],
            }
        )

    known = (
        ap is not None
        and bp is not None
        and a["t01Sequence"] is not None
        and b["t01Sequence"] is not None
    )
    valid = (
        known
        and a["namespace"] != b["namespace"]
        and ap in al
        and bp in bl
        and ap not in asp
    )
    add(
        "W1",
        bool(valid) if known else None,
        [],
        "Distinct identified P; live at cut; waiter current and unsuspended.",
    )
    bindings = [waiter["binding"], holder["binding"]]
    resource = s.resources.get(waiter["resource"], {})
    bound = all(
        x["datasource"] and x["database"] and x["enlisted"] is True for x in bindings
    )
    domain = bound and bindings[0]["database"] == bindings[1][
        "database"
    ] == resource.get("database")
    add(
        "W2",
        True
        if domain
        else False
        if bound or any(x["enlisted"] is False for x in bindings)
        else None,
        [x["premise"] for x in bindings],
        "Common database, effective datasource and JDBC enlistment explicitly assumed.",
    )
    relation, refs = s.relation(waiter, holder)
    add(
        "W3",
        True
        if relation == "SAME"
        else False
        if relation in {"DISJOINT", "CONTRADICTED"}
        else None,
        refs,
        "Object and opaque lock target overlap are separate explicit premises; granularity remains bounded/UNKNOWN.",
    )
    add(
        "W4",
        True if waiter["request"]["mode"] and holder["request"]["mode"] else None,
        [
            waiter["request"]["premise"],
            holder["request"]["premise"],
            held["acquisitionPremise"],
            held["retentionPremise"],
        ],
        "Waiter request, prior holder acquisition and retention have separate provenance.",
    )
    incompat = s.incompatible(waiter, holder)
    add(
        "W5",
        True
        if incompat == "INCOMPATIBLE"
        else False
        if incompat == "COMPATIBLE"
        else None,
        [s.value["lockRule"]["blockingPremise"]],
        "Versioned abstract incompatible modes and blocking (not NOWAIT/skip/retry).",
    )
    causal = (
        a["t01Sequence"] == cut["prefixes"][pa]
        and b["t01Sequence"] is not None
        and b["t01Sequence"] < cut["prefixes"][pb]
    )
    add(
        "W6",
        True if causal else None,
        [held["retentionPremise"]],
        "Pending waiter at invocation; holder acquisition precedes cut and is retained, not inferred from L/SP/S.",
    )
    temporal = cut["temporal"]["kind"]
    refs = [cut["temporal"]["premise"]]
    if pa != pb:
        refs += [s.participants[p]["independence"] for p in (pa, pb)]
        compatible = temporal == "CONCURRENT"
    else:
        tx = s.report(pa)["transactionModel"]
        compatible = (
            temporal == "OUTER_REQUIRES_NEW"
            and bp in bsp
            and any(
                x["physicalId"] == bp and x["replacementPhysicalId"] == ap
                for x in tx["suspensions"]
            )
        )
    add(
        "W7",
        True if compatible else False if temporal == "SERIAL" else None,
        refs,
        "Common explicit prefix cut with concurrent independent instances or live suspended outer/replacement.",
    )
    problems, unresolved = consistency
    add(
        "W8",
        False if problems else None if unresolved else True,
        [],
        "; ".join(problems + unresolved)
        or "Jointly compatible prefixes; no continuation beyond pending returns or unresolved frontiers.",
    )
    return result


def structural_cycle(edges):
    adjacency = {}
    for e in edges:
        adjacency.setdefault(e["from"], set()).add(e["to"])
    visiting, done = set(), set()
    # Iterative DFS avoids recursion on an inventory with many application frames.
    for root in adjacency:
        if root in done:
            continue
        stack = [(root, iter(adjacency.get(root, ())))]
        visiting.add(root)
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                visiting.remove(node)
                done.add(node)
                stack.pop()
            elif child in visiting:
                return True
            elif child not in done:
                visiting.add(child)
                stack.append((child, iter(adjacency.get(child, ()))))
    return False


def missing_holding_evidence(s, cut, selected, consistency, compare):
    """An omitted prior acquisition is not evidence of absent retention.

    Use the existing W ledger to exclude irrelevant pairs (same P, ended P,
    disjoint targets, etc.). No holder or edge is inferred from the operation.
    """
    missing = []
    held_ids = {h["operation"] for h in cut["holdings"]}
    for hid, holder in s.selected.items():
        op = selected[hid]
        if (
            hid in held_ids
            or op["t01Sequence"] is None
            or op["t01Sequence"] >= cut["prefixes"][holder["participant"]]
        ):
            continue
        for qid in cut["pending"]:
            compare()
            ledger = obligations(
                s,
                cut,
                s.selected[qid],
                holder,
                {"acquisitionPremise": None, "retentionPremise": None},
                selected,
                consistency,
            )
            if not any(w["state"] == "CONTRADICTED" for w in ledger):
                missing.append("W4: acquisition/retention unproven for " + hid)
                break
    return missing


def scope_problems(s):
    """Scope limits apply before any exhaustive negative assessment."""
    unsupported = []
    for key, count in (
        ("inputArtifacts", len(s.inputs.reports)),
        ("participants", len(s.participants)),
        ("resources", len(s.resources)),
        ("selectedOperations", len(s.selected)),
    ):
        if count > SCOPE[key]:
            unsupported.append(key + " exceeds I01 scope " + str(SCOPE[key]))
    for pid in s.participants:
        # Bound the modeled nesting depth, not just the count of sequential calls.
        events = s.report(pid)["transactionModel"]["events"]
        active = 0
        for e in events:
            if e["kind"] == "SUSPEND":
                active += 1
                if active > SCOPE["requiresNewLevels"]:
                    unsupported.append("requiresNewLevels exceeds I01 scope")
            elif e["kind"] == "RESUME_CONDITIONAL":
                active -= 1
    return unsupported


def single_physical_scope(selected):
    """D00 O-D01/O-E01: identified same-P frames exclude inter-P cycles.

    This limited identity proof needs no lock hypotheses or witness cut.
    It does not qualify a supplied incomplete cut or an unplaced operation.
    """
    return (
        len(selected) >= 2
        and all(
            o["namespace"]["originalPhysicalId"] and o["t01Sequence"] is not None
            for o in selected.values()
        )
        and len({node_id(o["namespace"]) for o in selected.values()}) == 1
        and len({o["observation"]["frame"] for o in selected.values()}) >= 2
    )


def structural_exclusion(s, cut, selected, apps, consistency, compare):
    """Prove acyclicity of a supergraph, never infer missing lock facts.

    Every frontier operation is a possible waiter, even if pending is omitted.
    Every prior operation is a possible holder, regardless of W2-W5. W1/W6
    alone exclude pairs. Active application completions are included so that
    a missing outer holding cannot hide a REQUIRES_NEW completion circuit.
    """
    problems, unresolved = consistency
    if not selected or problems or any(not u.startswith("W4:") for u in unresolved):
        return None
    if len(selected) != sum(
        len(s.report(pid)["observations"]) for pid in s.participants
    ):
        # An omitted source operation may hide another acquisition. In contrast
        # to evidence-complete exclusion, this proof needs the whole inventory.
        return None
    for pid, before in cut["prefixes"].items():
        if any(
            e["kind"] == "UNRESOLVED_CALL" and e["sequence"] <= before
            for e in s.report(pid)["transactionModel"]["events"]
        ):
            return None
    if any(
        o["t01Sequence"] is None or o["namespace"]["originalPhysicalId"] is None
        for o in selected.values()
    ):
        return None
    states = {
        pid: prefix_state(s, pid, before) for pid, before in cut["prefixes"].items()
    }
    edges = []
    for q in selected.values():
        qp, physical = (
            q["namespace"]["participantId"],
            q["namespace"]["originalPhysicalId"],
        )
        if (
            q["t01Sequence"] != cut["prefixes"][qp]
            or physical not in states[qp][0]
            or physical in states[qp][1]
        ):
            continue
        for h in selected.values():
            compare()
            hp = h["namespace"]["participantId"]
            if (
                h["namespace"] != q["namespace"]
                and h["t01Sequence"] < cut["prefixes"][hp]
                and h["namespace"]["originalPhysicalId"] in states[hp][0]
            ):
                edges.append(
                    {
                        "from": node_id(q["namespace"]),
                        "to": node_id(h["namespace"]),
                        "type": "POSSIBLE_DB_WAIT",
                        "evidence": [q["id"], h["id"]],
                    }
                )
    for app in apps:
        compare()
        pid = app["participant"]
        if app["enterT01Sequence"] < cut["prefixes"][pid] <= app["exitT01Sequence"]:
            if app["callerPhysical"] is None or app["calleePhysical"] is None:
                return None
            if app["callerPhysical"] != app["calleePhysical"]:
                edges.append(
                    {
                        "from": node_id(namespace(s, pid, app["callerPhysical"])),
                        "to": node_id(namespace(s, pid, app["calleePhysical"])),
                        "type": "APPLICATION_COMPLETION",
                        "evidence": [copy.deepcopy(app)],
                    }
                )
    if structural_cycle(edges):
        return None
    return {
        "kind": "STRUCTURAL_EXCLUSION",
        "rule": "ACYCLIC_CAUSAL_SUPERGRAPH",
        "operationRefs": sorted(o["id"] for o in selected.values()),
        "prefixes": copy.deepcopy(cut["prefixes"]),
        "upperBoundEdges": edges,
        "scope": "Selected operations at this cut; no lock or runtime absence asserted.",
    }


def _derive_report(raw_inputs, sidecar):
    """Internal F02 diagnostics and v1 comparison count; never a wire encoder."""
    require(isinstance(sidecar, dict), "sidecar must be an object")
    if len(encoded(sidecar)) > BUDGETS["sidecarBytes"]:
        raise BudgetExceeded("sidecar exceeds 2 MiB; coverage INCOMPLETE")
    declarations = unique(sidecar.get("inputs", []))
    inputs = Inputs(raw_inputs, declarations)
    s = Scenario(sidecar, inputs)
    operations, app_sources, cross = inventory(s)
    if len(cross) > BUDGETS["serializedEdges"]:
        raise BudgetExceeded(
            "serialized cross-layer edge budget exceeded; coverage INCOMPLETE"
        )
    opmap = {o["id"]: o for o in operations}
    selected = {
        key: opmap[x["participant"] + "/" + x["observation"]]
        for key, x in s.selected.items()
    }
    unsupported = scope_problems(s)
    claims, unknowns, dbedges, appedges, candidates = [], [], [], [], []

    def claim(category, ops, certainty, premises=(), **fields):
        record = {
            "id": "C" + str(len(claims) + 1),
            "category": category,
            "rule": {"id": "mana-s02-i01", "version": 1},
            "certainty": certainty,
            "operationRefs": list(ops),
            "premises": sorted({r for r in premises if r is not None}),
            "evidence": list(ops),
            "modelPremises": [
                {
                    "id": "M_" + str(len(claims) + 1),
                    "statement": "Referenced syntax, contexts and causal positions are those of the validated input model; execution and normal returns remain conditional.",
                    "scope": s.value["id"],
                    "state": "MODEL_EVIDENCE",
                    "provenance": {
                        "source": "validated-input-projection",
                        "reference": list(ops),
                    },
                    "dependsOn": [],
                }
            ],
            "propertyCertainty": {
                "runtimeExecution": "UNKNOWN",
                "runtimeWait": "UNKNOWN",
            },
            "excludedProperties": [
                "runtime lock acquisition",
                "runtime identity",
                "commit/rollback",
                "confirmed deadlock",
            ],
            **fields,
        }
        if (
            category in {"DB_WAIT_DEPENDENCY", "APPLICATION_WAIT_DEPENDENCY"}
            and len(dbedges) + len(appedges) + len(cross) >= BUDGETS["serializedEdges"]
        ):
            raise BudgetExceeded("serialized edge budget exceeded; coverage INCOMPLETE")
        claims.append(record)
        return record

    for op in operations:
        claim(
            "RESOURCE_OPERATION", [op["id"]], "STATIC_SYNTAX", endpoint=op["namespace"]
        )
        if op["observation"]["operationType"] == "EXPLICIT_LOCK_REQUEST":
            claim(
                "LOCK_REQUEST_CANDIDATE",
                [op["id"]],
                "STATIC_SYNTAX",
                origin="EXPLICIT_REQUEST_SYNTAX",
                endpoint=op["namespace"],
                mode="UNKNOWN",
                acquisition="UNKNOWN",
                retention="UNKNOWN",
            )
        if not op["selectedForDatabase"]:
            unknowns.append(
                {"operation": op["id"], "reason": "OUTSIDE_SELECTED_DATABASE_SCOPE"}
            )
        if op["t01Sequence"] is None:
            unknowns.append(
                {
                    "operation": op["id"],
                    "reason": "CAUSAL_ORDER_OR_BODY_UNPROVEN",
                    "limits": op["observation"]["limits"],
                }
            )
    for key, selection in s.selected.items():
        if (
            selection["request"]["mode"]
            and s.state([selection["request"]["premise"]]) == "EXPLICIT_ASSUMPTION"
        ):
            claim(
                "LOCK_REQUEST_CANDIDATE",
                [selected[key]["id"]],
                "CONDITIONAL",
                [selection["request"]["premise"]],
                origin="EXPLICIT_SCENARIO_RULE",
                endpoint=selected[key]["namespace"],
                mode=selection["request"]["mode"],
                abstractRule=copy.deepcopy(s.value["lockRule"]),
                acquisition="UNKNOWN",
                retention="UNKNOWN",
            )
    for key, selection in s.selected.items():
        missing = []
        binding = selection["binding"]
        if not (
            binding["datasource"]
            and binding["database"]
            and binding["enlisted"] is True
            and s.state([binding["premise"]]) == "EXPLICIT_ASSUMPTION"
        ):
            missing.append("W2")
        if s.relation(selection, selection)[0] == "UNKNOWN":
            missing.append("W3")
        if (
            not selection["request"]["mode"]
            or s.state([selection["request"]["premise"]]) != "EXPLICIT_ASSUMPTION"
        ):
            missing.append("W4")
        if s.state([s.value["lockRule"]["blockingPremise"]]) != "EXPLICIT_ASSUMPTION":
            missing.append("W5")
        if missing:
            unknowns.append(
                {
                    "operation": selected[key]["id"],
                    "reason": "DATABASE_PREMISES_UNPROVEN",
                    "missingObligations": missing,
                }
            )
    comparisons = 0
    proof_comparisons = 0
    cut_checks = {}

    def compare():
        nonlocal comparisons
        comparisons += 1
        if comparisons > BUDGETS["candidateComparisons"]:
            raise BudgetExceeded(
                "candidate comparison budget exceeded; coverage INCOMPLETE"
            )

    if not unsupported:
        items = list(s.selected.items())
        for i, (ak, a) in enumerate(items):
            for bk, b in items[i + 1 :]:
                compare()
                if (
                    s.relation(a, b)[0] == "SAME"
                    and s.incompatible(a, b) == "INCOMPATIBLE"
                    and s.state(
                        [
                            a["request"]["premise"],
                            b["request"]["premise"],
                            s.value["lockRule"]["blockingPremise"],
                        ]
                    )
                    == "EXPLICIT_ASSUMPTION"
                ):
                    claim(
                        "LOCK_CONFLICT_CANDIDATE",
                        [selected[ak]["id"], selected[bk]["id"]],
                        "CONDITIONAL",
                        s.relation(a, b)[1]
                        + [
                            a["request"]["premise"],
                            b["request"]["premise"],
                            s.value["lockRule"]["blockingPremise"],
                        ],
                        resource=a["resource"],
                        orientation="UNORIENTED",
                        holder="UNKNOWN",
                    )
        for cut in s.cuts.values():
            consistency = cut_consistency(s, cut, selected, compare)
            cut_checks[cut["id"]] = consistency
            if not cut["pending"] or not cut["holdings"]:
                unknowns.append(
                    {
                        "cut": cut["id"],
                        "reason": "NO_ORIENTED_WAIT_HYPOTHESIS",
                        "missingObligations": ["W4"],
                    }
                )
            for qid in cut["pending"]:
                for held in cut["holdings"]:
                    compare()
                    waiter, holder = s.selected[qid], s.selected[held["operation"]]
                    ledger = obligations(
                        s, cut, waiter, holder, held, selected, consistency
                    )
                    qualified = all(
                        w["state"] in {"MODEL_EVIDENCE", "EXPLICIT_ASSUMPTION"}
                        for w in ledger
                    )
                    candidate = {
                        "id": "W" + str(len(candidates) + 1),
                        "cut": cut["id"],
                        "waiter": qid,
                        "holder": held["operation"],
                        "obligations": ledger,
                        "status": "QUALIFIED"
                        if qualified
                        else "EXCLUDED"
                        if any(w["state"] == "CONTRADICTED" for w in ledger)
                        else "UNKNOWN",
                    }
                    candidates.append(candidate)
                    if qualified:
                        a, b = selected[qid], selected[held["operation"]]
                        refs = [p for w in ledger for p in w["premises"]]
                        c = claim(
                            "DB_WAIT_DEPENDENCY",
                            [a["id"], b["id"]],
                            "CONDITIONAL",
                            refs,
                            waiter=a["namespace"],
                            blocker=b["namespace"],
                            resource=waiter["resource"],
                            cut=cut["id"],
                            candidate=candidate["id"],
                            obligations=ledger,
                            request={
                                "operation": a["id"],
                                "mode": waiter["request"]["mode"],
                                "pending": "EXPLICIT_ASSUMPTION",
                            },
                            holding={
                                "operation": b["id"],
                                "mode": holder["request"]["mode"],
                                "acquisitionPremise": held["acquisitionPremise"],
                                "retentionPremise": held["retentionPremise"],
                            },
                        )
                        dbedges.append(
                            {
                                "from": node_id(a["namespace"]),
                                "to": node_id(b["namespace"]),
                                "claim": c["id"],
                                "cut": cut["id"],
                                "resource": waiter["resource"],
                                "certainty": "CONDITIONAL",
                            }
                        )
                    else:
                        unknowns.append(
                            {
                                "candidate": candidate["id"],
                                "cut": cut["id"],
                                "reason": candidate["status"],
                                "missingObligations": [
                                    w["id"] for w in ledger if w["state"] == "UNKNOWN"
                                ],
                                "contradictedObligations": [
                                    w["id"]
                                    for w in ledger
                                    if w["state"] == "CONTRADICTED"
                                ],
                            }
                        )
    for app in app_sources:
        a = namespace(s, app["participant"], app["caller"], "F")
        b = namespace(s, app["participant"], app["callee"], "F")
        c = claim(
            "APPLICATION_WAIT_DEPENDENCY",
            [],
            "CONDITIONAL",
            caller=a,
            callee=b,
            callerPhysical=namespace(s, app["participant"], app["callerPhysical"]),
            calleePhysical=namespace(s, app["participant"], app["calleePhysical"]),
            resource={
                "kind": "FRAME_COMPLETION",
                "granularity": "FRAME",
                "database": "NOT_APPLICABLE",
            },
            source=copy.deepcopy(app),
        )
        c["evidence"] = [copy.deepcopy(app)]
        c["modelPremises"][0]["provenance"]["reference"] = [copy.deepcopy(app)]
        c["completionPremises"] = [
            "Resolved synchronous invocation is reached after the recorded prior normal returns.",
            "Caller progression requires the callee's normal completion; no runtime blocked thread is asserted.",
        ]
        appedges.append(
            {
                "from": node_id(a),
                "to": node_id(b),
                "claim": c["id"],
                "certainty": "CONDITIONAL",
            }
        )
    if len(dbedges) + len(appedges) + len(cross) > BUDGETS["serializedEdges"]:
        raise BudgetExceeded("serialized edge budget exceeded; coverage INCOMPLETE")
    cut_results = []
    for cut in s.cuts.values():
        edges = [e for e in dbedges if e["cut"] == cut["id"]]
        problems, unresolved = (
            cut_checks[cut["id"]] if not unsupported else ([], ["UNSUPPORTED_SCOPE"])
        )
        missing_holds = (
            missing_holding_evidence(s, cut, selected, (problems, unresolved), compare)
            if not unsupported
            else []
        )
        cross_risk = False
        for edge in edges:
            c = next(c for c in claims if c["id"] == edge["claim"])
            w, h = [opmap[o] for o in c["operationRefs"]]
            # A same-instance completion circuit needs a real active call interval.
            for app in app_sources:
                pid = app["participant"]
                if (
                    w["namespace"]["participantId"]
                    == h["namespace"]["participantId"]
                    == pid
                    and app["callerPhysical"] == h["namespace"]["originalPhysicalId"]
                    and app["calleePhysical"] == w["namespace"]["originalPhysicalId"]
                    and app["enterT01Sequence"]
                    < cut["prefixes"][pid]
                    <= app["exitT01Sequence"]
                ):
                    cross_risk = True
        result = (
            "UNKNOWN"
            if unsupported or unresolved
            else "NO_CYCLE_IN_MODELED_SCENARIO"
            if problems
            else "CONDITIONAL_CYCLE_RISK"
            if structural_cycle(edges)
            else "CONDITIONAL_CROSS_LAYER_COMPLETION_RISK"
            if cross_risk
            else "UNKNOWN"
            if missing_holds
            or any(
                c["status"] == "UNKNOWN" and c["cut"] == cut["id"] for c in candidates
            )
            else "NO_CYCLE_IN_MODELED_SCENARIO"
        )
        proof = None
        if result == "NO_CYCLE_IN_MODELED_SCENARIO":
            proof = {
                "kind": "EVIDENCE_COMPLETE_EXCLUSION",
                "rule": "QUALIFIED_OR_CONTRADICTED_CANDIDATES",
                "candidateRefs": [c["id"] for c in candidates if c["cut"] == cut["id"]],
            }
        elif result == "UNKNOWN" and not unsupported:
            before_proof = comparisons
            proof = structural_exclusion(
                s, cut, selected, app_sources, (problems, unresolved), compare
            )
            proof_comparisons += comparisons - before_proof
            if proof is not None:
                result = "NO_CYCLE_IN_MODELED_SCENARIO"
        unresolved = list(unresolved) + missing_holds
        for candidate in candidates:
            if candidate["cut"] == cut["id"] and candidate["status"] == "UNKNOWN":
                unresolved.extend(
                    w["id"] + ": " + w["reason"]
                    for w in candidate["obligations"]
                    if w["state"] == "UNKNOWN"
                )
        cut_results.append(
            {
                "cut": cut["id"],
                "result": result,
                "contradictions": problems,
                "unknowns": unresolved,
                "claims": [e["claim"] for e in edges],
                "exclusionProof": proof,
            }
        )
        if missing_holds:
            unknowns.append(
                {
                    "cut": cut["id"],
                    "reason": "PRIOR_HOLDING_EVIDENCE_UNPROVEN",
                    "missingObligations": ["W4"],
                }
            )
    if unsupported:
        outcome = "UNKNOWN"
    elif any(r["result"] == "CONDITIONAL_CYCLE_RISK" for r in cut_results):
        outcome = "CONDITIONAL_CYCLE_RISK"
    elif any(
        r["result"] == "CONDITIONAL_CROSS_LAYER_COMPLETION_RISK" for r in cut_results
    ):
        outcome = "CONDITIONAL_CROSS_LAYER_COMPLETION_RISK"
    elif structural_cycle(
        dbedges
        + [
            e
            for r in cut_results
            if r["exclusionProof"]
            and r["exclusionProof"]["kind"] == "STRUCTURAL_EXCLUSION"
            for e in r["exclusionProof"]["upperBoundEdges"]
            if e["type"] == "POSSIBLE_DB_WAIT"
        ]
    ):
        outcome = "CYCLE_FEASIBILITY_UNKNOWN"
    elif cut_results and all(
        r["result"] == "NO_CYCLE_IN_MODELED_SCENARIO" for r in cut_results
    ):
        outcome = "NO_CYCLE_IN_MODELED_SCENARIO"
    else:
        outcome = (
            "NO_CYCLE_IN_MODELED_SCENARIO"
            if not s.cuts and single_physical_scope(selected)
            else "UNKNOWN"
        )
    reasons = list(unsupported)
    if not s.cuts:
        reasons.append("NO_WITNESS_CUT")
        unknowns.append(
            {
                "reason": "NO_WITNESS_CUT",
                "missingObligations": ["W2", "W3", "W4", "W5", "W6", "W7", "W8"],
            }
        )
    if any(not o["selectedForDatabase"] for o in operations):
        reasons.append("OPERATIONS_OUTSIDE_SELECTED_DATABASE_SCOPE")
    if unknowns or any(c["status"] == "UNKNOWN" for c in candidates):
        reasons.append("UNRESOLVED_DATA_OR_CAUSALITY")
    if not s.selected:
        reasons.append("NO_DATABASE_OPERATIONS_SELECTED")
    for pid in s.participants:
        if s.report(pid)["transactionModel"]["uncertainties"]:
            reasons.append("T01_UNCERTAINTIES:" + pid)

    def nodes(edges, namespaces):
        used = {e[k] for e in edges for k in ("from", "to")}
        return [{"id": key, "namespace": namespaces[key]} for key in sorted(used)]

    physical = {
        node_id(o["namespace"]): o["namespace"]
        for o in operations
        if o["namespace"]["originalPhysicalId"] is not None
    }
    frames = {
        node_id(namespace(s, pid, f["id"], "F")): namespace(s, pid, f["id"], "F")
        for pid in s.participants
        for f in s.report(pid)["transactionModel"]["frames"]
    }
    # Include all known P nodes, including isolated ones, preserving namespace identity.
    for pid in s.participants:
        for p in s.report(pid)["transactionModel"]["physicalTransactions"]:
            ns = namespace(s, pid, p["id"])
            physical[node_id(ns)] = ns
    proof_edge_count = sum(
        len(r["exclusionProof"].get("upperBoundEdges", []))
        for r in cut_results
        if r["exclusionProof"]
    )
    serialized_edges = len(dbedges) + len(appedges) + len(cross) + proof_edge_count
    if serialized_edges > BUDGETS["serializedEdges"]:
        raise BudgetExceeded(
            "serialized proof/graph edge budget exceeded; coverage INCOMPLETE"
        )
    report = {
        "schema": "mana.wait-dependency/v1",
        "status": "CONDITIONAL_STATIC_SCENARIO",
        "inputs": list(inputs.meta.values()),
        "scenario": copy.deepcopy(sidecar),
        "operations": operations,
        "claims": claims,
        "waitCandidates": candidates,
        "databaseGraph": {
            "nodes": [{"id": k, "namespace": v} for k, v in sorted(physical.items())],
            "edges": dbedges,
        },
        "applicationGraph": {"nodes": nodes(appedges, frames), "edges": appedges},
        "crossLayerRelations": cross,
        "unknowns": unknowns,
        "limits": list(LIMITS),
        "coverage": {
            "status": "INCOMPLETE" if reasons else "COMPLETE_MODELED_SCOPE",
            "reasons": sorted(set(reasons)),
            "scope": dict(SCOPE),
            "scopeStatus": "UNSUPPORTED" if unsupported else "SUPPORTED",
            "budgets": dict(BUDGETS),
            "candidateComparisons": comparisons,
            "serializedEdges": serialized_edges,
            "inventoryOperations": len(operations),
            "selectedOperations": len(selected),
            "globalRiskAbsence": "NOT_ASSERTED",
            "runtime": "NOT_RUN",
        },
        "assessment": {
            "result": outcome,
            "cuts": cut_results,
            "scope": "Only selected operations, explicit abstract rules and listed witness cuts.",
            "exclusionProof": {
                "kind": "STRUCTURAL_EXCLUSION",
                "rule": "SINGLE_PHYSICAL_IDENTITY",
                "operationRefs": sorted(o["id"] for o in selected.values()),
            }
            if outcome == "NO_CYCLE_IN_MODELED_SCENARIO" and not s.cuts
            else None,
        },
    }
    if len(encoded(report)) > BUDGETS["sidecarBytes"]:
        raise BudgetExceeded(
            "S02 report exceeds 2 MiB sidecar budget; coverage INCOMPLETE"
        )
    return report, comparisons - proof_comparisons


def build_report(raw_inputs, sidecar):
    """Produce the original public v1 shape, with source proofs kept internal.

    Extra proof work still consumes the F02 comparison/edge budgets. The wire
    counters describe v1 candidate comparisons and actually serialized edges.
    """
    report, candidate_comparisons = _derive_report(raw_inputs, sidecar)
    report["assessment"].pop("exclusionProof")
    for cut in report["assessment"]["cuts"]:
        cut.pop("exclusionProof")
    report["coverage"]["candidateComparisons"] = candidate_comparisons
    report["coverage"]["serializedEdges"] = (
        len(report["databaseGraph"]["edges"])
        + len(report["applicationGraph"]["edges"])
        + len(report["crossLayerRelations"])
    )
    return report
