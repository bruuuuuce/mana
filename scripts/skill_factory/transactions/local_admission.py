"""Proof of one conditional Java entry, separate from T01's causal trace.

No frame/body, return, successor or transaction certainty is granted. This is an
opt-in positive local authority, never an execution/negative-completeness flag.
"""

import copy
import hashlib

from .semantic import _canonical, member_bindings

FIELD = "localAdmissionExtension"
SCHEMA = "mana.local-executable-admission/v1"
WITNESS = "mana.java-local-entry-evaluation/v1"
PREMISES = [
    "CALLER_INSTANCE_BODY_ENTERED",
    "ORDINARY_SYNCHRONOUS_JAVA_EVALUATION",
    "NO_ADDITIONAL_RUNTIME_INSTRUMENTATION_ASSERTED",
]
LIMITS = [
    "CALLEE_BODY_NOT_ADMITTED",
    "NORMAL_RETURN_NOT_PROVEN",
    "SUCCESSORS_NOT_ADMITTED",
    "TRANSACTION_INTERCEPTION_NOT_PROVEN_BY_JAVA_ENTRY",
    "GLOBAL_COMPLETENESS_NOT_ASSERTED",
    "NO_NEGATIVE_DEPENDENCY_AUTHORITY",
]


def evaluation_witness(*args, **kwargs):
    return member_bindings(*args, **kwargs, local_entry=True)


def _projection(report, witness, requested_site):
    if (
        witness.get("schema") != WITNESS
        or witness.get("status") not in {"COMPLETE", "INCOMPLETE"}
        or witness.get("diagnostics")
        or witness.get("transactionTraversal") != "NOT_ASSERTED"
        or witness["request"]["entry"] != report["frames"][0]["evidence"]
    ):
        raise ValueError("local admission requires an attributed caller witness")
    if len(_canonical(witness)) > 4 * 1024 * 1024:
        raise ValueError("local witness exceeds payload budget")
    hashes = {e["path"]: e["sha256"] for e in report["evidence"]}
    if any(hashes.get(p) != h for p, h in witness["sources"].items()):
        raise ValueError("local witness differs from canonical source inventory")

    def evidence(ev, container=None):
        if (
            not isinstance(ev, dict)
            or set(ev) != {"file", "sha256", "start", "end", "line"}
            or hashes.get(ev["file"]) != ev["sha256"]
            or any(type(ev[k]) is not int for k in ("start", "end", "line"))
            or not 0 <= ev["start"] < ev["end"]
            or ev["line"] < 1
        ):
            raise ValueError("invalid local source evidence")
        if container and (
            ev["file"] != container["file"]
            or not container["start"] <= ev["start"] < ev["end"] <= container["end"]
        ):
            raise ValueError("local evidence outside enclosing region")

    evidence(requested_site, report["frames"][0]["evidence"])
    proof = witness.get("localEntry", {})
    qualified = proof.get("status") == "QUALIFIED"
    record = None
    if qualified:
        required = {
            "rule",
            "status",
            "caller",
            "callerDeclaration",
            "target",
            "targetDeclaration",
            "callSite",
            "statement",
            "prefix",
            "receiver",
            "dispatch",
            "dispatchCertainty",
            "arguments",
            "evaluationOrder",
            "lifecycle",
        }
        if (
            set(proof) != required
            or proof["rule"] != "PRIVATE_SELF_PREFIX_V1"
            or proof["receiver"] != "THIS"
            or proof["dispatch"] != "DIRECT"
            or proof["dispatchCertainty"] != "DECLARATION_EXACT"
            or proof["evaluationOrder"]
            != "PREFIX_RECEIVER_ARGUMENTS_LEFT_TO_RIGHT_ENTRY"
            or proof["lifecycle"] != "NO_NEW_ACTIVE_USE_BEFORE_PRIVATE_INSTANCE_ENTRY"
            or proof["callerDeclaration"] != witness["request"]["entry"]
            or proof["caller"].split("#")[0] != proof["target"].split("#")[0]
            or len(proof["prefix"]) > 32
        ):
            raise ValueError("local evaluation premises are not closed")
        caller = proof["callerDeclaration"]
        evidence(proof["targetDeclaration"])
        evidence(proof["statement"], caller)
        evidence(proof["callSite"], proof["statement"])
        previous = caller["start"]
        for step in proof["prefix"]:
            if set(step) != {"kind", "evidence"} or step["kind"] != "INT_LITERAL_LOCAL":
                raise ValueError("unsupported prefix dependency")
            evidence(step["evidence"], caller)
            if step["evidence"]["start"] < previous:
                raise ValueError("prefix order not established")
            previous = step["evidence"]["end"]
        if previous > proof["statement"]["start"]:
            raise ValueError("prefix does not precede call")
        previous = proof["callSite"]["start"]
        for arg in proof["arguments"]:
            kind = arg.get("kind")
            expected = {"kind", "type", "evidence"} | (
                {"parameter"} if kind == "FORMAL_PARAMETER_READ" else {"value"}
            )
            if set(arg) != expected or not isinstance(arg["type"], str):
                raise ValueError("invalid argument proof")
            if kind == "FORMAL_PARAMETER_READ":
                if type(arg["parameter"]) is not int or arg["parameter"] < 0:
                    raise ValueError("invalid formal parameter index")
            elif (
                kind != "BOOLEAN_LITERAL"
                or type(arg["value"]) is not bool
                or arg["type"] != "boolean"
            ):
                raise ValueError("argument may perform unqualified evaluation")
            evidence(arg["evidence"], proof["callSite"])
            if arg["evidence"]["start"] < previous:
                raise ValueError("argument order not established")
            previous = arg["evidence"]["end"]
        # If the static catalog covers this site, its canonical binding must agree.
        catalog = report.get("executableDependencyExtension", {})
        for r in catalog.get("records", []):
            if r["callSite"] == proof["callSite"] and (
                r["callerMethod"] != proof["caller"]
                or r["targetMethod"] != proof["target"]
                or r["targetDeclaration"] != proof["targetDeclaration"]
                or r["binding"] != "VERIFIED"
                or r["dispatch"] != "DIRECT"
                or r["dispatchCertainty"] != "DECLARATION_EXACT"
            ):
                raise ValueError("local admission contradicts canonical dependency")
        if proof["callSite"] == requested_site:
            identity = hashlib.sha256(
                _canonical([proof["caller"], requested_site])
            ).hexdigest()
            record = {
                "id": identity,
                "callerMethod": proof["caller"],
                "callSite": copy.deepcopy(requested_site),
                "targetMethod": proof["target"],
                "targetDeclaration": copy.deepcopy(proof["targetDeclaration"]),
                "admission": "ENTRY_JUSTIFIED_UNDER_PREMISES",
                "premises": list(PREMISES),
                "evaluationProof": copy.deepcopy(proof),
                "completion": "UNKNOWN",
                "returnValue": "UNKNOWN",
                "runtimeExecution": "NOT_OBSERVED",
                "transactionContext": {
                    "kind": "UNKNOWN",
                    "physicalId": None,
                    "manager": None,
                },
                "transactionInterception": "NOT_ASSERTED",
                "frontier": {
                    "at": "CALLEE_BODY_ENTRY",
                    "evidence": copy.deepcopy(proof["targetDeclaration"]),
                    "bodyTraversal": "NOT_ASSERTED",
                    "continuation": "UNKNOWN",
                },
            }
    elif (
        set(proof) != {"rule", "status", "reason"}
        or proof.get("rule") != "PRIVATE_SELF_PREFIX_V1"
        or proof.get("status") != "BLOCKED"
    ):
        raise ValueError("missing conservative evaluation result")
    return {
        "schema": SCHEMA,
        "scope": "CONDITIONAL_LOCAL_JAVA_ENTRY_ONLY",
        "requestedSite": copy.deepcopy(requested_site),
        "entries": [record] if record else [],
        "reason": "ENTRY_PREMISES_CLOSED"
        if record
        else "REQUESTED_ENTRY_NOT_QUALIFIED",
        "completeness": "INCOMPLETE",
        "negativeAuthority": "NOT_ASSERTED",
        "causalTraceAuthority": "NONE",
        "limits": list(LIMITS),
        "witness": copy.deepcopy(witness),
    }


