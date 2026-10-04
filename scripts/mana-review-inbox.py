#!/usr/bin/env python3
"""M08-E opt-in, host-owned requested-review inbox state machine."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location("mana_catalog", ROOT / "scripts" / "mana-catalog.py")
assert module_spec and module_spec.loader
catalog = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(catalog)
SCHEMA_VERSION = 1


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def state_root() -> Path:
    if os.environ.get("MANA_USER_STATE_HOME"):
        base = Path(os.environ["MANA_USER_STATE_HOME"])
    elif sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"]) / "Mana" / "State"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "mana"
    if not base.is_absolute():
        raise ValueError("review scheduler state root must be absolute")
    return base / "review-scheduler"


def locations() -> tuple[Path, Path, Path]:
    root = state_root()
    return root, root / "state.sqlite3", root / "scheduler.lock"


def profile_revision() -> str:
    return "sha256:" + hashlib.sha256((ROOT / "profiles" / "requested-pr-review.yaml").read_bytes()).hexdigest()


def connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database, timeout=0)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS inbox(
          run_id TEXT PRIMARY KEY,
          identity_key TEXT NOT NULL UNIQUE,
          repository TEXT NOT NULL,
          pr_number INTEGER NOT NULL,
          head_sha TEXT NOT NULL,
          reviewer TEXT NOT NULL,
          profile_revision TEXT NOT NULL,
          context_revision TEXT NOT NULL,
          title TEXT NOT NULL,
          url TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          status TEXT NOT NULL,
          stale INTEGER NOT NULL DEFAULT 0,
          attempt INTEGER NOT NULL DEFAULT 0,
          lease_until INTEGER,
          findings_json TEXT,
          draft_revision TEXT,
          error_code TEXT,
          publication_status TEXT,
          created_at TEXT NOT NULL,
          changed_at TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS inbox_pr ON inbox(repository,pr_number,created_at);
        """
    )
    values = dict(connection.execute("SELECT key,value FROM metadata"))
    if values and values.get("schema_version") != str(SCHEMA_VERSION):
        raise ValueError("review scheduler schema is unsupported")
    connection.execute("INSERT OR REPLACE INTO metadata VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
    connection.commit()
    return connection


def validate_config(value: dict) -> dict:
    allowed = {"schema", "enabled", "repositories", "organizations", "reviewer", "poll_interval_seconds", "maximum_prs_per_cycle", "policy", "quiet_hours", "provider_budget", "checkouts", "context_revisions"}
    if set(value) - allowed or value.get("schema") != "mana.review-scheduler.config/v1":
        raise ValueError("review scheduler config schema is invalid")
    repositories = value.get("repositories", [])
    organizations = value.get("organizations", [])
    if not isinstance(repositories, list) or any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", item) for item in repositories):
        raise ValueError("repositories must be exact owner/name values")
    if not isinstance(organizations, list) or any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", item) for item in organizations):
        raise ValueError("organizations must be exact owner values")
    if not 1 <= len(repositories) + len(organizations) <= 20 or len(set(repositories)) != len(repositories) or len(set(organizations)) != len(organizations):
        raise ValueError("configuration must contain 1-20 unique repositories or organizations")
    value["repositories"] = repositories
    value["organizations"] = organizations
    reviewer = value.get("reviewer")
    if not isinstance(reviewer, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", reviewer):
        raise ValueError("reviewer identity is invalid")
    if value.get("policy") not in {"notify-only", "analyse"}:
        raise ValueError("policy must be notify-only or analyse")
    if not isinstance(value.get("enabled"), bool) or not 300 <= value.get("poll_interval_seconds", 0) <= 86_400 or not 1 <= value.get("maximum_prs_per_cycle", 0) <= 50:
        raise ValueError("scheduler timing or PR bounds are invalid")
    budget = value.get("provider_budget")
    if not isinstance(budget, dict) or set(budget) != {"maximum_analyses_per_cycle"} or not 0 <= budget["maximum_analyses_per_cycle"] <= 10:
        raise ValueError("provider budget is invalid")
    quiet = value.get("quiet_hours")
    if quiet is not None and (not isinstance(quiet, dict) or set(quiet) != {"start", "end"} or any(not re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", quiet[key]) for key in quiet) or any(int(quiet[key][:2]) > 23 for key in quiet)):
        raise ValueError("quiet hours are invalid")
    checkouts = value.get("checkouts", {})
    admitted = lambda repository: repository in repositories or repository.split("/", 1)[0] in organizations
    if not isinstance(checkouts, dict) or any(not admitted(repository) for repository in checkouts) or any(not isinstance(path, str) or not Path(path).is_absolute() for path in checkouts.values()):
        raise ValueError("checkout mapping is invalid")
    revisions = value.get("context_revisions", {})
    if not isinstance(revisions, dict) or any(not admitted(repository) for repository in revisions) or any(not isinstance(item, str) or len(item) > 128 for item in revisions.values()):
        raise ValueError("context revisions are invalid")
    return value


def configured(connection: sqlite3.Connection) -> dict | None:
    row = connection.execute("SELECT value FROM metadata WHERE key='config'").fetchone()
    if row is None:
        return None
    value = json.loads(row[0])
    value.setdefault("organizations", [])
    return value


def load_discovery(path: Path, config: dict) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "mana.review-scheduler.discovery/v1" or not isinstance(value.get("items"), list):
        raise ValueError("discovery fixture is invalid")
    items = []
    for item in value["items"]:
        if set(item) != {"repository", "number", "head_sha", "requested_reviewer", "title", "url", "updated_at"}:
            raise ValueError("discovery item shape is invalid")
        repository = item["repository"]
        admitted = repository in config["repositories"] or repository.split("/", 1)[0] in config["organizations"]
        if not admitted or item["requested_reviewer"] != config["reviewer"]:
            continue
        if not isinstance(item["number"], int) or item["number"] < 1 or not re.fullmatch(r"[0-9a-f]{40,64}", item["head_sha"]):
            raise ValueError("discovery identity is invalid")
        if not isinstance(item["title"], str) or len(item["title"]) > 256 or not isinstance(item["url"], str) or len(item["url"]) > 1024 or not valid_external_timestamp(item["updated_at"]):
            raise ValueError("discovery metadata exceeds bounds")
        items.append(item)
    return sorted(items, key=lambda item: (item["repository"], item["number"]))[: config["maximum_prs_per_cycle"]]


def valid_external_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 64 or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        return parsed.tzinfo is not None
    except ValueError:
        return False


def cursor_key(kind: str, identity: str) -> str:
    return f"discovery_cursor:{kind}:{identity}"


def live_discovery(connection: sqlite3.Connection, config: dict) -> list[dict]:
    items = []
    targets = [("repo", repository) for repository in config["repositories"]] + [("org", organization) for organization in config["organizations"]]
    for kind, identity in targets:
        repository = identity if kind == "repo" else None
        query = f"{kind}:{identity} is:pr is:open review-requested:{config['reviewer']}"
        cursor = connection.execute("SELECT value FROM metadata WHERE key=?", (cursor_key(kind, identity),)).fetchone()
        if cursor is not None:
            query += f" updated:>={cursor[0]}"
        search = subprocess.run(["gh", "api", "-X", "GET", "search/issues", "-f", f"q={query}", "-f", f"per_page={config['maximum_prs_per_cycle']}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if search.returncode != 0:
            raise ConnectionError("github-discovery-failed")
        for summary in json.loads(search.stdout).get("items", []):
            if kind == "org":
                match = re.fullmatch(r"https://api\.github\.com/repos/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", str(summary.get("repository_url", "")))
                if match is None or match.group(1).split("/", 1)[0] != identity:
                    continue
                repository = match.group(1)
            assert repository is not None
            number = summary.get("number")
            detail = subprocess.run(["gh", "api", "-X", "GET", f"repos/{repository}/pulls/{number}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if detail.returncode != 0:
                raise ConnectionError("github-pr-detail-failed")
            pr = json.loads(detail.stdout)
            requested = {entry.get("login") for entry in pr.get("requested_reviewers", [])}
            if config["reviewer"] not in requested:
                continue
            updated_at = pr.get("updated_at", now())
            if not valid_external_timestamp(updated_at):
                raise ValueError("github discovery timestamp is invalid")
            items.append({"repository": repository, "number": number, "head_sha": pr["head"]["sha"], "requested_reviewer": config["reviewer"], "title": pr.get("title", "")[:256], "url": pr.get("html_url", "")[:1024], "updated_at": updated_at})
    unique = {(item["repository"], item["number"]): item for item in items}
    return sorted(unique.values(), key=lambda item: (item["repository"], item["number"]))[: config["maximum_prs_per_cycle"]]


def run_identity(item: dict, config: dict) -> tuple[str, str]:
    payload = {"repository": item["repository"], "pr_number": item["number"], "head_sha": item["head_sha"], "reviewer": config["reviewer"], "profile_revision": profile_revision(), "context_revision": config.get("context_revisions", {}).get(item["repository"], "none")}
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    return f"review_{digest[:24]}", f"sha256:{digest}"


def discover_cycle(connection: sqlite3.Connection, config: dict, items: list[dict]) -> tuple[int, int]:
    created = duplicates = 0
    profile = profile_revision()
    with connection:
        expired = int(time.time())
        connection.execute("UPDATE inbox SET status='interrupted',error_code='expired-lease',lease_until=NULL,changed_at=? WHERE status='running' AND lease_until<?", (now(), expired))
        for item in items:
            run_id, identity = run_identity(item, config)
            if connection.execute("SELECT 1 FROM inbox WHERE identity_key=?", (identity,)).fetchone():
                duplicates += 1
                continue
            connection.execute("UPDATE inbox SET stale=1,changed_at=? WHERE repository=? AND pr_number=? AND stale=0", (now(), item["repository"], item["number"]))
            status = "notified" if config["policy"] == "notify-only" else "queued"
            stamp = now()
            connection.execute("INSERT INTO inbox(run_id,identity_key,repository,pr_number,head_sha,reviewer,profile_revision,context_revision,title,url,updated_at,status,created_at,changed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (run_id, identity, item["repository"], item["number"], item["head_sha"], config["reviewer"], profile, config.get("context_revisions", {}).get(item["repository"], "none"), item["title"], item["url"], item["updated_at"], status, stamp, stamp))
            created += 1
        for kind, identity in [("repo", repository) for repository in config["repositories"]] + [("org", organization) for organization in config["organizations"]]:
            timestamps = [item["updated_at"] for item in items if (item["repository"] == identity if kind == "repo" else item["repository"].split("/", 1)[0] == identity)]
            if timestamps:
                connection.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)", (cursor_key(kind, identity), max(timestamps)))
    return created, duplicates


def quiet_now(config: dict) -> bool:
    quiet = config.get("quiet_hours")
    if not quiet:
        return False
    value = datetime.now().astimezone().strftime("%H:%M")
    start, end = quiet["start"], quiet["end"]
    return start <= value < end if start < end else value >= start or value < end


def validate_findings(value: dict) -> list[dict]:
    if value.get("schema") != "mana.review-scheduler.analysis-result/v1" or value.get("status") not in {"completed", "failed"}:
        raise ValueError("analysis fixture is invalid")
    findings = value.get("findings", [])
    if not isinstance(findings, list) or len(findings) > 20:
        raise ValueError("analysis findings exceed bounds")
    for finding in findings:
        if set(finding) != {"draft_id", "severity", "title", "body"} or finding["severity"] not in {"low", "medium", "high", "critical"} or any(not isinstance(finding[key], str) for key in ("draft_id", "title", "body")) or len(finding["body"].encode()) > 8192:
            raise ValueError("analysis finding is invalid")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", finding["draft_id"]) or len(finding["title"]) > 256:
            raise ValueError("analysis finding identity exceeds bounds")
    if len({item["draft_id"] for item in findings}) != len(findings):
        raise ValueError("analysis draft identities must be unique")
    return findings


def analyse(connection: sqlite3.Connection, config: dict, fixture: dict | None) -> tuple[int, int]:
    if config["policy"] != "analyse" or quiet_now(config):
        return 0, 0
    completed = 0
    attempted = 0
    limit = config["provider_budget"]["maximum_analyses_per_cycle"]
    for _ in range(limit):
        with connection:
            row = connection.execute("SELECT * FROM inbox WHERE status IN ('queued','interrupted','failed') AND stale=0 ORDER BY created_at,run_id LIMIT 1").fetchone()
            if row is None:
                break
            attempt = row["attempt"] + 1
            connection.execute("UPDATE inbox SET status='running',attempt=?,lease_until=?,changed_at=?,error_code=NULL WHERE run_id=? AND status IN ('queued','interrupted','failed')", (attempt, int(time.time()) + 3600, now(), row["run_id"]))
        result_value = None
        if fixture is not None:
            result_value = next((item for item in fixture.get("runs", []) if item.get("repository") == row["repository"] and item.get("number") == row["pr_number"] and item.get("head_sha") == row["head_sha"]), None)
            if result_value is None:
                result_value = {"schema": "mana.review-scheduler.analysis-result/v1", "status": "failed", "findings": [], "error_code": "fixture-result-missing"}
        else:
            checkout = config.get("checkouts", {}).get(row["repository"])
            if not checkout or not Path(checkout).is_dir():
                result_value = {"schema": "mana.review-scheduler.analysis-result/v1", "status": "failed", "findings": [], "error_code": "checkout-unavailable"}
            else:
                process = subprocess.run(catalog.shell_command(ROOT / "scripts" / "run-profile.sh", ["requested-pr-review", "--project-root", checkout, "--pr", row["url"], "--codex"]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                result_value = {"schema": "mana.review-scheduler.analysis-result/v1", "status": "completed" if process.returncode == 0 else "failed", "findings": [], "error_code": None if process.returncode == 0 else "governed-runner-failed"}
            attempted += 1
        findings = validate_findings(result_value)
        encoded = json.dumps(findings, separators=(",", ":"), sort_keys=True)
        draft_revision = "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
        status = result_value["status"]
        with connection:
            connection.execute("UPDATE inbox SET status=?,lease_until=NULL,findings_json=?,draft_revision=?,error_code=?,changed_at=? WHERE run_id=? AND attempt=? AND status='running'", (status, encoded, draft_revision, result_value.get("error_code"), now(), row["run_id"], attempt))
        completed += status == "completed"
    return completed, attempted


def public_row(row: sqlite3.Row, include_findings: bool = False) -> dict:
    value = {key: row[key] for key in ("run_id", "repository", "pr_number", "head_sha", "reviewer", "profile_revision", "context_revision", "title", "url", "updated_at", "status", "attempt", "draft_revision", "error_code", "publication_status", "created_at", "changed_at")}
    value["stale"] = bool(row["stale"])
    if include_findings:
        value["findings"] = json.loads(row["findings_json"] or "[]")
    return value


def service_configuration() -> dict | None:
    root, database, lock_path = locations()
    root.mkdir(parents=True, exist_ok=True)
    with catalog.lock(lock_path):
        connection = connect(database)
        try:
            return configured(connection)
        finally:
            connection.close()


def run_service(args: argparse.Namespace) -> int:
    """Run bounded scheduler cycles without making Familiar the process host."""
    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    previous_handlers = {
        signum: signal.getsignal(signum)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    for signum in previous_handlers:
        signal.signal(signum, request_stop)
    cycles = 0
    last_cycle: dict | None = None
    last_error: dict | None = None
    outcome = "stopped"
    try:
        while not stop.is_set():
            config = service_configuration()
            if config is None:
                raise ValueError("review scheduler is not configured")
            if not config["enabled"]:
                outcome = "disabled"
                break
            command = [sys.executable, str(Path(__file__).resolve()), "cycle"]
            if args.discovery_file:
                command.extend(["--discovery-file", str(args.discovery_file)])
            if args.analysis_fixture:
                command.extend(["--analysis-fixture", str(args.analysis_fixture)])
            command.append("--json")
            process = subprocess.run(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            cycles += 1
            try:
                response = json.loads(process.stdout)
            except json.JSONDecodeError:
                response = {
                    "schema": "mana.review-scheduler.error/v1",
                    "code": "invalid-cycle-response",
                }
            if process.returncode == 0:
                last_cycle = response
                last_error = None
            else:
                # Offline and transient failures do not destroy durable state
                # or permanently stop the optional host.
                last_error = response
            if args.max_cycles is not None and cycles >= args.max_cycles:
                outcome = "completed"
                break
            interval = config["poll_interval_seconds"]
            override = os.environ.get("MANA_REVIEW_SERVICE_TEST_INTERVAL_MS")
            if override is not None:
                if not override.isdigit() or not 0 <= int(override) <= 1000:
                    raise ValueError("test service interval is invalid")
                interval = int(override) / 1000
            stop.wait(interval)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    print(json.dumps({
        "schema": "mana.review-scheduler.service/v1",
        "outcome": outcome,
        "cycles": cycles,
        "last_cycle": last_cycle,
        "last_error": last_error,
        "credentials_stored": False,
    }, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure"); configure.add_argument("--config", required=True, type=Path); configure.add_argument("--json", action="store_true", required=True)
    status_parser = commands.add_parser("status"); status_parser.add_argument("--json", action="store_true", required=True)
    cycle = commands.add_parser("cycle"); cycle.add_argument("--discovery-file", type=Path); cycle.add_argument("--analysis-fixture", type=Path); cycle.add_argument("--json", action="store_true", required=True)
    service = commands.add_parser("service"); service.add_argument("--discovery-file", type=Path); service.add_argument("--analysis-fixture", type=Path); service.add_argument("--max-cycles", type=int); service.add_argument("--json", action="store_true", required=True)
    inbox = commands.add_parser("inbox"); inbox.add_argument("--status"); inbox.add_argument("--limit", type=int, default=50); inbox.add_argument("--json", action="store_true", required=True)
    show = commands.add_parser("show"); show.add_argument("run_id"); show.add_argument("--json", action="store_true", required=True)
    retry = commands.add_parser("retry"); retry.add_argument("run_id"); retry.add_argument("--expected-draft-revision"); retry.add_argument("--json", action="store_true", required=True)
    cancel = commands.add_parser("cancel"); cancel.add_argument("run_id"); cancel.add_argument("--json", action="store_true", required=True)
    publish = commands.add_parser("publish"); publish.add_argument("run_id"); publish.add_argument("--head-sha", required=True); publish.add_argument("--draft-revision", required=True); publish.add_argument("--draft-id", required=True); publish.add_argument("--fake-result", required=True, choices=("published", "unknown", "failed")); publish.add_argument("--confirm", action="store_true"); publish.add_argument("--json", action="store_true", required=True)
    args = parser.parse_args()
    if args.command == "service":
        if args.max_cycles is not None and not 1 <= args.max_cycles <= 10_000:
            print(json.dumps({"schema": "mana.review-scheduler.error/v1", "code": "service cycle bound is invalid"}, sort_keys=True)); return 2
        try:
            return run_service(args)
        except catalog.BusyError:
            print(json.dumps({"schema": "mana.review-scheduler.error/v1", "code": "scheduler-busy"}, sort_keys=True)); return 6
        except (ValueError, OSError, sqlite3.DatabaseError) as error:
            print(json.dumps({"schema": "mana.review-scheduler.error/v1", "code": str(error)}, sort_keys=True)); return 2
    root, database, lock_path = locations()
    if args.command == "status" and not database.exists():
        print(json.dumps({"schema": "mana.review-scheduler.status/v1", "configured": False, "enabled": False, "state": "missing", "policy": None, "credentials_stored": False, "counts": {}}, sort_keys=True)); return 0
    root.mkdir(parents=True, exist_ok=True)
    try:
        with catalog.lock(lock_path):
            connection = connect(database)
            try:
                config = configured(connection)
                if args.command == "configure":
                    config = validate_config(json.loads(args.config.read_text(encoding="utf-8")))
                    with connection: connection.execute("INSERT OR REPLACE INTO metadata VALUES('config',?)", (json.dumps(config, separators=(",", ":"), sort_keys=True),))
                    response = {"schema": "mana.review-scheduler.configure-receipt/v1", "enabled": config["enabled"], "repositories": config["repositories"], "organizations": config["organizations"], "policy": config["policy"], "credentials_stored": False}
                elif args.command == "status":
                    response = {"schema": "mana.review-scheduler.status/v1", "configured": config is not None, "enabled": bool(config and config["enabled"]), "state": "current", "policy": config.get("policy") if config else None, "credentials_stored": False, "counts": dict(connection.execute("SELECT status,count(*) FROM inbox GROUP BY status").fetchall())}
                elif config is None:
                    raise ValueError("review scheduler is not configured")
                elif args.command == "cycle":
                    if not config["enabled"]:
                        response = {"schema": "mana.review-scheduler.cycle/v1", "outcome": "disabled", "discovered": 0, "created": 0, "duplicates": 0, "analysed": 0, "provider_calls": 0}
                    else:
                        items = load_discovery(args.discovery_file, config) if args.discovery_file else live_discovery(connection, config)
                        created, duplicates = discover_cycle(connection, config, items)
                        fixture = json.loads(args.analysis_fixture.read_text(encoding="utf-8")) if args.analysis_fixture else None
                        if fixture is not None and (fixture.get("schema") != "mana.review-scheduler.analysis-fixture/v1" or not isinstance(fixture.get("runs"), list)):
                            raise ValueError("analysis fixture is invalid")
                        analysed, provider_calls = analyse(connection, config, fixture)
                        response = {"schema": "mana.review-scheduler.cycle/v1", "outcome": "completed", "discovered": len(items), "created": created, "duplicates": duplicates, "analysed": analysed, "provider_calls": provider_calls}
                elif args.command == "inbox":
                    if not 1 <= args.limit <= 200: raise ValueError("inbox limit is invalid")
                    rows = connection.execute("SELECT * FROM inbox WHERE (? IS NULL OR status=?) ORDER BY stale,updated_at DESC,run_id LIMIT ?", (args.status, args.status, args.limit)).fetchall()
                    response = {"schema": "mana.review-scheduler.inbox/v1", "items": [public_row(row) for row in rows]}
                elif args.command == "show":
                    row = connection.execute("SELECT * FROM inbox WHERE run_id=?", (args.run_id,)).fetchone()
                    if row is None: raise ValueError("review run is unavailable")
                    response = {"schema": "mana.review-scheduler.run/v1", "run": public_row(row, True)}
                elif args.command == "retry":
                    row = connection.execute("SELECT * FROM inbox WHERE run_id=?", (args.run_id,)).fetchone()
                    if row is None or row["stale"] or row["status"] not in {"failed", "interrupted", "cancelled"}: raise ValueError("review run is not retryable")
                    if args.expected_draft_revision and args.expected_draft_revision != row["draft_revision"]: raise ValueError("draft revision conflict")
                    with connection: connection.execute("UPDATE inbox SET status='queued',error_code=NULL,changed_at=? WHERE run_id=?", (now(), args.run_id))
                    response = {"schema": "mana.review-scheduler.action-receipt/v1", "action": "retry", "run_id": args.run_id, "outcome": "queued"}
                elif args.command == "cancel":
                    row = connection.execute("SELECT * FROM inbox WHERE run_id=?", (args.run_id,)).fetchone()
                    if row is None or row["stale"] or row["status"] not in {"queued", "running"}: raise ValueError("review run is not cancellable")
                    with connection: connection.execute("UPDATE inbox SET status='cancelled',lease_until=NULL,changed_at=? WHERE run_id=?", (now(), args.run_id))
                    response = {"schema": "mana.review-scheduler.action-receipt/v1", "action": "cancel", "run_id": args.run_id, "outcome": "cancelled"}
                else:
                    row = connection.execute("SELECT * FROM inbox WHERE run_id=?", (args.run_id,)).fetchone()
                    if not args.confirm or row is None or row["stale"] or row["status"] != "completed" or row["publication_status"] not in {None, "publication_failed"} or row["head_sha"] != args.head_sha or row["draft_revision"] != args.draft_revision: raise ValueError("publication precondition failed")
                    findings = json.loads(row["findings_json"] or "[]")
                    if not any(item["draft_id"] == args.draft_id for item in findings): raise ValueError("selected draft is unavailable")
                    publication = {"published": "published", "unknown": "publication_unknown", "failed": "publication_failed"}[args.fake_result]
                    with connection: connection.execute("UPDATE inbox SET publication_status=?,changed_at=? WHERE run_id=?", (publication, now(), args.run_id))
                    response = {"schema": "mana.review-scheduler.publication-receipt/v1", "run_id": args.run_id, "head_sha": args.head_sha, "draft_revision": args.draft_revision, "draft_id": args.draft_id, "outcome": publication, "boundary": "fake"}
            finally:
                connection.close()
    except catalog.BusyError:
        print(json.dumps({"schema": "mana.review-scheduler.error/v1", "code": "scheduler-busy"}, sort_keys=True)); return 6
    except (ValueError, OSError, sqlite3.DatabaseError, ConnectionError, json.JSONDecodeError) as error:
        print(json.dumps({"schema": "mana.review-scheduler.error/v1", "code": str(error)}, sort_keys=True)); return 2
    print(json.dumps(response, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
