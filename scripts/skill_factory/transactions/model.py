"""Conditional static transaction boundaries over a deliberately bounded Java AST."""

import copy

from .alternatives import (
    ADVICE_REASONS,
    compose,
    selected_manager,
    validate_composition,
)

SPRING = "org.springframework."
TX = SPRING + "transaction.annotation.Transactional"
ENABLE = SPRING + "transaction.annotation.EnableTransactionManagement"
BEAN = SPRING + "context.annotation.Bean"
STEREOTYPES = {
    SPRING + "stereotype." + n
    for n in ["Service", "Component", "Repository", "Controller"]
}
AUTOWIRED = SPRING + "beans.factory.annotation.Autowired"
ASYNC = SPRING + "scheduling.annotation.Async"
TYPES = {
    "TRANSACTION_LOGICAL_SCOPE",
    "TRANSACTION_PHYSICAL",
    "TRANSACTION_SUSPENDED",
    "TRANSACTION_SAVEPOINT",
    "NO_TRANSACTION",
    "UNKNOWN",
}
KNOWN_ANNOTATIONS = STEREOTYPES | {
    TX,
    ENABLE,
    BEAN,
    AUTOWIRED,
    ASYNC,
    SPRING + "context.annotation.Configuration",
    "Override",
    "java.lang.Override",
    "Deprecated",
    "java.lang.Deprecated",
}


def annotation(owner, name):
    return next((a for a in owner["annotations"] if a["type"] == name), None)


def literal(ann, key, default=None):
    if not ann or key not in ann["args"]:
        return default
    arg = ann["args"][key]
    return arg["literal"] if arg["kind"].endswith("LITERAL") else None


def no_transaction():
    return {"kind": "NO_TRANSACTION", "physicalId": None, "manager": None}


def unknown():
    return {"kind": "UNKNOWN", "physicalId": None, "manager": None}


def effective_context(state):
    return {
        "NO_TRANSACTION": "INACTIVE",
        "TRANSACTION_PHYSICAL": "ACTIVE",
        "UNKNOWN": "UNKNOWN",
    }[state["kind"]]


