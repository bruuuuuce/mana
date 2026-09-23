#!/usr/bin/env python3
"""Permanent independent CTX-08-R1 adversarial and local invocation tests."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/context-runtime"
FRAMEWORK = FIXTURES / "ctx06a-framework"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


budget = load("ctx08_regression_budget", ROOT / "scripts/lib/context-budget.py")
parser = load("ctx08_regression_usage", ROOT / "scripts/lib/provider-usage-parser.py")
runtime = budget.runtime
POLICY = budget.load_policy()


def rejected(action):
    try:
        action()
    except runtime.ContractError:
        return
    raise AssertionError("expected host validation rejection")


def command(argv, env=None, ok=True):
    result = subprocess.run(list(map(str, argv)), cwd=ROOT, env=env, text=True, capture_output=True)
    if ok:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0, result.stdout
    return result


def policy_validation():
    mutations = [
        lambda p: p.update(policyId="invalid id\n"),
        lambda p: p.update(policyId="valid-id\n"),
        lambda p: p.update(schemaVersion="unknown/v99"),
        lambda p: p.update(unrecognized=True),
        lambda p: p.update(capabilities={"automaticCompactionThreshold":"supported"}),
        lambda p: p.update(profiles={}),
        lambda p: p["profiles"].update(unselected={"modes":{}}),
        lambda p: p["profiles"]["default"]["modes"]["deep"].pop("childExecution"),
        lambda p: p["compactionPrompt"].update(reference="../../outside.txt"),
        lambda p: p["compactionPrompt"].update(reference="missing.txt"),
        lambda p: p["compactionPrompt"].update(version="valid-version\n"),
        lambda p: p["profiles"]["default"].pop("minimumMode"),
    ]
    for value in (-1, 0, 1.5, True, 10**100):
        mutations.append(lambda p, value=value: p["profiles"]["default"]["modes"]["deep"].update(cumulativeInputWarningTokens=value))
    for dimension in budget.NUMERIC_CEILINGS:
        mutations.append(lambda p, dimension=dimension: p["profiles"]["default"]["modes"]["deep"].update({dimension:1}))
        mutations.append(lambda p, dimension=dimension: p["profiles"]["default"]["modes"]["compact"].update({dimension:p["profiles"]["default"]["modes"]["deep"][dimension]+1}))
    for mutate in mutations:
        candidate = copy.deepcopy(POLICY); mutate(candidate)
        rejected(lambda: budget.validate_policy(candidate))
    schema = json.loads((ROOT / "contracts/context-runtime/provider-budget-policy-v1.schema.json").read_text())
    assert all(schema["$defs"]["mode"]["properties"][key]["maximum"] == ceiling for key, ceiling in budget.NUMERIC_CEILINGS.items())
    empty_profiles = copy.deepcopy(POLICY); empty_profiles["profiles"] = {}
    rejected(lambda: budget.validate_schema(empty_profiles,"provider-budget-policy-v1.schema.json"))
    print("Policy schema/all-branch validation and every numeric monotonicity/ceiling passed")


def safe_loading(tmp):
    for case in ("parent", "intermediate", "final", "fifo", "replacement", "read-mutation"):
        root = tmp / case; target = root / budget.POLICY_RELATIVE
        target.parent.mkdir(parents=True); target.write_bytes(runtime.canonical_bytes(POLICY))
        external = tmp / (case+"-external"); external.mkdir()
        if case == "parent":
            shutil.copytree(root / "config", external / "config")
            shutil.rmtree(root / "config"); (root / "config").symlink_to(external / "config", target_is_directory=True)
        elif case == "intermediate":
            shutil.copytree(target.parent, external / "policy")
            shutil.rmtree(target.parent); target.parent.symlink_to(external / "policy", target_is_directory=True)
        elif case == "final":
            shutil.copyfile(target, external / "policy.json"); target.unlink(); target.symlink_to(external / "policy.json")
        elif case == "fifo":
            target.unlink(); os.mkfifo(target)
        else:
            changed = False
            def hook(point):
                nonlocal changed
                if changed: return
                if case == "replacement" and point == "after-parent-component:0":
                    changed = True
                    (root / "config").rename(root / "displaced-config")
                    shutil.copytree(root / "displaced-config", root / "config")
                elif case == "read-mutation" and point == "after-final-open":
                    changed = True; target.write_text('{}')
            runtime._TEST_READ_SYNC_HOOK = hook
        try:
            rejected(lambda: budget.load_policy(root))
        finally:
            runtime._TEST_READ_SYNC_HOOK = None
    rejected(lambda: runtime.safe_read_bytes(tmp / "parent-external/config/context-runtime/provider-budget-policy-v1.json", project_root=ROOT))
    print("FD loading rejected parent/intermediate/final symlinks, FIFO, replacement and read mutation")


def fake_packet():
    return {"executionId":"execution-unit", "profileId":"unit", "provider":"claude", "contextManifest":{"modelEscalationSkills":[]}, "executionEnvelope":{"executionVersion":1,"permissions":{"repositoryWrite":False,"childAgents":False},"humanGates":["GATE-owner-approval"],"requiredSkills":["mandatory-skill"],"requiredEvidence":["EV-mandatory"],"requiredSpecialists":["mandatory-full"]}}


def mode_resolution():
    packet = fake_packet()
    default = budget.mode_decision(POLICY, packet, None)
    assert default["minimumMode"] == default["effectiveMode"] == "standard"
    assert default["decisionSource"] == "host-policy"
    stronger = budget.mode_decision(POLICY, packet, "deep")
    assert stronger["effectiveMode"] == "deep" and stronger["requestedMode"] == "deep"
    assert stronger["decisionSource"] == "human-cli"
    weaker = budget.mode_decision(POLICY, packet, "compact")
    assert weaker["effectiveMode"] == "standard" and weaker["requestedMode"] == "compact"
    packet["contextManifest"]["modelEscalationSkills"] = ["mandatory-full"]
    risk = budget.mode_decision(POLICY, packet, None)
    assert risk["effectiveMode"] == "deep" and risk["decisionSource"] == "profile-risk"
    assert budget.mode_decision(POLICY, packet, "compact")["effectiveMode"] == "deep"
    immutable_packet = copy.deepcopy(packet)
    for requested in budget.MODE_ORDER:
        decision = budget.mode_decision(POLICY, packet, requested)
        resolution = budget.resolve_policy(POLICY,"unit",decision["effectiveMode"])
        exceeded = budget.check_usage_value(resolution,{"usageStatus":"measured","totals":{"input":900000000,"cachedInput":450000000,"uncachedInput":450000000,"output":3,"reasoning":1}})
        assert exceeded["warnings"] and resolution["limits"]["childExecution"] == "disabled"
        assert packet == immutable_packet
        assert not any(key in decision for key in ("permissions","humanGates","requiredSkills","requiredEvidence","requiredSpecialists"))
    print("Host minimum, stronger/weaker requests, profile risk and technical provenance passed")


def accounting(tmp):
    valid = {"input_tokens":10,"cached_input_tokens":2,"uncached_input_tokens":8,"output_tokens":3,"reasoning_tokens":1}
    cases = [(valid,"measured"), ({},"unavailable"), ({"input_tokens":10},"partial")]
    for field in valid:
        for value in (-1, 1.5, 10**100, "10", None, True):
            event = dict(valid); event[field] = value; cases.append((event,"unavailable"))
    cases += [({**valid,"cached_input_tokens":11},"unavailable"), ({**valid,"uncached_input_tokens":11},"unavailable"), ({**valid,"uncached_input_tokens":7},"unavailable")]
    cases += [({**valid,"input":10.0},"unavailable"), ({**valid,"reasoning":True},"unavailable"), ({**valid,"input":11},"unavailable")]
    for index,(usage,status) in enumerate(cases):
        path = tmp / f"usage-{index}.jsonl"
        path.write_text(json.dumps({"type":"turn.completed","usage":usage})+'\n')
        parsed = parser.parse_trace(path)
        assert parsed["usageStatus"] == status, (usage,parsed)
        checked = budget.check_usage_value(budget.resolve_policy(POLICY,"unit","standard"),parsed)
        if status == "unavailable" and usage:
            assert parsed["parseErrors"] > 0 and checked["usageStatus"] == "invalid" and not checked["measured"]
        if status == "partial": assert parsed["totals"]["uncachedInput"] is None
    path = tmp / "overflow.jsonl"
    path.write_text('\n'.join(json.dumps({"usage":{"input_tokens":budget.runtime.USAGE_MAX_INTEGER}}) for _ in range(2)))
    assert parser.parse_trace(path)["parseErrors"] > 0
    for totals in ({"input":-1}, {"input":10,"cachedInput":20}, {"input":10,"cachedInput":2,"uncachedInput":7}):
        check = budget.check_usage_value(budget.resolve_policy(POLICY,"unit","standard"),{"usageStatus":"measured","totals":totals})
        assert check["usageStatus"] == "invalid" and not check["measured"]
    summary = json.loads((FIXTURES / "contracts/valid/usage-summary.json").read_text())
    summary.update(usageStatus="measured",totals={"input":runtime.USAGE_MAX_INTEGER,"cachedInput":0,"uncachedInput":runtime.USAGE_MAX_INTEGER,"output":3,"reasoning":1})
    path = tmp / "complete-domain-limit.json"; path.write_text(json.dumps(summary))
    project = tmp / "aggregate-project"; project.mkdir()
    resolution = budget.resolve_policy(POLICY,"unit","standard")
    resolution["decision"] = budget.mode_decision(POLICY,fake_packet(),None)
    budget.advisory(resolution,str(path),str(project),"invocation-one")
    overflow = budget.advisory(resolution,str(path),str(project),"invocation-two")
    assert overflow["usageCheck"]["usageStatus"] == "invalid" and not overflow["usageCheck"]["measured"]
    repeated = budget.advisory(resolution,str(path),str(project),"invocation-two")
    assert repeated == overflow
    aggregate = json.loads((project / ".mana/runtime/runs/execution-unit/provider-budget-usage-aggregate-v1.json").read_text())
    assert aggregate["parseErrors"] > 0 and len(aggregate["invocationKeys"]) == 2
    assert all(value is None for value in aggregate["totals"].values())
    worker = load("ctx08_worker_accounting",ROOT / "scripts/lib/context-worker-runtime.py")
    records = [{"invocationId":str(i),"status":"complete","totals":summary["totals"],"parseErrors":0} for i in range(2)]
    worker_overflow = worker._aggregate_records("task-unit",records)
    assert worker_overflow["parseErrors"] > 0 and worker_overflow["usageStatus"] == "unavailable"
    print("Numeric accounting valid/partial/missing, all negative/noninteger fields, sum and overflow passed")


def mixed_coverage_accounting(tmp):
    policy = copy.deepcopy(POLICY)
    policy["profiles"]["default"]["minimumMode"] = "compact"
    budget.validate_policy(policy)
    fixture = json.loads((FIXTURES / "contracts/valid/usage-summary.json").read_text())

    def summary_path(project, name, totals, errors=0):
        summary = copy.deepcopy(fixture)
        summary.update(executionId="execution-unit", profileId="unit", totals=totals,
                       parseErrors=errors, usageStatus="unavailable" if errors else runtime.usage_totals_status(totals, 0))
        runtime.validate_model("usage-summary", summary)
        path = project / f"{name}-summary.json"
        path.write_text(json.dumps(summary))
        return str(path)

    for mode in budget.MODE_ORDER:
        resolution = budget.resolve_policy(policy, "unit", mode)
        resolution["decision"] = budget.mode_decision(policy, fake_packet(), mode)
        assert resolution["decision"]["effectiveMode"] == mode
        high = dict(input=900000000, cachedInput=450000000, uncachedInput=450000000, output=5, reasoning=2)
        partial_high = dict.fromkeys(runtime.USAGE_FIELDS)
        partial_high["input"] = high["input"]
        prefixes = {
            "unavailable": (dict.fromkeys(runtime.USAGE_FIELDS), 0),
            "partial": ({**dict.fromkeys(runtime.USAGE_FIELDS), "input": 1}, 0),
            "invalid": (dict.fromkeys(runtime.USAGE_FIELDS), 1),
        }
        for prefix, (totals, errors) in prefixes.items():
            for current_status, current_totals in (("measured", high), ("partial", partial_high)):
                project = tmp / f"mixed-{mode}-{prefix}-{current_status}"
                project.mkdir()
                first = summary_path(project, "first", totals, errors)
                current = summary_path(project, "current", current_totals)
                budget.advisory(resolution, first, str(project), "first")
                result = budget.advisory(resolution, current, str(project), "current")
                assert "cumulative-input" in result["usageCheck"]["warnings"], (mode, prefix, current_status, result)
                invocation = result["invocationUsageCheck"]
                assert invocation["usageStatus"] == current_status and invocation["valid"]
                assert invocation["measured"] == (current_status == "measured")
                assert invocation["recommendation"] == "checkpoint-and-fresh-phase"
                assert set(invocation["warnings"]) <= set(result["usageCheck"]["warnings"])
                assert result["usageCheck"]["recommendation"] == ("human-scope-decision" if errors else "checkpoint-and-fresh-phase")
                assert result["aggregateUsageCheck"]["usageStatus"] == ("invalid" if errors else "partial" if prefix == "partial" else "unavailable")
                if errors:
                    assert not result["usageCheck"]["measured"] and not result["usageCheck"]["valid"]
                else:
                    assert result["usageCheck"]["usageStatus"] == current_status
                run = project / ".mana/runtime/runs/execution-unit"
                record_path = run / "budget-advisories/current.json"
                saved = record_path.read_bytes()
                aggregate_path = run / "provider-budget-usage-aggregate-v1.json"
                aggregate = aggregate_path.read_bytes()
                assert json.loads(aggregate)["totals"]["uncachedInput"] is None
                assert budget.advisory(resolution, current, str(project), "current") == result
                assert aggregate_path.read_bytes() == aggregate and record_path.read_bytes() == saved
                budget.advisory(resolution, current, str(project), "retry")
                assert record_path.read_bytes() == saved
                assert json.loads(aggregate_path.read_bytes())["invocationKeys"] == ["current", "first", "retry"]

        project = tmp / f"cumulative-{mode}"
        project.mkdir()
        low_input = resolution["limits"]["cumulativeInputWarningTokens"] // 2 + 1
        low = dict(input=low_input, cachedInput=0, uncachedInput=low_input, output=1, reasoning=0)
        path = summary_path(project, "low", low)
        budget.advisory(resolution, path, str(project), "first")
        result = budget.advisory(resolution, path, str(project), "second")
        assert "cumulative-input" not in result["invocationUsageCheck"]["warnings"]
        assert "cumulative-input" in result["aggregateUsageCheck"]["warnings"]
        assert "cumulative-input" in result["usageCheck"]["warnings"]
        assert result["usageCheck"]["recommendation"] == "checkpoint-and-fresh-phase"
        for name, errors in (("missing", 0), ("invalid", 1)):
            path = summary_path(project, name, dict.fromkeys(runtime.USAGE_FIELDS), errors)
            result = budget.advisory(resolution, path, str(project), name)
            assert result["invocationUsageCheck"]["usageStatus"] == ("invalid" if errors else "unavailable")
            assert not result["usageCheck"]["measured"]
            assert result["usageCheck"]["recommendation"] == ("human-scope-decision" if errors else None)
    print("Compact/standard/deep mixed coverage, invocation and aggregate warnings, reuse and immutable retry passed")


def authority(tmp):
    production = ROOT / "scripts/run-profile-v2.sh"
    command([production,"execution-override","--framework-root",tmp],ok=False)
    command([ROOT / "scripts/run-context-workers.sh","execution-override","--framework-root",tmp],ok=False)
    # Spoofing argv[0] while sourcing production cannot enter a fixture root.
    for production_path, harness in [(production,ROOT / 'tests/run-profile-v2-test-only.sh'),(ROOT / 'scripts/run-context-workers.sh',ROOT / 'tests/run-context-workers-test-only.sh')]:
        spoofed = command(['bash','-c','source "$1"',harness,production_path],ok=False)
        assert 'canonical test-only source entry point required' in spoofed.stderr
    env = dict(os.environ, MANA_FRAMEWORK_ROOT=str(tmp))
    assert "override is forbidden" in command([production,"execution-override","--project-root",tmp],env,ok=False).stderr
    for variable in budget.FORBIDDEN_ENV:
        command([production,"execution-override","--project-root",tmp],dict(os.environ,**{variable:str(tmp)}),ok=False)
    command([ROOT / "scripts/lib/context-budget.py","resolve",tmp / "copied-policy.json","unit","compact"],ok=False)
    for kind in ("phase-checkpoint", "delegation-task", "context-manifest"):
        original = json.loads((FIXTURES / "contracts/valid" / (kind+'.json')).read_text())
        for key in ("budgetMode", "minimumMode", "budgetPolicy", "frameworkRoot"):
            value = copy.deepcopy(original); value[key] = "caller-owned"
            rejected(lambda: runtime.validate_model(kind,value))
    print("Production CLI/environment/caller policy and model/task/checkpoint overrides rejected")


def invocations(tmp):
    for name,provider,mode,gap in [(mode,"codex",mode,"unknown") for mode in budget.MODE_ORDER] + [(gap,"claude","standard",gap) for gap in ("supported","unknown","unsupported")]:
        base = tmp / (provider+'-'+name); base.mkdir()
        framework = base / "framework"; shutil.copytree(FRAMEWORK,framework)
        policy = copy.deepcopy(POLICY); policy["profiles"]["default"]["minimumMode"] = "compact"
        for i,configured in enumerate(budget.MODE_ORDER,1):
            limits = policy["profiles"]["default"]["modes"][configured]
            limits.update(activeContextWarningTokens=i,cumulativeInputWarningTokens=5*i,cachedInputWarningTokens=i,uncachedInputWarningTokens=4*i)
        policy_path = framework / budget.POLICY_RELATIVE; policy_path.write_text(json.dumps(policy))
        project = base / "project"; workspace = project / ".mana/sessions/ctx06c-fixture"; workspace.mkdir(parents=True)
        (workspace / "manifest.yaml").write_text('workspace_type: "session"\nworkspace_id: "ctx06c-fixture"\n')
        execution = 'execution-budget-'+provider+'-'+name
        command([ROOT / "scripts/mana-context-pipeline.sh","initialize","ctx06c-fixture","--framework-root",framework,"--project-root",project,"--execution-id",execution,"--provider",provider,"--workspace",".mana/sessions/ctx06c-fixture","--objective","Complete both mandatory local phases."])
        budget.HOST_FRAMEWORK_ROOT = framework
        args = argparse.Namespace(execution_id=execution,project_root=str(project),requested_mode=mode,static_signal=[],request_skill=[],deep_load_skill=[])
        resolution = budget.materialize_decision(args)
        decision_path = project / f".mana/runtime/runs/{execution}/provider-budget-decision-v1.json"
        materialized = decision_path.read_bytes()
        policy_path.write_text('{}')
        assert budget.materialize_decision(args) == resolution
        bin_dir = base / "bin"; bin_dir.mkdir()
        shutil.copyfile(FIXTURES / "ctx08-provider-stub.sh",bin_dir / provider); (bin_dir / provider).chmod(0o755)
        state = base / "state"
        env = dict(os.environ,PATH=f"{bin_dir}:{os.environ['PATH']}",CTX08_FIXTURE_ROOT=str(FIXTURES),CTX08_STATE_DIR=str(state),CTX08_COMPACTION_STATUS=gap)
        ran = command([ROOT / "tests/run-profile-v2-test-only.sh",execution,"--project-root",project,"--codex-model","economy-fixture","--codex-full-model","full-fixture"],env)
        assert json.loads(ran.stdout)["providerInvocations"] == 2
        assert decision_path.read_bytes() == materialized
        prompts = [(state / f"prompt.{i}").read_text() for i in (1,2)]
        envelopes = [next(line for line in prompt.splitlines() if line.startswith('executionEnvelope=')) for prompt in prompts]
        assert envelopes[0] == envelopes[1]
        assert '"repositoryWrite":false' in envelopes[0]
        for i in (1,2):
            argv = (state / f"argv.{i}").read_text().splitlines()
            if provider == "claude" and gap == "supported":
                assert argv[argv.index('--autocompact')+1] == str(resolution["limits"]["automaticCompactionThresholdTokens"])
            else: assert '--autocompact' not in argv
            assert not any('compact-prompt' in arg or 'compaction-scope' in arg for arg in argv)
        if provider == "codex":
            assert 'CTX-08 provider budget advisory' in ran.stderr
            assert 'full-fixture' in (state / 'argv.2').read_text()
            aggregate = json.loads((project / f".mana/runtime/runs/{execution}/provider-budget-usage-aggregate-v1.json").read_text())
            assert aggregate["totals"]["input"] == 20 and len(aggregate["invocationKeys"]) == 2
        elif gap != "supported": assert f'automaticCompactionThreshold={gap}' in ran.stderr
        # Completed resume/reuse never starts another provider or changes policy.
        resumed = command([ROOT / "tests/run-profile-v2-test-only.sh",execution,"--project-root",project],env)
        assert json.loads(resumed.stdout)["providerInvocations"] == 0 and decision_path.read_bytes() == materialized
        if name == "compact":
            original = json.loads(materialized); original["requestedMode"] = "deep"; decision_path.write_bytes(runtime.canonical_bytes(original)+b'\n')
            rejected(lambda: budget.materialize_decision(args))
        print(f"{provider}/{name}: real stub argv, fresh/full phase, advisory, mutation and resume passed")
    budget.HOST_FRAMEWORK_ROOT = ROOT


def worker_and_legacy():
    workers = load("ctx08_worker_regressions", ROOT / "tests/context-runtime-workers.py")
    suite = workers.Suite()
    try:
        suite.setup(); env,state = suite.scenario_env("budget-workers")
        result = suite.command(suite.runner_args(),env=env)
        assert json.loads(result.stdout)["mergeStatus"] == "complete"
        run = suite.project / ".mana/runtime/runs/execution-ctx07b"
        decision = (run / "provider-budget-decision-v1.json").read_bytes()
        record = json.loads(decision)
        assert record["effectiveMode"] == "deep" and record["decisionSource"] == "profile-risk"
        assert len(list((run / 'budget-advisories').glob('*.json'))) == 2
        assert 'CTX-08 worker budget advisory' in result.stderr
        reused = suite.command([*suite.runner_args(),"--budget-mode","compact"],env=env)
        assert json.loads(reused.stdout)["mergeStatus"] == "complete"
        assert (run / "provider-budget-decision-v1.json").read_bytes() == decision
        assert len(list((run / 'budget-advisories').glob('*.json'))) == 2
        assert (state / "model.T-full").read_text().strip() == "opus-fixture"
        for task in ('T-economy','T-full'):
            argv = (state / f'argv.{task}').read_text()
            assert 'Agent,Bash,Edit,Write,WebFetch,WebSearch' in argv
        for provider in ('codex','opencode'):
            report_path = suite.tmp / (provider+'-caps.json')
            report = command([ROOT / 'scripts/mana-provider-capabilities.sh',provider,'--fixture',FIXTURES / 'provider-capabilities' / (provider+'-supported')])
            report_path.write_text(report.stdout)
            plan = budget.capability_plan(budget.resolve_policy(POLICY,'unit','standard'),str(report_path))
            assert not plan['controls']['automaticCompactionThreshold']['applied']
        legacy = suite.tmp / 'legacy'; legacy.mkdir()
        shutil.copyfile(FIXTURES / 'provider-usage-stub.sh',suite.bin / 'codex'); (suite.bin / 'codex').chmod(0o755)
        legacy_env = dict(env,MANA_UPDATE_CHECK='off',MANA_PROVIDER_USAGE_SCENARIO='complete')
        command([ROOT / 'scripts/run-profile.sh','mana-help','--project-root',legacy,'--codex','--no-codex-subagents'],legacy_env)
        assert not (legacy / '.mana/runtime/runs').exists()
        assert not [path for path in legacy.rglob('*') if 'budget' in path.name]
        print('Worker decision/advisory/reuse/full isolation and legacy-no-CTX08-state passed')
    finally:
        suite.cleanup()


def main():
    with tempfile.TemporaryDirectory(prefix='mana-context-budgets.') as directory:
        tmp = Path(directory).resolve()
        policy_validation(); safe_loading(tmp); mode_resolution(); accounting(tmp); mixed_coverage_accounting(tmp); authority(tmp); invocations(tmp); worker_and_legacy()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
