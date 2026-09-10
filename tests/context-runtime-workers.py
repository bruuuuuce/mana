#!/usr/bin/env python3
"""CTX-07B fresh host-worker, routing, and isolation regressions."""
from __future__ import annotations

import json
import hashlib
import importlib.util
import os
import signal
import shutil
import stat
import sys
import time
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = ROOT / "tests/fixtures/context-runtime/ctx06a-framework"
FIXTURES = ROOT / "tests/fixtures/context-runtime"
PIPELINE = ROOT / "scripts/mana-context-pipeline.sh"
EVIDENCE = ROOT / "scripts/mana-evidence.sh"
DELEGATION = ROOT / "scripts/mana-context-delegation.sh"
RUNNER = ROOT / "tests/run-context-workers-test-only.sh"
RETAIN_RUNNER = ROOT / "tests/run-context-workers-retain-test-only.sh"
PRODUCTION_RUNNER = ROOT / "scripts/run-context-workers.sh"
EXECUTION = "execution-ctx07b"
WORKSPACE = ".mana/sessions/ctx07b"
PROFILE = "ctx07b-fixture"


class Suite:
    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mana-context-workers.")).resolve()
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        shutil.copy2(FIXTURES / "ctx07b-claude-stub.sh", self.bin / "claude")
        (self.bin / "claude").chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = f"{self.bin}:{self.env['PATH']}"
        self.env["MANA_EVIDENCE_WORKSPACE"] = WORKSPACE
        self.env["CTX07B_FIXTURE_ROOT"] = str(FIXTURES)
        self.evidence_id = ""
        self.sibling_evidence_id = ""
        self.plan: dict[str, Any] = {}
        self.cases = 0

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp)

    def command(
        self, args: list[str], *, ok: bool = True, env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            args, cwd=ROOT, env=self.env if env is None else env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if ok and result.returncode != 0:
            raise AssertionError(
                f"command failed ({result.returncode}): {' '.join(args)}\n{result.stderr}"
            )
        if not ok and result.returncode == 0:
            raise AssertionError(f"command unexpectedly passed: {' '.join(args)}")
        return result

    def write_json(self, name: str, value: Any) -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        return path

    def common(self) -> list[str]:
        return [EXECUTION, "--project-root", str(self.project), "--framework-root", str(FRAMEWORK)]

    def setup(self) -> None:
        workspace = self.project / WORKSPACE
        workspace.mkdir(parents=True)
        (workspace / "manifest.yaml").write_text(
            'workspace_type: "session"\nworkspace_id: "ctx07b"\n', encoding="utf-8"
        )
        inputs = self.project / "inputs"
        inputs.mkdir()
        (inputs / "source.txt").write_text("EVIDENCE-BODY-SENTINEL\nSECOND-BOUNDARY-LINE\n", encoding="utf-8")
        collected = self.command([
            str(EVIDENCE), "--project-root", str(self.project), "collect",
            "--execution", EXECUTION, "--kind", "source", "--source-system", "fixture",
            "--source-locator", "ctx07b-source", "--input", "inputs/source.txt",
            "--media-type", "text/plain",
        ])
        self.evidence_id = json.loads(collected.stdout)["evidenceId"]
        (inputs / "sibling.txt").write_text("SIBLING-EVIDENCE-SENTINEL\n", encoding="utf-8")
        sibling = self.command([
            str(EVIDENCE), "--project-root", str(self.project), "collect",
            "--execution", EXECUTION, "--kind", "source", "--source-system", "fixture",
            "--source-locator", "ctx07b-sibling", "--input", "inputs/sibling.txt",
            "--media-type", "text/plain",
        ])
        self.sibling_evidence_id = json.loads(sibling.stdout)["evidenceId"]
        manifest = f".mana/runtime-evidence/executions/{EXECUTION}/manifest.json"
        self.command([
            str(PIPELINE), "initialize", PROFILE, "--framework-root", str(FRAMEWORK),
            "--project-root", str(self.project), "--execution-id", EXECUTION,
            "--provider", "claude", "--workspace", WORKSPACE,
            "--objective", "PARENT-TRANSCRIPT-SENTINEL must never enter a worker prompt.",
            "--evidence-manifest", manifest, "--evidence-ref", self.evidence_id,
        ])
        self.plan = self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [
                self.task("T-economy", "economy-owner", "Inspect the bounded source evidence.", []),
                self.task("T-full", "full-owner", "Assess the activated high-risk source concern.", ["ctx07b-full-skill"]),
            ],
        }, "plan")
        self.race_plan = self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [
                self.task("T-economy", "economy-owner", "Inspect the bounded source evidence for the concurrency regression.", []),
                self.task("T-full", "full-owner", "Assess the activated concern for the concurrency regression.", ["ctx07b-full-skill"]),
            ],
        }, "race")

    def task(
        self, task_id: str, owner: str, question: str, skills: list[str], *, domain: str = "source",
    ) -> dict[str, Any]:
        return {
            "taskId": task_id,
            "owner": owner,
            "question": question,
            "scope": {
                "domain": domain,
                "subjectKind": "component",
                "subjectId": "ctx07b-boundary",
                "boundaries": [{"kind": "evidence", "ref": self.evidence_id}],
            },
            "taskType": "analyze-source" if domain == "source" else "verify-claim",
            "effectClass": "read",
            "delegationAllowed": False,
            "maxChildDepth": 0,
            "skills": skills,
            "evidenceRefs": [self.evidence_id],
            "evidenceExtracts": [{"evidenceId": self.evidence_id, "selector": "lines:1:1", "maxBytes": 1024}],
            "evidenceGaps": [],
            "expectedOutput": {
                "contract": "mana.context-runtime.delegation-result/v1",
                "sections": [
                    "verifiedFacts", "findings", "assumptions", "inferences",
                    "openQuestions", "evidenceGaps", "artifactRefs", "uncertainty",
                ],
            },
            "stopConditions": ["question-answered", "evidence-unavailable"],
            "limits": {"retrievalCycles": 1},
        }

    def bind_plan(self, draft: dict[str, Any], name: str) -> dict[str, Any]:
        draft_path = self.write_json(f"{name}-draft.json", draft)
        result = self.command([
            str(DELEGATION), "bind-plan", *self.common(), "--draft", str(draft_path),
        ])
        plan = json.loads(result.stdout)
        self.write_json(f"{name}.json", plan)
        return plan

    def runner_args(
        self, plan_name: str = "plan", *, runner: Path = RUNNER,
        project: Path | None = None,
    ) -> list[str]:
        return [
            str(runner), EXECUTION, "--project-root", str(self.project if project is None else project),
            "--plan", str(self.tmp / f"{plan_name}.json"),
            "--profile", PROFILE, "--provider", "claude", "--max-parallel", "2",
        ]

    def worker_root_for(self, project: Path, task: dict[str, Any]) -> Path:
        matches = []
        for worker_root in (project / ".mana/runtime/worker-executions").iterdir():
            claim_path = worker_root / "claim.json"
            if claim_path.is_file() and json.loads(claim_path.read_text())["taskDigest"] == task["taskDigest"]:
                matches.append(worker_root)
        assert len(matches) == 1, (task["taskId"], matches)
        return matches[0]

    def scenario_env(self, state_name: str, **values: str) -> tuple[dict[str, str], Path]:
        state = self.tmp / state_name
        env = self.env.copy()
        env["CTX07B_STATE_DIR"] = str(state)
        env.update(values)
        return env, state

    def successful_workers(self) -> None:
        env, state = self.scenario_env("state-success")
        result = self.command(self.runner_args(), env=env)
        merged = json.loads(result.stdout)
        assert merged["schemaVersion"] == "mana.context-runtime.delegation-merge/v1"
        assert merged["mergeStatus"] == "complete"
        assert [item["taskId"] for item in merged["taskResults"]] == ["T-economy", "T-full"]
        assert (state / "model.T-economy").read_text().strip() == "sonnet-fixture"
        assert (state / "model.T-full").read_text().strip() == "opus-fixture"
        assert (state / "effort.T-economy").read_text().strip() == "medium"
        assert (state / "effort.T-full").read_text().strip() == "high"
        assert (state / "pid.T-economy").read_text() != (state / "pid.T-full").read_text()

        execution_root = self.project / ".mana/runtime/worker-executions"
        completed_roots = [path for path in execution_root.iterdir() if (path / "task-result-head.json").is_file()]
        assert len(completed_roots) == 2
        for worker_root in completed_roots:
            head = json.loads((worker_root / "task-result-head.json").read_text())
            assert (worker_root / head["artifact"]).is_file()
            metrics = list((worker_root / "metrics").glob("I-*.json"))
            assert len(metrics) == 1
            invocation = json.loads(metrics[0].read_text())
            aggregate = json.loads((worker_root / "usage-aggregate.json").read_text())
            assert aggregate["invocationIds"] == [invocation["invocationId"]]
            assert aggregate["invocationCount"] == 1
            assert invocation["rawTraceRetained"] is False
            assert not (worker_root / f"attempts/{invocation['invocationId']}/raw-provider-trace").exists()
            events = [json.loads(path.read_text()) for path in (worker_root / "events").glob("*.json")]
            event_types = {item["eventType"] for item in events}
            assert {"worker.claimed", "worker.started", "worker.result.accepted", "worker.completed"}.issubset(event_types)
            assert all("question" not in item and "prompt" not in item and "response" not in item for item in events)

        tasks = {item["taskId"]: item for item in self.plan["tasks"]}
        for task_id, sibling in (("T-economy", "T-full"), ("T-full", "T-economy")):
            prompt = (state / f"prompt.{task_id}").read_text(encoding="utf-8")
            packet_lines = [
                line for line in prompt.splitlines()
                if line.startswith("workerContextPacket=")
            ]
            assert len(packet_lines) == 1
            packet = json.loads(packet_lines[0][len("workerContextPacket="):])
            assert packet["delegationTask"] == tasks[task_id]
            envelope_path = self.project / f".mana/runtime/runs/{EXECUTION}/execution-envelope-v1.json"
            manifest_path = self.project / f".mana/runtime/runs/{EXECUTION}/context-manifest-v1.json"
            envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_bytes = json.dumps(
                manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            assert packet["governanceEnvelope"] == envelope
            assert packet["contextManifestProjection"]["sourceManifestDigest"] == (
                "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
            )
            assert packet["evidenceRefs"] == [self.evidence_id]
            assert packet["outputContract"] == tasks[task_id]["expectedOutput"]
            assert sibling not in prompt
            assert "PARENT-TRANSCRIPT-SENTINEL" not in prompt
            assert "EVIDENCE-BODY-SENTINEL" not in prompt
            assert "SIBLING-EVIDENCE-SENTINEL" not in prompt
            assert "INACTIVE-SKILL-BODY-SENTINEL" not in prompt
            assert "declaredCandidateSkills" not in prompt
            assert "inactiveSkills" not in prompt
            assert "phaseInput" not in prompt
            assert self.evidence_id in prompt
            if task_id == "T-full":
                assert "ACTIVE-SKILL-BODY-SENTINEL" in prompt
                assert [item["metadata"]["id"] for item in packet["activeSkills"]] == [
                    "ctx07b-full-skill"
                ]
            else:
                assert packet["activeSkills"] == []

            argv = (state / f"argv.{task_id}").read_text().splitlines()
            assert "--effort" in argv
            assert "--model" in argv
            assert "--safe-mode" in argv
            assert "Agent,Bash,Edit,Write,WebFetch,WebSearch" in argv
        self.cases += 1

    def concurrent_runners_converge_per_task(self) -> None:
        env, state = self.scenario_env("state-race")
        args = self.runner_args("race")
        first = subprocess.Popen(args, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        second = subprocess.Popen(args, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out1, err1 = first.communicate(timeout=30)
        out2, err2 = second.communicate(timeout=30)
        assert first.returncode == 0, err1
        assert second.returncode == 0, err2
        assert json.loads(out1)["mergeStatus"] == "complete"
        assert json.loads(out2)["mergeStatus"] == "complete"
        assert sorted((state / "invocations.log").read_text().splitlines()) == ["T-economy", "T-full"]
        execution_root = self.project / ".mana/runtime/worker-executions"
        assert len(list(execution_root.glob("*/task-result-head.json"))) >= 4
        assert len(list(execution_root.glob("*/attempts/*/result.json"))) >= 4
        self.cases += 1

    def distinct_tasks_overlap(self) -> None:
        self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task(f"T-overlap-{i}", f"overlap-owner-{i}",
                                f"Prove worker overlap for independent question {i}.", []) for i in range(2)],
        }, "overlap")
        env, state = self.scenario_env("state-overlap", CTX07B_SCENARIO="parallel")
        result = self.command(self.runner_args("overlap"), env=env)
        assert json.loads(result.stdout)["mergeStatus"] == "complete"
        assert sorted((state / "invocations.log").read_text().splitlines()) == ["T-overlap-0", "T-overlap-1"]
        self.cases += 1

    def capsule_materialization_is_bounded_and_link_safe(self) -> None:
        prepared = self.command([
            str(ROOT / "tests/context-worker-runtime-test-only.py"), "prepare-plan",
            EXECUTION, "--project-root", str(self.project),
            "--plan", str(self.tmp / "plan.json"),
        ])
        packet = json.loads(prepared.stdout)["workers"][0]["contextPacket"]
        packet_path = self.write_json("capsule-packet.json", packet)
        capsule = self.tmp / "private-capsule"
        result = self.command([
            str(ROOT / "tests/context-worker-runtime-test-only.py"), "materialize-capsule",
            "--packet", str(packet_path), "--project-root", str(self.project),
            "--capsule", str(capsule),
        ])
        manifest = json.loads(result.stdout)
        assert len(manifest["evidenceExtracts"]) == 1
        extract = json.loads((capsule / "evidence/extract-0.json").read_text())
        assert extract["content"] == "EVIDENCE-BODY-SENTINEL\n"
        assert extract["provenance"]["evidenceId"] == self.evidence_id
        assert extract["digest"].startswith("sha256:")
        assert self.sibling_evidence_id not in (capsule / "assignment.json").read_text()
        outside = self.tmp / "outside-sentinel"
        outside.write_text("UNCHANGED", encoding="utf-8")
        bad = self.tmp / "bad-capsule"
        bad.symlink_to(outside)
        failed = self.command([
            str(ROOT / "tests/context-worker-runtime-test-only.py"), "materialize-capsule",
            "--packet", str(packet_path), "--project-root", str(self.project),
            "--capsule", str(bad),
        ], ok=False)
        assert "non-symlink" in failed.stderr
        assert outside.read_text() == "UNCHANGED"
        for path in [capsule, *capsule.rglob("*")]:
            path.chmod(0o700 if path.is_dir() else 0o600)
        shutil.rmtree(capsule)
        self.cases += 1

    def high_risk_scope_routes_full(self) -> None:
        plan = self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task(
                "T-security", "security-owner", "Verify the bounded security claim.", [], domain="security"
            )],
        }, "security-plan")
        assert plan["tasks"][0]["skills"] == []
        env, state = self.scenario_env("state-security")
        result = self.command(self.runner_args("security-plan"), env=env)
        assert json.loads(result.stdout)["mergeStatus"] == "complete"
        assert (state / "model.T-security").read_text().strip() == "opus-fixture"
        assert (state / "effort.T-security").read_text().strip() == "high"
        self.cases += 1

    def capability_gap_fails_before_invocation(self) -> None:
        env, state = self.scenario_env(
            "state-capability-gap", CTX07B_CAPABILITY_SET="claude-no-effort"
        )
        result = self.command(self.runner_args(), ok=False, env=env)
        assert "explicitReasoningEffort" in result.stderr
        assert not state.exists()
        self.cases += 1

    def caller_overrides_are_rejected(self) -> None:
        env, state = self.scenario_env("state-cli-override")
        result = self.command(
            [*self.runner_args(), "--claude-model", "caller-model"],
            ok=False, env=env,
        )
        assert "unknown option: --claude-model" in result.stderr
        assert not state.exists()
        env, state = self.scenario_env("state-cli-effort-override")
        result = self.command(
            [*self.runner_args(), "--claude-reasoning-effort", "low"],
            ok=False, env=env,
        )
        assert "unknown option: --claude-reasoning-effort" in result.stderr
        assert not state.exists()
        env, state = self.scenario_env("state-cli-raw-trace-override")
        result = self.command(
            [*self.runner_args(), "--retain-raw-trace"], ok=False, env=env,
        )
        assert "unknown option: --retain-raw-trace" in result.stderr
        assert not state.exists()
        env, state = self.scenario_env(
            "state-env-override", MANA_CLAUDE_MODEL="caller-model"
        )
        result = self.command(self.runner_args(), ok=False, env=env)
        assert "caller worker authority override is forbidden" in result.stderr
        assert not state.exists()
        env, state = self.scenario_env(
            "state-env-legacy-raw-trace-override",
            MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE="true",
        )
        result = self.command(self.runner_args(), ok=False, env=env)
        assert "caller worker authority override is forbidden" in result.stderr
        assert not state.exists()
        env, state = self.scenario_env(
            "state-env-raw-trace-override", MANA_WORKER_RETAIN_RAW_TRACE="true"
        )
        result = self.command(self.runner_args(), ok=False, env=env)
        assert "caller worker authority override is forbidden" in result.stderr
        assert not state.exists()
        env, state = self.scenario_env(
            "state-env-effort-override", MANA_CLAUDE_REASONING_EFFORT="low"
        )
        result = self.command(self.runner_args(), ok=False, env=env)
        assert "caller worker authority override is forbidden" in result.stderr
        assert not state.exists()
        env, state = self.scenario_env(
            "state-env-framework-override", MANA_FRAMEWORK_ROOT=str(self.copied_framework("framework-env-override"))
        )
        result = self.command(self.runner_args(), ok=False, env=env)
        assert "caller worker authority override is forbidden" in result.stderr
        assert not state.exists()

        invalid_task = self.task(
            "T-model-field", "model-owner", "Inspect the bounded source evidence.", []
        )
        invalid_task["model"] = "caller-model"
        draft = self.write_json("model-field-draft.json", {
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [invalid_task],
        })
        result = self.command(
            [str(DELEGATION), "bind-plan", *self.common(), "--draft", str(draft)],
            ok=False,
        )
        assert "invalid field set" in result.stderr
        invalid_task = self.task(
            "T-retain-field", "retain-owner", "Inspect the bounded source evidence.", []
        )
        invalid_task["retainRawTrace"] = True
        draft = self.write_json("retain-field-draft.json", {
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [invalid_task],
        })
        result = self.command(
            [str(DELEGATION), "bind-plan", *self.common(), "--draft", str(draft)],
            ok=False,
        )
        assert "invalid field set" in result.stderr
        self.cases += 10

    def debug_policy_is_materialized_before_invocation(self) -> None:
        framework = self.copied_framework("framework-debug-snapshot")
        spec = importlib.util.spec_from_file_location(
            "ctx07b_debug_snapshot", ROOT / "scripts/lib/context-worker-runtime.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        snapshot = module.materialize_debug_policy(module.load_debug_policy(framework))
        policy_path = framework / "config/context-runtime/worker-debug-policy-v1.json"
        changed = json.loads(policy_path.read_text())
        changed["rawTraceRetention"] = "retain"
        policy_path.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")))
        assert snapshot["retainRawTrace"] is False
        assert module.materialize_debug_policy(module.load_debug_policy(framework))["retainRawTrace"] is True
        self.cases += 1

    def provider_stderr_is_contained(self) -> None:
        plan = self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task(
                "T-stderr-canary", "stderr-owner", "Exercise provider diagnostic containment.", []
            )],
        }, "stderr-canary-plan")
        env, state = self.scenario_env(
            "state-stderr-canary", CTX07B_SCENARIO="stderr-secret"
        )
        result = self.command(
            self.runner_args("stderr-canary-plan", runner=RETAIN_RUNNER),
            ok=False, env=env,
        )
        canary = "PROVIDER-STDERR-SECRET-CANARY"
        assert canary not in result.stdout
        assert canary not in result.stderr
        assert "transport_failure provider=claude invocationId=I-" in result.stderr
        assert "exitStatus=42" in result.stderr
        for base in (self.project, state):
            for path in base.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    assert canary.encode() not in path.read_bytes(), path
        worker_root = self.worker_root_for(self.project, plan["tasks"][0])
        metric = json.loads(next((worker_root / "metrics").glob("I-*.json")).read_text())
        assert metric["status"] == "failed"
        assert metric["rawTraceRetained"] is True
        assert (worker_root / f"attempts/{metric['invocationId']}/raw-provider-trace").is_file()
        assert not any(
            json.loads(path.read_text())["eventType"] == "worker.completed"
            for path in (worker_root / "events").glob("*.json")
        )
        self.cases += 1

    def raw_trace_host_policy_paths(self) -> None:
        def assert_trace(worker_root: Path, status: str) -> tuple[str, Path]:
            metrics = list((worker_root / "metrics").glob("I-*.json"))
            matching = [json.loads(path.read_text()) for path in metrics if json.loads(path.read_text())["status"] == status]
            assert len(matching) == 1, (worker_root, status, matching)
            metric = matching[0]
            assert metric["rawTraceRetained"] is True
            invocation = metric["invocationId"]
            trace = worker_root / f"attempts/{invocation}/raw-provider-trace"
            assert trace.is_file() and not trace.is_symlink()
            assert stat.S_IMODE(trace.stat().st_mode) == 0o600
            assert stat.S_IMODE(trace.parent.stat().st_mode) == 0o700
            aggregate = json.loads((worker_root / "usage-aggregate.json").read_text())
            assert "rawTrace" not in json.dumps(aggregate)
            return invocation, trace

        retained_plan = self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task("T-retain", "retain-owner", "Retain the host debug trace.", [])],
        }, "retain-plan")
        env, state = self.scenario_env("state-retain")
        args = self.runner_args("retain-plan", runner=RETAIN_RUNNER)
        result = self.command(args, env=env)
        assert json.loads(result.stdout)["mergeStatus"] == "complete"
        root = self.worker_root_for(self.project, retained_plan["tasks"][0])
        invocation, trace = assert_trace(root, "complete")
        assert b"structured_output" in trace.read_bytes()
        before_traces = sorted(self.project.glob(".mana/runtime/worker-executions/*/attempts/*/raw-provider-trace"))
        before_invocations = (state / "invocations.log").read_text()
        reused = self.command(args, env=env)
        assert json.loads(reused.stdout)["mergeStatus"] == "complete"
        assert (state / "invocations.log").read_text() == before_invocations
        assert sorted(self.project.glob(".mana/runtime/worker-executions/*/attempts/*/raw-provider-trace")) == before_traces
        assert json.loads((root / "task-result-head.json").read_text())["invocationId"] == invocation

        concurrent_plan = self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task(
                f"T-retain-concurrent-{i}", f"retain-concurrent-owner-{i}",
                f"Retain concurrent host trace {i}.", [],
            ) for i in range(2)],
        }, "retain-concurrent-plan")
        env, _ = self.scenario_env("state-retain-concurrent", CTX07B_SCENARIO="parallel")
        self.command(self.runner_args("retain-concurrent-plan", runner=RETAIN_RUNNER), env=env)
        concurrent_traces = []
        for task in concurrent_plan["tasks"]:
            worker_root = self.worker_root_for(self.project, task)
            concurrent_traces.append(assert_trace(worker_root, "complete")[1])
        assert concurrent_traces[0] != concurrent_traces[1]

        failure_plan = self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task("T-retain-failure", "retain-failure-owner", "Retain failure trace.", [])],
        }, "retain-failure-plan")
        env, _ = self.scenario_env("state-retain-failure", CTX07B_SCENARIO="provider-reject")
        self.command(self.runner_args("retain-failure-plan", runner=RETAIN_RUNNER), ok=False, env=env)
        assert_trace(self.worker_root_for(self.project, failure_plan["tasks"][0]), "failed")

        timeout_plan = self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task("T-retain-timeout", "retain-timeout-owner", "Retain timeout trace.", [])],
        }, "retain-timeout-plan")
        env, _ = self.scenario_env("state-retain-timeout", CTX07B_SCENARIO="timeout")
        timed = self.command(self.runner_args("retain-timeout-plan", runner=RETAIN_RUNNER), ok=False, env=env)
        assert timed.returncode == 124
        assert_trace(self.worker_root_for(self.project, timeout_plan["tasks"][0]), "timed_out")

        interrupt_plan = self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task("T-retain-interrupt", "retain-interrupt-owner", "Retain interruption trace.", [])],
        }, "retain-interrupt-plan")
        env, state = self.scenario_env("state-retain-interrupt", CTX07B_SCENARIO="timeout")
        process = subprocess.Popen(
            self.runner_args("retain-interrupt-plan", runner=RETAIN_RUNNER), cwd=ROOT,
            env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        ready = state / "grandchild.pid"
        deadline = time.monotonic() + 5
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        process.send_signal(signal.SIGTERM)
        _stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 143, stderr
        assert_trace(self.worker_root_for(self.project, interrupt_plan["tasks"][0]), "interrupted")

        for worker_root in (self.project / ".mana/runtime/worker-executions").iterdir():
            for metric_path in (worker_root / "metrics").glob("I-*.json"):
                metric = json.loads(metric_path.read_text())
                trace_path = worker_root / f"attempts/{metric['invocationId']}/raw-provider-trace"
                assert metric["rawTraceRetained"] == trace_path.is_file()
        self.cases += 7

    def copied_framework(self, name: str) -> Path:
        destination = self.tmp / name
        shutil.copytree(FRAMEWORK, destination)
        return destination

    def copied_policy_override_fails_before_invocation(self) -> None:
        framework = self.copied_framework("framework-no-full")
        policy_path = framework / "config/context-runtime/worker-routing-policy-v1.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["mappings"] = [
            item for item in policy["mappings"] if item["modelTier"] != "full"
        ]
        policy_path.write_text(
            json.dumps(policy, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        env, state = self.scenario_env("state-no-full")
        args = [
            str(PRODUCTION_RUNNER), EXECUTION, "--project-root", str(self.project),
            "--framework-root", str(framework), "--plan", str(self.tmp / "plan.json"),
        ]
        result = self.command(args, ok=False, env=env)
        assert "unknown option: --framework-root" in result.stderr
        assert not state.exists()
        self.cases += 1

    def invalid_plan_or_packet_fails_before_invocation(self) -> None:
        tampered = json.loads(json.dumps(self.plan))
        tampered["tasks"][0]["question"] = "Tampered after CTX-07A binding."
        self.write_json("tampered-plan.json", tampered)
        env, state = self.scenario_env("state-tampered-plan")
        result = self.command(self.runner_args("tampered-plan"), ok=False, env=env)
        assert "delegation plan is not valid" in result.stderr
        assert not state.exists()

        self.cases += 1

    def provider_model_rejection_is_transport_failure(self) -> None:
        self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task("T-reject", "reject-owner", "Exercise the fresh provider rejection path.", [])],
        }, "provider-reject-plan")
        env, state = self.scenario_env(
            "state-provider-reject", CTX07B_SCENARIO="provider-reject"
        )
        result = self.command(self.runner_args("provider-reject-plan"), ok=False, env=env)
        assert "transport_failure" in result.stderr
        assert (state / "invocations.log").read_text().splitlines() == ["T-reject"]
        claims = list((self.project / ".mana/runtime/worker-executions").glob("*/claim.json"))
        assert any(json.loads(path.read_text())["terminalStatus"] == "failed" for path in claims)
        self.cases += 1

    def host_parallel_limit_precedes_provider(self) -> None:
        env, state = self.scenario_env("state-limit")
        args = self.runner_args()
        args[args.index("--max-parallel") + 1] = "3"
        result = self.command(args, ok=False, env=env)
        assert "authoritative direct worker limit" in result.stderr
        assert not state.exists()
        self.cases += 1

    def isolation_unavailable_fails_before_provider(self) -> None:
        self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task("T-no-isolation", "isolation-owner", "Exercise unavailable isolation.", [])],
        }, "no-isolation-plan")
        env, state = self.scenario_env(
            "state-no-isolation", MANA_CTX07B_TEST_FORCE_ISOLATION_UNAVAILABLE="1"
        )
        result = self.command(self.runner_args("no-isolation-plan"), ok=False, env=env)
        assert "needs_model_escalation category=worker_isolation_unavailable" in result.stderr
        assert not state.exists()
        self.cases += 1

    def retry_keeps_immutable_invocation_metrics(self) -> None:
        self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task("T-retry-metrics", "retry-owner", "Exercise immutable retry metrics.", [])],
        }, "retry-metrics-plan")
        env, state = self.scenario_env("state-retry-metrics", CTX07B_SCENARIO="provider-reject")
        first = self.command(self.runner_args("retry-metrics-plan"), ok=False, env=env)
        assert "transport_failure" in first.stderr
        env["CTX07B_SCENARIO"] = "complete"
        second = self.command(self.runner_args("retry-metrics-plan"), env=env)
        assert json.loads(second.stdout)["mergeStatus"] == "complete"
        assert (state / "invocations.log").read_text().splitlines() == ["T-retry-metrics", "T-retry-metrics"]
        candidates = []
        for worker_root in (self.project / ".mana/runtime/worker-executions").iterdir():
            aggregate_path = worker_root / "usage-aggregate.json"
            if aggregate_path.is_file():
                aggregate = json.loads(aggregate_path.read_text())
                if aggregate["invocationCount"] == 2:
                    candidates.append((worker_root, aggregate))
        assert len(candidates) == 1
        worker_root, aggregate = candidates[0]
        assert aggregate["statuses"] == {"complete": 1, "failed": 1}
        assert len(aggregate["invocationIds"]) == 2
        assert len(list((worker_root / "metrics").glob("I-*.json"))) == 2
        self.cases += 1

    def invalid_or_unauthorized_output_is_not_accepted(self) -> None:
        for scenario in ("invalid", "unauthorized", "malformed"):
            name = f"{scenario}-plan"
            task_id = f"T-{scenario}"
            self.bind_plan({
                "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
                "tasks": [self.task(task_id, f"{scenario}-owner", f"Exercise the fresh {scenario} output path.", [])],
            }, name)
            env, _state = self.scenario_env(
                f"state-{scenario}", CTX07B_SCENARIO=scenario
            )
            result = self.command(self.runner_args(name), ok=False, env=env)
            merged = json.loads(result.stdout)
            assert merged["mergeStatus"] == "incomplete"
            assert merged["taskResults"] == []
            assert (_state / "invocations.log").read_text().splitlines() == [task_id]
            run_root = self.project / f".mana/runtime/runs/{EXECUTION}"
            assert not list(run_root.rglob("delegation-result*.json"))
        self.cases += 3

    def state_store_symlinks_fail_closed(self) -> None:
        self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task("T-state-link", "state-owner", "Exercise the state symlink boundary.", [])],
        }, "state-link-plan")
        prepared_result = self.command([
            str(ROOT / "tests/context-worker-runtime-test-only.py"), "prepare-plan",
            EXECUTION, "--project-root", str(self.project), "--plan", str(self.tmp / "state-link-plan.json"),
        ])
        prepared = self.write_json("state-link-prepared.json", json.loads(prepared_result.stdout))
        task = self.write_json("state-link-task.json", json.loads(prepared_result.stdout)["plan"]["tasks"][0])
        state_parent = self.project / ".mana/runtime/worker-executions"
        saved = self.project / ".mana/runtime/worker-executions.saved"
        state_parent.rename(saved)
        outside = self.tmp / "outside-state"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("UNCHANGED", encoding="utf-8")
        state_parent.symlink_to(outside, target_is_directory=True)
        try:
            result = self.command([
                str(ROOT / "tests/context-worker-runtime-test-only.py"), "claim-task",
                "--project-root", str(self.project), "--prepared", str(prepared), "--task", str(task),
            ], ok=False)
            assert "cannot read input" in result.stderr or "directory" in result.stderr
            assert sorted(path.name for path in outside.iterdir()) == ["sentinel"]
            assert sentinel.read_text() == "UNCHANGED"
        finally:
            state_parent.unlink()
            saved.rename(state_parent)
        self.cases += 1

    def timeout_kills_provider_process_tree(self) -> None:
        self.bind_plan({
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [self.task("T-timeout", "timeout-owner", "Exercise process-tree timeout supervision.", [])],
        }, "timeout-plan")
        env, state = self.scenario_env("state-timeout", CTX07B_SCENARIO="timeout")
        result = self.command(self.runner_args("timeout-plan"), ok=False, env=env)
        assert result.returncode == 124, result.stderr
        assert json.loads(result.stdout)["mergeStatus"] == "incomplete"
        pids = [int((state / name).read_text()) for name in ("pid.T-timeout", "child.pid", "grandchild.pid")]
        for pid in pids:
            deadline = time.monotonic() + 3
            while True:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError(f"provider descendant survived timeout: {pid}")
                time.sleep(0.05)
        claims = list((self.project / ".mana/runtime/worker-executions").glob("*/claim.json"))
        assert any(json.loads(path.read_text())["terminalStatus"] == "timed_out" for path in claims)
        self.cases += 1

    def signals_kill_provider_process_tree(self) -> None:
        for label, delivered, expected in (("sigint", signal.SIGINT, 130), ("sigterm", signal.SIGTERM, 143)):
            task_id = f"T-{label}"
            self.bind_plan({
                "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
                "tasks": [self.task(task_id, f"{label}-owner", f"Exercise {label} process-tree supervision.", [])],
            }, f"{label}-plan")
            env, state = self.scenario_env(f"state-{label}", CTX07B_SCENARIO="timeout")
            process = subprocess.Popen(
                self.runner_args(f"{label}-plan"), cwd=ROOT, env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            ready = state / "grandchild.pid"
            deadline = time.monotonic() + 5
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert ready.exists(), process.stderr.read() if process.stderr else "provider did not start"
            process.send_signal(delivered)
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode == expected, (process.returncode, stderr)
            assert stdout == ""
            pids = [int((state / name).read_text()) for name in (f"pid.{task_id}", "child.pid", "grandchild.pid")]
            for pid in pids:
                deadline = time.monotonic() + 3
                while True:
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        break
                    if time.monotonic() >= deadline:
                        raise AssertionError(f"provider descendant survived {label}: {pid}")
                    time.sleep(0.05)
            claims = list((self.project / ".mana/runtime/worker-executions").glob("*/claim.json"))
            assert any(
                json.loads(path.read_text()).get("terminalStatus") == "interrupted"
                and json.loads(path.read_text()).get("taskDigest")
                for path in claims
            )
            self.cases += 1

    def early_parent_exit_drains_descendants(self) -> None:
        for scenario in ("early-exit", "early-failure"):
            task_id = "T-" + scenario
            self.bind_plan({
                "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
                "tasks": [self.task(task_id, scenario + "-owner", "Verify " + scenario + " descendant cleanup.", [])],
            }, scenario)
            env, state = self.scenario_env("state-" + scenario, CTX07B_SCENARIO=scenario)
            result = self.command(self.runner_args(scenario), ok=scenario == "early-exit", env=env)
            assert (state / "invocations.log").read_text().splitlines() == [task_id]
            assert json.loads(result.stdout)["mergeStatus"] == ("complete" if scenario == "early-exit" else "incomplete")
            before = (state / "heartbeat").read_bytes()
            time.sleep(0.2)
            assert (state / "heartbeat").read_bytes() == before
            for name in ("pid." + task_id, "child.pid", "grandchild.pid"):
                pid = int((state / name).read_text())
                deadline = time.monotonic() + 3
                while True:
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        break
                    if time.monotonic() > deadline:
                        raise AssertionError(f"descendant survived {scenario}: {pid}")
                    time.sleep(0.02)
            self.cases += 1

    def result_and_metric_parent_symlinks_fail_closed(self) -> None:
        outside = self.tmp / "outside-publication"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("UNCHANGED", encoding="utf-8")

        def prepared_claim(label: str) -> tuple[Path, Path, dict[str, Any]]:
            task_id = f"T-{label}"
            self.bind_plan({
                "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
                "tasks": [self.task(task_id, f"{label}-owner", f"Exercise {label} state publication.", [])],
            }, f"{label}-plan")
            output = self.command([
                str(ROOT / "tests/context-worker-runtime-test-only.py"), "prepare-plan",
                EXECUTION, "--project-root", str(self.project), "--plan", str(self.tmp / f"{label}-plan.json"),
            ])
            prepared_value = json.loads(output.stdout)
            prepared_path = self.write_json(f"{label}-prepared.json", prepared_value)
            task_path = self.write_json(f"{label}-task.json", prepared_value["plan"]["tasks"][0])
            claim = self.command([
                str(ROOT / "tests/context-worker-runtime-test-only.py"), "claim-task",
                "--project-root", str(self.project), "--prepared", str(prepared_path), "--task", str(task_path),
            ])
            return prepared_path, task_path, json.loads(claim.stdout)

        prepared, task_path, claim = prepared_claim("result-link")
        key = claim["taskExecutionKey"]
        invocation = claim["invocationId"]
        execution_root = self.project / f".mana/runtime/worker-executions/{key}"
        (execution_root / "attempts").symlink_to(outside, target_is_directory=True)
        task = json.loads(task_path.read_text())
        draft = self.write_json("result-link-draft.json", {
            "schemaVersion": "mana.context-runtime.delegation-result-draft/v1", "taskId": task["taskId"],
            "status": "complete", "verifiedFacts": [], "findings": [], "assumptions": [],
            "inferences": [], "openQuestions": [], "evidenceGaps": [], "artifactRefs": [],
            "uncertainty": {"level": "none", "description": None, "evidenceRefs": []},
        })
        bound = self.command([
            str(DELEGATION), "bind-result", *self.common(), "--plan", str(self.tmp / "result-link-plan.json"), "--draft", str(draft),
        ])
        bound_path = self.write_json("result-link-bound.json", json.loads(bound.stdout))
        failed = self.command([
            str(ROOT / "tests/context-worker-runtime-test-only.py"), "publish-task-result",
            "--project-root", str(self.project), "--task-execution-key", key,
            "--invocation-id", invocation, "--result", str(bound_path),
            "--prepared", str(prepared), "--task", str(task_path),
        ], ok=False)
        assert "cannot read input" in failed.stderr or "directory" in failed.stderr
        assert sorted(path.name for path in outside.iterdir()) == ["sentinel"]

        _prepared, _task_path, metric_claim = prepared_claim("metric-link")
        metric_key = metric_claim["taskExecutionKey"]
        metric_root = self.project / f".mana/runtime/worker-executions/{metric_key}"
        (metric_root / "metrics").symlink_to(outside, target_is_directory=True)
        failed = self.command([
            str(ROOT / "tests/context-worker-runtime-test-only.py"), "finalize-task",
            "--project-root", str(self.project), "--task-execution-key", metric_key,
            "--invocation-id", metric_claim["invocationId"], "--status", "failed",
        ], ok=False)
        assert "directory" in failed.stderr or "cannot read input" in failed.stderr
        assert sentinel.read_text() == "UNCHANGED"
        assert sorted(path.name for path in outside.iterdir()) == ["sentinel"]
        self.cases += 2

    def run(self) -> None:
        self.setup()
        self.successful_workers()
        self.concurrent_runners_converge_per_task()
        self.distinct_tasks_overlap()
        self.capsule_materialization_is_bounded_and_link_safe()
        self.high_risk_scope_routes_full()
        self.capability_gap_fails_before_invocation()
        self.caller_overrides_are_rejected()
        self.debug_policy_is_materialized_before_invocation()
        self.provider_stderr_is_contained()
        self.raw_trace_host_policy_paths()
        self.copied_policy_override_fails_before_invocation()
        self.invalid_plan_or_packet_fails_before_invocation()
        self.provider_model_rejection_is_transport_failure()
        self.host_parallel_limit_precedes_provider()
        self.isolation_unavailable_fails_before_provider()
        self.retry_keeps_immutable_invocation_metrics()
        self.invalid_or_unauthorized_output_is_not_accepted()
        self.state_store_symlinks_fail_closed()
        self.timeout_kills_provider_process_tree()
        self.signals_kill_provider_process_tree()
        self.early_parent_exit_drains_descendants()
        self.result_and_metric_parent_symlinks_fail_closed()
        print(f"CTX-07B fresh host-worker regressions passed: {self.cases} cases (provider stub, zero-token)")


def main() -> int:
    suite = Suite()
    try:
        suite.run()
    finally:
        suite.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
