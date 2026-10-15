#!/usr/bin/env python3
"""Bounded simulated tool-readiness regressions; retains all fixtures and logs.

This exercises the production readiness functions and exit/count epilogue.
It does not qualify real tools, remote authentication or a release tuple.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--doctor', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'scripts/mana-doctor.sh')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bash', default='/bin/bash')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.doctor.read_text()
    functions = source.split('pass() {', 1)[1].split('echo "Mana doctor"', 1)[0]
    epilogue = source[source.index('if [ "$strict" = true ] && [ "$warnings" -gt 0 ]; then'):]
    harness = args.output / 'readiness.sh'
    harness.write_text('set -u\nerrors=0\nwarnings=0\nproject=""\n'
                       'strict="$1"\npass() {' + functions
                       + '\ncheck_external_tools\n' + epilogue)
    tools = ['bash', 'git', 'rg', 'curl', 'base64', 'shellcheck',
             'sonar-scanner', 'docker', 'gh', 'codex', 'claude']
    # name, strict, configured env, absent tool, failing tool, errors, warnings
    cases = [
        ('configured-normal', False, 'both', None, None, 0, 0),
        ('configured-strict', True, 'both', None, None, 0, 0),
        ('missing-url-strict', True, 'token', None, None, 1, 1),
        ('missing-token-strict', True, 'url', None, None, 1, 1),
        ('missing-env-normal', False, 'none', None, None, 0, 1),
        ('missing-env-strict', True, 'none', None, None, 1, 1),
        ('absent-scanner-normal', False, 'both', 'sonar-scanner', None, 0, 1),
        ('absent-scanner-strict', True, 'both', 'sonar-scanner', None, 1, 1),
        ('broken-scanner-normal', False, 'both', None, 'sonar-scanner', 0, 1),
        ('broken-scanner-strict', True, 'both', None, 'sonar-scanner', 1, 1),
        ('broken-scanner-and-env', True, 'none', None, 'sonar-scanner', 2, 2),
        ('missing-docker-strict', True, 'both', 'docker', None, 1, 1),
        ('unreachable-docker-strict', True, 'both', None, 'docker', 1, 1),
        ('missing-claude-strict', True, 'both', 'claude', None, 1, 1),
        ('broken-claude-strict', True, 'both', None, 'claude', 1, 1),
        ('broken-codex-strict', True, 'both', None, 'codex', 1, 1),
        ('missing-required-rg-normal', False, 'both', 'rg', None, 1, 0),
        ('missing-required-rg-strict', True, 'both', 'rg', None, 1, 0),
    ]
    results = []
    for name, strict, configured, absent, broken, errors, warnings in cases:
        case = args.output / name
        bindir = case / 'bin'
        bindir.mkdir(parents=True)
        calls = case / 'calls.log'
        for tool in tools:
            if tool == absent:
                continue
            stub = bindir / tool
            # Only the documented local version/info argv can succeed.
            allowed = 'info' if tool == 'docker' else '--version'
            status = 7 if tool == broken else 0
            stub.write_text('#!/bin/sh\n'
                            'printf "%s %s\\n" "${0##*/}" "$*" >> "$DOCTOR_TOOL_LOG"\n'
                            f'[ "$#" -eq 1 ] && [ "$1" = "{allowed}" ] || exit 91\n'
                            f'exit {status}\n')
            stub.chmod(0o755)
        # An explicit env prevents inherited credentials/tool paths from helping.
        env = {'PATH': str(bindir), 'DOCTOR_TOOL_LOG': str(calls),
               'JIRA_URL': 'https://jira.invalid', 'JIRA_API_TOKEN': 'fixture',
               'JIRA_USERNAME': 'fixture', 'PYTHONDONTWRITEBYTECODE': '1'}
        if configured in ('both', 'url'):
            env['SONAR_HOST_URL'] = 'https://sonar.invalid'
        if configured in ('both', 'token'):
            env['SONAR_TOKEN'] = 'fixture'
        argv = [args.bash, str(harness), str(strict).lower()]
        process = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)
        (case / 'stdout.log').write_text(process.stdout)
        (case / 'stderr.log').write_text(process.stderr)
        actual_calls = calls.read_text().splitlines() if calls.exists() else []
        expected_summary = f'Summary: {errors} error(s), {warnings} warning(s)'
        failures = []
        if process.returncode != (1 if errors else 0):
            failures.append('exit')
        if process.stdout.splitlines()[-1:] != [expected_summary]:
            failures.append('summary')
        if len(re.findall(r'^WARN:', process.stderr, re.M)) != warnings:
            failures.append('warning count')
        if 'WARN: Sonar server/authentication probe skipped' in process.stderr:
            failures.append('artificial skipped-probe warning')
        expected_calls = ['sonar-scanner --version', 'docker info',
                          'codex --version', 'claude --version']
        expected_calls = [call for call in expected_calls if call.split()[0] != absent]
        if actual_calls != expected_calls:
            failures.append('unexpected probe or missing local command')
        expected_message = None
        if absent == 'sonar-scanner':
            expected_message = 'optional tool missing: sonar-scanner'
        elif configured != 'both':
            expected_message = 'Sonar env not configured;'
        elif broken == 'sonar-scanner':
            expected_message = 'sonar-scanner is installed but did not run;'
        elif absent:
            expected_message = ('required tool missing: ' if absent == 'rg'
                                else 'optional tool missing: ') + absent
        elif broken == 'docker':
            expected_message = 'docker installed but daemon is not reachable;'
        elif broken:
            expected_message = broken + ' is installed but did not respond to --version'
        if expected_message and expected_message not in process.stderr:
            failures.append('missing specific diagnostic')
        if absent != 'sonar-scanner' and ('Sonar server/authentication probe skipped: '
                                          'mana doctor is local-only') not in process.stdout:
            failures.append('remote capability limitation not disclosed')
        result = {'case': name, 'kind': 'SIMULATED_REGRESSION', 'argv': argv,
                  'exit_code': process.returncode, 'expected_errors': errors,
                  'expected_warnings': warnings, 'calls': actual_calls,
                  'failures': failures, 'passed': not failures}
        (case / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        results.append(result)
        print(('PASS' if not failures else 'FAIL') + ': ' + name
              + (': ' + ', '.join(failures) if failures else ''))
    summary = {'kind': 'SIMULATED_REGRESSION', 'cases': results,
               'passed': sum(r['passed'] for r in results),
               'failed': sum(not r['passed'] for r in results)}
    (args.output / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f"Simulated tool-readiness regressions: {summary['passed']}/{len(results)} passed")
    return 1 if summary['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
