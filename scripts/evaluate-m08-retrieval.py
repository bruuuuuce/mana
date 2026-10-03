#!/usr/bin/env python3
"""Evaluate M08 lexical retrieval independently from generated answers."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEARCH = ROOT / "scripts" / "mana-knowledge.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--corpus", default=ROOT / "evals" / "m08-lexical-retrieval-v1.json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache-home", type=Path)
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    if corpus.get("schema") != "mana.knowledge.evaluation-corpus/v1" or len(corpus.get("questions", [])) < 30:
        raise SystemExit("evaluation corpus is malformed or too small")
    results = []
    for case in corpus["questions"]:
        command = [str(SEARCH), "--project-root", str(args.project_root), "search", "--query", case["query"], "--limit", str(corpus["limits"]["top_k"]), "--max-bytes", str(corpus["limits"]["max_returned_bytes"])]
        for scope in case["scopes"]:
            command.extend(["--scope", scope])
        for lifecycle in case["lifecycles"]:
            command.extend(["--lifecycle", lifecycle])
        command.append("--json")
        environment = None
        if args.cache_home:
            import os

            environment = {**os.environ, "MANA_CACHE_HOME": str(args.cache_home)}
        started = time.monotonic_ns()
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
        elapsed_ms = (time.monotonic_ns() - started) / 1_000_000
        if process.returncode != 0:
            raise SystemExit(f"evaluation search {case['id']} exited {process.returncode}")
        response = json.loads(process.stdout)
        returned = [item["source_reference"] for item in response["results"]]
        relevant = set(case["relevant"])
        retrieved_relevant = relevant.intersection(returned)
        if relevant:
            recall = len(retrieved_relevant) / len(relevant)
            precision = len(retrieved_relevant) / len(returned) if returned else 0.0
        else:
            recall = 1.0 if not returned else 0.0
            precision = 1.0 if not returned else 0.0
        scope_errors = sum(1 for item in response["results"] if item["source_scope"] not in case["scopes"])
        trap_hits = sorted(set(case.get("irrelevant_traps", [])).intersection(returned))
        results.append({"id": case["id"], "recall_at_k": round(recall, 4), "precision_at_k": round(precision, 4), "returned_bytes": response.get("returned_bytes", 0), "latency_ms": round(elapsed_ms, 3), "freshness": response["index"]["freshness"], "source_scope_errors": scope_errors, "irrelevant_trap_hits": trap_hits, "returned": returned})
    report = {"schema": "mana.knowledge.retrieval-evaluation/v1", "corpus_schema": corpus["schema"], "question_count": len(results), "limits": corpus["limits"], "aggregate": {"mean_recall_at_k": round(statistics.mean(item["recall_at_k"] for item in results), 4), "mean_precision_at_k": round(statistics.mean(item["precision_at_k"] for item in results), 4), "median_latency_ms": round(statistics.median(item["latency_ms"] for item in results), 3), "max_returned_bytes": max(item["returned_bytes"] for item in results), "freshness_errors": sum(item["freshness"] != "current" for item in results), "source_scope_errors": sum(item["source_scope_errors"] for item in results), "irrelevant_trap_hits": sum(len(item["irrelevant_trap_hits"]) for item in results)}, "answer_quality_evaluated": False, "results": results}
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
