#!/usr/bin/env python3
"""CTX-07A-R2 adversarial zero-provider regressions."""
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
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DELEGATION = ROOT / "scripts" / "mana-context-delegation.sh"
PIPELINE = ROOT / "scripts" / "mana-context-pipeline.sh"
EVIDENCE = ROOT / "scripts" / "mana-evidence.sh"
FRAMEWORK = ROOT / "tests" / "fixtures" / "context-runtime" / "ctx06a-framework"
EXECUTION = "execution-ctx07a-r1"
WORKSPACE = ".mana/sessions/ctx07a-r1"


def load_delegation() -> Any:
    path = ROOT / "scripts" / "lib" / "context-delegation.py"
    spec = importlib.util.spec_from_file_location("ctx07a_delegation_tests", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import context-delegation.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Suite:
    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mana-context-delegation-r2.")).resolve()
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.sentinel = self.tmp / "provider-invoked"
        self.env = os.environ.copy()
        self.env["MANA_EVIDENCE_WORKSPACE"] = WORKSPACE
        self.env["CTX07A_PROVIDER_SENTINEL"] = str(self.sentinel)
        self.cases = 0
        self.delegation = load_delegation()
        self.source_id = ""
        self.other_source_id = ""
        self.foreign_id = ""
        self.summary_id = ""
        self.partial_id = ""
        self.plan: dict[str, Any] = {}
        self.packet: dict[str, Any] = {}
        self.evidence_manifest: dict[str, Any] | None = None
        self.result_one: dict[str, Any] = {}
        self.result_two: dict[str, Any] = {}

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp)

    def write_json(self, name: str, value: Any) -> Path:
        path = self.tmp / name
        path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
        return path

    def command(
        self, args: list[str], *, ok: bool = True, env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            args,
            cwd=ROOT,
            env=self.env if env is None else env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if ok and completed.returncode != 0:
            raise AssertionError(f"command failed ({completed.returncode}): {' '.join(args)}\n{completed.stderr}")
        if not ok and completed.returncode == 0:
            raise AssertionError(f"command unexpectedly passed: {' '.join(args)}")
        if self.sentinel.exists():
            raise AssertionError("provider/model sentinel was written")
        return completed

    def phase_args(self) -> list[str]:
        return [EXECUTION, "--project-root", str(self.project), "--framework-root", str(FRAMEWORK)]

    def delegation_command(self, action: str, *extra: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        return self.command([str(DELEGATION), action, *self.phase_args(), *extra], ok=ok)

    def case(self, name: str, callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception as error:
            raise AssertionError(f"{name}: {error}") from error
        self.cases += 1

    def rejects(self, callback: Callable[[], Any]) -> None:
        try:
            callback()
        except (self.delegation.runtime.ContractError, AssertionError):
            return
        raise AssertionError("expected rejection")

    def setup(self) -> None:
        workspace = self.project / WORKSPACE
        workspace.mkdir(parents=True)
        (workspace / "manifest.yaml").write_text(
            'workspace_type: "session"\nworkspace_id: "ctx07a-r1"\n', encoding="utf-8"
        )
        inputs = self.project / "inputs"
        inputs.mkdir()
        (inputs / "source.txt").write_text("bounded source evidence\n", encoding="utf-8")
        (inputs / "summary.txt").write_text("bounded summary evidence\n", encoding="utf-8")
        stub_dir = self.tmp / "provider-bin"
        stub_dir.mkdir()
        stub = "#!/usr/bin/env bash\nprintf invoked > \"${CTX07A_PROVIDER_SENTINEL:?}\"\nexit 97\n"
        for executable in ("codex", "claude", "opencode", "curl", "wget", "nc"):
            path = stub_dir / executable
            path.write_text(stub, encoding="utf-8")
            path.chmod(0o755)
        self.env["PATH"] = f"{stub_dir}:{self.env['PATH']}"

        def collect(
            kind: str, locator: str, input_name: str, *extra: str,
            execution: str = EXECUTION, env: dict[str, str] | None = None,
        ) -> str:
            result = self.command([
                str(EVIDENCE), "--project-root", str(self.project), "collect",
                "--execution", execution, "--kind", kind, "--source-system", "fixture",
                "--source-locator", locator, "--input", f"inputs/{input_name}",
                "--media-type", "text/plain", *extra,
            ], env=env)
            return json.loads(result.stdout)["evidenceId"]

        self.source_id = collect("source", "source-r1", "source.txt")
        self.other_source_id = collect("source", "other-source-r2", "source.txt")
        self.summary_id = collect("summary", "summary-r1", "summary.txt")
        self.partial_id = collect(
            "source", "source-partial-r1", "source.txt", "--status", "partial",
            "--error-code", "partial_fixture", "--error-message", "fixture partial",
            "--gap", "missing tail",
        )
        foreign_workspace = ".mana/sessions/ctx07a-r2-foreign"
        foreign_workspace_path = self.project / foreign_workspace
        foreign_workspace_path.mkdir(parents=True)
        (foreign_workspace_path / "manifest.yaml").write_text(
            'workspace_type: "session"\nworkspace_id: "ctx07a-r2-foreign"\n', encoding="utf-8"
        )
        foreign_env = self.env.copy()
        foreign_env["MANA_EVIDENCE_WORKSPACE"] = foreign_workspace
        self.foreign_id = collect(
            "source", "foreign-source-r2", "source.txt", execution="execution-ctx07a-r2-foreign",
            env=foreign_env,
        )
        manifest = f".mana/runtime-evidence/executions/{EXECUTION}/manifest.json"
        self.command([
            str(PIPELINE), "initialize", "ctx06a-fixture", "--framework-root", str(FRAMEWORK),
            "--project-root", str(self.project), "--execution-id", EXECUTION,
            "--provider", "codex", "--workspace", WORKSPACE,
            "--objective", "Classify the bounded delegation fixture.",
            "--target-repository", "mana-fixture", "--target-base", "main",
            "--target-pr-number", "17", "--evidence-manifest", manifest,
            "--evidence-ref", self.source_id, "--evidence-ref", self.other_source_id,
        ])
        self.plan = self.bind_plan(self.base_plan_draft())
        args = argparse.Namespace(
            execution_id=EXECUTION, project_root=str(self.project), framework_root=str(FRAMEWORK),
            static_signal=[], request_skill=[], deep_load_skill=[],
        )
        self.packet, self.evidence_manifest = self.delegation.authoritative_context(args)
        self.result_one = self.bind_result(self.base_result_draft("T-source"), self.plan)
        self.result_two = self.bind_result(self.base_result_draft("T-tests", empty=True), self.plan)

    def task_draft(self, task_id: str, owner: str, question: str) -> dict[str, Any]:
        return {
            "taskId": task_id,
            "owner": owner,
            "question": question,
            "scope": {
                "domain": "source",
                "subjectKind": "component",
                "subjectId": "delegation-boundary",
                "boundaries": [{"kind": "evidence", "ref": self.source_id}],
            },
            "taskType": "analyze-source",
            "effectClass": "read",
            "delegationAllowed": False,
            "maxChildDepth": 0,
            "skills": [],
            "evidenceRefs": [self.source_id],
            "evidenceGaps": [{
                "description": "missing recovery test",
                "kind": "missing-test",
                "impact": "reduces-confidence",
            }],
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

    def base_plan_draft(self) -> dict[str, Any]:
        return {
            "schemaVersion": "mana.context-runtime.delegation-plan-draft/v1",
            "tasks": [
                self.task_draft("T-source", "source-owner", "Does the bounded fixture expose a source risk?"),
                self.task_draft("T-tests", "test-owner", "Is recovery test evidence available for the bounded fixture?"),
            ],
        }

    def claim(self, identifier: str, predicate: str, stance: str, text: str, *, severity: str | None = None, refs: list[str] | None = None) -> dict[str, Any]:
        return {
            "id": identifier,
            "subject": {"domain": "repository", "kind": "component", "identifier": "delegation-boundary"},
            "predicate": predicate,
            "stance": stance,
            "claim": text,
            "severity": severity,
            "evidenceRefs": [self.source_id] if refs is None else refs,
        }

    def base_result_draft(self, task_id: str, *, empty: bool = False) -> dict[str, Any]:
        if empty:
            facts: list[dict[str, Any]] = []
            findings: list[dict[str, Any]] = []
            assumptions: list[dict[str, Any]] = []
            inferences: list[dict[str, Any]] = []
            questions: list[dict[str, Any]] = []
            gaps: list[dict[str, Any]] = []
            artifacts: list[dict[str, Any]] = []
            uncertainty = {"level": "none", "description": None, "evidenceRefs": []}
        else:
            facts = [self.claim("F-source", "is-bounded", "affirmed", "The source evidence is bounded.")]
            findings = [self.claim("D-source", "needs-recovery-test", "affirmed", "Recovery behavior lacks direct test evidence.", severity="warning")]
            assumptions = [self.claim("A-source", "provider-neutral", "uncertain", "The contract remains provider-neutral.", refs=[])]
            inferences = [self.claim("I-source", "preserves-authority", "affirmed", "The packet cannot widen authority.")]
            questions = [{
                "id": "Q-open",
                "subject": {"domain": "test", "kind": "suite", "identifier": "recovery-tests"},
                "question": "Does recovery reject a stale attempt?",
                "evidenceRefs": [self.source_id],
            }]
            gaps = [{
                "description": "missing recovery test",
                "kind": "missing-test",
                "impact": "reduces-confidence",
                "evidenceRefs": [],
            }]
            artifacts = [{"artifactId": "A-report", "kind": "report", "evidenceRefs": [self.source_id]}]
            uncertainty = {"level": "low", "description": "Recovery evidence remains incomplete.", "evidenceRefs": [self.source_id]}
        return {
            "schemaVersion": "mana.context-runtime.delegation-result-draft/v1",
            "taskId": task_id,
            "status": "complete",
            "verifiedFacts": facts,
            "findings": findings,
            "assumptions": assumptions,
            "inferences": inferences,
            "openQuestions": questions,
            "evidenceGaps": gaps,
            "artifactRefs": artifacts,
            "uncertainty": uncertainty,
        }

    def bind_plan(self, draft: dict[str, Any]) -> dict[str, Any]:
        path = self.write_json("plan-draft.json", draft)
        result = self.delegation_command("bind-plan", "--draft", str(path))
        return json.loads(result.stdout)

    def validate_plan_cli(self, plan: dict[str, Any], *, ok: bool) -> None:
        path = self.write_json("candidate-plan.json", plan)
        self.delegation_command("validate-plan", "--plan", str(path), ok=ok)

    def bind_result(self, draft: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        plan_path = self.write_json("bound-plan.json", plan)
        draft_path = self.write_json("result-draft.json", draft)
        result = self.delegation_command("bind-result", "--plan", str(plan_path), "--draft", str(draft_path))
        return json.loads(result.stdout)

    def bind_result_rejected(self, draft: dict[str, Any]) -> subprocess.CompletedProcess[str]:
        plan_path = self.write_json("bound-plan.json", self.plan)
        draft_path = self.write_json("bad-result-draft.json", draft)
        completed = self.delegation_command("bind-result", "--plan", str(plan_path), "--draft", str(draft_path), ok=False)
        assert completed.stdout == ""
        return completed

    def merge(self, results: list[dict[str, Any]], *, ok: bool = True) -> bytes:
        plan_path = self.write_json("merge-plan.json", self.plan)
        args = ["--plan", str(plan_path)]
        for index, result in enumerate(results):
            path = self.write_json(f"merge-result-{index}.json", result)
            args.extend(["--result", str(path)])
        completed = self.delegation_command("merge-results", *args, ok=ok)
        return completed.stdout.encode()

    def binding_cases(self) -> None:
        self.case("valid authoritative plan", lambda: self.validate_plan_cli(self.plan, ok=True))
        for field, value in (
            ("executionId", "execution-foreign"),
            ("executionVersion", self.plan["executionVersion"] + 1),
            ("workspaceId", "W-" + "0" * 64),
            ("profileId", "foreign-profile"),
            ("phaseId", "synthesize"),
            ("attempt", self.plan["attempt"] + 1),
        ):
            def check(field: str = field, value: Any = value) -> None:
                candidate = copy.deepcopy(self.plan)
                candidate[field] = value
                self.validate_plan_cli(candidate, ok=False)
            self.case(f"wrong plan {field}", check)
        for field, value in (
            ("executionId", "execution-foreign"),
            ("executionVersion", self.result_one["executionVersion"] + 1),
            ("workspaceId", "W-" + "0" * 64),
            ("profileId", "foreign-profile"),
            ("phaseId", "synthesize"),
            ("attempt", self.result_one["attempt"] + 1),
            ("planId", "P-" + "0" * 64),
            ("taskDigest", "sha256:" + "0" * 64),
        ):
            def check_result(field: str = field, value: Any = value) -> None:
                candidate = copy.deepcopy(self.result_one)
                candidate[field] = value
                self.merge([candidate, self.result_two], ok=False)
            self.case(f"wrong result {field}", check_result)

        def stale_previous_attempt() -> None:
            current_task = copy.deepcopy(self.plan["tasks"][0])
            current_task["attempt"] = self.result_one["attempt"] + 1
            assert self.evidence_manifest is not None
            self.rejects(lambda: self.delegation.validate_result(
                self.result_one, self.packet, self.plan, current_task, self.evidence_manifest,
            ))
        self.case("same task replayed from previous attempt", stale_previous_attempt)

        def forged_plan_id() -> None:
            candidate = copy.deepcopy(self.plan)
            candidate["planId"] = "P-" + "f" * 64
            for task in candidate["tasks"]:
                task["planId"] = candidate["planId"]
                task["taskDigest"] = self.delegation.task_digest(task)
            self.validate_plan_cli(candidate, ok=False)
        self.case("plan ID must derive from canonical plan", forged_plan_id)

        def forged_task_digest() -> None:
            candidate = copy.deepcopy(self.plan)
            candidate["tasks"][0]["taskDigest"] = "sha256:" + "f" * 64
            self.validate_plan_cli(candidate, ok=False)
        self.case("task digest must derive from canonical task", forged_task_digest)

    def ownership_cases(self) -> None:
        def same_question_other_owner() -> None:
            draft = self.base_plan_draft()
            draft["tasks"][1]["question"] = draft["tasks"][0]["question"]
            draft["tasks"][1]["owner"] = "other-owner"
            self.rejects(lambda: self.bind_plan(draft))
        self.case("same canonical question different owner", same_question_other_owner)

        for name, field, value in (
            ("caller-selected ownership key", "ownershipKey", "O-" + "0" * 64),
            ("tampered question key", "questionKey", "Q-" + "0" * 64),
        ):
            def changed(field: str = field, value: str = value) -> None:
                candidate = copy.deepcopy(self.plan)
                candidate["tasks"][0][field] = value
                self.validate_plan_cli(candidate, ok=False)
            self.case(name, changed)

        def reused_task_id() -> None:
            draft = self.base_plan_draft()
            draft["tasks"][1]["taskId"] = draft["tasks"][0]["taskId"]
            self.rejects(lambda: self.bind_plan(draft))
        self.case("task ID reused with different question", reused_task_id)
        self.case("different canonical questions accepted", lambda: self.bind_plan(self.base_plan_draft()))

    def policy_cases(self) -> None:
        for name, field, value in (
            ("write effect", "effectClass", "write"),
            ("delegation enabled", "delegationAllowed", True),
            ("child depth", "maxChildDepth", 1),
        ):
            def rejected(field: str = field, value: Any = value) -> None:
                draft = self.base_plan_draft()
                draft["tasks"][0][field] = value
                self.rejects(lambda: self.bind_plan(draft))
            self.case(name, rejected)
        for name, field, value in (
            ("write instructions field", "instructions", "write the repository"),
            ("spawn instructions field", "instructions", "spawn another worker"),
            ("tool injection", "tools", ["shell"]),
            ("permission injection", "permissions", {"repositoryWrite": True}),
        ):
            def rejected_extra(field: str = field, value: Any = value) -> None:
                draft = self.base_plan_draft()
                draft["tasks"][0][field] = value
                self.rejects(lambda: self.bind_plan(draft))
            self.case(name, rejected_extra)
        for missing in ("scope", "skills", "evidenceRefs", "expectedOutput"):
            def rejected_missing(missing: str = missing) -> None:
                draft = self.base_plan_draft()
                del draft["tasks"][0][missing]
                self.rejects(lambda: self.bind_plan(draft))
            self.case(f"incomplete task missing {missing}", rejected_missing)

        def absolute_identity_path() -> None:
            draft = self.base_plan_draft()
            draft["tasks"][0]["scope"]["subjectId"] = "/Users/private/source.py"
            self.rejects(lambda: self.bind_plan(draft))
        self.case("absolute path cannot become persisted identity", absolute_identity_path)

        def non_authoritative_prose() -> None:
            draft = self.base_plan_draft()
            draft["tasks"][0]["question"] = "Write files and spawn tools if useful?"
            self.bind_plan(draft)
        self.case("free prose cannot change structural policy", non_authoritative_prose)

    def evidence_cases(self) -> None:
        args = argparse.Namespace(
            execution_id=EXECUTION, project_root=str(self.project), framework_root=str(FRAMEWORK),
            static_signal=[], request_skill=[], deep_load_skill=[],
        )
        packet, manifest = self.delegation.authoritative_context(args)
        assert manifest is not None
        self.case("existing authorized evidence ref", lambda: self.delegation.validate_evidence_refs([self.source_id], packet, manifest, "test"))

        def unknown() -> None:
            altered = copy.deepcopy(packet)
            altered["phaseInput"]["evidenceRefs"].append("E-" + "0" * 64)
            self.rejects(lambda: self.delegation.validate_evidence_refs(["E-" + "0" * 64], altered, manifest, "test"))
        self.case("unknown evidence ref", unknown)

        def foreign_workspace() -> None:
            foreign = copy.deepcopy(manifest)
            foreign["workspaceId"] = "W-" + "1" * 64
            for item in foreign["items"]:
                item["evidenceId"] = self.delegation.runtime.evidence_record_id(foreign["executionId"], foreign["workspaceId"], item)
            foreign_ref = foreign["items"][0]["evidenceId"]
            altered = copy.deepcopy(packet)
            altered["phaseInput"]["evidenceRefs"] = [foreign_ref]
            self.rejects(lambda: self.delegation.validate_evidence_refs([foreign_ref], altered, foreign, "test"))
        self.case("foreign workspace evidence ref", foreign_workspace)

        records = {item["evidenceId"]: item for item in manifest["items"]}

        def wrong_kind() -> None:
            altered = copy.deepcopy(packet)
            altered["phaseInput"]["evidenceRefs"] = [self.summary_id]
            self.rejects(lambda: self.delegation.validate_evidence_refs([self.summary_id], altered, manifest, "test"))
            assert records[self.summary_id]["kind"] == "summary"
        self.case("disallowed evidence kind", wrong_kind)

        def wrong_status() -> None:
            altered = copy.deepcopy(packet)
            altered["phaseInput"]["evidenceRefs"] = [self.partial_id]
            self.rejects(lambda: self.delegation.validate_evidence_refs([self.partial_id], altered, manifest, "test"))
            assert records[self.partial_id]["collectionStatus"] == "partial"
        self.case("disallowed evidence status", wrong_status)
        self.case("textual evidence gap", lambda: self.bind_plan(self.base_plan_draft()))

        for name, mutate in (
            ("oversized evidence gap", lambda gap: gap.__setitem__("description", "x" * 257)),
            ("malformed evidence gap", lambda gap: gap.pop("impact")),
            ("evidence ID used as gap", lambda gap: gap.__setitem__("description", self.source_id)),
        ):
            def rejected_gap(mutate: Callable[[dict[str, Any]], Any] = mutate) -> None:
                draft = self.base_plan_draft()
                mutate(draft["tasks"][0]["evidenceGaps"][0])
                self.rejects(lambda: self.bind_plan(draft))
            self.case(name, rejected_gap)

        def gap_as_fact_proof() -> None:
            draft = self.base_result_draft("T-source")
            draft["verifiedFacts"][0]["evidenceRefs"] = ["E-" + "0" * 64]
            self.bind_result_rejected(draft)
        self.case("gap used as fact proof", gap_as_fact_proof)

    def result_semantic_binding_cases(self) -> None:
        unknown_id = "E-" + "0" * 64

        def unknown_evidence() -> None:
            draft = self.base_result_draft("T-source")
            draft["verifiedFacts"][0]["evidenceRefs"] = [unknown_id]
            self.bind_result_rejected(draft)
        self.case("bind result rejects syntactically valid unknown evidence", unknown_evidence)

        def unauthorized_evidence() -> None:
            draft = self.base_result_draft("T-source")
            draft["verifiedFacts"][0]["evidenceRefs"] = [self.other_source_id]
            self.bind_result_rejected(draft)
        self.case("bind result rejects existing task-unauthorized evidence", unauthorized_evidence)

        def foreign_evidence() -> None:
            draft = self.base_result_draft("T-source")
            draft["verifiedFacts"][0]["evidenceRefs"] = [self.foreign_id]
            self.bind_result_rejected(draft)
        self.case("bind result rejects foreign execution workspace evidence", foreign_evidence)

        for category in (
            "verifiedFacts", "findings", "assumptions", "inferences", "openQuestions",
            "evidenceGaps", "artifactRefs",
        ):
            def duplicate_item(category: str = category) -> None:
                draft = self.base_result_draft("T-source")
                draft[category].append(copy.deepcopy(draft[category][0]))
                self.bind_result_rejected(draft)
            self.case(f"bind result rejects duplicate {category} item IDs", duplicate_item)

        def inconsistent_uncertainty() -> None:
            draft = self.base_result_draft("T-source", empty=True)
            draft["uncertainty"] = {
                "level": "none", "description": "Unexpected uncertainty.", "evidenceRefs": [],
            }
            self.bind_result_rejected(draft)
        self.case("bind result rejects inconsistent none uncertainty", inconsistent_uncertainty)

        def canonical_result_merges() -> None:
            plan_path = self.write_json("canonical-plan.json", self.plan)
            draft = self.base_result_draft("T-source")
            draft_path = self.write_json("canonical-result-draft.json", draft)
            completed = self.delegation_command(
                "bind-result", "--plan", str(plan_path), "--draft", str(draft_path),
            )
            result = json.loads(completed.stdout)
            assert completed.stdout.encode() == self.delegation.runtime.canonical_bytes(result) + b"\n"
            assert result == self.result_one
            self.merge([result, self.result_two])
        self.case("bind result emits canonical valid result accepted by merge", canonical_result_merges)

        def bind_success_implies_merge_acceptance() -> None:
            self.merge([self.result_one, self.result_two])
        self.case("bind success implies merge acceptance without tampering", bind_success_implies_merge_acceptance)

        def failure_hygiene() -> None:
            run_root = self.project / ".mana" / "runtime" / "runs" / EXECUTION
            project_paths_before = sorted(
                path.relative_to(self.project).as_posix() for path in self.project.rglob("*")
            )
            before = {
                path.relative_to(run_root).as_posix(): path.read_bytes()
                for path in run_root.rglob("*") if path.is_file()
            }
            draft = self.base_result_draft("T-source")
            draft["verifiedFacts"][0]["evidenceRefs"] = [unknown_id]
            completed = self.bind_result_rejected(draft)
            after = {
                path.relative_to(run_root).as_posix(): path.read_bytes()
                for path in run_root.rglob("*") if path.is_file()
            }
            project_paths_after = sorted(
                path.relative_to(self.project).as_posix() for path in self.project.rglob("*")
            )
            assert completed.stdout == ""
            assert before == after
            assert project_paths_before == project_paths_after
            assert not self.sentinel.exists()
        self.case("semantic bind failure leaves no output temporary or run mutation", failure_hygiene)

    def result_policy_cases(self) -> None:
        for field, value in (
            ("skills", ["new-skill"]), ("scope", {"domain": "repository"}),
            ("permissions", {"repositoryWrite": True}), ("approval", {"status": "approved"}),
            ("owner", "replacement-owner"), ("transcript", [{"role": "assistant", "content": "raw"}]),
            ("reasoning", "private reasoning"), ("bulkEvidence", "raw payload"),
        ):
            def rejected(field: str = field, value: Any = value) -> None:
                draft = self.base_result_draft("T-source")
                draft[field] = value
                self.bind_result_rejected(draft)
            self.case(f"result rejects {field}", rejected)

        def owner_tamper() -> None:
            result = copy.deepcopy(self.result_one)
            result["owner"] = "replacement-owner"
            self.merge([result, self.result_two], ok=False)
        self.case("bound result cannot change owner", owner_tamper)

    def merge_cases(self) -> None:
        forward = self.merge([self.result_one, self.result_two])
        reverse = self.merge([self.result_two, self.result_one])

        def order_check() -> None:
            assert forward == reverse
        self.case("result order byte identical", order_check)
        merged = json.loads(forward)

        def preservation() -> None:
            assert merged["mergeStatus"] == "complete"
            assert len(merged["taskResults"]) == 2
            assert merged["verifiedFacts"] == self.result_one["verifiedFacts"]
            assert merged["findings"] == self.result_one["findings"]
            assert merged["assumptions"] == self.result_one["assumptions"]
            assert merged["inferences"] == self.result_one["inferences"]
            assert merged["openQuestions"] == self.result_one["openQuestions"]
            assert merged["evidenceGaps"] == self.result_one["evidenceGaps"]
            assert merged["artifactRefs"] == self.result_one["artifactRefs"]
            assert merged["evidenceRefs"] == [self.source_id]
            provenance = merged["verifiedFacts"][0]["provenance"]
            assert provenance["taskId"] == "T-source"
            assert provenance["planId"] == self.plan["planId"]
            assert provenance["sourceResultDigest"] == self.result_one["resultDigest"]
        self.case("lossless merge preservation", preservation)
        self.case("duplicate result rejected", lambda: self.merge([self.result_one, self.result_one], ok=False))

        def unknown() -> None:
            candidate = copy.deepcopy(self.result_one)
            candidate["taskId"] = "T-unknown"
            self.merge([candidate], ok=False)
        self.case("unknown result rejected", unknown)

        missing = json.loads(self.merge([self.result_one]))

        def missing_check() -> None:
            assert missing["mergeStatus"] == "incomplete"
            assert missing["missingTaskIds"] == ["T-tests"]
        self.case("missing result incomplete", missing_check)

        partial_draft = self.base_result_draft("T-tests", empty=True)
        partial_draft["status"] = "partial"
        partial = self.bind_result(partial_draft, self.plan)
        incomplete = json.loads(self.merge([self.result_one, partial]))
        self.case("partial result incomplete", lambda: None if incomplete["mergeStatus"] == "incomplete" else (_ for _ in ()).throw(AssertionError()))

        def conflict_result(stance: str, predicate: str = "is-bounded") -> dict[str, Any]:
            draft = self.base_result_draft("T-tests", empty=True)
            text = "The source evidence is not bounded." if stance == "denied" else "The source evidence is bounded."
            draft["verifiedFacts"] = [self.claim("F-tests", predicate, stance, text)]
            return self.bind_result(draft, self.plan)

        conflicted = json.loads(self.merge([self.result_one, conflict_result("denied")]))

        def conflict_assertions() -> None:
            assert conflicted["mergeStatus"] == "conflicted"
            assert len(conflicted["conflicts"]) == 1
            assert conflicted["conflicts"][0]["stances"] == ["affirmed", "denied"]
            assert len(conflicted["verifiedFacts"]) == 2
            assert {entry["provenance"]["taskId"] for entry in conflicted["conflicts"][0]["claims"]} == {"T-source", "T-tests"}
        self.case("explicit structural conflict", conflict_assertions)

        compatible = json.loads(self.merge([self.result_one, conflict_result("affirmed")]))

        def compatible_check() -> None:
            assert compatible["mergeStatus"] == "complete"
            assert len(compatible["verifiedFacts"]) == 2
            assert not compatible["conflicts"]
        self.case("compatible stances preserved", compatible_check)

        unrelated = json.loads(self.merge([self.result_one, conflict_result("denied", "different-predicate")]))

        def unrelated_check() -> None:
            assert unrelated["mergeStatus"] == "complete"
            assert len(unrelated["verifiedFacts"]) == 2
            assert not unrelated["conflicts"]
        self.case("non-comparable claims preserved", unrelated_check)

    def cardinality_cases(self) -> None:
        def check_category(category: str, factory: Callable[[int], dict[str, Any]]) -> None:
            at_limit = self.base_result_draft("T-source", empty=True)
            limits = {
                "verifiedFacts": self.delegation.LIMITS["claimsPerCategory"],
                "findings": self.delegation.LIMITS["claimsPerCategory"],
                "openQuestions": self.delegation.LIMITS["questions"],
                "evidenceGaps": self.delegation.LIMITS["gaps"],
                "artifactRefs": self.delegation.LIMITS["artifactRefs"],
            }
            maximum = limits[category]
            at_limit[category] = [factory(index) for index in range(maximum)]
            self.bind_result(at_limit, self.plan)
            over = copy.deepcopy(at_limit)
            over[category].append(factory(maximum))
            self.bind_result_rejected(over)

        self.case("facts cardinality exact and over", lambda: check_category(
            "verifiedFacts", lambda index: self.claim(f"F-{index}", f"fact-{index}", "affirmed", f"Fact {index}.")
        ))
        self.case("findings cardinality exact and over", lambda: check_category(
            "findings", lambda index: self.claim(f"D-{index}", f"finding-{index}", "affirmed", f"Finding {index}.", severity="warning")
        ))
        self.case("questions cardinality exact and over", lambda: check_category(
            "openQuestions", lambda index: {
                "id": f"Q-{index}", "subject": {"domain": "test", "kind": "case", "identifier": f"case-{index}"},
                "question": f"Question {index}?", "evidenceRefs": [],
            }
        ))
        self.case("gaps cardinality exact and over", lambda: check_category(
            "evidenceGaps", lambda index: {
                "description": f"Missing evidence {index}", "kind": "missing-test",
                "impact": "reduces-confidence", "evidenceRefs": [],
            }
        ))
        self.case("artifact refs cardinality exact and over", lambda: check_category(
            "artifactRefs", lambda index: {"artifactId": f"A-{index}", "kind": "report", "evidenceRefs": []}
        ))

        def task_count() -> None:
            base_task = self.plan["tasks"][0]
            packet = {
                "executionId": base_task["executionId"], "profileId": base_task["profileId"],
                "currentAttempt": base_task["attempt"],
                "executionEnvelope": {"executionVersion": base_task["executionVersion"], "workspaceId": base_task["workspaceId"]},
                "phase": {"id": base_task["phaseId"], "policy": {"evidenceKinds": ["source"], "evidenceStatuses": ["complete"]}},
                "phaseInput": {"evidenceRefs": []},
                "contextManifest": {"limits": {"directWorkers": self.delegation.LIMITS["tasks"], "retrievalCyclesPerQuestion": 3}, "activatedSkills": []},
            }
            draft = {"schemaVersion": "mana.context-runtime.delegation-plan-draft/v1", "tasks": []}
            for index in range(self.delegation.LIMITS["tasks"]):
                item = self.task_draft(f"T-{index}", f"owner-{index}", f"Distinct bounded question {index}?")
                item["evidenceRefs"] = []
                item["scope"]["boundaries"] = [{"kind": "module", "ref": f"module-{index}"}]
                draft["tasks"].append(item)
            self.delegation.bind_plan(draft, packet, None)
            draft["tasks"].append(copy.deepcopy(draft["tasks"][0]))
            maximum = self.delegation.LIMITS["tasks"]
            draft["tasks"][-1]["taskId"] = f"T-{maximum}"
            draft["tasks"][-1]["owner"] = f"owner-{maximum}"
            draft["tasks"][-1]["question"] = f"Distinct bounded question {maximum}?"
            self.rejects(lambda: self.delegation.bind_plan(draft, packet, None))
        self.case("task count exact and over", task_count)

    def size_cases(self) -> None:
        def boundary(label: str, limit: int) -> None:
            base = {"padding": ""}
            remaining = limit - len(self.delegation.runtime.canonical_bytes(base))
            exact = {"padding": "x" * remaining}
            assert len(self.delegation.runtime.canonical_bytes(exact)) == limit
            self.delegation.enforce_size(label, exact, limit)
            over = {"padding": "x" * (remaining + 1)}
            self.rejects(lambda: self.delegation.enforce_size(label, over, limit))

        for name in ("planBytes", "taskBytes", "resultBytes", "mergeBytes"):
            self.case(f"{name} exact and over", lambda name=name: boundary(name, self.delegation.LIMITS[name]))

        def prose_limit() -> None:
            exact = self.base_plan_draft()
            maximum = self.delegation.LIMITS["proseChars"]
            exact["tasks"][0]["question"] = "x" * maximum
            self.bind_plan(exact)
            over = copy.deepcopy(exact)
            over["tasks"][0]["question"] = "x" * (maximum + 1)
            self.rejects(lambda: self.bind_plan(over))
        self.case("prose exact and over", prose_limit)

        def gap_limit() -> None:
            exact = self.base_plan_draft()
            maximum = self.delegation.LIMITS["gapDescriptionChars"]
            exact["tasks"][0]["evidenceGaps"][0]["description"] = "x" * maximum
            self.bind_plan(exact)
            over = copy.deepcopy(exact)
            over["tasks"][0]["evidenceGaps"][0]["description"] = "x" * (maximum + 1)
            self.rejects(lambda: self.bind_plan(over))
        self.case("gap prose exact and over", gap_limit)

    def isolation_case(self) -> None:
        def check() -> None:
            run_root = self.project / ".mana" / "runtime" / "runs" / EXECUTION
            before = {
                path.relative_to(run_root).as_posix(): path.read_bytes()
                for path in run_root.rglob("*") if path.is_file()
            }
            self.validate_plan_cli(self.plan, ok=True)
            self.merge([self.result_one, self.result_two])
            after = {
                path.relative_to(run_root).as_posix(): path.read_bytes()
                for path in run_root.rglob("*") if path.is_file()
            }
            assert before == after
            assert not self.sentinel.exists()
            source = (ROOT / "scripts" / "lib" / "context-delegation.py").read_text(encoding="utf-8")
            assert "import subprocess" not in source
            assert "import socket" not in source
            assert "run-profile-v2" not in source
        self.case("provider model and CTX-07B isolation", check)

    def run(self) -> None:
        self.setup()
        self.binding_cases()
        self.ownership_cases()
        self.policy_cases()
        self.evidence_cases()
        self.result_policy_cases()
        self.result_semantic_binding_cases()
        self.merge_cases()
        self.cardinality_cases()
        self.size_cases()
        self.isolation_case()
        print(f"CTX-07A-R2 Python regressions passed: {self.cases} cases")


def main() -> int:
    suite = Suite()
    try:
        suite.run()
        return 0
    finally:
        suite.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
