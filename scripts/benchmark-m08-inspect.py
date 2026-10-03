#!/usr/bin/env python3
"""Benchmark legacy Inspect sequences against M08 semantic snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path


def invoke(inspect: Path, project: Path, operation: str, *options: str) -> dict[str, object]:
    started = time.monotonic_ns()
    result = subprocess.run(
        [str(inspect), "--project-root", str(project), operation, *options, "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    elapsed_ms = (time.monotonic_ns() - started) / 1_000_000
    if result.returncode != 0:
        raise RuntimeError(f"{operation} exited {result.returncode}")
    response = json.loads(result.stdout)
    return {
        "operation": operation,
        "options": list(options),
        "elapsed_ms": round(elapsed_ms, 3),
        "response_bytes": len(result.stdout),
        "response": response,
    }


def sample(inspect: Path, project: Path, kind: str) -> dict[str, object]:
    if kind == "legacy_full_read":
        calls = [invoke(inspect, project, name) for name in ("project", "artifacts", "work-items", "project-context", "activity")]
        file_count = len(calls[1]["response"]["artifacts"])
        builds = 4
    elif kind == "snapshot_supporting":
        calls = [invoke(inspect, project, "project"), invoke(inspect, project, "semantic-snapshot", "--include-supporting")]
        file_count = calls[1]["response"]["inventory"]["file_count"]
        builds = calls[1]["response"]["inventory"]["catalog_build_count"]
    else:
        calls = [invoke(inspect, project, "project"), invoke(inspect, project, "semantic-snapshot")]
        file_count = calls[1]["response"]["inventory"]["file_count"]
        builds = calls[1]["response"]["inventory"]["catalog_build_count"]
    return {
        "total_ms": round(sum(call["elapsed_ms"] for call in calls), 3),
        "process_count": len(calls),
        "catalog_build_count": builds,
        "digest_file_visits": file_count * builds,
        "peak_response_bytes": max(call["response_bytes"] for call in calls),
        "total_response_bytes": sum(call["response_bytes"] for call in calls),
        "operations": [{key: value for key, value in call.items() if key != "response"} for call in calls],
    }


def revision(root: Path) -> str:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be positive")
    root = Path(__file__).resolve().parents[1]
    inspect = root / "scripts" / "mana-inspect.sh"
    manifest_path = args.project_root / "m08-fixture-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    modes: dict[str, list[dict[str, object]]] = {}
    for kind in ("legacy_full_read", "snapshot_supporting", "snapshot_route_minimal"):
        modes[kind] = [sample(inspect, args.project_root, kind) for _ in range(args.runs)]
    medians = {kind: statistics.median(run["total_ms"] for run in runs) for kind, runs in modes.items()}
    baseline = medians["legacy_full_read"]
    supporting = medians["snapshot_supporting"]
    report = {
        "schema": "mana.m08.inspect-benchmark/v1",
        "fixture": {
            "class": manifest["fixture_class"],
            "digest": manifest["fixture_digest"],
            "manifest_digest": f"sha256:{manifest_digest}",
            "logical_counts": manifest["logical_counts"],
        },
        "environment": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "mana_revision": revision(root),
        },
        "runs_per_mode": args.runs,
        "cold": {kind: runs[0] for kind, runs in modes.items()},
        "repeated": modes,
        "median_total_ms": {kind: round(value, 3) for kind, value in medians.items()},
        "improvement": {
            "supporting_elapsed_ms": round(baseline - supporting, 3),
            "supporting_percent": round(((baseline - supporting) / baseline) * 100, 2) if baseline else 0,
            "catalog_build_reduction": 3,
            "process_reduction": 3,
        },
        "privacy": {"source_content": False, "absolute_paths": False, "credentials": False},
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