def build(facts, context, entry):
    classes = {c["name"]: c for c in facts["classes"]}
    if len(classes) != len(facts["classes"]):
        raise ValueError("duplicate class identity; source binding is ambiguous")
    methods = {}
    for cls in classes.values():
        for method in cls["methods"]:
            key = cls["name"] + "#" + method["name"] + "()"
            if method["arity"] == 0:
                if key in methods:
                    raise ValueError("duplicate/ambiguous zero-argument method: " + key)
                methods[key] = (cls, method)
    if entry not in methods:
        raise ValueError(
            "entry must name an existing zero-argument method: Class#method()"
        )
    configs = [
        (c, a)
        for c in classes.values()
        for a in c["annotations"]
        if a["type"] == ENABLE
    ]
    interception_mode = proxy_mode = "UNKNOWN"
    if len(configs) == 1:
        args = configs[0][1]["args"]
        mode = args.get("mode", {}).get(
            "text", "org.springframework.context.annotation.AdviceMode.PROXY"
        )
        if mode == "org.springframework.context.annotation.AdviceMode.PROXY":
            interception_mode = "PROXY"
            value = literal(configs[0][1], "proxyTargetClass", False)
            proxy_mode = (
                "CLASS" if value is True else "JDK" if value is False else "UNKNOWN"
            )
        elif mode == "org.springframework.context.annotation.AdviceMode.ASPECTJ":
            interception_mode = "ASPECTJ"
    weaving = context.get("aspectjWeaving", "UNKNOWN")
    if weaving not in ("UNKNOWN", "ASSUMED_APPLIED"):
        raise ValueError("invalid AspectJ weaving scenario premise")
    managers = {}
    for cls in classes.values():
        if not annotation(cls, SPRING + "context.annotation.Configuration"):
            continue
        for method in cls["methods"]:
            if annotation(method, BEAN):
                # A declared manager type is not proof of driver/runtime capabilities.
                if "TransactionManager" in method["returnType"]:
                    manager_type = method["returnType"]
                    if method["name"] in managers or annotation(method, BEAN)["args"]:
                        manager_type = "UNKNOWN_DUPLICATE_OR_ALIASED_BEAN"
                    managers[method["name"]] = {
                        "id": method["name"],
                        "type": manager_type,
                        "evidence": method["evidence"],
                    }
    capabilities = context["managerCapabilities"]
    if set(capabilities) - set(managers):
        raise ValueError(
            "capabilities reference a manager not declared by a source @Bean method"
        )
    for manager in managers.values():
        manager["capabilities"] = capabilities.get(
            manager["id"], {"suspend": None, "savepoints": None}
        )
        manager["capabilityCertainty"] = "EXPLICIT_SCENARIO_ASSUMPTION"
    beans = {
        c["name"]: c
        for c in classes.values()
        if sum(bool(annotation(c, s)) for s in STEREOTYPES) == 1
    }
    report = {
        "schema": "mana.transaction-model/v1",
        "entry": entry,
        "status": "CONDITIONAL_STATIC_SCENARIO",
        "proxyMode": proxy_mode,
        "interceptionMode": interception_mode,
        "aspectjWeaving": {
            "application": weaving if interception_mode == "ASPECTJ" else "UNKNOWN",
            "runtimeApplication": "UNKNOWN",
        },
        "assumptions": [
            "Entry proxy crossing and prior context are explicit scenario inputs, not runtime facts.",
            "Manager capabilities are explicit scenario assumptions, not inferred driver/runtime support.",
            "Physical IDs are symbolic scenario identities; actual runtime identity is UNKNOWN.",
            "Normal synchronous return is conditional; commit/rollback outcome is UNKNOWN.",
            "Bean binding is closed to the observed annotation declarations; external wiring/advisors are not runtime-proven.",
        ],
        "context": context,
        "managers": list(managers.values()),
        "frames": [],
        "logicalScopes": [],
        "physicalTransactions": [],
        "suspensions": [],
        "savepoints": [],
        "events": [],
        "uncertainties": [],
    }
    if interception_mode == "ASPECTJ" and weaving == "ASSUMED_APPLIED":
        report["assumptions"].append(
            "AspectJ weaving application is an explicit conditional scenario assumption, not statically demonstrated or runtime-proven."
        )

    def emit(kind, frame, **extra):
        report["events"].append(
            {
                "sequence": len(report["events"]) + 1,
                "kind": kind,
                "frame": frame["id"],
                **extra,
            }
        )

    def uncertain(frame, reason, unsupported=False, *, preserve_interception=False):
        if not preserve_interception:
            frame["interception"] = {"status": "UNKNOWN", "reason": reason}
        frame["certainty"] = "UNKNOWN"
        frame["reason"] = reason
        frame["duringState"] = unknown()
        frame["bodyTraversal"] = "NOT_ASSERTED"
        report["uncertainties"].append(
            {
                "frame": frame["id"],
                "reason": reason,
                "classification": "UNSUPPORTED" if unsupported else "UNKNOWN",
                "evidence": frame["evidence"],
            }
        )

    def configuration(cls, method):
        ann = annotation(method, TX) or annotation(cls, TX)
        if not ann:
            return None
        raw = ann["args"]
        prop = raw.get("propagation", {}).get(
            "text", SPRING + "transaction.annotation.Propagation.REQUIRED"
        )
        prefix = SPRING + "transaction.annotation.Propagation."
        propagation = prop[len(prefix) :] if prop.startswith(prefix) else "UNKNOWN"
        manager = literal(ann, "transactionManager", "") or literal(ann, "value", "")
        if any(
            k in raw and raw[k]["kind"] != "STRING_LITERAL"
            for k in ("transactionManager", "value")
        ):
            manager = "UNKNOWN_EXPRESSION"
        if (
            literal(ann, "transactionManager", "")
            and literal(ann, "value", "")
            and literal(ann, "transactionManager") != literal(ann, "value")
        ):
            manager = "UNKNOWN_CONFLICTING_ALIASES"
        return {
            "propagation": propagation,
            "managerQualifier": manager,
            "attributes": raw,
            "evidence": ann["evidence"],
            "origin": "method" if annotation(method, TX) else "class",
            "resolution": "BOUNDARY_ATTRIBUTES_ONLY",
            "unmodeledAttributes": sorted(
                set(raw) - {"propagation", "transactionManager", "value"}
            ),
        }

    def resolve_call(cls, call):
        receiver = call["receiver"]
        if receiver in ("", "this"):
            return cls, False, "SELF_INVOCATION"
        field_name = receiver[5:] if receiver.startswith("this.") else receiver
        fields = [f for f in cls["fields"] if f["name"] == field_name]
        if (
            len(fields) != 1
            or fields[0]["initialized"]
            or not annotation(fields[0], AUTOWIRED)
        ):
            return None, None, "UNRESOLVED_RECEIVER_OR_NON_INJECTED_REFERENCE"
        field = fields[0]
        if (
            len(field["annotations"]) != 1
            or literal(annotation(field, AUTOWIRED), "required", True) is not True
        ):
            return None, None, "UNRESOLVED_INJECTION_QUALIFIER_OR_OPTIONAL_BINDING"
        # No speculative interface binding/subtype dispatch. Same-package concrete types only.
        package = cls["name"].rsplit(".", 1)[0] + "." if "." in cls["name"] else ""
        candidates = [
            c
            for c in beans.values()
            if c["name"] == field["type"]
            or ("." not in field["type"] and c["name"] == package + field["type"])
        ]
        if len(candidates) != 1 or candidates[0]["parents"]:
            return None, None, "AMBIGUOUS_OR_DYNAMIC_DISPATCH"
        if any(
            any(
                p in {candidates[0]["name"], candidates[0]["simpleName"]}
                for p in c["parents"]
            )
            for c in beans.values()
        ):
            return None, None, "AMBIGUOUS_OR_DYNAMIC_DISPATCH"
        call["bindingEvidence"] = field["evidence"]
        return candidates[0], True, "INJECTED_BEAN_SCENARIO"

    def interception(cls, method, conf, crossing):
        """Resolve advice application separately from the inherited context."""
        if not conf:
            return "BYPASSED", "NO_TRANSACTIONAL_ANNOTATION"
        if interception_mode == "UNKNOWN":
            return "UNKNOWN", "PROXY_OR_ASPECTJ_MODE_NOT_ESTABLISHED"
        flags = set(method["flags"])
        if interception_mode == "ASPECTJ":
            if weaving != "ASSUMED_APPLIED":
                return "UNKNOWN", "ASPECTJ_WEAVING_NOT_ESTABLISHED"
            # Retain T01's public concrete-method subset; no full AspectJ resolver.
            if flags & {"private", "static", "final"} or "public" not in flags:
                return "UNKNOWN", "ASPECTJ_METHOD_SHAPE_NOT_MODELED"
            if cls["name"] not in beans or "final" in cls["flags"]:
                return "UNKNOWN", "ASPECTJ_BEAN_SHAPE_NOT_MODELED"
            return "APPLIED", "ASPECTJ_WEAVING_ASSUMED_APPLIED"
        if crossing is False:
            return "BYPASSED", "SELF_OR_DIRECT_CALL"
        if flags & {"private", "static", "final"}:
            return "BYPASSED", "NON_INTERCEPTABLE_METHOD"
        if (
            crossing is not True
            or proxy_mode != "CLASS"
            or "public" not in flags
            or cls["name"] not in beans
            or "final" in cls["flags"]
        ):
            return "UNKNOWN", "PROXY_OR_VISIBILITY_NOT_ESTABLISHED"
        return "APPLIED", "SCENARIO_PROXY_CALL"

    def visit(key, previous, crossing, caller=None, site=None, stack=()):
        cls, method = methods[key]
        frame = {
            "id": "F" + str(len(report["frames"]) + 1),
            "callerMethod": caller,
            "calleeMethod": key,
            "callSite": site,
            "bean": cls["name"] if cls["name"] in beans else None,
            "proxy": {
                "mode": proxy_mode,
                "crossed": crossing if interception_mode != "ASPECTJ" else False,
                "configurationEvidence": [a["evidence"] for _, a in configs],
            },
            "manager": None,
            "configuration": configuration(cls, method),
            "logicalScope": None,
            "previousState": copy.deepcopy(previous),
            "duringState": copy.deepcopy(previous),
            "afterState": copy.deepcopy(previous),
            "certainty": "CONDITIONAL",
            "bodyTraversal": "STRAIGHT_LINE",
            "evidence": method["evidence"],
            "depth": len(stack),
        }
        frame["beanEvidence"] = cls["evidence"]
        frame["beanName"] = (
            next(
                (
                    literal(annotation(cls, s), "value")
                    for s in STEREOTYPES
                    if literal(annotation(cls, s), "value")
                ),
                cls["simpleName"][:1].lower() + cls["simpleName"][1:],
            )
            if frame["bean"]
            else None
        )
        report["frames"].append(frame)
        conf = frame["configuration"]
        flags = set(method["flags"])
        status, reason = interception(cls, method, conf, crossing)
        frame["interception"] = {"status": status, "reason": reason}
        frame["proxy"]["reason"] = (
            "NOT_APPLICABLE_ASPECTJ" if interception_mode == "ASPECTJ" else reason
        )
        if key in stack or len(stack) >= 16 or len(report["frames"]) >= 128:
            uncertain(frame, "RECURSION_OR_TRACE_BUDGET")
        elif annotation(method, ASYNC) or annotation(cls, ASYNC):
            uncertain(frame, "ASYNC_EXECUTION_CONTEXT")
        elif cls["parents"]:
            uncertain(frame, "INHERITANCE_OR_INTERFACE_RESOLUTION_NOT_MODELED")
        elif cls["kind"] != "CLASS" or "abstract" in cls["flags"]:
            uncertain(frame, "NON_CONCRETE_BEAN_TYPE")
        elif (
            interception_mode == "PROXY"
            and crossing is True
            and "final" in cls["flags"]
        ):
            uncertain(frame, "FINAL_CLASS_PROXY_NOT_ESTABLISHED")
        elif crossing is True and cls["name"] not in beans:
            uncertain(frame, "BEAN_IDENTITY_NOT_ESTABLISHED")
        elif any(
            a["type"] not in KNOWN_ANNOTATIONS
            for a in method["annotations"] + cls["annotations"]
        ):
            uncertain(frame, "UNRESOLVED_ANNOTATION_OR_META_ANNOTATION")
        elif method["hazards"]:
            uncertain(frame, "UNSUPPORTED_CONTROL_FLOW_OR_PROGRAMMATIC_EXPRESSION")
        elif crossing is True and "private" in flags:
            uncertain(frame, "INACCESSIBLE_EXTERNAL_PRIVATE_METHOD")
        elif status == "UNKNOWN":
            uncertain(frame, reason)
            frame["contextComposition"] = compose(
                previous,
                conf,
                report["managers"],
                method["evidence"],
                empty_body=not method["calls"],
            )
            frame["duringState"] = copy.deepcopy(
                frame["contextComposition"]["duringState"]
            )
            frame["manager"] = frame["duringState"]["manager"]
        elif previous["kind"] == "UNKNOWN" and status == "BYPASSED":
            uncertain(
                frame,
                "INHERITED_TRANSACTION_CONTEXT_UNKNOWN",
                preserve_interception=True,
            )
        elif status == "APPLIED":
            if conf["propagation"] not in {"REQUIRED", "REQUIRES_NEW", "NESTED"}:
                uncertain(
                    frame,
                    "PROPAGATION_NOT_MODELED:" + conf["propagation"],
                    True,
                    preserve_interception=True,
                )
            else:
                selected = conf["managerQualifier"]
                if not selected and len(managers) == 1:
                    selected = next(iter(managers))
                manager = managers.get(selected)
                if (
                    not manager
                    or manager["type"]
                    != SPRING + "jdbc.datasource.DataSourceTransactionManager"
                ):
                    uncertain(
                        frame,
                        "AMBIGUOUS_OR_UNMODELED_MANAGER",
                        preserve_interception=True,
                    )
                elif previous["kind"] == "UNKNOWN" or (
                    previous["physicalId"] and previous["manager"] != selected
                ):
                    uncertain(
                        frame,
                        "PRIOR_CONTEXT_OR_MANAGER_IDENTITY_UNKNOWN",
                        preserve_interception=True,
                    )
                else:
                    frame["manager"] = selected
                    frame["logicalScope"] = "L" + str(len(report["logicalScopes"]) + 1)
                    report["logicalScopes"].append(
                        {
                            "id": frame["logicalScope"],
                            "kind": "TRANSACTION_LOGICAL_SCOPE",
                            "frame": frame["id"],
                            "certainty": "CONDITIONAL",
                            "physicalId": None,
                        }
                    )
                    prop = conf["propagation"]
                    caps = capabilities.get(selected, {})
                    if (
                        previous["physicalId"]
                        and prop == "NESTED"
                        and caps.get("savepoints") is not True
                    ):
                        uncertain(
                            frame,
                            "SAVEPOINT_CAPABILITY_UNSUPPORTED"
                            if caps.get("savepoints") is False
                            else "SAVEPOINT_CAPABILITY_UNKNOWN",
                            caps.get("savepoints") is False,
                            preserve_interception=True,
                        )
                    elif (
                        previous["physicalId"]
                        and prop == "REQUIRES_NEW"
                        and caps.get("suspend") is not True
                    ):
                        uncertain(
                            frame,
                            "SUSPENSION_CAPABILITY_UNKNOWN_OR_UNSUPPORTED",
                            preserve_interception=True,
                        )
                    elif prop == "REQUIRES_NEW" or not previous["physicalId"]:
                        physical = {
                            "id": "P" + str(len(report["physicalTransactions"]) + 1),
                            "kind": "TRANSACTION_PHYSICAL",
                            "manager": selected,
                            "beginFrame": frame["id"],
                            "endFrame": frame["id"],
                            "identity": "SYMBOLIC_SCENARIO",
                            "runtimeIdentity": "UNKNOWN",
                            "certainty": "CONDITIONAL",
                            "outcome": "UNKNOWN",
                        }
                        report["physicalTransactions"].append(physical)
                        frame["duringState"] = {
                            "kind": "TRANSACTION_PHYSICAL",
                            "physicalId": physical["id"],
                            "manager": selected,
                        }
                    if (
                        frame["certainty"] != "UNKNOWN"
                        and prop == "NESTED"
                        and previous["physicalId"]
                    ):
                        savepoint = {
                            "id": "SP" + str(len(report["savepoints"]) + 1),
                            "kind": "TRANSACTION_SAVEPOINT",
                            "physicalId": previous["physicalId"],
                            "frame": frame["id"],
                            "certainty": "CONDITIONAL",
                        }
                        report["savepoints"].append(savepoint)
                    if frame["certainty"] != "UNKNOWN":
                        report["logicalScopes"][-1]["physicalId"] = frame[
                            "duringState"
                        ]["physicalId"]
                        if prop == "REQUIRES_NEW" and previous["physicalId"]:
                            report["suspensions"].append(
                                {
                                    "id": "S" + str(len(report["suspensions"]) + 1),
                                    "kind": "TRANSACTION_SUSPENDED",
                                    "physicalId": previous["physicalId"],
                                    "replacementPhysicalId": frame["duringState"][
                                        "physicalId"
                                    ],
                                    "frame": frame["id"],
                                    "certainty": "CONDITIONAL",
                                }
                            )
                    else:
                        report["logicalScopes"][-1]["certainty"] = "UNKNOWN"
        emit("FRAME_ENTER", frame)
        owned = [
            p for p in report["physicalTransactions"] if p["beginFrame"] == frame["id"]
        ]
        susp = [s for s in report["suspensions"] if s["frame"] == frame["id"]]
        saves = [s for s in report["savepoints"] if s["frame"] == frame["id"]]
        for item in susp:
            emit("SUSPEND", frame, entity=item["id"], physicalId=item["physicalId"])
        for item in owned:
            emit("PHYSICAL_BEGIN", frame, entity=item["id"])
        if frame["logicalScope"]:
            emit("LOGICAL_BEGIN", frame, entity=frame["logicalScope"])
        for item in saves:
            emit(
                "SAVEPOINT_CREATE",
                frame,
                entity=item["id"],
                physicalId=item["physicalId"],
            )
        if frame["certainty"] != "UNKNOWN":
            current = copy.deepcopy(frame["duringState"])
            for call in method["calls"]:
                target, proxy, reason = resolve_call(cls, call)
                target_key = (
                    target["name"] + "#" + call["name"] + "()" if target else None
                )
                if call["arity"] != 0 or target_key not in methods:
                    report["uncertainties"].append(
                        {
                            "frame": frame["id"],
                            "reason": reason
                            if not target
                            else "OVERLOAD_OR_CALL_NOT_RESOLVED",
                            "classification": "UNKNOWN",
                            "evidence": call["evidence"],
                        }
                    )
                    emit(
                        "UNRESOLVED_CALL",
                        frame,
                        callSite=call["evidence"],
                        receiver=call["receiver"],
                        method=call["name"],
                    )
                    frame["continuation"] = "UNKNOWN"
                    break
                child = visit(
                    target_key, current, proxy, key, call["evidence"], stack + (key,)
                )
                child["receiverBindingEvidence"] = call.get("bindingEvidence")
                if (
                    child["certainty"] == "UNKNOWN"
                    or child.get("continuation") == "UNKNOWN"
                ) and not (
                    "contextComposition" in child
                    and child["contextComposition"]["premises"]["body"] == "EMPTY"
                    and child["afterState"] == current
                    and current["kind"] != "UNKNOWN"
                ):
                    frame["continuation"] = "UNKNOWN"
                    break
        for item in reversed(saves):
            emit(
                "SAVEPOINT_RELEASE_CONDITIONAL",
                frame,
                entity=item["id"],
                physicalId=item["physicalId"],
            )
        if frame["logicalScope"]:
            emit("LOGICAL_END", frame, entity=frame["logicalScope"])
        for item in owned:
            emit("PHYSICAL_END_OUTCOME_UNKNOWN", frame, entity=item["id"])
        for item in reversed(susp):
            emit(
                "RESUME_CONDITIONAL",
                frame,
                entity=item["id"],
                physicalId=item["physicalId"],
            )
        if "contextComposition" in frame:
            frame["afterState"] = copy.deepcopy(
                frame["contextComposition"]["afterState"]
            )
        elif frame["certainty"] == "UNKNOWN" or frame.get("continuation") == "UNKNOWN":
            frame["afterState"] = unknown()
        frame["effectiveContext"] = {
            key: effective_context(frame[field])
            for key, field in (
                ("before", "previousState"),
                ("during", "duringState"),
                ("after", "afterState"),
            )
        }
        emit("FRAME_EXIT", frame)
        return frame

    previous = (
        no_transaction() if context["initialState"] == "NO_TRANSACTION" else unknown()
    )
    visit(entry, previous, context["entryThroughProxy"])
    return report


