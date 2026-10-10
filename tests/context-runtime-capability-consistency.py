#!/usr/bin/env python3
"""Native public legacy capability/dispatch consistency (no primitive mocks)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'scripts/context-runtime-rollout.py'
sys.dont_write_bytecode = True


def inventory(root):
    """No-follow inventory including empty directories and relevant metadata."""
    result = {}
    def visit(path):
        meta = path.lstat()
        kind = stat.S_IFMT(meta.st_mode)
        result[str(path.relative_to(root))] = (
            kind, stat.S_IMODE(meta.st_mode), meta.st_dev, meta.st_ino,
            meta.st_nlink, meta.st_size, meta.st_mtime_ns, meta.st_ctime_ns,
            os.readlink(path) if stat.S_ISLNK(meta.st_mode) else
            hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(meta.st_mode) else None)
        if stat.S_ISDIR(meta.st_mode):
            for child in sorted(path.iterdir()):
                visit(child)
    visit(root)
    return result


class CapabilityConsistency(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mana-capability-')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve()
        self.env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        # Use the interpreter whose native platform is being tested in Bash too.
        self.env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + self.env['PATH']
        for key in ('MANA_CONTEXT_RUNTIME_VERSION', 'MANA_CONTEXT_MANIFEST'):
            self.env.pop(key, None)
        self.bash = shutil.which('bash')
        self.assertIsNotNone(self.bash, 'public runner requires Bash')
        (self.project / 'sentinel').write_bytes(b'unchanged')
        (self.project / 'empty-directory').mkdir()

    def policy(self, mode):
        if mode is None:
            return
        path = self.project / '.mana/context-runtime/runtime-selection-v1.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        selection = {'mode': mode}
        if mode == 'v2':
            selection['failClosed'] = True
        path.write_text(json.dumps({'schemaVersion': 'mana.context-runtime.rollout-policy/v1',
                                   'defaultMode': 'legacy', 'profiles': {'mana-help': selection}}))
        if os.name == 'posix':
            path.chmod(0o600)

    def command(self, args):
        print(json.dumps({'starting': [str(x) for x in args]}), flush=True)
        result = subprocess.run(args, cwd=ROOT, env=self.env, text=True,
                                capture_output=True, timeout=60)
        print(json.dumps({'nativePlatform': os.name, 'command': [str(x) for x in args],
                          'exit': result.returncode, 'stdout': result.stdout,
                          'stderr': result.stderr}), flush=True)
        return result

    def cli(self, command, *args):
        return self.command([sys.executable, str(TOOL), command,
                             '--project-root', str(self.project), *args])

    def status(self):
        result = self.cli('status')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def assert_denial(self, result):
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertRegex(result.stderr, r'^ERROR: context runtime unavailable: [^\r\n]+\n$')
        self.assertNotIn('Traceback', result.stderr)
        self.assertNotIn(str(self.project), result.stderr)

    @unittest.skipUnless(os.name == 'nt', 'native Windows only')
    def test_windows_declared_unavailable_matches_public_denial_without_effects(self):
        for mode in (None, 'legacy', 'v2'):
            with self.subTest(policy=mode):
                self.policy(mode)
                before = inventory(self.project)
                view = self.status()
                self.assertFalse(view['legacyAvailable'])
                self.assertFalse(view['v2Available'])
                self.assertEqual(view['policy'], 'unavailable')
                for command in ('candidate', 'legacy-execution-identity'):
                    self.assert_denial(self.cli(command, '--profile', 'mana-help'))
                # Actual public runner, explicit legacy and a valid built-in profile.
                self.assert_denial(self.command([
                    self.bash, (ROOT / 'scripts/run-profile.sh').as_posix(), 'mana-help',
                    '--project-root', self.project.as_posix(), '--context-runtime', 'legacy', '--render-only']))
                # Exercise the exact CTX-10 observer block from doctor. Its full
                # tool-readiness checks are outside this runtime regression.
                source = (ROOT / 'scripts/mana-doctor.sh').read_text()
                functions = 'pass() {' + source.split('pass() {', 1)[1].split('\ncheck_file()', 1)[0]
                observer = 'echo "Context runtime rollout (CTX-10 local-only):"' + source.split(
                    'echo "Context runtime rollout (CTX-10 local-only):"', 1)[1].split('\nfor dir in docs ', 1)[0]
                doctor = self.command([self.bash, '-c',
                                       'root=$1; project=$2; errors=0; warnings=0\n' + functions + observer,
                                       'doctor-ctx10-observer', ROOT.as_posix(), self.project.as_posix()])
                self.assertEqual(doctor.returncode, 0)
                self.assertIn('legacy=false v2=false policy=unavailable', doctor.stdout)
                self.assertNotIn('legacy=true', doctor.stdout)
                self.assertEqual(before, inventory(self.project))

    @unittest.skipUnless(os.name == 'posix', 'supported POSIX only')
    def test_posix_missing_and_pinned_policy_allow_public_legacy(self):
        for mode in (None, 'legacy'):
            with self.subTest(policy=mode):
                self.policy(mode)
                view = self.status()
                self.assertTrue(view['legacyAvailable'])
                self.assertEqual(view['policy'], 'missing' if mode is None else 'current')
                preview = self.cli('candidate', '--profile', 'mana-help', '--requested-mode', 'legacy')
                self.assertEqual(preview.returncode, 0)
                self.assertEqual(preview.stderr, '')
                self.assertEqual(json.loads(preview.stdout)['mode'], 'legacy')
                identity = self.cli('legacy-execution-identity', '--profile', 'mana-help')
                self.assertEqual(identity.returncode, 0)
                self.assertEqual(identity.stderr, '')
                self.assertRegex(json.loads(identity.stdout)['executionId'], '^legacy-[a-f0-9]{32}$')
                rendered = self.command([
                    self.bash, (ROOT / 'scripts/run-profile.sh').as_posix(), 'mana-help',
                    '--project-root', self.project.as_posix(), '--context-runtime', 'legacy', '--render-only'])
                self.assertEqual(rendered.returncode, 0, rendered.stderr)
                self.assertTrue(rendered.stdout.strip())
                self.assertNotIn('ERROR:', rendered.stderr)
                self.assertNotIn('Traceback', rendered.stderr)

    @unittest.skipUnless(os.name == 'posix', 'supported POSIX only')
    def test_posix_capability_is_independent_of_selected_v2_policy(self):
        self.policy('v2')
        before = inventory(self.project)
        self.assertTrue(self.status()['legacyAvailable'])
        selected = self.cli('candidate', '--profile', 'mana-help')
        self.assertEqual(selected.returncode, 0)
        self.assertEqual(selected.stderr, '')
        self.assertEqual(json.loads(selected.stdout)['mode'], 'v2')
        conflict = self.cli('candidate', '--profile', 'mana-help', '--requested-mode', 'legacy')
        self.assertEqual(conflict.returncode, 2)
        self.assertEqual(conflict.stdout, '')
        self.assertIn('requested runtime mode conflicts', conflict.stderr)
        self.assertEqual(before, inventory(self.project))


if __name__ == '__main__':
    print(json.dumps({'python': sys.executable, 'version': sys.version, 'osName': os.name}), flush=True)
    unittest.main(verbosity=2)
