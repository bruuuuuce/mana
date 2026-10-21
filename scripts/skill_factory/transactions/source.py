"""Framework-only JDK parse adapter; target bytes never reach a build or processor."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def java_facts(factory, project, files):
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
                    "JDK parser failed: "
                    + result.stderr.decode("utf-8", "replace")[:2000]
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
        return facts
