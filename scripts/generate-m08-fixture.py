#!/usr/bin/env python3
"""Generate deterministic synthetic .mana workspaces for M08 performance gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from pathlib import Path


CLASSES = {
    "small": {"artifacts": 100, "work_items": 10, "runtime_events": 100, "knowledge_documents": 20},
    "medium": {"artifacts": 1_000, "work_items": 100, "runtime_events": 5_000, "knowledge_documents": 200},
    "large": {"artifacts": 10_000, "work_items": 500, "runtime_events": 50_000, "knowledge_documents": 2_000},
    "hostile-large": {"artifacts": 10_000, "work_items": 500, "runtime_events": 50_000, "knowledge_documents": 2_000},
}


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def inventory(root: Path) -> tuple[int, int, str]:
    records: list[str] = []
    total = 0
    count = 0
    for path in sorted(root.joinpath(".mana").rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(data).hexdigest()
        records.append(f"{relative}\0{len(data)}\0{digest}\n")
        total += len(data)
        count += 1
    return count, total, hashlib.sha256("".join(records).encode()).hexdigest()


def generate(root: Path, fixture_class: str, seed: int) -> dict[str, object]:
    spec = CLASSES[fixture_class]
    rng = random.Random(seed)
    root.mkdir(parents=True, exist_ok=False)
    mana = root / ".mana"
    mana.mkdir()

    for index in range(spec["work_items"]):
        workspace = mana / "features" / f"SYN-{index:05d}"
        write(
            workspace / "manifest.yaml",
            "\n".join(
                [
                    "workspace_type: feature",
                    f"workspace_id: SYN-{index:05d}",
                    f"feature_id: SYN-{index:05d}",
                    f"purpose: Synthetic work item {index}",
                    f"branch: fixture/syn-{index:05d}",
                    "canonical_branch: false",
                    "",
                ]
            ),
        )

    for index in range(spec["knowledge_documents"]):
        topic = rng.randrange(10_000_000)
        write(
            mana / "global" / "knowledge" / f"document-{index:05d}.md",
            f"# Synthetic knowledge {index}\n\nTopic {topic}. Deterministic fixture content.\n",
        )

    event_shards = (spec["runtime_events"] + 999) // 1000
    for shard in range(event_shards):
        start = shard * 1000
        stop = min(start + 1000, spec["runtime_events"])
        lines = [
            json.dumps(
                {
                    "eventId": f"evt-{index:07d}",
                    "timestamp": f"2026-01-{(index % 28) + 1:02d}T{index % 24:02d}:00:00Z",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            for index in range(start, stop)
        ]
        write(mana / "runtime" / "events" / f"events-{shard:04d}.jsonl", "\n".join(lines) + "\n")

    write(
        mana / "learning" / "journeys" / "jrn_000000000000000000000000" / "journey.yaml",
        '{"schema":"mana.learning.journey/v1","id":"jrn_000000000000000000000000","title":"Synthetic journey"}\n',
    )
    write(mana / "unknown" / "opaque.bin", b"M08-SYNTHETIC\x00DATA")

    current_count, _, _ = inventory(root)
    filler_count = spec["artifacts"] - current_count
    if filler_count < 0:
        raise RuntimeError(f"fixture structure exceeds artifact budget: {current_count}>{spec['artifacts']}")
    for index in range(filler_count):
        write(
            mana / "synthetic" / f"artifact-{index:05d}.md",
            f"# Synthetic artifact {index}\n\nSeed {seed}; value {rng.randrange(1_000_000_000)}.\n",
        )

    hostile_entries = 0
    if fixture_class == "hostile-large":
        write(mana / "hostile" / "malformed.json", "{not-json\n")
        write(mana / "hostile" / "oversize.md", "x" * 70_000)
        os.symlink("../../outside", mana / "hostile" / "escaping-link")
        hostile_entries = 3

    file_count, byte_count, digest = inventory(root)
    if file_count != spec["artifacts"] + (2 if fixture_class == "hostile-large" else 0):
        raise RuntimeError("generated regular-file count does not match the declared inventory")
    report = {
        "schema": "mana.m08.fixture/v1",
        "fixture_class": fixture_class,
        "seed": seed,
        "logical_counts": spec,
        "generated": {
            "regular_files": file_count,
            "symlinks": 1 if fixture_class == "hostile-large" else 0,
            "hostile_entries": hostile_entries,
            "bytes": byte_count,
        },
        "fixture_digest": f"sha256:{digest}",
        "contains_customer_data": False,
        "network_calls": 0,
        "model_calls": 0,
    }
    write(root / "m08-fixture-manifest.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--class", dest="fixture_class", choices=sorted(CLASSES), required=True)
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("output path already exists; choose an empty new path")
    report = generate(args.output, args.fixture_class, args.seed)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
