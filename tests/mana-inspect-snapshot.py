#!/usr/bin/env python3
"""Regression coverage for the read-only, single-inventory snapshot producer."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("snapshot", Path(__file__).parents[1] / "scripts/mana-inspect-snapshot.py")
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)

class SnapshotTest(unittest.TestCase):
    def test_feedback_capability_requires_project_and_bundled_producer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertNotIn("human_feedback", snapshot.project(root)["capabilities"])
            (root / ".mana").mkdir()
            for operation in ("project", "semantic-snapshot"):
                result = subprocess.run([str(Path(__file__).parents[1] / "scripts/mana-inspect.sh"), "--project-root", str(root), operation, "--json"], check=True, capture_output=True, text=True)
                value = json.loads(result.stdout)
                project = value if operation == "project" else value["project"]
                self.assertIn("human_feedback", project["capabilities"])
            with patch.object(snapshot, "__file__", str(root / "isolated-producer.py")):
                self.assertNotIn("human_feedback", snapshot.project(root)["capabilities"])
            self.assertEqual(list(root.rglob("*")), [root / ".mana"])

    def test_one_inventory_and_same_byte_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / ".mana/global/architecture.md"
            source.parent.mkdir(parents=True)
            source.write_text("# Architecture\nCittà e scelte\n", encoding="utf-8")
            catalog = snapshot.producer("catalog")
            semantic = snapshot.producer("semantic")
            before = source.read_bytes()
            with patch.object(snapshot, "producer", side_effect=lambda name: catalog if name == "catalog" else semantic), patch.object(catalog, "catalog", wraps=catalog.catalog) as scan:
                first = snapshot.snapshot(root, True)
                self.assertEqual(scan.call_count, 1)
                replacement = source.with_suffix(".tmp")
                replacement.write_bytes(before)
                replacement.replace(source)
                second = snapshot.snapshot(root, True)
                self.assertEqual(scan.call_count, 2)
            self.assertEqual(first["snapshot_revision"], second["snapshot_revision"])
            self.assertEqual(first["projections"]["work_items"], second["projections"]["work_items"])
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual([path for path in root.rglob("*") if path.is_file()], [source])
            self.assertEqual(first["projections"]["activity"]["status"], "available")
            self.assertEqual(first["inventory"]["catalog_build_count"], 1)
            result = subprocess.run([str(Path(__file__).parents[1] / "scripts/mana-inspect.sh"), "--project-root", str(root), "artifacts", "--json"], check=True, capture_output=True, text=True)
            public = json.loads(result.stdout)
            self.assertEqual(public["schema"], "mana.inspect.artifacts/v1")
            self.assertEqual(public["artifacts"], catalog.catalog(root))
            self.assertEqual(public["guarantees"], {"model_calls": 0, "writes": False, "paths": "project_relative_only"})
            self.assertEqual([path for path in root.rglob("*") if path.is_file()], [source])

if __name__ == "__main__":
    unittest.main()