def _interception_mode(report):
    # Only original v1 omits this field and records a CLASS proxy premise.
    # An explicit UNKNOWN never inherits that legacy interpretation.
    return report.get(
        "interceptionMode", "PROXY" if report.get("proxyMode") == "CLASS" else "UNKNOWN"
    )


def _validate_aop_premises(frame, report):
    """AOP premises apply even to UNKNOWN and legacy frames without advice fields."""
    mode = _interception_mode(report)
    if mode not in {"PROXY", "ASPECTJ", "UNKNOWN"}:
        raise ValueError("invalid interception mode premise")
    proxy = frame["proxy"]
    reason = proxy.get("reason")
    if mode == "ASPECTJ" and (
        proxy.get("crossed") is not False or reason != "NOT_APPLICABLE_ASPECTJ"
    ):
        raise ValueError("AspectJ scenario contradicts proxy premises")
    if reason == "NOT_APPLICABLE_ASPECTJ" and mode != "ASPECTJ":
        raise ValueError("AspectJ proxy premise requires AspectJ mode")
    if reason == "SCENARIO_PROXY_CALL" and not (
        mode == "PROXY"
        and proxy.get("crossed") is True
        and proxy.get("mode") == "CLASS"
    ):
        raise ValueError("proxy call contradicts interception mode/crossing")
    if (
        reason in {"SELF_OR_DIRECT_CALL", "NON_INTERCEPTABLE_METHOD"}
        and mode != "PROXY"
    ):
        raise ValueError("proxy bypass premise requires PROXY mode")
    advice_reason = frame.get("interception", {}).get("reason", "")
    if advice_reason.startswith("ASPECTJ_") and mode != "ASPECTJ":
        raise ValueError("AspectJ advice premise requires AspectJ mode")
    if (
        mode == "PROXY"
        and "contextComposition" in frame
        and (proxy.get("crossed") is False or reason == "NON_INTERCEPTABLE_METHOD")
    ):
        raise ValueError("advice alternatives contradict definite proxy bypass")


