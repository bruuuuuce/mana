"""Bounded APPLIED/BYPASSED context composition, never a runtime weaving proof."""

import copy

MANAGER_TYPE = "org.springframework.jdbc.datasource.DataSourceTransactionManager"
ADVICE_REASONS = {
    "ASPECTJ_WEAVING_NOT_ESTABLISHED",
    "ASPECTJ_METHOD_SHAPE_NOT_MODELED",
    "ASPECTJ_BEAN_SHAPE_NOT_MODELED",
    "PROXY_OR_ASPECTJ_MODE_NOT_ESTABLISHED",
    "PROXY_OR_VISIBILITY_NOT_ESTABLISHED",
}


def state(kind="UNKNOWN", physical=None, manager=None):
    return {"kind": kind, "physicalId": physical, "manager": manager}


def common_state(left, right):
    """Intersect properties; ACTIVE need not imply a common physical identity."""
    return {
        key: left[key] if left[key] == right[key] else fallback
        for key, fallback in (
            ("kind", "UNKNOWN"),
            ("physicalId", None),
            ("manager", None),
        )
    }


def selected_manager(configuration, managers):
    selected = configuration["managerQualifier"]
    if not selected and len(managers) == 1:
        selected = managers[0]["id"]
    return next(
        (m for m in managers if m["id"] == selected and m["type"] == MANAGER_TYPE),
        None,
    )


def applied_boundary(previous, configuration, managers):
    """Only the three supported propagations; no branch-only P/L/SP is materialized."""
    result = {
        "duringState": state(),
        "identity": "UNKNOWN",
        "logicalScope": "UNKNOWN",
        "savepoint": "UNKNOWN",
        "suspension": "UNKNOWN",
        "resolution": "MANAGER_OR_PRIOR_CONTEXT_UNKNOWN",
    }
    manager = selected_manager(configuration, managers)
    if (
        not manager
        or previous["kind"] == "UNKNOWN"
        or previous["manager"] not in (None, manager["id"])
        or previous["kind"] == "TRANSACTION_PHYSICAL"
        and not previous["physicalId"]
    ):
        return result
    prop = configuration["propagation"]
    if prop not in {"REQUIRED", "REQUIRES_NEW", "NESTED"}:
        result["resolution"] = "PROPAGATION_NOT_MODELED"
        return result
    caps = manager["capabilities"]
    if previous["physicalId"] and (
        prop == "REQUIRES_NEW"
        and caps.get("suspend") is not True
        or prop == "NESTED"
        and caps.get("savepoints") is not True
    ):
        result["resolution"] = "CAPABILITY_UNKNOWN_OR_UNSUPPORTED"
        return result
    fresh = prop == "REQUIRES_NEW" or previous["kind"] == "NO_TRANSACTION"
    return {
        "duringState": state("TRANSACTION_PHYSICAL", None, manager["id"])
        if fresh
        else copy.deepcopy(previous),
        "identity": "FRESH_IF_APPLIED" if fresh else "INHERITED",
        "logicalScope": "IF_APPLIED",
        "savepoint": "IF_APPLIED"
        if prop == "NESTED" and previous["physicalId"]
        else "ABSENT",
        "suspension": "IF_APPLIED"
        if prop == "REQUIRES_NEW" and previous["physicalId"]
        else "ABSENT",
        "resolution": "SUPPORTED",
    }


def compose(previous, configuration, managers, evidence, empty_body):
    applied = applied_boundary(previous, configuration, managers)
    # After means normal synchronous unwind, not proof of return/commit/rollback.
    applied["afterState"] = (
        copy.deepcopy(previous)
        if empty_body and applied["resolution"] == "SUPPORTED"
        else state()
    )
    bypassed = {
        "duringState": copy.deepcopy(previous),
        "afterState": copy.deepcopy(previous) if empty_body else state(),
        "identity": "INHERITED",
        "logicalScope": "ABSENT",
        "savepoint": "ABSENT",
        "suspension": "ABSENT",
        "resolution": "BYPASSED",
    }
    return {
        "premises": {
            "execution": "SYNCHRONOUS_BOUNDARY",
            "otherBoundaryMechanisms": "NONE_OBSERVED",
            "body": "EMPTY" if empty_body else "NOT_ASSERTED",
            "evidence": copy.deepcopy(evidence),
        },
        "alternatives": {"APPLIED": applied, "BYPASSED": bypassed},
        "duringState": common_state(applied["duringState"], bypassed["duringState"]),
        "afterState": common_state(applied["afterState"], bypassed["afterState"]),
    }


