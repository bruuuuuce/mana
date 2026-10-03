#!/usr/bin/env python3
"""Acceptance tests for the M08-E host-owned review inbox."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mana-review-inbox.py"


def invoke(env: dict[str, str], *arguments: str, expected: int = 0) -> dict:
    process = subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.returncode == expected, (arguments, process.returncode, process.stdout, process.stderr)
    return json.loads(process.stdout)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def configuration(
    policy: str,
    budget: int,
    context: str = "ctx-1",
    *,
    repositories: list[str] | None = None,
    organizations: list[str] | None = None,
) -> dict:
    repositories = ["acme/payments"] if repositories is None else repositories
    return {
        "schema": "mana.review-scheduler.config/v1",
        "enabled": True,
        "repositories": repositories,
        "organizations": organizations or [],
        "reviewer": "alice",
        "poll_interval_seconds": 900,
        "maximum_prs_per_cycle": 10,
        "policy": policy,
        "quiet_hours": None,
        "provider_budget": {"maximum_analyses_per_cycle": budget},
        "checkouts": {},
        "context_revisions": {repository: context for repository in repositories},
    }


def discovery(number: int, head: str, title: str = "Bounded review", repository: str = "acme/payments") -> dict:
    return {
        "schema": "mana.review-scheduler.discovery/v1",
        "items": [{
            "repository": repository,
            "number": number,
            "head_sha": head,
            "requested_reviewer": "alice",
            "title": title,
            "url": f"https://example.invalid/{repository}/pull/{number}",
            "updated_at": "2026-09-28T10:00:00Z",
        }],
    }


def analysis(number: int, head: str, status: str = "completed") -> dict:
    finding = {"draft_id": "draft-1", "severity": "high", "title": "Guard the boundary", "body": "A bounded draft finding."}
    return {
        "schema": "mana.review-scheduler.analysis-fixture/v1",
        "runs": [{
            "repository": "acme/payments",
            "number": number,
            "head_sha": head,
            "schema": "mana.review-scheduler.analysis-result/v1",
            "status": status,
            "findings": [finding] if status == "completed" else [],
            "error_code": None if status == "completed" else "offline",
        }],
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mana-review-inbox-") as temporary:
        temp = Path(temporary)
        env = os.environ.copy()
        env["MANA_USER_STATE_HOME"] = str(temp / "state")
        state_root = temp / "state" / "review-scheduler"

        missing = invoke(env, "status", "--json")
        assert missing == {"schema": "mana.review-scheduler.status/v1", "configured": False, "enabled": False, "state": "missing", "policy": None, "credentials_stored": False, "counts": {}}
        assert not state_root.exists(), "missing status must be read-only"

        config_path = temp / "config.json"
        discovery_path = temp / "discovery.json"
        analysis_path = temp / "analysis.json"
        write_json(config_path, configuration("notify-only", 0))
        configured = invoke(env, "configure", "--config", str(config_path), "--json")
        assert configured["policy"] == "notify-only" and configured["credentials_stored"] is False

        head_a = "a" * 40
        write_json(discovery_path, discovery(17, head_a))
        first = invoke(env, "cycle", "--discovery-file", str(discovery_path), "--json")
        assert (first["created"], first["duplicates"], first["analysed"], first["provider_calls"]) == (1, 0, 0, 0)
        database = state_root / "state.sqlite3"
        connection = sqlite3.connect(database)
        assert connection.execute("SELECT value FROM metadata WHERE key='discovery_cursor:repo:acme/payments'").fetchone()[0] == "2026-09-28T10:00:00Z"
        connection.close()
        repeated = invoke(env, "cycle", "--discovery-file", str(discovery_path), "--json")
        assert (repeated["created"], repeated["duplicates"], repeated["provider_calls"]) == (0, 1, 0)
        service_env = env.copy()
        service_env["MANA_REVIEW_SERVICE_TEST_INTERVAL_MS"] = "1"
        hosted = invoke(service_env, "service", "--discovery-file", str(discovery_path), "--max-cycles", "2", "--json")
        assert hosted["outcome"] == "completed" and hosted["cycles"] == 2
        assert hosted["last_cycle"]["duplicates"] == 1 and hosted["credentials_stored"] is False
        items = invoke(env, "inbox", "--json")["items"]
        assert len(items) == 1 and items[0]["status"] == "notified" and items[0]["attempt"] == 0

        head_b = "b" * 40
        write_json(config_path, configuration("analyse", 2, "ctx-2"))
        invoke(env, "configure", "--config", str(config_path), "--json")
        write_json(discovery_path, discovery(17, head_b))
        write_json(analysis_path, analysis(17, head_b))
        analysed = invoke(env, "cycle", "--discovery-file", str(discovery_path), "--analysis-fixture", str(analysis_path), "--json")
        assert (analysed["created"], analysed["analysed"], analysed["provider_calls"]) == (1, 1, 0)
        items = invoke(env, "inbox", "--json")["items"]
        current = next(item for item in items if item["head_sha"] == head_b)
        old = next(item for item in items if item["head_sha"] == head_a)
        assert current["status"] == "completed" and not current["stale"]
        assert old["stale"], "a new head/context identity must stale the old run"
        detail = invoke(env, "show", current["run_id"], "--json")["run"]
        assert detail["findings"][0]["draft_id"] == "draft-1"

        error = invoke(env, "publish", current["run_id"], "--head-sha", head_a, "--draft-revision", current["draft_revision"], "--draft-id", "draft-1", "--fake-result", "published", "--confirm", "--json", expected=2)
        assert error["code"] == "publication precondition failed"
        uncertain = invoke(env, "publish", current["run_id"], "--head-sha", head_b, "--draft-revision", current["draft_revision"], "--draft-id", "draft-1", "--fake-result", "unknown", "--confirm", "--json")
        assert uncertain["outcome"] == "publication_unknown"
        retry_unknown = invoke(env, "publish", current["run_id"], "--head-sha", head_b, "--draft-revision", current["draft_revision"], "--draft-id", "draft-1", "--fake-result", "published", "--confirm", "--json", expected=2)
        assert retry_unknown["code"] == "publication precondition failed"

        # A zero provider budget leaves work queued, so cancellation and retry are explicit.
        write_json(config_path, configuration("analyse", 0, "ctx-3"))
        invoke(env, "configure", "--config", str(config_path), "--json")
        head_c = "c" * 40
        write_json(discovery_path, discovery(18, head_c))
        queued = invoke(env, "cycle", "--discovery-file", str(discovery_path), "--json")
        assert queued["created"] == 1 and queued["analysed"] == 0
        run_c = next(item for item in invoke(env, "inbox", "--status", "queued", "--json")["items"] if item["head_sha"] == head_c)
        assert invoke(env, "cancel", run_c["run_id"], "--json")["outcome"] == "cancelled"
        assert invoke(env, "retry", run_c["run_id"], "--json")["outcome"] == "queued"

        # A failed fixture is retryable and a later cycle may complete it without duplicating work.
        write_json(config_path, configuration("analyse", 1, "ctx-3"))
        invoke(env, "configure", "--config", str(config_path), "--json")
        write_json(analysis_path, analysis(18, head_c, "failed"))
        failed = invoke(env, "cycle", "--discovery-file", str(discovery_path), "--analysis-fixture", str(analysis_path), "--json")
        assert failed["duplicates"] == 1 and failed["analysed"] == 0
        failed_run = invoke(env, "show", run_c["run_id"], "--json")["run"]
        assert failed_run["status"] == "failed" and failed_run["attempt"] == 1
        invoke(env, "retry", run_c["run_id"], "--expected-draft-revision", failed_run["draft_revision"], "--json")
        write_json(analysis_path, analysis(18, head_c))
        recovered = invoke(env, "cycle", "--discovery-file", str(discovery_path), "--analysis-fixture", str(analysis_path), "--json")
        assert recovered["duplicates"] == 1 and recovered["analysed"] == 1

        # The host lock makes concurrent cycles single-owner.
        holding_env = env.copy()
        holding_env["MANA_CATALOG_TEST_HOLD_LOCK_MS"] = "800"
        first_process = subprocess.Popen([str(SCRIPT), "status", "--json"], cwd=ROOT, env=holding_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.15)
        busy = invoke(env, "status", "--json", expected=6)
        assert busy["code"] == "scheduler-busy"
        assert first_process.wait(timeout=5) == 0

        # Offline discovery leaves the durable inbox unchanged.
        before = len(invoke(env, "inbox", "--json")["items"])
        connection = sqlite3.connect(database)
        cursors_before = connection.execute("SELECT key,value FROM metadata WHERE key LIKE 'discovery_cursor:%' ORDER BY key").fetchall()
        connection.close()
        fake_bin = temp / "bin"
        fake_bin.mkdir()
        gh = fake_bin / "gh"
        gh.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        gh.chmod(0o755)
        offline_env = env.copy()
        offline_env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
        offline = invoke(offline_env, "cycle", "--json", expected=2)
        assert offline["code"] == "github-discovery-failed"
        offline_env["MANA_REVIEW_SERVICE_TEST_INTERVAL_MS"] = "1"
        offline_service = invoke(offline_env, "service", "--max-cycles", "2", "--json")
        assert offline_service["cycles"] == 2
        assert offline_service["last_error"]["code"] == "github-discovery-failed"
        assert len(invoke(env, "inbox", "--json")["items"]) == before
        connection = sqlite3.connect(database)
        assert connection.execute("SELECT key,value FROM metadata WHERE key LIKE 'discovery_cursor:%' ORDER BY key").fetchall() == cursors_before
        connection.close()

        # Organization-only configuration admits repositories in that exact owner
        # and records a separate external-state cursor.
        write_json(config_path, configuration("notify-only", 0, repositories=[], organizations=["acme"]))
        configured_org = invoke(env, "configure", "--config", str(config_path), "--json")
        assert configured_org["repositories"] == [] and configured_org["organizations"] == ["acme"]
        write_json(discovery_path, discovery(19, "d" * 40, repository="acme/orders"))
        organization_cycle = invoke(env, "cycle", "--discovery-file", str(discovery_path), "--json")
        assert organization_cycle["created"] == 1 and organization_cycle["provider_calls"] == 0
        connection = sqlite3.connect(database)
        assert connection.execute("SELECT value FROM metadata WHERE key='discovery_cursor:org:acme'").fetchone()[0] == "2026-09-28T10:00:00Z"
        connection.close()

        # Restarted processes see the same durable state, without credentials or prompt/diff storage.
        restarted = invoke(env, "status", "--json")
        assert restarted["configured"] and restarted["counts"]["completed"] == 2
        connection = sqlite3.connect(database)
        sql = "\n".join(row[0] for row in connection.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"))
        columns = {row[1] for row in connection.execute("PRAGMA table_info(inbox)")}
        connection.close()
        assert not ({"token", "credential", "prompt", "diff", "comment_body"} & columns)
        assert "access_token" not in sql.lower()

    print("Mana M08 review inbox tests passed")


if __name__ == "__main__":
    main()
