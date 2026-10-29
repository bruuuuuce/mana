#!/usr/bin/env python3
"""Targeted offline acceptance for the candidate-only specialist factory."""

import hashlib
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/mana-skill-factory.py"
POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><groupId>example</groupId>
<artifactId>demo</artifactId><version>1</version><dependencies><dependency>
<groupId>org.springframework</groupId><artifactId>spring-context</artifactId>
</dependency></dependencies></project>"""

spec = importlib.util.spec_from_file_location("factory_under_test", CLI)
factory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(factory)
OBSERVED_WRITES = None


def observe_writes(event, args):
    if OBSERVED_WRITES is None:
        return
    paths = []
    if event == "open":
        path, mode, flags = args
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            paths = [(path, None)]
    elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod"}:
        paths = [(args[0], args[-1])]
    elif event in {"os.rename", "os.link"}:
        paths = [(args[0], args[2]), (args[1], args[3])]
    elif event == "os.symlink":
        paths = [(args[1], args[2])]
    for path, dir_fd in paths:
        if isinstance(path, (str, bytes, os.PathLike)):
            resolved = Path(os.fsdecode(path))
            if not resolved.is_absolute() and isinstance(dir_fd, int) and dir_fd >= 0:
                if sys.platform == "darwin":
                    import fcntl

                    parent = os.fsdecode(
                        fcntl.fcntl(dir_fd, fcntl.F_GETPATH, b"\0" * 1024).split(
                            b"\0", 1
                        )[0]
                    )
                else:
                    parent = os.readlink(f"/proc/self/fd/{dir_fd}")
                resolved = Path(parent) / resolved
            OBSERVED_WRITES.append((event, str(resolved.resolve())))


sys.addaudithook(observe_writes)


@contextmanager
def recording_writes():
    global OBSERVED_WRITES
    events = []
    OBSERVED_WRITES = events
    try:
        yield events
    finally:
        OBSERVED_WRITES = None


def snapshot(directory):
    return {
        p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.rglob("*")
        if p.is_file() and not p.is_symlink()
    }


class FactoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mana-meta-skill-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.project = self.base / "project"
        source = self.project / "src/main/java/example/Service.java"
        source.parent.mkdir(parents=True)
        source.write_text("package example; public class Service {}\n")
        (self.project / "pom.xml").write_text(POM)
        self.candidate = self.base / "candidate"

    def invoke(self, command="generate", expected=0, candidate=None, extra=()):
        args = [
            sys.executable,
            str(CLI),
            command,
            "--project-root",
            str(self.project),
            "--candidate-dir",
            str(candidate or self.candidate),
        ]
        if command == "generate":
            args += ["--request", "transaction-analysis"]
        result = subprocess.run(args + list(extra), capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout if expected == 0 else result.stderr)

    def test_evidence_native_contract_read_only_and_no_activation(self):
        before = snapshot(self.project)
        discovery = snapshot(ROOT / "skills")
        profiles = snapshot(ROOT / "profiles")
        self.invoke()
        self.invoke("validate")
        value = json.loads((self.candidate / "candidate.json").read_text())
        self.assertEqual(
            value["evidence"][0]["declarations"], ["org.springframework:spring-context"]
        )
        for fact in value["evidence"]:
            self.assertEqual(
                fact["sha256"],
                hashlib.sha256((self.project / fact["path"]).read_bytes()).hexdigest(),
            )
        self.assertFalse(value["trusted"])
        self.assertFalse(value["executable"])
        self.assertFalse(value["registered"])
        self.assertEqual(value["approval"]["status"], "pending")
        self.assertTrue(
            all(
                c["status"] == "partially_implemented"
                for c in value["futureCapabilities"]
            )
        )
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(ROOT / "skills"), discovery)
        self.assertEqual(snapshot(ROOT / "profiles"), profiles)
        # Existing native metadata and output shape validators run against isolation.
        stage = self.base / "contract-check"
        native = stage / "skills/java-spring-transaction-analysis"
        native.mkdir(parents=True)
        (native / "SKILL.md").write_bytes((self.candidate / "SKILL.md").read_bytes())
        standard = stage / "docs/standards"
        standard.mkdir(parents=True)
        (standard / "agent-skill-output-standard.md").write_bytes(
            (ROOT / "docs/standards/agent-skill-output-standard.md").read_bytes()
        )
        for script in ("validate-skills.sh", "validate-output-standard.sh"):
            result = subprocess.run(
                ["bash", str(ROOT / "scripts" / script), str(stage)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsupported_and_false_positive_technologies(self):
        cases = [
            "<project><!-- org.springframework spring-context --></project>",
            POM.replace("org.springframework", "com.example"),
            POM.replace(
                "<dependencies>", "<dependencyManagement><dependencies>"
            ).replace("</dependencies>", "</dependencies></dependencyManagement>"),
            POM.replace("</dependency>", "<scope>test</scope></dependency>"),
            "<project><description>Spring Java transactions</description></project>",
            "<project><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId></parent></project>",
        ]
        for pom in cases:
            with self.subTest(pom=pom):
                (self.project / "pom.xml").write_text(pom)
                self.invoke(expected=2)
                self.assertFalse(self.candidate.exists())
        (self.project / "pom.xml").unlink()
        (self.project / "build.gradle").write_text(
            "implementation 'org.springframework:spring-tx:6.0.0'"
        )
        self.invoke(expected=2)

    def test_module_locality_and_multimodule_support(self):
        source = self.project / "src/main/java/example/Service.java"
        other = self.project / "other/src/main/java/example/Service.java"
        other.parent.mkdir(parents=True)
        source.rename(other)
        self.invoke(expected=2)
        (self.project / "other/pom.xml").write_text(POM)
        self.invoke()
        value = json.loads((self.candidate / "candidate.json").read_text())
        self.assertEqual(value["evidence"][0]["path"], "other/pom.xml")

    def test_no_java_or_symlink_or_generated_evidence(self):
        source = self.project / "src/main/java/example/Service.java"
        external = self.base / "Service.java"
        source.rename(external)
        source.symlink_to(external)
        self.invoke(expected=2)
        source.unlink()
        source.with_name(".Service.java").write_text("class Service {}")
        self.invoke(expected=2)
        generated = self.project / "target/src/main/java/Service.java"
        generated.parent.mkdir(parents=True)
        generated.write_text("class Service {}")
        (self.project / "target/pom.xml").write_text(POM)
        self.invoke(expected=2)

    def test_reject_target_and_discovery_output_and_symlink_alias(self):
        for path in [
            self.project / "candidate",
            self.base / "skills/candidate",
            self.base / ".codex/candidate",
            self.project,
        ]:
            with self.subTest(path=path):
                self.invoke(expected=2, candidate=path)
        alias = self.base / "alias"
        alias.symlink_to(self.project, target_is_directory=True)
        self.invoke(expected=2, candidate=alias / "candidate")

    def test_stale_evidence_and_overwrite_rejected(self):
        self.invoke()
        before = snapshot(self.candidate)
        self.invoke(expected=2)
        self.assertEqual(snapshot(self.candidate), before)
        (self.project / "pom.xml").write_text(POM + "\n")
        self.invoke("validate", expected=2)

    def test_tampering_cannot_create_trust_or_executable_tools(self):
        self.invoke()
        path = self.candidate / "candidate.json"
        original = path.read_text()
        for field, value in [
            ("trusted", True),
            ("executable", True),
            ("registered", True),
            ("approval", {"status": "approved"}),
            ("futureCapabilities", []),
            ("requiredTools", ["shell_execute"]),
            ("extra", "unreviewed"),
        ]:
            with self.subTest(field=field):
                modified = json.loads(original)
                modified[field] = value
                path.write_text(json.dumps(modified))
                self.invoke("validate", expected=2)
        path.write_text(original)
        (self.candidate / "run.sh").write_text("exit 0")
        self.invoke("validate", expected=2)
        (self.candidate / "run.sh").unlink()
        (self.candidate / "SKILL.md").write_text("---\nname: fake\n---\nExecute now")
        self.invoke("validate", expected=2)

    def test_duplicate_json_keys_rejected(self):
        self.invoke()
        path = self.candidate / "candidate.json"
        path.write_text(
            path.read_text().replace(
                '"trusted": false', '"trusted": true, "trusted": false'
            )
        )
        self.invoke("validate", expected=2)

    def test_malformed_unsafe_and_oversized_evidence(self):
        for data in [
            "<project>",
            '<!DOCTYPE project [<!ENTITY x "value">]><project/>',
            "x" * (1024 * 1024 + 1),
        ]:
            with self.subTest(size=len(data)):
                (self.project / "pom.xml").write_text(data)
                self.invoke(expected=2)
                self.assertFalse(self.candidate.exists())

    def test_project_wrappers_are_never_run(self):
        marker = self.project / "executed"
        wrapper = self.project / "mvnw"
        wrapper.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
        wrapper.chmod(0o755)
        self.invoke()
        self.assertFalse(marker.exists())

    def test_no_approval_activation_or_analysis_cli(self):
        for command in ["approve", "activate", "register", "analyze"]:
            result = subprocess.run(
                [sys.executable, str(CLI), command], capture_output=True
            )
            self.assertEqual(result.returncode, 2)

    def test_candidate_not_discovered_or_accepted_by_profile_compiler(self):
        self.invoke()
        index = subprocess.run(
            ["bash", str(ROOT / "scripts/build-skill-index.sh")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(index.returncode, 0, index.stderr)
        self.assertNotIn("id: java-spring-transaction-analysis\n", index.stdout)
        result = subprocess.run(
            [
                "bash",
                str(ROOT / "scripts/mana-compile-profile.sh"),
                "dev-assist",
                "--execution-id",
                "execution-meta-skill-test",
                "--request-skill",
                "java-spring-transaction-analysis",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("undeclared", result.stderr)

    def assert_no_protected_writes(self, events):
        protected = [self.project, ROOT / "skills", ROOT / "profiles", ROOT / "agents"]
        self.assertFalse(
            [
                (event, path)
                for event, path in events
                if any(Path(path) == p or p in Path(path).parents for p in protected)
            ]
        )

    def test_external_temporary_paths_spaces_symlinks_and_child_writes(self):
        outside = self.base / "external temp with spaces"
        outside.mkdir()
        alias = self.base / "external alias"
        alias.symlink_to(outside, target_is_directory=True)
        wrapper = self.base / "bin/bash"
        wrapper.parent.mkdir()
        log = self.base / "child-writes.jsonl"
        # Observe actual child writes, then run the existing authoritative validator.
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import json,os,sys\nfrom pathlib import Path\n"
            "paths=[]\n"
            "for key in ['TMPDIR','TEMP','TMP','cwd']:\n"
            " parent=Path.cwd() if key=='cwd' else Path(os.environ[key])\n"
            " path=parent/('child-probe-'+key);path.write_text('probe');paths.append(str(path.resolve()))\n"
            "with open(os.environ['F01_CHILD_LOG'],'a') as stream: stream.write(json.dumps(paths)+'\\n')\n"
            "os.execv('/bin/bash',['/bin/bash',*sys.argv[1:]])\n"
        )
        wrapper.chmod(0o755)
        startup = self.project / "startup.sh"
        marker = self.project / "startup-executed"
        startup.write_text(f"touch '{marker}'\n")
        before = snapshot(self.project)
        for i, temporary in enumerate([outside, alias, Path(os.path.relpath(outside))]):
            with self.subTest(temporary=temporary):
                candidate = self.base / f"candidate with spaces-{i}"
                env = {
                    "TMPDIR": str(temporary),
                    "TEMP": str(self.project),
                    "TMP": str(self.project),
                    "PATH": str(wrapper.parent) + os.pathsep + os.environ["PATH"],
                    "F01_CHILD_LOG": str(log),
                    "BASH_ENV": str(startup),
                    "ENV": str(startup),
                }
                with mock.patch.dict(os.environ, env), recording_writes() as events:
                    factory.generate(self.project, candidate)
                    factory.validate(self.project, candidate)
                self.assert_no_protected_writes(events)
                self.assertTrue(
                    events, "write observer must see external output/staging writes"
                )
        self.assertEqual(snapshot(self.project), before)
        self.assertFalse(marker.exists())
        child_paths = [
            Path(p) for line in log.read_text().splitlines() for p in json.loads(line)
        ]
        self.assertTrue(child_paths)
        self.assertTrue(all(outside in p.parents for p in child_paths))

    def test_unsafe_or_missing_temporary_parent_blocks_before_any_write(self):
        self.invoke()
        alias = self.base / "target alias"
        alias.symlink_to(self.project, target_is_directory=True)
        loop = self.base / "loop"
        loop.symlink_to(loop)
        discovery = self.base / "skills"
        discovery.mkdir()
        cases = [
            self.project,
            self.project / "missing with spaces",
            alias,
            alias / "missing",
            Path(os.path.relpath(self.project)),
            self.base / "missing external",
            discovery,
            loop,
        ]
        for temporary in cases:
            for command in ("generate", "validate"):
                with self.subTest(temporary=temporary, command=command):
                    with mock.patch.dict(os.environ, {"TMPDIR": str(temporary)}):
                        with (
                            recording_writes() as events,
                            mock.patch.object(factory.subprocess, "run") as child,
                        ):
                            with self.assertRaisesRegex(
                                factory.FactoryError, "temporary parent"
                            ):
                                if command == "generate":
                                    factory.generate(
                                        self.project, self.base / "uncreated/child"
                                    )
                                else:
                                    factory.validate(self.project, self.candidate)
                            child.assert_not_called()
                        self.assertEqual(events, [])
                    self.assertFalse((self.base / "uncreated").exists())
        # Canonical containment also applies when a host calls the API through an alias.
        with (
            mock.patch.dict(os.environ, {"TMPDIR": str(self.project)}),
            recording_writes() as events,
        ):
            with self.assertRaisesRegex(factory.FactoryError, "temporary parent"):
                factory.generate(alias, self.base / "alias-candidate")
        self.assertEqual(events, [])

    def test_internal_temp_cli_returns_diagnostic_without_output(self):
        argv = [
            sys.executable,
            str(CLI),
            "generate",
            "--project-root",
            str(self.project),
            "--request",
            "transaction-analysis",
            "--candidate-dir",
            str(self.candidate),
        ]
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env={**os.environ, "TMPDIR": str(self.project)},
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stderr)["reason"],
            f"temporary parent is inside analyzed project: {self.project}",
        )
        self.assertFalse(self.candidate.exists())

    def test_temporary_environment_fallbacks_without_host_changes(self):
        before = dict(os.environ)
        for env in [
            {"TMPDIR": "", "TEMP": str(self.project), "TMP": str(self.base)},
            {"TMPDIR": "", "TEMP": "", "TMP": str(self.project)},
        ]:
            with mock.patch.dict(os.environ, env), recording_writes() as events:
                with self.assertRaisesRegex(
                    factory.FactoryError, "inside analyzed project"
                ):
                    factory.generate(self.project, self.candidate)
            self.assertEqual(events, [])
        with (
            mock.patch.dict(os.environ, {"TMPDIR": "", "TEMP": "", "TMP": ""}),
            recording_writes() as events,
        ):
            if os.name == "posix":
                self.assertEqual(
                    factory.temporary_parent(self.project), Path("/tmp").resolve()
                )
        self.assertEqual(events, [])
        self.assertEqual(dict(os.environ), before)

    def test_native_validation_failure_precedes_output_writes(self):
        failed = subprocess.CompletedProcess([], 1, "", "fixture validator failure")
        with (
            recording_writes() as events,
            mock.patch.object(factory.subprocess, "run", return_value=failed),
        ):
            with self.assertRaisesRegex(
                factory.FactoryError, "fixture validator failure"
            ):
                factory.generate(self.project, self.candidate)
        self.assert_no_protected_writes(events)
        self.assertFalse(self.candidate.exists())

    def test_json_malformed_and_deep_cli_block_without_writes(self):
        self.invoke()
        path = self.candidate / "candidate.json"
        for payload in [
            b'{"bad":',
            ('{"extra":' + "[" * 2000 + "0" + "]" * 2000 + "}").encode(),
            ("[0," * 10).encode(),
            b'{"number": NaN}',
        ]:
            with self.subTest(length=len(payload)):
                path.write_bytes(payload)
                before = snapshot(self.candidate)
                with (
                    recording_writes() as events,
                    mock.patch.object(factory.subprocess, "run") as child,
                ):
                    with self.assertRaises(factory.FactoryError):
                        factory.validate(self.project, self.candidate)
                    child.assert_not_called()
                self.assertEqual(events, [])
                response = self.invoke("validate", expected=2)
                self.assertEqual(response["status"], "blocked")
                self.assertEqual(snapshot(self.candidate), before)

    def test_json_size_depth_and_token_boundaries(self):
        self.invoke()
        path = self.candidate / "candidate.json"
        original = path.read_bytes()
        path.write_bytes(original + b" " * (factory.MAX_BYTES - len(original)))
        self.invoke("validate")
        path.write_bytes(path.read_bytes() + b" ")
        self.invoke("validate", expected=2)
        depth = factory.MAX_JSON_DEPTH
        self.assertIsInstance(
            factory.bounded_json(("[" * depth + "0" + "]" * depth).encode()), list
        )
        with self.assertRaisesRegex(factory.FactoryError, "depth limit"):
            factory.bounded_json(("[" * (depth + 1) + "0" + "]" * (depth + 1)).encode())
        # Arrays have one token per delimiter/comma/scalar: 2*n+1.
        close_to_limit = b"[" + b",".join([b"0"] * 9999) + b"]"
        self.assertEqual(len(factory.bounded_json(close_to_limit)), 9999)
        with self.assertRaisesRegex(factory.FactoryError, "token limit"):
            factory.bounded_json(b"[" + b",".join([b"0"] * 10000) + b"]")
        with self.assertRaisesRegex(factory.FactoryError, "byte limit"):
            factory.bounded_json(b" " * (factory.MAX_BYTES + 1))

    def test_quoted_brackets_and_escapes_do_not_consume_depth_budget(self):
        value = {"text": "[" * 2000 + '\\"' + "]" * 2000}
        self.assertEqual(factory.bounded_json(json.dumps(value).encode()), value)

    def test_adapter_boundary_extends_same_technology_without_core_changes(self):
        existing = factory.ADAPTERS[0]
        template = self.base / "fixture-contract.md"
        template.write_text(
            existing.template.read_text().replace(
                existing.skill_id, "fixture-java-contract"
            )
        )

        class FixtureRecipe(type(existing)):
            request = "fixture-java-request"
            skill_id = "fixture-java-contract"

        adapter = FixtureRecipe()
        adapter.template = template
        with mock.patch.object(factory, "ADAPTERS", (adapter,)):
            result = factory.generate(self.project, self.candidate, adapter.request)
            self.assertEqual(result["skillId"], adapter.skill_id)
            factory.validate(self.project, self.candidate)
        value = json.loads((self.candidate / "candidate.json").read_text())
        self.assertEqual(value["request"], adapter.request)
        self.assertFalse(value["trusted"] or value["executable"] or value["registered"])
        self.assertEqual(len(factory.ADAPTERS), 1)
        self.assertEqual(factory.ADAPTERS[0].request, "transaction-analysis")

    def test_unsupported_requests_and_adapter_governance_override_block(self):
        with recording_writes() as events:
            with self.assertRaisesRegex(factory.FactoryError, "unsupported"):
                factory.generate(self.project, self.candidate, "unsupported-technology")
        self.assertEqual(events, [])

        class UnsafeRecipe(type(factory.ADAPTERS[0])):
            skill_id = "../../project/unsafe"

        with (
            mock.patch.object(factory, "ADAPTERS", (UnsafeRecipe(),)),
            recording_writes() as events,
        ):
            with self.assertRaisesRegex(factory.FactoryError, "adapter skill_id"):
                factory.generate(self.project, self.candidate)
        self.assertEqual(events, [])
        adapter = mock.Mock(wraps=factory.ADAPTERS[0])
        adapter.skill_id = factory.ADAPTERS[0].skill_id
        adapter.evidence_names = frozenset({"pom.xml"})
        adapter.evidence_suffixes = frozenset({".java"})
        adapter.specialize.return_value = {
            **factory.ADAPTERS[0].specialize(
                factory.project_files(self.project, factory.ADAPTERS[0])
            ),
            "trusted": True,
        }
        with (
            mock.patch.object(factory, "ADAPTERS", (adapter,)),
            recording_writes() as events,
        ):
            with self.assertRaisesRegex(factory.FactoryError, "adapter contract"):
                factory.generate(self.project, self.candidate)
        self.assertEqual(events, [])
        self.assertFalse(self.candidate.exists())

    def test_overcomplex_generated_manifest_rejected_before_output(self):
        existing = factory.ADAPTERS[0]

        class OversizedRecipe(type(existing)):
            def specialize(self, files):
                domain = super().specialize(files)
                domain["limits"] = ["unbounded"] * 10000
                return domain

        with (
            mock.patch.object(factory, "ADAPTERS", (OversizedRecipe(),)),
            recording_writes() as events,
        ):
            with self.assertRaisesRegex(factory.FactoryError, "token limit"):
                factory.generate(self.project, self.base / "uncreated/child")
        self.assertEqual(events, [])
        self.assertFalse((self.base / "uncreated").exists())


if __name__ == "__main__":
    unittest.main()
