#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('home_paths', ROOT / 'scripts/validate-home-paths.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class HomePaths(unittest.TestCase):
    def test_detection(self):
        mac = '/' + 'Users' + '/person-123/project'
        linux = '/' + 'home' + '/person-123/project'
        windows = 'C:' + chr(92) + 'Users' + chr(92) + 'person-123' + chr(92) + 'project'
        escaped = mac.replace('/', chr(92) + '/')
        encoded = mac.replace('/', '%2F')
        for value in (mac, linux, windows, escaped, encoded, 'file://' + mac, 'file://localhost' + mac,
                      mac.replace('/', chr(92) + 'u002f')):
            with self.subTest(value=value):
                self.assertEqual(list(validator.violations('sample', value)), [1])
        self.assertEqual(list(validator.violations('tests/mana-catalog.py', '/' + 'Users/test/cache')), [])
        self.assertEqual(list(validator.violations('other', '/' + 'Users/test/cache')), [1])
        for value in ('src/project/file.py', '/usr/local/bin', '/var/tmp/data'):
            self.assertEqual(list(validator.violations('sample', value)), [])

    def test_tracked_new_file_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            path = root / 'new.txt'
            private = '/' + 'home' + '/person-123/secret'
            path.write_text('safe\n' + private + '\n')
            subprocess.run(['git', '-C', str(root), 'add', 'new.txt'], check=True)
            before = path.read_bytes()
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate-home-paths.py'), str(root)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("'new.txt':2:", result.stderr)
            self.assertNotIn(private, result.stderr)
            self.assertNotIn('person-123', result.stderr)
            self.assertEqual(path.read_bytes(), before)
            path.write_text('relative/path\n')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate-home-paths.py'), str(root)], capture_output=True)
            self.assertEqual(result.returncode, 1)  # The index still contains the private path.
            subprocess.run(['git', '-C', str(root), 'add', 'new.txt'], check=True)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate-home-paths.py'), str(root)], capture_output=True)
            self.assertEqual(result.returncode, 0)
            path.write_bytes(('café ' + private).encode('latin-1'))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate-home-paths.py'), str(root)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            path.write_bytes(private.encode('utf-16'))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate-home-paths.py'), str(root)], capture_output=True)
            self.assertEqual(result.returncode, 1)


if __name__ == '__main__':
    unittest.main()
