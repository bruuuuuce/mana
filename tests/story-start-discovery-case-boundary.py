#!/usr/bin/env python3
"""Native filesystem admission and read-boundary regression for Discovery receipts."""
from contextlib import closing
import csv
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/lib/story-start-discovery-receipt.py'
NAMESPACE = '.mana-story-start-discovery'


def main(base):
    base.mkdir(parents=True, exist_ok=True)
    probe = base / 'volume-probe'
    probe.mkdir()
    first = probe / 'NativeObject'
    first.write_text('isolated native filesystem probe\n')
    alias = probe / 'nATIVEoBJECT'
    insensitive = alias.exists() and os.path.samefile(first, alias)
    device = first.stat().st_dev
    matrix = []
    (base / 'probe.json').write_text(json.dumps({'case_insensitive': insensitive, 'device': device,
        'first_inode': first.stat().st_ino, 'alias_inode': alias.stat().st_ino if alias.exists() else None,
        'same_object': insensitive}, indent=2))
    legacy_script = base / 'baseline-catalog.py'
    legacy_script.write_bytes(subprocess.check_output(['git', 'show',
        '333670bcd18dc33f5fbd3d088b18b7c8dbfa9cd8:scripts/mana-catalog.py'], cwd=ROOT))

    def record(case, check, detail):
        matrix.append({'filesystem': 'case-insensitive' if insensitive else 'case-sensitive',
                       'case': case, 'check': check, 'result': 'PASS', 'detail': detail})
        with (base / 'case-sensitivity-matrix.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['filesystem', 'case', 'check', 'result', 'detail'])
            writer.writeheader()
            writer.writerows(matrix)

    def snapshot(directory):
        paths = [directory, *directory.rglob('*')]
        return {str(p.relative_to(directory)): (p.lstat().st_mode, p.lstat().st_ino,
                p.lstat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else None)
                for p in paths}

    for index, (case, mana_name, collection, namespace) in enumerate([
        ('canonical-feature', '.mana', 'features', NAMESPACE),
        ('canonical-session', '.mana', 'sessions', NAMESPACE),
        ('namespace-alias', '.mana', 'features', NAMESPACE.upper()),
        ('collection-alias', '.mana', 'Features', NAMESPACE),
        ('mana-alias', '.MANA', 'features', NAMESPACE),
    ]):
        directory = base / case
        project = directory / 'project'
        workspace = project / mana_name / collection / 'MiXeD'
        evidence = workspace / 'evidence'
        evidence.mkdir(parents=True)
        assert workspace.stat().st_dev == device, 'probe and test project must share a filesystem'
        kind = 'session' if collection == 'sessions' else 'feature'
        (workspace / 'manifest.yaml').write_text(f'workspace_type: {kind}\nworkspace_id: MiXeD\n')
        (evidence / 'application-evidence.md').write_text('# Legitimate evidence\n')
        (evidence / 'story-start-discovery-failure-document.json').write_text('{"executionId":"MiXeD-Application-ID"}\n')
        (evidence / '.discovery-receipt-document').write_text('ordinary similar file\n')
        (evidence / '.ordinary.tmp').write_text('ordinary hidden file\n')
        similar = workspace / (NAMESPACE.upper() + '-application')
        similar.mkdir()
        (similar / 'ordinary.json').write_text('{}\n')
        private = workspace / namespace
        private.mkdir(mode=0o700)
        history_id = f'{index + 10:032x}'
        history = private / ('story-start-discovery-failure-' + history_id + '.json')
        history.write_text(json.dumps({'executionId': history_id, 'schemaVersion': 'private-test'}))
        staging = private / ('.discovery-receipt-' + 'a' * 32)
        staging.write_text('synthetic previous staging\n')
        (private / 'nested').mkdir()
        (private / 'nested/arbitrary.md').write_text('private nested diagnostic\n')
        env = dict(os.environ, MANA_CACHE_HOME=str(directory / 'cache'), PYTHONDONTWRITEBYTECODE='1')
        before = snapshot(workspace)
        run_id = secrets.token_hex(16)
        publication = subprocess.run([sys.executable, str(HELPER), 'publish', '-', str(workspace),
            run_id, 'not_reached', 'UNKNOWN_FAILURE'], env=env, capture_output=True, text=True)
        (directory / 'publication.stderr').write_text(publication.stderr)
        canonical = case.startswith('canonical')
        assert publication.returncode == (0 if canonical else 1), publication.stderr
        final = private / ('story-start-discovery-failure-' + run_id + '.json')
        if canonical:
            assert final.is_file() and final.stat().st_mode & 0o777 == 0o600
            assert json.loads(final.read_text())['executionId'] == run_id
            assert [p.name for p in private.glob('.discovery-receipt-*')] == [staging.name]
        else:
            assert snapshot(workspace) == before, 'failed admission changed preexisting directory'
            assert not final.exists()
            # Also reject a canonical-spelled path that resolves to the same aliases natively.
            requested = project / '.mana' / 'features' / 'MiXeD'
            if requested.exists():
                assert os.path.samefile(requested, workspace)
                again = subprocess.run([sys.executable, str(HELPER), 'publish', '-', str(requested),
                    secrets.token_hex(16), 'not_reached', 'UNKNOWN_FAILURE'], env=env, capture_output=True)
                assert again.returncode == 1 and snapshot(workspace) == before
        record(case, 'publisher', 'canonical receipt 0600 and readable' if canonical else 'controlled rejection; inode/mode/mtime/content unchanged; no new staging')

        def call(script, args, label, expected=0):
            command = ['bash' if script.endswith('.sh') else sys.executable, str(ROOT / 'scripts' / script),
                       '--project-root', str(project), *args, '--json']
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            (directory / (label + '.json')).write_text(result.stdout)
            (directory / (label + '.stderr')).write_text(result.stderr)
            assert result.returncode == expected, (command, result.returncode, result.stderr)
            return json.loads(result.stdout) if result.stdout else None

        forbidden = [p.relative_to(project).as_posix() for p in private.rglob('*') if p.is_file()]

        def readers(phase):
            for name, args in [('artifacts', ['artifacts']), ('evidence', ['work-item', kind + ':MiXeD']),
                               ('snapshot', ['semantic-snapshot', '--include-supporting']), ('activity', ['activity'])]:
                payload = call('mana-inspect.sh', args, phase + '-' + name)
                text = json.dumps(payload)
                assert all(p not in text for p in forbidden)
                assert staging.name not in text and history.name not in text and 'nested/arbitrary.md' not in text
                if name == 'evidence' and mana_name == '.mana' and collection == collection.lower():
                    assert 'application-evidence.md' in text and 'story-start-discovery-failure-document.json' in text
                if name == 'artifacts':
                    admitted = [entry['path'] for entry in payload['artifacts']]
                    for filename in ['application-evidence.md', 'story-start-discovery-failure-document.json', '.discovery-receipt-document', '.ordinary.tmp']:
                        assert any(p.endswith('/' + filename) for p in admitted)
                    assert any(NAMESPACE.upper() + '-application/ordinary.json' in p for p in admitted)
            # Exact opaque IDs retain their case; no global ID normalization.
            if collection == collection.lower() and mana_name == '.mana':
                payload = call('mana-inspect.sh', ['artifact', 'workspace:MiXeD-Application-ID'], phase + '-legitimate-id')
                assert payload['artifact']['artifact_id'] == 'workspace:MiXeD-Application-ID'
                call('mana-inspect.sh', ['artifact', 'workspace:mixed-application-id'], phase + '-wrong-id-case', expected=2)
            for number, target in enumerate([staging.relative_to(project).as_posix(),
                    'file:' + staging.relative_to(project).as_posix(), history.relative_to(project).as_posix(),
                    'workspace:' + history_id, 'workspace:' + run_id]):
                call('mana-inspect.sh', ['artifact', target], phase + '-lookup-' + str(number), expected=2)
            call('mana-inspect.sh', ['source', staging.relative_to(project).as_posix()], phase + '-source', expected=2)

        # Actual baseline builder contaminates the index with the files that still exist.
        result = subprocess.run([sys.executable, str(legacy_script), '--project-root', str(project), 'build', '--json'],
                                env=env, capture_output=True, text=True)
        assert result.returncode == 0
        (directory / 'legacy-build.json').write_text(result.stdout)
        database = next((directory / 'cache').rglob('*.sqlite3'))
        with closing(sqlite3.connect(database)) as db:
            old_paths = [row[0] for row in db.execute('select path from entries')]
        assert any(p.casefold() == staging.relative_to(project).as_posix().casefold() for p in old_paths)
        db_before = database.read_bytes()
        files_before = snapshot(workspace)
        for command in ['status', 'verify']:
            state = call('mana-catalog.py', [command], 'legacy-' + command)
            assert state['freshness'] == 'stale' and state['reason'] == 'path-set-changed'
        readers('stale')
        assert database.read_bytes() == db_before and snapshot(workspace) == files_before
        record(case, 'legacy-readers', 'real baseline index stale; private lookup rejected; persistent database and evidence unchanged')
        call('mana-catalog.py', ['rebuild'], 'rebuild')
        state = call('mana-catalog.py', ['status'], 'rebuilt-status')
        assert state['freshness'] == 'current'
        with closing(sqlite3.connect(database)) as db:
            paths = [row[0] for row in db.execute('select path from entries')]
        assert not set(forbidden).intersection(paths)
        assert not any('/' + NAMESPACE + '/' in p.casefold() for p in paths)
        assert any(p.endswith('/application-evidence.md') for p in paths)
        assert any(p.endswith('/.ordinary.tmp') for p in paths)
        assert any(p.endswith('/story-start-discovery-failure-document.json') for p in paths)
        assert any(NAMESPACE.upper() + '-application/ordinary.json' in p for p in paths)
        readers('rebuilt')
        record(case, 'rebuild', 'current index contains only admitted paths; similar names and application evidence preserved')

    print('Native Discovery boundary tests passed on ' + ('case-insensitive' if insensitive else 'case-sensitive') + ' filesystem')


if __name__ == '__main__':
    output = os.environ.get('MANA_DIAGNOSTIC_CASE_OUTPUT')
    if output:
        main(Path(output))
    else:
        with tempfile.TemporaryDirectory(prefix='mana-discovery-case-') as directory:
            main(Path(directory))
