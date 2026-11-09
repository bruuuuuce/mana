"""Source observations at T01 frontiers; no transaction or lock state machine."""

import copy
import json

from .entry import method_key, shadows_receiver
from .model import validate_model
from .resource_leaf import AUTOWIRED, JDBC, binding_blocker, sql_operation

JDBC_OPERATIONS = "org.springframework.jdbc.core.JdbcOperations"
JDBC_APIS = {"query", "queryForObject", "queryForList", "update", "batchUpdate", "execute"}
QUALIFIER = "org.springframework.beans.factory.annotation.Qualifier"


def _required_autowired(method):
    for annotation in method.get("annotations", []):
        if annotation["type"] == AUTOWIRED:
            value = annotation.get("args", {}).get("required", {}).get("literal", True)
            return value is True
    return False


def _has_field_reassignment(cls, name):
    return any(
        assignment["target"].removeprefix("this.") == name
        for method in cls["methods"]
        for assignment in method.get("assignments", [])
    )

LIMITS = [
    "Observed syntax is not proof of execution, enlistment or an acquired lock.",
    "T01 scenario premises and unresolved continuations are preserved unchanged.",
    "Datasource, runtime resource identity and row/table lock granularity are UNKNOWN.",
    "No database query, runtime capture, commit/rollback or lock release is inferred.",
    "Only a direct unqualified Autowired JdbcTemplate field and one SQL literal argument are supported.",
]

V2_LIMITS = LIMITS[:-1] + [
    "Static JDBC receiver bindings and supported SQL APIs are recorded with explicit uncertainty; datasource and runtime enlistment are not resolved."
]

LEAF_LIMITS = V2_LIMITS[:-1] + [
    "Only a directly resolved JdbcTemplate injection/allocation and catalogued non-callback overload with one SQL literal argument can continue T01 traversal."
]
LEGACY_LEAF_LIMITS = LIMITS[:-1] + [
    "Only a direct JdbcTemplate field (injected observation or positively bound allocation) and one SQL literal argument are supported."
]


def _limits(transaction):
    return LEAF_LIMITS if "resourceLeafExtension" in transaction else V2_LIMITS


