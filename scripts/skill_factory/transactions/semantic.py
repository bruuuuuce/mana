"""Opt-in bounded javac witness. Never changes source facts or transaction models.

Caller supplies a small source inventory, an exact declaration evidence pointer,
selected member identities, and an offline JDK/classpath. No discovery/build occurs.
"""

import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import time
import zipfile

from .source import verify_leaf_snapshot

SCHEMA = "mana.java-member-bindings/v1"
LIMITS = {
    "seconds": 60,
    "heapMiB": 128,
    "nodes": 20000,
    "depth": 64,
    "sources": 64,
    "sourceBytes": 2 * 1024 * 1024,
    "classpathEntries": 32,
    "classpathBytes": 32 * 1024 * 1024,
    "outputBytes": 4 * 1024 * 1024,
}


class _Blocked(Exception):
    pass


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _environment(config, budgets):
    if set(config) != {"jdkHome", "release", "classpath"}:
        raise _Blocked("EXPLICIT_ENVIRONMENT_REQUIRED")
    home = Path(config["jdkHome"]).resolve(strict=True)
    release = config["release"]
    if release not in ("8", "17", "21"):
        raise _Blocked("UNSUPPORTED_RELEASE")
    suffix = ".exe" if os.name == "nt" else ""
    java, javac = [home / "bin" / (name + suffix) for name in ("java", "javac")]
    # Hash the runtime/compiler platform, not only launchers. No PATH substitution.
    platform = [
        p
        for p in (
            home / "release",
            home / "version.txt",
            home / "commitId.txt",
            home / "LICENSE",
            home / "ASSEMBLY_EXCEPTION",
            home / "lib/modules",
            home / "lib/tools.jar",
            home / "jre/lib/rt.jar",
        )
        if p.is_file()
    ]
    if not java.is_file() or not javac.is_file() or len(platform) < 2:
        raise _Blocked("JDK_ENVIRONMENT_INCOMPLETE")
    # Include native libraries and the remaining platform JARs (bounded metadata
    # walk of the explicitly selected toolchain, never of the target repository).
    paths = sorted(
        set([java, javac, *platform])
        | {
            p
            for folder in (home / "lib", home / "jre/lib")
            if folder.is_dir()
            for p in folder.rglob("*")
            if p.is_file() and p.suffix in (".jar", ".so", ".dylib", ".dll")
        }
    )
    if len(paths) > 2048 or sum(p.stat().st_size for p in paths) > 512 * 1024 * 1024:
        raise _Blocked("JDK_FINGERPRINT_BUDGET")
    toolchain = {str(p.relative_to(home)): _file_digest(p) for p in paths}
    jars = config["classpath"]
    if not isinstance(jars, list) or len(jars) > budgets["classpathEntries"]:
        raise _Blocked("CLASSPATH_BUDGET")
    copied, manifests, total = [], [], 0
    for name in jars:
        path = Path(name).resolve(strict=True)
        if path.suffix.lower() != ".jar" or not path.is_file():
            raise _Blocked("OFFLINE_JARS_REQUIRED")
        total += path.stat().st_size
        if total > budgets["classpathBytes"]:
            raise _Blocked("CLASSPATH_BUDGET")
        raw = path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as jar:
            entries = jar.infolist()
            if (
                len(entries) > 10000
                or sum(e.file_size for e in entries) > 128 * 1024 * 1024
            ):
                raise _Blocked("JAR_EXPANSION_BUDGET")
            # javac can follow manifest Class-Path entries. Refuse that implicit
            # dependency discovery; the caller must supply a closed offline list.
            for item in entries:
                if item.filename.upper() == "META-INF/MANIFEST.MF":
                    if item.file_size > 65536:
                        raise _Blocked("JAR_MANIFEST_BUDGET")
                    manifest = jar.read(item).decode("utf-8", errors="replace")
                    if re.search(r"(?im)^class-path\s*:", manifest):
                        raise _Blocked("IMPLICIT_MANIFEST_CLASSPATH")
        copied.append(raw)
        manifests.append({"sha256": _digest(raw), "bytes": len(raw)})
    return (
        home,
        java,
        javac,
        copied,
        {
            "release": release,
            "toolchain": toolchain,
            "classpath": manifests,
            "classpathBytes": total,
        },
    )