def validate_composition(frame, report):
    """Check branch semantics and the intersection against configuration/capabilities."""
    composition = frame["contextComposition"]
    if (
        frame["interception"]["status"] != "UNKNOWN"
        or frame["interception"]["reason"] not in ADVICE_REASONS
        or not frame["configuration"]
        or frame["logicalScope"] is not None
        or frame["bodyTraversal"] != "NOT_ASSERTED"
    ):
        raise ValueError("context composition outside an advice-only uncertainty")
    reason = frame["interception"]["reason"]
    mode = report["interceptionMode"]
    weaving = report["aspectjWeaving"]["application"]
    if (
        reason.startswith("ASPECTJ_")
        and mode != "ASPECTJ"
        or reason == "ASPECTJ_WEAVING_NOT_ESTABLISHED"
        and weaving != "UNKNOWN"
        or reason
        in {"ASPECTJ_METHOD_SHAPE_NOT_MODELED", "ASPECTJ_BEAN_SHAPE_NOT_MODELED"}
        and weaving != "ASSUMED_APPLIED"
        or reason == "PROXY_OR_VISIBILITY_NOT_ESTABLISHED"
        and mode != "PROXY"
        or reason == "PROXY_OR_ASPECTJ_MODE_NOT_ESTABLISHED"
        and mode != "UNKNOWN"
    ):
        raise ValueError("advice uncertainty contradicts mode/weaving premises")
    premises = composition["premises"]
    if (
        premises["execution"] != "SYNCHRONOUS_BOUNDARY"
        or premises["otherBoundaryMechanisms"] != "NONE_OBSERVED"
        or premises["body"] not in {"EMPTY", "NOT_ASSERTED"}
        or premises["evidence"] != frame["evidence"]
    ):
        raise ValueError("invalid composition execution premises/provenance")
    for manager in report["managers"]:
        caps = report["context"]["managerCapabilities"].get(
            manager["id"], {"suspend": None, "savepoints": None}
        )
        if manager["capabilities"] != caps:
            raise ValueError("composition capabilities contradict scenario context")
    branches = composition["alternatives"]
    if set(branches) != {"APPLIED", "BYPASSED"}:
        raise ValueError("composition requires both advice alternatives")
    applied, bypassed = branches["APPLIED"], branches["BYPASSED"]
    previous = frame["previousState"]
    if bypassed != {
        "duringState": previous,
        "afterState": previous if premises["body"] == "EMPTY" else state(),
        "identity": "INHERITED",
        "logicalScope": "ABSENT",
        "savepoint": "ABSENT",
        "suspension": "ABSENT",
        "resolution": "BYPASSED",
    }:
        raise ValueError("bypassed alternative changed inherited context")
    # Verify APPLIED directly rather than trusting its claimed resolution or common state.
    manager = selected_manager(frame["configuration"], report["managers"])
    prop = frame["configuration"]["propagation"]
    resolvable = bool(
        manager
        and previous["kind"] in {"NO_TRANSACTION", "TRANSACTION_PHYSICAL"}
        and previous["manager"] in (None, manager["id"])
        and (previous["kind"] == "NO_TRANSACTION" or previous["physicalId"])
    )
    supported_prop = prop in {"REQUIRED", "REQUIRES_NEW", "NESTED"}
    capable = bool(
        resolvable
        and (
            not previous["physicalId"]
            or prop == "REQUIRED"
            or prop == "NESTED"
            and manager["capabilities"].get("savepoints") is True
            or prop == "REQUIRES_NEW"
            and manager["capabilities"].get("suspend") is True
        )
    )
    if resolvable and supported_prop and capable:
        inherited = (
            previous["kind"] == "TRANSACTION_PHYSICAL" and prop != "REQUIRES_NEW"
        )
        expected = {
            "duringState": previous
            if inherited
            else state("TRANSACTION_PHYSICAL", None, manager["id"]),
            "afterState": previous if premises["body"] == "EMPTY" else state(),
            "identity": "INHERITED" if inherited else "FRESH_IF_APPLIED",
            "logicalScope": "IF_APPLIED",
            "savepoint": "IF_APPLIED" if inherited and prop == "NESTED" else "ABSENT",
            "suspension": "IF_APPLIED"
            if previous["physicalId"] and prop == "REQUIRES_NEW"
            else "ABSENT",
            "resolution": "SUPPORTED",
        }
    else:
        expected = {
            "duringState": state(),
            "afterState": state(),
            "identity": "UNKNOWN",
            "logicalScope": "UNKNOWN",
            "savepoint": "UNKNOWN",
            "suspension": "UNKNOWN",
            "resolution": "MANAGER_OR_PRIOR_CONTEXT_UNKNOWN"
            if not resolvable
            else "PROPAGATION_NOT_MODELED"
            if not supported_prop
            else "CAPABILITY_UNKNOWN_OR_UNSUPPORTED",
        }
    if applied != expected:
        raise ValueError(
            "applied alternative contradicts propagation/manager/capabilities"
        )
    for field in ("duringState", "afterState"):
        common = common_state(applied[field], bypassed[field])
        if composition[field] != common or frame[field] != common:
            raise ValueError("physical certainty is not common to advice alternatives")
    if frame["manager"] != composition["duringState"]["manager"]:
        raise ValueError("frame manager contradicts composition")
    # Optional branch effects must never leak into the unconditional event model.
    if any(
        item.get("frame", item.get("beginFrame")) == frame["id"]
        for family in (
            "logicalScopes",
            "physicalTransactions",
            "suspensions",
            "savepoints",
        )
        for item in report[family]
    ):
        raise ValueError("branch-only boundary materialized as an unconditional entity")
