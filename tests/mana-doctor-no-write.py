#!/usr/bin/env python3
"""Targeted real-process checks on disposable, bootstrapped framework/project copies.

Requires explicit fixture paths. Retains snapshots, content blobs and raw logs;
never cleans or changes the implementation checkout. Strict exit zero is not
expected while the original Sonar warning remains.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.root = args.root.resolve(strict=True)
    args.project = args.project.resolve(strict=True)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    blobs = args.output / 'contents'
    blobs.mkdir()
    env = dict(os.environ)
    env.update(PYTHONDONTWRITEBYTECODE='1', GIT_OPTIONAL_LOCKS='0')
    results = []

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + '\n')

    def inventory(root):
        records = {}
        for parent, dirs, names in os.walk(root, followlinks=False):
            for path in [Path(parent), *(Path(parent) / n for n in dirs + names)]:
                rel = str(path.relative_to(root))
                if rel in records:
                    continue
                meta = path.lstat()
                kind = ('link' if stat.S_ISLNK(meta.st_mode) else 'directory'
                        if stat.S_ISDIR(meta.st_mode) else 'file')
                record = {'type': kind, 'mode': stat.S_IMODE(meta.st_mode),
                          'size': meta.st_size, 'inode': meta.st_ino,
                          'device': meta.st_dev, 'links': meta.st_nlink,
                          'mtime_ns': meta.st_mtime_ns, 'ctime_ns': meta.st_ctime_ns}
                if kind == 'file':
                    data = path.read_bytes()
                    digest = hashlib.sha256(data).hexdigest()
                    record['sha256'] = digest
                    # Preserve .mana payloads; hash all other observed files.
                    if rel == '.mana' or rel.startswith('.mana/'):
                        target = blobs / digest
                        if not target.exists():
                            target.write_bytes(data)
                        record['content_blob'] = str(target.relative_to(args.output))
                elif kind == 'link':
                    record['target'] = os.readlink(path)
                records[rel] = record
        return records

    def run(name, argv, project, expected_exit, expect_writes=False, messages=()):
        directory = args.output / name
        directory.mkdir()
        roots = [args.root, project]
        before = {str(p): inventory(p) for p in roots}
        write(directory / 'before.json', before)
        started = time.monotonic()
        process = subprocess.run(list(map(str, argv)), cwd=args.root, env=env,
                                 capture_output=True, text=True, timeout=120)
        (directory / 'stdout.log').write_text(process.stdout)
        (directory / 'stderr.log').write_text(process.stderr)
        after = {str(p): inventory(p) for p in roots}
        write(directory / 'after.json', after)
        changes = []
        for root in before:
            for path in sorted(before[root].keys() | after[root].keys()):
                old, new = before[root].get(path), after[root].get(path)
                if old == new:
                    continue
                operation = ('CREATE' if old is None else 'DELETE' if new is None
                             else 'CONTENT_CHANGE' if old.get('sha256') != new.get('sha256')
                             or old.get('target') != new.get('target') else 'METADATA_ONLY')
                changes.append({'root': root, 'path': path, 'operation': operation,
                                'before': old, 'after': new})
        write(directory / 'changes.json', changes)
        failures = []
        if process.returncode != expected_exit:
            failures.append('exit')
        if not expect_writes and changes:
            failures.append('persistent mutation')
        if expect_writes and not any(c['operation'] == 'CREATE'
                                     and c['path'].startswith('.mana/runtime/execution-intents/')
                                     for c in changes):
            failures.append('ordinary execution identity no longer materialized')
        for message in messages:
            if message not in process.stdout + process.stderr:
                failures.append('missing diagnostic: ' + message)
        summary = re.search(r'Summary: (\d+) error\(s\), (\d+) warning\(s\)', process.stdout)
        if summary:
            errors, warnings = map(int, summary.groups())
            if '--strict' in argv:
                if errors != warnings or errors < 1:
                    failures.append('strict count/known Sonar warning')
            elif errors != 0:
                failures.append('normal error count')
        result = {'name': name, 'argv': list(map(str, argv)), 'cwd': str(args.root),
                  'exit_code': process.returncode, 'elapsed_seconds': round(time.monotonic() - started, 3),
                  'kind': 'REAL_PROCESS_TARGETED_REGRESSION',
                  'mutation_expected': expect_writes, 'delta_count': len(changes),
                  'operations': dict(collections.Counter(c['operation'] for c in changes)),
                  'failures': failures, 'passed': not failures}
        write(directory / 'result.json', result)
        results.append(result)
        print(('PASS' if not failures else 'FAIL') + ': ' + name, flush=True)

    doctor = ['bash', str(args.root / 'scripts/mana-doctor.sh'), '--root', args.root,
              '--project', args.project]
    expected_profiles = ['mana-help', 'jessica-fletcher', 'pre-commit', 'am-release-ready',
                         'architecture-review', 'team-planning', 'story-ready-for-dev']
    load_messages = [p + ' profile loads' for p in expected_profiles]
    load_messages += ['project wrapper can load ' + p for p in
                      ['mana-help', 'story-start', 'branch-ready', 'requested-pr-review']]
    load_messages += ['Sonar server/authentication probe skipped: mana doctor is local-only',
                      'project branch does not contain a generic issue key: master',
                      'project evidence index is unavailable/not-materialized']
    run('doctor-normal', doctor, args.project, 0, messages=load_messages)
    run('doctor-strict', doctor + ['--strict'], args.project, 1, messages=load_messages)

    def fixture(name, policy_mode=None, missing=False, invalid=False):
        target = args.output / 'fixtures' / name
        shutil.copytree(args.project, target, symlinks=True,
                        ignore=shutil.ignore_patterns('runtime-selection-v1.json') if missing else None)
        policy = target / '.mana/context-runtime/runtime-selection-v1.json'
        if invalid:
            policy.write_text('{"schemaVersion": "invalid"}\n')
        elif policy_mode:
            content = json.loads(policy.read_text())
            content['profiles']['mana-help'] = {'mode': policy_mode}
            policy.write_text(json.dumps(content) + '\n')
        return target

    helper = ['bash', str(args.root / 'scripts/run-profile.sh'), 'mana-help']
    for name, options, exit_code, message in [
        ('diagnostic-load', [], 0, 'Execution note: --render-only requested'),
        ('reject-runner', ['--codex'], 2, '--diagnose cannot select'),
        ('reject-identity', ['--runtime-execution-id', 'execution-r304'], 2, '--diagnose cannot select'),
        ('reject-manifest', ['--context-manifest', 'not-a-manifest.json'], 2, '--diagnose cannot select'),
        ('reject-runtime-override', ['--context-runtime', 'legacy'], 2, '--diagnose cannot select'),
        ('reject-unknown-skill', ['--request-skill', 'r304-does-not-exist'], 1, 'ERROR:'),
    ]:
        project = fixture(name)
        run(name, helper + ['--project-root', project, '--diagnose'] + options,
            project, exit_code, messages=[message])
    project = fixture('invalid-policy', invalid=True)
    run('invalid-policy', helper + ['--project-root', project, '--diagnose'], project, 2,
        messages=['runtime policy violates'])
    for mode, message in [('v2', 'CTX10_EXECUTION_IDENTITY_REQUIRED'),
                          ('shadow', 'does not render a provider prompt'),
                          ('compare', 'does not render a provider prompt')]:
        project = fixture('selected-' + mode, policy_mode=mode)
        run('selected-' + mode, helper + ['--project-root', project, '--diagnose'],
            project, 2, messages=[message])
    project = fixture('missing-policy', missing=True)
    run('missing-policy-strict', ['bash', str(args.root / 'scripts/mana-doctor.sh'),
                                 '--root', args.root, '--project', project, '--strict'],
        project, 1, messages=['CTX-10 host-owned runtime policy is unavailable or invalid'])
    project = fixture('ordinary-profile')
    run('ordinary-profile', helper + ['--project-root', project], project, 0, expect_writes=True)
    summary = {'kind': 'REAL_PROCESS_TARGETED_REGRESSION', 'cases': results,
               'passed': sum(r['passed'] for r in results),
               'failed': sum(not r['passed'] for r in results),
               'claim': 'Local no-write remediation only. Not overall Doctor or REL-01/A PASS.'}
    write(args.output / 'results.json', summary)
    print(f"Targeted no-write checks: {summary['passed']}/{len(results)} passed", flush=True)
    return 1 if summary['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