def member_bindings(
    factory,
    project,
    files,
    entry_evidence,
    dependencies,
    environment,
    *,
    parse_facts,
    limits=None,
    execution=False,
    local_entry=False,
):
    """Return a source-free sidecar and separate noncanonical cost measurements.

    All compiler errors invalidate all positive bindings in this first increment.
    This intentionally prefers incompleteness to javac recovery as positive proof.
    The parser witness is independently reparsed; contradictions produce CONFLICT.
    """
    if execution and local_entry:
        raise ValueError("recovery and local entry are separate witnesses")
    start = time.monotonic()
    budgets = dict(LIMITS)
    if limits:
        if any(
            k not in budgets or type(v) is not int or not 0 < v <= budgets[k]
            for k, v in limits.items()
        ):
            raise ValueError("limits may only lower positive integer defaults")
        budgets.update(limits)
    dependency_input_valid = (
        isinstance(dependencies, list)
        and len(dependencies) <= 16
        and all(
            isinstance(p, str)
            and len(p) <= 1024
            and re.fullmatch(r"[\w$]+(?:\.[\w$]+)+", p)
            for p in dependencies
        )
    )
    safe_dependencies = sorted(set(dependencies)) if dependency_input_valid else []
    witness = {
        "schema": (
            "mana.java-local-entry-evaluation/v1"
            if local_entry
            else "mana.java-execution-dependencies/v1"
            if execution
            else SCHEMA
        ),
        "status": "BLOCKED",
        "reason": "INPUT_INCOMPLETE",
        "request": {
            "entry": copy.deepcopy(entry_evidence),
            "dependencies": safe_dependencies,
        },
        "sources": {},
        "environment": None,
        "limits": budgets,
        "producer": {
            p: _file_digest(Path(__file__).with_name(p))
            for p in ("semantic.py", "JavaBindings.java", "JavaFacts.java", "source.py")
        },
        "types": [],
        "relations": [],
        "diagnostics": [],
        "transactionTraversal": "NOT_ASSERTED",
    }
    if execution:
        witness["producer"]["JavaExecution.java"] = _file_digest(
            Path(__file__).with_name("JavaExecution.java")
        )
    if local_entry:
        witness["producer"]["JavaLocalEntry.java"] = _file_digest(
            Path(__file__).with_name("JavaLocalEntry.java")
        )
    metrics = {"heapMiB": budgets["heapMiB"], "subprocesses": 0}
    try:
        if not dependency_input_valid:
            raise _Blocked("DEPENDENCY_REQUEST_BUDGET_OR_IDENTITY")
        if (
            not isinstance(files, dict)
            or not isinstance(parse_facts, dict)
            or any(
                not isinstance(p, str) or not isinstance(raw, bytes)
                for p, raw in files.items()
            )
        ):
            raise _Blocked("INPUT_INCOMPLETE")
        sources = {p: raw for p, raw in files.items() if p.endswith(".java")}
        if (
            not sources
            or len(sources) > budgets["sources"]
            or sum(map(len, sources.values())) > budgets["sourceBytes"]
        ):
            raise _Blocked("SOURCE_BUDGET")
        for name in sources:
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or str(path) != name
            ):
                raise _Blocked("UNSAFE_SOURCE_PATH")
        witness["sources"] = {p: _digest(raw) for p, raw in sorted(sources.items())}
        metrics.update(
            sourceBytes=sum(map(len, sources.values())), sourceFiles=len(sources)
        )
        # This check validates all parser facts, not a producer-authored boolean.
        try:
            verify_leaf_snapshot(parse_facts, witness["sources"])
        except ValueError as exc:
            if str(exc) not in {
                "resource leaf lacks hash-linked source bytes",
                "resource leaf invalid derived binding evidence",
                "resource leaf source facts contradict reparsed source bytes",
            }:
                raise _Blocked("PARSE_VERIFICATION_UNAVAILABLE") from None
            witness.update(status="CONFLICT", reason="PARSE_FACTS_DISAGREE_WITH_SOURCE")
            raise _Blocked(witness["reason"])
        methods = [
            m
            for c in parse_facts["classes"]
            for m in c["methods"]
            if m["evidence"] == entry_evidence
        ]
        if len(methods) != 1 or entry_evidence["file"] not in sources:
            raise _Blocked("ENTRY_EVIDENCE_ABSENT_OR_AMBIGUOUS")
        if {
            p: text.encode("utf-8") for p, text in parse_facts["sources"].items()
        } != sources:
            witness.update(status="CONFLICT")
            raise _Blocked("SOURCE_INVENTORIES_DISAGREE")
        home, java, javac, jars, env_manifest = _environment(environment, budgets)
        witness["environment"] = env_manifest
        parent = factory.temporary_parent(project)
        with tempfile.TemporaryDirectory(
            prefix="mana-java-bindings-", dir=parent
        ) as temporary:
            stage = Path(temporary)
            src, classes, empty = [stage / n for n in ("sources", "classes", "empty")]
            for p in (src, classes, empty):
                p.mkdir()
            env = {
                "PATH": str(home / "bin") + os.pathsep + os.defpath,
                "LANG": "C",
                "LC_ALL": "C",
                "TZ": "UTC",
            }
            if os.name == "nt":
                env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
            env.update({k: str(stage) for k in ("TMPDIR", "TEMP", "TMP")})
            jvm = [
                "-XX:-UsePerfData",
                "-Djava.io.tmpdir=" + str(stage),
                "-Xmx" + str(budgets["heapMiB"]) + "m",
                "-Xss1m",
            ]
            deadline = time.monotonic() + budgets["seconds"]

            def run(argv):
                metrics["subprocesses"] += 1
                # Files avoid unbounded capture_output allocation. Read only after
                # stat checks. Compiler messages never leave the external stage.
                with (
                    (stage / "stdout").open("wb") as out,
                    (stage / "stderr").open("wb") as err,
                ):
                    result = subprocess.run(
                        argv,
                        cwd=stage,
                        env=env,
                        stdout=out,
                        stderr=err,
                        timeout=max(0.001, deadline - time.monotonic()),
                    )
                if result.returncode:
                    raise _Blocked("JDK_PROCESS_FAILED")
                if any(
                    (stage / n).stat().st_size > budgets["outputBytes"]
                    for n in ("stdout", "stderr")
                ):
                    raise _Blocked("OUTPUT_BUDGET")
                return (stage / "stdout").read_bytes()

            tool_cp = str(classes)
            if (home / "lib/tools.jar").is_file():
                tool_cp += os.pathsep + str(home / "lib/tools.jar")
            helpers = [
                Path(__file__).with_name(n)
                for n in (
                    "JavaFacts.java",
                    "JavaBindings.java",
                    "JavaExecution.java",
                    "JavaLocalEntry.java",
                )
            ]
            run(
                [
                    str(javac),
                    *["-J" + p for p in jvm],
                    "-proc:none",
                    "-encoding",
                    "UTF-8",
                    "-cp",
                    tool_cp,
                    "-d",
                    str(classes),
                    *map(str, helpers),
                ]
            )
            paths = []
            for name, raw in sorted(sources.items()):
                path = src / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                paths.append(str(path))
            cp = []
            for i, raw in enumerate(jars):
                path = stage / ("dependency" + str(i) + ".jar")
                path.write_bytes(raw)
                cp.append(str(path))
            # Deliberately empty when no classpath was explicitly supplied.
            target_cp = os.pathsep.join(cp) if cp else str(empty)
            output = run(
                [
                    str(java),
                    *jvm,
                    "-cp",
                    tool_cp,
                    "JavaBindings",
                    str(src),
                    entry_evidence["file"],
                    str(entry_evidence["start"]),
                    str(budgets["nodes"]),
                    str(budgets["depth"]),
                    ",".join(witness["request"]["dependencies"]),
                    environment["release"],
                    target_cp,
                    *(
                        ["--execution"]
                        if execution
                        else ["--local-entry"]
                        if local_entry
                        else []
                    ),
                    *paths,
                ]
            )
            facts = json.loads(output)

            # Attach only source hashes to structured position dictionaries.
            def attach(value):
                if isinstance(value, dict):
                    if set(value) == {"file", "start", "end", "line"}:
                        value["sha256"] = witness["sources"][value["file"]]
                    for v in value.values():
                        attach(v)
                elif isinstance(value, list):
                    for v in value:
                        attach(v)

            attach(facts)
            witness.update(facts)
            if (
                execution
                and facts["status"] not in {"BLOCKED", "CONFLICT"}
                and facts.get("execution", {}).get("status") != "COMPLETE"
            ):
                witness.update(
                    status="INCOMPLETE", reason="EXECUTION_CLOSURE_INCOMPLETE"
                )
            if facts["status"] == "COMPLETE" and any(
                t["status"] != "VERIFIED" for t in facts["types"]
            ):
                witness.update(
                    status="INCOMPLETE", reason="MEMBER_DECLARATION_UNRESOLVED"
                )
            if any(r["status"] != "VERIFIED" for r in facts["relations"]):
                witness.update(status="INCOMPLETE", reason="RELATION_UNRESOLVED")
            # Attribution must not create target bytecode anywhere in the stage.
            if any(p for p in stage.rglob("*.class") if classes not in p.parents):
                raise _Blocked("UNEXPECTED_TARGET_OUTPUT")
            metrics["nodes"] = facts.get("nodes", 0)
            metrics["outputBytes"] = len(output)
            metrics["classpathBytes"] = env_manifest["classpathBytes"]
        # Reject drift of input environment during use. No silent witness refresh.
        if _environment(environment, budgets)[4] != witness["environment"]:
            raise _Blocked("ENVIRONMENT_CHANGED")
    except subprocess.TimeoutExpired:
        witness.update(status="BLOCKED", reason="TIME_BUDGET", types=[], relations=[])
    except _Blocked as exc:
        witness.update(reason=str(exc), types=[], relations=[])
        if witness["status"] != "CONFLICT":
            witness["status"] = "BLOCKED"
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
        witness.update(
            status="BLOCKED",
            reason="INPUT_OR_TOOLING_UNAVAILABLE",
            types=[],
            relations=[],
        )
    metrics["seconds"] = round(time.monotonic() - start, 6)
    if witness["status"] in {"BLOCKED", "CONFLICT"}:
        witness.pop("execution", None)
        witness.pop("localEntry", None)
    return witness, metrics


def verify_member_snapshot(
    witness, factory, project, files, environment, *, parse_facts, request
):
    """Recompute using caller-supplied pinned inputs; never trusts witness booleans.

    Input/toolchain freshness and integrity are verified, not external authenticity
    of the host. Cost measurements are separate from deterministic witness bytes.
    """
    if witness.get("schema") != SCHEMA:
        raise ValueError("unsupported member binding witness")
    if witness.get("request") != request:
        raise ValueError("member binding request differs from pinned request")
    actual, _ = member_bindings(
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
        raise ValueError("member binding witness contradicts pinned replay")
    return actual["status"]
