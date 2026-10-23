"""Authoritative, opt-in JDBC literal leaf catalog; no propagation or runtime proof."""

import copy
import re

from .source import verify_leaf_snapshot

JDBC = "org.springframework.jdbc.core.JdbcTemplate"
AUTOWIRED = "org.springframework.beans.factory.annotation.Autowired"
POLICY = "JDBC_LITERAL_V1"
MAX_LEAVES = 128
EXTENSION = "mana.transaction-resource-leaves/v1"
RULE = {"id": "spring-jdbc-template-literal", "version": 2}
SIGNATURES = {
    "execute": JDBC + "#execute(java.lang.String):void",
    "update": JDBC + "#update(java.lang.String):int",
    "queryForList": JDBC + "#queryForList(java.lang.String):java.util.List",
}
CALLER_ANNOTATIONS = {
    "org.springframework.stereotype." + name
    for name in ("Service", "Component", "Repository", "Controller")
} | {
    "org.springframework.transaction.annotation.Transactional",
    "Override",
    "java.lang.Override",
    "Deprecated",
    "java.lang.Deprecated",
}
PREMISES = [
    "The private final receiver is directly allocated as the catalogued Spring class; no reflective mutation, bytecode rewriting or external advisor is assumed.",
    "The bounded lexical binding and allocation screen succeeds; the named Spring library declaration/API is assumed authentic on the target classpath.",
    "Normal synchronous return is assumed only for continuation of this path.",
    "No unmodeled transaction-context changes by library, driver or database are assumed on this path.",
    "The catalogued overload has no application callback argument.",
]
LIMITS = [
    "Runtime execution, successful SQL completion and normal return are not proved.",
    "External wiring, library version, advisors, driver and database behavior are not runtime-verified.",
    "Datasource, connection enlistment, acquired locks and lock granularity remain UNKNOWN.",
    "Exceptional return does not reach this path's suffix; exception handling and outcome are not modeled.",
]
IDENTIFIER = r"[A-Za-z_][A-Za-z_0-9]*"
BEAN = "org.springframework.context.annotation.Bean"
MANAGER = "org.springframework.jdbc.datasource.DataSourceTransactionManager"
DISPATCH_ANNOTATIONS = CALLER_ANNOTATIONS | {
    AUTOWIRED,
    BEAN,
    "org.springframework.beans.factory.annotation.Qualifier",
    "org.springframework.context.annotation.Configuration",
    "org.springframework.transaction.annotation.EnableTransactionManagement",
    "org.springframework.scheduling.annotation.Async",
}


def dispatch_blocker(facts):
    """Fail closed over the bounded source inventory, not just the declared API.

    No subtype search is complete through an omitted type or an unresolved parent.
    A library method can itself dispatch to application overrides (including hooks
    with no callback argument), so even an inherited catalog overload is unsafe.
    External substitution remains an explicit conditional scenario premise.
    """
    if facts.get("errors"):
        return "RESOURCE_LEAF_SOURCE_DISPATCH_INCOMPLETE"
    for cls in facts["classes"]:
        if any(
            a["type"] not in DISPATCH_ANNOTATIONS
            for owner in [cls, *cls["methods"], *cls["fields"]]
            for a in owner["annotations"]
        ):
            # Imports, registrars, composed bean annotations and source advisors
            # can supply implementations without a directly observed @Bean.
            return "RESOURCE_LEAF_UNRESOLVED_WIRING_ANNOTATION"
        if cls.get("dispatchHazards") != [] or any(
            p.startswith("UNKNOWN_") for p in cls["parents"]
        ):
            return "RESOURCE_LEAF_SOURCE_DISPATCH_INCOMPLETE"
        if cls["name"] == JDBC or cls["simpleName"] in {"JdbcTemplate", "org"}:
            return "RESOURCE_LEAF_APPLICATION_TYPE_SHADOW"
        if any(p in {JDBC, "JdbcTemplate"} for p in cls["parents"]):
            return "RESOURCE_LEAF_APPLICATION_SUBTYPE"
        if any(p not in {"Object", "java.lang.Object"} for p in cls["parents"]):
            return "RESOURCE_LEAF_UNRESOLVED_SOURCE_SUPERTYPE"
        for method in cls["methods"]:
            if method["returnType"] in {JDBC, "JdbcTemplate"}:
                return "RESOURCE_LEAF_UNRESOLVED_IMPLEMENTATION_FACTORY"
            if (
                any(a["type"] == BEAN for a in method["annotations"])
                and method["returnType"] != MANAGER
            ):
                # Object/interface/subtype/factory/proxy/decorator returns are not
                # resolved here. The existing manager declaration is disjoint
                # from JdbcTemplate; no new bean resolver is introduced.
                return "RESOURCE_LEAF_UNRESOLVED_BEAN_IMPLEMENTATION"
    return None


