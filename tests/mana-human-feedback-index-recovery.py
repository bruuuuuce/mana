#!/usr/bin/env python3
"""Crash recovery rebuilds a dense synthetic cache within the consumer timeout."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which('bash.exe' if os.name == 'nt' else 'bash')
with tempfile.TemporaryDirectory(prefix='mana-index-recovery-') as temporary:
    project = Path(temporary)
    def run(fields, env=None):
        return subprocess.run([BASH, str(ROOT/'scripts/mana-human-feedback.sh'), '--project-root', str(project), 'create', '--request-stdin', '--json'], input=json.dumps(fields).encode(), capture_output=True, timeout=30, env=env)
    request = dict(artifactId='file:dense.md', artifactRevision='sha256:dense', author='Synthetic recovery', body='Dense recovery comment', idempotencyKey='dense-seed')
    seed = run(request); assert seed.returncode == 0, seed.stderr
    storage = project/'.mana/human-feedback'
    threads = storage/'threads'; indexes = storage/'indexes'
    original = json.loads(next(threads.glob('*.json')).read_bytes())
    # This is a deliberately synthetic density fixture, not 240 public writes.
    for ordinal in range(240):
        record = json.loads(json.dumps(original))
        record['threadId'] = 'thread_'+hashlib.sha256(str(ordinal).encode()).hexdigest()
        record['target']['artifactRevision'] = 'sha256:revision-'+str(ordinal % 6)
        record['target']['sectionId'] = None if ordinal % 2 else 'synthetic-section'
        record['entries'][0]['entryId'] = 'entry_'+hashlib.sha256(('entry-'+str(ordinal)).encode()).hexdigest()
        record['entries'][0]['body'] = 'Synthetic record '+str(ordinal)+'\n'+'x'*60000
        (threads/(record['threadId']+'.json')).write_text(json.dumps(record))
    request.update(idempotencyKey='dense-recovery', body='Recover exactly once')
    crash = run(request, dict(os.environ, MANA_HUMAN_FEEDBACK_TEST_ABORT_AFTER_CANONICAL_BEFORE_INDEX='1'))
    assert crash.returncode != 0
    (storage/'locks/write.lock').rmdir()
    assert not (indexes/'.target-index-v1-ready.json').exists()
    canonical = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in threads.glob('*.json')}
    started = time.monotonic(); recovered = run(request); elapsed = time.monotonic()-started
    assert recovered.returncode == 0, recovered.stderr.decode()
    result = json.loads(recovered.stdout)
    assert result['threadRevision'] == '1'
    assert canonical == {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in threads.glob('*.json')}
    expected = {}
    for p in threads.glob('*.json'):
        record = json.loads(p.read_bytes()); target = record['target']
        key = (target['artifactId'], target['artifactRevision'], target['sectionId'])
        expected.setdefault(key, []).append(record['threadId'])
    seen = {}
    for p in indexes.glob('target_*.json'):
        record = json.loads(p.read_bytes()); target = record['target']
        seen[(target['artifactId'], target['artifactRevision'], target['sectionId'])] = record['threadIds']
    assert seen == {key:sorted(ids) for key,ids in expected.items()}
    assert (indexes/'.target-index-v1-ready.json').exists()
    assert run(request).stdout == recovered.stdout
    # A bad canonical record must fail before replacing any target index.
    (indexes/'.target-index-v1-ready.json').unlink()
    bad = next(threads.glob('*.json')); record = json.loads(bad.read_bytes()); record['revision']='invalid'; bad.write_text(json.dumps(record))
    unchanged = {p.name:p.read_bytes() for p in indexes.glob('target_*.json')}
    rejected = run(dict(request, idempotencyKey='rejected-recovery'))
    assert rejected.returncode != 0 and b'malformed thread record' in rejected.stderr
    assert unchanged == {p.name:p.read_bytes() for p in indexes.glob('target_*.json')}
    assert not (indexes/'.target-index-v1-ready.json').exists()
    print(json.dumps(dict(status='passed', syntheticCanonicalThreads=len(canonical), targets=len(expected), recoverySeconds=elapsed, timeoutSeconds=30)))
