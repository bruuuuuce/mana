"""Framework-only JDK parse adapter; target bytes never reach a build or processor."""

import copy
import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def java_facts(factory, project, files, *, source_snapshot=False):
    """Return safe diagnostics unless an internal analysis snapshot is explicit."""
    sources = {p: b for p, b in files.items() if p.endswith(".java")}
    if (
        not sources
        or len(sources) > 64
        or sum(map(len, sources.values())) > 2 * 1024 * 1024
    ):
        raise factory.FactoryError(
            "Java parse budget: 1..64 sources, at most 2 MiB combined"
        )
    parent = factory.temporary_parent(project)
    with tempfile.TemporaryDirectory(
        prefix="mana-transaction-", dir=parent
    ) as temporary:
        stage = Path(temporary)
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "BASH_ENV",
                "ENV",
                "JAVA_TOOL_OPTIONS",
                "_JAVA_OPTIONS",
                "JDK_JAVA_OPTIONS",
                "JDK_JAVAC_OPTIONS",
                "CLASSPATH",
            }
        }
        env.update({k: str(stage) for k in ("TMPDIR", "TEMP", "TMP")})
        java, javac = shutil.which("java"), shutil.which("javac")
        if not java or not javac:
            raise factory.FactoryError(
                "JDK java and javac are required; no target build is used"
            )

        def run(argv):
            try:
                result = subprocess.run(
                    argv, cwd=stage, env=env, capture_output=True, timeout=60
                )
            except subprocess.TimeoutExpired as exc:
                raise factory.FactoryError("JDK parser timeout") from exc
            if result.returncode:
                raise factory.FactoryError(
                    "JDK parser failed (exit "
                    + str(result.returncode)
                    + "); diagnostics withheld"
                )
            return result.stdout, result.stderr

        classes = stage / "classes"
        classes.mkdir()
        helper = Path(__file__).with_name("JavaFacts.java")
        jvm = ["-XX:-UsePerfData", "-Djava.io.tmpdir=" + str(stage)]
        _, settings = run([java, *jvm, "-XshowSettings:properties", "-version"])
        match = re.search(rb"java.home\s*=\s*(.+)", settings)
        classpath = str(classes)
        if match:
            home = Path(match.group(1).decode().strip())
            tools = home.parent / "lib/tools.jar"
            if tools.is_file():
                classpath += os.pathsep + str(tools)
        run(
            [
                javac,
                "-J-XX:-UsePerfData",
                "-J-Djava.io.tmpdir=" + str(stage),
                "-proc:none",
                "-cp",
                classpath,
                "-d",
                str(classes),
                str(helper),
            ]
        )
        names = {}
        for index, (relative, raw) in enumerate(sorted(sources.items())):
            path = stage / f"source{index}.java"
            path.write_bytes(raw)
            names[path.name] = relative
        output, _ = run(
            [
                java,
                *jvm,
                "-Xmx128m",
                "-cp",
                classpath,
                "JavaFacts",
                *[str(stage / name) for name in names],
            ]
        )
        if len(output) > 4 * 1024 * 1024:
            raise factory.FactoryError("Java fact output budget exceeded")
        facts = json.loads(output)
        if facts["errors"]:
            raise factory.FactoryError(
                "Java syntax unsupported/invalid: " + "; ".join(facts["errors"])[:2000]
            )

        def attach(value):
            if isinstance(value, dict):
                if set(value) == {"file", "start", "end", "line"}:
                    value["file"] = names[value["file"]]
                    value["sha256"] = factory.digest(files[value["file"]])
                for item in value.values():
                    attach(item)
            elif isinstance(value, list):
                for item in value:
                    attach(item)

        attach(facts)
        facts["sources"] = {p: raw.decode("utf-8") for p, raw in sources.items()}
        return facts if source_snapshot else diagnostic_facts(facts)


def diagnostic_facts(facts):
    """Allowlisted inspection output. Internal snapshots are never diagnostics.

    Full sourceFacts/sources remain required by the existing local S01/leaf
    contracts. Do not print them: publish only to an explicitly selected local
    analysis output, or use this projection for diagnostics/reports.
    """
    from .entry import method_key

    return {
        "classes": [
            {
                "symbol": cls["name"],
                "evidence": copy.deepcopy(cls["evidence"]),
                "methods": [
                    {
                        "symbol": method["name"],
                        "signature": method_key(cls, method),
                        "arity": method["arity"],
                        "parameters": copy.deepcopy(method.get("parameters", [])),
                        "evidence": copy.deepcopy(method["evidence"]),
                        "calls": [
                            {
                                "symbol": call["name"],
                                "arity": call["arity"],
                                "evidence": copy.deepcopy(call["evidence"]),
                            }
                            for call in method["calls"]
                        ],
                        "hazards": list(method["hazards"]),
                    }
                    for method in cls["methods"]
                ],
            }
            for cls in facts["classes"]
        ]
    }


class _SnapshotHost:
    """Only the parse adapter's host operations; never accesses the original target."""

    FactoryError = ValueError

    @staticmethod
    def digest(raw):
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def temporary_parent(project):
        return Path("/tmp").resolve()


@lru_cache(maxsize=8)
def _reparse_snapshot(sources):
    return java_facts(
        _SnapshotHost,
        None,
        {p: raw.encode("utf-8") for p, raw in sources},
        source_snapshot=True,
    )


def verify_leaf_snapshot(facts, hashes):
    """Reparse supplied source bytes, not producer-authored proof booleans.

    Cached by source content, never by a claimed hash or mutable facts. This is
    parse-only, with the same source budgets and no target build/classpath.
    """
    sources = facts.get("sources")
    if (
        not isinstance(sources, dict)
        or not sources
        or any(
            not isinstance(p, str)
            or not isinstance(raw, str)
            or hashes.get(p) != hashlib.sha256(raw.encode("utf-8")).hexdigest()
            for p, raw in sources.items()
        )
    ):
        raise ValueError("resource leaf lacks hash-linked source bytes")
    # T01 decorates traversed injected calls with an evidence pointer. It is
    # derived metadata, not a parser fact; verify that pointer before removing it.
    parsed = copy.deepcopy(_reparse_snapshot(tuple(sorted(sources.items()))))
    supplied = copy.deepcopy(facts)
    # Parameter metadata is additive. Historical snapshots remain verifiable;
    # omit only this new derived field when the original snapshot lacks it.
    for parsed_cls, supplied_cls in zip(parsed["classes"], supplied.get("classes", [])):
        for parsed_method, supplied_method in zip(
            parsed_cls["methods"], supplied_cls["methods"]
        ):
            if "parameters" not in supplied_method:
                parsed_method.pop("parameters", None)
    for cls in supplied.get("classes", []):
        for method in cls["methods"]:
            for call in method["calls"]:
                if "bindingEvidence" in call:
                    fields = [
                        f
                        for f in cls["fields"]
                        if f["name"] == call["receiver"].removeprefix("this.")
                    ]
                    if (
                        len(fields) != 1
                        or call.pop("bindingEvidence") != fields[0]["evidence"]
                    ):
                        raise ValueError(
                            "resource leaf invalid derived binding evidence"
                        )
    if parsed != supplied:
        raise ValueError("resource leaf source facts contradict reparsed source bytes")
