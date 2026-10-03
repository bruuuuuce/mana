#!/usr/bin/env python3
"""M08-D action contract acceptance tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "scripts" / "mana-actions.py"
CATALOG = ROOT / "scripts" / "mana-catalog.py"
KNOWLEDGE = ROOT / "scripts" / "mana-knowledge.py"


def revision(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(project: Path, cache: Path, arguments: list[str], expected: int = 0, extra_env: dict[str, str] | None = None) -> dict:
    result = subprocess.run([str(ACTIONS), "--project-root", str(project), *arguments, "--json"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={**os.environ, "MANA_CACHE_HOME": str(cache), **(extra_env or {})})
    assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert str(project) not in result.stdout
    return payload


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mana-actions-test-") as temporary:
        base = Path(temporary)
        project = base / "project"
        cache = base / "cache"
        global_root = project / ".mana" / "global"
        global_root.mkdir(parents=True)
        document = global_root / "architecture.md"
        document.write_text("# Architecture\n\nOriginal.\n", encoding="utf-8")
        proposed = base / "proposed.md"
        proposed.write_text("# Architecture\n\nUpdated atomically.\n", encoding="utf-8")
        before = revision(document)

        applied = invoke(project, cache, ["knowledge-edit", "--scope", "project", "--target", ".mana/global/architecture.md", "--expected-revision", before, "--content-file", str(proposed)])
        assert applied["outcome"] == "applied"
        assert applied["before_revision"] == before
        assert applied["after_revision"] == revision(document)
        assert applied["receipt_artifact"].startswith("mana-cache://")
        repeated = invoke(project, cache, ["knowledge-edit", "--scope", "project", "--target", ".mana/global/architecture.md", "--expected-revision", before, "--content-file", str(proposed)])
        assert repeated == applied
        noop = invoke(project, cache, ["knowledge-edit", "--scope", "project", "--target", ".mana/global/architecture.md", "--expected-revision", revision(document), "--content-file", str(proposed)])
        assert noop["outcome"] == "noop"
        assert noop["before_revision"] == noop["after_revision"] == revision(document)
        assert invoke(project, cache, ["knowledge-edit", "--scope", "project", "--target", ".mana/global/architecture.md", "--expected-revision", revision(document), "--content-file", str(proposed)]) == noop

        conflict_payload = base / "conflict.md"
        conflict_payload.write_text("# Architecture\n\nConflicting proposal retained.\n", encoding="utf-8")
        current = revision(document)
        conflict = invoke(project, cache, ["knowledge-edit", "--scope", "project", "--target", ".mana/global/architecture.md", "--expected-revision", "sha256:" + "0" * 64, "--content-file", str(conflict_payload)], expected=7)
        assert conflict["outcome"] == "conflict" and conflict["after_revision"] == current
        assert document.read_text(encoding="utf-8") == proposed.read_text(encoding="utf-8")
        conflict_file = cache / "actions" / "conflicts" / f"{conflict['action_id']}.json"
        stored_proposal = json.loads(conflict_file.read_text(encoding="utf-8"))
        assert stored_proposal["proposed_content"] == conflict_payload.read_text(encoding="utf-8")

        framework = invoke(project, cache, ["knowledge-edit", "--scope", "framework", "--target", "docs/workflow/example.md", "--expected-revision", "sha256:" + "0" * 64, "--content-file", str(proposed)], expected=2)
        assert framework["outcome"] == "validation_failure"

        candidate_root = project / ".mana" / "learning" / "candidates"
        candidate_root.mkdir(parents=True)
        candidate = candidate_root / "learning-deadbeef.json"
        candidate.write_text(json.dumps({"schemaVersion": "2", "candidateId": "learning-deadbeef", "projectScope": "default", "observation": "Repeated timeout", "category": "execution-failure", "evidenceReferences": ["event-1"], "executions": ["execution-1"], "recurrenceCount": 1, "confidence": "low", "possibleImpact": "Review", "counterEvidence": "None", "suggestedDestination": "Service Context update", "status": "candidate", "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z", "lastObservedAt": "2026-01-01T00:00:00Z", "stale": False}) + "\n", encoding="utf-8")
        candidate_before = revision(candidate)
        reviewed = invoke(project, cache, ["project-learning", "--candidate-id", "learning-deadbeef", "--expected-revision", candidate_before, "--disposition", "review"])
        assert reviewed["outcome"] == "applied"
        assert reviewed["details"] == {"disposition": "review", "promotion_performed": False}
        assert json.loads(candidate.read_text(encoding="utf-8"))["status"] == "reviewed"
        assert (project / ".mana" / "learning" / "reviews" / "learning-deadbeef-review.md").is_file()
        assert invoke(project, cache, ["project-learning", "--candidate-id", "learning-deadbeef", "--expected-revision", candidate_before, "--disposition", "review"]) == reviewed

        user_source = base / "user-context"
        user_source.mkdir()
        user_state = base / "user-state"
        signals = user_state / "user-learning" / "signals"
        signals.mkdir(parents=True)
        signal_ids = []
        project_ids = []
        for number in range(1, 4):
            signal_id = f"user-choice-{number:064d}"
            project_id = f"project-{number:064d}"
            signal_ids.append(signal_id)
            project_ids.append(project_id)
            (signals / f"{signal_id}.json").write_text(json.dumps({"schemaVersion": "2", "signalId": signal_id, "sourceProject": {"projectId": project_id, "repositoryRoot": "/fixture"}, "sourceDecision": {"reference": f".mana/features/F/decisions/developer-choice-log.md#choice-{number}", "logPath": ".mana/features/F/decisions/developer-choice-log.md", "line": number, "choiceOrdinal": number, "status": "confirmed", "subject": "Async failure handling", "confirmedChoice": "durable retry", "confirmedBy": "developer"}, "provenance": {"sourceType": "developer-choice-log", "sourceArtifact": {"path": ".mana/features/F/decisions/developer-choice-log.md", "sha256": "0" * 64}, "evidence": ["fixture"]}, "capture": {"processor": "deterministic-developer-choice-log-v1", "modelCalls": 0, "capturedAt": "2026-08-08T00:00:00Z"}}) + "\n", encoding="utf-8")
        learning_env = {"MANA_USER_STATE_HOME": str(user_state), "MANA_USER_CONTEXT_ROOT": str(user_source)}
        aggregate = subprocess.run([str(ROOT / "scripts" / "mana-user-learning.sh"), "--project-root", str(project), "aggregate"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={**os.environ, **learning_env})
        assert aggregate.returncode == 0, (aggregate.stdout, aggregate.stderr)
        cluster_ids = [json.loads(path.read_text(encoding="utf-8"))["clusterId"] for path in sorted((user_state / "user-learning" / "clusters").glob("*.json"))]
        user_candidate_id = "user-context-candidate-" + "1" * 64
        user_candidate = user_state / "user-learning" / "candidates" / f"{user_candidate_id}.json"
        user_candidate.parent.mkdir(parents=True)
        user_candidate_value = {"schemaVersion": "1", "kind": "user-context-candidate", "candidateId": user_candidate_id, "synthesisVersion": "m3-bounded-semantic-synthesis-v1", "lifecycleState": "proposed", "guidance": "Prefer durable recovery.", "scope": "reliability", "sourceClusterIds": cluster_ids, "supportingSignalIds": signal_ids, "supportingProjectIds": project_ids, "counterEvidence": [], "synthesis": {"modelTier": "T1", "provider": "stub", "model": "fixture", "inputFingerprint": "m3-input-" + "2" * 64, "invocation": {"count": 1}, "rationale": "Repeated confirmed choice", "limitations": []}, "createdAt": "2026-08-08T00:00:00Z", "updatedAt": "2026-08-08T00:00:00Z"}
        user_candidate.write_text(json.dumps(user_candidate_value) + "\n", encoding="utf-8")
        user_review = invoke(project, cache, ["user-learning", "--candidate-id", user_candidate_id, "--expected-revision", revision(user_candidate), "--disposition", "accept"], extra_env=learning_env)
        assert user_review["outcome"] == "applied"
        assert user_review["details"]["promotion_required"] is True
        assert user_review["details"]["promotion_performed"] is False
        review_id = user_review["details"]["review_id"]
        review_file = user_state / "user-learning" / "reviews" / f"{review_id}.json"
        reviewed_candidate_ids = {"rejected": "2", "deferred": "3", "edited": "4"}
        for label, digit in reviewed_candidate_ids.items():
            candidate_id = "user-context-candidate-" + digit * 64
            candidate_path = user_state / "user-learning" / "candidates" / f"{candidate_id}.json"
            candidate_path.write_text(json.dumps({**user_candidate_value, "candidateId": candidate_id}) + "\n", encoding="utf-8")
            disposition = {"rejected": "reject", "deferred": "defer", "edited": "edit-and-accept"}[label]
            arguments = ["user-learning", "--candidate-id", candidate_id, "--expected-revision", revision(candidate_path), "--disposition", disposition]
            if disposition == "edit-and-accept":
                arguments.extend(["--guidance", "Prefer bounded durable recovery.", "--review-scope", "resilience"])
            receipt_value = invoke(project, cache, arguments, extra_env=learning_env)
            assert receipt_value["outcome"] == "applied"
            assert receipt_value["details"]["promotion_performed"] is False
            assert receipt_value["details"]["promotion_required"] is (disposition == "edit-and-accept")
            if disposition == "edit-and-accept":
                edited_review = json.loads((user_state / "user-learning" / "reviews" / f"{receipt_value['details']['review_id']}.json").read_text(encoding="utf-8"))
                assert edited_review["action"] == "EDIT_AND_ACCEPT"
                assert edited_review["reviewedGuidance"] == "Prefer bounded durable recovery."
                assert edited_review["reviewedScope"] == "resilience"
        for script in (CATALOG, KNOWLEDGE):
            built = subprocess.run(
                [str(script), "--project-root", str(project), "build", "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "MANA_CACHE_HOME": str(cache), **learning_env},
            )
            assert built.returncode == 0, (built.stdout, built.stderr)
        queued = subprocess.run(
            [str(KNOWLEDGE), "--project-root", str(project), "learning-candidates", "--lifecycle", "reviewed", "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "MANA_CACHE_HOME": str(cache), **learning_env},
        )
        assert queued.returncode == 0, (queued.stdout, queued.stderr)
        queued_user = next(item for item in json.loads(queued.stdout)["candidates"] if item["candidate_id"] == user_candidate_id)
        assert queued_user["promotion_eligible"] is True
        assert queued_user["review_id"] == review_id
        assert queued_user["review_revision"] == revision(review_file)
        for lifecycle, digit in (("rejected", "2"), ("deferred", "3")):
            queue = subprocess.run(
                [str(KNOWLEDGE), "--project-root", str(project), "learning-candidates", "--lifecycle", lifecycle, "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "MANA_CACHE_HOME": str(cache), **learning_env},
            )
            assert queue.returncode == 0, (queue.stdout, queue.stderr)
            candidate_id = "user-context-candidate-" + digit * 64
            reviewed_value = next(item for item in json.loads(queue.stdout)["candidates"] if item["candidate_id"] == candidate_id)
            assert reviewed_value["status"] == lifecycle
            assert reviewed_value["promotion_eligible"] is False
        promoted = invoke(project, cache, ["user-learning-promote", "--review-id", review_id, "--expected-revision", revision(review_file)], extra_env=learning_env)
        assert promoted["outcome"] == "applied"
        assert promoted["details"]["explicit_promotion"] is True
        assert promoted["details"]["refresh_succeeded"] is True
        assert invoke(project, cache, ["user-learning-promote", "--review-id", review_id, "--expected-revision", revision(review_file)], extra_env=learning_env) == promoted

        user_document = user_source / "preferences.md"
        user_document.write_text("# Preferences\n\nOriginal.\n", encoding="utf-8")
        user_proposal = base / "user-proposal.md"
        user_proposal.write_text("# Preferences\n\nExplicitly updated.\n", encoding="utf-8")
        user_env = {"MANA_USER_CONTEXT_ROOT": str(user_source)}
        user_applied = invoke(project, cache, ["knowledge-edit", "--scope", "user", "--target", "preferences.md", "--expected-revision", revision(user_document), "--content-file", str(user_proposal), "--confirm-user-source", str(user_source)], extra_env=user_env)
        assert user_applied["outcome"] == "applied"
        assert user_applied["details"] == {"mirror_refreshed": True, "source_published": True}
        assert user_document.read_text(encoding="utf-8") == user_proposal.read_text(encoding="utf-8")
        mirror = project / ".mana" / "user-context" / "preferences.md"
        assert mirror.read_text(encoding="utf-8") == user_proposal.read_text(encoding="utf-8")
        mirror.parent.chmod(0o755)
        mirror.chmod(0o644)

        partial_project = base / "partial-project"
        partial_mana = partial_project / ".mana"
        partial_mana.mkdir(parents=True)
        partial_document = user_source / "partial.md"
        partial_document.write_text("# Partial\n\nBefore.\n", encoding="utf-8")
        partial_proposal = base / "partial-proposal.md"
        partial_proposal.write_text("# Partial\n\nSource published.\n", encoding="utf-8")
        partial_mana.chmod(0o500)
        try:
            partial = invoke(partial_project, cache, ["knowledge-edit", "--scope", "user", "--target", "partial.md", "--expected-revision", revision(partial_document), "--content-file", str(partial_proposal), "--confirm-user-source", str(user_source)], expected=3, extra_env=user_env)
        finally:
            partial_mana.chmod(0o700)
        assert partial["outcome"] == "partial_refresh"
        assert partial["details"] == {"mirror_refreshed": False, "source_published": True}
        assert partial_document.read_text(encoding="utf-8") == partial_proposal.read_text(encoding="utf-8")

    print("Mana M08 action contract tests passed")


if __name__ == "__main__":
    main()
