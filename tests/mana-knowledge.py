#!/usr/bin/env python3
"""M08-C acceptance tests for scoped, bounded lexical retrieval."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "scripts" / "mana-catalog.py"
KNOWLEDGE = ROOT / "scripts" / "mana-knowledge.py"
EVALUATOR = ROOT / "scripts" / "evaluate-m08-retrieval.py"


def blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def invoke(script: Path, project: Path, cache: Path, arguments: list[str], expected: int = 0, extra_env: dict[str, str] | None = None) -> dict:
    result = subprocess.run([str(script), "--project-root", str(project), *arguments, "--json"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={**os.environ, "MANA_CACHE_HOME": str(cache), **(extra_env or {})})
    assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
    assert str(project) not in result.stdout
    return json.loads(result.stdout)


def write_user_mirror(project: Path, content: str) -> Path:
    root = project / ".mana" / "user-context"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "preferences.md"
    path.write_text(content, encoding="utf-8")
    path.chmod(0o444)
    root.chmod(0o555)
    record = f"{blob(path.read_bytes())}\t{path.stat().st_size}\tpreferences.md\n".encode()
    (project / ".mana" / "user-context-state").write_text(f"schema=1\nstatus=healthy\ndigest={blob(record)}\nfile_count=1\nskipped_count=0\n", encoding="utf-8")
    return path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mana-knowledge-test-") as temporary:
        base = Path(temporary)
        project = base / "project"
        cache = base / "cache"
        global_root = project / ".mana" / "global"
        global_root.mkdir(parents=True)
        architecture = global_root / "architecture.md"
        architecture.write_text("# Payment Architecture\n\nCircuit breaker retries protect the payment gateway.\n\n## Conflicts\n\nDo not retry irreversible captures.\n", encoding="utf-8")
        (global_root / "payment-policy.md").write_text("# Payment policy\n\nIdempotency prevents a duplicate charge and addebito duplicato. Safe retry requires an idempotenza key.\n", encoding="utf-8")
        (global_root / "database-policy.md").write_text("# Database policy\n\nLiquibase migration rollback must account for schema lock timeout.\n", encoding="utf-8")
        (global_root / "integration-map.md").write_text("# Integrations\n\nKafka uses a transactional outbox. Event ordering follows the partition key.\n", encoding="utf-8")
        (global_root / "security-policy.md").write_text("# Security\n\nPCI cardholder logs exclude credentials and redact every authorization token.\n", encoding="utf-8")
        (global_root / "testing-policy.md").write_text("# Testing\n\nDeterministic tests avoid unrelated architecture claims.\n", encoding="utf-8")
        (global_root / "credentials.env").write_text("PASSWORD=never-index-this\n", encoding="utf-8")
        candidate_root = project / ".mana" / "learning" / "candidates"
        candidate_root.mkdir(parents=True)
        candidate = candidate_root / "learning-deadbeef.json"
        candidate.write_text(json.dumps({"schemaVersion": "2", "candidateId": "learning-deadbeef", "status": "candidate", "observation": "Timeout budget repeats during provider calls", "possibleImpact": "Review provider timeout policy", "counterEvidence": "One successful fast call", "suggestedDestination": "Service Context update"}) + "\n", encoding="utf-8")
        rejected_candidate = candidate_root / "learning-rejected.json"
        rejected_candidate.write_text(json.dumps({"schemaVersion": "2", "candidateId": "learning-rejected", "status": "rejected", "observation": "Flaky clock sleep test", "possibleImpact": "No promotion", "counterEvidence": "Deterministic clock fixture exists", "suggestedDestination": "none"}) + "\n", encoding="utf-8")
        user_path = write_user_mirror(project, "# Review preference\n\nPrefer explicit evidence before approval. Use concise commit subject lines without prefixes.\n")
        user_source = base / "user-source"
        user_source.mkdir()
        external_user_path = user_source / "preferences.md"
        external_user_path.write_bytes(user_path.read_bytes())
        user_env = {"MANA_USER_CONTEXT_ROOT": str(user_source)}

        invoke(CATALOG, project, cache, ["build"])
        built = invoke(KNOWLEDGE, project, cache, ["build"])
        assert built["freshness"] == "current"
        assert built["documents"] >= 8
        assert built["fts"] == "sqlite-fts5-bm25/v1"
        repeated = invoke(KNOWLEDGE, project, cache, ["build"])
        assert repeated["indexed_documents"] == 0
        assert repeated["reused_documents"] == repeated["documents"]
        status = invoke(KNOWLEDGE, project, cache, ["status"])
        assert status["freshness"] == "current"
        capabilities = invoke(KNOWLEDGE, project, cache, ["capabilities"], extra_env=user_env)
        assert capabilities["index"]["freshness"] == "current"
        assert capabilities["effective_context_trace"]["status"] == "unavailable"
        assert {item["scope"] for item in capabilities["scopes"]} == {"framework", "user", "project", "candidate"}
        user_capability = next(item for item in capabilities["scopes"] if item["scope"] == "user")
        assert user_capability["editable"] is True
        assert user_capability["source_disclosure"] == str(user_source.resolve())
        document_list = invoke(KNOWLEDGE, project, cache, ["documents", "--scope", "project", "--limit", "3"])
        assert len(document_list["documents"]) == 3
        assert document_list["next_offset"] == 3
        architecture_document = next(item for item in invoke(KNOWLEDGE, project, cache, ["documents", "--scope", "project", "--limit", "50"])["documents"] if item["source_reference"] == ".mana/global/architecture.md")
        document_detail = invoke(KNOWLEDGE, project, cache, ["document", architecture_document["document_id"], "--max-bytes", "512"])
        assert document_detail["document"]["source_reference"] == ".mana/global/architecture.md"
        assert document_detail["document"]["returned_bytes"] <= 512
        user_document = invoke(KNOWLEDGE, project, cache, ["documents", "--scope", "user", "--limit", "50"])["documents"][0]
        user_detail = invoke(KNOWLEDGE, project, cache, ["document", user_document["document_id"], "--max-bytes", "512"], extra_env=user_env)["document"]
        assert user_detail["edit_capability"] == {
            "available": True,
            "expected_revision": user_document["document_revision"],
            "exact_content": external_user_path.read_text(encoding="utf-8"),
            "target": "preferences.md",
            "source_disclosure": str(user_source.resolve()),
        }
        review_queue = invoke(KNOWLEDGE, project, cache, ["learning-candidates", "--lifecycle", "candidate"])
        assert [item["candidate_id"] for item in review_queue["candidates"]] == ["learning-deadbeef"]
        assert review_queue["candidates"][0]["promotion_eligible"] is False

        evaluation_output = base / "evaluation.json"
        evaluation = subprocess.run([str(EVALUATOR), "--project-root", str(project), "--cache-home", str(cache), "--output", str(evaluation_output)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert evaluation.returncode == 0, (evaluation.stdout, evaluation.stderr)
        evaluation_report = json.loads(evaluation_output.read_text(encoding="utf-8"))
        if report_target := os.environ.get("MANA_M08_EVAL_REPORT"):
            Path(report_target).write_text(json.dumps(evaluation_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        assert evaluation_report["question_count"] == 30
        assert evaluation_report["aggregate"]["freshness_errors"] == 0
        assert evaluation_report["aggregate"]["source_scope_errors"] == 0
        assert evaluation_report["aggregate"]["max_returned_bytes"] <= 4096
        assert evaluation_report["answer_quality_evaluated"] is False
        assert evaluation_report["aggregate"]["mean_recall_at_k"] > 0.5

        project_search = invoke(KNOWLEDGE, project, cache, ["search", "--query", "circuit breaker retries", "--scope", "project", "--lifecycle", "active", "--limit", "3", "--max-bytes", "1024"])
        assert project_search["results"]
        assert all(result["source_scope"] == "project" for result in project_search["results"])
        assert all(result["source_reference"].startswith(".mana/") for result in project_search["results"])
        assert project_search["returned_bytes"] <= 1024
        first_passage = project_search["results"][0]["passage_id"]
        metadata = invoke(KNOWLEDGE, project, cache, ["search", "--query", "circuit breaker retries", "--scope", "project", "--metadata-only"])
        assert all("snippet" not in result for result in metadata["results"])
        detail = invoke(KNOWLEDGE, project, cache, ["passage", first_passage, "--max-bytes", "256"])
        assert detail["passage"]["source_scope"] == "project"
        assert len(detail["passage"]["body"].encode()) <= 256

        hidden_candidate = invoke(KNOWLEDGE, project, cache, ["search", "--query", "timeout budget provider", "--scope", "candidate", "--lifecycle", "active"])
        assert hidden_candidate["results"] == []
        visible_candidate = invoke(KNOWLEDGE, project, cache, ["search", "--query", "timeout budget provider", "--scope", "candidate", "--lifecycle", "candidate"])
        assert visible_candidate["results"]
        assert all(result["lifecycle_state"] == "candidate" for result in visible_candidate["results"])
        user_search = invoke(KNOWLEDGE, project, cache, ["search", "--query", "explicit evidence approval", "--scope", "user", "--lifecycle", "active"])
        assert user_search["results"] and all(result["source_scope"] == "user" for result in user_search["results"])
        framework_search = invoke(KNOWLEDGE, project, cache, ["search", "--query", "bounded explorer retrieval", "--scope", "framework", "--lifecycle", "active"])
        assert framework_search["results"] and all(result["source_reference"].startswith("mana://framework/") for result in framework_search["results"])
        assert "never-index-this" not in json.dumps(project_search)

        architecture.write_text(architecture.read_text(encoding="utf-8") + "\nFreshness mutation.\n", encoding="utf-8")
        stale = invoke(KNOWLEDGE, project, cache, ["search", "--query", "circuit breaker", "--scope", "project"], expected=4)
        assert stale["index"]["freshness"] == "stale" and stale["results"] == []
        invoke(CATALOG, project, cache, ["build"])
        refreshed = invoke(KNOWLEDGE, project, cache, ["build"])
        old_revision = project_search["index"]["revision"]
        conflict = invoke(KNOWLEDGE, project, cache, ["search", "--query", "circuit breaker", "--scope", "project", "--if-revision", old_revision], expected=4)
        assert conflict["gaps"] == [{"code": "revision_precondition_failed"}]
        assert refreshed["revision"] != old_revision

        candidate_value = json.loads(candidate.read_text(encoding="utf-8"))
        candidate_value["status"] = "rejected"
        candidate.write_text(json.dumps(candidate_value) + "\n", encoding="utf-8")
        invoke(CATALOG, project, cache, ["build"])
        invoke(KNOWLEDGE, project, cache, ["build"])
        rejected = invoke(KNOWLEDGE, project, cache, ["search", "--query", "timeout budget provider", "--scope", "candidate", "--lifecycle", "rejected"])
        assert rejected["results"] and all(result["lifecycle_state"] == "rejected" for result in rejected["results"])

        user_path.chmod(0o644)
        user_path.write_text("# Tampered\n\nThis mirror is stale.\n", encoding="utf-8")
        stale_user = invoke(KNOWLEDGE, project, cache, ["status"])
        assert stale_user["freshness"] == "stale"
        invoke(CATALOG, project, cache, ["build"])
        without_user = invoke(KNOWLEDGE, project, cache, ["build"])
        assert {item["code"] for item in without_user["diagnostics"]} == {"user_context_not_current"}
        no_user_result = invoke(KNOWLEDGE, project, cache, ["search", "--query", "explicit evidence approval", "--scope", "user", "--lifecycle", "active"])
        assert no_user_result["results"] == []
        user_path.parent.chmod(0o755)

    print("Mana M08 lexical knowledge retrieval tests passed")


if __name__ == "__main__":
    main()
