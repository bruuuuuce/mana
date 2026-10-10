#!/usr/bin/env python3
"""G00-FIX-01 native platform boundary and real multiprocess lock regressions.

Run unchanged with native Windows Python and with Linux/macOS Python.
Windows publication is intentionally unavailable under the existing CTX-03
contract; it is never exercised through a weaker lock or filesystem fallback.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def load(relative):
    name = 'platform_' + relative.replace('/', '_').replace('-', '_').replace('.', '_')
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = load('scripts/lib/context-runtime.py')
rollout = load('scripts/context-runtime-rollout.py')


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def increment(root, ready, release, results, iterations):
    try:
        ready.set()
        for _ in range(iterations):
            with runtime.stable_file_lock(Path(root), '.mana/counter.lock') as identity:
                if release is not None:
                    results.put(('held', identity))
                    release.wait(20)
                target = Path(root) / 'counter.json'
                previous = runtime.safe_read_bytes(Path("counter.json"), project_root=Path(root))
                value = int(previous)
                time.sleep(.003)
                runtime.atomic_write_bytes(Path(root), 'counter.json', str(value + 1).encode(),
                                           expected_current=previous)
        results.put(('done', iterations))
    except BaseException as error:
        results.put(('error', repr(error)))
        raise


def windows_probe(root, ready, release, results, iterations):
    try:
        ready.set()
        for _ in range(iterations):
            try:
                with runtime.stable_file_lock(Path(root), '.mana/counter.lock'):
                    raise AssertionError('unsupported lock entered its critical section')
            except runtime.PlatformUnavailable:
                pass
            try:
                runtime.atomic_write_bytes(Path(root), 'counter.json', b'changed')
            except runtime.PlatformUnavailable:
                pass
            else:
                raise AssertionError('unsupported publication succeeded')
            view = rollout.inspect(Path(root), 'default', 'execution-residue')
            assert view['artifacts']['status'] == 'unavailable'
            assert view['executionIdentity'] is None
            assert view['guarantees']['writes'] is False
            assert view['profileRuntimeSelection']['policyStatus'] == 'unavailable'
        results.put(('done', iterations))
    except BaseException as error:
        results.put(('error', repr(error)))
        raise


class PlatformBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mana-platform-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.context = multiprocessing.get_context('spawn')
        self.children = []
        self.worker_args = []
        self.addCleanup(self.stop_children)

    def stop_children(self):
        for child in self.children:
            if child.is_alive():
                child.terminate()
            child.join(5)

    def spawn(self, target, *args):
        self.worker_args.append(args)  # Keep spawn synchronization objects alive.
        child = self.context.Process(target=target, args=args)
        child.start()
        self.children.append(child)
        return child

    def test_all_runtime_modules_import_without_posix_import_requirement(self):
        for path in ['scripts/lib/context-phase-runtime.py', 'scripts/lib/context-pipeline.py',
                     'scripts/lib/context-worker-runtime.py', 'scripts/lib/context-budget.py',
                     'scripts/context-runtime-mode.py', 'scripts/context-runtime-live-shadow.py']:
            with self.subTest(path=path):
                load(path)

    def test_structural_validation_remains_available(self):
        fixtures = ROOT / 'tests/fixtures/context-runtime/contracts/valid'
        for kind in ('phase-input', 'phase-checkpoint', 'usage-summary', 'context-manifest'):
            with self.subTest(kind=kind):
                runtime.validate_model(kind, json.loads((fixtures / (kind + '.json')).read_bytes()))

    def test_missing_flock_fails_before_creating_lock_or_entering(self):
        before = snapshot(self.root)
        with mock.patch.object(runtime, 'fcntl', None):
            with self.assertRaisesRegex(runtime.PlatformUnavailable, 'unavailable.*flock'):
                with runtime.stable_file_lock(self.root, '.mana/lock'):
                    self.fail('critical section entered')
            with self.assertRaises(runtime.PlatformUnavailable):
                runtime.lock_exclusive(-1)
        self.assertEqual(before, snapshot(self.root))
        self.assertFalse((self.root / '.mana').exists())

    def test_observer_unavailable_is_not_missing_policy_or_dispatch_fallback(self):
        ctx = rollout._runtime_module()
        with mock.patch.object(ctx, '_require_secure_dir_fd_support',
                               side_effect=ctx.PlatformUnavailable('unavailable')):
            status = rollout.status(self.root)
            self.assertFalse(status['legacyAvailable'])
            self.assertFalse(status['v2Available'])
            view = rollout.inspect(self.root, 'default', 'execution-residue')
            self.assertEqual(view['profileRuntimeSelection']['policyStatus'], 'unavailable')
            self.assertEqual(view['runState']['artifactStatus'], 'unavailable')
            self.assertIsNone(view['executionIdentity'])
            self.assertEqual(view['guarantees']['modelCalls'], 0)
            self.assertFalse(view['guarantees']['writes'])
            for key in ('usage', 'delegation', 'producerReceipt', 'shadowComparison'):
                self.assertEqual(view[key]['status'], 'unavailable')
            with self.assertRaises(ctx.PlatformUnavailable):
                rollout.preview_policy(self.root, 'default')
            with self.assertRaises(rollout.DecisionAuthorityError):
                rollout.resolve(self.root, 'default')
        self.assertFalse((self.root / '.mana').exists())

    @unittest.skipUnless(os.name == 'nt', 'native Windows boundary only')
    def test_windows_concurrent_denial_and_residue_recovery_are_read_only(self):
        (self.root / 'counter.json').write_bytes(b'original')
        residue = self.root / '.mana/runtime/runs/execution-residue'
        residue.mkdir(parents=True)
        (residue / 'run-state-v1.json').write_text('{"status":"completed"}')
        policy = self.root / rollout.POLICY_RELATIVE
        policy.parent.mkdir(parents=True)
        policy.write_text('{"schemaVersion":"mana.context-runtime.rollout-policy/v1",'
                          '"defaultMode":"legacy","profiles":{"default":{"mode":"v2","failClosed":true}}}')
        (policy.parent / '.rollout-publication.lock').write_bytes(b'')
        before = snapshot(self.root)
        results = self.context.Queue()
        children = [self.spawn(windows_probe, str(self.root), self.context.Event(), None, results, 8)
                    for _ in range(4)]
        for child in children:
            child.join(30)
            self.assertEqual(child.exitcode, 0)
        self.assertEqual([results.get(timeout=5) for _ in children], [('done', 8)] * 4)
        self.assertEqual(snapshot(self.root), before)
        status = rollout.status(self.root)
        self.assertEqual(status['policy'], 'unavailable')
        self.assertFalse(status['legacyAvailable'])
        self.assertFalse(status['v2Available'])
        self.assertEqual(snapshot(self.root), before)
        with self.assertRaisesRegex(runtime.PlatformUnavailable, 'unavailable'):
            runtime._require_rename_primitives()
        with self.assertRaises(rollout._runtime_module().PlatformUnavailable):
            rollout.legacy_execution_identity(self.root, 'default')
        self.assertEqual(snapshot(self.root), before)

    @unittest.skipUnless(os.name == 'posix', 'CTX-03 supported POSIX host only')
    def test_multiprocess_mutual_exclusion_and_atomic_counter(self):
        (self.root / 'counter.json').write_bytes(b'0')
        results = self.context.Queue()
        children = [self.spawn(increment, str(self.root), self.context.Event(), None, results, 12)
                    for _ in range(4)]
        for child in children:
            child.join(30)
            self.assertEqual(child.exitcode, 0)
        self.assertEqual([results.get(timeout=5) for _ in children], [('done', 12)] * 4)
        self.assertEqual((self.root / 'counter.json').read_bytes(), b'48')
        lock = self.root / '.mana/counter.lock'
        self.assertEqual(lock.stat().st_size, 0)
        self.assertEqual(lock.stat().st_nlink, 1)
        self.assertEqual(lock.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(os.name == 'posix', 'CTX-03 supported POSIX host only')
    def test_contention_crash_recovery_keeps_stable_inode(self):
        (self.root / 'counter.json').write_bytes(b'0')
        results = self.context.Queue()
        release = self.context.Event()
        holder = self.spawn(increment, str(self.root), self.context.Event(), release, results, 1)
        kind, identity = results.get(timeout=10)
        self.assertEqual(kind, 'held')
        ready = self.context.Event()
        contender = self.spawn(increment, str(self.root), ready, None, results, 1)
        self.assertTrue(ready.wait(10))
        # The contender has announced its attempt, but cannot publish while held.
        time.sleep(.3)
        self.assertTrue(contender.is_alive())
        self.assertEqual((self.root / 'counter.json').read_bytes(), b'0')
        holder.kill()
        holder.join(5)
        self.assertNotEqual(holder.exitcode, 0)
        contender.join(10)
        self.assertEqual(contender.exitcode, 0)
        self.assertEqual(results.get(timeout=5), ('done', 1))
        self.assertEqual((self.root / 'counter.json').read_bytes(), b'1')
        with runtime.stable_file_lock(self.root, '.mana/counter.lock') as recovered:
            self.assertEqual(recovered, identity)
            runtime.atomic_write_bytes(self.root, 'counter.json', b'2', expected_current=b'1')
        self.assertEqual((self.root / 'counter.json').read_bytes(), b'2')


if __name__ == '__main__':
    unittest.main(verbosity=2)