def _interception_status(frame, report):
    """D3: read supplied advice evidence; never infer application from L/P effects."""
    if "interception" in frame:
        return frame["interception"]["status"]
    if not frame["configuration"]:
        return "BYPASSED"
    reason = frame.get("reason", "")
    if frame["certainty"] == "UNKNOWN" and not (
        reason
        in {
            "SAVEPOINT_CAPABILITY_UNKNOWN",
            "SAVEPOINT_CAPABILITY_UNSUPPORTED",
            "SUSPENSION_CAPABILITY_UNKNOWN_OR_UNSUPPORTED",
            "AMBIGUOUS_OR_UNMODELED_MANAGER",
            "PRIOR_CONTEXT_OR_MANAGER_IDENTITY_UNKNOWN",
        }
        or reason.startswith("PROPAGATION_NOT_MODELED:")
    ):
        return "UNKNOWN"
    proxy = frame["proxy"]
    mode = _interception_mode(report)
    if mode == "PROXY":
        if (
            proxy.get("crossed") is False
            and proxy.get("reason") == "SELF_OR_DIRECT_CALL"
        ):
            return "BYPASSED"
        if (
            proxy.get("crossed") is True
            and proxy.get("mode") == "CLASS"
            and proxy.get("reason") == "SCENARIO_PROXY_CALL"
            and proxy.get("configurationEvidence")
            and all(e.get("sha256") for e in proxy["configurationEvidence"])
        ):
            return "APPLIED"
    return "UNKNOWN"


