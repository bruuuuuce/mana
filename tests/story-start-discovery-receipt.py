#!/usr/bin/env python3
"""Offline receipt classification, privacy and publication tests."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
helper = root / 'scripts/lib/story-start-discovery-receipt.py'
spec = importlib.util.spec_from_file_location('receipt', helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp)
    status = path / 'status'
    assert module.read_status(status)[0] == 'SUPERVISOR_STATUS_MISSING'
    for raw in (b'0\t0\t0\t0\t0\t0\n', b'0\t0\t2\t0\t0\t0\t0\n', b'0\t0\t0\t0\t-1\t0\t0\n', b'0\t9\t0\t0\t0\t0\t0\n', b'0\t0\t0\t0\t0\t0\t0\nsecret'):
        status.write_bytes(raw)
        assert module.read_status(status)[0] == 'SUPERVISOR_STATUS_INVALID'
    for raw, expected in [('0\t0\t0\t0\t1\t2\t3\n', None), ('7\t0\t0\t0\t1\t2\t3\n', 'PROVIDER_EXIT_NONZERO'), ('143\t15\t0\t0\t1\t2\t3\n', 'PROVIDER_SIGNALLED'), ('143\t15\t1\t1\t1\t2\t3\n', 'PROVIDER_TIMEOUT'), ('0\t0\t0\t1\t1\t2\t3\n', 'PROVIDER_DESCENDANTS_TERMINATED')]:
        status.write_text(raw)
        assert module.read_status(status)[0] == expected
    workspace = path / 'workspace'
    workspace.mkdir()
    for run_id, payload, expected in [('c'*32, None, 'SUPERVISOR_STATUS_MISSING'), ('d'*32, b'malformed-secret', 'SUPERVISOR_STATUS_INVALID')]:
        if payload is None:
            status.unlink()
        else:
            status.write_bytes(payload)
        subprocess.run(['python3', str(helper), 'publish', str(status), str(workspace), run_id, 'not_reached', 'UNKNOWN_FAILURE'], check=True)
        receipt = json.loads((workspace / module.NAMESPACE / ('story-start-discovery-failure-' + run_id + '.json')).read_text())
        assert receipt['failureCategory'] == expected and receipt['supervisor'] is None
        assert 'malformed-secret' not in json.dumps(receipt)
    status.write_text('7\t0\t0\t0\t17\t21\t30\n')
    run = 'a' * 32
    subprocess.run(['python3', str(helper), 'publish', str(status), str(workspace), run, 'not_reached', 'UNKNOWN_FAILURE'], check=True)
    receipt_path = workspace / module.NAMESPACE / ('story-start-discovery-failure-' + run + '.json')
    receipt = json.loads(receipt_path.read_text())
    assert receipt['failureCategory'] == 'PROVIDER_EXIT_NONZERO'
    assert receipt['supervisor']['stdoutBytes'] == 17
    assert receipt_path.stat().st_mode & 0o777 == 0o600
    assert 'secret' not in receipt_path.read_text()
    original = receipt_path.read_bytes()
    assert subprocess.run(['python3', str(helper), 'publish', str(status), str(workspace), run, 'not_reached', 'UNKNOWN_FAILURE']).returncode != 0
    assert receipt_path.read_bytes() == original
    outside = path / 'outside'
    outside.mkdir()
    bad = path / 'bad'
    bad.mkdir()
    (bad / module.NAMESPACE).symlink_to(outside, target_is_directory=True)
    assert subprocess.run(['python3', str(helper), 'publish', str(status), str(bad), 'b'*32, 'not_reached', 'UNKNOWN_FAILURE']).returncode != 0
    assert list(outside.iterdir()) == []
    assert (workspace / module.NAMESPACE).stat().st_mode & 0o777 == 0o700
    # Reject a preexisting diagnostic namespace with public permissions.
    public = path / 'public'
    (public / module.NAMESPACE).mkdir(parents=True, mode=0o755)
    assert subprocess.run(['python3', str(helper), 'publish', str(status), str(public), 'b'*32, 'not_reached', 'UNKNOWN_FAILURE']).returncode != 0
    assert list((public / module.NAMESPACE).iterdir()) == []
    linked_workspace = path / 'linked-workspace'
    linked_workspace.symlink_to(workspace, target_is_directory=True)
    assert subprocess.run(['python3', str(helper), 'publish', str(status), str(linked_workspace), 'b'*32, 'not_reached', 'UNKNOWN_FAILURE']).returncode != 0
    # Collisions preserve old bytes and do not strand staging files.
    before = receipt_path.read_bytes()
    assert not list((workspace / module.NAMESPACE).glob('.discovery-receipt-*'))
    assert receipt_path.read_bytes() == before
    # Actual write/publication failure cleanup, without production hooks.
    for operation in ('fsync', 'link'):
        with patch.object(module.os, operation, side_effect=OSError('controlled test failure')):
            try:
                module.publish(str(workspace), 'e'*32, 'UNKNOWN_FAILURE', None, 'not_reached')
            except OSError:
                pass
            else:
                raise AssertionError('publication fault accepted')
        assert not list((workspace / module.NAMESPACE).glob('.discovery-receipt-*'))
        assert not (workspace / module.NAMESPACE / ('story-start-discovery-failure-' + 'e'*32 + '.json')).exists()
        assert receipt_path.read_bytes() == before
    # Intermediate symlinks must fail even when the target has valid .mana ancestry.
    target = path / 'target-project' / '.mana' / 'features' / 'ID'
    target.mkdir(parents=True)
    for name in ('collection', 'mana'):
        project = path / ('linked-' + name)
        project.mkdir()
        if name == 'collection':
            (project / '.mana').mkdir()
            (project / '.mana' / 'features').symlink_to(target.parent, target_is_directory=True)
        else:
            (project / '.mana').symlink_to(target.parent.parent, target_is_directory=True)
        candidate = project / '.mana' / 'features' / 'ID'
        assert subprocess.run(['python3', str(helper), 'publish', str(status), str(candidate), 'f'*32, 'not_reached', 'UNKNOWN_FAILURE']).returncode != 0
        assert not (target / module.NAMESPACE).exists()

# The shared read policy reserves only exact operational components.
from discovery_receipt_boundary import is_private_discovery_path
for relative in [
    '.mana/features/MiXeD/.mana-story-start-discovery',
    '.MANA/Features/MiXeD/.MANA-STORY-START-DISCOVERY/arbitrary/nested.md',
    '.mana/Sessions/ID/EVIDENCE/STORY-START-DISCOVERY-FAILURE-' + 'A'*32 + '.JSON',
    '.mana/features/ID/evidence/.DISCOVERY-RECEIPT-' + 'A'*32,
]:
    assert is_private_discovery_path(relative)
for relative in [
    '.mana/features/MiXeD/.mana-story-start-discovery-application/ordinary.json',
    '.mana/features/MiXeD/evidence/story-start-discovery-failure-document.json',
    '.mana/features/MiXeD/evidence/.discovery-receipt-document',
    '.mana/features/MiXeD/evidence/.ordinary.tmp',
    '.mana/features/MiXeD/evidence/ordinary.json',
    '.mana/features-application/ID/.mana-story-start-discovery/ordinary.json',
]:
    assert not is_private_discovery_path(relative)
print('Discovery receipt offline unit tests passed')
