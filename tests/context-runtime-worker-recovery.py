#!/usr/bin/env python3
"""Independent zero-token CTX-07B crash, authority and lifecycle regressions."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


suite_module = load('ctx07_recovery_suite', ROOT / 'tests/context-runtime-workers.py')
w = load('ctx07_recovery_worker', ROOT / 'scripts/lib/context-worker-runtime.py')
w.HOST_FRAMEWORK_ROOT = suite_module.FRAMEWORK


def rejected(action, fragment):
    try:
        action()
    except w.runtime.ContractError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f'expected rejection: {fragment}')


def main():
    suite = suite_module.Suite()
    try:
        suite.setup()
        prepared = json.loads(suite.command([
            str(ROOT / 'tests/context-worker-runtime-test-only.py'), 'prepare-plan',
            suite_module.EXECUTION, '--project-root', str(suite.project),
            '--plan', str(suite.tmp / 'plan.json'),
        ]).stdout)
        task = prepared['plan']['tasks'][0]
        pp = suite.write_json('recovery-prepared.json', prepared)
        tp = suite.write_json('recovery-task.json', task)
        draft = {'schemaVersion': 'mana.context-runtime.delegation-result-draft/v1',
                 'taskId': task['taskId'], 'status': 'complete',
                 **{name: [] for name in w.COLLECTION_SECTIONS},
                 'uncertainty': {'level': 'none', 'description': None, 'evidenceRefs': []}}
        dp = suite.write_json('recovery-draft.json', draft)
        result = json.loads(suite.command([
            str(suite_module.DELEGATION), 'bind-result', *suite.common(),
            '--plan', str(suite.tmp / 'plan.json'), '--draft', str(dp),
        ]).stdout)
        rp = suite.write_json('recovery-result.json', result)
        key = w.task_execution_key(prepared, task)
        phase_relative = f'.mana/runtime/runs/{suite_module.EXECUTION}/run-state-v1.json'
        phase = (suite.project / phase_relative).read_bytes()

        def fresh(label):
            project = suite.tmp / label
            shutil.copytree(suite.project, project)
            claim = w.claim_task(str(project), str(pp), str(tp))
            base = project / w._execution_relative(key)
            return project, base, claim

        def publish(project, claim):
            return w.publish_task(str(project), key, claim['invocationId'], str(rp), str(pp), str(tp))

        # Force another host to claim after we open the task directory but
        # before we acquire its lock. Both must converge on the same inode.
        project = suite.tmp / 'lock-publication-race'
        shutil.copytree(suite.project, project)
        ready_r, ready_w = os.pipe()
        resume_r, resume_w = os.pipe()
        pid = os.fork()
        if pid == 0:
            def pause_lock(point):
                if point == 'worker-before-state-lock':
                    w.runtime._TEST_SYNC_HOOK = None
                    os.write(ready_w, b'1')
                    os.read(resume_r, 1)
            w.runtime._TEST_SYNC_HOOK = pause_lock
            action = w.claim_task(str(project), str(pp), str(tp))['action']
            os._exit(0 if action == 'wait' else 90)
        assert os.read(ready_r, 1) == b'1'
        try:
            winner = w.claim_task(str(project), str(pp), str(tp))
            assert winner['action'] == 'claimed'
        finally:
            os.write(resume_w, b'1')
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        for fd in (ready_r, ready_w, resume_r, resume_w):
            os.close(fd)
        assert not list((project / w._execution_relative(key)).glob('*.tmp.*'))
        print('deterministic directory lock race passed', flush=True)

        # Exercise the three transport/normalization/binding boundaries through
        # the real worker runner and provider stub. The crash hook is reachable
        # only through the canonical test-only entry point.
        outside = suite.tmp / 'recovery-outside-sentinel'
        outside.write_text('UNCHANGED', encoding='utf-8')
        for label in ('after-provider', 'before-bind', 'after-bind'):
            task_id = 'T-recovery-' + label
            boundary_plan = suite.bind_plan({
                'schemaVersion': 'mana.context-runtime.delegation-plan-draft/v1',
                'tasks': [suite.task(
                    task_id, 'recovery-' + label + '-owner',
                    'Exercise the real ' + label + ' recovery boundary.', [],
                )],
            }, 'recovery-' + label)
            project = suite.tmp / ('real-crash-' + label)
            shutil.copytree(suite.project, project)
            phase_before = (project / phase_relative).read_bytes()
            state = suite.tmp / ('state-real-crash-' + label)
            env = suite.env.copy()
            env.update({
                'CTX07B_STATE_DIR': str(state),
                'MANA_CTX07B_TEST_CRASH_POINT': label,
            })
            args = suite.runner_args('recovery-' + label, project=project)
            crashed = suite.command(args, ok=False, env=env)
            assert crashed.returncode == 1, (label, crashed.returncode, crashed.stderr)
            assert 'worker_failure exitStatus=137' in crashed.stderr, (label, crashed.stderr)
            assert json.loads(crashed.stdout)['mergeStatus'] == 'incomplete'
            assert (state / f'provider-reached.{task_id}').is_file(), label
            assert (state / f'fault.{label}').read_text().strip() == label
            assert (state / 'invocations.log').read_text().splitlines() == [task_id]
            boundary_task = boundary_plan['tasks'][0]
            boundary_base = suite.worker_root_for(project, boundary_task)
            assert not (boundary_base / 'task-result-head.json').exists(), label
            boundary_prepared = json.loads(suite.command([
                str(ROOT / 'tests/context-worker-runtime-test-only.py'), 'prepare-plan',
                suite_module.EXECUTION, '--project-root', str(project),
                '--plan', str(suite.tmp / f'recovery-{label}.json'),
            ]).stdout)
            assert w._read_authoritative_head(
                project, boundary_base.name, boundary_prepared, boundary_task
            ) is None
            assert (project / phase_relative).read_bytes() == phase_before
            before_events = [json.loads(path.read_text()) for path in boundary_base.glob('events/*.json')]
            assert any(item['eventType'] == 'worker.started' for item in before_events)
            assert not any(item['eventType'] == 'worker.completed' for item in before_events)

            claim_path = boundary_base / 'claim.json'
            crashed_claim = json.loads(claim_path.read_text())
            crashed_invocation = crashed_claim['invocationId']
            crashed_claim['claimedAt'] -= w.WORKER_CLAIM_LEASE_SECONDS + 10
            crashed_claim['leaseExpiresAt'] = crashed_claim['claimedAt'] + w.WORKER_CLAIM_LEASE_SECONDS
            claim_path.write_text(json.dumps(crashed_claim), encoding='utf-8')
            env.pop('MANA_CTX07B_TEST_CRASH_POINT')
            retry = suite.command(args, env=env)
            assert json.loads(retry.stdout)['mergeStatus'] == 'complete'
            assert (state / 'invocations.log').read_text().splitlines() == [task_id, task_id]
            head = json.loads((boundary_base / 'task-result-head.json').read_text())
            assert head['invocationId'] != crashed_invocation
            assert (boundary_base / head['artifact']).is_file()
            assert (project / phase_relative).read_bytes() == phase_before
            metrics = {json.loads(path.read_text())['invocationId']: path for path in boundary_base.glob('metrics/I-*.json')}
            assert len(metrics) == 2
            crashed_metric = json.loads(metrics[crashed_invocation].read_text())
            assert crashed_metric['status'] == 'interrupted'
            assert json.loads(metrics[head['invocationId']].read_text())['status'] == 'complete'
            crashed_metric_bytes = metrics[crashed_invocation].read_bytes()
            aggregate = json.loads((boundary_base / 'usage-aggregate.json').read_text())
            assert aggregate['invocationCount'] == 2
            assert aggregate['statuses'] == {'complete': 1, 'interrupted': 1}
            events = [json.loads(path.read_text()) for path in boundary_base.glob('events/*.json')]
            old_events = [item['eventType'] for item in events if item.get('invocationId') == crashed_invocation]
            new_events = [item['eventType'] for item in events if item.get('invocationId') == head['invocationId']]
            assert old_events.count('worker.interrupted') == 1
            assert 'worker.completed' not in old_events
            assert new_events.count('worker.completed') == 1
            assert any(item['eventType'] == 'worker.claim.reconciled' for item in events)
            assert not [
                path for path in boundary_base.rglob('*')
                if any(marker in path.name for marker in ('.tmp.', '.stage', '.abort', 'quarantine'))
            ], label
            assert outside.read_text() == 'UNCHANGED'
            reused = suite.command(args, env=env)
            assert json.loads(reused.stdout)['mergeStatus'] == 'complete'
            assert (state / 'invocations.log').read_text().splitlines() == [task_id, task_id]
            assert metrics[crashed_invocation].read_bytes() == crashed_metric_bytes
            print('real boundary crash/recovery:', label, 'passed', flush=True)

        # These are actual process crashes: finally blocks and Python cleanup
        # cannot run. All test hooks live in this test process, never production CLI.
        faults = [
            ('receipt-stage', 'receipt.json', 'after-final-prepublish-check'),
            ('result-stage', 'result.json', 'after-final-prepublish-check'),
            ('after-attempt', 'result.json', 'after-write'),
            ('head-cas', 'task-result-head.json', 'after-final-prepublish-check'),
            ('after-head-cas', 'task-result-head.json', 'after-write'),
            ('metric-stage', 'metric', 'after-final-prepublish-check'),
            ('event-stage', 'worker.completed.json', 'after-final-prepublish-check'),
            ('aggregate-stage', 'usage-aggregate.json', 'after-final-prepublish-check'),
            ('claim-exchange', 'claim.json', 'after-exchange-before-cleanup'),
            ('after-cleanup', 'claim.json', 'after-write'),
        ]
        for label, target, point in faults:
            project, base, claim = fresh('crash-' + label)
            pid = os.fork()
            if pid == 0:
                original = w._publish_json

                def injected(root, relative, value, **kwargs):
                    selected = (('/metrics/' in relative) if target == 'metric' else relative.endswith(target))
                    if selected:
                        w.runtime._TEST_SYNC_HOOK = lambda p: os._exit(91) if p == point else None
                    try:
                        output = original(root, relative, value, **kwargs)
                    finally:
                        w.runtime._TEST_SYNC_HOOK = None
                    if selected and point == 'after-write':
                        os._exit(91)
                    return output

                w._publish_json = injected
                publish(project, claim)
                os._exit(92)
            _, status = os.waitpid(pid, 0)
            assert os.waitstatus_to_exitcode(status) == 91, label
            # An observer resolves only HEAD; stages are never reusable outputs.
            observer = w._read_authoritative_head(project, key, prepared, task)
            assert observer is None or observer[0] == result
            recovered = w.claim_task(str(project), str(pp), str(tp))
            assert recovered['action'] == 'reused', (label, recovered)
            again = w.claim_task(str(project), str(pp), str(tp))
            assert again['action'] == 'reused'
            publish(project, claim)  # idempotent exact retry
            assert len(list(base.glob('attempts/*/result.json'))) == 1
            metrics = list(base.glob('metrics/I-*.json'))
            assert len(metrics) == 1, label
            metric = json.loads(metrics[0].read_text())
            assert metric['status'] == 'complete'
            aggregate = json.loads((base / 'usage-aggregate.json').read_text())
            assert aggregate['invocationIds'] == [claim['invocationId']]
            events = [json.loads(p.read_text()) for p in base.glob('events/*.json')]
            terminal = 'worker.completed'
            assert sum(e['eventType'] == terminal for e in events) == 1, label
            assert (project / phase_relative).read_bytes() == phase
            assert not [p for p in base.rglob('*') if any(x in p.name for x in ('.tmp.', '.stage', '.abort', 'quarantine'))], label
            print('crash/recovery:', label, 'passed', flush=True)

        project, base, claim = fresh('conflict')
        publish(project, claim)
        changed = copy.deepcopy(draft)
        changed['status'] = 'partial'
        changed_path = suite.write_json('different-draft.json', changed)
        different = json.loads(suite.command([
            str(suite_module.DELEGATION), 'bind-result', *suite.common(),
            '--plan', str(suite.tmp / 'plan.json'), '--draft', str(changed_path),
        ]).stdout)
        different_path = suite.write_json('different-result.json', different)
        rejected(lambda: w.publish_task(str(project), key, claim['invocationId'], str(different_path), str(pp), str(tp)), 'conflicting')
        assert w.claim_task(str(project), str(pp), str(tp))['resultObject'] == result
        for label, mutation in [('foreign', {'taskId': 'T-foreign'}), ('stale', {'attempt': 99}), ('partial', {})]:
            target = base / f"attempts/{claim['invocationId']}/result.json"
            saved = target.read_bytes()
            target.write_text(json.dumps({**result, **mutation} if mutation else {}))
            try:
                rejected(lambda: w.claim_task(str(project), str(pp), str(tp)), '')
            finally:
                target.write_bytes(saved)
        print('reuse validation and conflicting publication passed', flush=True)

        project, base, claim = fresh('publication-failure')
        original_publish = w._publish_json

        def fail_head(root, relative, value, **kwargs):
            if relative.endswith('/task-result-head.json'):
                raise w.runtime.ContractError('injected HEAD publication failure')
            return original_publish(root, relative, value, **kwargs)

        w._publish_json = fail_head
        try:
            rejected(lambda: publish(project, claim), 'injected HEAD')
        finally:
            w._publish_json = original_publish
        w.finalize_task(str(project), key, claim['invocationId'], 'publication_failed')
        w.finalize_task(str(project), key, claim['invocationId'], 'publication_failed')
        assert not (base / 'task-result-head.json').exists()
        assert json.loads((base / 'claim.json').read_text())['terminalStatus'] == 'publication_failed'
        assert json.loads(next(base.glob('metrics/*.json')).read_text())['status'] == 'publication_failed'
        events = [json.loads(p.read_text()) for p in base.glob('events/*.json')]
        assert sum(e['eventType'] == 'worker.failed' for e in events) == 1
        assert not any(e['eventType'] == 'worker.completed' for e in events)
        assert w.claim_task(str(project), str(pp), str(tp))['action'] == 'claimed'
        print('publication failure lifecycle and immediate retry passed', flush=True)

        for label, mutation in [
            ('foreign-key', {'taskExecutionKey': 'W-' + '0' * 64}),
            ('foreign-task', {'taskDigest': 'sha256:' + '0' * 64}),
            ('future-lease', {'leaseExpiresAt': 99999999999}),
            ('bad-invocation', {'invocationId': '../outside'}),
            ('extra-field', {'permissions': 'write'}),
        ]:
            project, base, claim = fresh(label)
            path = base / 'claim.json'
            value = json.loads(path.read_text())
            value.update(mutation)
            path.write_text(json.dumps(value))
            rejected(lambda: w.claim_task(str(project), str(pp), str(tp)), '')
        policy = w.load_policy()
        policy['mappings'] = [m for m in policy['mappings'] if m['modelTier'] != 'full']
        rejected(lambda: w.policy_mapping(policy, 'claude', 'full', 'security', 'high'), 'no unique')
        print('claim tampering and missing full mapping passed', flush=True)
        # The destructive cleanup path must reject malformed, partial, foreign
        # or symlink candidates without touching any outside sentinel.
        project, base, claim = fresh('ambiguous-stage')
        sentinel = suite.tmp / 'outside-sentinel'
        sentinel.write_text('UNCHANGED')
        temp = base / '.claim.json.tmp.0123456789abcdef'
        temp.symlink_to(sentinel)
        rejected(lambda: w.claim_task(str(project), str(pp), str(tp)), '')
        assert temp.is_symlink() and sentinel.read_text() == 'UNCHANGED'
        print('ambiguous recovery fails closed without deletion passed', flush=True)
        print('CTX-07B durable recovery regressions passed (zero-token)')
    finally:
        suite.cleanup()


if __name__ == '__main__':
    main()
