"""Source observations at T01 frontiers; no transaction or lock state machine."""

import copy

from .model import validate_model
from .resource_leaf import AUTOWIRED, JDBC, binding_blocker, sql_operation

LIMITS = [
    "Observed syntax is not proof of execution, enlistment or an acquired lock.",
    "T01 scenario premises and unresolved continuations are preserved unchanged.",
    "Datasource, runtime resource identity and row/table lock granularity are UNKNOWN.",
    "No database query, runtime capture, commit/rollback or lock release is inferred.",
    "Only a direct unqualified Autowired JdbcTemplate field and one SQL literal argument are supported.",
]


LEAF_LIMITS = LIMITS[:-1] + [
    "Only a direct JdbcTemplate field (injected observation or positively bound allocation) and one SQL literal argument are supported."
]


def _limits(transaction):
    return LEAF_LIMITS if "resourceLeafExtension" in transaction else LIMITS


def _method(facts, frame):
    matches = [
        (cls, method)
        for cls in facts["classes"]
        for method in cls["methods"]
        if cls["name"] + "#" + method["name"] + "()" == frame["calleeMethod"]
        and method["arity"] == 0
    ]
    if len(matches) != 1 or matches[0][1]["evidence"] != frame["evidence"]:
        raise ValueError("resource facts do not match T01 method evidence")
    return matches[0]


def _observation(cls, method, call, frame, state, before):
    receiver = call["receiver"]
    field_name = receiver.removeprefix("this.")
    fields = [f for f in cls["fields"] if f["name"] == field_name]
    field = fields[0] if len(fields) == 1 else None
    annotations = field["annotations"] if field else []
    binding = bool(
        field
        and field["type"] == JDBC
        and not cls["parents"]
        and (
            binding_blocker(field) is None
            or (
                not field["initialized"]
                and len(annotations) == 1
                and annotations[0]["type"] == AUTOWIRED
                and not annotations[0]["args"]
            )
        )
        and receiver in {field_name, "this." + field_name}
        and not method["hazards"]
    )
    args = call.get("arguments", [])
    supported = (
        binding
        and call["name"] in {"execute", "update", "queryForList"}
        and call["arity"] == len(args) == 1
        and args[0]["kind"] == "STRING_LITERAL"
    )
    sql = args[0]["literal"] if supported else None
    kind, name = sql_operation(sql, call["name"])
    return {
        "frame": frame["id"],
        "method": frame["calleeMethod"],
        "applicationOperation": {"receiver": receiver, "method": call["name"]},
        "callSite": copy.deepcopy(call["evidence"]),
        "operationType": kind,
        "sqlLiteral": sql,
        "resource": {
            "status": "LEXICAL_SQL_IDENTIFIER" if name else "UNKNOWN",
            "name": name,
            "runtimeIdentity": "UNKNOWN",
            "lockGranularity": "UNKNOWN",
        },
        "transactionContext": copy.deepcopy(state),
        "datasource": {"status": "UNKNOWN", "id": None},
        "enlistment": "UNKNOWN",
        "lockAcquired": "UNKNOWN",
        "certainty": "CONDITIONAL" if before is not None else "UNKNOWN",
        "placement": {
            "status": "T01_FRONTIER" if before is not None else "UNPLACED",
            "beforeT01Sequence": before,
        },
        "evidence": [copy.deepcopy(call["evidence"])]
        + ([copy.deepcopy(field["evidence"])] if field else [])
        + ([copy.deepcopy(args[0]["evidence"])] if supported else []),
        "premises": ["T01 conditional path reaches this invocation syntax."]
        if before is not None
        else [],
        "limits": [
            "JDBC_DATASOURCE_BINDING_NOT_MODELED",
            "EXECUTION_AND_LOCK_OWNERSHIP_NOT_OBSERVED",
        ]
        + (["SQL_OR_RESOURCE_API_UNRESOLVED"] if kind == "UNKNOWN" else [])
        + (["T01_BODY_OR_CONTINUATION_NOT_TRAVERSED"] if before is None else []),
    }


