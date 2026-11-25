#!/usr/bin/env python3
"""Exercise hierarchical configuration through the direct and linked CLI."""

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="mana-project-config-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.area = self.base / "work"
        self.group = self.area / "payments"
        self.deep = self.group / "backend"
        self.project = self.deep / "ledger"
        self.project.mkdir(parents=True)
        self.xdg = self.base / "settings"
        self.registry = self.xdg / "mana" / "locations.toml"
        self.registry.parent.mkdir(parents=True)
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.xdg)}
        self.registry.write_text(f'''version = 1
[vaults]
work = "{self.base / 'vault'}"
[knowledge]
common = "{self.base / 'common'}"
personal = "{self.base / 'personal'}"
payments = "{self.base / 'payments-kb'}"
[roots.work]
path = "{self.area}"
vaults = ["work"]
knowledge = ["common", "payments"]
''')

    def layer(self, directory, content):
        file = directory / "mana.toml"
        file.write_text("version = 1\n" + content)
        return str(file)

    def invoke(self, project=None, args=("explain", "--json")):
        project = project or self.project
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/mana-config.py"), "--project-root", str(project), *args],
            env=self.env, cwd=self.base, capture_output=True, text=True,
        )

    def result(self, project=None):
        call = self.invoke(project)
        self.assertEqual(call.returncode, 0, call.stderr)
        return json.loads(call.stdout)

    def test_no_files_or_registry(self):
        self.assertEqual(self.result()["reason"], "no-project-config")
        self.registry.unlink()
        self.assertEqual(self.result()["reason"], "unregistered-project")

    def test_single_file_at_each_depth(self):
        for folder in (self.area, self.group, self.deep, self.project):
            with self.subTest(folder=folder):
                source = self.layer(folder, '[export]\nvault = "work"\n')
                data = self.result()
                self.assertEqual(data["files"], [source])
                self.assertEqual(data["settings"]["export.vault"], {"value": "work", "source": source})
                Path(source).unlink()

    def test_merge_and_override_with_missing_intermediate_file(self):
        root = self.layer(self.area, '[knowledge.sources]\ncommon = true\n[profiles.review.skills]\na = true\nb = true\n')
        group = self.layer(self.group, '[knowledge.sources]\npayments = true\n[profiles.review]\nruntime = "legacy"\n')
        leaf = self.layer(self.project, '[project]\nid = "ledger"\n[knowledge.sources]\ncommon = false\n[profiles.review.skills]\na = false\n')
        data = self.result()
        self.assertEqual(data["files"], [root, group, leaf])
        self.assertEqual(data["settings"]["knowledge.sources.common"], {"source": leaf, "value": False})
        self.assertEqual(data["settings"]["knowledge.sources.payments"], {"source": group, "value": True})
        self.assertEqual(data["settings"]["profiles.review.skills.b"], {"source": root, "value": True})
        self.assertEqual(data["settings"]["profiles.review.skills.a"], {"source": leaf, "value": False})
        self.assertEqual(data["settings"]["profiles.review.runtime"]["value"], "legacy")
        self.assertEqual(data["settings"]["project.id"]["value"], "ledger")

    def test_nested_registered_root_cuts_off_outer_files(self):
        self.layer(self.area, "unexpected = true\n")
        with self.registry.open("a") as out:
            out.write(f'\n[roots.nested]\npath = "{self.deep}"\nvaults = ["work"]\n')
        source = self.layer(self.deep, '[export]\nvault = "work"\n')
        self.assertEqual(self.result()["files"], [source])

    def test_nested_root_cannot_be_bypassed_with_an_alternate_case(self):
        alternate = self.group / "BACKEND"
        if not alternate.exists():
            self.skipTest("fixture filesystem is case-sensitive")
        self.assertTrue(alternate.samefile(self.deep))
        self.layer(self.area, '[export]\nvault = "work"\n')
        with self.registry.open("a") as out:
            out.write(f'\n[roots.nested]\npath = "{self.deep}"\n')
        data = self.result(alternate / self.project.name)
        self.assertTrue(Path(data["workspaceRoot"]).samefile(self.deep))
        self.assertEqual(data["settings"], {})
        with self.registry.open("a") as out:
            out.write(f'\n[roots.duplicate]\npath = "{alternate}"\n')
        self.assertIn("duplicate workspace root", self.invoke().stderr)

    def test_all_four_layers_and_a_project_as_registered_root(self):
        sources = [
            self.layer(self.area, '[profiles.review]\nruntime = "shadow"\n'),
            self.layer(self.group, '[profiles.review]\nruntime = "v2"\n'),
            self.layer(self.deep, '[profiles.review]\nruntime = "legacy"\n'),
            self.layer(self.project, '[profiles.review]\nruntime = "v2"\n'),
        ]
        data = self.result()
        self.assertEqual(data["files"], sources)
        self.assertEqual(data["settings"]["profiles.review.runtime"],
                         {"value": "v2", "source": sources[-1]})
        with self.registry.open("a") as out:
            out.write(f'\n[roots.leaf]\npath = "{self.project}"\n')
        source = self.layer(self.project, '[project]\nid = "ledger"\n')
        data = self.result()
        self.assertEqual(data["files"], [source])
        self.assertEqual(data["settings"], {"project.id": {"value": "ledger", "source": source}})

    def test_unregistered_and_sibling_files_are_ignored(self):
        outside = self.base / "work-other"
        outside.mkdir()
        self.layer(outside, "broken =\n")
        self.assertEqual(self.result(outside)["reason"], "unregistered-project")
        sibling = self.group / "sibling"
        sibling.mkdir()
        self.layer(sibling, "broken =\n")
        self.assertEqual(self.result()["reason"], "no-project-config")

    def test_invalid_nearer_file_is_not_silently_skipped(self):
        self.layer(self.area, '[export]\nvault = "work"\n')
        cases = {
            "unknown key": "unknown = true\n",
            "TOML": "version = 1\n",
            "export.vault": '[export]\nvault = "../other"\n',
            "personal": "[knowledge.sources]\npersonal = true\n",
            "expected a boolean": '[profiles.review.skills]\na = "yes"\n',
            "runtime": '[profiles.review]\nruntime = "compare"\n',
        }
        for diagnostic, content in cases.items():
            with self.subTest(content=content):
                source = self.layer(self.project, content)
                call = self.invoke()
                self.assertEqual(call.returncode, 2)
                self.assertIn(source, call.stderr)
                self.assertIn(diagnostic, call.stderr)
        (self.project / "mana.toml").write_text("version = 2\n")
        self.assertIn("expected version = 1", self.invoke().stderr)

    def test_project_id_cannot_be_inherited(self):
        self.layer(self.group, '[project]\nid = "ledger"\n')
        self.assertIn("identity belongs in the project directory", self.invoke().stderr)

    def test_symlink_config_rejected(self):
        outside = self.base / "elsewhere.toml"
        outside.write_text("version = 1\n")
        (self.project / "mana.toml").symlink_to(outside)
        self.assertEqual(self.invoke().returncode, 2)
        (self.project / "mana.toml").unlink()
        self.registry.unlink()
        self.registry.symlink_to(outside)
        self.assertEqual(self.invoke().returncode, 2)

    def test_linked_launcher_targets_its_own_project_and_is_read_only(self):
        source = self.layer(self.group, '[export]\nvault = "work"\n')
        bootstrap = subprocess.run(
            ["bash", str(ROOT / "scripts/bootstrap-project.sh"), "--project-root", str(self.project),
             "--no-links", "--no-jira-env", "--no-gitignore"],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)
        before = {p.relative_to(self.project): p.stat().st_mtime_ns for p in self.project.rglob("*")}
        for options in ([], ["--json"]):
            call = subprocess.run([str(self.project / "mana"), "config", "explain", *options],
                                  cwd=self.base, env=self.env, capture_output=True, text=True)
            self.assertEqual(call.returncode, 0, call.stderr)
            if options:
                self.assertEqual(json.loads(call.stdout)["files"], [source])
            else:
                self.assertIn("export.vault", call.stdout)
                self.assertIn(source, call.stdout)
        self.assertEqual(before, {p.relative_to(self.project): p.stat().st_mtime_ns for p in self.project.rglob("*")})

    def run_script(self, script, *arguments, expected=0):
        call = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), *map(str, arguments)],
            env={**self.env, "MANA_CACHE_HOME": str(self.base / "cache"), "PYTHONDONTWRITEBYTECODE": "1"},
            cwd=self.base, capture_output=True, text=True,
        )
        self.assertEqual(call.returncode, expected, (call.stdout, call.stderr))
        return call

    def test_export_generated_multientry_bundle_and_preserve_edits(self):
        fixture = ROOT / "tests/fixtures/transaction-investigation"
        shutil.copytree(fixture, self.project, dirs_exist_ok=True)
        self.layer(self.area, '[export]\nvault = "work"\n')
        self.layer(self.project, '[project]\nid = "ledger"\n')
        vault = self.base / "vault"
        vault.mkdir()
        bundle = self.base / "report bundle"
        self.run_script(
            "mana-investigate-transactions.py", "--project-root", self.project, "--output-dir", bundle,
            "--context", self.project / "context.json", "--entry", "investigation.OrderService#process()",
            "--entry", "investigation.OrderService#newBoundary()",
        )
        args = ("--project-root", self.project, "transaction", "--from", bundle, "--json")
        result = json.loads(self.run_script("mana-export.py", *args).stdout)
        dest = Path(result["destination"])
        self.assertEqual(result["status"], "preview")
        self.assertEqual(list(vault.iterdir()), [])
        self.assertEqual(json.loads(self.run_script("mana-export.py", *args, "--apply").stdout)["status"], "exported")
        self.assertEqual(sorted(p.name for p in dest.iterdir()), ["entry-02.sequence.puml", "report.md", "sequence.puml"])
        report = dest / "report.md"
        original = report.read_text()
        self.assertNotIn(str(self.project), original)
        self.assertNotIn("Evidence and reproduction commands", original)
        self.assertIn("](./entry-02.sequence.puml)", original)
        self.assertEqual(json.loads(self.run_script("mana-export.py", *args, "--apply").stdout)["status"], "unchanged")

        sibling = self.group / "similar"
        shutil.copytree(fixture, sibling)
        self.layer(sibling, '[project]\nid = "ledger"\n')
        rejected = self.run_script(
            "mana-export.py", "--project-root", sibling, "transaction", "--from", bundle, "--apply", expected=2
        )
        self.assertIn("different project", rejected.stderr)
        sibling_bundle = self.base / "sibling bundle"
        self.run_script(
            "mana-investigate-transactions.py", "--project-root", sibling, "--output-dir", sibling_bundle,
            "--context", sibling / "context.json", "--entry", "investigation.OrderService#process()",
            "--entry", "investigation.OrderService#newBoundary()",
        )
        sibling_result = json.loads(self.run_script(
            "mana-export.py", "--project-root", sibling, "transaction", "--from", sibling_bundle, "--apply", "--json"
        ).stdout)
        self.assertNotEqual(Path(sibling_result["destination"]).parent, dest.parent)

        report.write_text(original + "\nMy Obsidian notes.\n")
        self.assertIn("modified artifacts", self.run_script("mana-export.py", *args, "--apply", expected=2).stderr)
        self.assertTrue(report.read_text().endswith("My Obsidian notes.\n"))
        self.assertEqual(list(dest.parent.iterdir()), [dest])
        source_report = bundle / "report.md"
        original_source = source_report.read_bytes()
        manifest_file = bundle / "entries.json"
        original_manifest = manifest_file.read_bytes()
        heading = b"### Transaction call tree"
        def insert_path(value):
            source_report.write_bytes(original_source.replace(b"\n" + heading, b"\nPath: " + value + b"\n\n" + heading, 1))
        insert_path(b"/private/sample/secret")
        self.assertIn("digest differs", self.run_script("mana-export.py", *args, expected=2).stderr)
        for path in (b"/private/sample/secret", b"/srv/application/file", b"/data/import/source",
                     b"file:/srv/application/file", b"file:///srv/application/file",
                     br"\\server\share\secret"):
            with self.subTest(path=path):
                insert_path(path)
                manifest = json.loads(original_manifest)
                manifest["reportSha256"] = hashlib.sha256(source_report.read_bytes()).hexdigest()
                manifest_file.write_text(json.dumps(manifest))
                self.assertIn("machine-specific path", self.run_script("mana-export.py", *args, expected=2).stderr)
        source_report.write_bytes(original_source)
        manifest_file.write_bytes(original_manifest)
        diagram = bundle / "sequence.puml"
        original_diagram = diagram.read_bytes()
        diagram.write_text("tampered")
        self.assertIn("digest differs", self.run_script("mana-export.py", *args, expected=2).stderr)
        diagram.write_bytes(original_diagram + b"\n' Reference: /srv/application/trace\n")
        manifest = json.loads(original_manifest)
        manifest["entries"][0]["sequenceDiagramSha256"] = hashlib.sha256(diagram.read_bytes()).hexdigest()
        manifest_file.write_text(json.dumps(manifest))
        self.assertIn("sequence.puml: contains a machine-specific path",
                      self.run_script("mana-export.py", *args, expected=2).stderr)

        alternate_project = self.deep / self.project.name.upper()
        if alternate_project.exists():
            nested_vault = self.project / "vault"
            nested_vault.mkdir()
            self.registry.write_text(self.registry.read_text().replace(
                f'work = "{vault}"', f'work = "{alternate_project / "vault"}"'))
            diagram.write_bytes(original_diagram)
            manifest_file.write_bytes(original_manifest)
            denied = self.run_script("mana-export.py", *args, "--apply", expected=2)
            self.assertIn("must be outside the project", denied.stderr)
            self.assertEqual(list(nested_vault.iterdir()), [])

    def test_export_interruption_leaves_no_partial_bundle(self):
        script = ROOT / "scripts/mana-export.py"
        spec = importlib.util.spec_from_file_location("mana_test_export", script)
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", [str(script.parent), *sys.path]):
            spec.loader.exec_module(module)
        staging, contract_error = module.staging_class()
        vault = self.base / "vault"
        vault.mkdir()
        original = staging.write_bytes

        def interrupt(stage, artifact, payload):
            if artifact == "sequence.puml":
                raise KeyboardInterrupt
            original(stage, artifact, payload)

        with patch.object(module, "staging_class", return_value=(staging, contract_error)):
            with patch.object(staging, "write_bytes", interrupt), self.assertRaises(KeyboardInterrupt):
                module.publish(vault, "Mana/ledger", "analysis-1",
                               {"report.md": b"report", "sequence.puml": b"diagram"})
            self.assertEqual(list((vault / "Mana/ledger").iterdir()), [])
            self.assertEqual(module.publish(vault, "Mana/ledger", "analysis-1",
                                            {"report.md": b"report", "sequence.puml": b"diagram"}), "exported")

    def test_knowledge_sources_are_scoped_read_only_and_revocable(self):
        (self.project / ".mana").mkdir()
        for name in ("common", "payments-kb", "personal"):
            folder = self.base / name
            folder.mkdir()
            (folder / "note.md").write_text(f"# {name}\n\nA unique thermocline observation.\n")
        (self.base / "common" / "outside.md").symlink_to(self.base / "personal" / "note.md")
        self.layer(self.area, "[knowledge.sources]\ncommon = true\npersonal = false\n")
        self.layer(self.group, "[knowledge.sources]\npayments = true\n")
        args = ("--project-root", self.project)
        self.run_script("mana-catalog.py", *args, "build", "--json")
        self.run_script("mana-knowledge.py", *args, "build", "--json")
        search = (*args, "search", "--query", "thermocline", "--json")
        found = json.loads(self.run_script("mana-knowledge.py", *search).stdout)
        self.assertEqual({item["source_reference"] for item in found["results"]},
                         {"mana://knowledge/common/note.md", "mana://knowledge/payments/note.md"})
        self.layer(self.project, "[knowledge.sources]\npayments = false\n")
        stale = json.loads(self.run_script("mana-knowledge.py", *search, expected=4).stdout)
        self.assertEqual(stale["results"], [])
        self.run_script("mana-knowledge.py", *args, "build", "--json")
        found = json.loads(self.run_script("mana-knowledge.py", *search).stdout)
        self.assertEqual([item["source_reference"] for item in found["results"]],
                         ["mana://knowledge/common/note.md"])

    def test_profile_preferences_use_existing_runtime_and_skill_admission(self):
        args = ("--project-root", self.project, "profile-options", "--profile", "requested-pr-review")
        self.layer(self.group, '[profiles.requested-pr-review]\nruntime = "shadow"\n'
                   '[profiles.requested-pr-review.skills]\narchitecture-risk = true\n')
        denied = self.run_script("mana-config.py", *args, expected=2)
        self.assertIn("allow_runtime", denied.stderr)
        explicit = self.run_script("mana-config.py", *args, "--explicit-runtime")
        self.assertEqual(explicit.stdout.strip(), "skill architecture-risk")
        explicit_signal = self.run_script("mana-config.py", *args, "--explicit-runtime",
                                          "--static-signal", "architecture_boundary_change")
        self.assertEqual(explicit_signal.stdout.strip(), "")
        with self.registry.open("a") as config:
            config.write("allow_runtime = true\n")

        def run_profile(*arguments):
            return subprocess.run(
                ["bash", str(ROOT / "scripts/run-profile.sh"), "requested-pr-review", "--project-root", str(self.project), *arguments],
                env={**self.env, "MANA_UPDATE_CHECK": "off"}, cwd=self.base, capture_output=True, text=True,
            )

        shadow = run_profile()
        self.assertEqual(shadow.returncode, 2, shadow.stdout)
        self.assertIn("shadow requires an initialized execution identity", shadow.stderr)
        legacy = run_profile("--context-runtime", "legacy", "--render-only")
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertIn("architecture-risk", legacy.stdout)
        self.layer(self.project, '[profiles.requested-pr-review]\nruntime = "v2"\n'
                   '[profiles.requested-pr-review.skills]\narchitecture-risk = false\n')
        v2 = run_profile()
        self.assertEqual(v2.returncode, 2, v2.stdout)
        self.assertIn("CTX10_EXECUTION_IDENTITY_REQUIRED", v2.stderr)

    def test_legacy_baseline_skill_preference_is_already_satisfied(self):
        self.layer(self.group, "[profiles.architecture-review.skills]\narchitecture-risk = true\n")
        result = self.run_script("mana-config.py", "--project-root", self.project,
                                 "profile-options", "--profile", "architecture-review")
        self.assertEqual(result.stdout, "")

    def test_registry_rejects_symlink_rebinding_and_personal_overlap(self):
        shared = self.base / "common"
        shared.symlink_to(self.base / "personal")
        self.assertIn("canonical path", self.invoke().stderr)
        shared.unlink()
        self.registry.write_text(self.registry.read_text().replace(
            f'personal = "{self.base / "personal"}"', f'personal = "{shared / "personal"}"'))
        self.assertIn("locations must not overlap", self.invoke().stderr)

    def test_personal_alias_is_available_and_read_only_with_stale_mirror(self):
        personal = self.base / "personal"
        personal.mkdir()
        (personal / "preference.md").write_text("# Personal\n\nA private thermocline note.\n")
        (self.project / ".mana/user-context").mkdir(parents=True)
        self.registry.write_text(self.registry.read_text().replace(
            'knowledge = ["common", "payments"]',
            'knowledge = ["personal"]\nallow_personal = true'))
        self.layer(self.area, "[knowledge.sources]\npersonal = true\n")
        args = ("--project-root", self.project)
        self.run_script("mana-catalog.py", *args, "build", "--json")
        self.run_script("mana-knowledge.py", *args, "build", "--json")
        capabilities = json.loads(self.run_script("mana-knowledge.py", *args, "capabilities", "--json").stdout)
        user = next(item for item in capabilities["scopes"] if item["scope"] == "user")
        self.assertEqual(user["health"], "current")
        self.assertFalse(user["editable"])
        search = (*args, "search", "--query", "thermocline", "--scope", "user", "--json")
        found = json.loads(self.run_script("mana-knowledge.py", *search).stdout)["results"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["source_reference"], "mana://knowledge/personal/preference.md")
        result = self.run_script("mana-knowledge.py", *args, "document", found[0]["document_id"], "--json")
        self.assertFalse(json.loads(result.stdout)["document"]["edit_capability"]["available"])


if __name__ == "__main__":
    unittest.main()
