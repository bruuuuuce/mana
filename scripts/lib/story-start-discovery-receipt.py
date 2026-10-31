#!/usr/bin/env python3
"""Validate supervisor metadata and publish a private Discovery failure receipt."""
import json
import os
import re
import secrets
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from discovery_receipt_boundary import (NAMESPACE, directory_flags,
                                        open_discovery_workspace, require_canonical_entry)

FIELDS = ('exitCode', 'signal', 'timedOut', 'descendantsTerminated',
          'stdoutBytes', 'stderrBytes', 'durationMs')
LIMITS = (255, 127, 1, 1, 2**63-1, 2**63-1, 2**63-1)


def read_status(path):
    try:
        with open(path, 'rb') as stream:
            data = stream.read(512)
    except FileNotFoundError:
        return 'SUPERVISOR_STATUS_MISSING', None
    except OSError:
        return 'SUPERVISOR_STATUS_INVALID', None
    if not re.fullmatch(rb'(?:0|[1-9][0-9]{0,18})(?:\t(?:0|[1-9][0-9]{0,18})){6}\n', data):
        return 'SUPERVISOR_STATUS_INVALID', None
    values = [int(x) for x in data[:-1].split(b'\t')]
    if any(value > limit for value, limit in zip(values, LIMITS)):
        return 'SUPERVISOR_STATUS_INVALID', None
    code, signal, timeout, descendants, *_ = values
    if signal and (code != 128 + signal or code > 255):
        return 'SUPERVISOR_STATUS_INVALID', None
    fields = dict(zip(FIELDS, values))
    fields['timedOut'] = bool(timeout)
    fields['descendantsTerminated'] = bool(descendants)
    if timeout:
        category = 'PROVIDER_TIMEOUT'
    elif descendants:
        category = 'PROVIDER_DESCENDANTS_TERMINATED'
    elif signal:
        category = 'PROVIDER_SIGNALLED'
    elif code:
        category = 'PROVIDER_EXIT_NONZERO'
    else:
        category = None
    return category, fields


def publish(workspace, run_id, category, fields, schema_result):
    if not re.fullmatch(r'[0-9a-f]{32}', run_id):
        raise ValueError('invalid execution id')
    flags = directory_flags()
    root = open_discovery_workspace(workspace)
    diagnostics = None
    temp = None
    try:
        require_canonical_entry(root, NAMESPACE)
        try:
            os.mkdir(NAMESPACE, 0o700, dir_fd=root)
        except FileExistsError:
            pass
        diagnostics = os.open(NAMESPACE, flags, dir_fd=root)
        require_canonical_entry(root, NAMESPACE, diagnostics)
        info = os.fstat(diagnostics)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('unsafe diagnostic directory')
        filename = 'story-start-discovery-failure-' + run_id + '.json'
        temp = '.discovery-receipt-' + secrets.token_hex(16)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=diagnostics)
        receipt = {'schemaVersion': 'mana.story-start.discovery-failure-receipt/v1',
                   'phase': 'discovery', 'executionId': run_id,
                   'failureCategory': category, 'supervisor': fields,
                   'schemaValidation': schema_result}
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(receipt, out, sort_keys=True, separators=(',', ':'))
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        # A hard link creates the final name atomically without replacing anything.
        os.link(temp, filename, src_dir_fd=diagnostics, dst_dir_fd=diagnostics, follow_symlinks=False)
        os.unlink(temp, dir_fd=diagnostics)
        temp = None
        print('Discovery diagnostic receipt: ' + NAMESPACE + '/' + filename, file=sys.stderr)
    finally:
        if temp is not None and diagnostics is not None:
            try:
                os.unlink(temp, dir_fd=diagnostics)
            except OSError:
                pass
        if diagnostics is not None:
            os.close(diagnostics)
        os.close(root)


def main():
    mode, status = sys.argv[1:3]
    category, fields = (None, None) if mode == 'publish' and status == '-' else read_status(status)
    if mode == 'check':
        return 0 if category is None else 1
    if mode != 'publish' or len(sys.argv) != 7:
        return 2
    workspace, run_id, result, fallback = sys.argv[3:]
    if result not in ('not_reached', 'passed', 'failed') or fallback not in ('UNKNOWN_FAILURE', 'PROVIDER_OUTPUT_SCHEMA_INVALID'):
        return 2
    try:
        publish(workspace, run_id, category or fallback, fields, result)
    except (OSError, ValueError):
        print('WARNING: Discovery diagnostic receipt publication failed', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
