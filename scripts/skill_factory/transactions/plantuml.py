"""Render the validated ordered scenario without includes, URLs or target directives."""

import re

from .model import _interception_status


def label(value):
    return re.sub(r"[^A-Za-z0-9_.:#()/ =?\-]", "_", str(value))[:180]


def render(report):
    participants = sorted(
        {
            name.split("#")[0]
            for f in report["frames"]
            for name in (f["calleeMethod"], f["callerMethod"])
            if name
        }
    )
    aliases = {p: "B" + str(i + 1) for i, p in enumerate(participants)}
    frames = {f["id"]: f for f in report["frames"]}
    unresolved_markers = {
        item["id"]
        for item in report["logicalScopes"]
        if item["certainty"] == "UNKNOWN" and item["physicalId"] is None
    }
    lines = [
        "@startuml",
        "hide footbox",
        "title Conditional static transaction scenario - runtime identity UNKNOWN",
        'actor "Scenario entry" as Entry',
    ]
    for name, alias in aliases.items():
        lines.append(f'participant "{label(name)}" as {alias}')
    lines += [
        "legend left",
        "All P identifiers are SYMBOLIC_SCENARIO; actual runtime identity UNKNOWN.",
        "L = TRANSACTION_LOGICAL_SCOPE; P = TRANSACTION_PHYSICAL",
        "S = TRANSACTION_SUSPENDED; SP = TRANSACTION_SAVEPOINT",
        "Green: shared physical context / logical scope",
        "Blue: independent physical scope; outer P retained while SUSPENDED",
        "Yellow: nested SAVEPOINT on the SAME P",
        "Gray: NO_TRANSACTION; red: UNKNOWN / unsupported path",
        "Groups show method nesting. BEGIN/END notes define physical lifetimes.",
        "Suspended lifetime overlap is explicit in SUSPEND/RESUME notes.",
        "Interception: APPLIED / BYPASSED / UNKNOWN; context: ACTIVE / INACTIVE / UNKNOWN.",
        "INHERITED physical context does not require interception of this method.",
        "AspectJ ASSUMED_APPLIED is a conditional premise, never runtime weaving proof.",
        "endlegend",
    ]
    for event in report["events"]:
        frame = frames[event["frame"]]
        callee = aliases[frame["calleeMethod"].split("#")[0]]
        caller = (
            aliases[frame["callerMethod"].split("#")[0]]
            if frame["callerMethod"]
            else "Entry"
        )
        state = frame["duringState"]
        if event["kind"] == "FRAME_ENTER":
            prop = (frame["configuration"] or {}).get("propagation", "UNANNOTATED")
            unknown = frame["certainty"] == "UNKNOWN" or state["kind"] == "UNKNOWN"
            composition = frame.get("contextComposition")
            physical_unknown = state["kind"] == "UNKNOWN" or (
                state["kind"] == "TRANSACTION_PHYSICAL" and not state["physicalId"]
            )
            savepoint = any(s["frame"] == frame["id"] for s in report["savepoints"])
            new = any(
                p["beginFrame"] == frame["id"] for p in report["physicalTransactions"]
            )
            color = (
                "#FFCCCC"
                if (physical_unknown if composition else unknown)
                else "#FFF0AA"
                if savepoint
                else "#CCE5FF"
                if new
                else "#EEEEEE"
                if state["kind"] == "NO_TRANSACTION"
                else "#D6F5D6"
            )
            lines.append(
                f"{caller} -> {callee}: {label(frame['calleeMethod'])} / {'CANDIDATE_ATTEMPT' if unknown else 'CONDITIONAL_CALL'}"
            )
            conditional_scope = (
                composition
                and composition["alternatives"]["APPLIED"]["logicalScope"]
                == "IF_APPLIED"
            )
            scope = frame["logicalScope"] or (
                "CONDITIONAL_LOGICAL_SCOPE" if conditional_scope else "METHOD_EXECUTION"
            )
            if frame["logicalScope"] in unresolved_markers:
                scope = "UNRESOLVED_LOGICAL_MARKER " + frame["logicalScope"]
            text = (
                f"{frame['id']} {prop} {scope} {state['physicalId'] or state['kind']}"
            )
            lines.append(f"group {color} {label(text)}")
            # Accept historical v1 models, which predate the additive F01 fields.
            interception = _interception_status(frame, report)
            context = frame.get("effectiveContext", {}).get(
                "during",
                "UNKNOWN"
                if state["kind"] == "UNKNOWN"
                else "ACTIVE"
                if state["physicalId"]
                else "INACTIVE",
            )
            physical = (
                "INDEPENDENT " + state["physicalId"]
                if new
                else "INHERITED " + state["physicalId"]
                if state["physicalId"]
                else "PHYSICAL_ID_UNKNOWN"
                if state["kind"] == "TRANSACTION_PHYSICAL"
                else state["kind"]
            )
            lines.append(
                f"note right of {callee}: interception={label(interception)}; context={label(context)}; {label(physical)}"
            )
            if report.get("interceptionMode") == "ASPECTJ":
                application = report["aspectjWeaving"]["application"]
                lines.append(
                    f"note right of {callee}: ASPECTJ weaving={label(application)} / conditional scenario"
                )
            reason = frame.get("interception", {}).get(
                "reason", frame["proxy"]["reason"]
            )
            lines.append(
                f"note right of {callee}: advice={label(reason)}; manager={label(frame['manager'] or 'UNKNOWN_OR_NOT_USED')}"
            )
            if composition:
                applied = composition["alternatives"]["APPLIED"]
                lines.append(
                    f"note right of {callee}: APPLIED or BYPASSED / only common physical properties retained"
                )
                lines.append(
                    f"note right of {callee}: LOGICAL_SCOPE {label('CONDITIONAL IF_ADVICE_APPLIED' if conditional_scope else 'UNKNOWN')}; APPLIED identity={label(applied['identity'])}"
                )
                if applied["savepoint"] == "IF_APPLIED":
                    lines.append(
                        f"note right of {callee} #FFF0AA: SAVEPOINT CONDITIONAL IF_ADVICE_APPLIED on SAME {label(state['physicalId'])}"
                    )
                elif prop == "NESTED":
                    lines.append(
                        f"note right of {callee}: SAVEPOINT {label(applied['savepoint'])}; capability not inferred"
                    )
                if applied["suspension"] == "IF_APPLIED":
                    lines.append(
                        f"note right of {callee} #CCE5FF: IF_ADVICE_APPLIED: SUSPEND {label(frame['previousState']['physicalId'])} / FRESH PHYSICAL / RESUME on normal unwind"
                    )
                lines.append(
                    f"note right of {callee}: synchronous boundary; body={label(composition['premises']['body'])}; after normal unwind={label(frame['effectiveContext']['after'])} {label(frame['afterState']['physicalId'] or '')}"
                )
            if unknown:
                lines.append(
                    f"note right of {callee} #FFCCCC: UNKNOWN {label(frame['reason'])}; body NOT ASSERTED"
                )
            if frame["logicalScope"] in unresolved_markers:
                lines.append(
                    f"note right of {callee} #FFCCCC: D2 attempted boundary / execution and transactional effects NOT ESTABLISHED"
                )
                if frame["previousState"]["physicalId"]:
                    lines.append(
                        f"note right of {callee}: retained physical lifetime {label(frame['previousState']['physicalId'])} / not ended by this marker"
                    )
        elif event["kind"] == "FRAME_EXIT":
            lines.append("end")
            text = (
                "attempt/path end UNKNOWN"
                if frame["certainty"] == "UNKNOWN"
                or frame.get("continuation") == "UNKNOWN"
                else "scope exit / outcome UNKNOWN"
            )
            lines.append(f"{callee} --> {caller}: {text}")
        elif event["kind"] == "UNRESOLVED_CALL":
            lines.append(
                f"note right of {callee} #FFCCCC: UNKNOWN call {label(event['receiver'])}.{label(event['method'])}; remaining order NOT ASSERTED"
            )
        else:
            kind = event["kind"]
            if event.get("entity") in unresolved_markers:
                kind = (
                    "UNRESOLVED_LOGICAL_MARKER_BEGIN"
                    if kind == "LOGICAL_BEGIN"
                    else "UNRESOLVED_LOGICAL_MARKER_END"
                )
            lines.append(
                f"note over {callee}: {event['sequence']} {kind} {label(event.get('entity', ''))} {label(event.get('physicalId', ''))}"
            )
    lines.append("@enduml")
    return "\n".join(lines) + "\n"
