"""Render the validated ordered scenario without includes, URLs or target directives."""

import re

from .model import _interception_status, validate_model


def label(value):
    return re.sub(r"[^A-Za-z0-9_.:#()/ =?\-]", "_", str(value))[:180]


def render(report, timeline=None):
    if timeline is not None:
        from .resources import validate_timeline

        validate_timeline(timeline)
        if timeline["transactionModel"] != report:
            raise ValueError("renderer timeline references another T01 model")
    elif (
        "resourceLeafExtension" in report
        or report.get("context", {}).get("resourceLeafPolicy", "DISABLED") != "DISABLED"
        or any(e["kind"] == "RESOURCE_LEAF_CALL" for e in report["events"])
    ):
        validate_model(report)
    if any(
        e["kind"]
        not in {
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
            "RESOURCE_LEAF_CALL",
        }
        for e in report["events"]
    ):
        raise ValueError("renderer does not support transaction event")
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
        if timeline is not None:
            for observation in timeline["observations"]:
                if (
                    observation["placement"].get("beforeT01Sequence")
                    == event["sequence"]
                ):
                    operation = observation["applicationOperation"]
                    context = observation["transactionContext"]
                    site = observation["callSite"]
                    color = (
                        "#FFCCCC"
                        if observation["operationType"] == "UNKNOWN"
                        or context["kind"] == "UNKNOWN"
                        else "#EEEEEE"
                        if context["kind"] == "NO_TRANSACTION"
                        else "#D6F5D6"
                    )
                    position = next(
                        t["sequence"]
                        for t in timeline["timeline"]
                        if t["kind"] == "RESOURCE_OPERATION"
                        and t["observation"] == observation["id"]
                    )
                    lines.append(
                        f"note right of {callee} {color}: JDBC {label(observation['id'])} "
                        f"{label(operation['receiver'])}.{label(operation['method'])} "
                        f"{label(observation['operationType'])} {label(observation['resource'].get('name') or 'UNKNOWN')}"
                        f"\\nCONDITIONAL timeline={position} before T01={event['sequence']} "
                        f"context={label(context['physicalId'] or context['kind'])} "
                        f"manager={label(context['manager'])}"
                        f"\\n{label(site['file'])}:{site['line']} / lockAcquired=UNKNOWN"
                    )
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
            if timeline is not None:
                site = frame.get("callSite") or frame["evidence"]
                lines.append(
                    f"note right of {callee}: bean={label(frame.get('beanName') or frame.get('bean') or 'UNKNOWN')} "
                    f"proxy={label(frame['proxy']['mode'])} crossed={label(frame['proxy']['crossed'])}"
                    f"\\nsource={label(site['file'])}:{site['line']} / VERIFIED static reference"
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
        elif event["kind"] == "RESOURCE_LEAF_CALL":
            if timeline is not None:
                lines.append(
                    f"note right of {callee} #CCE5FF: RESOURCE_LEAF_CALL T01={event['sequence']} / witness in evidence.json"
                    "\\nContinuation IF normal return / context preserved under catalog premises"
                    "\\nRuntime execution UNKNOWN"
                )
            else:
                lines.append(
                    f"note right of {callee} #CCE5FF: RESOURCE_LEAF_CALL {label(event['witness']['signature'])}; continuation IF normal return; context preserved under catalog premises; runtime execution UNKNOWN"
                )
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
            if timeline is not None and kind == "SUSPEND":
                lines.append(
                    f"note over {callee} #CCE5FF: {label(event['physicalId'])} LIVE / SUSPENDED"
                    "\\nRetained until conditional resume; no commit or automatic lock release"
                )
    if timeline is not None:
        for observation in timeline["observations"]:
            if observation["placement"]["status"] == "UNPLACED":
                lines.append(
                    "note over Entry #FFCCCC: UNPLACED / no temporal position asserted: "
                    f"{label(observation['id'])} {label(observation['operationType'])} "
                    f"{label(observation['resource'].get('name') or 'UNKNOWN')} / context UNKNOWN"
                )
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def render_integrated(report, raw_inputs):
    """Validate the full projection before emitting any source; never derive claims."""
    import json

    from .wait_dependencies import BUDGETS, parse_json
    from .wait_validation import validate_report

    validate_report(report, raw_inputs)
    artifacts = {}
    scenario = report["scenario"]["id"]
    banner = [
        "KNOWN / VERIFIED = validated static structure only; execution CONDITIONAL.",
        "UNKNOWN is not absence. Runtime NOT_RUN; locks and waits are not observed.",
        "P IDs are participant-local symbolic identities; no confirmed deadlock claim.",
        "Coverage: " + label(report["coverage"]["status"]),
        "Assessment: " + label(report["assessment"]["result"]),
    ]
    banner += ["INCOMPLETE: " + label(v) for v in report["coverage"]["reasons"]]
    for value in report["unknowns"]:
        if isinstance(value, dict) and "candidate" in value:
            banner += [
                "Candidate "
                + label(value["candidate"])
                + " / cut="
                + label(value.get("cut"))
                + " / "
                + label(value.get("reason")),
                "UNKNOWN obligations: "
                + ", ".join(label(v) for v in value.get("missingObligations", []))
                + "; contradicted: "
                + ", ".join(label(v) for v in value.get("contradictedObligations", [])),
            ]
        else:
            banner.append("UNKNOWN: " + label(value))
    banner += [
        "No universal deadlock freedom. See evidence.json for full source references.",
        "DB dashed red = candidate wait; app solid blue = synchronous completion.",
        "Mixed dotted purple = typed relation, not an additional DB wait edge.",
        "Application/typed links are scenario-wide; only DB edges are filtered by cut.",
    ]

    for participant in report["scenario"]["participants"]:
        timeline = parse_json(
            raw_inputs[participant["input"]], BUDGETS["timelineBytes"]
        )
        source = render(timeline["transactionModel"], timeline)
        header = [
            "note over Entry #FFF0AA",
            "Scenario "
            + label(scenario)
            + " / participant "
            + label(participant["id"]),
            "Local causal order only; panels are not a global concurrent schedule.",
            "SUSPEND retains lifetime; neither END nor suspension proves lock release.",
            *banner[:5],
            "end note",
        ]
        source = source.replace(
            "endlegend\n", "endlegend\n" + "\n".join(header) + "\n", 1
        )
        artifacts["sequence-" + participant["id"] + ".puml"] = source

    claims = {c["id"]: c for c in report["claims"]}

    def namespace_key(ns):
        return json.dumps(ns, sort_keys=True)

    def graph_source(title, graphs, relations=(), cut=None):
        lines = [
            "@startuml",
            "top to bottom direction",
            "skinparam shadowing false",
            "title " + label(scenario) + " / " + title,
        ]
        aliases = {}

        def node(ns):
            key = namespace_key(ns)
            if key not in aliases:
                alias = "N" + str(len(aliases) + 1)
                aliases[key] = alias
                kind = "PHYSICAL " if "originalPhysicalId" in ns else "FRAME "
                name = (
                    ns.get("originalPhysicalId")
                    or ns.get("originalFrameId")
                    or "UNKNOWN"
                )
                lines.append(
                    f'rectangle "{kind}{label(ns["participantId"])} / {label(name)}" as {alias} '
                    + ("#CCE5FF" if kind.startswith("PHYSICAL") else "#D6F5D6")
                )
            return aliases[key]

        for graph, category in graphs:
            nodes = {n["id"]: n["namespace"] for n in graph["nodes"]}
            for ns in nodes.values():
                node(ns)
            for edge in graph["edges"]:
                if (
                    category == "DATABASE"
                    and cut is not None
                    and edge.get("cut") != cut
                ):
                    continue
                a, b = node(nodes[edge["from"]]), node(nodes[edge["to"]])
                claim = claims[edge["claim"]]
                style = (
                    "-[#B03030,dashed]->" if category == "DATABASE" else "-[#245A9C]->"
                )
                details = [category + " DEPENDENCY " + claim["id"], "CONDITIONAL"]
                if category == "DATABASE":
                    details += [
                        "resource=" + label(edge["resource"]),
                        "cut=" + label(edge["cut"]),
                        "candidate=" + label(claim["candidate"]),
                    ]
                else:
                    details += ["synchronous FRAME_COMPLETION"]
                lines.append(f"{a} {style} {b}: " + "\\n".join(details))
                lines += [
                    f"note right of {a}",
                    "Claim " + label(claim["id"]) + " / evidence.json",
                    "sources: "
                    + ", ".join(label(ref) for ref in claim["operationRefs"]),
                ]
                if category == "APPLICATION":
                    site = claim["source"]["callSite"]
                    lines.append(
                        "call site: " + label(site["file"]) + ":" + str(site["line"])
                    )
                # Keep full premise IDs visible, wrapped rather than silently clipped.
                for i in range(0, len(claim["premises"]), 3):
                    lines.append(
                        "premises: "
                        + ", ".join(label(p) for p in claim["premises"][i : i + 3])
                    )
                lines.append("end note")
        relation_groups = {}
        for index, relation in enumerate(relations, 1):
            if "physical" in relation and "replacement" in relation:
                a, b = node(relation["physical"]), node(relation["replacement"])
            elif "frame" in relation and "physical" in relation:
                a, b = node(relation["frame"]), node(relation["physical"])
            else:
                continue
            relation_groups.setdefault((a, b, relation["type"]), []).append(
                "R" + str(index)
            )
        for (a, b, kind), refs in relation_groups.items():
            # Wrap the resume type at a word boundary: SVG viewers can use
            # wider font metrics than PlantUML's textLength calculation.
            mixed_label = (
                "MIXED / RESUME_REQUIRES_\\nCOMPLETION"
                if kind == "RESUME_REQUIRES_COMPLETION"
                else f"MIXED / {label(kind)}"
            )
            lines.append(
                f"{a} -[#8050A0,dotted]-> {b}: {mixed_label}\\nCONDITIONAL / "
                + ", ".join(refs)
                + " / evidence.json"
            )
        summary = list(banner)
        if cut is not None:
            assessment = next(
                c for c in report["assessment"]["cuts"] if c["cut"] == cut
            )
            summary += [
                "Cut " + label(cut),
                label(assessment["result"]),
                "Exclusion is scoped; missing evidence remains UNKNOWN.",
            ]
            if assessment["result"] == "NO_CYCLE_IN_MODELED_SCENARIO":
                summary += [
                    "Validated S02 structural exclusion in this cut / selected scope only.",
                    "This is distinct from missing acquisition or retention evidence.",
                ]
            for claim in report["claims"]:
                if claim["category"] == "LOCK_CONFLICT_CANDIDATE":
                    summary += [
                        "CONFLICT "
                        + label(claim["id"])
                        + " CONDITIONAL / UNORIENTED / holder UNKNOWN",
                        "resource="
                        + label(claim["resource"])
                        + " sources="
                        + ", ".join(label(ref) for ref in claim["operationRefs"]),
                    ]
            for candidate in report["waitCandidates"]:
                if candidate["cut"] != cut or candidate["status"] == "QUALIFIED":
                    continue
                summary += [
                    "Candidate "
                    + label(candidate["id"])
                    + " "
                    + label(candidate["status"]),
                    *[
                        label(o["id"]) + " " + label(o["state"])
                        for o in candidate["obligations"]
                        if o["state"] in {"UNKNOWN", "CONTRADICTED"}
                    ],
                ]
        lines += ["legend left", *summary, "endlegend", "@enduml"]
        return "\n".join(lines) + "\n"

    cuts = [c["cut"] for c in report["assessment"]["cuts"]]
    for cut in cuts:
        artifacts["database-" + cut + ".puml"] = graph_source(
            "DATABASE DEPENDENCY", [(report["databaseGraph"], "DATABASE")], cut=cut
        )
    if not cuts:
        artifacts["database.puml"] = graph_source(
            "DATABASE DEPENDENCY / no qualified cut",
            [(report["databaseGraph"], "DATABASE")],
        )
    artifacts["application.puml"] = graph_source(
        "APPLICATION DEPENDENCY", [(report["applicationGraph"], "APPLICATION")]
    )
    # Never union DB edges across different cuts into a purported feasible circuit.
    for cut in cuts or [None]:
        artifacts["mixed" + ("-" + cut if cut else "") + ".puml"] = graph_source(
            "MIXED DEPENDENCY / typed links",
            [
                (report["databaseGraph"], "DATABASE"),
                (report["applicationGraph"], "APPLICATION"),
            ],
            report["crossLayerRelations"],
            cut=cut,
        )
    artifacts["evidence.json"] = (
        json.dumps(
            {
                "schema": "mana.transaction-visualization/v1",
                "validatedS02": report,
                "relationRefs": {
                    "R" + str(i): r
                    for i, r in enumerate(report["crossLayerRelations"], 1)
                },
                "views": sorted(artifacts),
            },
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )
    return artifacts