def sql_operation(sql, api):
    """Closed syntax grammar excludes SQL demarcation, calls and compound statements."""
    if not isinstance(sql, str):
        return "UNKNOWN", None
    patterns = [
        (rf"SELECT \* FROM ({IDENTIFIER}) FOR UPDATE", "EXPLICIT_LOCK_REQUEST"),
        (rf"SELECT \* FROM ({IDENTIFIER})", "READ"),
        (rf"UPDATE ({IDENTIFIER}) SET {IDENTIFIER} = [0-9]+", "WRITE"),
        (rf"DELETE FROM ({IDENTIFIER})", "WRITE"),
        (rf"INSERT INTO ({IDENTIFIER}) \({IDENTIFIER}\) VALUES \([0-9]+\)", "WRITE"),
    ]
    for pattern, kind in patterns:
        match = re.fullmatch(pattern, sql.strip(), re.IGNORECASE | re.ASCII)
        if match and (
            api == "execute"
            or api == "update"
            and kind == "WRITE"
            or api == "queryForList"
            and kind in {"READ", "EXPLICIT_LOCK_REQUEST"}
        ):
            return kind, match.group(1)
    return "UNKNOWN", None


def source_method(facts, frame):
    from .entry import method_key

    matches = [
        (cls, method)
        for cls in facts["classes"]
        for method in cls["methods"]
        if method_key(cls, method) == frame["calleeMethod"]
        and method["evidence"] == frame["evidence"]
    ]
    if len(matches) != 1:
        raise ValueError("resource leaf has no unique source method")
    return matches[0]


def binding_blocker(field):
    """Positive allocation identity; an injected static API type proves no target."""
    if field.get("type") != JDBC:
        return "RESOURCE_LEAF_TYPE_BINDING_UNPROVEN"
    allocation = field.get("allocation")
    if isinstance(allocation, dict) and allocation.get("explicitType") is not True:
        return "RESOURCE_LEAF_TYPE_BINDING_UNPROVEN"
    if (
        not field.get("initialized")
        or set(field.get("flags", [])) != {"private", "final"}
        or field.get("annotations") != []
        or not isinstance(allocation, dict)
        or allocation.get("type") != JDBC
        or allocation.get("explicitType") is not True
        or allocation.get("arity") != 0
        or allocation.get("anonymous") is not False
    ):
        return "RESOURCE_LEAF_DISPATCH_UNPROVEN"
    return None


def call_blocker(facts, cls, call):
    blocker = dispatch_blocker(facts)
    if blocker is not None:
        return blocker
    fields = [
        f for f in cls["fields"] if f["name"] == call["receiver"].removeprefix("this.")
    ]
    return (
        binding_blocker(fields[0])
        if len(fields) == 1
        else "RESOURCE_LEAF_TYPE_BINDING_UNPROVEN"
    )