def _legacy_observations(observations, facts):
    """Recreate the original direct-field-only v1 observation semantics."""
    result = []
    for observation in observations:
        # v1 retained UNPLACED JdbcTemplate field observations, but its bounded
        # receiver inventory did not include newly supported JdbcOperations,
        # constructor, setter, alias, or local-binding observations.
        if observation["placement"]["beforeT01Sequence"] is None:
            matches = [
                (cls, call)
                for cls in facts["classes"] for method in cls["methods"] for call in method["calls"]
                if call["evidence"] == observation["callSite"]
            ]
            if len(matches) != 1:
                raise ValueError("legacy unplaced call has no unique source invocation")
            cls, call = matches[0]
            field = next(
                (f for f in cls["fields"] if f["name"] == call["receiver"].removeprefix("this.")),
                None,
            )
            if field is None or not (
                field["type"] == JDBC
                or field["type"].startswith("UNKNOWN_TYPE_PARAMETER:")
            ):
                continue
        if observation["placement"]["status"] == "T01_RESOURCE_LEAF":
            legacy = {k: copy.deepcopy(v) for k, v in observation.items() if k != "jdbcBinding"}
            matches = [
                (cls, method, call)
                for cls in facts["classes"] for method in cls["methods"] for call in method["calls"]
                if call["evidence"] == observation["callSite"]
            ]
            if len(matches) != 1:
                raise ValueError("legacy resource leaf has no unique source invocation")
            cls, _, call = matches[0]
            field = next((f for f in cls["fields"] if f["name"] == call["receiver"].removeprefix("this.")), None)
            legacy["evidence"] = [copy.deepcopy(call["evidence"])]
            if field:
                legacy["evidence"].append(copy.deepcopy(field["evidence"]))
            args = call.get("arguments", [])
            if args and args[0]["kind"] == "STRING_LITERAL":
                legacy["evidence"].append(copy.deepcopy(args[0]["evidence"]))
            result.append(legacy)
            continue
        matches = [
            (cls, method, call)
            for cls in facts["classes"]
            for method in cls["methods"]
            for call in method["calls"]
            if call["evidence"] == observation["callSite"]
        ]
        if len(matches) != 1:
            raise ValueError("legacy resource call has no unique source invocation")
        cls, method, call = matches[0]
        receiver = call["receiver"]
        fields = [f for f in cls["fields"] if f["name"] == receiver.removeprefix("this.")]
        field = fields[0] if len(fields) == 1 else None
        annotations = field["annotations"] if field else []
        binding = bool(
            field and not shadows_receiver(method, receiver)
            and field["type"] == JDBC and not cls["parents"]
            and not method["hazards"] and receiver in {field["name"], "this." + field["name"]}
            and (
                binding_blocker(field) is None
                or (
                    not field["initialized"] and len(annotations) == 1
                    and annotations[0]["type"] == AUTOWIRED and not annotations[0]["args"]
                )
            )
        )
        args = call.get("arguments", [])
        supported = binding and call["name"] in {"execute", "update", "queryForList"} \
            and call["arity"] == len(args) == 1 and args[0]["kind"] == "STRING_LITERAL"
        sql = args[0]["literal"] if supported else None
        kind, name = sql_operation(sql, call["name"])
        legacy = {k: copy.deepcopy(v) for k, v in observation.items() if k != "jdbcBinding"}
        legacy["operationType"] = kind
        legacy["sqlLiteral"] = sql
        legacy["resource"] = {
            "status": "LEXICAL_SQL_IDENTIFIER" if name else "UNKNOWN",
            "name": name, "runtimeIdentity": "UNKNOWN", "lockGranularity": "UNKNOWN",
        }
        legacy["evidence"] = [copy.deepcopy(call["evidence"])]
        if field:
            legacy["evidence"].append(copy.deepcopy(field["evidence"]))
        if supported:
            legacy["evidence"].append(copy.deepcopy(args[0]["evidence"]))
        legacy["limits"] = [
            "JDBC_DATASOURCE_BINDING_NOT_MODELED",
            "EXECUTION_AND_LOCK_OWNERSHIP_NOT_OBSERVED",
        ] + (["SQL_OR_RESOURCE_API_UNRESOLVED"] if kind == "UNKNOWN" else []) \
          + (["T01_BODY_OR_CONTINUATION_NOT_TRAVERSED"] if legacy["placement"]["beforeT01Sequence"] is None else [])
        result.append(legacy)
    return result


def _method(facts, frame):
    matches = [
        (cls, method)
        for cls in facts["classes"]
        for method in cls["methods"]
        if method_key(cls, method) == frame["calleeMethod"]
    ]
    if len(matches) != 1 or matches[0][1]["evidence"] != frame["evidence"]:
        raise ValueError("resource facts do not match T01 method evidence")
    return matches[0]


def _jdbc_binding(cls, field):
    """Resolve only source-proven Spring injection or direct JdbcTemplate allocation."""
    if field.get("type") not in {JDBC, JDBC_OPERATIONS}:
        return "UNKNOWN_OR_AMBIGUOUS", []
    if field["type"] == JDBC:
        annotations = field.get("annotations", [])
        if (
            not field.get("initialized")
            and not _has_field_reassignment(cls, field["name"])
            and len(annotations) == 1
            and annotations[0]["type"] == AUTOWIRED
            and annotations[0].get("args", {}).get("required", {}).get("literal", True) is True
        ):
            return "RESOLVED_STATIC_TYPE", [field["evidence"]]
        if binding_blocker(field) is None:
            return "RESOLVED_STATIC_TYPE", [field["evidence"], field["allocation"]["evidence"]]
    allocation = field.get("allocation")
    if (
        field.get("initialized") is True
        and "final" in field.get("flags", [])
        and field.get("annotations") == []
        and isinstance(allocation, dict)
        and allocation.get("type") == JDBC
        and allocation.get("explicitAllocationType") is True
        and allocation.get("anonymous") is False
        and not _has_field_reassignment(cls, field["name"])
    ):
        return "RESOLVED_STATIC_TYPE", [field["evidence"], allocation["evidence"]]
    name = field["name"]
    constructors = [m for m in cls["methods"] if m["name"] in {"<init>", cls["simpleName"]}]
    candidates = []
    for method in cls["methods"]:
        injected = _required_autowired(method)
        constructor = method in constructors and (len(constructors) == 1 or injected)
        setter = injected and method["name"].lower().startswith("set")
        if not (constructor or setter):
            continue
        parameters = {p["name"]: p for p in method.get("parameters", [])}
        for assignment in method.get("assignments", []):
            target = assignment["target"].removeprefix("this.")
            value = assignment["value"]
            parameter = parameters.get(value)
            if (
                target == name
                and parameter
                and parameter.get("type") == JDBC
                and not any(a["type"] == QUALIFIER for a in parameter.get("annotations", []))
            ):
                candidates.append((method, parameter, assignment))
    if len(candidates) == 1:
        method, parameter, assignment = candidates[0]
        assignments = [
            item
            for owner in cls["methods"]
            for item in owner.get("assignments", [])
            if item["target"].removeprefix("this.") == name
        ]
        if len(assignments) == 1 and assignments[0] == assignment:
            return "RESOLVED_STATIC_TYPE", [field["evidence"], method["evidence"], parameter["evidence"], assignment["evidence"]]
    return "UNKNOWN_OR_AMBIGUOUS", []


