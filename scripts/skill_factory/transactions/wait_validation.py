"""S02 output invariants plus full source/reference projection verification."""

from .wait_dependencies import (
    BUDGETS,
    LIMITS,
    BudgetExceeded,
    RejectedInput,
    _derive_report,
    Inputs,
    Scenario,
    build_report,
    cut_consistency,
    inventory,
    keys,
    missing_holding_evidence,
    node_id,
    obligations,
    require,
    scope_problems,
    structural_cycle,
    unique,
)

CATEGORIES = {
    "RESOURCE_OPERATION",
    "LOCK_REQUEST_CANDIDATE",
    "LOCK_CONFLICT_CANDIDATE",
    "DB_WAIT_DEPENDENCY",
    "APPLICATION_WAIT_DEPENDENCY",
}


def acyclic_source_graph(edges):
    """Independent topological check; does not call the producer's DFS."""
    adjacency, indegree = {}, {}
    for edge in edges:
        a, b = edge["from"], edge["to"]
        adjacency.setdefault(a, []).append(b)
        indegree.setdefault(a, 0)
        indegree[b] = indegree.get(b, 0) + 1
    ready = [n for n, degree in indegree.items() if degree == 0]
    removed = 0
    while ready:
        n = ready.pop()
        removed += 1
        for child in adjacency.get(n, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    return removed == len(indegree)


def source_completion_edges(s, cut, apps, compare):
    edges = []
    for app in apps:
        compare()
        pid = app["participant"]
        if not app["enterT01Sequence"] < cut["prefixes"][pid] <= app["exitT01Sequence"]:
            continue
        require(
            app["callerPhysical"] is not None and app["calleePhysical"] is not None,
            "exclusion has unknown application context",
        )
        if app["callerPhysical"] != app["calleePhysical"]:
            template = {
                "scenarioId": s.value["id"],
                "participantId": pid,
                "inputDigest": s.inputs.meta[s.participants[pid]["input"]]["sha256"],
            }
            edges.append(
                {
                    "from": node_id(
                        {**template, "originalPhysicalId": app["callerPhysical"]}
                    ),
                    "to": node_id(
                        {**template, "originalPhysicalId": app["calleePhysical"]}
                    ),
                    "type": "APPLICATION_COMPLETION",
                    "evidence": [app],
                }
            )
    return edges


def validate_structural_exclusion(s, cut, selected, apps, proof, consistency, compare):
    """Reconstruct the proof without the producer's proof/cycle functions.

    Canonical v1 has no certificate field. A historical F02 certificate, when
    supplied, must equal this source reconstruction. Reconstruct all possible
    frontier/prior pairs and active app links, then eliminate zero-indegree
    nodes. Unknown lock facts never remove an edge.
    """
    problems, unresolved = consistency
    require(
        not problems and all(u.startswith("W4:") for u in unresolved),
        "structural exclusion has unresolved causal scope",
    )
    require(selected, "structural exclusion requires selected source operations")
    require(
        len(selected)
        == sum(len(s.report(pid)["observations"]) for pid in s.participants),
        "structural exclusion omits source operations",
    )
    live, suspended = {}, {}
    for pid, before in cut["prefixes"].items():
        live[pid], suspended[pid] = set(), set()
        for e in s.report(pid)["transactionModel"]["events"]:
            require(
                e["kind"] != "UNRESOLVED_CALL" or e["sequence"] > before,
                "structural exclusion crosses an unresolved frontier",
            )
            if e["sequence"] >= before:
                continue
            if e["kind"] == "PHYSICAL_BEGIN":
                live[pid].add(e["entity"])
            elif e["kind"] == "PHYSICAL_END_OUTCOME_UNKNOWN":
                live[pid].discard(e["entity"])
            elif e["kind"] == "SUSPEND":
                suspended[pid].add(e["physicalId"])
            elif e["kind"] == "RESUME_CONDITIONAL":
                suspended[pid].discard(e["physicalId"])
    require(
        all(
            o["t01Sequence"] is not None
            and o["namespace"]["originalPhysicalId"] is not None
            for o in selected.values()
        ),
        "structural exclusion needs identified positioned endpoints",
    )
    expected = []
    for q in selected.values():
        qp, physical = (
            q["namespace"]["participantId"],
            q["namespace"]["originalPhysicalId"],
        )
        if (
            q["t01Sequence"] != cut["prefixes"][qp]
            or physical not in live[qp]
            or physical in suspended[qp]
        ):
            continue
        for h in selected.values():
            compare()
            hp = h["namespace"]["participantId"]
            if (
                h["namespace"] != q["namespace"]
                and h["t01Sequence"] < cut["prefixes"][hp]
                and h["namespace"]["originalPhysicalId"] in live[hp]
            ):
                expected.append(
                    {
                        "from": node_id(q["namespace"]),
                        "to": node_id(h["namespace"]),
                        "type": "POSSIBLE_DB_WAIT",
                        "evidence": [q["id"], h["id"]],
                    }
                )
    expected.extend(source_completion_edges(s, cut, apps, compare))
    require(
        proof is None
        or proof
        == {
            "kind": "STRUCTURAL_EXCLUSION",
            "rule": "ACYCLIC_CAUSAL_SUPERGRAPH",
            "operationRefs": sorted(o["id"] for o in selected.values()),
            "prefixes": cut["prefixes"],
            "upperBoundEdges": expected,
            "scope": "Selected operations at this cut; no lock or runtime absence asserted.",
        },
        "structural exclusion certificate differs from authoritative source upper bound",
    )
    require(
        acyclic_source_graph(expected),
        "structural exclusion upper bound contains a DB/application circuit",
    )
    return [e for e in expected if e["type"] == "POSSIBLE_DB_WAIT"]


def validate_negative_assessments(report, raw_inputs):
    """Authorize negative claims from sources, never from producer W/status flags.

    Reconstruct source positions and premise dependencies before the final full
    projection comparison. A contradicted candidate is excluded; an unresolved
    candidate is not. D00's same-P proof without cuts is a separate narrow case.
    """
    negative = "NO_CYCLE_IN_MODELED_SCENARIO"
    cuts = report["assessment"]["cuts"]
    global_negative = report["assessment"]["result"] == negative
    if not global_negative and not any(c["result"] == negative for c in cuts):
        return
    value = report["scenario"]
    s = Scenario(value, Inputs(raw_inputs, unique(value["inputs"])))
    require(not scope_problems(s), "NO_CYCLE requires supported complete cut scope")
    operations, apps, _ = inventory(s)
    opmap = {o["id"]: o for o in operations}
    selected = {
        key: opmap[o["participant"] + "/" + o["observation"]]
        for key, o in s.selected.items()
    }
    require(
        len(cuts) == len(s.cuts) and {c["cut"] for c in cuts} == set(s.cuts),
        "NO_CYCLE cut inventory differs from source scenario",
    )
    if global_negative:
        same_identity = (
            len(selected) >= 2
            and all(
                o["namespace"]["originalPhysicalId"] is not None
                and o["t01Sequence"] is not None
                for o in selected.values()
            )
            and len({node_id(o["namespace"]) for o in selected.values()}) == 1
            and len({o["observation"]["frame"] for o in selected.values()}) >= 2
        )
        require(
            all(c["result"] == negative for c in cuts) if s.cuts else same_identity,
            "NO_CYCLE requires every cut qualified or the D00 same-P identity proof",
        )
        require(
            not structural_cycle(report["databaseGraph"]["edges"]),
            "NO_CYCLE cannot certify a cyclic union of cuts",
        )
        if not s.cuts:
            require(
                report["assessment"].get("exclusionProof") is None
                or report["assessment"]["exclusionProof"]
                == {
                    "kind": "STRUCTURAL_EXCLUSION",
                    "rule": "SINGLE_PHYSICAL_IDENTITY",
                    "operationRefs": sorted(o["id"] for o in selected.values()),
                },
                "invalid same-P structural exclusion certificate",
            )
    comparisons = 0
    source_edges = []

    def compare():
        nonlocal comparisons
        comparisons += 1
        if comparisons > BUDGETS["candidateComparisons"]:
            raise BudgetExceeded(
                "negative evidence validation budget; coverage INCOMPLETE"
            )

    for assessment in cuts:
        if assessment["result"] != negative:
            continue
        cut = s.cuts[assessment["cut"]]
        proof = assessment.get("exclusionProof")
        require(proof is None or isinstance(proof, dict), "invalid exclusion proof")
        consistency = cut_consistency(s, cut, selected, compare)
        bound = None
        structural_route = (
            proof is None
            and (
                assessment["unknowns"]
                or consistency[1]
                or not cut["pending"]
                or not cut["holdings"]
            )
        ) or (proof is not None and proof.get("kind") == "STRUCTURAL_EXCLUSION")
        # Prefer the existing evidence-complete path for complete negatives.
        # Its source guards below establish completeness; these flags only
        # select which independent proof to attempt, never authorize a claim.
        if structural_route:
            try:
                bound = validate_structural_exclusion(
                    s, cut, selected, apps, proof, consistency, compare
                )
            except RejectedInput:
                # A source supergraph can be cyclic while qualified/contradicted
                # lock candidates exclude a cycle. Only an absent certificate
                # can fall back; an explicit false certificate must be rejected.
                if proof is not None:
                    raise
        if bound is not None:
            required_unknowns = list(consistency[1]) + missing_holding_evidence(
                s, cut, selected, consistency, compare
            )
            for qid in cut["pending"]:
                for held in cut["holdings"]:
                    compare()
                    ledger = obligations(
                        s,
                        cut,
                        s.selected[qid],
                        s.selected[held["operation"]],
                        held,
                        selected,
                        consistency,
                    )
                    if not any(w["state"] == "CONTRADICTED" for w in ledger):
                        required_unknowns.extend(
                            w["id"] + ": " + w["reason"]
                            for w in ledger
                            if w["state"] == "UNKNOWN"
                        )
            require(
                set(required_unknowns) <= set(assessment["unknowns"]),
                "structural exclusion hides unresolved source evidence",
            )
            require(
                not required_unknowns or report["coverage"]["status"] == "INCOMPLETE",
                "structural exclusion cannot complete missing lock evidence",
            )
            if not cut["pending"] or not cut["holdings"]:
                require(
                    {
                        "cut": cut["id"],
                        "reason": "NO_ORIENTED_WAIT_HYPOTHESIS",
                        "missingObligations": ["W4"],
                    }
                    in report["unknowns"],
                    "structural exclusion hides global W4 uncertainty",
                )
            allowed = {(e["from"], e["to"]) for e in bound}
            require(
                all(
                    (e["from"], e["to"]) in allowed
                    for e in report["databaseGraph"]["edges"]
                    if e["cut"] == cut["id"]
                ),
                "DB edge outside structural source upper bound",
            )
            source_edges.extend(bound)
            continue
        require(
            proof is None
            or proof
            == {
                "kind": "EVIDENCE_COMPLETE_EXCLUSION",
                "rule": "QUALIFIED_OR_CONTRADICTED_CANDIDATES",
                "candidateRefs": [
                    c["id"] for c in report["waitCandidates"] if c["cut"] == cut["id"]
                ],
            },
            "invalid evidence-complete exclusion certificate",
        )
        # Explicit source guard: a fabricated MODEL_EVIDENCE W4 ledger, an empty
        # graph, or a COMPLETE coverage flag cannot supply missing holdings.
        require(
            cut["pending"] and cut["holdings"],
            "NO_CYCLE requires W4 request and separate acquisition/retention evidence",
        )
        require(not consistency[1], "NO_CYCLE has unresolved cut evidence")
        require(
            not missing_holding_evidence(s, cut, selected, consistency, compare),
            "NO_CYCLE lacks W4 evidence for a prior potential holder",
        )
        require(not assessment["unknowns"], "NO_CYCLE reports unresolved cut premises")
        cut_edges = []
        for qid in cut["pending"]:
            for held in cut["holdings"]:
                compare()
                ledger = obligations(
                    s,
                    cut,
                    s.selected[qid],
                    s.selected[held["operation"]],
                    held,
                    selected,
                    consistency,
                )
                states = {w["state"] for w in ledger}
                require(
                    "CONTRADICTED" in states or "UNKNOWN" not in states,
                    "NO_CYCLE has source obligations UNKNOWN: "
                    + ", ".join(w["id"] for w in ledger if w["state"] == "UNKNOWN"),
                )
                if states <= {"MODEL_EVIDENCE", "EXPLICIT_ASSUMPTION"}:
                    cut_edges.append(
                        {
                            "from": node_id(selected[qid]["namespace"]),
                            "to": node_id(selected[held["operation"]]["namespace"]),
                        }
                    )
        source_edges.extend(cut_edges)
        require(
            acyclic_source_graph(
                cut_edges + source_completion_edges(s, cut, apps, compare)
            ),
            "NO_CYCLE contradicts a DB/application cycle qualified by source evidence",
        )
        require(
            not structural_cycle(
                [e for e in report["databaseGraph"]["edges"] if e["cut"] == cut["id"]]
            ),
            "NO_CYCLE cut contains a structural cycle",
        )
    if global_negative:
        require(
            acyclic_source_graph(source_edges),
            "NO_CYCLE contradicts the union of source-qualified cuts",
        )


def validate_report(report, raw_inputs):
    """Check invariants independently of serialization; then verify full derivation.

    Semantic acceptance is also tested against independent manual A-J oracles.
    Reprojection alone is not the semantic oracle.
    """
    keys(
        report,
        (
            "schema",
            "status",
            "inputs",
            "scenario",
            "operations",
            "claims",
            "waitCandidates",
            "databaseGraph",
            "applicationGraph",
            "crossLayerRelations",
            "unknowns",
            "limits",
            "coverage",
            "assessment",
        ),
    )
    require(
        report["schema"] == "mana.wait-dependency/v1"
        and report["status"] == "CONDITIONAL_STATIC_SCENARIO",
        "invalid S02 envelope",
    )
    require(report["limits"] == LIMITS, "missing S02 limitations")
    operations = {o["id"]: o for o in report["operations"]}
    require(len(operations) == len(report["operations"]), "duplicate operation")
    claims = {c["id"]: c for c in report["claims"]}
    require(len(claims) == len(report["claims"]), "duplicate claim")
    candidates = {c["id"]: c for c in report["waitCandidates"]}
    require(
        len(candidates) == len(report["waitCandidates"]), "duplicate wait candidate"
    )
    for op in operations.values():
        obs = op["observation"]
        require(
            op["namespace"]["originalPhysicalId"]
            == obs["transactionContext"]["physicalId"],
            "physical identity override",
        )
        if obs["placement"]["status"] == "UNPLACED":
            require(
                op["t01Sequence"] is None and op["timelineSequence"] is None,
                "unplaced operation promoted to causal position",
            )
        else:
            require(
                op["t01Sequence"] == obs["placement"]["beforeT01Sequence"]
                and type(op["timelineSequence"]) is int,
                "Timeline/T01 sequence confusion",
            )
    for c in claims.values():
        require(c["category"] in CATEGORIES, "unknown claim category")
        require(
            c["modelPremises"]
            and all(
                p["state"] == "MODEL_EVIDENCE" and p["provenance"]["reference"]
                for p in c["modelPremises"]
            ),
            "missing model premise provenance",
        )
        require(
            c["certainty"] in {"STATIC_SYNTAX", "CONDITIONAL", "UNKNOWN"},
            "OBSERVED requires R1-R7 and a separate runtime mandate",
        )
        require(
            all(o in operations for o in c["operationRefs"]), "unknown source operation"
        )
        require(
            c["propertyCertainty"]
            == {"runtimeExecution": "UNKNOWN", "runtimeWait": "UNKNOWN"},
            "static runtime certainty promotion",
        )
        if c["category"] == "DB_WAIT_DEPENDENCY":
            require(
                c["certainty"] == "CONDITIONAL" and len(c["operationRefs"]) == 2,
                "invalid DB dependency",
            )
            a, b = [operations[o] for o in c["operationRefs"]]
            require(
                a["namespace"] == c["waiter"] and b["namespace"] == c["blocker"],
                "waiter/blocker source reference mismatch",
            )
            require(
                c["waiter"] != c["blocker"]
                and all(
                    c[x]["originalPhysicalId"] is not None
                    for x in ("waiter", "blocker")
                ),
                "unknown endpoint or database self-loop",
            )
            require(
                all(x["t01Sequence"] is not None for x in (a, b)),
                "UNPLACED source in DB wait",
            )
            require(
                [w["id"] for w in c["obligations"]]
                == ["W" + str(i) for i in range(1, 9)],
                "missing W1-W8",
            )
            require(
                all(
                    w["state"] in {"MODEL_EVIDENCE", "EXPLICIT_ASSUMPTION"}
                    and w["reason"]
                    and w["evidence"]
                    for w in c["obligations"]
                ),
                "unproven DB obligation",
            )
            require(
                c["candidate"] in candidates
                and candidates[c["candidate"]]["status"] == "QUALIFIED",
                "unqualified wait candidate",
            )
            require(
                c["holding"]["acquisitionPremise"] and c["holding"]["retentionPremise"],
                "holding without acquisition/retention provenance",
            )
        if c["category"] == "APPLICATION_WAIT_DEPENDENCY":
            require(
                c["resource"]
                == {
                    "kind": "FRAME_COMPLETION",
                    "granularity": "FRAME",
                    "database": "NOT_APPLICABLE",
                },
                "application completion conflated with database resource",
            )
            require(
                c["source"]["callSite"] and c["caller"] != c["callee"],
                "application call lacks resolved source frame",
            )
    total = 0
    for graph_name, category in (
        ("databaseGraph", "DB_WAIT_DEPENDENCY"),
        ("applicationGraph", "APPLICATION_WAIT_DEPENDENCY"),
    ):
        graph = report[graph_name]
        keys(graph, ("nodes", "edges"))
        nodes = {n["id"]: n for n in graph["nodes"]}
        require(len(nodes) == len(graph["nodes"]), "merged or duplicate namespace node")
        for n in nodes.values():
            require(n["id"] == node_id(n["namespace"]), "namespace tuple corruption")
            if graph_name == "databaseGraph":
                require(
                    n["namespace"]["originalPhysicalId"] is not None,
                    "invented P for null identity",
                )
        seen = set()
        for edge in graph["edges"]:
            total += 1
            require(
                edge["from"] in nodes and edge["to"] in nodes, "unknown graph endpoint"
            )
            require(
                edge["claim"] in claims
                and claims[edge["claim"]]["category"] == category,
                "wrong graph edge category",
            )
            require(edge["claim"] not in seen, "duplicated graph claim")
            seen.add(edge["claim"])
            c = claims[edge["claim"]]
            require(
                edge["certainty"] == c["certainty"] == "CONDITIONAL",
                "graph certainty mismatch",
            )
            if category == "DB_WAIT_DEPENDENCY":
                require(
                    edge["from"] == node_id(c["waiter"])
                    and edge["to"] == node_id(c["blocker"])
                    and edge["cut"] == c["cut"],
                    "DB direction/cut mismatch",
                )
            else:
                require(
                    edge["from"] == node_id(c["caller"])
                    and edge["to"] == node_id(c["callee"]),
                    "application direction mismatch",
                )
        require(
            seen == {c["id"] for c in claims.values() if c["category"] == category},
            "missing dependency graph edge",
        )
    require(
        total
        + len(report["crossLayerRelations"])
        + sum(
            len(c["exclusionProof"].get("upperBoundEdges", []))
            for c in report["assessment"]["cuts"]
            if c.get("exclusionProof")
        )
        <= BUDGETS["serializedEdges"],
        "serialized edge budget exceeded",
    )
    require(
        all(
            r["type"] in {"EXECUTES_IN", "SUSPENDS_FOR", "RESUME_REQUIRES_COMPLETION"}
            and r["evidence"]
            for r in report["crossLayerRelations"]
        ),
        "invalid cross-layer relation",
    )
    require(
        report["coverage"]["globalRiskAbsence"] == "NOT_ASSERTED"
        and report["coverage"]["runtime"] == "NOT_RUN",
        "unqualified global/runtime conclusion",
    )
    validate_negative_assessments(report, raw_inputs)
    # Revalidate original input bytes and the scenario, including cut semantics,
    # source witness, premise dependencies and the inventory's exact completeness.
    expected = build_report(raw_inputs, report["scenario"])
    if report != expected and (
        "exclusionProof" in report["assessment"]
        or any("exclusionProof" in cut for cut in report["assessment"]["cuts"])
    ):
        # Read historical F02 artifacts strictly, including their counters and
        # every certificate byte. This shape is never emitted as public v1.
        expected, _ = _derive_report(raw_inputs, report["scenario"])
    require(report == expected, "S02 derivation/reference projection mismatch")
    return True
