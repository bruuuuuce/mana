#!/usr/bin/env python3
"""Paginated reads must accept a collection larger than an exec argument."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash.exe" if os.name == "nt" else "bash")
with tempfile.TemporaryDirectory(prefix="mana-feedback-large-reads-") as temporary:
    project = Path(temporary)
    artifact = project / "report.md"
    artifact.write_text("# Synthetic large feedback\n")
    target = dict(artifactId="file:report.md", artifactRevision="sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest())
    def invoke(action, fields):
        completed = subprocess.run([BASH, str(ROOT / "scripts/mana-human-feedback.sh"), "--project-root", str(project), action, "--request-stdin", "--json"], input=json.dumps(fields).encode(), capture_output=True, timeout=60)
        assert completed.returncode == 0, completed.stderr.decode()
        return json.loads(completed.stdout)
    expected = {}
    for ordinal in range(24):
        body = f"Synthetic large comment {ordinal}\n" + "x" * 60000
        created = invoke("create", dict(**target, author="Synthetic acceptance", body=body, idempotencyKey=f"large-{ordinal}"))
        expected[created["threadId"]] = body
    storage = project / ".mana/human-feedback"
    def snapshot():
        return {str(p.relative_to(storage)): hashlib.sha256(p.read_bytes()).hexdigest() for p in storage.rglob("*") if p.is_file()}
    before = snapshot()
    for action in ("list", "list-history"):
        seen = {}; cursor = ""; revisions = set()
        while True:
            page = invoke(action, dict(**target, cursor=cursor, limit="2"))
            revisions.add(page["viewRevision"])
            assert len(page["threads"]) <= 2
            for thread in page["threads"]:
                assert thread["threadId"] not in seen
                seen[thread["threadId"]] = thread["entries"][0]["body"]
            cursor = page["nextCursor"]
            if not cursor:
                break
        assert seen == expected and len(revisions) == 1
        assert snapshot() == before, "read mutated canonical storage"
    # Reject malformed canonical records on both indexed and fallback reads.
    first = next((storage / "threads").glob("*.json"))
    invalid = json.loads(first.read_bytes()); invalid["revision"] = "invalid"
    first.write_text(json.dumps(invalid))
    for fallback in (False, True):
        if fallback:
            (storage / "indexes/.target-index-v1-ready.json").unlink()
        corrupted = snapshot()
        for action in ("list", "list-history"):
            result = subprocess.run([BASH, str(ROOT / "scripts/mana-human-feedback.sh"), "--project-root", str(project), action, "--request-stdin", "--json"], input=json.dumps(target).encode(), capture_output=True, timeout=60)
            assert result.returncode != 0 and b"malformed thread record" in result.stderr, (fallback, action, result.returncode, result.stderr.decode())
            assert snapshot() == corrupted
print("Human Feedback large paginated reads: PASS")
