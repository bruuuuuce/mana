"""Verified dependency declarations attached to T01, never execution events.

The selected EXEC closure is not a complete inventory of executable dependencies.
This first contract deliberately has no positive reachability/admission variant.
"""

import copy
import hashlib
import json

from .execution import SCHEMA as WITNESS_SCHEMA, verify_execution_snapshot

SCHEMA = "mana.executable-dependency-contract/v1"
FIELD = "executableDependencyExtension"
LIMITS = [
    "SELECTED_CLOSURE_NOT_EXECUTION_COMPLETENESS",
    "REACHABILITY_AND_EVALUATION_NOT_ESTABLISHED",
    "TRANSACTION_INTERCEPTION_NOT_ESTABLISHED",
]


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _projection(witness, report):
    if (
        witness.get("schema") != WITNESS_SCHEMA
        or witness.get("status") not in {"COMPLETE", "INCOMPLETE"}
        or witness.get("transactionTraversal") != "NOT_ASSERTED"
    ):
        raise ValueError("dependency witness has no admissible static recovery")
    if len(_encoded(witness)) > 4 * 1024 * 1024:
        raise ValueError("dependency witness exceeds payload bound")
    hashes = {e["path"]: e["sha256"] for e in report["evidence"]}
    if any(hashes.get(p) != h for p, h in witness["sources"].items()):
        raise ValueError("dependency sources differ from T01 evidence")

    def evidence(ev):
        if (
            not isinstance(ev, dict)
            or set(ev) != {"file", "sha256", "start", "end", "line"}
            or hashes.get(ev["file"]) != ev["sha256"]
            or any(type(ev[k]) is not int for k in ("start", "end", "line"))
            or not 0 <= ev["start"] < ev["end"]
            or ev["line"] < 1
        ):
            raise ValueError("invalid dependency source evidence")

    execution = witness["execution"]
    methods, sites = execution["methods"], execution["sites"]
    if (
        execution["transactionTraversal"] != "NOT_ASSERTED"
        or not 1 <= len(methods) <= 32
        or len(sites) > 20000
        or witness["request"]["entry"] != report["frames"][0]["evidence"]
        or methods[0]["declaration"] != witness["request"]["entry"]
    ):
        raise ValueError("dependency entry or closure bound differs from T01")
    by_id = {m["identity"]: m for m in methods}
    if len(by_id) != len(methods):
        raise ValueError("duplicate dependency method identity")
    for method in methods:
        evidence(method["declaration"])
        if method["traversal"] != "NOT_ASSERTED":
            raise ValueError("dependency recovery asserts method execution")

    records = []
    seen = set()
    for ordinal, site in enumerate(sites):
        caller = by_id.get(site["caller"])
        if caller is None or site["traversal"] != "NOT_ASSERTED":
            raise ValueError("dependency caller or traversal invalid")
        ev = site["site"]
        if ev is not None:
            evidence(ev)
            parent = caller["declaration"]
            if (
                ev["file"] != parent["file"]
                or not parent["start"] <= ev["start"] < ev["end"] <= parent["end"]
            ):
                raise ValueError("dependency site outside caller declaration")
        if site["declaration"] is not None:
            evidence(site["declaration"])
        verified = site["binding"] == "VERIFIED"
        if site["binding"] not in {"VERIFIED", "UNRESOLVED"} or (
            verified and (not site["target"] or ev is None)
        ):
            raise ValueError("dependency binding lacks source site/target")
        if site["dispatch"] not in {
            "STATIC",
            "DIRECT",
            "VIRTUAL",
            "CONSTRUCTOR",
            "UNKNOWN",
        }:
            raise ValueError("invalid dependency dispatch")
        if site["dispatchCertainty"] not in {"DECLARATION_EXACT", "UNKNOWN"}:
            raise ValueError("invalid dependency dispatch certainty")
        # A source site is stable across projection; generated/implicit sites have
        # only an occurrence ID, never a fabricated source location.
        key = (
            [site["caller"], ev] if ev is not None else [site["caller"], None, ordinal]
        )
        identity = hashlib.sha256(_encoded(key)).hexdigest()
        if identity in seen:
            raise ValueError("duplicate dependency call site")
        seen.add(identity)
        target = by_id.get(site["target"])
        if target and (
            target["declaration"] != site["declaration"]
            or target["bodyAvailable"] != site["bodyAvailable"]
        ):
            raise ValueError("dependency target declaration/body conflict")
        records.append(
            {
                "id": identity,
                "idKind": "SOURCE_SITE" if ev is not None else "IMPLICIT_OCCURRENCE",
                "callerMethod": site["caller"],
                "callSite": copy.deepcopy(ev),
                "targetMethod": site["target"],
                "targetDeclaration": copy.deepcopy(site["declaration"]),
                "declarationAvailability": "SOURCE"
                if site["declaration"]
                else "UNAVAILABLE",
                "binding": site["binding"],
                "dispatch": site["dispatch"],
                "dispatchCertainty": site["dispatchCertainty"],
                "bodyAvailable": site["bodyAvailable"],
                "relation": "STATIC_BINDING" if verified else "UNRESOLVED",
                "dependencyCompleteness": "INCOMPLETE",
                "reachability": "NOT_ASSERTED",
                "runtimeExecution": "NOT_OBSERVED",
                "transactionInterception": "NOT_ASSERTED",
                "admission": "NOT_ASSERTED",
                "limits": sorted(set(site["limits"]) | set(LIMITS)),
            }
        )
    return {
        "schema": SCHEMA,
        "scope": "SELECTED_STATIC_DEPENDENCIES_ONLY",
        "t01Entry": report["entry"],
        "entryDeclaration": methods[0]["identity"],
        "completeness": "INCOMPLETE",
        "records": records,
        "limits": list(LIMITS),
        "witness": copy.deepcopy(witness),
    }


def validate_extension(report):
    """Structural consistency only; authenticity requires the pinned replay API."""
    if FIELD not in report:
        return
    extension = report[FIELD]
    if extension != _projection(extension["witness"], report):
        raise ValueError("dependency projection contradicts recovery witness")


def build_with_dependencies(
    facts,
    context,
    entry,
    witness,
    factory,
    project,
    files,
    environment,
    *,
    parse_facts,
    request,
):
    """Replay pinned inputs before attaching static facts to an ordinary T01 model.

    No boolean from a producer/caller can bypass the replay. Neither inputs nor
    legacy execution arrays are changed. Incomplete bindings remain in the model.
    """
    from .model import build, validate_model

    verify_execution_snapshot(
        witness,
        factory,
        project,
        files,
        environment,
        parse_facts=parse_facts,
        request=request,
    )
    report = build(facts, context, entry)
    # Like the resource-leaf opt-in, pure builder callers need source hashes;
    # the ordinary CLI adds them outside build(). Never use witness hashes as
    # their own corroboration.
    if "evidence" not in report:
        report["evidence"] = [
            {"path": path, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
            for path, text in sorted(facts["sources"].items())
        ]
    report[FIELD] = _projection(witness, report)
    if len(_encoded(report)) > 4 * 1024 * 1024:
        raise ValueError("extended transaction model exceeds payload bound")
    validate_model(report)
    return report


def verify_model_dependencies(
    report, factory, project, files, environment, *, parse_facts, request
):
    """Revalidate a transported model with independently pinned request/inputs."""
    from .model import validate_model

    if FIELD not in report:
        raise ValueError("model has no dependency extension")
    validate_model(report)
    return verify_execution_snapshot(
        report[FIELD]["witness"],
        factory,
        project,
        files,
        environment,
        parse_facts=parse_facts,
        request=request,
    )
