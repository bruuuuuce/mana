#!/usr/bin/env python3
"""Native Windows jq output translation must not change request strings."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='mana-feedback-line-endings-') as temporary:
    root = Path(temporary)
    binary = root / 'bin'
    binary.mkdir()
    jq = binary / 'jq'
    jq.write_text('''#!/usr/bin/env python3
import subprocess, sys
args = sys.argv[1:]
binary = '--binary' in args
args = [value for value in args if value != '--binary']
result = subprocess.run([REAL_JQ, *args], input=sys.stdin.buffer.read(), capture_output=True)
sys.stdout.buffer.write(result.stdout if binary else result.stdout.replace(b'\\n', b'\\r\\n'))
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
'''.replace('REAL_JQ', repr(shutil.which('jq'))))
    jq.chmod(0o755)
    project = root / 'project'
    project.mkdir()
    env = dict(os.environ, OS='Windows_NT', PATH=str(binary) + os.pathsep + os.environ['PATH'])
    body = 'Prima riga: è 👩🏽‍💻\nSeconda riga\r\nTerza riga\n\n'
    author = 'Ada è 👩🏽‍💻'
    def invoke(action, fields):
        result = subprocess.run([str(ROOT / 'scripts/mana-human-feedback.sh'), '--project-root', str(project), action, '--request-stdin', '--json'], input=json.dumps(fields).encode(), capture_output=True, env=env)
        assert result.returncode == 0, result.stderr.decode()
        return json.loads(result.stdout)
    request = dict(artifactId='file:report.md', artifactRevision='sha256:test', author=author, body=body, idempotencyKey='line-endings-create')
    created = invoke('create', request)
    assert invoke('create', request) == created
    replied = invoke('reply', dict(threadId=created['threadId'], threadRevision=created['threadRevision'], author=author, body=body, idempotencyKey='line-endings-reply'))
    record = json.loads((project / '.mana/human-feedback/threads' / (created['threadId'] + '.json')).read_bytes())
    assert replied['threadRevision'] == '2'
    assert len(record['entries']) == 2
    for entry in record['entries']:
        assert entry['author'] == author
        assert entry['body'].encode() == body.encode(), repr(entry['body'])
print('Human Feedback Windows line endings: PASS')