def classify(facts, cls, method, call, state, sequence, dependencies):
    """Recompute the whole witness from facts and the fixed catalog, never safe=true."""
    receiver = call["receiver"]
    from .entry import shadows_receiver

    if shadows_receiver(method, receiver):
        return None
    field_name = receiver.removeprefix("this.")
    fields = [f for f in cls["fields"] if f["name"] == field_name]
    args = call.get("arguments", [])
    if (
        state["kind"] not in {"NO_TRANSACTION", "TRANSACTION_PHYSICAL"}
        or state["kind"] == "TRANSACTION_PHYSICAL"
        and not state["physicalId"]
        or len(fields) != 1
        or receiver not in {field_name, "this." + field_name}
        or cls["parents"]
        or cls["kind"] != "CLASS"
        or "abstract" in cls["flags"]
        or "public" not in method["flags"]
        or bool(set(method["flags"]) & {"static", "abstract"})
        or any(
            a["type"] not in CALLER_ANNOTATIONS
            for a in cls["annotations"] + method["annotations"]
        )
        or method["hazards"]
        or call.get("statementCall") is not True
        or call["name"] not in SIGNATURES
        or call["arity"] != 1
        or len(args) != 1
        or args[0]["kind"] != "STRING_LITERAL"
        or sql_operation(args[0]["literal"], call["name"])[0] == "UNKNOWN"
    ):
        return None
    field = fields[0]
    if binding_blocker(field) is not None:
        return None

    def inside(child, parent):
        return (
            child["file"] == parent["file"]
            and child["sha256"] == parent["sha256"]
            and type(child["start"]) is int
            and type(child["end"]) is int
            and parent["start"] <= child["start"] < child["end"] <= parent["end"]
        )

    if not (
        inside(method["evidence"], cls["evidence"])
        and inside(field["evidence"], cls["evidence"])
        and inside(call["evidence"], method["evidence"])
        and inside(args[0]["evidence"], call["evidence"])
    ):
        return None
    if dispatch_blocker(facts) is not None:
        return None
    index = next(i for i, c in enumerate(method["calls"], 1) if c == call)
    return {
        "schema": "mana.resource-leaf-witness/v1",
        "rule": dict(RULE),
        "signature": SIGNATURES[call["name"]],
        "receiverType": JDBC,
        "callSite": copy.deepcopy(call["evidence"]),
        "methodEvidence": copy.deepcopy(method["evidence"]),
        "bindingEvidence": copy.deepcopy(field["evidence"]),
        "argumentEvidence": copy.deepcopy(args[0]["evidence"]),
        "sourceCallOrdinal": index,
        "t01Sequence": sequence,
        "normalReturnDependencies": list(dependencies),
        "transactionContext": copy.deepcopy(state),
        "premises": list(PREMISES),
        "limits": list(LIMITS),
    }