def _parameter_binding(facts, cls, method, receiver, allowed_callers=None):
    if sum(m["name"] == method["name"] and m["arity"] == method["arity"] for m in cls["methods"]) != 1:
        return None, "UNKNOWN_OR_AMBIGUOUS", []
    parameters = [p for p in method.get("parameters", []) if p["name"] == receiver]
    if len(parameters) != 1 or parameters[0].get("type") not in {JDBC, JDBC_OPERATIONS}:
        return None, "UNKNOWN_OR_AMBIGUOUS", []
    parameter = parameters[0]
    if any(a["type"] == QUALIFIER for a in parameter.get("annotations", [])):
        return None, "UNKNOWN_OR_AMBIGUOUS", [parameter["evidence"]]
    matches = []
    unresolved_match = False
    for caller_cls in facts["classes"]:
        for caller in caller_cls["methods"]:
            if allowed_callers is not None and method_key(caller_cls, caller) not in allowed_callers:
                continue
            for call in caller["calls"]:
                if call["name"] != method["name"] or call["arity"] != method["arity"]:
                    continue
                arguments = call.get("arguments", [])
                if len(arguments) != method["arity"]:
                    continue
                plausible_target = (
                    caller_cls["name"] == cls["name"]
                    and call["receiver"] in {"", "this"}
                ) or (
                    caller_cls["name"] != cls["name"]
                    and any(
                        f["name"] == call["receiver"].removeprefix("this.")
                        and f["type"] in {cls["name"], cls["simpleName"]}
                        for f in caller_cls["fields"]
                    )
                )
                if not plausible_target:
                    continue
                if caller_cls["name"] == cls["name"]:
                    if call["receiver"] not in {"", "this"}:
                        continue
                else:
                    target_fields = [
                        f for f in caller_cls["fields"]
                        if f["name"] == call["receiver"].removeprefix("this.")
                        and f["type"] in {cls["name"], cls["simpleName"]}
                    ]
                    if len(target_fields) != 1:
                        continue
                # Parameter position is stable in the declaration.
                index = method.get("parameters", []).index(parameter)
                expression = arguments[index].get("text", "")
                if not expression or not expression.replace("this.", "", 1).isidentifier():
                    unresolved_match = True
                    continue
                bound_field, bound_status, bound_evidence = _receiver_binding(
                    caller_cls, caller, expression
                )
                type_compatible = bool(
                    bound_field
                    and (
                        parameter["type"] == JDBC
                        and bound_field["type"] == JDBC
                        or parameter["type"] == JDBC_OPERATIONS
                        and bound_field["type"] in {JDBC, JDBC_OPERATIONS}
                    )
                )
                if type_compatible and bound_status == "RESOLVED_STATIC_TYPE":
                    matches.append((bound_field, call, arguments[index], bound_evidence))
                else:
                    unresolved_match = True
    if not matches or unresolved_match:
        return None, "UNKNOWN_OR_AMBIGUOUS", [parameter["evidence"]]
    identities = {json.dumps(item[0]["evidence"], sort_keys=True) for item in matches}
    if len(identities) != 1:
        return None, "UNKNOWN_OR_AMBIGUOUS", [parameter["evidence"]]
    source_field, call, argument, source_evidence = matches[0]
    proxy = {
        "name": receiver,
        "type": parameter["type"],
        "annotations": parameter.get("annotations", []),
        "evidence": parameter["evidence"],
    }
    evidence = [parameter["evidence"], *source_evidence, call["evidence"], argument["evidence"]]
    return proxy, "RESOLVED_STATIC_TYPE", evidence


