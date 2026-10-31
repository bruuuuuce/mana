#!/usr/bin/env python3
"""Offline publication barriers around the real helper; no production test hooks."""
import csv
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/lib/story-start-discovery-receipt.py'
NAMESPACE = '.mana-story-start-discovery'


def load_helper():
    spec = importlib.util.spec_from_file_location('receipt', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_for(path, child=None):
    deadline = time.monotonic() + 30
    while not path.exists():
        if child is not None:
            assert child.poll() is None, 'publisher exited before barrier'
        assert time.monotonic() < deadline, f'barrier timed out: {path.name}'
        time.sleep(0.01)


def publisher(workspace, barrier, run_id, outcome):
    helper = load_helper()
    original_link = helper.os.link

    def held_link(source, destination, **kwargs):
        temporary = workspace / NAMESPACE / source
        final = workspace / NAMESPACE / destination
        assert temporary.is_file() and not final.exists()
        (barrier / 'ready.json').write_text(json.dumps({'temporary': str(temporary), 'final': str(final)}))
        wait_for(barrier / 'release')
        if outcome == 'failure':
            raise OSError('controlled publication failure')
        original_link(source, destination, **kwargs)
        assert temporary.stat().st_ino == final.stat().st_ino
        (barrier / 'linked').touch()
        wait_for(barrier / 'cleanup')

    with patch.object(helper.os, 'link', side_effect=held_link):
        try:
            helper.publish(str(workspace), run_id, 'UNKNOWN_FAILURE', None, 'not_reached')
        except OSError:
            assert outcome == 'failure'
            return
    assert outcome == 'success'


def main(base):
    project = base / 'project'
    cache = base / 'cache'
    env = dict(os.environ, MANA_CACHE_HOME=str(cache), PYTHONDONTWRITEBYTECODE='1')
    matrix = []

    def record(cycle, phase, check, detail):
        matrix.append(dict(cycle=cycle, phase=phase, check=check, result='PASS', detail=detail))
        with (base / 'temporal-visibility-matrix.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['cycle', 'phase', 'check', 'result', 'detail'])
            writer.writeheader()
            writer.writerows(matrix)

    def call(script, args, label, expected=0, cache_override=None):
        command = [str(ROOT / 'scripts' / script), '--project-root', str(project), *args, '--json']
        result = subprocess.run(command, env=env if cache_override is None else {**env, 'MANA_CACHE_HOME': str(cache_override)}, capture_output=True, text=True)
        (base / (label + '.json')).write_text(result.stdout)
        (base / (label + '.stderr')).write_text(result.stderr)
        assert result.returncode == expected, (command, result.returncode, result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    for kind, wid in [('features', 'TEMPORAL'), ('sessions', 'SESSION')]:
        workspace = project / '.mana' / kind / wid
        evidence = workspace / 'evidence'
        evidence.mkdir(parents=True)
        (workspace / 'manifest.yaml').write_text(f'workspace_type: {"feature" if kind == "features" else "session"}\nworkspace_id: {wid}\n')
        for name in ['application-evidence.md', 'story-start-discovery-failure-document.json', '.discovery-receipt-document', '.ordinary.tmp']:
            (evidence / name).write_text('{}\n' if name.endswith('.json') else '# Legitimate application evidence\n')
        similar = workspace / (NAMESPACE + '-application')
        similar.mkdir()
        (similar / 'ordinary.json').write_text('{}\n')
        # Whole namespace exclusion must cover arbitrary descendants, not only known filenames.
        private = workspace / NAMESPACE
        private.mkdir(mode=0o700)
        (private / 'nested').mkdir()
        (private / 'nested/arbitrary.md').write_text('PRIVATE_DIAGNOSTIC_SENTINEL\n')
        # Historical bytes remain intact and excluded without migration writes.
        (evidence / ('story-start-discovery-failure-' + 'e' * 32 + '.json')).write_text('{"executionId":"legacy"}\n')
        (evidence / ('.discovery-receipt-' + 'f' * 32)).write_text('PRIVATE_DIAGNOSTIC_SENTINEL\n')
    global_root = project / '.mana/global'
    global_root.mkdir()
    (global_root / 'architecture.md').write_text('# Temporal positive control\n\nAPPLICATION_KNOWLEDGE_CONTROL\n')
    call('mana-catalog.py', ['build'], 'initial-build')
    call('mana-knowledge.py', ['build'], 'initial-knowledge-build')
    database = next(cache.rglob('*.sqlite3'))

    def paths(database_path=None):
        with closing(sqlite3.connect(database_path or database)) as db:
            return [row[0] for row in db.execute('select path from entries order by path')]

    def readonly_snapshot():
        # SQLite mode=ro may maintain WAL/SHM coordination sidecars. Verify
        # durable database bytes and all canonical files, not reader locks.
        files = [database, *[p for p in project.rglob('*') if p.is_file()]]
        return {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in files}

    def consumers(cycle, phase, temporary, run_id):
        relative = temporary.relative_to(project).as_posix()
        snapshot = readonly_snapshot()
        for name, args in [('artifacts', ['artifacts']), ('snapshot', ['semantic-snapshot', '--include-supporting']),
                           ('evidence', ['work-item', 'feature:TEMPORAL']), ('session', ['work-item', 'session:SESSION']),
                           ('activity', ['activity'])]:
            payload = call('mana-inspect.sh', args, f'{cycle}-{phase}-{name}')
            serialized = json.dumps(payload)
            assert NAMESPACE + '/' not in serialized
            assert '/evidence/.discovery-receipt-' + 'f' * 32 not in serialized
            assert 'story-start-discovery-failure-' + 'e' * 32 not in serialized
            if name in ('artifacts', 'evidence', 'session'):
                assert 'application-evidence.md' in serialized
                assert 'story-start-discovery-failure-document.json' in serialized
            if name == 'artifacts':
                visible = {entry['path'] for entry in payload['artifacts']}
                assert any(p.endswith('/.discovery-receipt-document') for p in visible)
                assert any(p.endswith('/.ordinary.tmp') for p in visible)
                assert any(NAMESPACE + '-application/ordinary.json' in p for p in visible)
        for i, target in enumerate([relative, 'file:' + relative, 'workspace:' + run_id]):
            call('mana-inspect.sh', ['artifact', target], f'{cycle}-{phase}-lookup-{i}', expected=2)
        # The knowledge API has its own allowlisted sources, not the catalog entries table.
        docs = call('mana-knowledge.py', ['documents', '--scope', 'project'], f'{cycle}-{phase}-documents')
        assert docs['index']['freshness'] == 'current'
        assert any(d['source_reference'] == '.mana/global/architecture.md' for d in docs['documents'])
        assert NAMESPACE not in json.dumps(docs)
        search = call('mana-knowledge.py', ['search', '--scope', 'project', '--query', 'PRIVATE_DIAGNOSTIC_SENTINEL'], f'{cycle}-{phase}-search')
        assert search['results'] == []
        doc_id = 'doc_' + hashlib.sha256(('project\0' + relative).encode()).hexdigest()[:24]
        call('mana-knowledge.py', ['document', doc_id], f'{cycle}-{phase}-document', expected=2)
        call('mana-knowledge.py', ['passage', 'psg_' + '0' * 24], f'{cycle}-{phase}-passage', expected=2)
        assert readonly_snapshot() == snapshot, 'read-only consumers modified cache files'
        record(cycle, phase, 'Inspect/lookup/Evidence/Activity/snapshot/knowledge', 'private paths absent; positive controls visible; read-only database and canonical bytes unchanged')

    for index, (kind, wid, outcome) in enumerate([
        ('features', 'TEMPORAL', 'success'), ('features', 'TEMPORAL', 'failure'),
        ('sessions', 'SESSION', 'success'), ('sessions', 'SESSION', 'failure')]):
        cycle = f'{kind}-{outcome}'
        workspace = project / '.mana' / kind / wid
        barrier = base / cycle
        barrier.mkdir()
        run_id = f'{index + 1:032x}'
        # This legacy index predates publication and survives the live build in
        # the separate current cache. Never keep SQLite handles across rebuild.
        legacy_cache = barrier / 'legacy-cache'
        legacy_database = legacy_cache / 'catalogs' / database.name
        legacy_database.parent.mkdir(parents=True)
        orphan = f'.mana/{kind}/{wid}/evidence/.discovery-receipt-' + 'a' * 32
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(legacy_database)) as target:
            source.backup(target)
            row = target.execute('select * from entries limit 1').fetchone()
            target.execute('insert into entries values (' + ','.join('?' * len(row)) + ')', (orphan, *row[1:]))
            target.commit()

        def legacy_status(phase):
            before = legacy_database.read_bytes()
            for command in ['status', 'verify']:
                payload = call('mana-catalog.py', [command], f'{cycle}-{phase}-legacy-{command}', cache_override=legacy_cache)
                assert payload['freshness'] == 'stale' and payload['reason'] == 'path-set-changed'
            # Derived retrieval uses a separate, allowlisted knowledge projection.
            docs = call('mana-knowledge.py', ['documents', '--scope', 'project'], f'{cycle}-{phase}-legacy-documents', cache_override=legacy_cache)
            assert any(d['source_reference'] == '.mana/global/architecture.md' for d in docs['documents'])
            assert not any('/evidence/' in d['source_reference'] or NAMESPACE + '/' in d['source_reference'] for d in docs['documents'])
            search = call('mana-knowledge.py', ['search', '--scope', 'project', '--query', 'PRIVATE_DIAGNOSTIC_SENTINEL'], f'{cycle}-{phase}-legacy-search', cache_override=legacy_cache)
            assert search['results'] == []
            doc_id = 'doc_' + hashlib.sha256(('project\0' + orphan).encode()).hexdigest()[:24]
            call('mana-knowledge.py', ['document', doc_id], f'{cycle}-{phase}-legacy-document', expected=2, cache_override=legacy_cache)
            assert legacy_database.read_bytes() == before
            assert orphan in paths(legacy_database)

        legacy_status('0-before-publication')
        with (barrier / 'publisher.log').open('w') as log:
            child = subprocess.Popen([sys.executable, __file__, '--publisher', str(workspace), str(barrier), run_id, outcome], env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_for(barrier / 'ready.json', child)
                info = json.loads((barrier / 'ready.json').read_text())
                temporary, final = Path(info['temporary']), Path(info['final'])
                assert temporary.exists() and not final.exists()
                assert temporary.stat().st_mode & 0o777 == 0o600
                assert (workspace / NAMESPACE).stat().st_mode & 0o777 == 0o700
                legacy_status('2-staging-present')
                record(cycle, '1-2', 'publication started; staging present', 'final name absent; staging 0600; namespace 0700')
                consumers(cycle, '3', temporary, run_id)
                call('mana-catalog.py', ['build'], f'{cycle}-4-build-during-staging')
                admitted = paths()
                assert not any('/' + NAMESPACE + '/' in p for p in admitted)
                assert not any('/evidence/.discovery-receipt-' + 'f' * 32 in p for p in admitted)
                assert any(p.endswith('/application-evidence.md') for p in admitted)
                assert any(p.endswith('/.ordinary.tmp') for p in admitted)
                record(cycle, '4-5', 'build and direct lookup during staging', 'reserved namespace not admitted; direct path and ID lookup exit 2')
                (barrier / 'release').touch()
                if outcome == 'success':
                    wait_for(barrier / 'linked', child)
                    assert temporary.stat().st_ino == final.stat().st_ino
                    assert json.loads(final.read_text())['executionId'] == run_id
                    consumers(cycle, '6-linked', temporary, run_id)
                    (barrier / 'cleanup').touch()
                assert child.wait(timeout=30) == 0
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
        assert not temporary.exists()
        assert final.exists() == (outcome == 'success')
        assert not list((workspace / NAMESPACE).glob('.discovery-receipt-*'))
        assert call('mana-catalog.py', ['verify'], f'{cycle}-7-verify')['freshness'] == 'current'
        record(cycle, '6-7', 'completion/failure and cleanup', f'{outcome}; temporary removed; completed receipt locally readable only on success')
        legacy_status('8-after-cleanup')
        consumers(cycle, '8-stale', temporary, run_id)
        record(cycle, '8', 'preexisting orphan index', 'same legacy index stale before/during/after publication; no read-only rewrite; private row not served')
        call('mana-catalog.py', ['rebuild'], f'{cycle}-9-rebuild', cache_override=legacy_cache)
        assert orphan not in paths(legacy_database) and paths(legacy_database) == admitted
        assert call('mana-catalog.py', ['status'], f'{cycle}-9-status', cache_override=legacy_cache)['freshness'] == 'current'
        consumers(cycle, '9-final', temporary, run_id)
        record(cycle, '9', 'explicit rebuild comparison', 'orphan removed; exact admitted path set restored; final positive controls visible')
    print('Temporal diagnostic publication tests passed: feature/session, success/failure, live staging and legacy index')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--publisher':
        publisher(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5])
    elif os.environ.get('MANA_DIAGNOSTIC_TEST_OUTPUT'):
        output = Path(os.environ['MANA_DIAGNOSTIC_TEST_OUTPUT'])
        output.mkdir(parents=True, exist_ok=True)
        main(output)
    else:
        with tempfile.TemporaryDirectory(prefix='mana-discovery-temporal-') as directory:
            main(Path(directory))
