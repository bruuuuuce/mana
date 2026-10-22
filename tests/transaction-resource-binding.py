#!/usr/bin/env python3
"""F02 literal binding/dispatch oracles; javac compiles only these isolated fixtures."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/resource-timeline"
REVIEWS = {
    n: json.loads(
        (
            ROOT / f"docs/reports/MANA-TRANSACTION-01-T02-S01-D02-{n}-results.json"
        ).read_text()
    )
    for n in ["R1", "R2"]
}
# The actual R2 source is independently retained as a mandatory negative.
R2 = REVIEWS["R2"]["counterexample"]["source"]
BASE = (
    R2.split("\n@Service\nclass ApplicationJdbc", 1)[0]
    .replace(
        "class Operations<JdbcTemplate extends ApplicationJdbc>", "class Operations"
    )
    .replace(
        "@Autowired JdbcTemplate jdbc;",
        "private final JdbcTemplate jdbc = new JdbcTemplate();",
    )
)
DYNAMIC = BASE.replace(
    "private final JdbcTemplate jdbc = new JdbcTemplate();",
    "@Autowired JdbcTemplate jdbc;",
)
SUBCLASS = "\nclass CustomJdbc extends JdbcTemplate { @Override public void execute(String sql) {} }\n"
# Literal expectations; neither source expectations nor javap owners come from Mana.
CASES = {
    "import_allocation": (BASE, 2),
    "qualified": (
        BASE.replace(
            "private final JdbcTemplate jdbc = new JdbcTemplate();",
            "private final org.springframework.jdbc.core.JdbcTemplate jdbc = new org.springframework.jdbc.core.JdbcTemplate();",
        ),
        0,
    ),
    "generic_shadow": (R2, 0),
    "application_homonym": (
        DYNAMIC.replace("import org.springframework.jdbc.core.JdbcTemplate;", "")
        + "\nclass JdbcTemplate { public void execute(String sql) {} public int update(String sql) { return 0; } }",
        0,
    ),
    "override": (DYNAMIC + SUBCLASS, 0),
    "dynamic": (DYNAMIC, 0),
    "overload": (
        BASE.replace(
            'jdbc.execute("SELECT * FROM accounts")',
            'jdbc.execute("SELECT * FROM accounts", "extra")',
        ),
        0,
    ),
    "three": (
        BASE.replace(
            'jdbc.update("DELETE FROM ledger");',
            'jdbc.update("DELETE FROM ledger"); jdbc.update("INSERT INTO audit (id) VALUES (1)");',
        ),
        3,
    ),
    "member": (DYNAMIC + "\nclass CustomConfig { static " + SUBCLASS + " }", 0),
    "local": (DYNAMIC + "\nclass Provider { void create() { " + SUBCLASS + " } }", 0),
    "generic_bound_spring": (
        DYNAMIC.replace(
            "class Operations",
            "class Operations<JdbcTemplate extends org.springframework.jdbc.core.JdbcTemplate>",
        ),
        0,
    ),
    "method_generic": (
        BASE.replace("public void sequence()", "public <JdbcTemplate> void sequence()"),
        0,
    ),
    "mutable": (BASE.replace("private final JdbcTemplate", "private JdbcTemplate"), 0),
    "anonymous": (
        BASE.replace(
            "new JdbcTemplate();",
            "new JdbcTemplate() { @Override public void execute(String sql) {} };",
        ),
        0,
    ),
}
STUBS = {
    "org/springframework/jdbc/core/JdbcTemplate.java": "package org.springframework.jdbc.core; public class JdbcTemplate { public void execute(String sql) {} public void execute(String sql, String extra) {} public int update(String sql) { return 0; } }",
    "org/springframework/jdbc/datasource/DataSourceTransactionManager.java": "package org.springframework.jdbc.datasource; public class DataSourceTransactionManager {}",
}
for package, names in {
    "org.springframework.stereotype": ["Service"],
    "org.springframework.beans.factory.annotation": ["Autowired"],
    "org.springframework.transaction.annotation": [
        "Transactional",
        "EnableTransactionManagement",
    ],
    "org.springframework.context.annotation": ["Configuration", "Bean"],
}.items():
    for name in names:
        STUBS[package.replace(".", "/") + "/" + name + ".java"] = (
            f"package {package}; public @interface {name} {{ boolean proxyTargetClass() default false; }}"
        )


def snapshot(project):
    return {
        str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in project.rglob("*")
        if p.is_file()
    }


class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="mana-binding-")
        cls.stage = Path(cls.tmp.name).resolve()
        spec = importlib.util.spec_from_file_location(
            "binding_cli", ROOT / "scripts/mana-resource-timeline.py"
        )
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)
        cls.oracle_results = {}
        cls.reports = {}
        cls.projects = {}
        for name, (source, _) in {
            **CASES,
            "historical_r1": (REVIEWS["R1"]["counterexample"]["source"], 0),
        }.items():
            project = cls.stage / name
            path = project / "src/main/java/fixture/Resources.java"
            path.parent.mkdir(parents=True)
            path.write_text(source)
            shutil.copyfile(FIXTURE / "pom.xml", project / "pom.xml")
            context = json.loads((FIXTURE / "context.json").read_text())
            context["resourceLeafPolicy"] = "JDBC_LITERAL_V1"
            (project / "context.json").write_text(json.dumps(context))
            before = snapshot(project)
            cls.reports[name] = cls.cli.analyze(
                project, project / "context.json", "fixture.Operations#sequence()"
            )
            if snapshot(project) != before:
                raise AssertionError("analysis modified target")
            cls.projects[name] = project

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def leaves(self, name):
        return [
            e
            for e in self.reports[name]["transactionModel"]["events"]
            if e["kind"] == "RESOURCE_LEAF_CALL"
        ]

    def reject_both(self, report, message="resource leaf"):
        with self.assertRaisesRegex(ValueError, message):
            self.cli.t01.validate_model(report["transactionModel"])
        with self.assertRaisesRegex(ValueError, message):
            self.cli.validate_timeline(report)

    def test_literal_matrix(self):
        for name, (_, expected) in CASES.items():
            with self.subTest(case=name):
                report = self.reports[name]
                self.cli.t01.validate_model(report["transactionModel"])
                self.cli.validate_timeline(report)
                self.assertEqual(len(self.leaves(name)), expected)

    def test_two_consecutive_certified_leaves(self):
        leaves = self.leaves("import_allocation")
        self.assertEqual([e["sequence"] for e in leaves], [4, 5])
        self.assertEqual(
            [e["witness"]["normalReturnDependencies"] for e in leaves], [[], [4]]
        )
        self.assertEqual(
            [
                o["transactionContext"]["physicalId"]
                for o in self.reports["import_allocation"]["observations"]
            ],
            ["P1", "P1"],
        )

    def test_three_consecutive_certified_leaves(self):
        leaves = self.leaves("three")
        self.assertEqual([e["sequence"] for e in leaves], [4, 5, 6])
        self.assertEqual(
            [e["witness"]["normalReturnDependencies"] for e in leaves],
            [[], [4], [4, 5]],
        )

    def test_dynamic_receiver_has_no_false_continuation(self):
        report = self.reports["dynamic"]
        self.assertEqual(
            [o["placement"]["status"] for o in report["observations"]],
            ["T01_FRONTIER", "UNPLACED"],
        )
        self.assertEqual(
            [o["transactionContext"]["physicalId"] for o in report["observations"]],
            ["P1", None],
        )
        self.assertIn(
            "RESOURCE_LEAF_DISPATCH_UNPROVEN",
            [u["reason"] for u in report["transactionModel"]["uncertainties"]],
        )

    def test_both_historical_high_sources_and_witnesses(self):
        for review, case in [("R1", "historical_r1"), ("R2", "generic_shadow")]:
            with self.subTest(review=review):
                counterexample = REVIEWS[review]["counterexample"]
                raw = (self.projects[case] / counterexample["sourcePath"]).read_bytes()
                self.assertEqual(
                    hashlib.sha256(raw).hexdigest(), counterexample["sourceSha256"]
                )
                self.assertEqual(self.leaves(case), [])
                report = self.reports[case]
                self.assertEqual(
                    [o["placement"]["status"] for o in report["observations"]],
                    ["T01_FRONTIER", "UNPLACED"],
                )
                self.reject_both(copy.deepcopy(counterexample["fullReport"]))

    def test_forged_witness(self):
        report = copy.deepcopy(self.reports["import_allocation"])
        report["transactionModel"]["events"][3]["witness"]["signature"] = (
            "app.JdbcTemplate#execute(java.lang.String):void"
        )
        self.reject_both(report)

    def test_forged_producer_facts_conflict_with_source_bytes(self):
        report = copy.deepcopy(self.reports["import_allocation"])
        facts = report["transactionModel"]["resourceLeafExtension"]["sourceFacts"]
        next(c for c in facts["classes"] if c["simpleName"] == "Operations")["fields"][
            0
        ]["allocation"]["explicitType"] = False
        report["sourceFacts"] = copy.deepcopy(facts)
        self.reject_both(report, "reparsed source bytes")

    def test_forged_proof_on_authentic_dynamic_source(self):
        report = copy.deepcopy(self.reports["import_allocation"])
        facts = copy.deepcopy(self.reports["dynamic"]["sourceFacts"])
        field = next(c for c in facts["classes"] if c["simpleName"] == "Operations")[
            "fields"
        ][0]
        positive = self.reports["import_allocation"]["sourceFacts"]
        proof = next(c for c in positive["classes"] if c["simpleName"] == "Operations")[
            "fields"
        ][0]
        for key in ["flags", "allocation", "initialized", "annotations"]:
            field[key] = copy.deepcopy(proof[key])
        # Genuine negative bytes and matching declared hashes; only the proof facts lie.
        digest = hashlib.sha256(DYNAMIC.encode()).hexdigest()

        def rehash(value):
            if isinstance(value, dict):
                if "sha256" in value:
                    value["sha256"] = digest
                for item in value.values():
                    rehash(item)
            elif isinstance(value, list):
                for item in value:
                    rehash(item)

        rehash(report)
        rehash(facts)
        report["transactionModel"]["resourceLeafExtension"]["sourceFacts"] = facts
        report["sourceFacts"] = copy.deepcopy(facts)
        self.reject_both(report, "reparsed source bytes")

    def test_missing_source_bytes_cannot_certify(self):
        report = copy.deepcopy(self.reports["import_allocation"])
        del report["transactionModel"]["resourceLeafExtension"]["sourceFacts"][
            "sources"
        ]
        self.reject_both(report, "source bytes")

    def test_javac_javap_independent_binding_oracles(self):
        # Compile these tiny fixtures only. No class, processor or target is run.
        expected_owners = {
            "generic_shadow": "fixture/ApplicationJdbc",
            "application_homonym": "fixture/JdbcTemplate",
        }
        for name in CASES:
            with self.subTest(case=name):
                stage = self.stage / ("oracle-" + name)
                stage.mkdir()
                files = {**STUBS, "fixture/Resources.java": CASES[name][0]}
                for relative, source in files.items():
                    path = stage / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(source)
                classes = stage / "classes"
                classes.mkdir()
                env = {
                    k: v
                    for k, v in os.environ.items()
                    if k
                    not in {
                        "CLASSPATH",
                        "JAVA_TOOL_OPTIONS",
                        "_JAVA_OPTIONS",
                        "JDK_JAVA_OPTIONS",
                        "JDK_JAVAC_OPTIONS",
                    }
                }
                compile_result = subprocess.run(
                    [
                        "javac",
                        "-proc:none",
                        "-cp",
                        str(classes),
                        "-d",
                        str(classes),
                        *[str(stage / p) for p in files],
                    ],
                    cwd=stage,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
                result = subprocess.run(
                    [
                        "javap",
                        "-c",
                        "-p",
                        "-s",
                        "-classpath",
                        str(classes),
                        "fixture.Operations",
                    ],
                    cwd=stage,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.oracle_results[name] = {
                    "sources": files,
                    "javacExit": compile_result.returncode,
                    "javacStderr": compile_result.stderr,
                    "javapExit": result.returncode,
                    "javapOutput": result.stdout,
                }
                owner = expected_owners.get(
                    name, "org/springframework/jdbc/core/JdbcTemplate"
                )
                self.assertIn(owner + ".execute:", result.stdout)
                self.assertIn(owner + ".update:(Ljava/lang/String;)I", result.stdout)
                if name == "generic_shadow":
                    self.assertIn(
                        "descriptor: Lfixture/ApplicationJdbc;", result.stdout
                    )
                if name in {"import_allocation", "three"}:
                    self.assertIn(
                        "private final org.springframework.jdbc.core.JdbcTemplate jdbc;",
                        result.stdout,
                    )
                    self.assertIn('JdbcTemplate."<init>":()V', result.stdout)
                if name in {"override", "member", "local", "anonymous"}:
                    # A Spring symbolic invokevirtual owner alone does not prove
                    # the dynamic implementation. Inspect the application override.
                    target = {
                        "override": "fixture.CustomJdbc",
                        "member": "fixture.CustomConfig$CustomJdbc",
                        "local": "fixture.Provider$1CustomJdbc",
                        "anonymous": "fixture.Operations$1",
                    }[name]
                    override = subprocess.run(
                        ["javap", "-c", "-p", "-s", "-classpath", str(classes), target],
                        cwd=stage,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assertEqual(override.returncode, 0, override.stderr)
                    self.assertIn(
                        "public void execute(java.lang.String);", override.stdout
                    )
                    self.oracle_results[name]["overrideOutput"] = override.stdout


if __name__ == "__main__":
    unittest.main()