def _validate_transition(frame, report, children):
    """MR00 closed boundary effects, independently of the generator/branch builder."""
    status = _interception_status(frame, report)
    previous, during, after = (
        frame[k] for k in ("previousState", "duringState", "afterState")
    )
    conf = frame["configuration"]
    owned = {
        family: [
            s
            for s in report[family]
            if s.get("frame", s.get("beginFrame")) == frame["id"]
        ]
        for family in (
            "logicalScopes",
            "physicalTransactions",
            "savepoints",
            "suspensions",
        )
    }
    logical, physical, saves, susp = (owned[k] for k in owned)
    trace = [e for e in report["events"] if e["frame"] == frame["id"]]
    mode = _interception_mode(report)
    if (
        status == "BYPASSED"
        and conf
        and (
            mode != "PROXY"
            or not (
                frame["proxy"].get("crossed") is False
                and frame["proxy"].get("reason") == "SELF_OR_DIRECT_CALL"
                or frame["proxy"].get("reason") == "NON_INTERCEPTABLE_METHOD"
            )
        )
    ):
        raise ValueError("bypass contradicts interception mode/evidence")
    if status == "APPLIED" and not (
        conf
        and (
            mode == "PROXY"
            and frame["proxy"].get("crossed") is True
            and frame["proxy"].get("mode") == "CLASS"
            and frame["proxy"].get("reason") == "SCENARIO_PROXY_CALL"
            or mode == "ASPECTJ"
            and report["aspectjWeaving"]["application"] == "ASSUMED_APPLIED"
            and frame.get("interception", {}).get("reason")
            == "ASPECTJ_WEAVING_ASSUMED_APPLIED"
        )
    ):
        raise ValueError("applied interception lacks compatible scenario evidence")

    # D4 evidence comes from this frame's bounded uncertainty, an unresolved call,
    # or a direct child with an unresolved return. A bare UNKNOWN flag is not proof.
    reason = frame.get("reason")
    known_limits = {
        "RECURSION_OR_TRACE_BUDGET",
        "ASYNC_EXECUTION_CONTEXT",
        "INHERITANCE_OR_INTERFACE_RESOLUTION_NOT_MODELED",
        "NON_CONCRETE_BEAN_TYPE",
        "FINAL_CLASS_PROXY_NOT_ESTABLISHED",
        "BEAN_IDENTITY_NOT_ESTABLISHED",
        "UNRESOLVED_ANNOTATION_OR_META_ANNOTATION",
        "UNSUPPORTED_CONTROL_FLOW_OR_PROGRAMMATIC_EXPRESSION",
        "INACCESSIBLE_EXTERNAL_PRIVATE_METHOD",
        "INHERITED_TRANSACTION_CONTEXT_UNKNOWN",
        "AMBIGUOUS_OR_UNMODELED_MANAGER",
        "PRIOR_CONTEXT_OR_MANAGER_IDENTITY_UNKNOWN",
        "SAVEPOINT_CAPABILITY_UNSUPPORTED",
        "SAVEPOINT_CAPABILITY_UNKNOWN",
        "SUSPENSION_CAPABILITY_UNKNOWN_OR_UNSUPPORTED",
    } | ADVICE_REASONS
    linked_limit = bool(
        reason
        and (reason in known_limits or reason.startswith("PROPAGATION_NOT_MODELED:"))
        and frame["certainty"] == "UNKNOWN"
        and frame["bodyTraversal"] == "NOT_ASSERTED"
        and any(
            u["frame"] == frame["id"]
            and u["reason"] == reason
            and u["evidence"] == frame["evidence"]
            for u in report["uncertainties"]
        )
    )
    unresolved_call = any(
        e["kind"] == "UNRESOLVED_CALL"
        and any(
            u["frame"] == frame["id"] and u["evidence"] == e["callSite"]
            for u in report["uncertainties"]
        )
        for e in trace
    )
    child_unknown = any(c["afterState"]["kind"] == "UNKNOWN" for c in children)
    unresolved_return = (
        linked_limit
        or frame.get("continuation") == "UNKNOWN"
        and (unresolved_call or child_unknown)
    )
    if after == unknown() and not unresolved_return:
        raise ValueError(
            "UNKNOWN after-state lacks an unresolved continuation with evidence"
        )
    if "contextComposition" in frame:
        # validate_composition already verifies exact branch semantics/intersection.
        if [e["kind"] for e in trace] != ["FRAME_ENTER", "FRAME_EXIT"] or children:
            raise ValueError("branch-only boundary cannot assert body execution/events")
        return
    if frame["bodyTraversal"] == "NOT_ASSERTED" and (children or unresolved_call):
        raise ValueError("unasserted body contains asserted child execution")

    opening, closing = [], []

    def logical_pair(item):
        opening.append(("LOGICAL_BEGIN", item["id"]))
        closing.insert(0, ("LOGICAL_END", item["id"]))

    if status == "APPLIED":
        manager = selected_manager(conf, report["managers"])
        prop = conf["propagation"]
        resolvable = bool(
            manager
            and previous["kind"] != "UNKNOWN"
            and previous["manager"] in (None, manager["id"])
            and (previous["kind"] == "NO_TRANSACTION" or previous["physicalId"])
        )
        cap = (
            "savepoints"
            if prop == "NESTED"
            else "suspend"
            if prop == "REQUIRES_NEW"
            else None
        )
        lacks_capability = bool(
            resolvable
            and previous["physicalId"]
            and cap
            and manager["capabilities"][cap] is not True
        )
        supported = (
            resolvable
            and prop in {"REQUIRED", "REQUIRES_NEW", "NESTED"}
            and not lacks_capability
        )
        if not supported:
            if physical or saves or susp:
                raise ValueError(
                    "APPLIED effects contradict propagation/manager/capabilities"
                )
            if during != unknown() or after != unknown() or not linked_limit:
                raise ValueError(
                    "unresolved boundary requires a motivated UNKNOWN continuation"
                )
            if prop not in {"REQUIRED", "REQUIRES_NEW", "NESTED"}:
                expected_reasons = {"PROPAGATION_NOT_MODELED:" + prop}
            elif not manager:
                expected_reasons = {"AMBIGUOUS_OR_UNMODELED_MANAGER"}
            elif not resolvable:
                expected_reasons = {"PRIOR_CONTEXT_OR_MANAGER_IDENTITY_UNKNOWN"}
            elif cap == "savepoints":
                expected_reasons = {
                    "SAVEPOINT_CAPABILITY_UNSUPPORTED"
                    if manager["capabilities"][cap] is False
                    else "SAVEPOINT_CAPABILITY_UNKNOWN"
                }
            else:
                expected_reasons = {"SUSPENSION_CAPABILITY_UNKNOWN_OR_UNSUPPORTED"}
            if reason not in expected_reasons:
                raise ValueError(
                    "boundary uncertainty contradicts its capability/manager/prior cause"
                )
            if logical:
                if (
                    not lacks_capability
                    or len(logical) != 1
                    or logical[0]["physicalId"] is not None
                    or logical[0]["certainty"] != "UNKNOWN"
                ):
                    raise ValueError("invalid unresolved logical marker")
                if frame["logicalScope"] != logical[0]["id"]:
                    raise ValueError("unresolved logical marker not owned by frame")
                logical_pair(logical[0])
            elif frame["logicalScope"] is not None:
                raise ValueError("unresolved logical marker missing")
        else:
            if (
                frame["certainty"] != "CONDITIONAL"
                or frame["bodyTraversal"] != "STRAIGHT_LINE"
            ):
                raise ValueError(
                    "resolved APPLIED effects lack conditional execution premises"
                )
            fresh = previous["kind"] == "NO_TRANSACTION" or prop == "REQUIRES_NEW"
            needs_save = bool(previous["physicalId"] and prop == "NESTED")
            needs_suspend = bool(previous["physicalId"] and prop == "REQUIRES_NEW")
            if (len(logical), len(physical), len(saves), len(susp)) != (
                1,
                int(fresh),
                int(needs_save),
                int(needs_suspend),
            ):
                raise ValueError("APPLIED propagation effects/cardinality mismatch")
            if any(s["certainty"] != "CONDITIONAL" for s in saves + susp):
                raise ValueError(
                    "APPLIED effects have unresolved savepoint/suspension certainty"
                )
            identity = physical[0]["id"] if fresh else previous["physicalId"]
            expected_during = {
                "kind": "TRANSACTION_PHYSICAL",
                "physicalId": identity,
                "manager": manager["id"],
            }
            if during != expected_during or frame["manager"] != manager["id"]:
                raise ValueError(
                    "APPLIED propagation physical identity/manager mismatch"
                )
            if (
                logical[0]["id"] != frame["logicalScope"]
                or logical[0]["physicalId"] != identity
                or logical[0]["certainty"] != "CONDITIONAL"
            ):
                raise ValueError("APPLIED logical scope mapping/certainty mismatch")
            if needs_suspend:
                item = susp[0]
                if (
                    item["physicalId"] != previous["physicalId"]
                    or item["replacementPhysicalId"] != identity
                    or identity == previous["physicalId"]
                ):
                    raise ValueError("APPLIED suspension identity mismatch")
                opening.append(("SUSPEND", item["id"]))
                closing.append(("RESUME_CONDITIONAL", item["id"]))
            if fresh:
                item = physical[0]
                if (
                    item["beginFrame"] != frame["id"]
                    or item["endFrame"] != frame["id"]
                    or item["manager"] != manager["id"]
                ):
                    raise ValueError("physical ownership/manager mismatch")
                opening.append(("PHYSICAL_BEGIN", identity))
                closing.insert(0, ("PHYSICAL_END_OUTCOME_UNKNOWN", identity))
            logical_pair(logical[0])
            if needs_save:
                if saves[0]["physicalId"] != identity:
                    raise ValueError("APPLIED savepoint physical identity mismatch")
                opening.append(("SAVEPOINT_CREATE", saves[0]["id"]))
                closing.insert(0, ("SAVEPOINT_RELEASE_CONDITIONAL", saves[0]["id"]))
            if after != previous and not (after == unknown() and unresolved_return):
                raise ValueError(
                    "after-state did not restore incoming physical context"
                )
    else:
        if any(owned.values()) or frame["logicalScope"] is not None:
            raise ValueError(
                "unclassified/bypassed boundary cannot certify transactional effects"
            )
        if status == "BYPASSED":
            if during != previous and not (during == unknown() and linked_limit):
                raise ValueError("bypassed boundary changed inherited context")
            if after != previous and not (after == unknown() and unresolved_return):
                raise ValueError(
                    "after-state did not restore bypassed incoming context"
                )
        elif during != unknown() or after != unknown() or not linked_limit:
            raise ValueError(
                "unclassified interception cannot certify a positive boundary"
            )

    # Verify the complete frame projection and the position of body/child events.
    boundary = [
        (e["kind"], e.get("entity"))
        for e in trace
        if e["kind"] not in {"FRAME_ENTER", "FRAME_EXIT", "UNRESOLVED_CALL"}
    ]
    if boundary != opening + closing:
        raise ValueError("boundary effects missing or out of order")
    start = trace[len(opening)]["sequence"]
    finish = trace[-len(closing) - 1]["sequence"]
    for child in children:
        child_trace = [e for e in report["events"] if e["frame"] == child["id"]]
        if child_trace[0]["sequence"] <= start or child_trace[-1]["sequence"] >= finish:
            raise ValueError(
                "child execution outside completed boundary opening/closing"
            )
    if any(
        e["kind"] == "UNRESOLVED_CALL" and not start < e["sequence"] < finish
        for e in trace
    ):
        raise ValueError("unresolved body call outside boundary opening/closing")


