#!/usr/bin/env python3
"""Portable receipt paths must preserve replay and interrupted-ACK recovery."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which('bash.exe' if os.name == 'nt' else 'bash')
with tempfile.TemporaryDirectory(prefix='mana-portable-operation-') as temporary:
    project = Path(temporary)
    def invoke(action, fields, extra_env=None, accepted=True):
        arguments = [BASH, str(ROOT/'scripts/mana-human-feedback.sh'), '--project-root', str(project), action, '--json']
        if action == 'operation':
            arguments += ['--operation-id', fields['operationId']]
        else:
            arguments += ['--request-stdin']
        result = subprocess.run(arguments, input=json.dumps(fields).encode(), capture_output=True, timeout=60, env=dict(os.environ, **(extra_env or {})))
        if accepted:
            assert result.returncode == 0, result.stderr.decode()
            return json.loads(result.stdout)
        assert result.returncode != 0, 'injected interruption did not stop the producer'
        return result
    target = dict(artifactId='file:portable.md', artifactRevision='sha256:portable')
    keys = ['comment:1791140989704833', 'reply:portable', 'CON', 'a'+':'*127,
            'operation_'+hashlib.sha256(b'comment:1791140989704833').hexdigest()]
    for ordinal, key in enumerate(keys):
        request = dict(**target, author='Portable fixture', body=f'Portable body {ordinal}', idempotencyKey=key)
        created = invoke('create', request)
        assert invoke('create', request) == created
        status = invoke('operation', dict(operationId=key))
        assert status['status'] == 'persisted' and status['result'] == created
        file = project/'.mana/human-feedback/operations'/('operation~'+hashlib.sha256(key.encode()).hexdigest()+'.json')
        assert file.is_file() and json.loads(file.read_bytes())['operationId'] == key
    storage = project/'.mana/human-feedback'
    assert all(':' not in file.name for file in (storage/'operations').iterdir())
    assert len(list((storage/'threads').glob('thread_*.json'))) == len(keys)
    for boundary in ['MANA_HUMAN_FEEDBACK_TEST_ABORT_AFTER_RECORD','MANA_HUMAN_FEEDBACK_TEST_ABORT_AFTER_CANONICAL_BEFORE_INDEX']:
        key = 'comment:'+boundary
        request = dict(**target, author='Portable fixture', body=boundary, idempotencyKey=key)
        invoke('create', request, {boundary:'1'}, accepted=False)
        (storage/'locks/write.lock').rmdir()
        prepared = invoke('operation', dict(operationId=key))
        assert prepared['status'] == 'outcome_to_verify'
        recovered = invoke('create', request)
        assert recovered == prepared['result'] and invoke('create', request) == recovered
        assert invoke('operation', dict(operationId=key))['status'] == 'persisted'
        entries = [entry for file in (storage/'threads').glob('thread_*.json') for entry in json.loads(file.read_bytes())['entries']]
        assert sum(entry['body'] == boundary for entry in entries) == 1
    if os.name != 'nt':
        key = keys[0]
        current = storage/'operations'/('operation~'+hashlib.sha256(key.encode()).hexdigest()+'.json')
        legacy = storage/'operations'/(key+'.json')
        current.rename(legacy)
        before = {p.name:p.read_bytes() for p in (storage/'operations').iterdir()}
        assert invoke('operation', dict(operationId=key))['status'] == 'persisted'
        invoke('create', dict(**target,author='Portable fixture',body='Portable body 0',idempotencyKey=key))
        assert {p.name:p.read_bytes() for p in (storage/'operations').iterdir()} == before, 'legacy replay wrote state'
        invalid = json.loads(legacy.read_bytes()); invalid['operationId'] = 'other-operation'
        legacy.write_text(json.dumps(invalid))
        invoke('operation', dict(operationId=key), accepted=False)
print('Human Feedback portable operation receipts: PASS')
