"""Bounded declaration selectors; runtime arguments are never resolved or bound."""

import json
import re


def method_key(cls, method):
    if method["arity"] == 0:
        return cls["name"] + "#" + method["name"] + "()"
    parameters = method.get("parameters", [])
    if len(parameters) != method["arity"] or any(
        p["type"] is None and p.get("typeResolution") != "DECLARED_ONLY"
        for p in parameters
    ):
        return None
    return (
        cls["name"]
        + "#"
        + method["name"]
        + "("
        + ",".join(p["type"] or p["declaredType"] for p in parameters)
        + ")"
    )


def select_methods(classes, entry):
    methods, erased = {}, {}
    declarations = []
    for cls in classes.values():
        for method in cls["methods"]:
            key = method_key(cls, method)
            declarations.append((cls, method, key))
            if key is not None:
                depth, erased_key = 0, ""
                for char in key:
                    if char == "<":
                        depth += 1
                    elif char == ">":
                        depth -= 1
                    elif depth == 0:
                        erased_key += char
                if erased_key in erased:
                    raise ValueError(
                        "duplicate/ambiguous method signature; alternatives: "
                        + json.dumps(
                            [
                                erased[erased_key],
                                {"signature": key, "evidence": method["evidence"]},
                            ]
                        )
                    )
                erased[erased_key] = {"signature": key, "evidence": method["evidence"]}
                methods[key] = (cls, method)
    # A bare Class#method selects by name only when exactly one declaration exists.
    # Parentheses always denote an exact signature, including the legacy () form.
    if not re.fullmatch(r"[\w.$]+#[\w$]+(?:\([\w.$<>?,\[\]\s]*\))?", entry):
        raise ValueError(
            "invalid entry selector; use Class#method or Class#method(types)"
        )
    entry = re.sub(r"\s+", "", entry)
    name = entry.split("(", 1)[0]
    candidates = [
        (c, m, k) for c, m, k in declarations if c["name"] + "#" + m["name"] == name
    ]
    unresolved_overload = len(candidates) > 1 and any(
        key is None
        or any(
            p.get("typeResolution") == "DECLARED_ONLY"
            for p in method.get("parameters", [])
        )
        for _, method, key in candidates
    )
    if "(" not in entry and len(candidates) == 1 and candidates[0][2] is not None:
        entry = candidates[0][2]
    if entry not in methods or unresolved_overload:
        alternatives = [
            {
                "signature": k,
                "arity": m["arity"],
                "parameters": m.get("parameters", []),
                "evidence": m["evidence"],
            }
            for _, m, k in candidates
        ]
        # Only symbols and source references, never AST expressions/source bytes.
        raise ValueError(
            "entry is absent, ambiguous or signature unsupported; alternatives: "
            + json.dumps(alternatives)
        )
    return methods, entry


def shadows_receiver(method, receiver):
    return any(p["name"] == receiver for p in method.get("parameters", []))
