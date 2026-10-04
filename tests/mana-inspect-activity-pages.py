#!/usr/bin/env python3
"""Real producer pagination: complete traversal, stable order and stale cursors."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def command(project, *arguments):
    return subprocess.run(["bash", str(ROOT / "scripts/mana-inspect.sh"), "--project-root", str(project), *arguments, "--json"], capture_output=True, text=True)


with tempfile.TemporaryDirectory(prefix="mana-activity-pages-") as temporary:
    project = Path(temporary)
    events = project / ".mana/runtime/events/synthetic.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text("".join(json.dumps({"eventId": f"synthetic:{i:05}", "timestamp": "2026-10-04T08:00:00Z"}) + "\n" for i in range(12050)))
    before = {path.relative_to(project).as_posix(): path.read_bytes() for path in project.rglob("*") if path.is_file()}
    full = command(project, "activity")
    assert full.returncode == 0, full.stderr
    expected = json.loads(full.stdout)["events"]
    found, cursor, first = [], None, None
    while True:
        args = ["activity-page", "--limit", "500"]
        if cursor:
            args += ["--cursor", cursor]
        result = command(project, *args)
        assert result.returncode == 0, result.stderr
        page = json.loads(result.stdout)
        if first is None:
            first = page
        assert page["schema"] == "mana.inspect.activity-page/v1"
        assert page["view_revision"] == first["view_revision"]
        assert page["total_events"] == len(expected)
        assert len(page["events"]) <= 500
        assert page["guarantees"]["writes"] is False
        found.extend(page["events"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert found == expected
    assert len({item["event_id"] for item in found}) == len(found)
    after = {path.relative_to(project).as_posix(): path.read_bytes() for path in project.rglob("*") if path.is_file()}
    assert before == after, "Inspect wrote to canonical or derived storage"
    for invalid in ("../cursor", "f" * 64 + ":9999999999"):
        assert command(project, "activity-page", "--cursor", invalid).returncode != 0
    assert command(project, "activity-page", "--limit", "501").returncode != 0
    with events.open("a") as handle:
        handle.write(json.dumps({"eventId": "synthetic:new", "timestamp": "2026-10-04T08:00:01Z"}) + "\n")
    stale = command(project, "activity-page", "--cursor", first["next_cursor"])
    assert stale.returncode != 0 and "activity_view_changed" in stale.stderr
    print(f"Activity pages: all {len(found)} events traversed once in producer order; stale/malformed cursors rejected; no writes")
