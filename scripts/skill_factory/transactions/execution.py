"""Partial executable recovery through HYBRID's attributed task.

No execution ordering or traversal is inferred. The canonical T01 builder retains
its guards: even an exact declaration with a source body is insufficient to prove
expression execution, construction lifecycle, or normal continuation.
"""

from .semantic import _canonical, member_bindings

SCHEMA = "mana.java-execution-dependencies/v1"


def execution_dependencies(*args, **kwargs):
    """Use exactly the explicit source/classpath request; never discover inputs."""
    return member_bindings(*args, **kwargs, execution=True)


def verify_execution_snapshot(
    witness, factory, project, files, environment, *, parse_facts, request
):
    """Replay every body/site fact against separately pinned input and environment."""
    if witness.get("schema") != SCHEMA or witness.get("request") != request:
        raise ValueError("execution witness differs from pinned request")
    actual, _ = execution_dependencies(
        factory,
        project,
        files,
        request["entry"],
        request["dependencies"],
        environment,
        parse_facts=parse_facts,
        limits=witness["limits"],
    )
    if _canonical(actual) != _canonical(witness):
        raise ValueError("execution witness contradicts pinned replay")
    return actual["status"]