def validate_extension(report):
    if FIELD in report:
        extension = report[FIELD]
        if extension != _projection(
            report, extension["witness"], extension["requestedSite"]
        ):
            raise ValueError("local admission contradicts evaluation proof")


def verify_local_admission(
    report,
    factory,
    project,
    files,
    environment,
    *,
    parse_facts,
    request,
    requested_site,
):
    """Reattribute transported proof against separately pinned source and request."""
    from .model import validate_model

    validate_model(report)
    extension = report[FIELD]
    witness = extension["witness"]
    if witness["request"] != request or extension["requestedSite"] != requested_site:
        raise ValueError("local admission differs from pinned request/site")
    actual, _ = evaluation_witness(
        factory,
        project,
        files,
        request["entry"],
        request["dependencies"],
        environment,
        parse_facts=parse_facts,
        limits=witness["limits"],
    )
    if actual != witness:
        raise ValueError("local evaluation contradicts pinned source replay")
    return len(extension["entries"])


def attach_local_admission(
    report,
    witness,
    factory,
    project,
    files,
    environment,
    *,
    parse_facts,
    request,
    requested_site,
):
    """Copy a validated T01, verify proof, attach one entry or a blocked frontier."""
    from .model import validate_model

    validate_model(report)
    result = copy.deepcopy(report)
    result[FIELD] = _projection(result, witness, requested_site)
    if len(_canonical(result)) > 4 * 1024 * 1024:
        raise ValueError("local admission model exceeds payload budget")
    verify_local_admission(
        result,
        factory,
        project,
        files,
        environment,
        parse_facts=parse_facts,
        request=request,
        requested_site=requested_site,
    )
    return result