def _validate_causal_order(report, frames, children):
    """Keep body order distinct from physical-state certainty and boundary unwind."""
    order_resolved = {}
    # A validated frame tree is acyclic; examine children before their parent.
    entries = [e["frame"] for e in report["events"] if e["kind"] == "FRAME_ENTER"]
    for identity in reversed(entries):
        frame = frames[identity]
        steps = [
            (e["sequence"], False)
            for e in report["events"]
            if e["frame"] == identity and e["kind"] == "UNRESOLVED_CALL"
        ]
        for child in children[identity]:
            entry = next(
                e["sequence"]
                for e in report["events"]
                if e["frame"] == child["id"] and e["kind"] == "FRAME_ENTER"
            )
            steps.append((entry, order_resolved[child["id"]]))
        body_order = True
        for _, resolved in sorted(steps):
            if not body_order:
                raise ValueError("body call follows unresolved execution order")
            body_order = resolved
        empty_body = (
            frame.get("contextComposition", {}).get("premises", {}).get("body")
            == "EMPTY"
        )
        order_resolved[identity] = body_order and (
            frame["bodyTraversal"] == "STRAIGHT_LINE" or empty_body
        )


def validate_model(report):
    """Referential/temporal checks independent of diagram text."""
    if report["schema"] != "mana.transaction-model/v1":
        raise ValueError("wrong model schema")
    frames = {f["id"]: f for f in report["frames"]}
    if len(frames) != len(report["frames"]):
        raise ValueError("duplicate frame identity")
    for frame in frames.values():
        _validate_aop_premises(frame, report)
        for field in ("previousState", "duringState", "afterState"):
            if frame[field]["kind"] not in {
                "NO_TRANSACTION",
                "TRANSACTION_PHYSICAL",
                "UNKNOWN",
            }:
                raise ValueError("invalid context state kind")
    if (
        report.get("aspectjWeaving", {}).get("runtimeApplication", "UNKNOWN")
        != "UNKNOWN"
    ):
        raise ValueError("unsubstantiated runtime weaving application")
    physical = {p["id"]: p for p in report["physicalTransactions"]}
    if len(physical) != len(report["physicalTransactions"]):
        raise ValueError("duplicate physical identity")
    manager_ids = [m["id"] for m in report["managers"]]
    if len(set(manager_ids)) != len(manager_ids):
        raise ValueError("duplicate manager identity")
    if set(report["context"]["managerCapabilities"]) - set(manager_ids):
        raise ValueError("capabilities reference an undeclared manager")
    for manager in report["managers"]:
        caps = manager["capabilities"]
        if set(caps) != {"suspend", "savepoints"} or any(
            v is not None and type(v) is not bool for v in caps.values()
        ):
            raise ValueError("invalid manager capability values")
        if caps != report["context"]["managerCapabilities"].get(
            manager["id"], {"suspend": None, "savepoints": None}
        ):
            raise ValueError("manager capabilities contradict scenario context")
    stack = []
    entered = set()
    exited = set()
    children = {identity: [] for identity in frames}
    current_contexts = {}
    active_physical = set()
    started_physical = set()
    suspended_physical = {}
    suspensions = {s["id"]: s for s in report["suspensions"]}
    scopes = {s["id"]: s for s in report["logicalScopes"] + report["savepoints"]}
    open_scopes = set()

    def require_current(identity):
        if identity and (
            identity not in active_physical or identity in suspended_physical
        ):
            raise ValueError("physical context outside its active lifetime")

    for index, event in enumerate(report["events"], 1):
        if event["sequence"] != index or event["frame"] not in frames:
            raise ValueError("invalid event trace")
        if event["kind"] not in {
            "FRAME_ENTER",
            "FRAME_EXIT",
            "PHYSICAL_BEGIN",
            "PHYSICAL_END_OUTCOME_UNKNOWN",
            "LOGICAL_BEGIN",
            "LOGICAL_END",
            "SUSPEND",
            "RESUME_CONDITIONAL",
            "SAVEPOINT_CREATE",
            "SAVEPOINT_RELEASE_CONDITIONAL",
            "UNRESOLVED_CALL",
        }:
            raise ValueError("unrecognized transaction event")
        if event["kind"] == "FRAME_ENTER":
            if event["frame"] in entered:
                raise ValueError("repeated frame entry after terminal or earlier entry")
            entered.add(event["frame"])
            frame = frames[event["frame"]]
            if stack:
                parent = frames[stack[-1]]
                children[parent["id"]].append(frame)
                site = frame["callSite"]
                if (
                    frame["callerMethod"] != parent["calleeMethod"]
                    or not site
                    or site["file"] != parent["evidence"]["file"]
                    or site.get("sha256") != parent["evidence"]["sha256"]
                    or site["start"] < parent["evidence"]["start"]
                    or site["start"] > site["end"]
                    or site["end"] > parent["evidence"]["end"]
                ):
                    raise ValueError(
                        "call site outside caller or incorrect caller identity"
                    )
                if frame["previousState"] != current_contexts[parent["id"]]:
                    raise ValueError("frame lost caller context provenance")
            elif frame["callerMethod"] is not None:
                raise ValueError("root frame has caller")
            elif len(entered) != 1 or frame["calleeMethod"] != report["entry"]:
                raise ValueError("multiple roots or root contradicts requested entry")
            elif frame["previousState"] != (
                no_transaction()
                if report["context"]["initialState"] == "NO_TRANSACTION"
                else unknown()
            ):
                raise ValueError("frame contradicts initial scenario context")
            require_current(frame["previousState"]["physicalId"])
            identity = frame["duringState"]["physicalId"]
            owned = (
                identity in physical and physical[identity]["beginFrame"] == frame["id"]
            )
            # FRAME_ENTER precedes opening events; owned P is checked at BEGIN.
            if not owned:
                require_current(frame["duringState"]["physicalId"])
                if identity and identity != frame["previousState"]["physicalId"]:
                    raise ValueError("physical identity changed without a begin event")
            stack.append(event["frame"])
            current_contexts[frame["id"]] = frame["duringState"]
        elif event["kind"] == "FRAME_EXIT":
            frame = frames[event["frame"]]
            require_current(frame["afterState"]["physicalId"])
            if frame["afterState"]["physicalId"] and (
                frame["afterState"] != frame["previousState"]
            ):
                raise ValueError(
                    "after-state did not restore incoming physical context"
                )
            exited.add(event["frame"])
            if not stack or stack.pop() != event["frame"]:
                raise ValueError("unbalanced frame trace")
            if stack:
                current_contexts[stack[-1]] = frames[event["frame"]]["afterState"]
        elif not stack or stack[-1] != event["frame"]:
            raise ValueError("event outside active method frame")
        if event["kind"] == "PHYSICAL_BEGIN":
            identity = event["entity"]
            frame = frames[event["frame"]]
            if (
                identity not in physical
                or identity in started_physical
                or physical[identity]["beginFrame"] != frame["id"]
                or frame["duringState"]["physicalId"] != identity
            ):
                raise ValueError("invalid physical begin or reused physical identity")
            previous = frame["previousState"]["physicalId"]
            if previous and (
                previous not in suspended_physical
                or suspended_physical[previous]["replacementPhysicalId"] != identity
            ):
                raise ValueError(
                    "new physical transaction did not suspend prior context"
                )
            started_physical.add(identity)
            active_physical.add(identity)
        elif event["kind"] == "PHYSICAL_END_OUTCOME_UNKNOWN":
            identity = event["entity"]
            require_current(identity)
            if (
                physical[identity]["beginFrame"] != event["frame"]
                or physical[identity]["endFrame"] != event["frame"]
            ):
                raise ValueError("physical end attached to wrong frame / ownership")
            if any(scopes[s]["physicalId"] == identity for s in open_scopes):
                raise ValueError(
                    "physical end precedes logical scope/savepoint closure"
                )
            active_physical.remove(identity)
        elif event["kind"] == "SUSPEND":
            item = suspensions[event["entity"]]
            require_current(item["physicalId"])
            if (
                event["physicalId"] != item["physicalId"]
                or item["replacementPhysicalId"] in started_physical
            ):
                raise ValueError("invalid suspension order or identity")
            suspended_physical[item["physicalId"]] = item
        elif event["kind"] == "RESUME_CONDITIONAL":
            item = suspensions[event["entity"]]
            if (
                suspended_physical.get(item["physicalId"]) != item
                or event["physicalId"] != item["physicalId"]
                or item["physicalId"] not in active_physical
                or item["replacementPhysicalId"] not in started_physical
                or item["replacementPhysicalId"] in active_physical
            ):
                raise ValueError(
                    "resume requires a live suspended context and ended replacement"
                )
            del suspended_physical[item["physicalId"]]
        elif event["kind"] in {
            "LOGICAL_BEGIN",
            "LOGICAL_END",
            "SAVEPOINT_CREATE",
            "SAVEPOINT_RELEASE_CONDITIONAL",
        }:
            item = scopes[event["entity"]]
            require_current(item["physicalId"])
            if (
                event["kind"].startswith("SAVEPOINT_")
                and event.get("physicalId") != item["physicalId"]
            ):
                raise ValueError("savepoint event contradicts physical identity")
            if event["kind"] in {"LOGICAL_BEGIN", "SAVEPOINT_CREATE"}:
                open_scopes.add(item["id"])
            else:
                if item["id"] not in open_scopes:
                    raise ValueError("scope/savepoint closed before opening")
                open_scopes.remove(item["id"])
    if stack or entered != set(frames) or exited != entered:
        raise ValueError("open frames or frames absent from trace")
    if active_physical or suspended_physical or open_scopes:
        raise ValueError("unfinished physical lifetime, suspension or scope")
    for frame in frames.values():
        if "contextComposition" in frame and "interception" not in frame:
            raise ValueError("composition requires interception observation")
        # Historical v1 fixtures may omit the additive F01 fields.
        if "effectiveContext" in frame:
            expected = {
                key: effective_context(frame[field])
                for key, field in (
                    ("before", "previousState"),
                    ("during", "duringState"),
                    ("after", "afterState"),
                )
            }
            if frame["effectiveContext"] != expected:
                raise ValueError("effective context contradicts physical state")
        if "interception" in frame:
            status = frame["interception"]["status"]
            if status not in {"APPLIED", "BYPASSED", "UNKNOWN"}:
                raise ValueError("invalid interception status")
            if status == "BYPASSED" and (
                frame["logicalScope"] is not None
                or frame["duringState"] != frame["previousState"]
                and frame["duringState"]["kind"] != "UNKNOWN"
            ):
                raise ValueError("bypassed advice changed inherited context")
            if "contextComposition" in frame:
                validate_composition(frame, report)
            elif status == "UNKNOWN" and (
                frame["duringState"] != unknown() or frame["afterState"] != unknown()
            ):
                raise ValueError("unknown advice asserted an effective context")
        for state_field in ("previousState", "duringState", "afterState"):
            state = frame[state_field]
            if state["kind"] not in {
                "NO_TRANSACTION",
                "UNKNOWN",
                "TRANSACTION_PHYSICAL",
            } or (state["physicalId"] and state["physicalId"] not in physical):
                raise ValueError("invalid context reference")
            if state["physicalId"] and (
                state["kind"] != "TRANSACTION_PHYSICAL"
                or physical[state["physicalId"]]["manager"] != state["manager"]
            ):
                raise ValueError("physical state kind/manager contradicts identity")
            if state["kind"] == "UNKNOWN" and state != unknown():
                raise ValueError("unknown state contains unproven physical properties")
            if state["kind"] == "NO_TRANSACTION" and state != no_transaction():
                raise ValueError("inactive state contains physical properties")
            if (
                state["kind"] == "TRANSACTION_PHYSICAL"
                and not state["physicalId"]
                and (state_field != "duringState" or "contextComposition" not in frame)
            ):
                raise ValueError(
                    "partial physical identity requires a composition witness"
                )
        if frame["callSite"] is not None and not frame["callSite"].get("sha256"):
            raise ValueError("missing call-site provenance")
        if not frame["evidence"].get("sha256"):
            raise ValueError("missing method provenance")
    for item in report["savepoints"]:
        frame = frames[item["frame"]]
        if (
            item["physicalId"] != frame["previousState"]["physicalId"]
            or item["physicalId"] != frame["duringState"]["physicalId"]
        ):
            raise ValueError("savepoint must share physical transaction")
    for item in report["suspensions"]:
        if item["physicalId"] == item["replacementPhysicalId"]:
            raise ValueError("independent transaction reused identity")
        frame = frames[item["frame"]]
        if (
            item["physicalId"] != frame["previousState"]["physicalId"]
            or item["replacementPhysicalId"] != frame["duringState"]["physicalId"]
        ):
            raise ValueError("suspension does not match entry context")
    families = [
        ("logicalScopes", "TRANSACTION_LOGICAL_SCOPE", "LOGICAL_BEGIN", "LOGICAL_END"),
        (
            "physicalTransactions",
            "TRANSACTION_PHYSICAL",
            "PHYSICAL_BEGIN",
            "PHYSICAL_END_OUTCOME_UNKNOWN",
        ),
        (
            "savepoints",
            "TRANSACTION_SAVEPOINT",
            "SAVEPOINT_CREATE",
            "SAVEPOINT_RELEASE_CONDITIONAL",
        ),
        ("suspensions", "TRANSACTION_SUSPENDED", "SUSPEND", "RESUME_CONDITIONAL"),
    ]
    all_ids = set()
    for family, kind, begin, end in families:
        for item in report[family]:
            if item["id"] in all_ids or item["kind"] != kind:
                raise ValueError("duplicate entity identity or wrong kind")
            all_ids.add(item["id"])
            events = [e for e in report["events"] if e.get("entity") == item["id"]]
            if [e["kind"] for e in events] != [begin, end]:
                raise ValueError("entity lifetime missing or out of order")
            owner = item.get("frame", item.get("beginFrame"))
            if owner not in frames or any(e["frame"] != owner for e in events):
                raise ValueError("entity lifetime attached to wrong frame")
            if (
                family == "logicalScopes"
                and item["physicalId"] != frames[owner]["duringState"]["physicalId"]
            ):
                raise ValueError(
                    "logical scope mapped to incorrect physical transaction"
                )
    if any(e.get("entity") and e["entity"] not in all_ids for e in report["events"]):
        raise ValueError("event references an unknown entity")
    for frame in frames.values():
        _validate_transition(frame, report, children[frame["id"]])
    _validate_causal_order(report, frames, children)
    for p in physical.values():
        if p["outcome"] != "UNKNOWN" or p["certainty"] != "CONDITIONAL":
            raise ValueError("unsubstantiated physical outcome/certainty")
        if p["runtimeIdentity"] != "UNKNOWN" or p["identity"] != "SYMBOLIC_SCENARIO":
            raise ValueError("unsubstantiated runtime identity")
    return True