def _project(transaction, facts):
    validate_model(transaction)
    hashes = {e["path"]: e["sha256"] for e in transaction.get("evidence", [])}

    def verify(value):
        if isinstance(value, dict):
            if {"file", "sha256", "start", "end", "line"} <= value.keys():
                if hashes.get(value["file"]) != value["sha256"]:
                    raise ValueError("resource source hash differs from T01 snapshot")
            for item in value.values():
                verify(item)
        elif isinstance(value, list):
            for item in value:
                verify(item)

    verify(facts)
    frames = {f["id"]: f for f in transaction["frames"]}
    observations, timeline, stack = [], [], []
    live, suspended = set(), set()
    leaf_dependencies = []
    if (
        "resourceLeafExtension" in transaction
        and transaction["resourceLeafExtension"]["sourceFacts"] != facts
    ):
        raise ValueError("resource source facts differ from T01 leaf snapshot")
    for event in transaction["events"]:
        frame = frames[event["frame"]]
        kind = event["kind"]
        if kind == "FRAME_ENTER":
            stack.append(copy.deepcopy(frame["duringState"]))
        elif kind == "PHYSICAL_BEGIN":
            live.add(event["entity"])
        elif kind == "PHYSICAL_END_OUTCOME_UNKNOWN":
            live.remove(event["entity"])
        elif kind == "SUSPEND":
            suspended.add(event["physicalId"])
        elif kind == "RESUME_CONDITIONAL":
            suspended.remove(event["physicalId"])
        elif kind in {"UNRESOLVED_CALL", "RESOURCE_LEAF_CALL"}:
            cls, method = _method(facts, frame)
            calls = [c for c in method["calls"] if c["evidence"] == event["callSite"]]
            if len(calls) != 1:
                raise ValueError("T01 frontier has no unique source invocation")
            if (calls[0]["receiver"], calls[0]["name"]) != (
                event["receiver"],
                event["method"],
            ):
                raise ValueError("T01 frontier invocation differs from source facts")
            state = stack[-1]
            physical = state["physicalId"]
            if physical is not None and (physical not in live or physical in suspended):
                raise ValueError(
                    "resource operation requires a live current T01 transaction"
                )
            observation = _observation(
                cls, method, calls[0], frame, state, event["sequence"]
            )
            if kind == "RESOURCE_LEAF_CALL":
                observation["placement"]["status"] = "T01_RESOURCE_LEAF"
                observation["premises"].extend(event["witness"]["premises"])
            if leaf_dependencies:
                observation["premises"].append(
                    "Normal returns required from prior T01 resource leaf calls: "
                    + str(leaf_dependencies)
                )
            if kind == "RESOURCE_LEAF_CALL":
                leaf_dependencies.append(event["sequence"])
            observation["id"] = "O" + str(len(observations) + 1)
            observations.append(observation)
            timeline.append(
                {"kind": "RESOURCE_OPERATION", "observation": observation["id"]}
            )
        elif kind == "FRAME_EXIT":
            stack.pop()
            if stack:
                stack[-1] = copy.deepcopy(frame["afterState"])
        timeline.append({"kind": "T01_EVENT", "event": copy.deepcopy(event)})

    # Untraversed bodies/suffixes retain syntax, never an invented causal position/P.
    for frame in transaction["frames"]:
        cls, method = _method(facts, frame)
        for call in method["calls"]:
            if any(
                o["frame"] == frame["id"] and o["callSite"] == call["evidence"]
                for o in observations
            ):
                continue
            field_name = call["receiver"].removeprefix("this.")
            if not any(
                f["name"] == field_name
                and (
                    f["type"] == JDBC or f["type"].startswith("UNKNOWN_TYPE_PARAMETER:")
                )
                for f in cls["fields"]
            ):
                continue
            observation = _observation(
                cls,
                method,
                call,
                frame,
                {"kind": "UNKNOWN", "physicalId": None, "manager": None},
                None,
            )
            observation["id"] = "O" + str(len(observations) + 1)
            observations.append(observation)
    for sequence, event in enumerate(timeline, 1):
        event["sequence"] = sequence
    return observations, timeline


def build_timeline(transaction, facts):
    observations, timeline = _project(transaction, facts)
    return {
        "schema": "mana.resource-timeline/v1",
        "status": "CONDITIONAL_STATIC_SCENARIO",
        "transactionModel": copy.deepcopy(transaction),
        "sourceFacts": copy.deepcopy(facts),
        "observations": observations,
        "timeline": timeline,
        "limits": list(_limits(transaction)),
    }


def validate_timeline(report):
    """Check T01 first, then exact source/context/causal projection; no runtime claim."""
    if (
        set(report)
        != {
            "schema",
            "status",
            "transactionModel",
            "sourceFacts",
            "observations",
            "timeline",
            "limits",
        }
        or report["schema"] != "mana.resource-timeline/v1"
    ):
        raise ValueError("invalid resource timeline schema")
    observations, timeline = _project(report["transactionModel"], report["sourceFacts"])
    if report["status"] != "CONDITIONAL_STATIC_SCENARIO" or report["limits"] != _limits(
        report["transactionModel"]
    ):
        raise ValueError("invalid resource timeline certainty/limits")
    if report["observations"] != observations or report["timeline"] != timeline:
        raise ValueError("resource timeline differs from T01 causal/source projection")