def _receiver_binding(cls, method, receiver, facts=None, allowed_callers=None):
    """Resolve direct fields and simple local aliases without following calls."""
    evidence = []
    if shadows_receiver(method, receiver):
        parameter = next((p for p in method.get("parameters", []) if p["name"] == receiver), None)
        if facts is not None:
            return _parameter_binding(facts, cls, method, receiver, allowed_callers)
        return None, "UNKNOWN_OR_AMBIGUOUS", [parameter["evidence"]] if parameter else []
    seen = set()
    current = receiver
    for _ in range(5):
        if current in seen:
            return None, "UNKNOWN_OR_AMBIGUOUS", []
        seen.add(current)
        field_name = current.removeprefix("this.")
        fields = [f for f in cls["fields"] if f["name"] == field_name]
        if len(fields) == 1 and current in {field_name, "this." + field_name}:
            field = fields[0]
            status, binding_evidence = _jdbc_binding(cls, field)
            return field, status, evidence + binding_evidence
        aliases = [v for v in method.get("variables", []) if v["name"] == current]
        if len(aliases) != 1 or aliases[0].get("type") not in {JDBC, JDBC_OPERATIONS}:
            return None, "UNKNOWN_OR_AMBIGUOUS", []
        alias = aliases[0]
        if any(a["target"].removeprefix("this.") == current for a in method.get("assignments", [])):
            return None, "UNKNOWN_OR_AMBIGUOUS", [alias["evidence"]]
        evidence.append(alias["evidence"])
        initializer = alias.get("initializer")
        if not isinstance(initializer, str) or not initializer.replace("this.", "", 1).isidentifier():
            return None, "UNKNOWN_OR_AMBIGUOUS", evidence
        current = initializer
    return None, "UNKNOWN_OR_AMBIGUOUS", evidence