def validate_extension(report):
    """Check capability/version, fact provenance and source prefix independently of build."""
    policy = report["context"].get("resourceLeafPolicy", "DISABLED")
    if policy not in ("DISABLED", POLICY):
        raise ValueError("unsupported resource leaf policy")
    extension = report.get("resourceLeafExtension")
    leaves = [e for e in report["events"] if e["kind"] == "RESOURCE_LEAF_CALL"]
    if len(leaves) > MAX_LEAVES:
        raise ValueError("resource leaf budget exceeded")
    if policy == "DISABLED":
        if extension is not None or leaves:
            raise ValueError("resource leaf requires explicit versioned capability")
        return None
    if (
        not isinstance(extension, dict)
        or set(extension) != {"schema", "sourceFacts"}
        or extension["schema"] != EXTENSION
    ):
        raise ValueError("missing or unsupported resource leaf extension")
    facts = extension["sourceFacts"]
    if not isinstance(facts, dict) or not isinstance(facts.get("classes"), list):
        raise ValueError("invalid resource leaf source facts")
    if facts.get("errors") or len({c["name"] for c in facts["classes"]}) != len(
        facts["classes"]
    ):
        raise ValueError("invalid resource leaf source facts")
    hashes = {e["path"]: e["sha256"] for e in report.get("evidence", [])}

    def verify(value):
        if isinstance(value, dict):
            if {"file", "sha256", "start", "end", "line"} <= value.keys():
                if hashes.get(value["file"]) != value["sha256"]:
                    raise ValueError("resource leaf source hash mismatch")
            for item in value.values():
                verify(item)
        elif isinstance(value, list):
            for item in value:
                verify(item)

    verify(facts)
    if leaves:
        blocker = dispatch_blocker(facts)
        if blocker is not None:
            raise ValueError("resource leaf dispatch not demonstrated: " + blocker)
        verify_leaf_snapshot(facts, hashes)
    stack, parent_of = [], {}
    for event in report["events"]:
        if event["kind"] == "FRAME_ENTER":
            parent_of[event["frame"]] = stack[-1] if stack else None
            stack.append(event["frame"])
        elif event["kind"] == "FRAME_EXIT":
            if not stack or stack.pop() != event["frame"]:
                raise ValueError("unbalanced resource leaf frame trace")
    for frame in report["frames"]:
        _, method = source_method(facts, frame)
        statement_sites = [
            c["evidence"] for c in method["calls"] if c.get("statementCall") is True
        ]
        if any(
            b["start"] < a["end"] for a, b in zip(statement_sites, statement_sites[1:])
        ):
            raise ValueError("resource leaf statement order contradicts source spans")
        steps = []
        for event in report["events"]:
            if event["frame"] == frame["id"] and event["kind"] in {
                "RESOURCE_LEAF_CALL",
                "UNRESOLVED_CALL",
            }:
                steps.append((event["sequence"], event["callSite"], event))
            elif event["kind"] == "FRAME_ENTER":
                child = next(f for f in report["frames"] if f["id"] == event["frame"])
                if parent_of[child["id"]] == frame["id"]:
                    steps.append((event["sequence"], child["callSite"], child))
        steps.sort(key=lambda s: s[0])
        if [s[1] for s in steps] != [
            c["evidence"] for c in method["calls"][: len(steps)]
        ]:
            raise ValueError("resource leaf source call order/provenance mismatch")
        if frame["bodyTraversal"] == "STRAIGHT_LINE" and len(steps) < len(
            method["calls"]
        ):
            last = steps[-1][2] if steps else {}
            if not (
                last.get("kind") == "UNRESOLVED_CALL"
                or last.get("continuation") == "UNKNOWN"
                or last.get("bodyTraversal") == "NOT_ASSERTED"
            ):
                raise ValueError("resource leaf source suffix missing without frontier")
    return facts


def validate_call(report, facts, frame, event, current, dependencies):
    if facts is None:
        raise ValueError("resource leaf lacks source capability")
    if set(event) != {
        "sequence",
        "kind",
        "frame",
        "callSite",
        "receiver",
        "method",
        "witness",
    }:
        raise ValueError("resource leaf event requires its versioned witness")
    cls, method = source_method(facts, frame)
    calls = [c for c in method["calls"] if c["evidence"] == event["callSite"]]
    if len(calls) != 1 or (event["receiver"], event["method"]) != (
        calls[0]["receiver"],
        calls[0]["name"],
    ):
        raise ValueError("resource leaf call site differs from source")
    blocker = dispatch_blocker(facts)
    if blocker is not None:
        raise ValueError("resource leaf dispatch not demonstrated: " + blocker)
    expected = classify(
        facts, cls, method, calls[0], current, event["sequence"], dependencies
    )
    witness = event.get("witness")
    if (
        expected is None
        or witness != expected
        or type(witness["rule"]["version"]) is not int
        or type(witness["sourceCallOrdinal"]) is not int
        or type(witness["t01Sequence"]) is not int
        or any(type(i) is not int for i in witness["normalReturnDependencies"])
    ):
        raise ValueError("resource leaf witness fails authoritative classification")
