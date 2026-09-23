#!/usr/bin/env python3
"""Adversarial CTX-09A tests, with exclusively local provider stubs."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
ENTRY = REPO / 'scripts/run-profile.sh'
HELPER = REPO / 'scripts/context-runtime-mode.py'
SPEC = importlib.util.spec_from_file_location('ctx09_test', HELPER)
mode = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mode)
HARNESS_SPEC = importlib.util.spec_from_file_location('ctx09_producers', REPO / 'tests/fixtures/context-runtime/ctx09b-producer-harness.py')
harness = importlib.util.module_from_spec(HARNESS_SPEC)
HARNESS_SPEC.loader.exec_module(harness)


class Modes(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ctx09-tests-', dir='/private/tmp' if sys.platform == 'darwin' else '/tmp')
        self.base = Path(self.temporary.name)
        self.project = self.base / 'project with spaces'
        (self.project / 'artifacts').mkdir(parents=True)
        self.legacy = self.project / 'artifacts/legacy.json'
        self.v2 = self.project / 'artifacts/v2.json'
        self.legacy.write_bytes(b'PROMPT RESPONSE REASONING CREDENTIAL SOURCE DIFF RAW EVIDENCE\n')
        self.v2.write_bytes(b'local v2 fixture\n')
        harness.publish_pair(mode, self.project, 'test', self.legacy.read_bytes(), self.v2.read_bytes(),
                             profile_id='jira-state-audit')
        workspace = self.project / '.mana/sessions/ctx09c-mode-workspace'
        workspace.mkdir(mode=0o700, parents=True)
        (workspace / 'manifest.yaml').write_text(
            'workspace_type: "session"\nworkspace_id: "ctx09c-mode-workspace"\n')
        (self.project / '.mana/active-workspace').write_text('.mana/sessions/ctx09c-mode-workspace\n')
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        (self.bin / 'codex').symlink_to(REPO / 'tests/fixtures/context-runtime/ctx09a-provider-stub.py')
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'], MANA_UPDATE_CHECK='off',
                        MANA_RUNTIME_EXECUTION_ID='execution-ctx09-test', CTX09_ACTION='complete',
                        MANA_UNIVERSAL_CONTEXT_ROOT=str(self.base / 'absent-universal-context'))
        self.env.pop('MANA_CONTEXT_RUNTIME_VERSION', None)
        self.namespace = self.project / mode.NAMESPACE
        self.plan = self.namespace / 'test/mode-plan-v1.json'

    def tearDown(self):
        mode._TEST_HOOK = None
        self.temporary.cleanup()

    def cli(self, *extra, root=None, operation='compare', check=False):
        command = [sys.executable, str(HELPER), operation, '--project-root', str(root or self.project), '--execution-id', 'test']
        if operation == 'compare':
            command += ['--legacy-artifact', 'artifacts/legacy.json', '--v2-artifact', 'artifacts/v2.json',
                        '--profile-id', 'jira-state-audit', '--target-key', 'a' * 64]
        return subprocess.run(command + list(extra), env=self.env, capture_output=True, text=True, check=check)

    def profile(self, selected=None, profile='jira-state-audit', extra=(), project=None, disable_subagents=True):
        command = [str(ENTRY), profile, '--project-root', str(project or self.project), '--codex']
        if disable_subagents:
            command.append('--no-codex-subagents')
        if selected is not None:
            runtime_id = self.env['MANA_RUNTIME_EXECUTION_ID'] if selected == 'shadow' else 'test'
            command += ['--context-runtime', selected, '--runtime-execution-id', runtime_id]
        if selected == 'compare':
            command += ['--comparison-target-key', 'a' * 64]
        return subprocess.run(command + list(extra), env=self.env, capture_output=True, text=True)

    def shadow_registration(self):
        # CTX-09A's registration/containment contract remains independently
        # covered. Public live-shadow now consumes the CTX-09C canonical packet.
        return subprocess.run([sys.executable, str(REPO / 'tests/context-runtime-mode-test-only.py'), 'shadow-run', '--project-root', str(self.project),
            '--execution-id', 'test', '--', str(ENTRY), 'jira-state-audit', '--project-root', str(self.project),
            '--codex', '--no-codex-subagents'], env=self.env, capture_output=True, text=True)

    def no_staging(self, directory=None):
        for path in (directory or self.base).rglob('*'):
            self.assertNotIn('.stage.', path.name, str(path))

    def source(self, path='artifacts/legacy.json'):
        with mode.HostRoot(self.project) as root:
            return mode.project_file(root, path)

    def publish(self):
        with mode.HostRoot(self.project) as root:
            with root.directory_fd(mode.NAMESPACE.split('/'), create=True) as parent:
                mode.publish(root, parent, 'test', {'mode': 'compare'})

    def test_compare_bytes_privacy_canonical_and_determinism(self):
        original = (self.legacy.read_bytes(), self.v2.read_bytes())
        self.cli(check=True)
        raw = self.plan.read_bytes()
        value = json.loads(raw)
        self.assertEqual(value['authority'], 'none')
        self.assertEqual(value['comparison'], 'deferred-ctx-09b')
        for name, body in zip(('legacy', 'v2'), original):
            self.assertEqual(value['artifacts'][name]['path'], f'artifacts/{name}.json')
            self.assertEqual(value['artifacts'][name]['sha256'], hashlib.sha256(body).hexdigest())
            self.assertEqual(value['artifacts'][name]['producerRuntime'], name)
        self.assertEqual((self.legacy.read_bytes(), self.v2.read_bytes()), original)
        self.assertEqual(raw, mode.canonical(value))
        self.assertFalse(set(value) & {'prompt', 'response', 'reasoning', 'environment', 'trace', 'verdict', 'equivalence', 'timestamp'})
        self.assertNotIn(original[0], raw)
        other = self.base / 'other'
        (other / 'artifacts').mkdir(parents=True)
        harness.publish_pair(mode, other, 'test', *original, profile_id='jira-state-audit')
        self.cli(root=other, check=True)
        other_value = json.loads((other / mode.NAMESPACE / 'test/mode-plan-v1.json').read_bytes())
        self.assertNotEqual(value['artifacts']['legacy']['fileInstance'], other_value['artifacts']['legacy']['fileInstance'])
        self.assertEqual(raw, mode.canonical(value))
        self.no_staging()

    def test_unsafe_relative_paths(self):
        for path in (str(self.legacy), '../outside', 'artifacts/../artifacts/legacy.json', './artifacts/legacy.json',
                     'artifacts//legacy.json', 'artifacts\\legacy.json', 'artifacts/legacy.json\n'):
            with self.subTest(path=path), self.assertRaises(mode.runtime.ContractError):
                self.source(path)

    def test_symlinks_special_files_and_hardlinks(self):
        (self.project / 'linked').symlink_to(self.project / 'artifacts', target_is_directory=True)
        (self.project / 'artifacts/link').symlink_to(self.legacy)
        (self.project / 'artifacts/directory').mkdir()
        os.mkfifo(self.project / 'artifacts/fifo')
        for path in ('linked/legacy.json', 'artifacts/link', 'artifacts/directory', 'artifacts/fifo'):
            with self.subTest(path=path), self.assertRaises((mode.runtime.ContractError, OSError)):
                self.source(path)
        os.link(self.legacy, self.project / 'artifacts/hardlink')
        with self.assertRaises(mode.runtime.ContractError):
            self.source()

    def test_root_and_ancestor_symlinks_rejected(self):
        for target in (self.project, self.base):
            alias = self.base / ('project-alias' if target == self.project else 'ancestor-alias')
            alias.symlink_to(target, target_is_directory=True)
            root = alias if target == self.project else alias / self.project.name
            self.assertNotEqual(self.cli(root=root).returncode, 0)
            for selected in ('shadow', 'compare'):
                result = self.profile(selected, project=root,
                    extra=('--legacy-runtime-artifact', 'artifacts/legacy.json', '--v2-runtime-artifact', 'artifacts/v2.json') if selected == 'compare' else ())
                self.assertEqual(result.returncode, 2)
                self.assertNotIn('Starting Codex', result.stdout)
        self.assertFalse(self.namespace.exists())

    def test_source_replacement_and_midread_mutation(self):
        for point in ('source-opened', 'source-chunk-read'):
            self.legacy.write_bytes(b'A' * 150000)
            changed = False
            def mutate(actual):
                nonlocal changed
                if actual == point and not changed:
                    changed = True
                    if point == 'source-opened':
                        self.legacy.unlink()
                        self.legacy.write_bytes(b'REPLACEMENT')
                    else:
                        with self.legacy.open('r+b') as stream:
                            stream.seek(70000)
                            stream.write(b'B' * 50000)
            mode._TEST_HOOK = mutate
            with self.subTest(point=point), self.assertRaises(mode.runtime.ContractError):
                self.source()
        with mock.patch.object(mode, 'MAX_ARTIFACT_BYTES', 4), self.assertRaises(mode.runtime.ContractError):
            self.source()

    def test_source_parent_rebinding(self):
        def mutate(point):
            if point == 'source-opened':
                (self.project / 'artifacts').rename(self.base / 'moved-artifacts')
                (self.project / 'artifacts').symlink_to(self.base / 'moved-artifacts', target_is_directory=True)
        mode._TEST_HOOK = mutate
        with self.assertRaises((mode.runtime.ContractError, OSError)):
            self.source()

    def test_private_permissions_even_under_restrictive_umask(self):
        previous = os.umask(0o777)
        try:
            self.publish()
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(self.plan.stat().st_mode), 0o600)
        for path in (self.namespace, self.plan.parent):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.no_staging()

    def test_existing_insecure_namespace_rejected(self):
        self.namespace.mkdir(parents=True, mode=0o755)
        self.namespace.chmod(0o755)
        self.assertNotEqual(self.cli().returncode, 0)
        self.assertEqual(stat.S_IMODE(self.namespace.stat().st_mode), 0o755)
        self.assertFalse(self.plan.exists())

    def test_namespace_symlinks_and_collisions(self):
        outside = self.base / 'outside'
        outside.mkdir()
        for component in ('.mana', '.mana/runtime', mode.NAMESPACE):
            path = self.project / component
            path.parent.mkdir(parents=True, exist_ok=True)
            saved = self.base / 'saved-component'
            existed = path.exists()
            if existed:
                path.rename(saved)
            path.symlink_to(outside, target_is_directory=True)
            self.assertNotEqual(self.cli().returncode, 0)
            self.assertEqual(list(outside.iterdir()), [])
            path.unlink()
            if existed:
                saved.rename(path)
        self.namespace.mkdir(exist_ok=True, mode=0o700)
        for kind in ('file', 'directory', 'symlink', 'fifo'):
            collision = self.plan.parent
            if kind == 'file': collision.write_bytes(b'preserve')
            elif kind == 'directory': collision.mkdir(mode=0o700)
            elif kind == 'symlink': collision.symlink_to(outside, target_is_directory=True)
            else: os.mkfifo(collision)
            before = collision.lstat()
            self.assertNotEqual(self.cli().returncode, 0)
            self.assertEqual(collision.lstat().st_ino, before.st_ino)
            if kind == 'directory': collision.rmdir()
            else: collision.unlink()
        self.no_staging()

    def test_publication_fault_cleanup(self):
        for point in ('before-stage-write', 'before-publication', 'after-publication', 'before-commit'):
            def fault(actual):
                if actual == point: raise OSError('injected publication failure')
            mode._TEST_HOOK = fault
            with self.subTest(point=point), self.assertRaises(OSError): self.publish()
            self.assertFalse(self.plan.parent.exists())
            self.no_staging()
        mode._TEST_HOOK = None
        for operation in ('canonical',):
            with mock.patch.object(mode, operation, side_effect=ValueError('encoding failure')), self.assertRaises(ValueError):
                self.publish()
            self.assertFalse(self.namespace.exists())
        with mock.patch.object(mode.os, 'write', return_value=0), self.assertRaises(OSError): self.publish()
        self.no_staging()
        with mock.patch.object(mode.os, 'fsync', side_effect=OSError('fsync failure')), self.assertRaises(OSError): self.publish()
        self.no_staging()

    def test_namespace_moved_outside_rolls_back(self):
        for index, point in enumerate(('before-publication', 'after-publication', 'before-commit')):
            outside = self.base / f'moved-{index}'
            def move(actual):
                if actual == point:
                    self.namespace.rename(outside)
                    self.namespace.symlink_to(outside, target_is_directory=True)
            mode._TEST_HOOK = move
            with self.subTest(point=point), self.assertRaises((mode.runtime.ContractError, OSError)): self.publish()
            self.assertEqual(list(outside.iterdir()), [])
            self.namespace.unlink()
            self.no_staging()

    def test_concurrent_collision_has_one_winner(self):
        argv = [sys.executable, str(HELPER), 'compare', '--project-root', str(self.project), '--execution-id', 'test',
                '--profile-id', 'jira-state-audit', '--target-key', 'a' * 64,
                '--legacy-artifact', 'artifacts/legacy.json', '--v2-artifact', 'artifacts/v2.json']
        children = [subprocess.Popen(argv, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
        for child in children: child.communicate(timeout=30)
        self.assertEqual(sorted(child.returncode for child in children), [0, 2, 2, 2])
        self.assertEqual(json.loads(self.plan.read_bytes())['authority'], 'none')
        self.no_staging()

    def test_required_primitives_fail_closed(self):
        for operation in ('_require_secure_dir_fd_support', '_require_rename_primitives'):
            with mock.patch.object(mode.runtime, operation, side_effect=mode.runtime.ContractError('unavailable')), self.assertRaises(mode.runtime.ContractError):
                self.publish()
            self.no_staging()

    def test_handled_publication_signals_cleanup(self):
        for number in (signal.SIGTERM, signal.SIGINT):
            for point in ('before-stage-write', 'after-publication'):
                def interrupt(actual):
                    if actual == point: os.kill(os.getpid(), number)
                mode._TEST_HOOK = interrupt
                with self.subTest(signal=number, point=point), mode.publication_signals(), self.assertRaises(OSError):
                    self.publish()
                self.assertFalse(self.plan.parent.exists())
                self.no_staging()

    def test_staged_payload_tampering_fails_closed(self):
        for action in ('bytes', 'file-mode', 'dir-mode', 'symlink', 'extra-file'):
            def mutate(point):
                if point != 'before-publication': return
                stage = next(self.namespace.glob('.mode-plan.stage.*'))
                path = stage / 'mode-plan-v1.json'
                if action == 'bytes': path.write_bytes(b'INJECTED')
                elif action == 'file-mode': path.chmod(0o644)
                elif action == 'dir-mode': stage.chmod(0o755)
                elif action == 'extra-file': (stage / 'unauthorized').write_bytes(b'RAW EVIDENCE')
                else:
                    path.unlink()
                    path.symlink_to(self.legacy)
            mode._TEST_HOOK = mutate
            with self.subTest(action=action), self.assertRaises(mode.runtime.ContractError): self.publish()
            self.assertFalse(self.plan.parent.exists())
            self.no_staging()
            self.assertIn(b'PROMPT', self.legacy.read_bytes())

    def test_stage_open_failure_cleans_created_entry(self):
        original = mode.HostRoot.open_dir
        def fail(root, name, parent=None):
            if str(name).startswith('.mode-plan.stage.'):
                raise OSError('injected open failure')
            return original(root, name, parent)
        with mock.patch.object(mode.HostRoot, 'open_dir', fail), self.assertRaises(OSError): self.publish()
        self.no_staging()

    def test_compare_never_invokes_legacy_or_v2_provider(self):
        self.env['CTX09_ACTION'] = 'fail'
        result = self.profile('compare', extra=('--legacy-runtime-artifact', 'artifacts/legacy.json', '--v2-runtime-artifact', 'artifacts/v2.json'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Starting Codex', result.stdout)
        self.assertFalse((self.project / '.mana/runtime/metrics').exists())
        self.assertFalse((self.project / '.mana/runtime/runs').exists())

    def test_shadow_handoff_failure_records_are_canonical(self):
        self.cli(operation='shadow', check=True, *('--legacy-exit-status', '23'))
        raw = self.plan.read_bytes()
        value = json.loads(raw)
        self.assertEqual(value['legacyExecution'], {'status': 'failed', 'exitStatus': 23})
        self.assertEqual(raw, mode.canonical(value))
        self.assertEqual(set(value), {'schemaVersion', 'executionId', 'mode', 'authority', 'externalActions', 'permissionGrant',
                                     'comparison', 'v2Execution', 'publication', 'legacyExecution'})
        other = self.base / 'other-shadow'
        other.mkdir()
        self.cli(operation='shadow', root=other, check=True, *('--legacy-exit-status', '23'))
        self.assertEqual(raw, (other / mode.NAMESPACE / 'test/mode-plan-v1.json').read_bytes())

    @unittest.skipUnless(sys.platform == 'darwin', 'positive isolation requires fixed macOS host backend')
    def test_shadow_concurrency_runs_legacy_once(self):
        argv = [sys.executable, str(REPO / 'tests/context-runtime-mode-test-only.py'), 'shadow-run', '--project-root', str(self.project), '--execution-id', 'test',
                '--', str(ENTRY), 'jira-state-audit', '--project-root', str(self.project), '--codex', '--no-codex-subagents']
        children = [subprocess.Popen(argv, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        output = [child.communicate(timeout=30)[0] for child in children]
        self.assertEqual(sorted(child.returncode for child in children), [0, 2])
        self.assertEqual(sum(b'legacy-answer' in value for value in output), 1)
        self.no_staging()

    def test_invalid_execution_identity_and_status_no_writes(self):
        for identity in ('../outside', '/absolute', '.', '..', 'a/b', 'a' * 129):
            result = self.cli('--execution-id', identity)
            self.assertEqual(result.returncode, 2)
        for status in ('-1', '256'):
            self.assertEqual(self.cli('--legacy-exit-status', status, operation='shadow').returncode, 2)
        self.assertFalse(self.namespace.exists())

    def test_default_legacy_output_and_failure_status(self):
        default = self.profile()
        inventory = sorted(str(path.relative_to(self.project)) for path in self.project.rglob('*'))
        explicit = self.profile('legacy')
        self.assertEqual((default.returncode, explicit.returncode), (0, 0), default.stderr + explicit.stderr)
        self.assertEqual(default.stdout, explicit.stdout)
        self.assertEqual(inventory, sorted(str(path.relative_to(self.project)) for path in self.project.rglob('*')))
        self.assertIn('legacy-answer', default.stdout)
        self.assertFalse(self.namespace.exists())
        self.assertFalse((self.project / '.mana/runtime/runs').exists())
        self.env['CTX09_ACTION'] = 'fail'
        self.assertEqual(self.profile().returncode, 23)
        self.assertEqual(self.profile('legacy').returncode, 23)

    @unittest.skipUnless(sys.platform == 'darwin', 'positive isolation requires fixed macOS host backend')
    def test_default_legacy_and_shadow_render_the_same_prompt(self):
        self.env['CTX09_ACTION'] = 'prompt-hash'
        results = [self.profile(), self.profile('legacy'), self.profile('shadow')]
        self.assertEqual([result.returncode for result in results], [0, 0, 0], ''.join(result.stderr for result in results))
        self.assertEqual(results[0].stdout, results[1].stdout)
        self.assertEqual(results[1].stdout, results[2].stdout)

    @unittest.skipUnless(sys.platform == 'darwin', 'positive isolation requires fixed macOS host backend')
    def test_shadow_default_subagents_never_materialize_project_codex_agents(self):
        agents = self.project / '.codex/agents'
        config_capture = self.base / 'provider-config-observed.json'
        self.env['CTX09_CONFIG_CAPTURE'] = str(config_capture)
        self.assertFalse(agents.exists())
        result = self.profile('shadow', disable_subagents=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('legacy-answer', result.stdout)
        self.assertFalse(agents.exists())
        observed = json.loads(config_capture.read_text())
        private_root = Path(observed['codexHome']).parent
        self.assertNotEqual(private_root, self.project)
        self.assertTrue(str(private_root).startswith('/private/tmp/'))
        expected = {'agents/mana-explorer.toml', 'agents/mana-full-specialist.toml', 'agents/mana-worker.toml'}
        self.assertEqual({item['path'] for item in observed['entries'] if item['path'].startswith('agents/')}, expected)
        self.assertTrue(all(item['mode'] == (0o700 if item['type'] == 'directory' else 0o600)
                            and (item['type'] == 'directory' or item['links'] == 1)
                            and not item['symlink'] for item in observed['entries']))
        self.assertFalse(private_root.exists())

        agents.mkdir(parents=True)
        user_owned = agents / 'user-owned.toml'
        user_owned.write_bytes(b'user-owned\n')
        managed = agents / 'mana-worker.toml'
        managed.write_bytes(b'# Mana-managed Codex custom agent\npreexisting\n')
        before = {path.name: (path.lstat().st_mode, path.lstat().st_ino,
                              hashlib.sha256(path.read_bytes()).hexdigest())
                  for path in agents.iterdir()}
        self.env['MANA_RUNTIME_EXECUTION_ID'] = 'execution-ctx09-default-config-existing'
        result = self.profile('shadow', disable_subagents=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {path.name: (path.lstat().st_mode, path.lstat().st_ino,
                             hashlib.sha256(path.read_bytes()).hexdigest())
                 for path in agents.iterdir()}
        self.assertEqual(before, after)

    @unittest.skipUnless(sys.platform == 'darwin', 'positive isolation requires fixed macOS host backend')
    def test_shadow_provider_config_failures_signals_and_crash_clean_up(self):
        capture = self.base / 'provider-config-lifecycle.json'
        project_agents = self.project / '.codex/agents'
        # Exact legacy outcomes remain caller-visible while every private
        # provider-config root is reclaimed. Actual process-tree timeout
        # supervision is exercised by context-runtime-live-shadow.py.
        for ordinal, (action, expected) in enumerate((('sleep', 2), ('fail', 23), ('sigint', 0),
                                                      ('sigterm', 143), ('crash', 137))):
            with self.subTest(action=action):
                capture.unlink(missing_ok=True)
                env = dict(self.env, CTX09_ACTION=action, CTX09_CONFIG_CAPTURE=str(capture),
                           MANA_CTX09C_LEGACY_TIMEOUT_SECONDS='1',
                           MANA_CTX09C_SHADOW_TIMEOUT_SECONDS='1',
                           MANA_CTX09C_KILL_GRACE_SECONDS='1',
                           MANA_RUNTIME_EXECUTION_ID=f'execution-ctx09-config-lifecycle-{ordinal}')
                command = [str(ENTRY), 'jira-state-audit', '--project-root', str(self.project),
                           '--codex', '--context-runtime', 'shadow', '--runtime-execution-id',
                           env['MANA_RUNTIME_EXECUTION_ID']]
                result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, expected, result.stderr)
                private_root = Path(json.loads(capture.read_text())['codexHome']).parent
                self.assertFalse(private_root.exists())
                self.assertFalse(project_agents.exists())

        mktemp = self.bin / 'mktemp'
        mktemp.write_text('#!/bin/sh\ncase "$*" in *mana-shadow-provider-config*) exit 73;; esac\nexec /usr/bin/mktemp "$@"\n')
        mktemp.chmod(0o700)
        capture.unlink(missing_ok=True)
        env = dict(self.env, CTX09_CONFIG_CAPTURE=str(capture),
                   MANA_RUNTIME_EXECUTION_ID='execution-ctx09-config-setup-failure')
        result = subprocess.run([str(ENTRY), 'jira-state-audit', '--project-root', str(self.project),
            '--codex', '--context-runtime', 'shadow', '--runtime-execution-id',
            env['MANA_RUNTIME_EXECUTION_ID']], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('shadow unavailable: private provider configuration could not be created', result.stderr)
        self.assertFalse(capture.exists())
        self.assertFalse(project_agents.exists())

    @unittest.skipUnless(sys.platform == 'darwin', 'positive isolation requires fixed macOS host backend')
    def test_shadow_ignores_project_provider_config_symlink_and_outside_sentinel(self):
        outside = self.base / 'outside-provider-config'
        outside.mkdir()
        sentinel = outside / 'sentinel'
        sentinel.write_bytes(b'outside-sentinel\n')
        project_config = self.project / '.codex'
        project_config.symlink_to(outside, target_is_directory=True)
        before = (project_config.lstat().st_mode, project_config.lstat().st_ino,
                  os.readlink(project_config), sentinel.lstat().st_mode,
                  sentinel.lstat().st_ino, hashlib.sha256(sentinel.read_bytes()).hexdigest())
        result = self.profile('shadow', disable_subagents=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = (project_config.lstat().st_mode, project_config.lstat().st_ino,
                 os.readlink(project_config), sentinel.lstat().st_mode,
                 sentinel.lstat().st_ino, hashlib.sha256(sentinel.read_bytes()).hexdigest())
        self.assertEqual(before, after)
        self.assertFalse((outside / 'agents').exists())

    @unittest.skipUnless(sys.platform == 'darwin', 'positive isolation requires fixed macOS host backend')
    def test_shadow_claude_and_opencode_leave_project_config_unchanged(self):
        cases = (('claude', '.claude/agents', '--claude', 'CLAUDE_CONFIG_DIR'),
                 ('opencode', '.opencode/agents', '--opencode', 'OPENCODE_CONFIG_DIR'))
        for provider, relative, flag, env_name in cases:
            with self.subTest(provider=provider):
                executable = self.bin / provider
                executable.symlink_to(REPO / 'tests/fixtures/context-runtime/ctx09a-provider-stub.py')
                config = self.project / relative
                config.mkdir(parents=True, exist_ok=True)
                owned = config / 'user-owned.md'
                owned.write_bytes((provider + '-user-owned\n').encode())
                before = (owned.lstat().st_mode, owned.lstat().st_ino,
                          hashlib.sha256(owned.read_bytes()).hexdigest())
                capture = self.base / f'{provider}-config-observed.json'
                env = dict(self.env, MANA_RUNTIME_EXECUTION_ID=f'execution-ctx09-{provider}-private-config',
                           CTX09_CONFIG_CAPTURE=str(capture))
                result = subprocess.run([str(ENTRY), 'jira-state-audit', '--project-root', str(self.project),
                    flag, '--context-runtime', 'shadow', '--runtime-execution-id',
                    env['MANA_RUNTIME_EXECUTION_ID']], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                observed = json.loads(capture.read_text())
                private_config = Path(observed['configDirs'][env_name])
                self.assertNotEqual(private_config, self.project / relative.split('/')[0])
                self.assertTrue(str(private_config).startswith('/private/tmp/'))
                expected = ({'agents/mana-orchestrator.md', 'agents/mana-explorer.md',
                             'agents/mana-full-specialist.md', 'agents/mana-worker.md'}
                            if provider == 'claude' else
                            {'agents/mana_orchestrator.md', 'agents/mana_explorer.md',
                             'agents/mana_full_specialist.md', 'agents/mana_worker.md'})
                entries = observed['configTrees'][env_name]
                self.assertEqual({item['path'] for item in entries if item['type'] == 'file'}, expected)
                self.assertTrue(all(item['mode'] == (0o700 if item['type'] == 'directory' else 0o600)
                                    and (item['type'] == 'directory' or item['links'] == 1)
                                    and not item['symlink'] for item in entries))
                self.assertFalse(private_config.parent.exists())
                after = (owned.lstat().st_mode, owned.lstat().st_ino,
                         hashlib.sha256(owned.read_bytes()).hexdigest())
                self.assertEqual(before, after)

    def test_mode_environment_has_no_authority_and_v2_no_fallback(self):
        for selected in ('legacy', 'v2', 'shadow', 'compare', 'UNKNOWN', ''):
            self.env['MANA_CONTEXT_RUNTIME_VERSION'] = selected
            with self.subTest(selected=selected): self.assertEqual(self.profile().returncode, 2)
        self.env.pop('MANA_CONTEXT_RUNTIME_VERSION')
        self.assertEqual(self.profile('UNKNOWN').returncode, 2)
        result = self.profile('v2')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('legacy-answer', result.stdout)
        self.assertFalse(self.plan.exists())

    def test_shadow_rejects_undeclared_mutating_publish_and_discovery(self):
        for profile, extra in (('mana-help', ()), ('api-test-validation', ()),
                               ('requested-pr-review', ('--pr', '1', '--publish-high-risk-comments')),
                               ('jira-state-audit', ('--service-discovery-approved',))):
            result = self.profile('shadow', profile=profile, extra=extra)
            with self.subTest(profile=profile, extra=extra):
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn('Starting Codex', result.stdout)
                self.assertFalse(self.plan.exists())

    @unittest.skipUnless(sys.platform == 'darwin', 'positive isolation requires fixed macOS host backend')
    def test_shadow_authoritative_output_failure_and_collision(self):
        legacy = self.profile('legacy')
        self.env['MANA_UPDATE_CHECK'] = 'INVALID-DO-NOT-CONTACT-REMOTE'
        shadow = self.shadow_registration()
        self.assertEqual(shadow.returncode, 0, shadow.stderr)
        self.assertEqual(shadow.stdout, legacy.stdout)
        value = json.loads(self.plan.read_bytes())
        self.assertEqual(value['legacyExecution'], {'status': 'completed', 'exitStatus': 0})
        self.assertEqual(value['v2Execution'], 'deferred-ctx-09c')
        self.assertFalse((self.project / '.mana/runtime/runs').exists())
        collision = self.shadow_registration()
        self.assertEqual(collision.returncode, 2)
        self.assertNotIn('Starting Codex', collision.stdout)
        self.plan.unlink()
        self.plan.parent.rmdir()
        self.env['CTX09_ACTION'] = 'fail'
        failed = self.shadow_registration()
        self.assertEqual(failed.returncode, 23, failed.stderr)
        self.assertEqual(json.loads(self.plan.read_bytes())['legacyExecution'], {'status': 'failed', 'exitStatus': 23})
        self.no_staging()

    @unittest.skipUnless(sys.platform == 'darwin', 'positive isolation requires fixed macOS host backend')
    def test_shadow_denies_application_writes_and_local_network(self):
        protected = [self.legacy, self.project / '.git/HEAD', self.project / '.mana/runtime/runs/execution-ctx09-test/run-state.json',
                     self.project / '.mana/approvals/approval.json', self.base / 'outside-sentinel']
        for path in protected:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'UNCHANGED')
        metrics_alias = self.project / '.mana/runtime/metrics/escape-symlink'
        metrics_alias.parent.mkdir(exist_ok=True)
        metrics_alias.symlink_to(protected[1])
        protected.append(metrics_alias)
        self.env.update(CTX09_ACTION='attack', CTX09_DENIED_PATHS=json.dumps([str(path) for path in protected]))
        result = self.shadow_registration()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(json.dumps({'blocked': [True] * 8}), result.stdout)
        for path in protected: self.assertEqual(path.read_bytes(), b'UNCHANGED', str(path))
        self.assertNotIn(b'UNCHANGED', self.plan.read_bytes())
        self.no_staging()

    @unittest.skipUnless(sys.platform == 'darwin', 'positive isolation requires fixed macOS host backend')
    def test_provider_output_cannot_change_shadow_authority(self):
        self.env['CTX09_ACTION'] = 'mode-output'
        result = self.shadow_registration()
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(self.plan.read_bytes())
        self.assertEqual((value['mode'], value['authority']), ('shadow', 'legacy'))
        self.assertFalse((self.project / '.mana/runtime/runs').exists())

    def test_handoff_failure_does_not_change_legacy_exit_status(self):
        argv = [str(HELPER), 'shadow-run', '--project-root', str(self.project), '--execution-id', 'test', '--', str(ENTRY)]
        for status in (0, 23):
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(mode, 'shadow_legacy', return_value=status), \
                 mock.patch.object(mode, 'publish', side_effect=mode.runtime.ContractError('injected')), contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(mode.main(), status)
                self.assertEqual(json.loads(error.getvalue())['handOff'], 'failed')
            self.assertFalse(self.plan.exists())
            self.no_staging()

    def test_shadow_without_enforced_backend_fails_before_execution(self):
        with mode.HostRoot(self.project) as root, mock.patch.object(sys, 'platform', 'unsupported'), self.assertRaises(mode.runtime.ContractError):
            mode.shadow_legacy(root, [str(ENTRY)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