def _observation(cls, method, call, frame, state, before, facts=None):
    receiver = call["receiver"]
    field, binding_status, binding_evidence = _receiver_binding(cls, method, receiver, facts)
    annotations = field["annotations"] if field else []
    binding = bool(
        field
        and (not shadows_receiver(method, receiver) or binding_status == "RESOLVED_STATIC_TYPE")
        and binding_status == "RESOLVED_STATIC_TYPE"
        and not cls["parents"]
        and (
            binding_status == "RESOLVED_STATIC_TYPE"
        )
        and receiver not in {"", "this"}
    )
    args = call.get("arguments", [])
    api = call["name"] in JDBC_APIS
    has_sql_arg = bool(args) and call["arity"] == len(args)
    literal_sql = (
        has_sql_arg
        and args[0]["kind"] == "STRING_LITERAL"
        and not (call["name"] == "batchUpdate" and call["arity"] != 1)
    )
    sql = args[0]["literal"] if api and literal_sql else None
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
        "jdbcBinding": {
            "status": binding_status,
            "declaredType": field["type"] if field else None,
        },
        "datasource": {"status": "UNKNOWN", "id": None},
        "enlistment": "UNKNOWN",
        "lockAcquired": "UNKNOWN",
        "certainty": "CONDITIONAL" if before is not None else "UNKNOWN",
        "placement": {
            "status": "T01_FRONTIER" if before is not None else "UNPLACED",
            "beforeT01Sequence": before,
        },
        "evidence": [copy.deepcopy(call["evidence"])]
        + [copy.deepcopy(e) for e in binding_evidence]
        + (
            [copy.deepcopy(field["evidence"])]
            if field and field["evidence"] not in binding_evidence
            else []
        )
        + ([copy.deepcopy(args[0]["evidence"])] if api and has_sql_arg else []),
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
                cls, method, calls[0], frame, state, event["sequence"], facts
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
    traversed_methods = set()
    for frame in transaction["frames"]:
        traversed_methods.add(frame["calleeMethod"])
        cls, method = _method(facts, frame)
        for call in method["calls"]:
            if any(
                o["frame"] == frame["id"] and o["callSite"] == call["evidence"]
                for o in observations
            ):
                continue
            field, _, _ = _receiver_binding(cls, method, call["receiver"], facts)
            if field is None or not (
                field.get("type") in {JDBC, JDBC_OPERATIONS}
                or field.get("type", "").startswith("UNKNOWN_TYPE_PARAMETER:")
            ):
                continue
            observation = _observation(
                cls,
                method,
                call,
                frame,
                {"kind": "UNKNOWN", "physicalId": None, "manager": None},
                None,
                facts,
            )
            observation["id"] = "O" + str(len(observations) + 1)
            observations.append(observation)
    # Retain JDBC operations in untraversed helper bodies when a unique call-site
    # argument proves their JDBC receiver. They remain UNPLACED with UNKNOWN T01 state.
    for cls in facts["classes"]:
        for method in cls["methods"]:
            method_id = method_key(cls, method)
            if method_id in traversed_methods:
                continue
            for call in method["calls"]:
                if call["name"] not in JDBC_APIS:
                    continue
                parameter = next(
                    (p for p in method.get("parameters", []) if p["name"] == call["receiver"]),
                    None,
                )
                if parameter is None:
                    continue
                if not any(
                    method_key(caller_cls, caller) in traversed_methods
                    and any(c["name"] == method["name"] and c["arity"] == method["arity"] for c in caller["calls"])
                    for caller_cls in facts["classes"]
                    for caller in caller_cls["methods"]
                ):
                    continue
                field, status, _ = _receiver_binding(
                    cls, method, call["receiver"], facts, traversed_methods
                )
                if field is None or status != "RESOLVED_STATIC_TYPE":
                    continue
                synthetic_frame = {"id": None, "calleeMethod": method_id}
                observation = _observation(
                    cls,
                    method,
                    call,
                    synthetic_frame,
                    {"kind": "UNKNOWN", "physicalId": None, "manager": None},
                    None,
                    facts,
                )
                observation["id"] = "O" + str(len(observations) + 1)
                observations.append(observation)
    for sequence, event in enumerate(timeline, 1):
        event["sequence"] = sequence
    return observations, timeline


def build_timeline(transaction, facts):
    observations, timeline = _project(transaction, facts)
    schema = "mana.resource-timeline/v2" if observations else "mana.resource-timeline/v1"
    limits = _limits(transaction) if schema.endswith("v2") else (LEGACY_LEAF_LIMITS if "resourceLeafExtension" in transaction else LIMITS)
    if schema.endswith("v1"):
        observations = _legacy_observations(observations, facts)
    return {
        "schema": schema,
        "status": "CONDITIONAL_STATIC_SCENARIO",
        "transactionModel": copy.deepcopy(transaction),
        "sourceFacts": copy.deepcopy(facts),
        "observations": observations,
        "timeline": timeline,
        "limits": list(limits),
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
        or report["schema"] not in {"mana.resource-timeline/v1", "mana.resource-timeline/v2"}
    ):
        raise ValueError("invalid resource timeline schema")
    observations, timeline = _project(report["transactionModel"], report["sourceFacts"])
    expected_limits = (
        (LEGACY_LEAF_LIMITS if "resourceLeafExtension" in report["transactionModel"] else LIMITS)
        if report["schema"] == "mana.resource-timeline/v1"
        else _limits(report["transactionModel"])
    )
    if report["status"] != "CONDITIONAL_STATIC_SCENARIO" or report["limits"] != expected_limits:
        raise ValueError("invalid resource timeline certainty/limits")
    if report["schema"] == "mana.resource-timeline/v1":
        # Read-only compatibility for published S01 v1 artifacts.
        observations = _legacy_observations(observations, report["sourceFacts"])
    if report["observations"] != observations or report["timeline"] != timeline:
        raise ValueError("resource timeline differs from T01 causal/source projection")
